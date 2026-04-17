"""
Booking tool functions for the agent tool-use loop.

Writes confirmed bookings to Supabase and reads a customer's booking history.
db, client_config, and phone_number are injected via closure in build_tool_dispatch().
"""
import logging
import random
import string
from typing import Optional

logger = logging.getLogger(__name__)


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
    Confirm a booking: create Google Calendar event + INSERT into bookings table.

    Also updates the customers record with name/address/postal collected during booking.

    This is an atomic operation from the agent's perspective — both the calendar event
    and the DB row must succeed. If the calendar write fails, the booking is not created.

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
        dict: {booking_id, status, slot_date, slot_window, service_type, calendar_event_id}

    Raises:
        Exception if Google Calendar write or Supabase INSERT fails.
        Caller (agent_runner._execute_tool) catches and returns error dict to Claude.
    """
    booking_id = _generate_booking_id(slot_date)

    # ── Step 1: Create Google Calendar event ─────────────────────────────────
    calendar_event_id: Optional[str] = None
    if client_config.google_calendar_creds and client_config.google_calendar_id:
        from engine.integrations.google_calendar import create_booking_event

        calendar_event_id = await create_booking_event(
            google_calendar_creds=client_config.google_calendar_creds,
            calendar_id=client_config.google_calendar_id,
            booking_id=booking_id,
            customer_name=customer_name,
            phone_number=phone_number,
            service_type=service_type,
            unit_count=unit_count,
            address=address,
            postal_code=postal_code,
            slot_date=slot_date,
            slot_window=slot_window,
            aircon_brand=aircon_brand,
            notes=notes,
        )
    else:
        logger.warning(
            f"Google Calendar not configured for {client_config.client_id} "
            "— skipping calendar event creation"
        )

    # ── Step 2: INSERT booking row ────────────────────────────────────────────
    booking_row: dict = {
        "booking_id": booking_id,
        "phone_number": phone_number,
        "service_type": service_type,
        "unit_count": unit_count,
        "slot_date": slot_date,
        "slot_window": slot_window,
        "booking_status": "Confirmed",
    }
    if calendar_event_id:
        booking_row["calendar_event_id"] = calendar_event_id
    if aircon_brand:
        booking_row["aircon_brand"] = aircon_brand
    if notes:
        booking_row["notes"] = notes

    await db.table("bookings").insert(booking_row).execute()

    # ── Step 3: Update customer record with name/address captured in this flow ─
    customer_update: dict = {
        "customer_name": customer_name,
        "address": address,
        "postal_code": postal_code,
    }
    try:
        await (
            db.table("customers")
            .update(customer_update)
            .eq("phone_number", phone_number)
            .execute()
        )
    except Exception as e:
        # Non-fatal — booking row already written.
        logger.warning(
            f"Failed to update customer record for {phone_number} "
            f"after booking {booking_id}: {e}"
        )

    logger.info(
        f"Booking {booking_id} written for {phone_number} "
        f"({slot_date} {slot_window}, {service_type})"
    )

    return {
        "booking_id": booking_id,
        "status": "Confirmed",
        "slot_date": slot_date,
        "slot_window": slot_window,
        "service_type": service_type,
        "calendar_event_id": calendar_event_id,
        "message": (
            f"Booking confirmed! Your reference is {booking_id}. "
            f"We'll see you on {slot_date} ({slot_window} slot) for {service_type}."
        ),
    }


async def get_customer_bookings(
    db,
    phone_number: str,
) -> dict:
    """
    Retrieve the customer's 5 most recent bookings from Supabase.

    Used when a customer asks about their existing appointments or wants to reschedule.

    Args:
        db:           Supabase async client (injected).
        phone_number: Customer phone number (injected).

    Returns:
        dict: {phone_number, bookings (list), count}

    Never raises — on DB error returns empty bookings list.
    """
    try:
        result = await (
            db.table("bookings")
            .select("booking_id, service_type, slot_date, slot_window, booking_status")
            .eq("phone_number", phone_number)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        bookings = result.data or []
    except Exception as e:
        logger.error(
            f"Failed to fetch bookings for {phone_number}: {e}", exc_info=True
        )
        bookings = []

    return {
        "phone_number": phone_number,
        "bookings": bookings,
        "count": len(bookings),
    }
