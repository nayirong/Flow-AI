"""
Booking tool functions for the agent tool-use loop.

Writes confirmed bookings to Supabase and reads a customer's booking history.
db, client_config, and phone_number are injected via closure in build_tool_dispatch().
"""
import asyncio
import logging
import random
import string
from datetime import datetime, timezone
from typing import Optional

from engine.integrations.google_sheets import sync_booking_to_sheets, sync_customer_to_sheets

logger = logging.getLogger(__name__)

_BOOKING_FAILURE_ALERT_TEMPLATE = (
    "⚠️ *Booking Backend Failure — Action Required*\n\n"
    "A booking was pending confirmation but a backend error occurred.\n\n"
    "Customer: {phone_number}\n"
    "Name: {customer_name}\n"
    "Service: {service_type} ({unit_count} units)\n"
    "Date: {slot_date} ({slot_window})\n"
    "Address: {address}, Singapore {postal_code}\n\n"
    "Error: {error}\n\n"
    "Please create the booking manually and confirm with the customer."
)


async def _alert_booking_failure(
    client_config,
    phone_number: str,
    customer_name: str,
    service_type: str,
    unit_count: str,
    address: str,
    postal_code: str,
    slot_date: str,
    slot_window: str,
    error: str,
) -> None:
    """Send a WhatsApp alert to the human agent when a booking backend failure occurs."""
    if not client_config.human_agent_number:
        logger.error(
            "No human_agent_number configured — cannot send booking failure alert"
        )
        return
    try:
        from engine.integrations.meta_whatsapp import send_message

        alert_text = _BOOKING_FAILURE_ALERT_TEMPLATE.format(
            phone_number=phone_number,
            customer_name=customer_name,
            service_type=service_type,
            unit_count=unit_count,
            address=address,
            postal_code=postal_code,
            slot_date=slot_date,
            slot_window=slot_window,
            error=error,
        )
        await send_message(
            client_config=client_config,
            to_phone_number=client_config.human_agent_number,
            text=alert_text,
        )
        logger.info(
            f"Booking failure alert sent to human agent for customer {phone_number}"
        )
    except Exception as e:
        logger.error(f"Failed to send booking failure alert: {e}", exc_info=True)


def _generate_booking_id(slot_date: str) -> str:
    """
    Generate a booking ID in the format HA-YYYYMMDD-XXXX.

    The 4-char suffix is random alphanumeric (uppercase).
    This is safe for Phase 1 volumes — revisit if collision risk grows.

    Args:
        slot_date: Date string in YYYY-MM-DD format.

    Returns:
        e.g. "HA-20260430-A3F2"
    """
    date_compact = slot_date.replace("-", "")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"HA-{date_compact}-{suffix}"


