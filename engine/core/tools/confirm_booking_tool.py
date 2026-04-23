"""
confirm_booking tool function.

Called by the agent after the customer explicitly confirms their pending booking.
Checks for slot conflicts, creates the Google Calendar event, updates booking
status to 'confirmed', and updates the customer record.

db, client_config, and phone_number are injected via closure in build_tool_dispatch().
"""
import asyncio
import logging

from engine.integrations.google_calendar import check_slot_availability, create_booking_event
from engine.integrations.google_sheets import sync_booking_to_sheets, sync_customer_to_sheets

logger = logging.getLogger(__name__)


async def confirm_booking(
    db,
    client_config,
    phone_number: str,
    booking_id: str,
) -> dict:
    """
    Finalise a pending booking: conflict check → calendar event → status update.

    Args:
        db:            Supabase async client (injected).
        client_config: ClientConfig with calendar credentials (injected).
        phone_number:  Customer phone number (injected — used for validation).
        booking_id:    Booking ID returned by write_booking (supplied by Claude).

    Returns:
        dict with one of three shapes:
        
        Success:
            {booking_id, status: 'confirmed', calendar_event_id, message}
        
        Slot conflict:
            {booking_id, status: 'conflict', error: 'slot_no_longer_available', message}
        
        Other error:
            {booking_id, status: 'error', error: str, message}
    """
    # ── Step 1: Fetch the pending booking ─────────────────────────────────────
    try:
        result = await (
            db.table("bookings")
            .select("*")
            .eq("booking_id", booking_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error(f"confirm_booking: DB fetch failed for {booking_id}: {e}", exc_info=True)
        return {
            "booking_id": booking_id,
            "status": "error",
            "error": "database_error",
            "message": (
                "I'm sorry, I wasn't able to confirm your booking due to a technical issue. "
                "Our team has been notified and will follow up with you shortly."
            ),
        }

    if not result.data:
        logger.error(f"confirm_booking: booking_id {booking_id} not found in DB")
        return {
            "booking_id": booking_id,
            "status": "error",
            "error": "booking_not_found",
            "message": (
                "I'm sorry, I couldn't find that booking. "
                "Our team has been notified and will follow up with you shortly."
            ),
        }

    booking = result.data[0]

    # ── Step 2: Validate ownership and status ─────────────────────────────────
    if booking.get("phone_number") != phone_number:
        logger.error(
            f"confirm_booking: phone_number mismatch for {booking_id} — "
            f"booking={booking.get('phone_number')}, caller={phone_number}"
        )
        return {
            "booking_id": booking_id,
            "status": "error",
            "error": "phone_mismatch",
            "message": (
                "I'm sorry, I wasn't able to confirm that booking. "
                "Our team has been notified and will follow up."
            ),
        }

    if booking.get("booking_status") == "confirmed":
        logger.info(f"confirm_booking: {booking_id} already confirmed — idempotent return")
        return {
            "booking_id": booking_id,
            "status": "confirmed",
            "calendar_event_id": booking.get("calendar_event_id", ""),
            "message": (
                f"✅ Your booking is already confirmed! Reference: {booking_id}. "
                f"We'll see you on {booking['slot_date']} ({booking['slot_window']} slot) "
                f"for {booking['service_type']}. See you then!"
            ),
        }

    # ── Step 3: Slot conflict check ───────────────────────────────────────────
    if not client_config.google_calendar_creds or not client_config.google_calendar_id:
        logger.error(
            f"confirm_booking: Google Calendar not configured for {client_config.client_id}"
        )
        return {
            "booking_id": booking_id,
            "status": "error",
            "error": "calendar_not_configured",
            "message": (
                "I'm sorry, I wasn't able to confirm your booking right now. "
                "Our team has been notified and will follow up with you shortly."
            ),
        }

    try:
        availability = await check_slot_availability(
            google_calendar_creds=client_config.google_calendar_creds,
            calendar_id=client_config.google_calendar_id,
            slot_date=booking["slot_date"],
            timezone="Asia/Singapore",
        )
    except Exception as e:
        logger.error(
            f"confirm_booking: slot conflict check failed for {booking_id}: {e}", exc_info=True
        )
        return {
            "booking_id": booking_id,
            "status": "error",
            "error": "calendar_check_failed",
            "message": (
                "I'm sorry, I wasn't able to verify your slot right now. "
                "Our team has been notified and will follow up with you shortly."
            ),
        }

    slot_key = "am_available" if booking["slot_window"] == "AM" else "pm_available"
    if not availability.get(slot_key, False):
        logger.warning(
            f"confirm_booking: slot conflict for {booking_id} "
            f"({booking['slot_date']} {booking['slot_window']})"
        )
        # Update booking status to reflect the conflict
        try:
            await (
                db.table("bookings")
                .update({"booking_status": "cancelled"})
                .eq("booking_id", booking_id)
                .execute()
            )
        except Exception:
            pass  # Non-fatal — main concern is telling the customer
        return {
            "booking_id": booking_id,
            "status": "conflict",
            "error": "slot_no_longer_available",
            "message": (
                f"I'm sorry, the {booking['slot_window']} slot on {booking['slot_date']} "
                "is no longer available — it was just taken. "
                "Let me check what other slots are open for you."
            ),
        }

    # ── Step 4: Create Google Calendar event ─────────────────────────────────
    try:
        # Fetch customer_name from customers table for the calendar event
        customer_result = await (
            db.table("customers")
            .select("customer_name")
            .eq("phone_number", phone_number)
            .limit(1)
            .execute()
        )
        customer_name = (
            customer_result.data[0].get("customer_name", phone_number)
            if customer_result.data
            else phone_number
        )

        calendar_event_id = await create_booking_event(
            google_calendar_creds=client_config.google_calendar_creds,
            calendar_id=client_config.google_calendar_id,
            booking_id=booking_id,
            customer_name=customer_name,
            phone_number=phone_number,
            service_type=booking["service_type"],
            unit_count=booking["unit_count"],
            address=booking["address"],
            postal_code=booking["postal_code"],
            slot_date=booking["slot_date"],
            slot_window=booking["slot_window"],
            aircon_brand=booking.get("aircon_brand"),
            notes=booking.get("notes"),
        )
    except Exception as e:
        logger.error(
            f"confirm_booking: calendar event creation failed for {booking_id}: {e}",
            exc_info=True,
        )
        return {
            "booking_id": booking_id,
            "status": "error",
            "error": "calendar_write_failed",
            "message": (
                "I'm sorry, I wasn't able to create your calendar appointment right now. "
                "Our team has been notified and will follow up with you shortly."
            ),
        }

    # ── Step 5: Update booking status in DB ──────────────────────────────────
    try:
        await (
            db.table("bookings")
            .update({
                "booking_status": "confirmed",
                "calendar_event_id": calendar_event_id,
            })
            .eq("booking_id", booking_id)
            .execute()
        )
    except Exception as e:
        logger.error(
            f"confirm_booking: DB status update failed for {booking_id} "
            f"(calendar_event_id={calendar_event_id}): {e}",
            exc_info=True,
        )
        # Calendar event created but DB not updated — partial failure
        return {
            "booking_id": booking_id,
            "status": "error",
            "error": "db_update_failed",
            "message": (
                "I'm sorry, there was an issue confirming your booking. "
                "Our team has been notified and will follow up with you shortly."
            ),
        }

    # ── Step 6: Update customer name + sync to Sheets ────────────────────────
    # total_bookings trigger fires on booking INSERT (already done in write_booking),
    # not on UPDATE, so we just update the customer name here.
    try:
        await (
            db.table("customers")
            .update({"customer_name": customer_name})
            .eq("phone_number", phone_number)
            .execute()
        )
        # Re-fetch for Sheets sync (gets trigger-updated values)
        refreshed = await (
            db.table("customers")
            .select("*")
            .eq("phone_number", phone_number)
            .limit(1)
            .execute()
        )
        if refreshed.data:
            asyncio.create_task(sync_customer_to_sheets(
                client_id=client_config.client_id,
                client_config=client_config,
                customer_data=refreshed.data[0],
            ))
    except Exception as e:
        logger.warning(
            f"confirm_booking: customer update failed for {phone_number} "
            f"(booking {booking_id}) — non-fatal: {e}"
        )

    # Sync confirmed booking to Sheets (fire-and-forget)
    booking_for_sheets = {
        **booking,
        "booking_status": "confirmed",
        "calendar_event_id": calendar_event_id,
        "customer_name": customer_name,
    }
    asyncio.create_task(sync_booking_to_sheets(
        client_id=client_config.client_id,
        client_config=client_config,
        booking_data=booking_for_sheets,
    ))

    logger.info(
        f"Booking {booking_id} confirmed for {phone_number} "
        f"({booking['slot_date']} {booking['slot_window']}, calendar_event_id={calendar_event_id})"
    )

    return {
        "booking_id": booking_id,
        "status": "confirmed",
        "calendar_event_id": calendar_event_id,
        "message": (
            f"✅ Your booking is confirmed! Reference: {booking_id}. "
            f"We'll see you on {booking['slot_date']} ({booking['slot_window']} slot) "
            f"for {booking['service_type']}. See you then!"
        ),
    }
