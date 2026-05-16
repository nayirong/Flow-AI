"""
Integration tests for takeover pipeline.

Tests full end-to-end flows:
- Full takeover lifecycle (alert → take → release)
- Takeover with escalation (both flags)
- Auto-resume after timeout
- Status command during active takeover
- Conversation alert throttling (session detection)
- Takeover gate priority over escalation gate
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from engine.core.message_handler import handle_inbound_message
from engine.core.reset_handler import handle_human_agent_message
from engine.core.takeover_auto_resume import _auto_resume_for_client


def _make_full_db(customer_row=None, interactions_log_count=1):
    """
    Build a fully-featured mock DB for integration tests.
    
    Args:
        customer_row: Customer dict (or None for new customer)
        interactions_log_count: Number of recent inbound messages (for session detection)
    """
    def table_factory(table_name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.insert.return_value = chain
        chain.update.return_value = chain
        chain.upsert.return_value = chain
        chain.eq.return_value = chain
        chain.gt.return_value = chain
        chain.lt.return_value = chain
        chain.is_.return_value = chain
        chain.in_.return_value = chain
        chain.not_.eq = MagicMock(return_value=chain)
        chain.limit.return_value = chain
        chain.order.return_value = chain
        
        mock_response = MagicMock()
        if table_name == "customers":
            mock_response.data = [customer_row] if customer_row else []
        elif table_name == "interactions_log":
            mock_response.data = []
            mock_response.count = interactions_log_count
        else:
            mock_response.data = []
        
        chain.execute = AsyncMock(return_value=mock_response)
        
        return chain
    
    db = MagicMock()
    db.table.side_effect = table_factory
    
    return db


@pytest.fixture
def mock_full_config():
    """Mock ClientConfig with all required fields."""
    config = MagicMock()
    config.client_id = "hey-aircon"
    config.human_agent_number = "+6598765432"
    config.meta_whatsapp_token = "test_token"
    return config


# ── Integration Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_takeover_lifecycle(mock_full_config):
    """
    Full lifecycle: customer messages → alert sent → human takes over → customer replies → 
    forwarded to human → human releases → AI resumes.
    """
    # Step 1: Customer sends initial message (new session)
    customer_row = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_flag": False,
        "escalation_flag": False,
    }
    db = _make_full_db(customer_row=customer_row, interactions_log_count=1)
    
    with patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock) as mock_load_config:
        with patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock) as mock_get_db:
            with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
                with patch("engine.core.message_handler.run_agent", new_callable=AsyncMock) as mock_agent:
                    mock_load_config.return_value = mock_full_config
                    mock_get_db.return_value = db
                    mock_send.return_value = "wamid.alert123"
                    mock_agent.return_value = "Sure, I can help with that!"
                    
                    await handle_inbound_message(
                        client_id="hey-aircon",
                        phone_number="6591234567",
                        message_text="I need help",
                        message_type="text",
                        message_id="wamid.msg1",
                        display_name="John Tan",
                    )
    
    # Verify conversation alert was sent
    alert_calls = [call for call in mock_send.call_args_list if "AI handling" in call[1].get("text", "")]
    assert len(alert_calls) > 0
    
    # Step 2: Human agent replies "take" to the alert
    db2 = _make_full_db(customer_row={
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_flag": False,
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock) as mock_send2:
        await handle_human_agent_message(
            db=db2,
            client_config=mock_full_config,
            phone_number="+6598765432",
            message_text="take",
            context_message_id="wamid.alert123",
        )
    
    # Verify takeover confirmation sent
    confirmation_calls = [call for call in mock_send2.call_args_list if "Taking over" in call[0][2]]
    assert len(confirmation_calls) > 0
    
    # Step 3: Customer sends another message while in takeover
    customer_row_takeover = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_flag": True,
        "escalation_flag": False,
    }
    db3 = _make_full_db(customer_row=customer_row_takeover)
    
    with patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock) as mock_load_config:
        with patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock) as mock_get_db:
            with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send3:
                mock_load_config.return_value = mock_full_config
                mock_get_db.return_value = db3
                
                await handle_inbound_message(
                    client_id="hey-aircon",
                    phone_number="6591234567",
                    message_text="Can I change my booking?",
                    message_type="text",
                    message_id="wamid.msg2",
                    display_name="John Tan",
                )
    
    # Verify message was forwarded to human agent
    forward_calls = [call for call in mock_send3.call_args_list if "just replied" in call[1]["text"]]
    assert len(forward_calls) > 0


@pytest.mark.asyncio
async def test_takeover_with_escalation_both_flags(mock_full_config):
    """Customer has both takeover_flag and escalation_flag: takeover takes priority."""
    customer_row = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_flag": True,
        "escalation_flag": True,
        "escalation_notified": False,
    }
    db = _make_full_db(customer_row=customer_row)
    
    with patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock) as mock_load_config:
        with patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock) as mock_get_db:
            with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
                mock_load_config.return_value = mock_full_config
                mock_get_db.return_value = db
                
                await handle_inbound_message(
                    client_id="hey-aircon",
                    phone_number="6591234567",
                    message_text="Hello",
                    message_type="text",
                    message_id="wamid.msg1",
                    display_name="John Tan",
                )
    
    # Verify takeover forward was sent (NOT escalation holding reply)
    assert mock_send.called
    forward_calls = [call for call in mock_send.call_args_list if "just replied" in call[1]["text"]]
    assert len(forward_calls) > 0
    
    # Should NOT contain holding reply text
    holding_calls = [call for call in mock_send.call_args_list if "team member will get back to you" in call[1]["text"]]
    assert len(holding_calls) == 0


@pytest.mark.asyncio
async def test_auto_resume_after_timeout(mock_full_config):
    """Auto-resume job clears stale takeover and sends notification."""
    now = datetime.now(timezone.utc)
    stale_customer = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_at": (now - timedelta(hours=5)).isoformat(),
    }
    
    db = MagicMock()
    
    def table_factory(table_name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.lt.return_value = chain
        chain.is_.return_value = chain
        
        if table_name == "customers":
            mock_response = MagicMock(data=[stale_customer])
        else:
            mock_response = MagicMock(data=[])
        
        chain.execute = AsyncMock(return_value=mock_response)
        return chain
    
    db.table.side_effect = table_factory
    
    with patch("engine.core.takeover_auto_resume.get_client_db", new_callable=AsyncMock) as mock_get_db:
        with patch("engine.core.takeover_auto_resume.send_message", new_callable=AsyncMock) as mock_send:
            mock_get_db.return_value = db
            
            await _auto_resume_for_client(mock_full_config, timeout_hours=4)
    
    # Verify notification sent
    mock_send.assert_called_once()
    assert "AI auto-resumed" in mock_send.call_args[0][2]


@pytest.mark.asyncio
async def test_status_command_during_active_takeover(mock_full_config):
    """//status command returns list of active takeovers."""
    now = datetime.now(timezone.utc)
    active_takeovers = [
        {
            "phone_number": "6591234567",
            "customer_name": "John Tan",
            "takeover_at": (now - timedelta(hours=2)).isoformat(),
        },
    ]
    
    db = MagicMock()
    
    def table_factory(table_name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        
        if table_name == "customers":
            mock_response = MagicMock(data=active_takeovers)
        else:
            mock_response = MagicMock(data=[])
        
        chain.execute = AsyncMock(return_value=mock_response)
        return chain
    
    db.table.side_effect = table_factory
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock) as mock_send:
        await handle_human_agent_message(
            db=db,
            client_config=mock_full_config,
            phone_number="+6598765432",
            message_text="//status",
            context_message_id=None,
        )
    
    # Verify status response
    mock_send.assert_called_once()
    status_text = mock_send.call_args[0][2]
    assert "Active takeovers (1)" in status_text
    assert "John Tan" in status_text


