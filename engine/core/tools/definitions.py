"""
Anthropic-format tool definitions for the platform agent.

Tools are split into named constants so message_handler can compose a
phase-appropriate tool list per request:

  Phase A — no pending booking:
      check_calendar_availability, write_booking, get_customer_bookings, escalate_to_human

  Phase B — pending booking exists (awaiting customer confirmation):
      confirm_booking, get_customer_bookings, escalate_to_human
      (write_booking excluded — prevents the LLM from creating a duplicate)
      (check_calendar_availability excluded — slot was already checked in Phase A)

Use build_tool_definitions(pending_booking) from tools/__init__.py to get the
right list for the current request.

Format: Anthropic tools API (https://docs.anthropic.com/en/docs/tool-use)
"""

_CHECK_CALENDAR_TOOL: dict = {
    "name": "check_calendar_availability",
    "description": (
        "Check whether the AM and PM slots are available on a given date. "
        "Only call this AFTER you have confirmed ALL required booking "
        "fields from the customer: service type, number of units, full address, and "
        "postal code. Do not call this if any required booking field is still unknown. "
        "Specific times for each slot are in the APPOINTMENT WINDOWS section of your instructions. "
        "Returns availability status and a human-readable summary message."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": (
                    "Date to check in YYYY-MM-DD format. "
                    "Must respect the minimum booking lead time (see APPOINTMENT WINDOWS in instructions)."
                ),
            },
            "timezone": {
                "type": "string",
                "description": "Timezone string. Defaults to Asia/Singapore.",
            },
        },
        "required": ["date"],
    },
}

_WRITE_BOOKING_TOOL: dict = {
    "name": "write_booking",
    "description": (
        "Record a pending booking in the database. Does NOT create a Google Calendar event yet. "
        "Call this AFTER the customer has provided all booking details and the requested slot has been verified as available. "
        "If the customer already requested that exact date and AM/PM slot, do NOT ask for a second confirmation before calling this tool. "
        "Returns a booking_id and a summary for you to send to the customer. "
        "After calling this, send the customer a booking summary and ask them to confirm. "
        "Once they reply affirmatively, call confirm_booking to finalise the appointment. "
        "Do NOT call this to check availability — use check_calendar_availability first."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_name": {
                "type": "string",
                "description": "Customer's full name.",
            },
            "service_type": {
                "type": "string",
                "description": (
                    "Type of service requested by the customer, based on the active "
                    "client's configured service catalog."
                ),
            },
            "unit_count": {
                "type": "string",
                "description": "Quantity associated with the service (e.g. '2').",
            },
            "address": {
                "type": "string",
                "description": "Full street address for the service.",
            },
            "postal_code": {
                "type": "string",
                "description": "6-digit Singapore postal code.",
            },
            "slot_date": {
                "type": "string",
                "description": "Confirmed booking date in YYYY-MM-DD format.",
            },
            "slot_window": {
                "type": "string",
                "enum": ["AM", "PM"],
                "description": "AM or PM slot. Specific times are in the APPOINTMENT WINDOWS section of your instructions.",
            },
            "service_brand": {
                "type": "string",
                "description": "Optional. Brand information if relevant to the service.",
            },
            "notes": {
                "type": "string",
                "description": "Optional. Any additional notes from the customer.",
            },
        },
        "required": [
            "customer_name",
            "service_type",
            "unit_count",
            "address",
            "postal_code",
            "slot_date",
            "slot_window",
        ],
    },
}

_CONFIRM_BOOKING_TOOL: dict = {
    "name": "confirm_booking",
    "description": (
        "Finalise the customer's pending booking. "
        "Call this when the customer confirms they want to go ahead — even if phrased casually "
        "(e.g. 'yes', 'ok', 'confirm', 'go ahead', 'sure', 'correct'). "
        "You MUST pass the exact booking_id shown in the PENDING BOOKING context above. "
        "Do NOT ask the customer for their booking reference — you already have it. "
        "If the customer asks a question instead of confirming, answer it — do NOT call this tool. "
        "This creates the Google Calendar event and updates the booking status to confirmed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "booking_id": {
                "type": "string",
                "description": (
                    "The booking ID from the PENDING BOOKING context. "
                    "Use the exact ID provided — do not guess or fabricate it."
                ),
            },
        },
        "required": ["booking_id"],
    },
}

