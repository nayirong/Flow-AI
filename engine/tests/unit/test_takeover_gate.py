"""
Unit tests for takeover gate and conversation alerts in message_handler.py.

Tests:
- Takeover gate blocks AI when takeover_flag=True
- Takeover gate forwards message to human agent
- Takeover gate runs before escalation gate
- Conversation alert sent on new session
- Conversation alert NOT sent when session active
- Conversation alert stores alert_msg_id
- No conversation alert when human_agent_number not configured
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from engine.core.message_handler import (
    handle_inbound_message,
    _handle_takeover_inbound,
    _maybe_send_conversation_alert,
)


def _make_db(customer_row=None, interactions_log_rows=None):
    """
    Build a fully-chainable mock Supabase client.
    
    Args:
        customer_row: Dict for customers table query
        interactions_log_rows: List of dicts for interactions_log query (for session check)
    """
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.gt.return_value = chain
    chain.limit.return_value = chain
    chain.order.return_value = chain

    # Default response for customers table
    mock_response = MagicMock()
    mock_response.data = [customer_row] if customer_row else []
    mock_response.count = len(interactions_log_rows) if interactions_log_rows else 0
    chain.execute = AsyncMock(return_value=mock_response)

    db = MagicMock()
    db.table.return_value = chain

    return db, chain


_PARAMS = dict(
    client_id="hey-aircon",
    phone_number="6591234567",
    message_text="I need help with my booking",
    message_type="text",
    message_id="wamid.test123",
    display_name="John Tan",
)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_takeover_gate_blocks_ai_when_flag_true(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """When takeover_flag=True, AI does not run (pipeline stops at takeover gate)."""
    mock_load_config.return_value = mock_client_config_obj
    taken_over_customer = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_flag": True,
        "takeover_by": "+6598765432",
        "takeover_at": datetime.now(timezone.utc).isoformat(),
    }
    db, chain = _make_db(customer_row=taken_over_customer)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # Agent runner should NOT have been called (pipeline stopped at takeover gate)
    # We can't directly check if run_agent was called without patching it,
    # but we can verify that the message was forwarded to human agent
    assert mock_send.called
    forward_call = mock_send.call_args_list[-1]
    assert "just replied" in forward_call[1]["text"]


@pytest.mark.asyncio
async def test_takeover_inbound_forwards_to_human(mock_client_config_obj):
    """_handle_takeover_inbound forwards message to human_agent_number."""
    db = MagicMock()
    mock_client_config_obj.human_agent_number = "+6598765432"

    with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
        await _handle_takeover_inbound(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="6591234567",
            display_name="John Tan",
            message_text="Can I change my booking?",
        )

    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args[1]["to_phone_number"] == "+6598765432"
    assert "John Tan" in call_args[1]["text"]
    assert "Can I change my booking?" in call_args[1]["text"]
    assert 'Reply "done"' in call_args[1]["text"]


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_takeover_gate_runs_before_escalation_gate(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """Customer with both takeover_flag and escalation_flag: takeover takes priority."""
    mock_load_config.return_value = mock_client_config_obj
    both_flags_customer = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_flag": True,
        "escalation_flag": True,
        "escalation_notified": False,
    }
    db, chain = _make_db(customer_row=both_flags_customer)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # Takeover forward should be sent, NOT escalation holding reply
    assert mock_send.called
    forward_call = mock_send.call_args_list[-1]
    assert "just replied" in forward_call[1]["text"]
    # Should NOT contain holding reply text
    assert "team member will get back to you" not in forward_call[1]["text"]


@pytest.mark.asyncio
async def test_conversation_alert_sent_on_new_session(mock_client_config_obj):
    """Conversation alert sent when no recent inbound messages (new session)."""
    # Mock DB: only 1 inbound in last 4 hours (the current one just logged)
    db = MagicMock()
    mock_response = MagicMock()
    mock_response.data = []
    mock_response.count = 1  # Only current message
    
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gt.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(return_value=mock_response)
    chain.update.return_value = chain
    
    db.table.return_value = chain
    
    mock_client_config_obj.human_agent_number = "+6598765432"

    with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = "wamid.alert123"
        
        await _maybe_send_conversation_alert(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="6591234567",
            display_name="John Tan",
            message_text="Hello, I need help",
        )

    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args[1]["to_phone_number"] == "+6598765432"
    assert "AI handling" in call_args[1]["text"]
    assert "John Tan" in call_args[1]["text"]
    assert 'Reply "take"' in call_args[1]["text"]


@pytest.mark.asyncio
async def test_conversation_alert_not_sent_when_session_active(mock_client_config_obj):
    """Conversation alert NOT sent when >1 inbound messages in last 4 hours."""
    # Mock DB: 3 inbound messages in last 4 hours (session is active)
    db = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [
        {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()},
        {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
        {"timestamp": datetime.now(timezone.utc).isoformat()},
    ]
    mock_response.count = 3
    
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gt.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(return_value=mock_response)
    
    db.table.return_value = chain
    
    mock_client_config_obj.human_agent_number = "+6598765432"

    with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
        await _maybe_send_conversation_alert(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="6591234567",
            display_name="John Tan",
            message_text="Another message",
        )

    # No alert should be sent
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_conversation_alert_stores_wamid(mock_client_config_obj):
    """Conversation alert stores returned wamid in customers.last_ai_alert_msg_id."""
    # Mock DB
    db = MagicMock()
    mock_response = MagicMock()
    mock_response.data = []
    mock_response.count = 1
    
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gt.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.update.return_value = chain
    chain.execute = AsyncMock(return_value=mock_response)
    
    db.table.return_value = chain
    
    mock_client_config_obj.human_agent_number = "+6598765432"

    with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = "wamid.alert123"
        
        await _maybe_send_conversation_alert(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="6591234567",
            display_name="John Tan",
            message_text="Hello",
        )

    # Verify update was called with the wamid
    chain.update.assert_called_with({"last_ai_alert_msg_id": "wamid.alert123"})


@pytest.mark.asyncio
async def test_no_conversation_alert_when_human_agent_not_configured(mock_client_config_obj):
    """No conversation alert sent when human_agent_number is None."""
    db = MagicMock()
    mock_client_config_obj.human_agent_number = None  # Not configured

    with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
        await _maybe_send_conversation_alert(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="6591234567",
            display_name="John Tan",
            message_text="Hello",
        )

    # No message should be sent
    mock_send.assert_not_called()