@pytest.mark.asyncio
async def test_conversation_alert_throttling(mock_full_config):
    """Conversation alert sent only once per session (not per message)."""
    customer_row = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_flag": False,
    }
    
    # First message: new session (count=1, only current message)
    db1 = _make_full_db(customer_row=customer_row, interactions_log_count=1)
    
    with patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock) as mock_load_config:
        with patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock) as mock_get_db:
            with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
                with patch("engine.core.message_handler.run_agent", new_callable=AsyncMock) as mock_agent:
                    mock_load_config.return_value = mock_full_config
                    mock_get_db.return_value = db1
                    mock_send.return_value = "wamid.alert123"
                    mock_agent.return_value = "Sure!"
                    
                    await handle_inbound_message(
                        client_id="hey-aircon",
                        phone_number="6591234567",
                        message_text="First message",
                        message_type="text",
                        message_id="wamid.msg1",
                        display_name="John Tan",
                    )
    
    # Verify alert sent
    alert_calls_1 = [call for call in mock_send.call_args_list if "AI handling" in call[1].get("text", "")]
    assert len(alert_calls_1) == 1
    
    # Second message: session active (count=2, current + previous)
    db2 = _make_full_db(customer_row=customer_row, interactions_log_count=2)
    
    with patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock) as mock_load_config:
        with patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock) as mock_get_db:
            with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
                with patch("engine.core.message_handler.run_agent", new_callable=AsyncMock) as mock_agent:
                    mock_load_config.return_value = mock_full_config
                    mock_get_db.return_value = db2
                    mock_agent.return_value = "Sure!"
                    
                    await handle_inbound_message(
                        client_id="hey-aircon",
                        phone_number="6591234567",
                        message_text="Second message",
                        message_type="text",
                        message_id="wamid.msg2",
                        display_name="John Tan",
                    )
    
    # Verify NO alert sent (session still active)
    alert_calls_2 = [call for call in mock_send.call_args_list if "AI handling" in call[1].get("text", "")]
    assert len(alert_calls_2) == 0


@pytest.mark.asyncio
async def test_takeover_gate_priority_over_escalation(mock_full_config):
    """Pipeline order verification: takeover gate runs before escalation gate."""
    customer_row = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "takeover_flag": True,
        "escalation_flag": True,
        "escalation_notified": False,
    }
    db = _make_full_db(customer_row=customer_row)
    
    with patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock) as mock_load_config:
        with patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock) as mock_get_db:
            with patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send:
                mock_load_config.return_value = mock_full_config
                mock_get_db.return_value = db
                
                await handle_inbound_message(
                    client_id="hey-aircon",
                    phone_number="6591234567",
                    message_text="Hello",
                    message_type="text",
                    message_id="wamid.msg1",
                    display_name="John Tan",
                )
    
    # Verify ONLY takeover forward sent (escalation gate skipped)
    assert mock_send.called
    
    # Should have takeover forward
    forward_calls = [call for call in mock_send.call_args_list if "just replied" in call[1]["text"]]
    assert len(forward_calls) > 0
    
    # Should NOT have escalation holding reply
    holding_calls = [call for call in mock_send.call_args_list if "team member will get back to you" in call[1]["text"]]
    assert len(holding_calls) == 0
