"""  
Inbound message processing pipeline — Flow AI engine core.

Pipeline (Slice 3):
    1. Load client config + DB connection
    2. Log inbound to interactions_log (always first, before any other processing)
    3. Escalation gate — query customers table
    4. If escalation_flag=True: send holding reply, log outbound, return
    5. Upsert customer record (INSERT new / UPDATE last_seen for existing)
    6. Log "Escalation gate passed" → return  (Slice 4 adds agent invocation)

All exceptions are caught at the outer level — nothing propagates to the webhook.
The webhook has already returned 200 to Meta before this function runs.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone

from engine.config.client_config import load_client_config, ClientNotFoundError
from engine.integrations.supabase_client import get_client_db
from engine.integrations.meta_whatsapp import send_message
from engine.integrations.google_sheets import sync_customer_to_sheets
from engine.core.context_builder import build_system_message, fetch_conversation_history
from engine.core.agent_runner import run_agent
from engine.core.tools import TOOL_DEFINITIONS, build_tool_dispatch

logger = logging.getLogger(__name__)

# Per-customer asyncio locks — serialize agent invocations for the same phone number.
# Prevents race conditions when a customer sends multiple messages in rapid succession:
# without this, concurrent background tasks read stale conversation history and
# produce duplicate/conflicting agent responses.
_customer_locks: dict[str, asyncio.Lock] = {}


def _get_customer_lock(phone_number: str) -> asyncio.Lock:
    """Return (or create) the asyncio.Lock for a given phone number."""
    if phone_number not in _customer_locks:
        _customer_locks[phone_number] = asyncio.Lock()
    return _customer_locks[phone_number]

# Sent to the customer when their escalation_flag is True.
# Human agent will follow up directly.
HOLDING_REPLY = (
    "Thank you for reaching out. "
    "A member of our team will get back to you today."
)

# Sent when a critical Supabase failure prevents normal processing.
FALLBACK_REPLY = (
    "We're experiencing a technical issue right now. "
    "Please try again in a moment, or call us directly. "
    "We apologise for the inconvenience."
)

_AFFIRMATIVE_CONFIRMATION_PATTERNS = [
    "yes",
    "y",
    "ok",
    "okay",
    "confirm",
    "confirmed",
    "sure",
    "correct",
    "yep",
    "yup",
    "go ahead",
    "sounds good",
    "looks good",
    "yes please",
    "ok can",
    "can",
]


def _is_affirmative_confirmation(message_text: str) -> bool:
    """Return True when the inbound is a plain confirmation to a pending summary."""
    normalised = re.sub(r"[^a-z0-9\s]+", " ", (message_text or "").lower())
    normalised = " ".join(normalised.split())
    return normalised in _AFFIRMATIVE_CONFIRMATION_PATTERNS


def _remove_current_inbound_from_history(
    history: list[dict],
    current_message: str,
) -> list[dict]:
    """Drop the just-logged inbound row so the LLM does not see it twice."""
    if not history:
        return history

    last_message = history[-1]
    if (
        last_message.get("role") == "user"
        and (last_message.get("content") or "") == current_message
    ):
        return history[:-1]
    return history


async def _get_latest_pending_booking(db, phone_number: str) -> dict | None:
    """Fetch the newest pending_confirmation booking for this customer."""
    try:
        result = await (
            db.table("bookings")
            .select("booking_id, service_type, slot_date, slot_window, address, postal_code, created_at")
            .eq("phone_number", phone_number)
            .eq("booking_status", "pending_confirmation")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.warning(
            "Failed to fetch latest pending booking for %s: %s",
            phone_number,
            e,
            exc_info=True,
        )
        return None

    if not result.data:
        return None

    booking = result.data[0]
    if not booking.get("booking_id"):
        return None
    return booking


async def handle_inbound_message(
    client_id: str,
    phone_number: str,
    message_text: str,
    message_type: str,
    message_id: str,
    display_name: str,
    context_message_id: str | None = None,
) -> None:
    """
    Full inbound message processing pipeline.

    Runs as a FastAPI background task after the webhook returns 200 to Meta.
    All exceptions are caught — nothing propagates out of this function.

    Args:
        client_id:           Client slug (e.g. "hey-aircon").
        phone_number:        Sender's WhatsApp number (E.164 without +, e.g. "6591234567").
        message_text:        Extracted message body (empty string for non-text types).
        message_type:        Meta message type string (e.g. "text", "image", "audio").
        message_id:          Meta message ID (wamid.xxx).
        display_name:        Sender's WhatsApp display name.
        context_message_id:  wamid of the message being replied to (None if not a reply).
    """
    try:
        # ── Step 1: Load client config and DB connection ──────────────────────
        client_config = await load_client_config(client_id)
        db = await get_client_db(client_id)

        # ── Step 0: Human agent routing (inserted before inbound log) ─────────
        if phone_number == client_config.human_agent_number:
            logger.info(
                f"Human agent message detected from {phone_number} (client: {client_id})"
            )
            from engine.core.reset_handler import handle_human_agent_message
            await handle_human_agent_message(
                db=db,
                client_config=client_config,
                phone_number=phone_number,
                message_text=message_text,
                context_message_id=context_message_id,
            )
            return  # Do NOT log to interactions_log, do NOT run agent

        now = datetime.now(timezone.utc).isoformat()

        # ── Step 2: Log inbound (ALWAYS first, before any other processing) ───
        try:
            await db.table("interactions_log").insert({
                "timestamp": now,
                "phone_number": phone_number,
                "direction": "inbound",
                "message_text": message_text,
                "message_type": message_type,
            }).execute()
            logger.info(
                f"Inbound logged for {phone_number} "
                f"(client: {client_id}, type: {message_type}, id: {message_id})"
            )
        except Exception as e:
            logger.error(
                f"Failed to log inbound message for {phone_number}: {e}",
                exc_info=True,
            )
            # Continue — a logging failure is not fatal.

        # ── Step 3: Escalation gate — query customer record ───────────────────
        try:
            result = (
                await db.table("customers")
                .select("*")
                .eq("phone_number", phone_number)
                .limit(1)
                .execute()
            )
            customer_row = result.data[0] if result.data else None
        except Exception as e:
            logger.error(
                f"Failed to query customer record for {phone_number}: {e}",
                exc_info=True,
            )
            # Critical DB failure — send fallback reply and exit cleanly.
            _now = datetime.now(timezone.utc).isoformat()
            try:
                await send_message(client_config, phone_number, FALLBACK_REPLY)
                await db.table("interactions_log").insert({
                    "timestamp": _now,
                    "phone_number": phone_number,
                    "direction": "outbound",
                    "message_text": FALLBACK_REPLY,
                    "message_type": "text",
                }).execute()
            except Exception:
                pass  # Even the fallback failed — log already captured above.
            return

        # ── Step 4: Hard escalation gate (programmatic — never an agent decision) ──
        if customer_row and customer_row.get("escalation_flag") is True:
            already_notified = customer_row.get("escalation_notified", False)
            if already_notified:
                # Holding reply already sent for this escalation — silently drop.
                # Human agent is handling the conversation directly; no reply needed.
                logger.info(
                    f"Escalation gate BLOCKED (silent) for {phone_number} (client: {client_id}) — "
                    f"holding reply already sent, dropping message"
                )
                return

            # First message since escalation — send holding reply once.
            logger.info(
                f"Escalation gate BLOCKED for {phone_number} (client: {client_id}) — "
                f"reason: {customer_row.get('escalation_reason', 'not set')}"
            )
            _now = datetime.now(timezone.utc).isoformat()
            try:
                await send_message(client_config, phone_number, HOLDING_REPLY)
                await db.table("interactions_log").insert({
                    "timestamp": _now,
                    "phone_number": phone_number,
                    "direction": "outbound",
                    "message_text": HOLDING_REPLY,
                    "message_type": "text",
                }).execute()
                # Mark notified so subsequent messages are silently dropped.
                await db.table("customers").update({
                    "escalation_notified": True,
                }).eq("phone_number", phone_number).execute()
            except Exception as e:
                logger.error(
                    f"Failed to send/log holding reply to {phone_number}: {e}",
                    exc_info=True,
                )
            return  # Agent does NOT run for escalated customers.

        # ── Step 5: Upsert customer record ────────────────────────────────────
        # Use upsert with ignore_duplicates=True (ON CONFLICT DO NOTHING) to
        # guard against WhatsApp double-delivery: two concurrent webhooks for
        # the same message both see customer_row=None at Step 3 and both reach
        # here. Only one INSERT wins; the second is a silent no-op.
        # Requires UNIQUE constraint on customers(phone_number) in Supabase.
        try:
            _now = datetime.now(timezone.utc).isoformat()
            if customer_row is None:
                insert_result = await db.table("customers").upsert(
                    {
                        "phone_number": phone_number,
                        "customer_name": display_name,
                        "first_seen": now,
                        "last_seen": now,
                        "escalation_flag": False,
                    },
                    on_conflict="phone_number",
                    ignore_duplicates=True,
                ).execute()
                if insert_result.data:
                    logger.info(
                        f"New customer created: {phone_number} (client: {client_id})"
                    )
                    asyncio.create_task(sync_customer_to_sheets(
                        client_id=client_id,
                        client_config=client_config,
                        customer_data=insert_result.data[0],
                    ))
                else:
                    logger.debug(
                        f"Customer insert no-op (race condition suppressed): {phone_number}"
                    )
            else:
                # Returning customer — update last_seen only.
                await db.table("customers").update({
                    "last_seen": _now,
                }).eq("phone_number", phone_number).execute()
                logger.debug(
                    f"Returning customer last_seen updated: {phone_number}"
                )
                # Sync to Sheets (fire-and-forget)
                updated_customer = {**customer_row, "last_seen": _now}
                asyncio.create_task(sync_customer_to_sheets(
                    client_id=client_id,
                    client_config=client_config,
                    customer_data=updated_customer,
                ))
        except Exception as e:
            logger.error(
                f"Failed to upsert customer record for {phone_number}: {e}",
                exc_info=True,
            )
            # Upsert failure is non-fatal — continue to agent.

        # ── Step 6: Context builder → agent runner → send reply ───────────────
        # Acquire per-customer lock before running the agent. This serializes
        # concurrent background tasks for the same customer so each agent turn
        # reads a fully up-to-date conversation history (including replies from
        # the preceding turn). Without this, rapid successive messages produce
        # parallel agent invocations with stale history.
        logger.info(
            f"Escalation gate passed for {phone_number} (client: {client_id}) — "
            "invoking agent"
        )
        async with _get_customer_lock(phone_number):
            try:
                tool_dispatch = build_tool_dispatch(db, client_config, phone_number)
                pending_booking = await _get_latest_pending_booking(db, phone_number)

                if pending_booking and _is_affirmative_confirmation(message_text):
                    logger.info(
                        "Affirmative confirmation detected for pending booking %s — bypassing LLM",
                        pending_booking["booking_id"],
                    )
                    confirm_result = await tool_dispatch["confirm_booking"](
                        booking_id=pending_booking["booking_id"]
                    )
                    agent_reply = confirm_result.get("message") or FALLBACK_REPLY
                else:
                    system_message = await build_system_message(db)
                    known_name = (customer_row or {}).get("customer_name") if customer_row else None
                    if known_name:
                        system_message += (
                            f"\n\nCURRENT CUSTOMER:\n"
                            f"Name: {known_name}\n"
                            f"Use this name when calling write_booking — do NOT ask the customer "
                            f"for their name again unless they say it has changed.\n"
                        )
                    if pending_booking:
                        system_message += (
                            "\n\nLATEST PENDING BOOKING:\n"
                            f"Reference: {pending_booking['booking_id']}\n"
                            f"Service: {pending_booking['service_type']}\n"
                            f"Date: {pending_booking['slot_date']}\n"
                            f"Time: {pending_booking['slot_window']}\n"
                            f"Address: {pending_booking['address']}, Singapore {pending_booking['postal_code']}\n"
                            "If the customer is affirming this pending booking summary, call confirm_booking "
                            "with this exact booking_id. Do NOT call write_booking again for the same pending booking.\n"
                        )
                    history = await fetch_conversation_history(db, phone_number)
                    history = _remove_current_inbound_from_history(history, message_text)
                    agent_reply = await run_agent(
                        system_message=system_message,
                        conversation_history=history,
                        current_message=message_text,
                        tool_definitions=TOOL_DEFINITIONS,
                        tool_dispatch=tool_dispatch,
                        client_id=client_id,
                        anthropic_api_key=client_config.anthropic_api_key,
                        openai_api_key=client_config.openai_api_key,
                    )
            except Exception as e:
                logger.error(
                    f"Agent error for {phone_number} (client: {client_id}): {e}",
                    exc_info=True,
                )
                agent_reply = FALLBACK_REPLY

            # ── Step 7: Send reply + log outbound ─────────────────────────────
            # Inside the lock so the next waiting task sees this reply in history.
            _now = datetime.now(timezone.utc).isoformat()
            try:
                await send_message(client_config, phone_number, agent_reply)
                await db.table("interactions_log").insert({
                    "timestamp": _now,
                    "phone_number": phone_number,
                    "direction": "outbound",
                    "message_text": agent_reply,
                    "message_type": "text",
                }).execute()
                logger.info(f"Reply sent and logged for {phone_number}")
            except Exception as e:
                logger.error(
                    f"Failed to send/log agent reply to {phone_number}: {e}",
                    exc_info=True,
                )

    except ClientNotFoundError:
        logger.error(
            f"Unknown client '{client_id}' — cannot process message from {phone_number}"
        )
    except Exception as e:
        logger.error(
            f"Unhandled error in handle_inbound_message "
            f"(client: {client_id}, phone: {phone_number}): {e}",
            exc_info=True,
        )
