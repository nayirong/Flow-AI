"""
Integration tests for AI schedule gate in the full message processing pipeline.

Tests full webhook → schedule gate → response flow.
"""
import pytest
from datetime import datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from engine.core.message_handler import handle_inbound_message


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_client_config():
    """Mock ClientConfig with schedule fields."""
    from engine.config.client_config import ClientConfig
    return ClientConfig(
        client_id="test-client",
        display_name="Test Client",
        meta_phone_number_id="123456789",
        meta_verify_token="test_token",
        meta_whatsapp_token="test_whatsapp_token",
        human_agent_number="6591111111",
        google_calendar_id=None,
        google_calendar_creds={},
        supabase_url="https://test.supabase.co",
        supabase_service_key="test_key",
        anthropic_api_key="test_anthropic_key",
        openai_api_key="test_openai_key",
        timezone="UTC",
        is_active=True,
        ai_active_start_time="09:00:00",
        ai_active_end_time="18:00:00",
        business_start_time="09:00:00",
        business_end_time="18:00:00",
    )


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    db = MagicMock()
    
    # Mock table().select().eq().limit().execute() chain for customers query
    customers_result = MagicMock()
    customers_result.data = []
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(return_value=customers_result)
    
    # Mock table().insert().execute() for interactions_log
    db.table.return_value.insert.return_value.execute = AsyncMock()
    
    # Mock table().upsert().execute() for customers upsert
    upsert_result = MagicMock()
    upsert_result.data = [{"phone_number": "6591234567", "customer_name": "Test User"}]
    db.table.return_value.upsert.return_value.execute = AsyncMock(return_value=upsert_result)
    
    # Mock table().update().eq().execute() for customers update
    db.table.return_value.update.return_value.eq.return_value.execute = AsyncMock()
    
    return db


