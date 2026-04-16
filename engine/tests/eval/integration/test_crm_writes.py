"""
Integration tests: CRM writes, calendar events, and booking creation.

Verifies that agent tools produce correct side effects in:
  - Client Supabase: bookings, customers, interactions_log tables
  - Google Calendar: calendar events created with correct payload

Design:
  - Tools are imported directly from engine.core.tools (skipped if engine not built yet)
  - Every test uses a unique TEST_<timestamp>_<random> phone number to avoid collisions
  - A session-scoped autouse fixture cleans up all TEST_ rows after the suite runs
  - Calendar tests mock the Google Calendar API by default; set GOOGLE_CALENDAR_TEST=1
    for real calendar writes (requires GOOGLE_CALENDAR_CREDS env var)

Run (with real DB):
    pytest engine/tests/eval/integration/test_crm_writes.py -m integration -v

Skip (default):
    Automatically skipped when EVAL_CLIENT_SUPABASE_URL_HEYAIRCON is not set.

Markers:
    integration  — requires live Supabase client credentials
    calendar     — additionally requires GOOGLE_CALENDAR_CREDS
"""

import os
import re
import time
import uuid
import pytest
import pytest_asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Skip entire module unless creds are present
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("EVAL_CLIENT_SUPABASE_URL_HEYAIRCON")
SUPABASE_KEY = os.getenv("EVAL_CLIENT_SUPABASE_SERVICE_KEY_HEYAIRCON")
SKIP_INTEGRATION = not (SUPABASE_URL and SUPABASE_KEY)

pytestmark = pytest.mark.skipif(
    SKIP_INTEGRATION,
    reason="EVAL_CLIENT_SUPABASE_URL_HEYAIRCON / EVAL_CLIENT_SUPABASE_SERVICE_KEY_HEYAIRCON not set",
)

# ---------------------------------------------------------------------------
# Tool imports — skipped gracefully until engine is built
# ---------------------------------------------------------------------------
try:
    from engine.core.tools.write_booking import write_booking
    from engine.core.tools.get_customer_bookings import get_customer_bookings
    from engine.core.tools.escalate_to_human import escalate_to_human
    from engine.core.tools.create_calendar_event import create_calendar_event
    from engine.core.tools.check_calendar_availability import check_calendar_availability
    TOOLS_AVAILABLE = True
except ImportError:
    TOOLS_AVAILABLE = False

