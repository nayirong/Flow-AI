"""
Google Calendar integration for the Flow AI engine.

Uses a service account (JSON creds stored per-client in env vars).

Capabilities:
- check_slot_availability(): AM/PM freebusy check for a date
- create_booking_event():    add a new calendar event (add-only — never modify/delete)

All Google API calls are run in a thread-pool executor so they don't block
the async event loop.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Slot windows (SGT, UTC+8)
_SLOT_TIMES: dict[str, tuple[str, str]] = {
    "AM": ("09:00", "13:00"),
    "PM": ("14:00", "18:00"),
}


def _build_service(creds_dict: dict):
    """
    Build an authenticated Google Calendar Resource.

    Runs synchronously — wrap in run_in_executor when called from async code.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=_SCOPES
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


async def check_slot_availability(
    google_calendar_creds: dict,
    calendar_id: str,
    slot_date: str,
    timezone: str = "Asia/Singapore",
) -> dict:
    """
    Check AM and PM slot availability for a given date using Google Calendar freebusy.

    A slot is considered taken if ANY event exists in that time window.

    Args:
        google_calendar_creds: Service account credentials dict.
        calendar_id:           Google Calendar ID.
        slot_date:             Date to check in YYYY-MM-DD format.
        timezone:              Calendar timezone (default Asia/Singapore).

    Returns:
        dict: {date, am_available (bool), pm_available (bool)}

    Raises:
        Exception on Google API error — caller is responsible for handling.
    """
    loop = asyncio.get_event_loop()
    service = await loop.run_in_executor(None, _build_service, google_calendar_creds)

    availability: dict[str, bool] = {}

    for slot_window, (start_t, end_t) in _SLOT_TIMES.items():
        time_min = f"{slot_date}T{start_t}:00+08:00"
        time_max = f"{slot_date}T{end_t}:00+08:00"

        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": timezone,
            "items": [{"id": calendar_id}],
        }

        freebusy = await loop.run_in_executor(
            None,
            lambda b=body: service.freebusy().query(body=b).execute(),
        )

        busy_periods = (
            freebusy
            .get("calendars", {})
            .get(calendar_id, {})
            .get("busy", [])
        )
        availability[slot_window] = len(busy_periods) == 0

    return {
        "date": slot_date,
        "am_available": availability.get("AM", False),
        "pm_available": availability.get("PM", False),
    }


async def create_booking_event(
    google_calendar_creds: dict,
    calendar_id: str,
    booking_id: str,
    customer_name: str,
    phone_number: str,
    service_type: str,
    unit_count: str,
    address: str,
    postal_code: str,
    slot_date: str,
    slot_window: str,
    aircon_brand: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Create a Google Calendar event for a confirmed booking.

    HARD RULE: This function only ever adds events.
    The agent must never modify or delete calendar events.

    Args:
        google_calendar_creds: Service account credentials dict.
        calendar_id:           Google Calendar ID.
        booking_id:            Booking reference (e.g. HA-20260430-A3F2).
        customer_name:         Customer's full name.
        phone_number:          Customer's phone number.
        service_type:          Aircon service type (e.g. "General Servicing").
        unit_count:            Number of aircon units.
        address:               Service address.
        postal_code:           6-digit Singapore postal code.
        slot_date:             Date in YYYY-MM-DD format.
        slot_window:           "AM" or "PM".
        aircon_brand:          Optional aircon brand.
        notes:                 Optional free-text notes.

    Returns:
        Google Calendar event ID string.

    Raises:
        Exception on Google API error — caller handles.
    """
    loop = asyncio.get_event_loop()
    service = await loop.run_in_executor(None, _build_service, google_calendar_creds)

    start_t, end_t = _SLOT_TIMES[slot_window]

    description_lines = [
        f"Booking ID: {booking_id}",
        f"Service: {service_type}",
        f"Units: {unit_count}",
        f"Customer: {customer_name}",
        f"Phone: {phone_number}",
        f"Address: {address}, Singapore {postal_code}",
    ]
    if aircon_brand:
        description_lines.append(f"Brand: {aircon_brand}")
    if notes:
        description_lines.append(f"Notes: {notes}")

    event_body = {
        "summary": (
            f"[{booking_id}] {service_type} — {customer_name} ({unit_count} units)"
        ),
        "location": f"{address}, Singapore {postal_code}",
        "description": "\n".join(description_lines),
        "start": {
            "dateTime": f"{slot_date}T{start_t}:00+08:00",
            "timeZone": "Asia/Singapore",
        },
        "end": {
            "dateTime": f"{slot_date}T{end_t}:00+08:00",
            "timeZone": "Asia/Singapore",
        },
    }

    created = await loop.run_in_executor(
        None,
        lambda: service.events().insert(calendarId=calendar_id, body=event_body).execute(),
    )

    event_id: str = created["id"]
    logger.info(
        f"Calendar event created: {event_id} for booking {booking_id} "
        f"on {slot_date} {slot_window}"
    )
    return event_id
