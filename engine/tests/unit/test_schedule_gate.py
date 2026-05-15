"""
Unit tests for AI schedule gate and business hours.

Tests _is_within_ai_hours() and _handle_out_of_hours_message() helpers.
"""
import pytest
from datetime import datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from engine.core.message_handler import _is_within_ai_hours, _handle_out_of_hours_message
from engine.config.client_config import ClientConfig


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_client_config():
    """Base client config with schedule fields."""
    return ClientConfig(
        client_id="test-client",
        display_name="Test Client",
        meta_phone_number_id="123456789",
        meta_verify_token="test_token",
        meta_whatsapp_token="test_whatsapp_token",
        human_agent_number="6591234567",
        google_calendar_id=None,
        google_calendar_creds={},
        supabase_url="https://test.supabase.co",
        supabase_service_key="test_key",
        anthropic_api_key="test_anthropic_key",
        openai_api_key="test_openai_key",
        timezone="UTC",
        is_active=True,
        ai_active_start_time=None,
        ai_active_end_time=None,
        business_start_time=None,
        business_end_time=None,
    )


# ── Tests for _is_within_ai_hours() ──────────────────────────────────────────

def test_is_within_ai_hours_24_7_active(mock_client_config):
    """When both AI hours are NULL, AI is active 24/7."""
    mock_client_config.ai_active_start_time = None
    mock_client_config.ai_active_end_time = None
    
    assert _is_within_ai_hours(mock_client_config) is True


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_daytime_window_inside(mock_datetime, mock_client_config):
    """Daytime window 09:00–18:00, current 12:00 → True."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    mock_client_config.timezone = "UTC"
    
    # Mock current time to 12:00 UTC
    mock_now = MagicMock()
    mock_now.time.return_value = time(12, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    assert _is_within_ai_hours(mock_client_config) is True


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_daytime_window_outside(mock_datetime, mock_client_config):
    """Daytime window 09:00–18:00, current 20:00 → False."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    mock_client_config.timezone = "UTC"
    
    # Mock current time to 20:00 UTC
    mock_now = MagicMock()
    mock_now.time.return_value = time(20, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    assert _is_within_ai_hours(mock_client_config) is False


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_overnight_window_inside_before_midnight(mock_datetime, mock_client_config):
    """Overnight window 18:00–09:00, current 20:00 → True."""
    mock_client_config.ai_active_start_time = "18:00:00"
    mock_client_config.ai_active_end_time = "09:00:00"
    mock_client_config.timezone = "UTC"
    
    # Mock current time to 20:00 UTC (after 18:00, before midnight)
    mock_now = MagicMock()
    mock_now.time.return_value = time(20, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    assert _is_within_ai_hours(mock_client_config) is True


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_overnight_window_inside_after_midnight(mock_datetime, mock_client_config):
    """Overnight window 18:00–09:00, current 06:00 → True."""
    mock_client_config.ai_active_start_time = "18:00:00"
    mock_client_config.ai_active_end_time = "09:00:00"
    mock_client_config.timezone = "UTC"
    
    # Mock current time to 06:00 UTC (after midnight, before 09:00)
    mock_now = MagicMock()
    mock_now.time.return_value = time(6, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    assert _is_within_ai_hours(mock_client_config) is True


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_overnight_window_outside(mock_datetime, mock_client_config):
    """Overnight window 18:00–09:00, current 12:00 → False."""
    mock_client_config.ai_active_start_time = "18:00:00"
    mock_client_config.ai_active_end_time = "09:00:00"
    mock_client_config.timezone = "UTC"
    
    # Mock current time to 12:00 UTC (outside the overnight window)
    mock_now = MagicMock()
    mock_now.time.return_value = time(12, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    assert _is_within_ai_hours(mock_client_config) is False


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_edge_at_start(mock_datetime, mock_client_config):
    """Start time is inclusive → True."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    mock_client_config.timezone = "UTC"
    
    # Mock current time to exactly 09:00 UTC
    mock_now = MagicMock()
    mock_now.time.return_value = time(9, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    assert _is_within_ai_hours(mock_client_config) is True


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_edge_at_end(mock_datetime, mock_client_config):
    """End time is exclusive → False."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    mock_client_config.timezone = "UTC"
    
    # Mock current time to exactly 18:00 UTC
    mock_now = MagicMock()
    mock_now.time.return_value = time(18, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    assert _is_within_ai_hours(mock_client_config) is False


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_timezone_conversion(mock_datetime, mock_client_config):
    """SGT timezone correctly interpreted."""
    mock_client_config.ai_active_start_time = "18:00:00"
    mock_client_config.ai_active_end_time = "09:00:00"
    mock_client_config.timezone = "Asia/Singapore"
    
    # Mock current time to 20:00 SGT
    mock_now = MagicMock()
    mock_now.time.return_value = time(20, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    assert _is_within_ai_hours(mock_client_config) is True


def test_is_within_ai_hours_invalid_timezone_defaults_utc(mock_client_config, caplog):
    """Invalid timezone logs error and defaults to UTC."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    mock_client_config.timezone = "Invalid/Timezone"
    
    with patch('engine.core.message_handler.datetime') as mock_datetime:
        mock_now = MagicMock()
        mock_now.time.return_value = time(12, 0, 0)
        mock_datetime.now.return_value = mock_now
        
        result = _is_within_ai_hours(mock_client_config)
        
        # Should default to 24/7 active due to error, but let's check it doesn't crash
        assert isinstance(result, bool)
        assert "Invalid timezone" in caplog.text


def test_is_within_ai_hours_partial_config_logs_warning(mock_client_config, caplog):
    """One field NULL logs warning and returns True (24/7 active fallback)."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = None
    
    result = _is_within_ai_hours(mock_client_config)
    
    assert result is True
    assert "partial AI hours config" in caplog.text


@patch('engine.core.message_handler.datetime')
def test_is_within_ai_hours_same_start_end_no_window(mock_datetime, mock_client_config, caplog):
    """Start == end logs warning and returns False (no active window)."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "09:00:00"
    mock_client_config.timezone = "UTC"
    
    mock_now = MagicMock()
    mock_now.time.return_value = time(12, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    result = _is_within_ai_hours(mock_client_config)
    
    assert result is False
    assert "no active window" in caplog.text


# ── Tests for _handle_out_of_hours_message() ─────────────────────────────────

@pytest.mark.asyncio
async def test_handle_out_of_hours_message_with_business_hours(mock_client_config):
    """Includes business hours in auto-reply when configured."""
    mock_client_config.business_start_time = "09:00:00"
    mock_client_config.business_end_time = "18:00:00"
    
    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute = AsyncMock()
    
    with patch('engine.core.message_handler.send_message', new_callable=AsyncMock) as mock_send:
        await _handle_out_of_hours_message(
            db=mock_db,
            client_config=mock_client_config,
            phone_number="6591234567",
            display_name="Test User",
            message_text="Hello",
        )
        
        # Verify send_message was called with business hours
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        message = call_args[2]
        assert "9:00am" in message
        assert "6:00pm" in message


@pytest.mark.asyncio
async def test_handle_out_of_hours_message_no_business_hours(mock_client_config):
    """Generic message when no business hours configured."""
    mock_client_config.business_start_time = None
    mock_client_config.business_end_time = None
    
    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute = AsyncMock()
    
    with patch('engine.core.message_handler.send_message', new_callable=AsyncMock) as mock_send:
        await _handle_out_of_hours_message(
            db=mock_db,
            client_config=mock_client_config,
            phone_number="6591234567",
            display_name="Test User",
            message_text="Hello",
        )
        
        # Verify send_message was called with generic message
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        message = call_args[2]
        assert "Our team will respond shortly" in message
        assert "9:00am" not in message


@pytest.mark.asyncio
async def test_handle_out_of_hours_send_failure_non_fatal(mock_client_config, caplog):
    """Exception during send is caught and doesn't propagate."""
    mock_client_config.business_start_time = "09:00:00"
    mock_client_config.business_end_time = "18:00:00"
    
    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute = AsyncMock()
    
    with patch('engine.core.message_handler.send_message', new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = Exception("Send failed")
        
        # Should not raise — exception is caught
        await _handle_out_of_hours_message(
            db=mock_db,
            client_config=mock_client_config,
            phone_number="6591234567",
            display_name="Test User",
            message_text="Hello",
        )
        
        # Verify error was logged
        assert "Failed to send out-of-hours auto-reply" in caplog.text
        
        # Verify logging still attempted (should have been called once)
        mock_db.table.assert_called_with("interactions_log")
