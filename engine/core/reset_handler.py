"""
Human agent command handler.

Currently supports:
  - Escalation reset via reply-to-message

Future commands (not yet implemented):
  - pause / resume (manual agent silence without escalation flag)
  - status (query customer state)
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from engine.integrations.meta_whatsapp import send_message
from engine.integrations.google_sheets import sync_customer_to_sheets

logger = logging.getLogger(__name__)

# Approved reset keywords (case-insensitive, whitespace-collapsed).
RESET_KEYWORDS = frozenset([
    "done", "resolved", "ok", "handled", "fixed", "cleared",
    "completed", "closed", "finish", "finished", "okay"
])

# Takeover command keywords
TAKEOVER_KEYWORDS = frozenset([
    "take", "mine", "me", "takeover", "i'll handle", "ill handle", "take over"
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

    Handles:
    1. Escalation reset (existing)
    2. Takeover command (new) — "take"
    3. Release command (new) — "done" clears both escalation and takeover
    4. Status command (new) — "//status"

    Args:
        db:                  Supabase async client.
        client_config:       ClientConfig for the active client.
        phone_number:        Human agent's phone number.
        message_text:        Message body from Meta webhook.
        context_message_id:  wamid of the message being replied to (None if not a reply).

    Returns:
        None. Never raises — errors are logged and help messages sent.
    """

    # ── Status command (standalone, not a reply) ──────────────────────────────
    if message_text.strip().lower() in ["//status", "status"]:
        await _handle_status_command(db, client_config, phone_number)
        return

    # ── Takeover and reset commands require reply-to-message ──────────────────
    if context_message_id is None:
        # Not a reply — send help
        help_text = (
            "To take over a conversation: Reply \"take\" to an AI alert.\n"
            "To release a conversation: Reply \"done\" to a customer message.\n"
            "To see active takeovers: Send \"//status\"."
        )
        try:
            await send_message(client_config, phone_number, help_text)
        except Exception:
            pass
        return

    # Normalize message text
    normalized = _normalise(message_text)

    # ── Path 1: Takeover command ──────────────────────────────────────────────
    if normalized in TAKEOVER_KEYWORDS:
        await _handle_takeover_command(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            context_message_id=context_message_id,
        )
        return

    # ── Path 2: Release/reset command ─────────────────────────────────────────
    if normalized in RESET_KEYWORDS:
        # This handles BOTH escalation reset AND takeover release
        await _handle_release_command(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            context_message_id=context_message_id,
        )
        return

    # ── Invalid keyword ───────────────────────────────────────────────────────
    help_text = (
        "Valid commands:\n"
        "• \"take\" — take over a conversation\n"
        "• \"done\" — release a conversation\n"
        "• \"//status\" — list active takeovers"
    )
    try:
        await send_message(client_config, phone_number, help_text)
    except Exception:
        pass