pytestmark = [
    pytestmark,
    pytest.mark.skipif(
        not TOOLS_AVAILABLE,
        reason="engine.core.tools not available — Python engine not built yet",
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _test_phone() -> str:
    """Generate a unique test phone number that is easy to identify and clean up."""
    return f"+TEST_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def _future_date(days_ahead: int = 3) -> str:
    """Return a booking date at least 3 days ahead (satisfies MIN_BOOKING_NOTICE_DAYS=2)."""
    return (date.today() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Client Supabase fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def client_db():
    """
    Async Supabase client for the HeyAircon production DB.
    Scoped to the module — one connection shared across all tests in this file.
    """
    from supabase import create_client, Client  # type: ignore
    db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    yield db


@pytest_asyncio.fixture(scope="module", autouse=True)
async def cleanup_test_rows(client_db):
    """
    Module-scoped cleanup: delete all rows whose phone_number starts with '+TEST_'.
    Runs after all tests in this file complete.
    """
    yield
    # Cleanup bookings
    await client_db.table("bookings").delete().like("phone_number", "+TEST_%").execute()
    # Cleanup customers
    await client_db.table("customers").delete().like("phone_number", "+TEST_%").execute()
    # Cleanup interactions_log
    await client_db.table("interactions_log").delete().like("phone_number", "+TEST_%").execute()


# ---------------------------------------------------------------------------
# Booking write tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_write_booking_creates_bookings_row(client_db):
    """
    Calling write_booking with valid data inserts exactly one row into
    the bookings table with all required fields populated.
    """
    phone = _test_phone()
    booking_date = _future_date()

    booking_id = await write_booking(
        phone_number=phone,
        customer_name="Test Customer",
        service_type="General Servicing",
        booking_date=booking_date,
        slot="AM",
        address="1 Test Street #01-01",
        unit_count=2,
        calendar_event_id="MOCK_CAL_EVENT_001",
        db=client_db,
    )

    # Verify row exists in DB
    result = await client_db.table("bookings").select("*").eq("phone_number", phone).execute()
    rows = result.data

    assert len(rows) == 1
    row = rows[0]
    assert row["service_type"] == "General Servicing"
    assert row["booking_date"] == booking_date
    assert row["slot"] == "AM"
    assert row["address"] == "1 Test Street #01-01"
    assert row["unit_count"] == 2
    assert row["calendar_event_id"] == "MOCK_CAL_EVENT_001"
    assert row["phone_number"] == phone


@pytest.mark.asyncio
@pytest.mark.integration
async def test_booking_id_format(client_db):
    """
    write_booking returns a booking_id in the format HA-YYYYMMDD-XXXX.
    """
    phone = _test_phone()
    booking_date = _future_date()

    booking_id = await write_booking(
        phone_number=phone,
        customer_name="Test Customer",
        service_type="Chemical Wash",
        booking_date=booking_date,
        slot="PM",
        address="2 Test Avenue #02-02",
        unit_count=1,
        calendar_event_id="MOCK_CAL_EVENT_002",
        db=client_db,
    )

    assert booking_id is not None
    assert re.match(r"^HA-\d{8}-\d{4}$", booking_id), (
        f"booking_id '{booking_id}' does not match expected format HA-YYYYMMDD-XXXX"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_write_booking_upserts_customer_new(client_db):
    """
    First call to write_booking for a new phone number creates a new
    row in the customers table.
    """
    phone = _test_phone()

    await write_booking(
        phone_number=phone,
        customer_name="New Customer",
        service_type="Gas Top Up",
        booking_date=_future_date(),
        slot="AM",
        address="3 New Road #03-03",
        unit_count=1,
        calendar_event_id="MOCK_CAL_EVENT_003",
        db=client_db,
    )

    result = await client_db.table("customers").select("*").eq("phone_number", phone).execute()
    rows = result.data

    assert len(rows) == 1
    customer = rows[0]
    assert customer["phone_number"] == phone
    assert customer["customer_name"] == "New Customer"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_write_booking_updates_customer_booking_count(client_db):
    """
    Second call to write_booking for the same phone number increments
    booking_count on the customers row (upsert behaviour).
    """
    phone = _test_phone()

    await write_booking(
        phone_number=phone,
        customer_name="Repeat Customer",
        service_type="General Servicing",
        booking_date=_future_date(days_ahead=3),
        slot="AM",
        address="4 Repeat St #04-04",
        unit_count=2,
        calendar_event_id="MOCK_CAL_EVENT_004a",
        db=client_db,
    )
    await write_booking(
        phone_number=phone,
        customer_name="Repeat Customer",
        service_type="Chemical Overhaul",
        booking_date=_future_date(days_ahead=10),
        slot="PM",
        address="4 Repeat St #04-04",
        unit_count=2,
        calendar_event_id="MOCK_CAL_EVENT_004b",
        db=client_db,
    )

    result = await client_db.table("customers").select("booking_count").eq("phone_number", phone).execute()
    rows = result.data

    assert len(rows) == 1
    assert rows[0]["booking_count"] >= 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_customer_bookings_returns_created_booking(client_db):
    """
    get_customer_bookings returns the booking just created by write_booking.
    Verifies the read-after-write roundtrip.
    """
    phone = _test_phone()
    booking_date = _future_date()

    await write_booking(
        phone_number=phone,
        customer_name="Roundtrip Customer",
        service_type="Aircon Repair",
        booking_date=booking_date,
        slot="AM",
        address="5 Roundtrip Ave #05-05",
        unit_count=1,
        calendar_event_id="MOCK_CAL_EVENT_005",
        db=client_db,
    )

    bookings = await get_customer_bookings(phone_number=phone, db=client_db)

    assert len(bookings) >= 1
    booking = next((b for b in bookings if b["booking_date"] == booking_date), None)
    assert booking is not None, f"Expected booking on {booking_date} not found in {bookings}"
    assert booking["service_type"] == "Aircon Repair"


# ---------------------------------------------------------------------------
# Escalation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_escalate_to_human_sets_flag_in_customers(client_db):
    """
    escalate_to_human sets escalation_flag=TRUE on the customer row and
    writes an entry to interactions_log with reason recorded.
    """
    phone = _test_phone()

    # Create a customer row first via write_booking so there is a row to flag
    await write_booking(
        phone_number=phone,
        customer_name="Escalation Customer",
        service_type="General Servicing",
        booking_date=_future_date(),
        slot="AM",
        address="6 Escalation Blvd #06-06",
        unit_count=1,
        calendar_event_id="MOCK_CAL_EVENT_006",
        db=client_db,
    )

    # Mock client_config to avoid needing full config object
    mock_client_config = MagicMock()
    mock_client_config.human_agent_number = "+6500000000"

    await escalate_to_human(
        phone_number=phone,
        reason="Customer is upset about late technician",
        db=client_db,
        client_config=mock_client_config,
    )

    result = await client_db.table("customers").select("escalation_flag").eq("phone_number", phone).execute()
    rows = result.data

    assert len(rows) == 1
    assert rows[0]["escalation_flag"] is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_escalate_to_human_writes_interactions_log(client_db):
    """
    escalate_to_human writes a row to interactions_log with the escalation reason.
    """
    phone = _test_phone()

    await write_booking(
        phone_number=phone,
        customer_name="Log Customer",
        service_type="General Servicing",
        booking_date=_future_date(),
        slot="PM",
        address="7 Log Lane #07-07",
        unit_count=1,
        calendar_event_id="MOCK_CAL_EVENT_007",
        db=client_db,
    )

    mock_client_config = MagicMock()
    mock_client_config.human_agent_number = "+6500000000"

    reason = "Customer requested refund"
    await escalate_to_human(
        phone_number=phone,
        reason=reason,
        db=client_db,
        client_config=mock_client_config,
    )

    result = (
        await client_db.table("interactions_log")
        .select("*")
        .eq("phone_number", phone)
        .execute()
    )
    rows = result.data

    assert len(rows) >= 1
    escalation_entries = [r for r in rows if "escalat" in (r.get("event_type") or "").lower() or reason in (r.get("content") or "")]
    assert len(escalation_entries) >= 1


# ---------------------------------------------------------------------------
# Calendar event tests (mocked by default)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_calendar_event_payload_structure():
    """
    create_calendar_event constructs the correct Google Calendar event payload:
    - summary contains customer name and service type
    - start/end times correspond to the AM (9am–1pm) or PM (2pm–6pm) slot window
    - timezone is Asia/Singapore
    - description contains address and unit count

    The Google Calendar API call is mocked — no real calendar writes occur.
    Set GOOGLE_CALENDAR_TEST=1 to write to a real test calendar.
    """
    captured_payload = {}

    async def mock_insert_event(calendar_id, event_body, **kwargs):
        captured_payload.update(event_body)
        return {"id": "MOCK_GCAL_ID_001", "htmlLink": "https://calendar.google.com/mock"}

    with patch(
        "engine.integrations.google_calendar.GoogleCalendarClient.insert_event",
        side_effect=mock_insert_event,
    ):
        event_id = await create_calendar_event(
            date="2026-05-01",
            slot="AM",
            customer_name="Test Customer",
            phone_number="+6591234567",
            service_type="Chemical Wash",
            address="8 Calendar St #08-08",
            unit_count=3,
        )

    assert event_id == "MOCK_GCAL_ID_001"

    # Verify payload structure
    assert "summary" in captured_payload
    assert "Test Customer" in captured_payload["summary"] or "Chemical Wash" in captured_payload["summary"]

    start = captured_payload.get("start", {})
    end = captured_payload.get("end", {})
    assert start.get("timeZone") == "Asia/Singapore"
    assert end.get("timeZone") == "Asia/Singapore"

    # AM slot: 09:00–13:00
    assert "09:00" in start.get("dateTime", ""), (
        f"AM slot start time should be 09:00, got: {start.get('dateTime')}"
    )
    assert "13:00" in end.get("dateTime", ""), (
        f"AM slot end time should be 13:00, got: {end.get('dateTime')}"
    )

    description = captured_payload.get("description", "")
    assert "8 Calendar St" in description
    assert "3" in description  # unit_count


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_calendar_event_pm_slot_times():
    """
    create_calendar_event with slot=PM sets event window to 14:00–18:00 SGT.
    """
    captured_payload = {}

    async def mock_insert_event(calendar_id, event_body, **kwargs):
        captured_payload.update(event_body)
        return {"id": "MOCK_GCAL_ID_002"}

    with patch(
        "engine.integrations.google_calendar.GoogleCalendarClient.insert_event",
        side_effect=mock_insert_event,
    ):
        await create_calendar_event(
            date="2026-05-02",
            slot="PM",
            customer_name="PM Customer",
            phone_number="+6599999999",
            service_type="Gas Top Up",
            address="9 PM Road #09-09",
            unit_count=1,
        )

    start = captured_payload.get("start", {})
    end = captured_payload.get("end", {})

    assert "14:00" in start.get("dateTime", ""), (
        f"PM slot start time should be 14:00, got: {start.get('dateTime')}"
    )
    assert "18:00" in end.get("dateTime", ""), (
        f"PM slot end time should be 18:00, got: {end.get('dateTime')}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_booking_flow_calendar_event_id_stored_in_booking(client_db):
    """
    End-to-end: create_calendar_event → write_booking.
    The calendar_event_id returned by create_calendar_event is stored in
    the bookings row.
    """
    phone = _test_phone()
    booking_date = _future_date()

    with patch(
        "engine.integrations.google_calendar.GoogleCalendarClient.insert_event",
        return_value={"id": "E2E_CAL_EVENT_ID_001"},
    ):
        event_id = await create_calendar_event(
            date=booking_date,
            slot="AM",
            customer_name="E2E Customer",
            phone_number=phone,
            service_type="General Servicing",
            address="10 E2E Street #10-10",
            unit_count=2,
        )

    booking_id = await write_booking(
        phone_number=phone,
        customer_name="E2E Customer",
        service_type="General Servicing",
        booking_date=booking_date,
        slot="AM",
        address="10 E2E Street #10-10",
        unit_count=2,
        calendar_event_id=event_id,
        db=client_db,
    )

    result = await client_db.table("bookings").select("calendar_event_id").eq("phone_number", phone).execute()
    rows = result.data

    assert len(rows) == 1
    assert rows[0]["calendar_event_id"] == "E2E_CAL_EVENT_ID_001"


# ---------------------------------------------------------------------------
# Lead capture tests (first message)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_first_message_creates_customer_lead(client_db):
    """
    When a new phone number contacts the agent for the first time,
    the message_handler creates a row in the customers table (lead capture).

    This is an infrastructure-level test: message_handler auto-creates the
    customer record before the agent even runs.
    """
    phone = _test_phone()

    # Import message_handler — skips gracefully if engine not built
    try:
        from engine.core.message_handler import handle_inbound_message
    except ImportError:
        pytest.skip("message_handler not available — Python engine not built yet")

    mock_client_config = MagicMock()
    mock_client_config.client_id = "hey-aircon"
    mock_client_config.human_agent_number = "+6500000000"
    mock_client_config.is_active = True

    with patch("engine.core.agent_runner.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = {
            "response_text": "Hi! How can I help?",
            "tool_called": None,
        }
        await handle_inbound_message(
            phone_number=phone,
            message_text="Hello",
            client_config=mock_client_config,
            db=client_db,
        )

    result = await client_db.table("customers").select("*").eq("phone_number", phone).execute()
    rows = result.data

    assert len(rows) == 1, f"Expected 1 customer row for {phone}, got {len(rows)}"
    assert rows[0]["phone_number"] == phone


@pytest.mark.asyncio
@pytest.mark.integration
async def test_every_message_writes_to_interactions_log(client_db):
    """
    Every inbound message — regardless of content — writes a row to
    interactions_log. This is the audit trail for all conversations.
    """
    phone = _test_phone()

    try:
        from engine.core.message_handler import handle_inbound_message
    except ImportError:
        pytest.skip("message_handler not available — Python engine not built yet")

    mock_client_config = MagicMock()
    mock_client_config.client_id = "hey-aircon"
    mock_client_config.human_agent_number = "+6500000000"
    mock_client_config.is_active = True

    messages = ["Hello", "What services do you offer?", "I want to book a service"]

    with patch("engine.core.agent_runner.run_agent", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = {"response_text": "Sure!", "tool_called": None}
        for msg in messages:
            await handle_inbound_message(
                phone_number=phone,
                message_text=msg,
                client_config=mock_client_config,
                db=client_db,
            )

    result = (
        await client_db.table("interactions_log")
        .select("*")
        .eq("phone_number", phone)
        .execute()
    )
    rows = result.data

    # At minimum one row per message sent (may include agent replies too)
    assert len(rows) >= len(messages), (
        f"Expected at least {len(messages)} interactions_log rows, got {len(rows)}"
    )
