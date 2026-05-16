"""
Auto-resume job for human takeover timeout.

Runs every 30 minutes via APScheduler (registered in webhook.py lifespan).
Clears takeover_flag for any customer where takeover_at is older than the configured timeout.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from engine.config.client_config import get_all_active_clients
from engine.integrations.supabase_client import get_client_db
from engine.integrations.meta_whatsapp import send_message
from engine.config.settings import get_settings

logger = logging.getLogger(__name__)

# Default timeout: 4 hours
# Override with TAKEOVER_TIMEOUT_HOURS env var
DEFAULT_TIMEOUT_HOURS = 4


async def run_takeover_auto_resume() -> None:
    """
    Auto-resume job — clears stale takeover flags.
    
    For each active client:
    1. Query customers where takeover_flag=True and takeover_at < (now - timeout)
    2. Clear takeover_flag, takeover_by, takeover_at
    3. Log release to takeover_tracking
    4. Send notification to human_agent_number
    """
    settings = get_settings()
    timeout_hours = getattr(settings, "takeover_timeout_hours", DEFAULT_TIMEOUT_HOURS)
    
    logger.info(f"Takeover auto-resume job starting (timeout: {timeout_hours}h)")
    
    # Get all active clients
    try:
        clients = await get_all_active_clients()
    except Exception as e:
        logger.error(f"Failed to load active clients for takeover auto-resume: {e}", exc_info=True)
        return
    
    for client_config in clients:
        try:
            await _auto_resume_for_client(client_config, timeout_hours)
        except Exception as e:
            logger.error(
                f"Takeover auto-resume failed for client {client_config.client_id}: {e}",
                exc_info=True,
            )
            # Continue to next client — don't let one failure block others


async def _auto_resume_for_client(client_config, timeout_hours: int) -> None:
    """Auto-resume stale takeovers for one client."""
    db = await get_client_db(client_config.client_id)
    
    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=timeout_hours)).isoformat()
    
    # Query stale takeovers
    try:
        result = await (
            db.table("customers")
            .select("phone_number, customer_name, takeover_at")
            .eq("takeover_flag", True)
            .lt("takeover_at", cutoff_time)
            .execute()
        )
    except Exception as e:
        logger.error(
            f"Failed to query stale takeovers for {client_config.client_id}: {e}",
            exc_info=True,
        )
        return
    
    if not result.data:
        # No stale takeovers
        logger.debug(f"No stale takeovers for {client_config.client_id}")
        return
    
    now = datetime.now(timezone.utc).isoformat()
    
    for row in result.data:
        customer_phone = row["phone_number"]
        customer_name = row.get("customer_name", customer_phone)
        
        try:
            # Clear takeover flag
            await db.table("customers").update({
                "takeover_flag": False,
                "takeover_by": None,
                "takeover_at": None,
            }).eq("phone_number", customer_phone).execute()
            
            # Log release to takeover_tracking
            await db.table("takeover_tracking").update({
                "released_at": now,
                "release_command_type": "auto_resume",
            }).eq("phone_number", customer_phone).is_("released_at", "null").execute()
            
            logger.info(
                f"Auto-resumed takeover for {customer_phone} (client: {client_config.client_id}) "
                f"after {timeout_hours}h timeout"
            )
            
            # Send notification to human agent
            if client_config.human_agent_number:
                notification = (
                    f"⏰ AI auto-resumed for *{customer_name}* (+{customer_phone}) "
                    f"after {timeout_hours}-hour timeout."
                )
                try:
                    await send_message(client_config, client_config.human_agent_number, notification)
                except Exception as e:
                    logger.error(
                        f"Failed to send auto-resume notification to {client_config.human_agent_number}: {e}",
                        exc_info=True,
                    )
        
        except Exception as e:
            logger.error(
                f"Failed to auto-resume takeover for {customer_phone}: {e}",
                exc_info=True,
            )
            # Continue to next customer
