"""
Unit tests for Google Sheets sync integration.

All gspread calls are mocked — no real API calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from dataclasses import dataclass

from engine.integrations.google_sheets import (
    sync_customer_to_sheets,
    sync_booking_to_sheets,
    CUSTOMER_HEADERS,
    BOOKING_HEADERS,
)


@dataclass
class MockClientConfig:
    """Mock ClientConfig for testing."""
    sheets_sync_enabled: bool = True
    sheets_spreadsheet_id: str = "mock-spreadsheet-id"
    sheets_service_account_creds: dict = None
    
    def __post_init__(self):
        if self.sheets_service_account_creds is None:
            self.sheets_service_account_creds = {"type": "service_account"}


@pytest.mark.asyncio
async def test_sync_disabled_returns_immediately():
    """Test that sync returns immediately when sheets_sync_enabled=False."""
    config = MockClientConfig(sheets_sync_enabled=False)
    customer_data = {"id": "test-id", "phone_number": "1234567890"}
    
    with patch("engine.integrations.google_sheets._build_sheets_client") as mock_build:
        await sync_customer_to_sheets("test-client", config, customer_data)
        mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_no_spreadsheet_id_logs_error():
    """Test that missing spreadsheet_id logs error and returns."""
    config = MockClientConfig(sheets_spreadsheet_id=None)
    customer_data = {"id": "test-id", "phone_number": "1234567890"}
    
    with patch("engine.integrations.google_sheets.logger") as mock_logger:
        with patch("engine.integrations.google_sheets._build_sheets_client") as mock_build:
            await sync_customer_to_sheets("test-client", config, customer_data)
            mock_build.assert_not_called()
            mock_logger.error.assert_called_once()
            assert "no spreadsheet_id configured" in str(mock_logger.error.call_args)


@pytest.mark.asyncio
async def test_empty_sheet_writes_header_and_row():
    """Test that empty sheet gets header + data row."""
    config = MockClientConfig()
    customer_data = {
        "id": "uuid-1",
        "phone_number": "1234567890",
        "customer_name": "John Doe",
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-01-02T00:00:00Z",
        "total_bookings": 3,
        "escalation_flag": False,
    }
    
    mock_gc = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = []  # Empty sheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_gc.open_by_key.return_value = mock_spreadsheet
    
    with patch("engine.integrations.google_sheets._build_sheets_client", return_value=mock_gc):
        with patch("asyncio.get_event_loop") as mock_loop:
            async def run_in_executor(executor, fn, *args):
                return fn(*args) if fn else None
            mock_loop.return_value.run_in_executor = run_in_executor

            await sync_customer_to_sheets("test-client", config, customer_data)

    # Verify header row written
    assert mock_worksheet.append_row.call_count == 2
    first_call = mock_worksheet.append_row.call_args_list[0][0][0]
    assert first_call == CUSTOMER_HEADERS
    
    # Verify data row written
    second_call = mock_worksheet.append_row.call_args_list[1][0][0]
    assert second_call[0] == "uuid-1"
    assert second_call[1] == "1234567890"
    assert second_call[6] == "FALSE"


@pytest.mark.asyncio
async def test_new_row_appended():
    """Test that new row (UUID not in sheet) is appended."""
    config = MockClientConfig()
    customer_data = {
        "id": "uuid-new",
        "phone_number": "9876543210",
        "customer_name": "Jane Doe",
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-01-02T00:00:00Z",
        "total_bookings": 1,
        "escalation_flag": True,
    }
    
    mock_gc = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    # Existing rows: header + one data row with different UUID
    mock_worksheet.get_all_values.return_value = [
        CUSTOMER_HEADERS,
        ["uuid-existing", "1111111111", "Existing", "2026-01-01", "2026-01-01", "0", "FALSE"],
    ]
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_gc.open_by_key.return_value = mock_spreadsheet
    
    with patch("engine.integrations.google_sheets._build_sheets_client", return_value=mock_gc):
        with patch("asyncio.get_event_loop") as mock_loop:
            async def run_in_executor(executor, fn, *args):
                return fn(*args) if fn else None
            mock_loop.return_value.run_in_executor = run_in_executor

            await sync_customer_to_sheets("test-client", config, customer_data)

    # Verify append_row called (not update)
    mock_worksheet.append_row.assert_called_once()
    appended_row = mock_worksheet.append_row.call_args[0][0]
    assert appended_row[0] == "uuid-new"
    assert appended_row[6] == "TRUE"  # escalation_flag


@pytest.mark.asyncio
async def test_existing_row_updated():
    """Test that existing row (UUID found) is updated, not duplicated."""
    config = MockClientConfig()
    customer_data = {
        "id": "uuid-existing",
        "phone_number": "1234567890",
        "customer_name": "Updated Name",
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-01-03T00:00:00Z",
        "total_bookings": 5,
        "escalation_flag": False,
    }
    
    mock_gc = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = [
        CUSTOMER_HEADERS,
        ["uuid-existing", "1234567890", "Old Name", "2026-01-01", "2026-01-02", "3", "FALSE"],
    ]
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_gc.open_by_key.return_value = mock_spreadsheet
    
    with patch("engine.integrations.google_sheets._build_sheets_client", return_value=mock_gc):
        with patch("asyncio.get_event_loop") as mock_loop:
            async def run_in_executor(executor, fn, *args):
                return fn(*args) if fn else None
            mock_loop.return_value.run_in_executor = run_in_executor

            await sync_customer_to_sheets("test-client", config, customer_data)

    # Verify update called (not append)
    mock_worksheet.update.assert_called_once()
    update_range = mock_worksheet.update.call_args[0][0]
    assert update_range == "A2:I2"  # Row 2 (1-based, header is 1), 9 customer columns
    updated_row = mock_worksheet.update.call_args[0][1][0]
    assert updated_row[2] == "Updated Name"
    assert updated_row[4] == "2026-01-03 08:00 SGT"  # last_seen converted to SGT
    assert updated_row[5] == "5"  # total_bookings
    
    mock_worksheet.append_row.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_matches_updates_first_logs_warning():
    """Test that multiple UUID matches update first row and log WARNING."""
    config = MockClientConfig()
    customer_data = {
        "id": "uuid-duplicate",
        "phone_number": "1234567890",
        "customer_name": "Updated",
        "first_seen": "2026-01-01T00:00:00Z",
        "last_seen": "2026-01-04T00:00:00Z",
        "total_bookings": 10,
        "escalation_flag": False,
    }
    
    mock_gc = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = [
        CUSTOMER_HEADERS,
        ["uuid-duplicate", "1234567890", "First", "2026-01-01", "2026-01-02", "3", "FALSE"],
        ["uuid-duplicate", "1234567890", "Second", "2026-01-01", "2026-01-03", "5", "FALSE"],
    ]
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_gc.open_by_key.return_value = mock_spreadsheet
    
    with patch("engine.integrations.google_sheets._build_sheets_client", return_value=mock_gc):
        with patch("engine.integrations.google_sheets.logger") as mock_logger:
            with patch("asyncio.get_event_loop") as mock_loop:
                async def run_in_executor(executor, fn, *args):
                    return fn(*args) if fn else None
                mock_loop.return_value.run_in_executor = run_in_executor

                await sync_customer_to_sheets("test-client", config, customer_data)

    # Verify warning logged
    mock_logger.warning.assert_called_once()
    assert "duplicate ID" in str(mock_logger.warning.call_args)
    
    # Verify first row updated
    mock_worksheet.update.assert_called_once()
    update_range = mock_worksheet.update.call_args[0][0]
    assert update_range == "A2:I2"  # First match (row 2), 9 customer columns


@pytest.mark.asyncio
async def test_gspread_exception_logged_not_raised():
    """Test that gspread exception is logged but not re-raised."""
    config = MockClientConfig()
    customer_data = {"id": "uuid-1", "phone_number": "1234567890"}
    
    with patch("engine.integrations.google_sheets._build_sheets_client") as mock_build:
        mock_build.side_effect = Exception("API connection failed")
        
        with patch("engine.integrations.google_sheets.logger") as mock_logger:
            # Should not raise
            await sync_customer_to_sheets("test-client", config, customer_data)
            
            # Verify error logged
            mock_logger.error.assert_called_once()
            assert "Sheets sync failed" in str(mock_logger.error.call_args)


@pytest.mark.asyncio
async def test_sync_booking_to_sheets():
    """Test booking sync function (basic flow)."""
    config = MockClientConfig()
    booking_data = {
        "booking_id": "booking-uuid-1",
        "phone_number": "1234567890",
        "customer_name": "John Doe",
        "service_type": "Aircon Servicing",
        "slot_date": "2026-04-25",
        "slot_window": "AM",
        "address": "123 Main St",
        "unit_number": "05-10",
        "notes": "Call before arriving",
        "booking_status": "Confirmed",
        "created_at": "2026-04-20T00:00:00Z",
    }
    
    mock_gc = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = [
        BOOKING_HEADERS,
    ]
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_gc.open_by_key.return_value = mock_spreadsheet
    
    with patch("engine.integrations.google_sheets._build_sheets_client", return_value=mock_gc):
        with patch("asyncio.get_event_loop") as mock_loop:
            async def run_in_executor(executor, fn, *args):
                return fn(*args) if fn else None
            mock_loop.return_value.run_in_executor = run_in_executor

            await sync_booking_to_sheets("test-client", config, booking_data)

    # Verify append_row called
    mock_worksheet.append_row.assert_called_once()
    appended_row = mock_worksheet.append_row.call_args[0][0]
    assert appended_row[0] == "booking-uuid-1"
    assert appended_row[3] == "Aircon Servicing"  # service_type
    assert appended_row[6] == "2026-04-25"        # slot_date → Booking Date
    assert appended_row[7] == "AM"               # slot_window → Booking Time
    assert appended_row[11] == "Confirmed"        # booking_status → Status


@pytest.mark.asyncio
async def test_sync_booking_to_sheets_updates_existing_pending_row_by_booking_id():
    """Confirmed sync must update the pending row, not append a second row."""
    config = MockClientConfig()
    booking_data = {
        "id": 24,
        "booking_id": "HA-20260429-ABCD",
        "phone_number": "1234567890",
        "customer_name": "John Doe",
        "service_type": "Aircon Servicing",
        "unit_count": "2",
        "slot_date": "2026-04-29",
        "slot_window": "PM",
        "address": "123 Main St",
        "postal_code": "123456",
        "notes": "Call before arriving",
        "booking_status": "confirmed",
        "created_at": "2026-04-20T00:00:00Z",
    }

    mock_gc = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = [
        BOOKING_HEADERS,
        [
            "HA-20260429-ABCD",
            "1234567890",
            "John Doe",
            "Aircon Servicing",
            "2",
            "",
            "2026-04-29",
            "PM",
            "123 Main St",
            "123456",
            "",
            "pending_confirmation",
            "2026-04-20 08:00 SGT",
        ],
    ]
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_gc.open_by_key.return_value = mock_spreadsheet

    with patch("engine.integrations.google_sheets._build_sheets_client", return_value=mock_gc):
        with patch("asyncio.get_event_loop") as mock_loop:
            async def run_in_executor(executor, fn, *args):
                return fn(*args) if fn else None
            mock_loop.return_value.run_in_executor = run_in_executor

            await sync_booking_to_sheets("test-client", config, booking_data)

    mock_worksheet.update.assert_called_once()
    updated_row = mock_worksheet.update.call_args[0][1][0]
    assert updated_row[0] == "HA-20260429-ABCD"
    assert updated_row[11] == "confirmed"
    mock_worksheet.append_row.assert_not_called()


@pytest.mark.asyncio
async def test_booking_sync_handles_missing_fields():
    """Test that booking sync handles missing optional fields gracefully."""
    config = MockClientConfig()
    booking_data = {
        "booking_id": "booking-uuid-2",
        "phone_number": "9876543210",
        "slot_date": "2026-04-26",
        "slot_window": "PM",
        "booking_status": "Pending",
        # Missing: customer_name, service_type, address, unit_number, notes, created_at
    }
    
    mock_gc = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = [BOOKING_HEADERS]
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_gc.open_by_key.return_value = mock_spreadsheet
    
    with patch("engine.integrations.google_sheets._build_sheets_client", return_value=mock_gc):
        with patch("asyncio.get_event_loop") as mock_loop:
            async def run_in_executor(executor, fn, *args):
                return fn(*args) if fn else None
            mock_loop.return_value.run_in_executor = run_in_executor

            await sync_booking_to_sheets("test-client", config, booking_data)
    
    # Should not crash, should append with empty strings
    mock_worksheet.append_row.assert_called_once()
    appended_row = mock_worksheet.append_row.call_args[0][0]
    assert appended_row[0] == "booking-uuid-2"
    assert appended_row[2] == ""   # customer_name
    assert appended_row[8] == ""   # address (index 8 in 13-col schema)
    assert appended_row[9] == ""   # postal_code (index 9)
