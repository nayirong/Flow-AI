"""
Escalation tool for the agent tool-use loop.

Sets escalation_flag=True on the customer record and notifies the human agent
via WhatsApp. After this runs, the hard gate in message_handler.py will silence
the agent for all future messages from this customer until a human clears the flag.

db, client_config, and phone_number are injected via closure in build_tool_dispatch().
"""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Message template sent to the human agent's WhatsApp number.
_HUMAN_AGENT_ALERT_TEMPLATE = (
    "🔔 *HeyAircon Escalation Alert*\n\n"
    "Customer: {phone_number}\n"
    "Reason: {reason}\n\n"
    "Please follow up directly. "
    "The AI agent has been silenced for this customer."
)


async def escalate_to_human(
    db,
    client_config,
    phone_number: str,
    reason: str,
) -> dict:
    """
    Trigger human escalation for a customer.

    Steps:
    1. UPDATE customers SET escalation_flag=TRUE, escalation_reason=...
    2. Send WhatsApp alert to human_agent_number with customer details.

    The escalation gate in message_handler.py will then block the agent
    for all subsequent messages from this customer.

    Args:
        db:            Supabase async client (injected).
        client_config: ClientConfig with human_agent_number + WhatsApp creds (injected).
        phone_number:  Customer phone number being escalated (injected).
        reason:        Free-text reason provided by Claude (e.g. "Customer requested
                       to speak to a person", "Slot conflict on 30 Apr AM").

    Returns:
        dict: {status: "escalated", message: <confirmation text for Claude>}

    Never raises — escalation failures are logged but do not crash the agent loop.
    The agent still sends the customer a handoff message regardless of whether
    the DB write or human alert succeeded.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── Step 1: Set escalation flag in Supabase ───────────────────────────────
    try:
        await (
            db.table("customers")
            .update({
                "escalation_flag": True,
                "escalation_reason": reason,
                "last_seen": now,
            })
            .eq("phone_number", phone_number)
            .execute()
        )
        logger.info(
            f"Escalation flag set for {phone_number} — reason: {reason}"
        )

        # Sync updated customer record to Google Sheets (fire-and-forget).
        # Fetch the full row so Sheets has accurate data (booking count, name, etc.).
        try:
            from engine.integrations.google_sheets import sync_customer_to_sheets
            row_result = (
                await db.table("customers")
                .select("*")
                .eq("phone_number", phone_number)
                .limit(1)
                .execute()
            )
            if row_result.data:
                asyncio.create_task(sync_customer_to_sheets(
                    client_id=client_config.client_id,
                    client_config=client_config,
                    customer_data=row_result.data[0],
                ))
        except Exception as sheets_err:
            from engine.integrations.observability import log_noncritical_failure
            asyncio.create_task(log_noncritical_failure(
                source="escalation_sheets_sync",
                error_type=type(sheets_err).__name__,
                error_message=str(sheets_err),
                client_id=client_config.client_id,
                context={"phone_number": phone_number},
            ))
            logger.warning(
                f"Sheets sync failed after escalation for {phone_number}: {sheets_err}"
            )

    except Exception as e:
        logger.error(
            f"Failed to set escalation_flag for {phone_number}: {e}",
            exc_info=True,
        )
        # Continue — still send the human agent alert if possible.

    # ── Step 2: Notify human agent via WhatsApp ───────────────────────────────
    alert_msg_id = None  # Will be populated if alert send succeeds
    if client_config.human_agent_number:
        try:
            from engine.integrations.meta_whatsapp import send_message

            alert_text = _HUMAN_AGENT_ALERT_TEMPLATE.format(
                phone_number=phone_number,
                reason=reason,
            )
            alert_msg_id = await send_message(
                client_config=client_config,
                to_phone_number=client_config.human_agent_number,
                text=alert_text,
            )
            if alert_msg_id:
                logger.info(
                    f"Human agent alert sent to {client_config.human_agent_number} "
                    f"for customer {phone_number}, wamid={alert_msg_id}"
                )
            else:
                logger.warning(
                    f"Failed to send human agent alert for {phone_number} — "
                    f"alert_msg_id will be NULL in escalation_tracking"
                )
        except Exception as e:
            logger.error(
                f"Failed to send human agent alert for {phone_number}: {e}",
                exc_info=True,
            )
            try:
                from engine.integrations.observability import log_noncritical_failure
                asyncio.create_task(log_noncritical_failure(
                    source="escalation_human_alert",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    client_id=client_config.client_id,
                    context={"phone_number": phone_number, "human_agent_number": client_config.human_agent_number},
                ))
            except Exception:
                pass  # Observability must never crash escalation.
    else:
        logger.warning(
            f"No human_agent_number configured for client {client_config.client_id} "
            "— skipping human agent WhatsApp alert"
        )

    # ── Step 3: Insert escalation tracking row ────────────────────────────────
    try:
        await (
            db.table("escalation_tracking")
            .insert({
                "phone_number": phone_number,
                "alert_msg_id": alert_msg_id,
                "escalation_reason": reason,
            })
            .execute()
        )
        logger.info(
            f"Escalation tracking row inserted for {phone_number}, alert_msg_id={alert_msg_id}"
        )
    except Exception as tracking_err:
        logger.warning(
            f"Failed to insert escalation_tracking row for {phone_number}: {tracking_err} — "
            f"escalation flag is still set, but tracking audit is missing"
        )
        # Non-fatal — escalation flag is set, human agent alert may have been sent

    return {
        "status": "escalated",
        "message": (
            "I've flagged this for our team and they'll be in touch with you shortly. "
            "Is there anything else I can help with in the meantime?"
        ),
    }