_GET_CUSTOMER_BOOKINGS_TOOL: dict = {
    "name": "get_customer_bookings",
    "description": (
        "Retrieve the customer's bookings. Use this when a customer asks about their "
        "appointments, booking status, or wants to reschedule or cancel. "
        "Set 'filter' based on what the customer is asking: "
        "'upcoming' for future appointments (today onwards), "
        "'past' for previous appointments, "
        "'all' when unspecified or ambiguous. "
        "Returns booking ID, service type, date, time window, and status."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "enum": ["upcoming", "past", "all"],
                "description": (
                    "Which bookings to retrieve. "
                    "'upcoming' = today and future dates (use when customer asks about next appointment, upcoming bookings). "
                    "'past' = dates before today (use when customer asks about previous or past bookings). "
                    "'all' = no date filter (use when customer asks generally about their bookings without specifying past or future)."
                ),
            },
        },
        "required": [],
    },
}

_ESCALATE_TO_HUMAN_TOOL: dict = {
    "name": "escalate_to_human",
    "description": (
        "Escalate the conversation to a human agent. Use this tool in TWO scenarios:\n"
        "1. IMMEDIATE (capability-based): You have determined the customer's question is unanswerable "
        "because the required information is not in your knowledge base, policies, or available tools. "
        "See the UNANSWERABLE QUESTION CATEGORIES in your system instructions for examples.\n"
        "2. GRADUAL (customer-requested): The customer explicitly asks to speak to a person, "
        "or expresses frustration/anger that requires human judgment.\n"
        "After calling this, you must inform the customer that a team member will follow up. "
        "Include a clear reason parameter explaining which category applies (e.g., "
        "'Customer asked for real-time dispatch information (Category 1)' or "
        "'Customer requested to speak to a human')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": (
                    "Brief reason for escalation (1–2 sentences). "
                    "This is sent to the human agent as context. "
                    "Example: 'Customer requested to reschedule booking HA-20260430-A3F2 "
                    "to a different date.'"
                ),
            },
        },
        "required": ["reason"],
    },
}


def build_tool_definitions(pending_booking) -> list:
    """
    Return the phase-appropriate tool list for this request.

    Phase A (no pending booking):
        check_calendar_availability, write_booking, get_customer_bookings, escalate_to_human

    Phase B (pending booking exists):
        confirm_booking, get_customer_bookings, escalate_to_human

    Excluding write_booking in Phase B prevents the LLM from creating a duplicate
    pending row instead of confirming the existing one. Excluding check_calendar in
    Phase B prevents the LLM from re-entering the booking collection flow.

    Args:
        pending_booking: The pending booking dict, or None if no pending booking exists.

    Returns:
        List of Anthropic-format tool definition dicts.
    """
    if pending_booking:
        return [
            _CONFIRM_BOOKING_TOOL,
            _GET_CUSTOMER_BOOKINGS_TOOL,
            _ESCALATE_TO_HUMAN_TOOL,
        ]
    return [
        _CHECK_CALENDAR_TOOL,
        _WRITE_BOOKING_TOOL,
        _GET_CUSTOMER_BOOKINGS_TOOL,
        _ESCALATE_TO_HUMAN_TOOL,
    ]


# Legacy flat list kept for backwards-compatibility with any direct imports.
# New code should use build_tool_definitions(pending_booking) instead.
TOOL_DEFINITIONS: list = [
    _CHECK_CALENDAR_TOOL,
    _WRITE_BOOKING_TOOL,
    _CONFIRM_BOOKING_TOOL,
    _GET_CUSTOMER_BOOKINGS_TOOL,
    _ESCALATE_TO_HUMAN_TOOL,
]
