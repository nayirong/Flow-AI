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
) -> dict:
    """
    Check AM and PM slot availability on a given date.

    Called by the agent before offering a customer an appointment slot.

    Args:
        client_config: ClientConfig with google_calendar_creds + google_calendar_id.
                       Injected via closure — not passed by Claude.
        date:          Date to check in YYYY-MM-DD format.
        timezone:      Timezone string (default Asia/Singapore).

    Returns:
        dict: {date, am_available, pm_available, message}
        The 'message' key is a human-readable summary for the agent to relay.

    Never raises — on error returns both slots as unavailable with an error flag.
    """
    if not client_config.google_calendar_creds or not client_config.google_calendar_id:
        logger.warning(
            f"Google Calendar not configured for client {client_config.client_id} "
            "— returning both slots as available (skip check)"
        )
        return {
            "date": date,
            "am_available": True,
            "pm_available": True,
            "message": f"Both AM (9am–1pm) and PM (2pm–6pm) slots appear available on {date}.",
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
                f"Both the AM slot (9am–1pm) and PM slot (2pm–6pm) "
                f"are available on {date}. Please offer both options to the customer."
            )
        elif am:
            message = (
                f"Only the AM slot (9am–1pm) is available on {date}. "
                f"The PM slot is already taken."
            )
        elif pm:
            message = (
                f"Only the PM slot (2pm–6pm) is available on {date}. "
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
