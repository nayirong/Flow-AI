"""
Anthropic-format tool definitions for the HeyAircon agent.

These are the 4 tools the agent can call:
1. check_calendar_availability — check AM/PM slot availability for a date
2. write_booking               — confirm booking: calendar event + Supabase row
3. get_customer_bookings       — retrieve customer's recent bookings
4. escalate_to_human           — set escalation flag + notify human agent

Format: Anthropic tools API (https://docs.anthropic.com/en/docs/tool-use)
"""

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "check_calendar_availability",
        "description": (
            "Check whether the AM slot (9am–1pm) and/or PM slot (2pm–6pm) are available "
            "on a given date. Only call this AFTER you have confirmed ALL required booking "
            "fields from the customer: service type, number of units, full address, and "
            "postal code. Do not call this if any required booking field is still unknown. "
            "Returns availability status and a human-readable summary message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": (
                        "Date to check in YYYY-MM-DD format. "
                        "Must be at least 2 days from today (booking lead time)."
                    ),
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone string. Defaults to Asia/Singapore.",
                },
            },
            "required": ["date"],
        },
    },
    {
        "name": "write_booking",
        "description": (
            "Confirm and write a booking. Creates a Google Calendar event and records "
            "the booking in the database. Only call this AFTER the customer has explicitly "
            "confirmed all booking details (service type, date, time window, address, "
            "number of units). Do NOT call this to check availability — use "
            "check_calendar_availability first."
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
                        "Type of aircon service. One of: General Servicing, "
                        "Chemical Wash, Chemical Overhaul, Gas Top Up, Aircon Repair."
                    ),
                },
                "unit_count": {
                    "type": "string",
                    "description": "Number of aircon units to service (e.g. '2').",
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
                    "description": "AM (9am–1pm) or PM (2pm–6pm).",
                },
                "aircon_brand": {
                    "type": "string",
                    "description": "Optional. Aircon brand (e.g. Daikin, Mitsubishi).",
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
    },
    {
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
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Escalate the conversation to a human agent. Use this when: "
            "(1) the customer explicitly asks to speak to a person, "
            "(2) the requested slot is fully booked and the customer wants to arrange "
            "an alternative, "
            "(3) the customer requests a reschedule or cancellation, "
            "(4) the customer raises a complaint or urgent issue, "
            "(5) the question is outside the scope of the agent's context. "
            "After calling this, inform the customer that the team will follow up."
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
    },
]
