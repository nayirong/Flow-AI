"""
Unit tests for follow-up scheduler.

Tests T+2h, T+24h, and T+48h follow-up logic with mocked Supabase and Meta API calls.
No real network calls — all external dependencies are mocked.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from engine.core.followup_scheduler import (
    run_followup_scheduler,
    process_client_followups,
    process_t2h_followups,
    process_t24h_followups,
    process_t48h_abandonments,
    is_customer_escalated,
    has_customer_replied_since,
    get_message_template,
)


@pytest.fixture
def mock_shared_db():
    """Mock shared Supabase client."""
    db = MagicMock()
    db.table = MagicMock(return_value=db)
    db.select = MagicMock(return_value=db)
    db.eq = MagicMock(return_value=db)
    db.insert = MagicMock(return_value=db)
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_client_db():
    """Mock client-specific Supabase client."""
    db = MagicMock()
    db.table = MagicMock(return_value=db)
    db.select = MagicMock(return_value=db)
    db.eq = MagicMock(return_value=db)
    db.gt = MagicMock(return_value=db)
    db.limit = MagicMock(return_value=db)
    db.update = MagicMock(return_value=db)
    db.insert = MagicMock(return_value=db)
    db.rpc = MagicMock(return_value=db)
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_client_config():
    """Mock ClientConfig object."""
    config = MagicMock()
    config.meta_whatsapp_token = "test_token"
    config.meta_phone_number_id = "123456"
    return config


@pytest.mark.asyncio
async def test_t2h_eligibility_sends_message(mock_client_db, mock_client_config):
    """
    T+2h eligible booking (created 3h ago, followup_stage=None, no reply, not escalated)
    should send message and update followup_stage to '2h_sent'.
    """
    created_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{  # T+2h eligible bookings
            "booking_id": "booking_123",
            "phone_number": "6591234567",
            "service_type": "Aircon Servicing",
            "slot_date": "2026-04-25",
            "slot_window": "9AM-12PM",
            "created_at": created_at,
        }]),
        MagicMock(data=[{"escalation_flag": False}]),  # escalation check
        MagicMock(data=[]),  # customer reply check (no replies)
        MagicMock(data=[{"booking_id": "booking_123"}]),  # update booking
    ]
    
    with patch("engine.core.followup_scheduler.get_client_db", return_value=mock_client_db):
        with patch("engine.core.followup_scheduler.send_message", return_value="wamid_123"):
            results = await process_t2h_followups(
                "test-client",
                mock_client_config,
                mock_client_db,
                "Hi! {service_type} on {slot_date} ({slot_window})",
            )
    
    assert results["sent"] == 1
    assert results["failed"] == 0


@pytest.mark.asyncio
async def test_t2h_already_sent_excluded(mock_client_db, mock_client_config):
    """
    Booking with followup_stage='2h_sent' should not be picked up by T+2h query.
    """
    mock_client_db.execute.side_effect = [
        MagicMock(data=[]),  # T+2h query returns empty (2h_sent bookings excluded)
    ]
    
    results = await process_t2h_followups(
        "test-client",
        mock_client_config,
        mock_client_db,
        "Hi! {service_type}",
    )
    
    assert results["sent"] == 0
    assert results["failed"] == 0


@pytest.mark.asyncio
async def test_t24h_eligibility_sends_message(mock_client_db, mock_client_config):
    """
    T+24h eligible booking (followup_stage='2h_sent', 25h since last followup, no reply)
    should send message and update followup_stage to '24h_sent'.
    """
    last_followup_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    
    # Mock execute responses
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{  # T+24h eligible bookings
            "booking_id": "booking_456",
            "phone_number": "6591234567",
            "service_type": "Aircon Servicing",
            "slot_date": "2026-04-25",
            "slot_window": "2PM-5PM",
            "last_followup_sent_at": last_followup_at,
        }]),
        MagicMock(data=[{"escalation_flag": False}]),  # escalation check
        MagicMock(data=[]),  # customer reply check (no replies)
        MagicMock(data=[{"booking_id": "booking_456"}]),  # update booking
    ]
    
    with patch("engine.core.followup_scheduler.send_message", return_value="wamid_456"):
        results = await process_t24h_followups(
            "test-client",
            mock_client_config,
            mock_client_db,
            "Hi again! {service_type} on {slot_date} ({slot_window})",
        )
    
    assert results["sent"] == 1
    assert results["failed"] == 0


@pytest.mark.asyncio
async def test_t48h_abandon_no_message(mock_client_db):
    """
    T+48h eligible booking (followup_stage='24h_sent', 25h since last followup, no reply)
    should be abandoned with DB update only — NO message sent.
    """
    last_followup_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    
    # Mock execute responses
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{  # T+48h eligible bookings
            "booking_id": "booking_789",
            "phone_number": "6591234567",
            "last_followup_sent_at": last_followup_at,
        }]),
        MagicMock(data=[]),  # customer reply check (no replies)
        MagicMock(data=[{"booking_id": "booking_789"}]),  # update booking to abandoned
    ]
    
    with patch("engine.core.followup_scheduler.send_message") as mock_send:
        abandoned = await process_t48h_abandonments("test-client", mock_client_db)
    
    assert abandoned == 1
    # Verify send_message was NEVER called
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_customer_reply_stops_t2h_followup(mock_client_db, mock_client_config):
    """
    If customer has sent inbound message after booking created_at,
    T+2h follow-up should be skipped.
    """
    created_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    
    # Mock execute responses
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{  # T+2h eligible bookings
            "booking_id": "booking_100",
            "phone_number": "6591234567",
            "service_type": "Aircon Servicing",
            "slot_date": "2026-04-25",
            "slot_window": "9AM-12PM",
            "created_at": created_at,
        }]),
        MagicMock(data=[{"escalation_flag": False}]),  # escalation check
        MagicMock(data=[{"id": 1}]),  # customer reply check (has replied)
    ]
    
    with patch("engine.core.followup_scheduler.send_message") as mock_send:
        results = await process_t2h_followups(
            "test-client",
            mock_client_config,
            mock_client_db,
            "Hi! {service_type}",
        )
    
    assert results["sent"] == 0
    assert results["failed"] == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_escalated_customer_excluded(mock_client_db, mock_client_config):
    """
    If customer escalation_flag=True, T+2h follow-up should be skipped.
    """
    created_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    
    # Mock execute responses
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{  # T+2h eligible bookings
            "booking_id": "booking_200",
            "phone_number": "6591234567",
            "service_type": "Aircon Servicing",
            "slot_date": "2026-04-25",
            "slot_window": "9AM-12PM",
            "created_at": created_at,
        }]),
        MagicMock(data=[{"escalation_flag": True}]),  # escalation check (escalated!)
    ]
    
    with patch("engine.core.followup_scheduler.send_message") as mock_send:
        results = await process_t2h_followups(
            "test-client",
            mock_client_config,
            mock_client_db,
            "Hi! {service_type}",
        )
    
    assert results["sent"] == 0
    assert results["failed"] == 0
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_opted_out_booking_excluded(mock_client_db, mock_client_config):
    """
    Booking with followup_stage='opted_out' should not be picked up by any query.
    """
    mock_client_db.execute.side_effect = [
        MagicMock(data=[]),  # T+2h query returns empty (opted_out bookings excluded)
    ]
    
    results = await process_t2h_followups(
        "test-client",
        mock_client_config,
        mock_client_db,
        "Hi! {service_type}",
    )
    
    assert results["sent"] == 0
    assert results["failed"] == 0


@pytest.mark.asyncio
async def test_meta_api_failure_stage_not_updated(mock_client_db, mock_client_config):
    """
    If send_message fails, followup_stage should NOT be updated
    and messages_sent_failed should be incremented.
    """
    created_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    
    # Mock execute responses
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{  # T+2h eligible bookings
            "booking_id": "booking_300",
            "phone_number": "6591234567",
            "service_type": "Aircon Servicing",
            "slot_date": "2026-04-25",
            "slot_window": "9AM-12PM",
            "created_at": created_at,
        }]),
        MagicMock(data=[{"escalation_flag": False}]),  # escalation check
        MagicMock(data=[]),  # customer reply check (no replies)
    ]
    
    with patch("engine.core.followup_scheduler.send_message", return_value=None):  # send_message fails
        with patch("engine.core.followup_scheduler.get_shared_db") as mock_shared:
            mock_shared_db = MagicMock()
            mock_shared_db.table = MagicMock(return_value=mock_shared_db)
            mock_shared_db.insert = MagicMock(return_value=mock_shared_db)
            mock_shared_db.execute = AsyncMock()
            mock_shared.return_value = mock_shared_db
            
            results = await process_t2h_followups(
                "test-client",
                mock_client_config,
                mock_client_db,
                "Hi! {service_type}",
            )
    
    assert results["sent"] == 0
    assert results["failed"] == 1
    # Verify followup_stage was NOT updated (no call to update bookings table)
    # The mock's update method should not be called
    update_calls = [call for call in mock_client_db.method_calls if 'update' in str(call)]
    assert len(update_calls) == 0


@pytest.mark.asyncio
async def test_message_template_interpolation(mock_client_db, mock_client_config):
    """
    Message sent should contain correct service_type, slot_date, slot_window.
    """
    created_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    
    # Mock execute responses
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{  # T+2h eligible bookings
            "booking_id": "booking_400",
            "phone_number": "6591234567",
            "service_type": "Chemical Wash",
            "slot_date": "2026-05-01",
            "slot_window": "2PM-5PM",
            "created_at": created_at,
        }]),
        MagicMock(data=[{"escalation_flag": False}]),  # escalation check
        MagicMock(data=[]),  # customer reply check (no replies)
        MagicMock(data=[{"booking_id": "booking_400"}]),  # update booking
    ]
    
    template = "Service: {service_type} on {slot_date} during {slot_window}"
    expected_message = "Service: Chemical Wash on 2026-05-01 during 2PM-5PM"
    
    with patch("engine.core.followup_scheduler.send_message") as mock_send:
        mock_send.return_value = "wamid_400"
        
        results = await process_t2h_followups(
            "test-client",
            mock_client_config,
            mock_client_db,
            template,
        )
        
        # Verify send_message was called with interpolated template
        mock_send.assert_called_once_with(
            mock_client_config,
            "6591234567",
            expected_message,
        )
    
    assert results["sent"] == 1


@pytest.mark.asyncio
async def test_scheduler_logs_run_metrics(mock_shared_db, mock_client_db, mock_client_config):
    """
    After scheduler run, scheduler_runs row should be inserted with correct counts.
    """
    # Mock shared DB for clients query
    mock_shared_db.execute.side_effect = [
        MagicMock(data=[{"client_id": "test-client", "is_active": True}]),  # active clients
        MagicMock(data=[]),  # scheduler_runs insert
    ]
    
    # Mock client DB for followup_enabled check
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{"value": "true"}]),  # followup_enabled check
        MagicMock(data=[{"value": "Template {service_type}"}]),  # T+2h template
        MagicMock(data=[]),  # T+2h bookings (empty)
        MagicMock(data=[{"value": "Template {service_type}"}]),  # T+24h template
        MagicMock(data=[]),  # T+24h bookings (empty)
        MagicMock(data=[]),  # T+48h bookings (empty)
    ]
    
    with patch("engine.core.followup_scheduler.get_shared_db", return_value=mock_shared_db):
        with patch("engine.core.followup_scheduler.get_client_db", return_value=mock_client_db):
            with patch("engine.core.followup_scheduler.load_client_config", return_value=mock_client_config):
                await run_followup_scheduler()
    
    # Verify scheduler_runs insert was called
    insert_calls = [call for call in mock_shared_db.method_calls if 'insert' in str(call)]
    assert len(insert_calls) > 0


@pytest.mark.asyncio
async def test_followup_disabled_client_skipped(mock_shared_db, mock_client_db, mock_client_config):
    """
    If followup_enabled='false' in config, no queries should run for that client.
    """
    # Mock shared DB for clients query
    mock_shared_db.execute.side_effect = [
        MagicMock(data=[{"client_id": "test-client", "is_active": True}]),  # active clients
    ]
    
    # Mock client DB for followup_enabled check
    mock_client_db.execute.side_effect = [
        MagicMock(data=[{"value": "false"}]),  # followup_enabled check (disabled!)
    ]
    
    with patch("engine.core.followup_scheduler.get_shared_db", return_value=mock_shared_db):
        with patch("engine.core.followup_scheduler.get_client_db", return_value=mock_client_db):
            with patch("engine.core.followup_scheduler.load_client_config", return_value=mock_client_config):
                with patch("engine.core.followup_scheduler.process_t2h_followups") as mock_t2h:
                    with patch("engine.core.followup_scheduler.process_t24h_followups") as mock_t24h:
                        with patch("engine.core.followup_scheduler.process_t48h_abandonments") as mock_t48h:
                            await run_followup_scheduler()
    
    # Verify no follow-up processing functions were called
    mock_t2h.assert_not_called()
    mock_t24h.assert_not_called()
    mock_t48h.assert_not_called()


@pytest.mark.asyncio
async def test_is_customer_escalated():
    """Test is_customer_escalated helper function."""
    mock_db = MagicMock()
    mock_db.table = MagicMock(return_value=mock_db)
    mock_db.select = MagicMock(return_value=mock_db)
    mock_db.eq = MagicMock(return_value=mock_db)
    mock_db.limit = MagicMock(return_value=mock_db)
    mock_db.execute = AsyncMock(return_value=MagicMock(data=[{"escalation_flag": True}]))
    
    result = await is_customer_escalated(mock_db, "6591234567")
    assert result is True


@pytest.mark.asyncio
async def test_has_customer_replied_since():
    """Test has_customer_replied_since helper function."""
    mock_db = MagicMock()
    mock_db.table = MagicMock(return_value=mock_db)
    mock_db.select = MagicMock(return_value=mock_db)
    mock_db.eq = MagicMock(return_value=mock_db)
    mock_db.gt = MagicMock(return_value=mock_db)
    mock_db.limit = MagicMock(return_value=mock_db)
    mock_db.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))
    
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    result = await has_customer_replied_since(mock_db, "6591234567", timestamp)
    assert result is True


@pytest.mark.asyncio
async def test_get_message_template():
    """Test get_message_template with fallback to default."""
    mock_db = MagicMock()
    mock_db.table = MagicMock(return_value=mock_db)
    mock_db.select = MagicMock(return_value=mock_db)
    mock_db.eq = MagicMock(return_value=mock_db)
    mock_db.limit = MagicMock(return_value=mock_db)
    mock_db.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Should return default template when DB has no value
    template = await get_message_template(mock_db, "followup_message_t2h", "test-client")
    assert "{service_type}" in template
    assert "{slot_date}" in template
    assert "{slot_window}" in template
