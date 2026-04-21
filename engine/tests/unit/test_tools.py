"""
Slice 5 — Tool unit tests.

Tests for all 4 tool functions and build_tool_dispatch().
Google Calendar API and Supabase are fully mocked — no real external calls.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_client_config(
    has_calendar: bool = True,
    human_agent_number: str = "6590000001",
) -> MagicMock:
    cfg = MagicMock()
    cfg.client_id = "hey-aircon"
    cfg.human_agent_number = human_agent_number
    cfg.meta_phone_number_id = "123456789"
    cfg.meta_whatsapp_token = "test_token"
    if has_calendar:
        cfg.google_calendar_creds = {"type": "service_account", "project_id": "test"}
        cfg.google_calendar_id = "primary@group.calendar.google.com"
    else:
        cfg.google_calendar_creds = None
        cfg.google_calendar_id = None
    return cfg


def _make_db() -> MagicMock:
    """Chainable Supabase mock that captures the last execute() call."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    db = MagicMock()
    db.table.return_value = chain
    return db


# ── check_calendar_availability ───────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.integrations.google_calendar.check_slot_availability", new_callable=AsyncMock)
async def test_check_availability_both_slots_free(mock_check):
    """Both AM and PM available → message says both are free."""
    from engine.core.tools.calendar_tools import check_calendar_availability

    mock_check.return_value = {
        "date": "2026-05-01",
        "am_available": True,
        "pm_available": True,
    }
    cfg = _make_client_config(has_calendar=True)
    result = await check_calendar_availability(cfg, date="2026-05-01")

    assert result["am_available"] is True
    assert result["pm_available"] is True
    assert "Both" in result["message"]


@pytest.mark.asyncio
@patch("engine.integrations.google_calendar.check_slot_availability", new_callable=AsyncMock)
async def test_check_availability_am_only(mock_check):
    """PM taken → message mentions only AM available."""
    from engine.core.tools.calendar_tools import check_calendar_availability

    mock_check.return_value = {
        "date": "2026-05-01",
        "am_available": True,
        "pm_available": False,
    }
    cfg = _make_client_config(has_calendar=True)
    result = await check_calendar_availability(cfg, date="2026-05-01")

    assert result["am_available"] is True
    assert result["pm_available"] is False
    assert "AM" in result["message"]
    assert "PM slot is already taken" in result["message"]


@pytest.mark.asyncio
async def test_check_availability_no_calendar_config():
    """No calendar configured → both slots returned as available, no API call."""
    from engine.core.tools.calendar_tools import check_calendar_availability

    cfg = _make_client_config(has_calendar=False)
    result = await check_calendar_availability(cfg, date="2026-05-01")

    assert result["am_available"] is True
    assert result["pm_available"] is True


@pytest.mark.asyncio
@patch(
    "engine.integrations.google_calendar.check_slot_availability",
    new_callable=AsyncMock,
    side_effect=Exception("Google API down"),
)
async def test_check_availability_google_error_returns_unavailable(mock_check):
    """Google Calendar error → returns both unavailable with error flag, never raises."""
    from engine.core.tools.calendar_tools import check_calendar_availability

    cfg = _make_client_config(has_calendar=True)
    result = await check_calendar_availability(cfg, date="2026-05-01")

    assert result["am_available"] is False
    assert result["pm_available"] is False
    assert result.get("error") == "calendar_check_failed"


# ── write_booking ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.integrations.google_calendar.create_booking_event", new_callable=AsyncMock)
async def test_write_booking_inserts_row_and_updates_customer(mock_create_event):
    """write_booking creates calendar event, inserts booking row, updates customer."""
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.return_value = "cal_event_xyz"
    db = _make_db()
    cfg = _make_client_config(has_calendar=True)

    result = await write_booking(
        db=db,
        client_config=cfg,
        phone_number="6591234567",
        customer_name="Alice Tan",
        service_type="General Servicing",
        unit_count="2",
        address="10 Jurong East Street 21",
        postal_code="609607",
        slot_date="2026-05-01",
        slot_window="AM",
    )

    assert result["status"] == "Confirmed"
    assert result["calendar_event_id"] == "cal_event_xyz"
    assert result["booking_id"].startswith("HA-20260501-")
    assert len(result["booking_id"]) == len("HA-20260501-XXXX")

    # bookings + customers tables both touched
    table_names = [call[0][0] for call in db.table.call_args_list]
    assert "bookings" in table_names
    assert "customers" in table_names


