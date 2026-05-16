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
from datetime import datetime, timezone, timedelta, time as dt_time
from zoneinfo import ZoneInfo

from engine.config.client_config import load_client_config, ClientNotFoundError
from engine.integrations.supabase_client import get_client_db
from engine.integrations.meta_whatsapp import send_message
from engine.integrations.google_sheets import sync_customer_to_sheets
from engine.core.context_builder import build_system_message, fetch_conversation_history, fetch_lead_days, fetch_appointment_windows
from engine.core.agent_runner import run_agent
from engine.core.tools import build_tool_definitions, build_tool_dispatch

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

# Opt-out keywords — case-insensitive, matched against stripped normalised input.
# These stop the follow-up sequence for the customer's latest pending booking.
_OPT_OUT_KEYWORDS = frozenset({
    "stop",
    "unsubscribe",
    "opt out",
    "opt-out",
    "no follow up",
    "no follow-up",
    "stop messaging",
    "stop sending",
    "dont contact me",
    "do not contact me",
    "remove me",
    "no more messages",
    "cancel reminders",
    "cancel follow up",
    "cancel follow-up",
})

OPT_OUT_REPLY = (
    "Understood! We won't send any more follow-up messages about your upcoming appointment. "
    "If you'd like to book a service or need help, feel free to message us anytime."
)

def _is_opt_out_keyword(message_text: str) -> bool:
    """Return True if the message matches a recognised opt-out keyword."""
    normalised = re.sub(r"[^a-z0-9\s]+", " ", (message_text or "").lower())
    normalised = " ".join(normalised.split())
    return normalised in _OPT_OUT_KEYWORDS


def _is_within_ai_hours(client_config) -> bool:
    """
    Check if current time is within AI operational hours for this client.

    Returns:
        True if AI should handle this message, False if out-of-hours.
        Returns True (always active) if ai_active_start_time and ai_active_end_time are both None.
    """
    start_time = client_config.ai_active_start_time
    end_time = client_config.ai_active_end_time
    
    # If both NULL, AI is active 24/7
    if start_time is None and end_time is None:
        return True
    
    # If only one is set (should not happen due to DB constraint, but handle gracefully)
    if start_time is None or end_time is None:
        logger.warning(
            f"Client {client_config.client_id} has partial AI hours config "
            f"(start={start_time}, end={end_time}) — defaulting to 24/7 active"
        )
        return True
    
    # Parse timezone (default to UTC if invalid)
    try:
        tz = ZoneInfo(client_config.timezone)
    except Exception as e:
        logger.error(
            f"Invalid timezone '{client_config.timezone}' for client {client_config.client_id}: {e} "
            f"— defaulting to UTC"
        )
        tz = ZoneInfo("UTC")
    
    # Get current time in client's timezone
    now = datetime.now(tz)
    current_time = now.time()
    
    # Parse start/end times (format: "HH:MM:SS")
    try:
        start_hour, start_min, start_sec = map(int, start_time.split(":"))
        end_hour, end_min, end_sec = map(int, end_time.split(":"))
        start = dt_time(start_hour, start_min, start_sec)
        end = dt_time(end_hour, end_min, end_sec)
    except Exception as e:
        logger.error(
            f"Failed to parse AI hours for client {client_config.client_id}: {e} "
            f"— defaulting to 24/7 active"
        )
        return True
    
    # Edge case: start == end → no active window
    if start == end:
        logger.warning(
            f"Client {client_config.client_id} has AI hours start == end ({start}) — "
            f"no active window (AI inactive 24/7)"
        )
        return False
    
    # Check if current time is within window
    if start <= end:
        # Daytime window (e.g., 09:00 → 18:00)
        return start <= current_time < end
    else:
        # Overnight window (e.g., 18:00 → 09:00)
        return current_time >= start or current_time < end


