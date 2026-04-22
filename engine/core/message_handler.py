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
    "A member of our team will get back to you shortly."
)

# Sent when a critical Supabase failure prevents normal processing.
FALLBACK_REPLY = (
    "We're experiencing a technical issue right now. "
    "Please try again in a moment, or call us directly. "
    "We apologise for the inconvenience."
)


async def handle_inbound_message(
    client_id: str,
    phone_number: str,
    message_text: str,
    message_type: str,
    message_id: str,
    display_name: str,
) -> None:
    """
    Full inbound message processing pipeline.

    Runs as a FastAPI background task after the webhook returns 200 to Meta.
    All exceptions are caught — nothing propagates out of this function.

    Args:
        client_id:    Client slug (e.g. "hey-aircon").
        phone_number: Sender's WhatsApp number (E.164 without +, e.g. "6591234567").
        message_text: Extracted message body (empty string for non-text types).
        message_type: Meta message type string (e.g. "text", "image", "audio").
        message_id:   Meta message ID (wamid.xxx).
        display_name: Sender's WhatsApp display name.
    """
    try:
        # ── Step 1: Load client config and DB connection ──────────────────────
        client_config = await load_client_config(client_id)
        db = await get_client_db(client_id)

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
                system_message = await build_system_message(db)
                history = await fetch_conversation_history(db, phone_number)
                tool_dispatch = build_tool_dispatch(db, client_config, phone_number)
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
