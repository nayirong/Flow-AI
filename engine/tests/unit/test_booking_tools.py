"""
Unit tests for booking tool functions.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """Mock Supabase async client with chainable table() interface."""
    mock_response = MagicMock()
    mock_response.data = []
    mock_execute = AsyncMock(return_value=mock_response)

    chain = MagicMock()
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.lt.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = mock_execute

    db = MagicMock()
    db.table.return_value = chain
    return db


@pytest.fixture
def mock_client_config():
    """Minimal mock ClientConfig."""
    config = MagicMock()
    config.client_id = "hey-aircon"
    config.human_agent_number = "+6591234567"
    config.google_calendar_creds = {"type": "service_account"}
    config.google_calendar_id = "test@group.calendar.google.com"
    config.sheets_sync_enabled = False
    return config


BOOKING_KWARGS = dict(
    customer_name="Alice Tan",
    service_type="General Servicing",
    unit_count="2",
    address="123 Orchard Road",
    postal_code="238858",
    slot_date="2026-05-10",
    slot_window="AM",
)


# ── Tests: write_booking ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_booking_creates_pending_booking(mock_db, mock_client_config):
    """write_booking must INSERT a row with booking_status = 'pending_confirmation'."""
    from engine.core.tools.booking_tools import write_booking

    with patch("engine.core.tools.booking_tools.sync_booking_to_sheets", new=AsyncMock()):
        result = await write_booking(
            db=mock_db,
            client_config=mock_client_config,
            phone_number="+6591234567",
            **BOOKING_KWARGS,
        )

    assert result["status"] == "pending_confirmation"
    assert "booking_id" in result
    assert result["booking_id"].startswith("HA-20260510-")

    # Verify INSERT was called
    mock_db.table.assert_any_call("bookings")
    insert_call = mock_db.table.return_value.insert
    insert_call.assert_called_once()
    inserted_row = insert_call.call_args[0][0]
    assert inserted_row["booking_status"] == "pending_confirmation"


@pytest.mark.asyncio
async def test_write_booking_no_calendar_event(mock_db, mock_client_config):
    """write_booking must NOT call create_booking_event."""
    from engine.core.tools.booking_tools import write_booking

    with patch("engine.core.tools.booking_tools.sync_booking_to_sheets", new=AsyncMock()):
        with patch("engine.integrations.google_calendar.create_booking_event") as mock_calendar:
            result = await write_booking(
                db=mock_db,
                client_config=mock_client_config,
                phone_number="+6591234567",
                **BOOKING_KWARGS,
            )

    mock_calendar.assert_not_called()
    assert "calendar_event_id" not in result


@pytest.mark.asyncio
async def test_write_booking_return_value_shape(mock_db, mock_client_config):
    """write_booking return value must have required fields and correct values."""
    from engine.core.tools.booking_tools import write_booking

    with patch("engine.core.tools.booking_tools.sync_booking_to_sheets", new=AsyncMock()):
        result = await write_booking(
            db=mock_db,
            client_config=mock_client_config,
            phone_number="+6591234567",
            **BOOKING_KWARGS,
        )

    assert result["status"] == "pending_confirmation"
    assert result["slot_date"] == "2026-05-10"
    assert result["slot_window"] == "AM"
    assert result["service_type"] == "General Servicing"
    assert "message" in result
    assert "confirm_booking" in result["message"]
    assert "calendar_event_id" not in result


@pytest.mark.asyncio
async def test_write_booking_requires_address(mock_db, mock_client_config):
    """write_booking must raise ValueError if address is empty."""
    from engine.core.tools.booking_tools import write_booking

    kwargs_no_address = {**BOOKING_KWARGS, "address": ""}
    with pytest.raises(ValueError, match="address"):
        await write_booking(
            db=mock_db,
            client_config=mock_client_config,
            phone_number="+6591234567",
            **kwargs_no_address,
        )


@pytest.mark.asyncio
async def test_write_booking_no_customers_update(mock_db, mock_client_config):
    """write_booking must NOT update the customers table."""
    from engine.core.tools.booking_tools import write_booking

    with patch("engine.core.tools.booking_tools.sync_booking_to_sheets", new=AsyncMock()):
        await write_booking(
            db=mock_db,
            client_config=mock_client_config,
            phone_number="+6591234567",
            **BOOKING_KWARGS,
        )

    # Verify customers table was NOT updated
    for call in mock_db.table.call_args_list:
        assert call[0][0] != "customers", "write_booking must not write to customers table"


@pytest.mark.asyncio
async def test_write_booking_db_failure_alerts_human(mock_db, mock_client_config):
    """On DB INSERT failure, write_booking must call _alert_booking_failure and re-raise."""
    from engine.core.tools.booking_tools import write_booking

    mock_db.table.return_value.execute = AsyncMock(side_effect=RuntimeError("DB timeout"))

    with patch("engine.core.tools.booking_tools.sync_booking_to_sheets", new=AsyncMock()):
        with patch("engine.core.tools.booking_tools._alert_booking_failure", new=AsyncMock()) as mock_alert:
            with pytest.raises(RuntimeError):
                await write_booking(
                    db=mock_db,
                    client_config=mock_client_config,
                    phone_number="+6591234567",
                    **BOOKING_KWARGS,
                )

    mock_alert.assert_called_once()


# ── Tests: get_customer_bookings ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_customer_bookings_returns_empty_on_db_error(mock_db):
    """get_customer_bookings must return empty list on Supabase error, never raise."""
    from engine.core.tools.booking_tools import get_customer_bookings

    mock_db.table.return_value.execute = AsyncMock(side_effect=RuntimeError("DB down"))

    result = await get_customer_bookings(db=mock_db, phone_number="+6591234567")
    assert result["bookings"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_get_customer_bookings_upcoming_filter(mock_db):
    """get_customer_bookings with filter='upcoming' must apply gte date filter."""
    from engine.core.tools.booking_tools import get_customer_bookings

    mock_response = MagicMock()
    mock_response.data = []
    mock_db.table.return_value.execute = AsyncMock(return_value=mock_response)

    await get_customer_bookings(db=mock_db, phone_number="+6591234567", filter="upcoming")

    mock_db.table.return_value.gte.assert_called_once()