# ── Integration tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch('engine.core.message_handler.load_client_config')
@patch('engine.core.message_handler.get_client_db')
@patch('engine.core.message_handler.send_message')
@patch('engine.core.message_handler.datetime')
async def test_out_of_hours_message_sends_auto_reply_stops_pipeline(
    mock_datetime, mock_send, mock_get_db, mock_load_config, mock_client_config, mock_db
):
    """Outside AI hours → auto-reply sent, agent NOT run."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    
    mock_load_config.return_value = mock_client_config
    mock_get_db.return_value = mock_db
    mock_send.return_value = AsyncMock()
    
    # Mock current time to 20:00 UTC (outside 09:00–18:00)
    mock_now = MagicMock()
    mock_now.time.return_value = time(20, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    with patch('engine.core.message_handler.run_agent') as mock_agent:
        await handle_inbound_message(
            client_id="test-client",
            phone_number="6591234567",
            message_text="Hello",
            message_type="text",
            message_id="wamid.test",
            display_name="Test User",
        )
        
        # Verify auto-reply was sent
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "Thanks for reaching out" in call_args[2]
        
        # Verify agent was NOT run
        mock_agent.assert_not_called()


@pytest.mark.asyncio
@patch('engine.core.message_handler.load_client_config')
@patch('engine.core.message_handler.get_client_db')
@patch('engine.core.message_handler.send_message')
@patch('engine.core.message_handler.datetime')
@patch('engine.core.message_handler.run_agent')
@patch('engine.core.message_handler.build_system_message')
@patch('engine.core.message_handler.fetch_conversation_history')
@patch('engine.core.message_handler.fetch_lead_days')
@patch('engine.core.message_handler.fetch_appointment_windows')
async def test_within_hours_message_runs_agent_normally(
    mock_windows, mock_lead, mock_history, mock_system, mock_agent, mock_datetime,
    mock_send, mock_get_db, mock_load_config, mock_client_config, mock_db
):
    """Within AI hours → agent runs, no auto-reply."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    
    mock_load_config.return_value = mock_client_config
    mock_get_db.return_value = mock_db
    mock_send.return_value = AsyncMock()
    
    # Mock current time to 12:00 UTC (within 09:00–18:00)
    mock_now = MagicMock()
    mock_now.time.return_value = time(12, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    # Mock agent dependencies
    mock_system.return_value = "System message"
    mock_history.return_value = []
    mock_lead.return_value = {"standard": 1}
    mock_windows.return_value = []
    mock_agent.return_value = "Agent reply"
    
    await handle_inbound_message(
        client_id="test-client",
        phone_number="6591234567",
        message_text="Hello",
        message_type="text",
        message_id="wamid.test",
        display_name="Test User",
    )
    
    # Verify agent was run
    mock_agent.assert_called_once()
    
    # Verify agent reply was sent (not auto-reply)
    assert mock_send.call_count == 1
    call_args = mock_send.call_args[0]
    assert call_args[2] == "Agent reply"


@pytest.mark.asyncio
@patch('engine.core.message_handler.load_client_config')
@patch('engine.core.message_handler.get_client_db')
@patch('engine.core.message_handler.send_message')
@patch('engine.core.message_handler.run_agent')
@patch('engine.core.message_handler.build_system_message')
@patch('engine.core.message_handler.fetch_conversation_history')
@patch('engine.core.message_handler.fetch_lead_days')
@patch('engine.core.message_handler.fetch_appointment_windows')
async def test_24_7_active_no_gate_interference(
    mock_windows, mock_lead, mock_history, mock_system, mock_agent,
    mock_send, mock_get_db, mock_load_config, mock_client_config, mock_db
):
    """NULL AI hours → agent always runs regardless of time."""
    mock_client_config.ai_active_start_time = None
    mock_client_config.ai_active_end_time = None
    
    mock_load_config.return_value = mock_client_config
    mock_get_db.return_value = mock_db
    mock_send.return_value = AsyncMock()
    
    # Mock agent dependencies
    mock_system.return_value = "System message"
    mock_history.return_value = []
    mock_lead.return_value = {"standard": 1}
    mock_windows.return_value = []
    mock_agent.return_value = "Agent reply"
    
    await handle_inbound_message(
        client_id="test-client",
        phone_number="6591234567",
        message_text="Hello",
        message_type="text",
        message_id="wamid.test",
        display_name="Test User",
    )
    
    # Verify agent was run (no schedule gate interference)
    mock_agent.assert_called_once()


@pytest.mark.asyncio
@patch('engine.core.message_handler.load_client_config')
@patch('engine.core.message_handler.get_client_db')
@patch('engine.core.message_handler.send_message')
@patch('engine.core.message_handler.datetime')
@patch('engine.core.message_handler.run_agent')
@patch('engine.core.message_handler.build_system_message')
@patch('engine.core.message_handler.fetch_conversation_history')
@patch('engine.core.message_handler.fetch_lead_days')
@patch('engine.core.message_handler.fetch_appointment_windows')
async def test_overnight_window_before_midnight(
    mock_windows, mock_lead, mock_history, mock_system, mock_agent, mock_datetime,
    mock_send, mock_get_db, mock_load_config, mock_client_config, mock_db
):
    """Overnight window 18:00–09:00, current 20:00 → agent runs."""
    mock_client_config.ai_active_start_time = "18:00:00"
    mock_client_config.ai_active_end_time = "09:00:00"
    
    mock_load_config.return_value = mock_client_config
    mock_get_db.return_value = mock_db
    mock_send.return_value = AsyncMock()
    
    # Mock current time to 20:00 UTC (after 18:00, before midnight)
    mock_now = MagicMock()
    mock_now.time.return_value = time(20, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    # Mock agent dependencies
    mock_system.return_value = "System message"
    mock_history.return_value = []
    mock_lead.return_value = {"standard": 1}
    mock_windows.return_value = []
    mock_agent.return_value = "Agent reply"
    
    await handle_inbound_message(
        client_id="test-client",
        phone_number="6591234567",
        message_text="Hello",
        message_type="text",
        message_id="wamid.test",
        display_name="Test User",
    )
    
    # Verify agent was run (within overnight window)
    mock_agent.assert_called_once()


@pytest.mark.asyncio
@patch('engine.core.message_handler.load_client_config')
@patch('engine.core.message_handler.get_client_db')
@patch('engine.core.message_handler.send_message')
@patch('engine.core.message_handler.datetime')
@patch('engine.core.message_handler.run_agent')
@patch('engine.core.message_handler.build_system_message')
@patch('engine.core.message_handler.fetch_conversation_history')
@patch('engine.core.message_handler.fetch_lead_days')
@patch('engine.core.message_handler.fetch_appointment_windows')
async def test_overnight_window_after_midnight(
    mock_windows, mock_lead, mock_history, mock_system, mock_agent, mock_datetime,
    mock_send, mock_get_db, mock_load_config, mock_client_config, mock_db
):
    """Overnight window 18:00–09:00, current 03:00 → agent runs."""
    mock_client_config.ai_active_start_time = "18:00:00"
    mock_client_config.ai_active_end_time = "09:00:00"
    
    mock_load_config.return_value = mock_client_config
    mock_get_db.return_value = mock_db
    mock_send.return_value = AsyncMock()
    
    # Mock current time to 03:00 UTC (after midnight, before 09:00)
    mock_now = MagicMock()
    mock_now.time.return_value = time(3, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    # Mock agent dependencies
    mock_system.return_value = "System message"
    mock_history.return_value = []
    mock_lead.return_value = {"standard": 1}
    mock_windows.return_value = []
    mock_agent.return_value = "Agent reply"
    
    await handle_inbound_message(
        client_id="test-client",
        phone_number="6591234567",
        message_text="Hello",
        message_type="text",
        message_id="wamid.test",
        display_name="Test User",
    )
    
    # Verify agent was run (within overnight window)
    mock_agent.assert_called_once()


@pytest.mark.asyncio
@patch('engine.core.message_handler.load_client_config')
@patch('engine.core.message_handler.get_client_db')
@patch('engine.core.message_handler.send_message')
@patch('engine.core.message_handler.datetime')
async def test_overnight_window_outside_midday(
    mock_datetime, mock_send, mock_get_db, mock_load_config, mock_client_config, mock_db
):
    """Overnight window 18:00–09:00, current 12:00 → auto-reply sent."""
    mock_client_config.ai_active_start_time = "18:00:00"
    mock_client_config.ai_active_end_time = "09:00:00"
    
    mock_load_config.return_value = mock_client_config
    mock_get_db.return_value = mock_db
    mock_send.return_value = AsyncMock()
    
    # Mock current time to 12:00 UTC (outside overnight window)
    mock_now = MagicMock()
    mock_now.time.return_value = time(12, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    with patch('engine.core.message_handler.run_agent') as mock_agent:
        await handle_inbound_message(
            client_id="test-client",
            phone_number="6591234567",
            message_text="Hello",
            message_type="text",
            message_id="wamid.test",
            display_name="Test User",
        )
        
        # Verify auto-reply was sent
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "Thanks for reaching out" in call_args[2]
        
        # Verify agent was NOT run
        mock_agent.assert_not_called()


@pytest.mark.asyncio
@patch('engine.core.message_handler.load_client_config')
@patch('engine.core.message_handler.get_client_db')
@patch('engine.core.message_handler.send_message')
@patch('engine.core.message_handler.datetime')
async def test_schedule_gate_runs_after_escalation_gate(
    mock_datetime, mock_send, mock_get_db, mock_load_config, mock_client_config, mock_db
):
    """Escalated customer within AI hours → escalation gate fires first, not schedule gate."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    
    mock_load_config.return_value = mock_client_config
    
    # Mock escalated customer
    customers_result = MagicMock()
    customers_result.data = [{
        "phone_number": "6591234567",
        "escalation_flag": True,
        "escalation_notified": False,
    }]
    mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(return_value=customers_result)
    mock_get_db.return_value = mock_db
    mock_send.return_value = AsyncMock()
    
    # Mock current time to 12:00 UTC (within AI hours)
    mock_now = MagicMock()
    mock_now.time.return_value = time(12, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    with patch('engine.core.message_handler.run_agent') as mock_agent:
        await handle_inbound_message(
            client_id="test-client",
            phone_number="6591234567",
            message_text="Hello",
            message_type="text",
            message_id="wamid.test",
            display_name="Test User",
        )
        
        # Verify escalation holding reply was sent (not out-of-hours auto-reply)
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "member of our team will get back to you" in call_args[2]
        
        # Verify agent was NOT run (escalation takes priority)
        mock_agent.assert_not_called()


@pytest.mark.asyncio
@patch('engine.core.message_handler.load_client_config')
@patch('engine.core.message_handler.get_client_db')
@patch('engine.core.message_handler.send_message')
@patch('engine.core.message_handler.datetime')
async def test_escalated_customer_outside_ai_hours(
    mock_datetime, mock_send, mock_get_db, mock_load_config, mock_client_config, mock_db
):
    """Escalated customer outside hours → escalation gate fires, not schedule gate."""
    mock_client_config.ai_active_start_time = "09:00:00"
    mock_client_config.ai_active_end_time = "18:00:00"
    
    mock_load_config.return_value = mock_client_config
    
    # Mock escalated customer
    customers_result = MagicMock()
    customers_result.data = [{
        "phone_number": "6591234567",
        "escalation_flag": True,
        "escalation_notified": False,
    }]
    mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(return_value=customers_result)
    mock_get_db.return_value = mock_db
    mock_send.return_value = AsyncMock()
    
    # Mock current time to 20:00 UTC (outside AI hours)
    mock_now = MagicMock()
    mock_now.time.return_value = time(20, 0, 0)
    mock_datetime.now.return_value = mock_now
    
    with patch('engine.core.message_handler.run_agent') as mock_agent:
        await handle_inbound_message(
            client_id="test-client",
            phone_number="6591234567",
            message_text="Hello",
            message_type="text",
            message_id="wamid.test",
            display_name="Test User",
        )
        
        # Verify escalation holding reply was sent (not out-of-hours auto-reply)
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "member of our team will get back to you" in call_args[2]
        
        # Verify agent was NOT run
        mock_agent.assert_not_called()