async def _handle_takeover_command(
    db,
    client_config,
    phone_number: str,
    context_message_id: str,
) -> None:
    """
    Handle takeover command ("take") from human agent.
    
    Steps:
    1. Look up customer by last_ai_alert_msg_id = context_message_id
    2. Set takeover_flag=TRUE
    3. Log to takeover_tracking
    4. Send confirmation to human agent
    """
    
    # Query customers table for matching alert
    try:
        result = await (
            db.table("customers")
            .select("phone_number, customer_name, takeover_flag")
            .eq("last_ai_alert_msg_id", context_message_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error(
            f"Failed to query customer by alert_msg_id={context_message_id}: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "⚠️ Failed to take over — please try again.",
            )
        except Exception:
            pass
        return
    
    if not result.data:
        # No matching alert found
        try:
            await send_message(
                client_config,
                phone_number,
                "No active conversation found for this alert. It may have been too long ago.",
            )
        except Exception:
            pass
        return
    
    customer_row = result.data[0]
    customer_phone = customer_row["phone_number"]
    customer_name = customer_row.get("customer_name", customer_phone)
    already_taken = customer_row.get("takeover_flag", False)
    
    if already_taken:
        # Already in takeover mode
        try:
            await send_message(
                client_config,
                phone_number,
                f"✅ {customer_name} is already in your takeover. AI is paused.",
            )
        except Exception:
            pass
        return
    
    # Set takeover flag
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.table("customers").update({
            "takeover_flag": True,
            "takeover_by": phone_number,
            "takeover_at": now,
        }).eq("phone_number", customer_phone).execute()
        
        logger.info(
            f"Takeover initiated for {customer_phone} by {phone_number} "
            f"(client: {client_config.client_id})"
        )
    except Exception as e:
        logger.error(
            f"Failed to set takeover_flag for {customer_phone}: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "⚠️ Failed to set takeover — please try again.",
            )
        except Exception:
            pass
        return
    
    # Log to takeover_tracking
    try:
        await db.table("takeover_tracking").insert({
            "phone_number": customer_phone,
            "alert_msg_id": context_message_id,
            "takeover_by": phone_number,
            "command_type": "reply_to_alert",
        }).execute()
    except Exception as e:
        logger.error(
            f"Failed to log takeover_tracking for {customer_phone}: {e}",
            exc_info=True,
        )
        # Non-fatal — takeover flag is already set
    
    # Send confirmation
    confirmation = (
        f"✅ Taking over *{customer_name}*. AI paused.\n\n"
        f"Reply \"done\" to this thread when finished."
    )
    try:
        await send_message(client_config, phone_number, confirmation)
    except Exception as e:
        logger.error(
            f"Failed to send takeover confirmation to {phone_number}: {e}",
            exc_info=True,
        )


async def _handle_release_command(
    db,
    client_config,
    phone_number: str,
    context_message_id: str,
) -> None:
    """
    Handle release command ("done") from human agent.
    
    Clears BOTH escalation_flag AND takeover_flag (if present).
    
    Lookup priority:
    1. Look up by last_ai_alert_msg_id (takeover case)
    2. Fall back to escalation_tracking.alert_msg_id (escalation case)
    """
    
    # Try takeover lookup first
    try:
        result = await (
            db.table("customers")
            .select("phone_number, customer_name, takeover_flag, escalation_flag")
            .eq("last_ai_alert_msg_id", context_message_id)
            .limit(1)
            .execute()
        )
        
        if result.data:
            customer_row = result.data[0]
            customer_phone = customer_row["phone_number"]
            customer_name = customer_row.get("customer_name", customer_phone)
            had_takeover = customer_row.get("takeover_flag", False)
            had_escalation = customer_row.get("escalation_flag", False)
            
            # Clear both flags
            now = datetime.now(timezone.utc).isoformat()
            await db.table("customers").update({
                "takeover_flag": False,
                "takeover_by": None,
                "takeover_at": None,
                "escalation_flag": False,
                "escalation_notified": False,
                "escalation_reason": None,
            }).eq("phone_number", customer_phone).execute()
            
            # Log release to takeover_tracking
            if had_takeover:
                try:
                    await db.table("takeover_tracking").update({
                        "released_at": now,
                        "released_by": phone_number,
                        "release_command_type": "manual_done",
                    }).eq("phone_number", customer_phone).is_("released_at", "null").execute()
                except Exception as e:
                    logger.error(
                        f"Failed to log takeover release for {customer_phone}: {e}",
                        exc_info=True,
                    )
            
            # Log release to escalation_tracking
            if had_escalation:
                try:
                    await db.table("escalation_tracking").update({
                        "resolved_at": now,
                        "resolved_by": phone_number,
                    }).eq("phone_number", customer_phone).is_("resolved_at", "null").execute()
                except Exception as e:
                    logger.error(
                        f"Failed to log escalation resolution for {customer_phone}: {e}",
                        exc_info=True,
                    )
            
            # Sync to Sheets
            try:
                row_result = await db.table("customers").select("*").eq("phone_number", customer_phone).limit(1).execute()
                if row_result.data:
                    asyncio.create_task(sync_customer_to_sheets(
                        client_id=client_config.client_id,
                        client_config=client_config,
                        customer_data=row_result.data[0],
                    ))
            except Exception:
                pass
            
            # Send confirmation
            flags_cleared = []
            if had_takeover:
                flags_cleared.append("takeover")
            if had_escalation:
                flags_cleared.append("escalation")
            
            if flags_cleared:
                confirmation = f"✅ AI resumed for *{customer_name}* ({' + '.join(flags_cleared)} cleared)."
            else:
                confirmation = f"✅ AI resumed for *{customer_name}*."
            
            try:
                await send_message(client_config, phone_number, confirmation)
            except Exception:
                pass
            
            logger.info(
                f"Release command processed for {customer_phone} by {phone_number} "
                f"(cleared: {', '.join(flags_cleared) if flags_cleared else 'none'})"
            )
            return
    except Exception as e:
        logger.error(
            f"Failed takeover lookup for context_message_id={context_message_id}: {e}",
            exc_info=True,
        )
    
    # Fall back to escalation lookup (existing escalation reset logic)
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

    escalation_row = result.data[0] if result.data else None

    if escalation_row is None:
        try:
            historical_result = await (
                db.table("escalation_tracking")
                .select("phone_number")
                .eq("alert_msg_id", context_message_id)
                .limit(1)
                .execute()
            )
        except Exception as e:
            logger.error(
                f"Failed historical escalation lookup for context_message_id={context_message_id}: {e}",
                exc_info=True,
            )
            historical_result = None

        historical_phone = None
        if historical_result and historical_result.data:
            historical_phone = historical_result.data[0].get("phone_number")

        if historical_phone:
            try:
                latest_result = await (
                    db.table("escalation_tracking")
                    .select("*")
                    .eq("phone_number", historical_phone)
                    .is_("resolved_at", "null")
                    .order("escalated_at", desc=True)
                    .limit(1)
                    .execute()
                )
                escalation_row = latest_result.data[0] if latest_result.data else None
            except Exception as e:
                logger.error(
                    f"Failed fallback unresolved lookup for {historical_phone}: {e}",
                    exc_info=True,
                )
                escalation_row = None

            if escalation_row is not None:
                logger.info(
                    f"Recovered unresolved escalation for {historical_phone} via historical alert_msg_id={context_message_id} "
                    f"(tracking_id={escalation_row['id']})"
                )

    if escalation_row is None:
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

    # Clear escalation flag (keyword already validated in caller)
    customer_phone = escalation_row["phone_number"]

    try:
        # Update customers table — clear flag and reset notified state
        now = datetime.now(timezone.utc).isoformat()
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

        # Sync updated customer row to Google Sheets (fire-and-forget).
        try:
            row_result = await (
                db.table("customers")
                .select("*")
                .eq("phone_number", customer_phone)
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
            logger.warning(
                f"Sheets sync failed after escalation reset for {customer_phone}: {sheets_err}"
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

    # Send confirmation to human agent
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


async def _handle_status_command(
    db,
    client_config,
    phone_number: str,
) -> None:
    """
    Handle //status command from human agent.
    
    Returns a list of all customers with active takeover flags.
    """
    
    try:
        result = await (
            db.table("customers")
            .select("phone_number, customer_name, takeover_at")
            .eq("takeover_flag", True)
            .order("takeover_at", desc=True)
            .execute()
        )
    except Exception as e:
        logger.error(
            f"Failed to query active takeovers: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "⚠️ Failed to fetch takeover status — please try again.",
            )
        except Exception:
            pass
        return
    
    if not result.data:
        # No active takeovers
        try:
            await send_message(
                client_config,
                phone_number,
                "No active takeovers. All conversations are handled by AI.",
            )
        except Exception:
            pass
        return
    
    # Format response
    now = datetime.now(timezone.utc)
    lines = [f"Active takeovers ({len(result.data)}):"]
    
    for i, row in enumerate(result.data, start=1):
        customer_name = row.get("customer_name", row["phone_number"])
        takeover_at_str = row.get("takeover_at")
        
        if takeover_at_str:
            takeover_at = datetime.fromisoformat(takeover_at_str.replace("Z", "+00:00"))
            duration = now - takeover_at
            hours_ago = int(duration.total_seconds() / 3600)
            minutes_ago = int((duration.total_seconds() % 3600) / 60)
            
            if hours_ago > 0:
                time_str = f"{hours_ago} hour{'s' if hours_ago > 1 else ''} ago"
            else:
                time_str = f"{minutes_ago} minute{'s' if minutes_ago > 1 else ''} ago"
        else:
            time_str = "unknown"
        
        lines.append(f"\n{i}. {customer_name} (+{row['phone_number']})")
        lines.append(f"   Taken over: {time_str}")
    
    lines.append("\n\nReply \"done\" to any of their forwarded messages to release.")
    
    status_text = "\n".join(lines)
    
    try:
        await send_message(client_config, phone_number, status_text)
    except Exception as e:
        logger.error(
            f"Failed to send status response to {phone_number}: {e}",
            exc_info=True,
        )


async def _escalation_fallback(
    db,
    client_config,
    phone_number: str,
    context_message_id: str,
    message_text: str,
) -> None:
    """
    Fallback escalation reset logic (original reset_handler behavior).
    
    Called from _handle_release_command() when takeover lookup fails.
    """

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

    escalation_row = result.data[0] if result.data else None

    if escalation_row is None:
        try:
            historical_result = await (
                db.table("escalation_tracking")
                .select("phone_number")
                .eq("alert_msg_id", context_message_id)
                .limit(1)
                .execute()
            )
        except Exception as e:
            logger.error(
                f"Failed historical escalation lookup for context_message_id={context_message_id}: {e}",
                exc_info=True,
            )
            historical_result = None

        historical_phone = None
        if historical_result and historical_result.data:
            historical_phone = historical_result.data[0].get("phone_number")

        if historical_phone:
            try:
                latest_result = await (
                    db.table("escalation_tracking")
                    .select("*")
                    .eq("phone_number", historical_phone)
                    .is_("resolved_at", "null")
                    .order("escalated_at", desc=True)
                    .limit(1)
                    .execute()
                )
                escalation_row = latest_result.data[0] if latest_result.data else None
            except Exception as e:
                logger.error(
                    f"Failed fallback unresolved lookup for {historical_phone}: {e}",
                    exc_info=True,
                )
                escalation_row = None

            if escalation_row is not None:
                logger.info(
                    f"Recovered unresolved escalation for {historical_phone} via historical alert_msg_id={context_message_id} "
                    f"(tracking_id={escalation_row['id']})"
                )

    if escalation_row is None:
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

        # Sync updated customer row to Google Sheets (fire-and-forget).
        # Ensures CRM reflects escalation_flag=False immediately on reset,
        # without waiting for the customer's next inbound message.
        try:
            row_result = await (
                db.table("customers")
                .select("*")
                .eq("phone_number", customer_phone)
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
            logger.warning(
                f"Sheets sync failed after escalation reset for {customer_phone}: {sheets_err}"
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
