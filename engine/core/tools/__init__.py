"""
Tool definitions and dispatch table — Slice 5.

TOOL_DEFINITIONS: static list of 4 Anthropic-format tool dicts.
build_tool_dispatch(): per-request factory that injects db, client_config,
                       and phone_number into tool closures.

Usage in message_handler.py:
    from engine.core.tools import TOOL_DEFINITIONS, build_tool_dispatch

    tool_dispatch = build_tool_dispatch(db, client_config, phone_number)
    reply = await run_agent(..., tool_definitions=TOOL_DEFINITIONS, tool_dispatch=tool_dispatch)
"""

from engine.core.tools.definitions import TOOL_DEFINITIONS, build_tool_definitions
from engine.core.tools.calendar_tools import check_calendar_availability
from engine.core.tools.booking_tools import write_booking, get_customer_bookings
from engine.core.tools.confirm_booking_tool import confirm_booking
from engine.core.tools.escalation_tool import escalate_to_human


def build_tool_dispatch(db, client_config, phone_number: str, lead_time_days: int = 2) -> dict:
    """
    Build the tool dispatch table for a single inbound message.

    Injects db, client_config, phone_number, and lead_time_days into each tool
    via closure so the agent_runner can call tools with only Claude-supplied args.

    Args:
        db:             Supabase async client for the client's DB.
        client_config:  ClientConfig for the active client.
        phone_number:   Inbound customer phone number.
        lead_time_days: Minimum days in advance a booking must be made. Enforced
                        as a hard guard in check_calendar_availability and write_booking.
    """
    from datetime import date as _date

    def _is_within_lead_time(slot_date_str: str) -> bool:
        try:
            slot = _date.fromisoformat(slot_date_str)
            delta = (slot - _date.today()).days
            return delta < lead_time_days
        except ValueError:
            return False

    async def _check_calendar_availability(
        date: str,
        timezone: str = "Asia/Singapore",
    ) -> dict:
        if _is_within_lead_time(date):
            return {
                "date": date,
                "am_available": False,
                "pm_available": False,
                "error": "lead_time_violation",
                "message": (
                    f"Bookings must be made at least {lead_time_days} days in advance. "
                    f"{date} is too soon. Please ask the customer to choose a later date."
                ),
            }
        return await check_calendar_availability(
            client_config=client_config,
            date=date,
            timezone=timezone,
        )

    async def _write_booking(
        customer_name: str,
        service_type: str,
        unit_count: str,
        address: str,
        postal_code: str,
        slot_date: str,
        slot_window: str,
        aircon_brand: str | None = None,
        notes: str | None = None,
    ) -> dict:
        if _is_within_lead_time(slot_date):
            return {
                "error": "lead_time_violation",
                "message": (
                    f"Booking rejected: {slot_date} is within the {lead_time_days}-day minimum "
                    f"notice period. Inform the customer and ask them to choose a later date."
                ),
            }
        return await write_booking(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            customer_name=customer_name,
            service_type=service_type,
            unit_count=unit_count,
            address=address,
            postal_code=postal_code,
            slot_date=slot_date,
            slot_window=slot_window,
            aircon_brand=aircon_brand,
            notes=notes,
        )

    async def _confirm_booking(booking_id: str) -> dict:
        return await confirm_booking(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            booking_id=booking_id,
        )

    async def _get_customer_bookings(filter: str = "all") -> dict:
        return await get_customer_bookings(db=db, phone_number=phone_number, filter=filter)

    async def _escalate_to_human(reason: str) -> dict:
        return await escalate_to_human(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            reason=reason,
        )

    return {
        "check_calendar_availability": _check_calendar_availability,
        "write_booking": _write_booking,
        "confirm_booking": _confirm_booking,
        "get_customer_bookings": _get_customer_bookings,
        "escalate_to_human": _escalate_to_human,
    }


# Legacy empty constant kept for backwards-compatibility with any imports
# that still reference TOOL_DISPATCH directly. message_handler.py uses
# build_tool_dispatch() instead.
TOOL_DISPATCH: dict = {}

__all__ = ["TOOL_DEFINITIONS", "build_tool_definitions", "TOOL_DISPATCH", "build_tool_dispatch"]