def _make_db_for_booking_step3(total_bookings: int):
    """
    Supabase mock for write_booking Step 3.

    Call sequence:
      db.table("bookings").insert(...).execute()         → booking INSERT
      db.table("customers").update({name}).eq(...).execute()   → name UPDATE
      db.table("customers").select("*").eq(...).limit(1).execute() → re-fetch with trigger-updated total_bookings
    """
    bookings_chain = MagicMock()
    bookings_chain.insert.return_value = bookings_chain
    bookings_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    update_chain = MagicMock()
    update_chain.update.return_value = update_chain
    update_chain.eq.return_value = update_chain
    update_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # Re-fetch chain returns the trigger-updated customer row
    refetch_chain = MagicMock()
    refetch_chain.select.return_value = refetch_chain
    refetch_chain.eq.return_value = refetch_chain
    refetch_chain.limit.return_value = refetch_chain
    refetch_chain.execute = AsyncMock(
        return_value=MagicMock(data=[{"id": 1, "total_bookings": total_bookings}])
    )

    customers_calls = [update_chain, refetch_chain]
    customers_call_count = {"n": 0}

    def table_router(name):
        if name == "bookings":
            return bookings_chain
        idx = customers_call_count["n"]
        customers_call_count["n"] += 1
        return customers_calls[idx] if idx < len(customers_calls) else refetch_chain

    db = MagicMock()
    db.table.side_effect = table_router
    db._update_chain = update_chain
    return db


@pytest.mark.asyncio
@patch("engine.integrations.google_calendar.create_booking_event", new_callable=AsyncMock)
async def test_write_booking_updates_customer_name_and_syncs_sheets(mock_create_event):
    """
    write_booking Step 3: UPDATE sets customer_name; re-fetch picks up
    trigger-updated total_bookings for Sheets sync.
    """
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.return_value = "cal_event_new"
    db = _make_db_for_booking_step3(total_bookings=1)
    cfg = _make_client_config(has_calendar=True)

    result = await write_booking(
        db=db,
        client_config=cfg,
        phone_number="6591111111",
        customer_name="Carol Ng",
        service_type="General Servicing",
        unit_count="1",
        address="3 Bedok North Ave",
        postal_code="460003",
        slot_date="2026-05-10",
        slot_window="AM",
    )

    assert result["status"] == "Confirmed"

    # UPDATE must only set customer_name — no booking_count field
    update_call_args = db._update_chain.update.call_args
    assert update_call_args is not None
    updated_data = update_call_args[0][0]
    assert updated_data == {"customer_name": "Carol Ng"}
    assert "booking_count" not in updated_data
    assert "total_bookings" not in updated_data


@pytest.mark.asyncio
@patch("engine.integrations.google_calendar.create_booking_event", new_callable=AsyncMock)
async def test_write_booking_refetches_customer_after_update(mock_create_event):
    """
    write_booking Step 3: after updating customer_name, a SELECT * re-fetch
    must be issued so the Sheets sync receives the trigger-updated total_bookings.
    """
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.return_value = "cal_event_return"
    db = _make_db_for_booking_step3(total_bookings=2)
    cfg = _make_client_config(has_calendar=True)

    result = await write_booking(
        db=db,
        client_config=cfg,
        phone_number="6592222222",
        customer_name="David Koh",
        service_type="Chemical Wash",
        unit_count="2",
        address="8 Bishan Street 11",
        postal_code="570008",
        slot_date="2026-05-15",
        slot_window="PM",
    )

    assert result["status"] == "Confirmed"
    # The refetch chain's execute must have been awaited
    db._update_chain.eq.assert_called()


@pytest.mark.asyncio
async def test_write_booking_no_calendar_raises_and_alerts():
    """No calendar config → raises RuntimeError and alerts human agent (never writes to DB)."""
    from engine.core.tools.booking_tools import write_booking
    from unittest.mock import AsyncMock, patch

    db = _make_db()
    cfg = _make_client_config(has_calendar=False)

    with patch("engine.core.tools.booking_tools._alert_booking_failure", new_callable=AsyncMock) as mock_alert:
        with pytest.raises(RuntimeError, match="Google Calendar not configured"):
            await write_booking(
                db=db,
                client_config=cfg,
                phone_number="6591234567",
                customer_name="Bob Lim",
                service_type="Chemical Wash",
                unit_count="1",
                address="5 Tampines Ave",
                postal_code="520005",
                slot_date="2026-05-02",
                slot_window="PM",
            )

    mock_alert.assert_called_once()
    # DB must NOT have been touched
    db.table.assert_not_called()


def test_generate_booking_id_format():
    """Booking ID must match HA-YYYYMMDD-XXXX format."""
    from engine.core.tools.booking_tools import _generate_booking_id

    bid = _generate_booking_id("2026-05-01")
    assert bid.startswith("HA-20260501-")
    assert len(bid) == 16  # "HA-" + 8 + "-" + 4


