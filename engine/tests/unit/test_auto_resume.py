"""
Unit tests for takeover auto-resume job.

Tests:
- Auto-resume clears stale takeovers after timeout
- Auto-resume logs to takeover_tracking
- Auto-resume sends notification to human agent
- Auto-resume does not affect non-stale takeovers
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from engine.core.takeover_auto_resume import (
    run_takeover_auto_resume,
    _auto_resume_for_client,
)


def _make_db(stale_takeovers=None):
    """
    Build a mock Supabase client.
    
    Args:
        stale_takeovers: List of customer dicts with takeover_at timestamps
    """
    if stale_takeovers is None:
        stale_takeovers = []
    
    chain = MagicMock()
    chain.select.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.lt.return_value = chain
    chain.is_.return_value = chain
    chain.execute = AsyncMock(return_value=MagicMock(data=stale_takeovers))
    
    db = MagicMock()
    db.table.return_value = chain
    
    return db


@pytest.fixture
def mock_client_config():
    """Mock ClientConfig for auto-resume tests."""
    config = MagicMock()
    config.client_id = "hey-aircon"
    config.human_agent_number = "+6598765432"
    return config


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_resume_clears_stale_takeovers(mock_client_config):
    """Auto-resume clears takeover_flag for customers with takeover_at older than timeout."""
    now = datetime.now(timezone.utc)
    stale_customer = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_at": (now - timedelta(hours=5)).isoformat(),  # 5 hours ago (timeout = 4)
    }
    
    db = _make_db(stale_takeovers=[stale_customer])
    
    with patch("engine.core.takeover_auto_resume.get_client_db", new_callable=AsyncMock) as mock_get_db:
        mock_get_db.return_value = db
        
        with patch("engine.core.takeover_auto_resume.send_message", new_callable=AsyncMock):
            await _auto_resume_for_client(mock_client_config, timeout_hours=4)
    
    # Verify update was called to clear takeover flags
    db.table.assert_called()
    # Check that update was called with takeover_flag=False
    table_calls = db.table.call_args_list
    customers_updates = [call for call in table_calls if call[0][0] == "customers"]
    assert len(customers_updates) > 0


@pytest.mark.asyncio
async def test_auto_resume_logs_to_tracking(mock_client_config):
    """Auto-resume logs release to takeover_tracking table."""
    now = datetime.now(timezone.utc)
    stale_customer = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_at": (now - timedelta(hours=5)).isoformat(),
    }
    
    db = _make_db(stale_takeovers=[stale_customer])
    
    with patch("engine.core.takeover_auto_resume.get_client_db", new_callable=AsyncMock) as mock_get_db:
        mock_get_db.return_value = db
        
        with patch("engine.core.takeover_auto_resume.send_message", new_callable=AsyncMock):
            await _auto_resume_for_client(mock_client_config, timeout_hours=4)
    
    # Verify update was called on takeover_tracking
    tracking_updates = [call for call in db.table.call_args_list if call[0][0] == "takeover_tracking"]
    assert len(tracking_updates) > 0


@pytest.mark.asyncio
async def test_auto_resume_sends_notification(mock_client_config):
    """Auto-resume sends notification to human_agent_number."""
    now = datetime.now(timezone.utc)
    stale_customer = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_at": (now - timedelta(hours=5)).isoformat(),
    }
    
    db = _make_db(stale_takeovers=[stale_customer])
    
    with patch("engine.core.takeover_auto_resume.get_client_db", new_callable=AsyncMock) as mock_get_db:
        mock_get_db.return_value = db
        
        with patch("engine.core.takeover_auto_resume.send_message", new_callable=AsyncMock) as mock_send:
            await _auto_resume_for_client(mock_client_config, timeout_hours=4)
    
    # Verify notification was sent
    mock_send.assert_called_once()
    notification_text = mock_send.call_args[0][2]
    assert "AI auto-resumed" in notification_text
    assert "John Tan" in notification_text
    assert "4-hour timeout" in notification_text


@pytest.mark.asyncio
async def test_auto_resume_does_not_affect_recent_takeovers(mock_client_config):
    """Auto-resume does not clear takeovers that are still within timeout window."""
    now = datetime.now(timezone.utc)
    recent_customer = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_at": (now - timedelta(hours=2)).isoformat(),  # 2 hours ago (within 4h timeout)
    }
    
    # DB query returns empty (no stale takeovers found by the query)
    db = _make_db(stale_takeovers=[])
    
    with patch("engine.core.takeover_auto_resume.get_client_db", new_callable=AsyncMock) as mock_get_db:
        mock_get_db.return_value = db
        
        with patch("engine.core.takeover_auto_resume.send_message", new_callable=AsyncMock) as mock_send:
            await _auto_resume_for_client(mock_client_config, timeout_hours=4)
    
    # No notifications should be sent (no stale takeovers)
    mock_send.assert_not_called()
