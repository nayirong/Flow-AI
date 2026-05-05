"""
Calendar tool function for the agent tool-use loop.

Wraps engine/integrations/google_calendar.py.
client_config is injected via closure in build_tool_dispatch() — not passed by Claude.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def check_calendar_availability(
    client_config,
    date: str,
    timezone: str = "Asia/Singapore",
    appointment_windows: dict = None,
) -> dict:
    """
    Check AM and PM slot availability on a given date.

    Called by the agent before offering a customer an appointment slot.

    Args:
        client_config:         ClientConfig with google_calendar_creds + google_calendar_id.
                               Injected via closure — not passed by Claude.
        date:                  Date to check in YYYY-MM-DD format.
        timezone:              Timezone string (default Asia/Singapore).
        appointment_windows:   Dict with keys: am_start, am_end, pm_start, pm_end (time strings).
                               If None, defaults to standard times.

    Returns:
        dict: {date, am_available, pm_available, message}
        The 'message' key is a human-readable summary for the agent to relay.

    Never raises — on error returns both slots as unavailable with an error flag.
    """
    if appointment_windows is None:
        appointment_windows = {
            "am_start": "09:00",
            "am_end": "13:00",
            "pm_start": "14:00",
            "pm_end": "18:00",
        }

    # Format time window strings for user messages (e.g., "09:00" -> "9am", "13:00" -> "1pm")
    def format_time(time_str: str) -> str:
        try:
            hour = int(time_str.split(":")[0])
            suffix = "am" if hour < 12 else "pm"
            hour_12 = hour if hour <= 12 else hour - 12
            return f"{hour_12}{suffix}"
        except (ValueError, IndexError):
            return time_str

    am_display = f"{format_time(appointment_windows['am_start'])}–{format_time(appointment_windows['am_end'])}"
    pm_display = f"{format_time(appointment_windows['pm_start'])}–{format_time(appointment_windows['pm_end'])}"
    if not client_config.google_calendar_creds or not client_config.google_calendar_id:
        logger.warning(
            f"Google Calendar not configured for client {client_config.client_id} "
            "— returning both slots as available (skip check)"
        )
        return {
            "date": date,
            "am_available": True,
            "pm_available": True,
            "message": f"Both AM ({am_display}) and PM ({pm_display}) slots appear available on {date}.",
        }

    try:
        from engine.integrations.google_calendar import check_slot_availability

        result = await check_slot_availability(
            google_calendar_creds=client_config.google_calendar_creds,
            calendar_id=client_config.google_calendar_id,
            slot_date=date,
            timezone=timezone,
        )

        am = result["am_available"]
        pm = result["pm_available"]

        if am and pm:
            message = (
                f"Both the AM slot ({am_display}) and PM slot ({pm_display}) "
                f"are available on {date}. Please offer both options to the customer."
            )
        elif am:
            message = (
                f"Only the AM slot ({am_display}) is available on {date}. "
                f"The PM slot is already taken."
            )
        elif pm:
            message = (
                f"Only the PM slot ({pm_display}) is available on {date}. "
                f"The AM slot is already taken."
            )
        else:
            message = (
                f"Both slots on {date} are fully booked. "
                f"Please ask the customer to choose another date."
            )

        return {**result, "message": message}

    except Exception as e:
        logger.error(
            f"Calendar availability check failed for {date}: {e}", exc_info=True
        )
        return {
            "date": date,
            "am_available": False,
            "pm_available": False,
            "error": "calendar_check_failed",
            "message": (
                "I was unable to check calendar availability right now. "
                "Please escalate to a human agent to confirm the slot."
            ),
        }