async def _handle_out_of_hours_message(
    db,
    client_config,
    phone_number: str,
    display_name: str,
    message_text: str,
) -> None:
    """
    Handle a message that arrived outside AI operational hours.
    
    Steps:
    1. Build auto-reply message (with business hours if configured)
    2. Send auto-reply to customer
    3. Log outbound message
    4. Return (do NOT invoke agent)
    """
    # Build auto-reply message
    if client_config.business_start_time and client_config.business_end_time:
        # Format business hours (strip seconds for customer-facing text)
        start = client_config.business_start_time[:5]  # "09:00:00" -> "09:00"
        end = client_config.business_end_time[:5]
        
        # Convert to 12-hour format with am/pm for readability
        def format_12hr(time_str: str) -> str:
            hour, minute = map(int, time_str.split(":"))
            period = "am" if hour < 12 else "pm"
            hour_12 = hour if hour <= 12 else hour - 12
            hour_12 = 12 if hour_12 == 0 else hour_12  # midnight = 12am
            return f"{hour_12}:{minute:02d}{period}"
        
        start_12hr = format_12hr(start)
        end_12hr = format_12hr(end)
        hours_text = f"Our team operates {start_12hr}–{end_12hr}."
    else:
        hours_text = "Our team will respond shortly."
    
    auto_reply = f"Thanks for reaching out! {hours_text} A team member will respond shortly."
    
    # Send auto-reply
    try:
        await send_message(client_config, phone_number, auto_reply)
        logger.info(
            f"Out-of-hours auto-reply sent to {phone_number} (client: {client_config.client_id})"
        )
    except Exception as e:
        logger.error(
            f"Failed to send out-of-hours auto-reply to {phone_number}: {e}",
            exc_info=True,
        )
        # Continue to logging even if send failed
    
    # Log outbound
    try:
        now = datetime.now(timezone.utc).isoformat()
        await db.table("interactions_log").insert({
            "timestamp": now,
            "phone_number": phone_number,
            "direction": "outbound",
            "message_text": auto_reply,
            "message_type": "text",
        }).execute()
    except Exception as e:
        logger.error(
            f"Failed to log out-of-hours auto-reply for {phone_number}: {e}",
            exc_info=True,
        )



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


