"""
Unit tests for confirm_booking tool function.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

PENDING_BOOKING = {
    "booking_id": "HA-20260510-TEST",
    "phone_number": "+6591234567",
    "service_type": "General Servicing",
    "unit_count": "2",
    "address": "123 Orchard Road",
    "postal_code": "238858",
    "slot_date": "2026-05-10",
    "slot_window": "AM",
    "booking_status": "pending_confirmation",
    "aircon_brand": None,
    "notes": None,
}

CUSTOMER_ROW = {
    "phone_number": "+6591234567",
    "customer_name": "Alice Tan",
}


def make_db_mock(booking_data=None, customer_data=None):
    """Build a chainable Supabase mock that returns specified data."""
    def make_response(data):
        resp = MagicMock()
        resp.data = data if data is not None else []
        return resp

    call_count = {"n": 0}
    responses = []
    if booking_data is not None:
        responses.append(make_response(booking_data))
    if customer_data is not None:
        responses.append(make_response(customer_data))

    async def execute():
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(responses):
            return responses[idx]
        return make_response([])

    chain = MagicMock()
    chain.select.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute = execute

    db = MagicMock()
    db.table.return_value = chain
    return db


@pytest.fixture
def mock_client_config():
    config = MagicMock()
    config.client_id = "hey-aircon"
    config.google_calendar_creds = {"type": "service_account"}
    config.google_calendar_id = "test@group.calendar.google.com"
    config.sheets_sync_enabled = False
    return config


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_booking_success_path(mock_client_config):
    """Success: pending booking → slot available → calendar event created → confirmed."""
    db = make_db_mock(
        booking_data=[PENDING_BOOKING],
        customer_data=[CUSTOMER_ROW],
    )

    mock_availability = {"am_available": True, "pm_available": True}
    mock_calendar_event_id = "google_event_abc123"

    with patch("engine.core.tools.confirm_booking_tool.check_slot_availability", new=AsyncMock(return_value=mock_availability)), \
         patch("engine.core.tools.confirm_booking_tool.create_booking_event", new=AsyncMock(return_value=mock_calendar_event_id)), \
         patch("engine.core.tools.confirm_booking_tool.sync_booking_to_sheets", new=AsyncMock()), \
         patch("engine.core.tools.confirm_booking_tool.sync_customer_to_sheets", new=AsyncMock()):
        from engine.core.tools.confirm_booking_tool import confirm_booking
        result = await confirm_booking(
            db=db,
            client_config=mock_client_config,
            phone_number="+6591234567",
            booking_id="HA-20260510-TEST",
        )

    assert result["status"] == "confirmed"
    assert result["booking_id"] == "HA-20260510-TEST"
    assert result["calendar_event_id"] == mock_calendar_event_id
    assert "✅" in result["message"]


@pytest.mark.asyncio
async def test_confirm_booking_slot_conflict(mock_client_config):
    """Slot taken: returns conflict status, does not create calendar event."""
    db = make_db_mock(
        booking_data=[PENDING_BOOKING],
        customer_data=[CUSTOMER_ROW],
    )

    mock_availability = {"am_available": False, "pm_available": True}

    with patch("engine.core.tools.confirm_booking_tool.check_slot_availability", new=AsyncMock(return_value=mock_availability)), \
         patch("engine.core.tools.confirm_booking_tool.create_booking_event", new=AsyncMock()) as mock_create, \
         patch("engine.core.tools.confirm_booking_tool.sync_booking_to_sheets", new=AsyncMock()), \
         patch("engine.core.tools.confirm_booking_tool.sync_customer_to_sheets", new=AsyncMock()):
        from engine.core.tools.confirm_booking_tool import confirm_booking
        result = await confirm_booking(
            db=db,
            client_config=mock_client_config,
            phone_number="+6591234567",
            booking_id="HA-20260510-TEST",
        )

    assert result["status"] == "conflict"
    assert result["error"] == "slot_no_longer_available"
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_booking_not_found(mock_client_config):
    """Booking ID not in DB: returns error."""
    db = make_db_mock(booking_data=[])  # empty — booking not found

    from engine.core.tools.confirm_booking_tool import confirm_booking
    result = await confirm_booking(
        db=db,
        client_config=mock_client_config,
        phone_number="+6591234567",
        booking_id="HA-20260510-XXXX",
    )

    assert result["status"] == "error"
    assert result["error"] == "booking_not_found"


@pytest.mark.asyncio
async def test_confirm_booking_phone_mismatch(mock_client_config):
    """Phone number doesn't match booking owner: returns error."""
    booking = {**PENDING_BOOKING, "phone_number": "+6599999999"}
    db = make_db_mock(booking_data=[booking])

    from engine.core.tools.confirm_booking_tool import confirm_booking
    result = await confirm_booking(
        db=db,
        client_config=mock_client_config,
        phone_number="+6591234567",  # different from booking owner
        booking_id="HA-20260510-TEST",
    )

    assert result["status"] == "error"
    assert result["error"] == "phone_mismatch"


@pytest.mark.asyncio
async def test_confirm_booking_already_confirmed(mock_client_config):
    """Already confirmed booking: idempotent — returns confirmed without re-creating calendar event."""
    booking = {**PENDING_BOOKING, "booking_status": "confirmed", "calendar_event_id": "existing_event"}
    db = make_db_mock(booking_data=[booking])

    with patch("engine.core.tools.confirm_booking_tool.create_booking_event", new=AsyncMock()) as mock_create:
        from engine.core.tools.confirm_booking_tool import confirm_booking
        result = await confirm_booking(
            db=db,
            client_config=mock_client_config,
            phone_number="+6591234567",
            booking_id="HA-20260510-TEST",
        )

    assert result["status"] == "confirmed"
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_booking_pm_slot_check(mock_client_config):
    """PM slot booking: checks pm_available, not am_available."""
    pm_booking = {**PENDING_BOOKING, "slot_window": "PM"}
    db = make_db_mock(booking_data=[pm_booking], customer_data=[CUSTOMER_ROW])

    # PM available, AM not — should succeed
    mock_availability = {"am_available": False, "pm_available": True}

    with patch("engine.core.tools.confirm_booking_tool.check_slot_availability", new=AsyncMock(return_value=mock_availability)), \
         patch("engine.core.tools.confirm_booking_tool.create_booking_event", new=AsyncMock(return_value="event_pm")), \
         patch("engine.core.tools.confirm_booking_tool.sync_booking_to_sheets", new=AsyncMock()), \
         patch("engine.core.tools.confirm_booking_tool.sync_customer_to_sheets", new=AsyncMock()):
        from engine.core.tools.confirm_booking_tool import confirm_booking
        result = await confirm_booking(
            db=db,
            client_config=mock_client_config,
            phone_number="+6591234567",
            booking_id="HA-20260510-TEST",
        )

    assert result["status"] == "confirmed"