async def write_booking(
    db,
    client_config,
    phone_number: str,
    customer_name: str,
    service_type: str,
    unit_count: str,
    address: str,
    postal_code: str,
    slot_date: str,
    slot_window: str,
    aircon_brand: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Record a pending booking in the database. Does NOT create a Google Calendar event.

    This is Phase 1 of the two-phase booking flow:
    - Phase 1 (this function): Record booking details with pending_confirmation status
    - Phase 2 (confirm_booking): After customer confirms, create calendar event and
      update status to confirmed

    Args:
        db:            Supabase async client (injected).
        client_config: ClientConfig with calendar + DB credentials (injected).
        phone_number:  Customer phone number (injected).
        customer_name: Customer's full name.
        service_type:  Aircon service type.
        unit_count:    Number of aircon units.
        address:       Service address.
        postal_code:   6-digit Singapore postal code.
        slot_date:     Booking date in YYYY-MM-DD format.
        slot_window:   "AM" or "PM".
        aircon_brand:  Optional aircon brand.
        notes:         Optional free-text notes.

    Returns:
        dict: {booking_id, status, slot_date, slot_window, service_type, message}
              status will be "pending_confirmation"
              message contains instructions for the agent to send summary and wait for confirmation

    Raises:
        ValueError if address is empty.
        Exception if Supabase INSERT fails.
        Caller (agent_runner._execute_tool) catches and returns error dict to Claude.
    """
    if not address:
        raise ValueError(
            "write_booking() requires a non-empty address. "
            "The agent must collect address from the customer before calling this tool."
        )

    booking_id = _generate_booking_id(slot_date)

    # ── INSERT booking row with pending_confirmation status ───────────────────────
    # Note: customer_name is NOT a column in the bookings table — it lives in
    # customers. We keep it in the dict only so Sheets sync can include it;
    # it is NOT sent to Supabase (excluded from db_booking_row below).
    _created_at = datetime.now(timezone.utc).isoformat()
    booking_row: dict = {
        "booking_id": booking_id,
        "phone_number": phone_number,
        "customer_name": customer_name,  # Sheets sync only — not in DB schema
        "service_type": service_type,
        "unit_count": unit_count,
        "address": address,
        "postal_code": postal_code,
        "slot_date": slot_date,
        "slot_window": slot_window,
        "booking_status": "pending_confirmation",
        "created_at": _created_at,
    }
    db_booking_row = {k: v for k, v in booking_row.items() if k != "customer_name"}
    if aircon_brand:
        booking_row["aircon_brand"] = aircon_brand
        db_booking_row["aircon_brand"] = aircon_brand
    if notes:
        booking_row["notes"] = notes
        db_booking_row["notes"] = notes

    try:
        await db.table("bookings").insert(db_booking_row).execute()
        # Sync to Sheets with full booking_row (includes customer_name for Sheets column)
        asyncio.create_task(sync_booking_to_sheets(
            client_id=client_config.client_id,
            client_config=client_config,
            booking_data=booking_row,
        ))
    except Exception as db_err:
        logger.error(
            f"DB write failed for booking {booking_id} ({phone_number}): {db_err}",
            exc_info=True,
        )
        await _alert_booking_failure(
            client_config=client_config,
            phone_number=phone_number,
            customer_name=customer_name,
            service_type=service_type,
            unit_count=unit_count,
            address=address,
            postal_code=postal_code,
            slot_date=slot_date,
            slot_window=slot_window,
            error=f"DB write failed: {db_err}",
        )
        raise

    logger.info(
        f"Pending booking {booking_id} recorded for {phone_number} "
        f"({slot_date} {slot_window}, {service_type})"
    )

    return {
        "booking_id": booking_id,
        "status": "pending_confirmation",
        "slot_date": slot_date,
        "slot_window": slot_window,
        "service_type": service_type,
        "message": (
            f"Booking details recorded (Reference: {booking_id}). "
            "Send the customer a summary: their service, date, time slot, and address. "
            "Ask them to confirm. Once they reply yes, call confirm_booking with this booking_id."
        ),
    }


async def get_customer_bookings(
    db,
    phone_number: str,
    filter: str = "all",
) -> dict:
    """
    Retrieve the customer's bookings from Supabase.

    Args:
        db:           Supabase async client (injected).
        phone_number: Customer phone number (injected).
        filter:       "upcoming" (slot_date >= today), "past" (slot_date < today),
                      or "all" (no date filter). Defaults to "all".

    Returns:
        dict: {phone_number, filter, bookings (list), count}

    Never raises — on DB error returns empty bookings list.
    """
    from datetime import date

    today = date.today().isoformat()

    try:
        query = (
            db.table("bookings")
            .select("booking_id, service_type, slot_date, slot_window, booking_status")
            .eq("phone_number", phone_number)
        )

        if filter == "upcoming":
            query = query.gte("slot_date", today).order("slot_date", desc=False)
        elif filter == "past":
            query = query.lt("slot_date", today).order("slot_date", desc=True)
        else:
            query = query.order("slot_date", desc=False)

        result = await query.limit(5).execute()
        bookings = result.data or []
    except Exception as e:
        logger.error(f"Failed to fetch bookings for {phone_number}: {e}", exc_info=True)
        bookings = []

    return {
        "phone_number": phone_number,
        "filter": filter,
        "bookings": bookings,
        "count": len(bookings),
    }