async def _get_active_followup_booking(db, phone_number: str) -> dict | None:
    """
    Fetch the newest booking eligible for opt-out.

    Eligible = booking_status is 'pending_confirmation' AND followup_stage is NOT already 'opted_out'.
    """
    try:
        result = await (
            db.table("bookings")
            .select("booking_id, followup_stage, booking_status")
            .eq("phone_number", phone_number)
            .eq("booking_status", "pending_confirmation")
            .not_.eq("followup_stage", "opted_out")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(
            "Failed to fetch active followup booking for %s: %s",
            phone_number,
            e,
            exc_info=True,
        )
        return None


async def _handle_takeover_inbound(
    db,
    client_config,
    phone_number: str,
    display_name: str,
    message_text: str,
) -> None:
    """
    Handle a message from a customer who is currently in takeover mode.
    
    Steps:
    1. Forward the message to human_agent_number in real-time
    2. Return (do NOT send AI reply, do NOT invoke agent)
    """
    logger.info(
        f"Takeover gate ACTIVE for {phone_number} (client: {client_config.client_id}) — "
        "forwarding to human agent, AI will not respond"
    )
    
    # Format forward message
    customer_name = display_name or phone_number
    forward_text = (
        f"📥 *{customer_name}* just replied:\n\n"
        f'"{message_text}"\n\n'
        f"(AI is paused. Reply \"done\" to resume AI.)"
    )
    
    # Send forward to human agent
    if client_config.human_agent_number:
        try:
            await send_message(
                client_config=client_config,
                to_phone_number=client_config.human_agent_number,
                text=forward_text,
            )
            logger.info(
                f"Takeover inbound forwarded to {client_config.human_agent_number} "
                f"for customer {phone_number}"
            )
        except Exception as e:
            logger.error(
                f"Failed to forward takeover inbound for {phone_number}: {e}",
                exc_info=True,
            )
            # Non-fatal — continue (human may see message in WhatsApp Business inbox)
    
    # Do NOT send any reply to the customer — complete silence
    # Message is already logged to interactions_log (Step 2 in pipeline)


async def _maybe_send_conversation_alert(
    db,
    client_config,
    phone_number: str,
    display_name: str,
    message_text: str,
) -> None:
    """
    Send a proactive conversation alert to human_agent_number if this is a new session.
    
    A "new session" = only one inbound message from this customer in the last 4 hours
    (the current one just logged).
    
    Alert is sent ONCE per session (not per message) to prevent spam.
    """
    SESSION_TIMEOUT_HOURS = 4
    
    # Check last inbound message timestamp
    # Count how many inbound messages in the session window
    # If count > 1, session is already active (more than just the current message)
    # If count == 1, it's a new session (only the current message is recent)
    try:
        cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=SESSION_TIMEOUT_HOURS)).isoformat()
        result = await (
            db.table("interactions_log")
            .select("timestamp", count="exact")
            .eq("phone_number", phone_number)
            .eq("direction", "inbound")
            .gt("timestamp", cutoff_time)
            .execute()
        )
        
        count = result.count or len(result.data or [])
        if count > 1:
            # Session active (more than just the current message)
            logger.debug(
                f"Conversation session active for {phone_number} — skipping alert"
            )
            return
    except Exception as e:
        logger.error(
            f"Failed to check conversation session for {phone_number}: {e}",
            exc_info=True,
        )
        # On error, do NOT send alert (fail-safe — prefer no alert over spam)
        return
    
    # New session detected — send alert
    if not client_config.human_agent_number:
        return  # No human agent configured, skip alert
    
    customer_name = display_name or phone_number
    alert_text = (
        f"📨 AI handling: *{customer_name}*\n\n"
        f'"{message_text[:80]}{"..." if len(message_text) > 80 else ""}"\n\n'
        f"Reply \"take\" to this message to take over."
    )
    
    try:
        alert_msg_id = await send_message(
            client_config=client_config,
            to_phone_number=client_config.human_agent_number,
            text=alert_text,
        )
        
        if alert_msg_id:
            logger.info(
                f"Conversation alert sent to {client_config.human_agent_number} "
                f"for customer {phone_number}, wamid={alert_msg_id}"
            )
            
            # Store alert wamid for reply-to-message detection
            await db.table("customers").update({
                "last_ai_alert_msg_id": alert_msg_id,
            }).eq("phone_number", phone_number).execute()
        else:
            logger.warning(
                f"Failed to send conversation alert for {phone_number} — "
                "alert_msg_id is NULL"
            )
    except Exception as e:
        logger.error(
            f"Failed to send conversation alert for {phone_number}: {e}",
            exc_info=True,
        )
        # Non-fatal — AI still handled the message successfully


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

        # Guard: verify loaded config matches the requested client_id.
        # Catches any cache contamination before it propagates to any client.
        if client_config.client_id != client_id:
            logger.critical(
                "Client config ID mismatch: requested '%s', loaded '%s' — "
                "aborting message processing for %s. This is a cache bug.",
                client_id,
                client_config.client_id,
                phone_number,
            )
            return

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

        # ── Step 3b: Takeover gate (runs BEFORE escalation gate) ──────────────
        if customer_row and customer_row.get("takeover_flag") is True:
            await _handle_takeover_inbound(
                db=db,
                client_config=client_config,
                phone_number=phone_number,
                display_name=display_name,
                message_text=message_text,
            )
            return  # Stop pipeline — AI does NOT run

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

        # ── Step 4b: Schedule gate — AI operational hours check ───────────────
        if not _is_within_ai_hours(client_config):
            await _handle_out_of_hours_message(
                db=db,
                client_config=client_config,
                phone_number=phone_number,
                display_name=display_name,
                message_text=message_text,
            )
            return  # Stop pipeline — do NOT invoke agent

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

        # ── Step 5b: Opt-out detection (pre-agent gate) ───────────────────────
        # If customer sends an opt-out keyword and has an active pending booking,
        # mark followup_stage = 'opted_out', send confirmation, and return.
        # Agent is NOT invoked. This runs before the affirmative confirmation check.
        if _is_opt_out_keyword(message_text):
            active_booking = await _get_active_followup_booking(db, phone_number)
            if active_booking:
                try:
                    await db.table("bookings").update(
                        {"followup_stage": "opted_out"}
                    ).eq("booking_id", active_booking["booking_id"]).execute()
                    logger.info(
                        "Opt-out detected for %s — booking %s marked opted_out",
                        phone_number,
                        active_booking["booking_id"],
                    )
                except Exception as e:
                    logger.error(
                        "Failed to mark opt-out for booking %s: %s",
                        active_booking.get("booking_id"),
                        e,
                        exc_info=True,
                    )
                _now = datetime.now(timezone.utc).isoformat()
                try:
                    await send_message(client_config, phone_number, OPT_OUT_REPLY)
                    await db.table("interactions_log").insert({
                        "timestamp": _now,
                        "phone_number": phone_number,
                        "direction": "outbound",
                        "message_text": OPT_OUT_REPLY,
                        "message_type": "text",
                    }).execute()
                except Exception as e:
                    logger.error(
                        "Failed to send/log opt-out reply to %s: %s",
                        phone_number,
                        e,
                        exc_info=True,
                    )
                return  # Agent does NOT run after opt-out is processed.
            # No active pending booking — fall through to normal agent handling.
            logger.debug(
                "Opt-out keyword received from %s but no active pending booking found — passing to agent",
                phone_number,
            )

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
                lead_days, pending_booking, windows = await asyncio.gather(
                    fetch_lead_days(db),
                    _get_latest_pending_booking(db, phone_number),
                    fetch_appointment_windows(db),
                )
                tool_dispatch = build_tool_dispatch(db, client_config, phone_number, lead_days, windows)

                # Phase-based tool selection:
                #   Phase A (no pending): check_calendar, write_booking, get_bookings, escalate
                #   Phase B (pending exists): confirm_booking, get_bookings, escalate
                # write_booking is excluded in Phase B — the LLM structurally cannot
                # create a duplicate booking. confirm_booking is excluded in Phase A —
                # the LLM cannot confirm something that doesn't exist yet.
                tool_definitions = build_tool_definitions(pending_booking)

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
                        "\n\nPENDING BOOKING AWAITING CONFIRMATION:\n"
                        f"Reference: {pending_booking['booking_id']}\n"
                        f"Service: {pending_booking['service_type']}\n"
                        f"Date: {pending_booking['slot_date']}\n"
                        f"Time: {pending_booking['slot_window']}\n"
                        f"Address: {pending_booking['address']}, Singapore {pending_booking['postal_code']}\n"
                        "\nThe customer has already provided all booking details. "
                        "Your only available booking action is confirm_booking — use the exact booking_id above. "
                        "If the customer is affirming (yes/ok/confirm/sure/go ahead), call confirm_booking immediately. "
                        "If the customer asks a question, answer it first. "
                        "Do NOT ask the customer to repeat their details.\n"
                    )
                history = await fetch_conversation_history(db, phone_number)
                history = _remove_current_inbound_from_history(history, message_text)
                agent_reply = await run_agent(
                    system_message=system_message,
                    conversation_history=history,
                    current_message=message_text,
                    tool_definitions=tool_definitions,
                    tool_dispatch=tool_dispatch,
                    client_id=client_id,
                    anthropic_api_key=client_config.anthropic_api_key,
                    openai_api_key=client_config.openai_api_key,
                    pending_booking_id=pending_booking["booking_id"] if pending_booking else None,
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

        # ── Step 8: Send conversation alert (if new session) ──────────────────
        # After the lock exits — fire-and-forget proactive alert to human_agent_number
        await _maybe_send_conversation_alert(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            display_name=display_name,
            message_text=message_text,
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
