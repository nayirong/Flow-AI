"""
Human agent command handler.

Currently supports:
  - Escalation reset via reply-to-message

Future commands (not yet implemented):
  - pause / resume (manual agent silence without escalation flag)
  - status (query customer state)
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Approved reset keywords (case-insensitive, whitespace-collapsed).
RESET_KEYWORDS = frozenset([
    "done", "resolved", "ok", "handled", "fixed", "cleared",
    "completed", "closed", "finish", "finished", "okay"
])

# Help messages sent to human agent
_HELP_NO_REPLY = (
    "To clear this escalation, reply with: done, resolved, or ok"
)

_HELP_NO_ESCALATION = (
    "No pending escalation found for this alert."
)

_HELP_INVALID_KEYWORD = (
    "To clear this escalation, reply with: done, resolved, or ok"
)


def _normalise(text: str) -> str:
    """
    Normalise message text for keyword matching.
    
    Steps:
    1. Strip leading/trailing whitespace
    2. Remove ALL internal whitespace (spaces, tabs, newlines)
    3. Lowercase
    
    Examples:
        "  DONE  " → "done"
        "res olved" → "resolved"
        "o k" → "ok"
    """
    # Strip leading/trailing whitespace
    text = text.strip()
    # Remove all internal whitespace
    text = re.sub(r'\s+', '', text)
    # Lowercase
    text = text.lower()
    return text


async def handle_human_agent_message(
    db,
    client_config,
    phone_number: str,
    message_text: str,
    context_message_id: Optional[str],
) -> None:
    """
    Process a message from the human agent.

    Currently only handles escalation reset commands.
    Sends help messages for any invalid usage.

    Args:
        db:                  Supabase async client.
        client_config:       ClientConfig for the active client.
        phone_number:        Human agent's phone number.
        message_text:        Message body from Meta webhook.
        context_message_id:  wamid of the message being replied to (None if not a reply).

    Returns:
        None. Never raises — errors are logged and help messages sent.
    """
    from engine.integrations.meta_whatsapp import send_message

    # ── Step 1: Check if message is a reply ───────────────────────────────────
    if context_message_id is None:
        logger.info(
            f"Human agent message from {phone_number} is not a reply — sending help"
        )
        try:
            await send_message(client_config, phone_number, _HELP_NO_REPLY)
        except Exception as e:
            logger.error(f"Failed to send help message (no reply): {e}", exc_info=True)
        return

    # ── Step 2: Query escalation_tracking for matching alert ──────────────────
    try:
        result = await (
            db.table("escalation_tracking")
            .select("*")
            .eq("alert_msg_id", context_message_id)
            .is_("resolved_at", "null")
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error(
            f"Failed to query escalation_tracking for context_message_id={context_message_id}: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "⚠️ Failed to clear escalation — please try again.",
            )
        except Exception:
            pass
        return

    if not result.data:
        # No unresolved escalation found for this alert
        logger.info(
            f"No pending escalation found for alert_msg_id={context_message_id} — "
            f"may be already resolved or not an alert"
        )
        try:
            await send_message(client_config, phone_number, _HELP_NO_ESCALATION)
        except Exception as e:
            logger.error(f"Failed to send 'no escalation' message: {e}", exc_info=True)
        return

    # ── Step 3: Check keyword match ───────────────────────────────────────────
    normalised = _normalise(message_text)
    if normalised not in RESET_KEYWORDS:
        logger.info(
            f"Unrecognised keyword from {phone_number}: '{message_text}' → '{normalised}' — sending help"
        )
        try:
            await send_message(client_config, phone_number, _HELP_INVALID_KEYWORD)
        except Exception as e:
            logger.error(f"Failed to send invalid keyword help: {e}", exc_info=True)
        return

    # ── Step 4: Clear escalation flag ─────────────────────────────────────────
    escalation_row = result.data[0]
    customer_phone = escalation_row["phone_number"]

    try:
        # Update customers table — clear flag and reset notified state
        await (
            db.table("customers")
            .update({
                "escalation_flag": False,
                "escalation_notified": False,
            })
            .eq("phone_number", customer_phone)
            .execute()
        )

        # Update escalation_tracking — mark resolved
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await (
            db.table("escalation_tracking")
            .update({
                "resolved_at": now,
                "resolved_by": phone_number,
            })
            .eq("id", escalation_row["id"])
            .execute()
        )

        logger.info(
            f"Escalation cleared for {customer_phone} by {phone_number} "
            f"(tracking_id={escalation_row['id']})"
        )

    except Exception as e:
        logger.error(
            f"Failed to clear escalation for {customer_phone}: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "⚠️ Failed to clear escalation — please try again.",
            )
        except Exception:
            pass
        return

    # ── Step 5: Send confirmation to human agent ──────────────────────────────
    try:
        # Fetch customer name for confirmation message
        customer_result = await (
            db.table("customers")
            .select("customer_name")
            .eq("phone_number", customer_phone)
            .limit(1)
            .execute()
        )
        customer_name = None
        if customer_result.data:
            customer_name = customer_result.data[0].get("customer_name")

        customer_display = customer_name or customer_phone

        confirmation = (
            f"✅ Escalation cleared for {customer_display}. "
            f"AI will resume handling their messages."
        )
        await send_message(client_config, phone_number, confirmation)
        logger.info(f"Confirmation sent to {phone_number}: {confirmation}")

    except Exception as e:
        logger.error(
            f"Failed to send confirmation to {phone_number}: {e}",
            exc_info=True,
        )
        # Non-fatal — escalation was cleared successfully
