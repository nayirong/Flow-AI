"""
Proactive follow-up scheduler for pending bookings.

Runs every 60 minutes via APScheduler. Queries per-client Supabase for eligible
pending bookings and sends T+2h and T+24h follow-up messages, or marks T+48h
bookings as abandoned.

Slice 4 — Proactive follow-up automation.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from engine.integrations.supabase_client import get_client_db, get_shared_db
from engine.integrations.meta_whatsapp import send_message
from engine.config.client_config import load_client_config

logger = logging.getLogger(__name__)


@dataclass
class FollowupTimingConfig:
    """
    Per-client configurable timing windows for the follow-up scheduler.

    All values are in hours. Loaded from the per-client `config` table;
    any missing key falls back to the default listed here.

    Config table keys:
        followup_first_min_hours   — hours after booking creation before first follow-up fires
        followup_first_max_hours   — upper bound; bookings older than this move to second follow-up logic
        followup_second_after_hours — hours since last_followup_sent_at before second follow-up fires
        followup_abandon_after_hours — hours since last_followup_sent_at before booking is abandoned
    """
    first_min_hours: int = 2    # send first follow-up 2h after booking
    first_max_hours: int = 24   # stop first follow-up logic after 24h
    second_after_hours: int = 22  # send second follow-up 22h after first
    abandon_after_hours: int = 22  # abandon 22h after second follow-up


async def load_followup_timing_config(client_db, client_id: str) -> FollowupTimingConfig:
    """
    Load follow-up timing windows from the per-client config table.

    Reads integer values for each timing key. Any key that is missing or
    non-integer falls back silently to the FollowupTimingConfig default.

    Args:
        client_db: Per-client Supabase AsyncClient
        client_id: Client identifier (for logging only)

    Returns:
        FollowupTimingConfig with values from DB (or defaults)
    """
    timing_keys = [
        "followup_first_min_hours",
        "followup_first_max_hours",
        "followup_second_after_hours",
        "followup_abandon_after_hours",
    ]
    defaults = FollowupTimingConfig()
    overrides: dict = {}

    try:
        result = await (
            client_db.table("config")
            .select("key, value")
            .in_("key", timing_keys)
            .execute()
        )
        for row in result.data or []:
            try:
                overrides[row["key"]] = int(row["value"])
            except (ValueError, TypeError):
                logger.warning(
                    f"Client '{client_id}': config key '{row['key']}' "
                    f"value '{row['value']}' is not an integer — using default"
                )
    except Exception as e:
        logger.warning(
            f"Client '{client_id}': failed to load timing config — using defaults. Error: {e}"
        )

    timing = FollowupTimingConfig(
        first_min_hours=overrides.get("followup_first_min_hours", defaults.first_min_hours),
        first_max_hours=overrides.get("followup_first_max_hours", defaults.first_max_hours),
        second_after_hours=overrides.get("followup_second_after_hours", defaults.second_after_hours),
        abandon_after_hours=overrides.get("followup_abandon_after_hours", defaults.abandon_after_hours),
    )
    logger.info(
        f"Client '{client_id}' timing config: "
        f"first follow-up={timing.first_min_hours}h–{timing.first_max_hours}h, "
        f"second follow-up after {timing.second_after_hours}h, "
        f"abandon after {timing.abandon_after_hours}h"
    )
    return timing


async def run_followup_scheduler() -> None:
    """
    Entry point called by APScheduler every 60 minutes.
    
    For each active client with followup_enabled=true:
    1. Send T+2h follow-ups (bookings 2-24h old, no customer reply, not escalated)
    2. Send T+24h follow-ups (bookings 24-48h since last followup, no reply)
    3. Abandon T+48h bookings (bookings 48h+ since last followup, no reply)
    4. Log metrics to scheduler_runs table
    
    Never crashes the FastAPI process — catches all exceptions at top level.
    """
    try:
        logger.info("Follow-up scheduler run started")
        
        # Load active clients from shared DB
        shared_db = await get_shared_db()
        result = await shared_db.table("clients").select("client_id, is_active").eq("is_active", True).execute()
        
        if not result.data:
            logger.info("No active clients found — scheduler run complete")
            return
        
        active_clients = [row["client_id"] for row in result.data]
        logger.info(f"Found {len(active_clients)} active clients: {active_clients}")
        
        # Process each client
        for client_id in active_clients:
            try:
                await process_client_followups(client_id)
            except Exception as e:
                logger.error(
                    f"Error processing follow-ups for client '{client_id}': {e}",
                    exc_info=True,
                )
                # Continue to next client — do not let one client failure stop the entire run
                continue
        
        logger.info("Follow-up scheduler run completed")
        
    except Exception as e:
        # Top-level exception handler — never crash the FastAPI process
        logger.error(f"Critical error in follow-up scheduler: {e}", exc_info=True)


async def process_client_followups(client_id: str) -> None:
    """
    Process follow-ups for a single client.
    
    Args:
        client_id: Client identifier
    """
    # Load client config
    try:
        client_config = await load_client_config(client_id)
    except Exception as e:
        logger.error(f"Failed to load config for client '{client_id}': {e}")
        return
    
    # Check if follow-up is enabled for this client
    client_db = await get_client_db(client_id)
    
    try:
        config_result = await client_db.table("config").select("value").eq("key", "followup_enabled").limit(1).execute()
        
        if not config_result.data or config_result.data[0]["value"].lower() != "true":
            logger.info(f"Follow-up disabled for client '{client_id}' — skipping")
            return
    except Exception as e:
        logger.error(f"Failed to check followup_enabled config for client '{client_id}': {e}")
        return
    
    logger.info(f"Processing follow-ups for client '{client_id}'")
    
    # Initialize metrics
    bookings_t2h = 0
    bookings_t24h = 0
    bookings_abandoned = 0
    messages_sent_failed = 0
    
    # Load per-client timing config
    timing = await load_followup_timing_config(client_db, client_id)

    # Load message templates
    template_t2h = await get_message_template(client_db, "followup_message_t2h", client_id)
    template_t24h = await get_message_template(client_db, "followup_message_t24h", client_id)
    
    # Process T+2h follow-ups
    try:
        t2h_results = await process_t2h_followups(
            client_id, client_config, client_db, template_t2h, timing
        )
        bookings_t2h = t2h_results["sent"]
        messages_sent_failed += t2h_results["failed"]
    except Exception as e:
        logger.error(f"Error processing T+2h follow-ups for client '{client_id}': {e}", exc_info=True)
    
    # Process T+24h follow-ups
    try:
        t24h_results = await process_t24h_followups(
            client_id, client_config, client_db, template_t24h, timing
        )
        bookings_t24h = t24h_results["sent"]
        messages_sent_failed += t24h_results["failed"]
    except Exception as e:
        logger.error(f"Error processing T+24h follow-ups for client '{client_id}': {e}", exc_info=True)
    
    # Process T+48h abandonments
    try:
        bookings_abandoned = await process_t48h_abandonments(client_id, client_db, timing)
    except Exception as e:
        logger.error(f"Error processing T+48h abandonments for client '{client_id}': {e}", exc_info=True)
    
    # Log metrics to scheduler_runs table (shared DB)
    try:
        shared_db = await get_shared_db()
        await shared_db.table("scheduler_runs").insert({
            "client_id": client_id,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "bookings_t2h": bookings_t2h,
            "bookings_t24h": bookings_t24h,
            "bookings_abandoned": bookings_abandoned,
            "messages_sent_failed": messages_sent_failed,
        }).execute()
        
        logger.info(
            f"Client '{client_id}' follow-up metrics: "
            f"T+2h={bookings_t2h}, T+24h={bookings_t24h}, "
            f"abandoned={bookings_abandoned}, failed={messages_sent_failed}"
        )
    except Exception as e:
        logger.error(f"Failed to log scheduler_runs for client '{client_id}': {e}")


async def get_message_template(client_db, key: str, client_id: str) -> str:
    """
    Load message template from config table, with fallback to default.
    
    Args:
        client_db: Client Supabase AsyncClient
        key: Config key (e.g., "followup_message_t2h")
        client_id: Client identifier (for logging)
        
    Returns:
        Message template string
    """
    defaults = {
        "followup_message_t2h": (
            "Hi! Just checking in — you have a pending booking for {service_type} "
            "on {slot_date} ({slot_window} slot). Reply *yes* to confirm or let us "
            "know if you need to change anything!"
        ),
        "followup_message_t24h": (
            "Hi again! Your booking for {service_type} on {slot_date} ({slot_window} slot) "
            "is still pending confirmation. Reply *yes* to confirm, or we'll assume you "
            "no longer need it."
        ),
    }
    
    try:
        result = await client_db.table("config").select("value").eq("key", key).limit(1).execute()
        
        if result.data:
            return result.data[0]["value"]
    except Exception as e:
        logger.warning(f"Failed to load template '{key}' for client '{client_id}': {e}")
    
    return defaults.get(key, "")


async def process_t2h_followups(
    client_id: str,
    client_config,
    client_db,
    template: str,
    timing: FollowupTimingConfig,
) -> Dict[str, int]:
    """
    Process T+2h follow-ups (bookings created t2h_min_hours–t2h_max_hours ago, no customer reply).

    Timing windows come from the per-client FollowupTimingConfig.

    Returns:
        dict with 'sent' and 'failed' counts
    """
    sent = 0
    failed = 0
    
    # Query eligible bookings using PostgREST client with Python-computed timestamps
    now = datetime.now(timezone.utc)
    min_cutoff = (now - timedelta(hours=timing.first_min_hours)).isoformat()
    max_cutoff = (now - timedelta(hours=timing.first_max_hours)).isoformat()

    try:
        result = await (
            client_db.table("bookings")
            .select("booking_id, phone_number, service_type, slot_date, slot_window, created_at")
            .eq("booking_status", "pending_confirmation")
            .is_("followup_stage", "null")
            .lte("created_at", min_cutoff)
            .gt("created_at", max_cutoff)
            .execute()
        )
        bookings = result.data if result.data else []
    except Exception as e:
        logger.error(f"Failed to query first follow-up bookings for client '{client_id}': {e}")
        return {"sent": 0, "failed": 0}
    
    logger.info(f"Found {len(bookings)} candidate first follow-up bookings for client '{client_id}'")
    
    # Process each booking
    for booking in bookings:
        booking_id = booking["booking_id"]
        phone_number = booking["phone_number"]
        
        # Check escalation flag
        if await is_customer_escalated(client_db, phone_number):
            logger.info(f"Booking {booking_id} — customer escalated, skipping T+2h follow-up")
            continue
        
        # Check if customer has replied since booking created
        if await has_customer_replied_since(client_db, phone_number, booking["created_at"]):
            logger.info(f"Booking {booking_id} — customer replied since creation, skipping T+2h follow-up")
            continue
        
        # Send message
        message_text = template.format(
            service_type=booking["service_type"],
            slot_date=booking["slot_date"],
            slot_window=booking["slot_window"],
        )
        
        wamid = await send_message(client_config, phone_number, message_text)
        
        if wamid:
            # Message sent successfully — update followup_stage
            try:
                await client_db.table("bookings").update({
                    "followup_stage": "2h_sent",
                    "last_followup_sent_at": datetime.now(timezone.utc).isoformat(),
                }).eq("booking_id", booking_id).execute()
                
                sent += 1
                logger.info(f"T+2h follow-up sent for booking {booking_id}")
            except Exception as e:
                logger.error(f"Failed to update followup_stage for booking {booking_id}: {e}")
                failed += 1
        else:
            # Message send failed
            failed += 1
            logger.warning(f"Failed to send T+2h follow-up for booking {booking_id}")
            
            # Log to api_incidents (shared DB)
            try:
                shared_db = await get_shared_db()
                await shared_db.table("api_incidents").insert({
                    "client_id": client_id,
                    "incident_type": "meta_api_failure",
                    "phone_number": phone_number,
                    "details": f"T+2h follow-up message send failed for booking {booking_id}",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                logger.error(f"Failed to log api_incident for booking {booking_id}: {e}")
    
    return {"sent": sent, "failed": failed}


async def process_t24h_followups(
    client_id: str,
    client_config,
    client_db,
    template: str,
    timing: FollowupTimingConfig,
) -> Dict[str, int]:
    """
    Process T+24h follow-ups (bookings with 2h_sent stage, t24h_after_hours since last follow-up).

    Timing windows come from the per-client FollowupTimingConfig.

    Returns:
        dict with 'sent' and 'failed' counts
    """
    sent = 0
    failed = 0
    
    # Query eligible bookings using PostgREST client with Python-computed timestamp
    now = datetime.now(timezone.utc)
    second_cutoff = (now - timedelta(hours=timing.second_after_hours)).isoformat()

    try:
        result = await (
            client_db.table("bookings")
            .select("booking_id, phone_number, service_type, slot_date, slot_window, last_followup_sent_at")
            .eq("booking_status", "pending_confirmation")
            .eq("followup_stage", "2h_sent")
            .lte("last_followup_sent_at", second_cutoff)
            .execute()
        )
        bookings = result.data if result.data else []
    except Exception as e:
        logger.error(f"Failed to query second follow-up bookings for client '{client_id}': {e}")
        return {"sent": 0, "failed": 0}
    
    logger.info(f"Found {len(bookings)} candidate second follow-up bookings for client '{client_id}'")
    
    # Process each booking
    for booking in bookings:
        booking_id = booking["booking_id"]
        phone_number = booking["phone_number"]
        
        # Check escalation flag
        if await is_customer_escalated(client_db, phone_number):
            logger.info(f"Booking {booking_id} — customer escalated, skipping T+24h follow-up")
            continue
        
        # Check if customer has replied since last followup
        if await has_customer_replied_since(client_db, phone_number, booking["last_followup_sent_at"]):
            logger.info(f"Booking {booking_id} — customer replied since last followup, skipping T+24h follow-up")
            continue
        
        # Send message
        message_text = template.format(
            service_type=booking["service_type"],
            slot_date=booking["slot_date"],
            slot_window=booking["slot_window"],
        )
        
        wamid = await send_message(client_config, phone_number, message_text)
        
        if wamid:
            # Message sent successfully — update followup_stage
            try:
                await client_db.table("bookings").update({
                    "followup_stage": "24h_sent",
                    "last_followup_sent_at": datetime.now(timezone.utc).isoformat(),
                }).eq("booking_id", booking_id).execute()
                
                sent += 1
                logger.info(f"T+24h follow-up sent for booking {booking_id}")
            except Exception as e:
                logger.error(f"Failed to update followup_stage for booking {booking_id}: {e}")
                failed += 1
        else:
            # Message send failed
            failed += 1
            logger.warning(f"Failed to send T+24h follow-up for booking {booking_id}")
            
            # Log to api_incidents (shared DB)
            try:
                shared_db = await get_shared_db()
                await shared_db.table("api_incidents").insert({
                    "client_id": client_id,
                    "incident_type": "meta_api_failure",
                    "phone_number": phone_number,
                    "details": f"T+24h follow-up message send failed for booking {booking_id}",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                logger.error(f"Failed to log api_incident for booking {booking_id}: {e}")
    
    return {"sent": sent, "failed": failed}


async def process_t48h_abandonments(client_id: str, client_db, timing: FollowupTimingConfig) -> int:
    """
    Process T+48h abandonments (bookings with 24h_sent stage, t48h_after_hours since last follow-up).

    No message is sent — DB update only. Timing window from per-client FollowupTimingConfig.

    Returns:
        Count of bookings abandoned
    """
    abandoned = 0
    
    # Query eligible bookings using PostgREST client with Python-computed timestamp
    now = datetime.now(timezone.utc)
    abandon_cutoff = (now - timedelta(hours=timing.abandon_after_hours)).isoformat()

    try:
        result = await (
            client_db.table("bookings")
            .select("booking_id, phone_number, last_followup_sent_at")
            .eq("booking_status", "pending_confirmation")
            .eq("followup_stage", "24h_sent")
            .lte("last_followup_sent_at", abandon_cutoff)
            .execute()
        )
        bookings = result.data if result.data else []
    except Exception as e:
        logger.error(f"Failed to query abandon bookings for client '{client_id}': {e}")
        return 0
    
    logger.info(f"Found {len(bookings)} candidate abandon bookings for client '{client_id}'")
    
    # Process each booking
    for booking in bookings:
        booking_id = booking["booking_id"]
        phone_number = booking["phone_number"]
        
        # Check if customer has replied since last followup
        if await has_customer_replied_since(client_db, phone_number, booking["last_followup_sent_at"]):
            logger.info(f"Booking {booking_id} — customer replied since last followup, skipping T+48h abandon")
            continue
        
        # Abandon booking — DB update only, no message sent
        try:
            await client_db.table("bookings").update({
                "booking_status": "abandoned",
                "followup_stage": "abandoned",
                "abandoned_at": datetime.now(timezone.utc).isoformat(),
            }).eq("booking_id", booking_id).execute()
            
            abandoned += 1
            logger.info(f"Booking {booking_id} abandoned (T+48h)")
        except Exception as e:
            logger.error(f"Failed to abandon booking {booking_id}: {e}")
    
    return abandoned


async def is_customer_escalated(client_db, phone_number: str) -> bool:
    """
    Check if customer is currently escalated.
    
    Args:
        client_db: Client Supabase AsyncClient
        phone_number: Customer phone number
        
    Returns:
        True if escalation_flag=True, False otherwise
    """
    try:
        result = await client_db.table("customers").select("escalation_flag").eq("phone_number", phone_number).limit(1).execute()
        
        if result.data:
            return result.data[0].get("escalation_flag", False)
    except Exception as e:
        logger.error(f"Failed to check escalation flag for {phone_number}: {e}")
    
    return False


async def has_customer_replied_since(client_db, phone_number: str, timestamp: str) -> bool:
    """
    Check if customer has sent any inbound message after the given timestamp.
    
    Args:
        client_db: Client Supabase AsyncClient
        phone_number: Customer phone number
        timestamp: ISO 8601 timestamp to check after
        
    Returns:
        True if customer has replied, False otherwise
    """
    try:
        result = await client_db.table("interactions_log").select("id").eq("phone_number", phone_number).eq("direction", "inbound").gt("timestamp", timestamp).limit(1).execute()
        
        return len(result.data) > 0 if result.data else False
    except Exception as e:
        logger.error(f"Failed to check customer replies for {phone_number}: {e}")
        return False