# ── get_customer_bookings ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_customer_bookings_returns_rows():
    """Returns a list of booking dicts from Supabase."""
    from engine.core.tools.booking_tools import get_customer_bookings

    mock_rows = [
        {
            "booking_id": "HA-20260501-A1B2",
            "service_type": "General Servicing",
            "slot_date": "2026-05-01",
            "slot_window": "AM",
            "booking_status": "Confirmed",
        }
    ]

    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(return_value=MagicMock(data=mock_rows))

    db = MagicMock()
    db.table.return_value = chain

    result = await get_customer_bookings(db=db, phone_number="6591234567")

    assert result["count"] == 1
    assert result["bookings"][0]["booking_id"] == "HA-20260501-A1B2"


@pytest.mark.asyncio
async def test_get_customer_bookings_db_error_returns_empty():
    """DB error → returns empty bookings list, never raises."""
    from engine.core.tools.booking_tools import get_customer_bookings

    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(side_effect=Exception("DB down"))

    db = MagicMock()
    db.table.return_value = chain

    result = await get_customer_bookings(db=db, phone_number="6591234567")

    assert result["bookings"] == []
    assert result["count"] == 0


# ── escalate_to_human ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_escalate_sets_flag_and_notifies_human(mock_send):
    """Escalation sets DB flag and sends WhatsApp alert to human agent."""
    from engine.core.tools.escalation_tool import escalate_to_human

    db = _make_db()
    cfg = _make_client_config()

    result = await escalate_to_human(
        db=db,
        client_config=cfg,
        phone_number="6591234567",
        reason="Customer requested to speak to a person.",
    )

    assert result["status"] == "escalated"

    # DB update called
    table_names = [call[0][0] for call in db.table.call_args_list]
    assert "customers" in table_names

    # Human agent notified
    mock_send.assert_awaited_once()
    call_kwargs = mock_send.call_args[1] if mock_send.call_args[1] else {}
    call_args = mock_send.call_args[0] if mock_send.call_args[0] else ()
    # Recipient should be the human agent number
    to_number = call_kwargs.get("to_phone_number") or (call_args[1] if len(call_args) > 1 else None)
    assert to_number == cfg.human_agent_number


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_escalate_no_human_number_does_not_crash(mock_send):
    """No human_agent_number → skip WhatsApp alert, still return escalated."""
    from engine.core.tools.escalation_tool import escalate_to_human

    db = _make_db()
    cfg = _make_client_config()
    cfg.human_agent_number = None

    result = await escalate_to_human(
        db=db,
        client_config=cfg,
        phone_number="6591234567",
        reason="Out of scope query.",
    )

    assert result["status"] == "escalated"
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_escalate_db_failure_does_not_crash(mock_send):
    """DB failure on flag update → still returns escalated (non-fatal)."""
    from engine.core.tools.escalation_tool import escalate_to_human

    chain = MagicMock()
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.execute = AsyncMock(side_effect=Exception("DB write failed"))
    db = MagicMock()
    db.table.return_value = chain

    cfg = _make_client_config()

    result = await escalate_to_human(
        db=db,
        client_config=cfg,
        phone_number="6591234567",
        reason="Complaint.",
    )

    assert result["status"] == "escalated"


# ── build_tool_dispatch ───────────────────────────────────────────────────────

def test_build_tool_dispatch_registers_all_tools():
    """build_tool_dispatch returns all 4 expected tool names."""
    from engine.core.tools import build_tool_dispatch

    db = _make_db()
    cfg = _make_client_config()

    dispatch = build_tool_dispatch(db=db, client_config=cfg, phone_number="6591234567")

    assert set(dispatch.keys()) == {
        "check_calendar_availability",
        "write_booking",
        "get_customer_bookings",
        "escalate_to_human",
    }


def test_tool_definitions_count():
    """TOOL_DEFINITIONS exports exactly 4 tool dicts."""
    from engine.core.tools import TOOL_DEFINITIONS

    assert len(TOOL_DEFINITIONS) == 4
    names = {t["name"] for t in TOOL_DEFINITIONS}
    assert names == {
        "check_calendar_availability",
        "write_booking",
        "get_customer_bookings",
        "escalate_to_human",
    }


def test_tool_definitions_have_required_keys():
    """Every tool definition has name, description, and input_schema."""
    from engine.core.tools import TOOL_DEFINITIONS

    for tool in TOOL_DEFINITIONS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"
        assert "required" in tool["input_schema"]
