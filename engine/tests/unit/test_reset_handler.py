"""
Reset handler unit tests — handle_human_agent_message() function.

Tests the escalation reset workflow:
- Help messages for invalid usage
- Keyword normalisation (case, spaces)
- Escalation flag clearing
- Tracking row updates
- Confirmation messages
- Error handling
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db(escalation_row=None):
    """Mock Supabase client with chainable table() methods."""
    # Mock for escalation_tracking query
    tracking_chain = MagicMock()
    tracking_chain.select.return_value = tracking_chain
    tracking_chain.update.return_value = tracking_chain
    tracking_chain.eq.return_value = tracking_chain
    tracking_chain.is_.return_value = tracking_chain
    tracking_chain.limit.return_value = tracking_chain
    tracking_chain.order.return_value = tracking_chain

    tracking_result = MagicMock()
    tracking_result.data = [escalation_row] if escalation_row else []
    tracking_chain.execute = AsyncMock(return_value=tracking_result)
    
    # Mock for customers update
    customers_chain = MagicMock()
    customers_chain.update.return_value = customers_chain
    customers_chain.eq.return_value = customers_chain
    customers_chain.select.return_value = customers_chain
    customers_chain.limit.return_value = customers_chain
    customers_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Root table() selector
    db = MagicMock()
    def table_selector(name):
        if name == "escalation_tracking":
            return tracking_chain
        elif name == "customers":
            return customers_chain
        return MagicMock()
    
    db.table = MagicMock(side_effect=table_selector)
    
    return db, tracking_chain, customers_chain


def _make_db_with_tracking_results(tracking_results):
    """Mock DB where escalation_tracking queries return a sequence of results."""
    tracking_chain = MagicMock()
    tracking_chain.select.return_value = tracking_chain
    tracking_chain.update.return_value = tracking_chain
    tracking_chain.eq.return_value = tracking_chain
    tracking_chain.is_.return_value = tracking_chain
    tracking_chain.limit.return_value = tracking_chain
    tracking_chain.order.return_value = tracking_chain

    async def tracking_execute():
        if tracking_results:
            data = tracking_results.pop(0)
        else:
            data = []
        return MagicMock(data=data)

    tracking_chain.execute = AsyncMock(side_effect=tracking_execute)

    customers_chain = MagicMock()
    customers_chain.update.return_value = customers_chain
    customers_chain.eq.return_value = customers_chain
    customers_chain.select.return_value = customers_chain
    customers_chain.limit.return_value = customers_chain
    customers_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    db = MagicMock()

    def table_selector(name):
        if name == "escalation_tracking":
            return tracking_chain
        if name == "customers":
            return customers_chain
        return MagicMock()

    db.table = MagicMock(side_effect=table_selector)
    return db, tracking_chain, customers_chain


def _make_client_config():
    """Mock ClientConfig."""
    cfg = MagicMock()
    cfg.client_id = "hey-aircon"
    cfg.human_agent_number = "6590000001"
    return cfg


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_no_context_id_sends_help(mock_send):
    """Human agent sends fresh message (not a reply) → help message sent."""
    from engine.core.reset_handler import handle_human_agent_message
    
    db, _, _ = _make_db()
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="done",
        context_message_id=None,
    )
    
    # Assert help message sent
    mock_send.assert_awaited_once()
    call_args = mock_send.call_args
    assert call_args[0][1] == "6590000001"  # to_phone_number
    assert "reply" in call_args[0][2].lower()  # help text mentions "reply"


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_no_matching_alert_sends_not_found(mock_send):
    """Human agent replies to unrelated message → 'no escalation found' sent."""
    from engine.core.reset_handler import handle_human_agent_message
    
    db, _, _ = _make_db(escalation_row=None)  # Empty result
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="done",
        context_message_id="wamid.unrelated",
    )
    
    # Assert "no escalation found" message sent
    mock_send.assert_awaited_once()
    call_args = mock_send.call_args
    assert "No pending escalation" in call_args[0][2]


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_already_resolved_alert_sends_not_found(mock_send):
    """Human agent replies to already-resolved alert → 'no escalation found' sent."""
    from engine.core.reset_handler import handle_human_agent_message
    
    # Mock: query returns no rows (resolved_at IS NULL filter excludes resolved rows)
    db, _, _ = _make_db(escalation_row=None)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="done",
        context_message_id="wamid.already_resolved",
    )
    
    # Assert "no escalation found" message sent
    mock_send.assert_awaited_once()
    call_args = mock_send.call_args
    assert "No pending escalation" in call_args[0][2]


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_historical_alert_recovers_latest_unresolved_escalation(mock_send):
    """Replying to an older alert can clear the latest unresolved escalation for that customer."""
    from engine.core.reset_handler import handle_human_agent_message

    latest_unresolved = {
        "id": 2,
        "phone_number": "6591234567",
        "alert_msg_id": None,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Latest unresolved",
        "resolved_at": None,
        "resolved_by": None,
    }

    db, tracking_chain, customers_chain = _make_db_with_tracking_results([
        [],
        [{"phone_number": "6591234567"}],
        [latest_unresolved],
    ])
    cfg = _make_client_config()

    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="done",
        context_message_id="wamid.oldalert123",
    )

    customers_chain.update.assert_called()
    update_call = customers_chain.update.call_args[0][0]
    assert update_call["escalation_flag"] is False
    assert tracking_chain.update.call_count >= 1
    confirmation = mock_send.call_args[0][2]
    assert "cleared" in confirmation.lower()


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_unrecognised_keyword_sends_help(mock_send):
    """Human agent replies with typo → help message sent, flag NOT cleared."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, _, customers_chain = _make_db(escalation_row=escalation_row)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="resolvedd",  # typo
        context_message_id="wamid.alert123",
    )
    
    # Assert help message sent
    mock_send.assert_awaited_once()
    call_args = mock_send.call_args
    assert "reply with" in call_args[0][2].lower()
    
    # Assert customers update NOT called (flag not cleared)
    customers_chain.update.assert_not_called()


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_emoji_sends_help(mock_send):
    """Human agent replies with emoji → help message sent."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, _, customers_chain = _make_db(escalation_row=escalation_row)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="👍",
        context_message_id="wamid.alert123",
    )
    
    # Assert help message sent
    mock_send.assert_awaited_once()
    call_args = mock_send.call_args
    assert "reply with" in call_args[0][2].lower()
    
    # Assert customers update NOT called
    customers_chain.update.assert_not_called()


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_keyword_done_clears_flag(mock_send):
    """Human agent replies with 'done' → flag cleared, confirmation sent."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, tracking_chain, customers_chain = _make_db(escalation_row=escalation_row)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="done",
        context_message_id="wamid.alert123",
    )
    
    # Assert customers.escalation_flag cleared
    customers_chain.update.assert_called()
    update_call = customers_chain.update.call_args[0][0]
    assert update_call["escalation_flag"] is False
    
    # Assert escalation_tracking resolved
    assert tracking_chain.update.call_count >= 1  # At least one update (tracking row)
    
    # Assert confirmation sent
    assert mock_send.await_count == 1
    confirmation = mock_send.call_args[0][2]
    assert "✅" in confirmation
    assert "cleared" in confirmation.lower()


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_keyword_uppercase_clears_flag(mock_send):
    """Human agent replies with 'DONE' → flag cleared (case insensitive)."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, _, customers_chain = _make_db(escalation_row=escalation_row)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="DONE",
        context_message_id="wamid.alert123",
    )
    
    # Assert flag cleared
    customers_chain.update.assert_called()
    update_call = customers_chain.update.call_args[0][0]
    assert update_call["escalation_flag"] is False


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_keyword_internal_space_clears_flag(mock_send):
    """Human agent replies with 'res olved' → normalised, flag cleared."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, _, customers_chain = _make_db(escalation_row=escalation_row)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="res olved",
        context_message_id="wamid.alert123",
    )
    
    # Assert flag cleared (normalised "res olved" → "resolved")
    customers_chain.update.assert_called()
    update_call = customers_chain.update.call_args[0][0]
    assert update_call["escalation_flag"] is False


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_keyword_leading_trailing_space_clears_flag(mock_send):
    """Human agent replies with '  done  ' → stripped, flag cleared."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, _, customers_chain = _make_db(escalation_row=escalation_row)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="  done  ",
        context_message_id="wamid.alert123",
    )
    
    # Assert flag cleared
    customers_chain.update.assert_called()
    update_call = customers_chain.update.call_args[0][0]
    assert update_call["escalation_flag"] is False


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_keyword_ok_clears_flag(mock_send):
    """Human agent replies with 'ok' → flag cleared."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, _, customers_chain = _make_db(escalation_row=escalation_row)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="ok",
        context_message_id="wamid.alert123",
    )
    
    # Assert flag cleared
    customers_chain.update.assert_called()
    update_call = customers_chain.update.call_args[0][0]
    assert update_call["escalation_flag"] is False


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_confirmation_contains_customer_info(mock_send):
    """Confirmation message contains customer phone number."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, _, _ = _make_db(escalation_row=escalation_row)
    cfg = _make_client_config()
    
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="done",
        context_message_id="wamid.alert123",
    )
    
    # Assert confirmation contains customer phone
    mock_send.assert_awaited_once()
    confirmation = mock_send.call_args[0][2]
    assert "6591234567" in confirmation or "customer" in confirmation.lower()


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_db_failure_sends_error_reply(mock_send):
    """DB UPDATE raises exception → error message sent, no re-raise."""
    from engine.core.reset_handler import handle_human_agent_message
    
    escalation_row = {
        "id": 1,
        "phone_number": "6591234567",
        "alert_msg_id": "wamid.alert123",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "escalation_reason": "Test",
        "resolved_at": None,
        "resolved_by": None,
    }
    
    db, _, customers_chain = _make_db(escalation_row=escalation_row)
    
    # Mock customers.update().execute() to raise exception
    customers_chain.execute = AsyncMock(side_effect=Exception("DB connection lost"))
    
    cfg = _make_client_config()
    
    # Should NOT raise
    await handle_human_agent_message(
        db=db,
        client_config=cfg,
        phone_number="6590000001",
        message_text="done",
        context_message_id="wamid.alert123",
    )
    
    # Assert error message sent
    mock_send.assert_awaited_once()
    error_msg = mock_send.call_args[0][2]
    assert "Failed" in error_msg or "⚠️" in error_msg


@pytest.mark.asyncio
async def test_non_human_agent_not_routed_to_reset():
    """Customer message (not human agent) passes through normal pipeline."""
    from engine.core.message_handler import handle_inbound_message
    
    # This test verifies that Step 0 routing check works correctly.
    # We'll mock the client config to have a different human_agent_number.
    
    with patch("engine.core.message_handler.load_client_config") as mock_config_load, \
         patch("engine.core.message_handler.get_client_db") as mock_db, \
         patch("engine.core.message_handler.send_message", new_callable=AsyncMock) as mock_send, \
         patch("engine.core.reset_handler.handle_human_agent_message") as mock_reset:
        
        # Mock config with different human agent number
        cfg = _make_client_config()
        cfg.human_agent_number = "6599999999"  # Different from message sender
        mock_config_load.return_value = cfg
        
        # Mock DB with escalation_flag=False
        db, _, _ = _make_db()
        mock_db.return_value = db
        
        # Customer sends message
        await handle_inbound_message(
            client_id="hey-aircon",
            phone_number="6591234567",  # Customer, not human agent
            message_text="Hello",
            message_type="text",
            message_id="wamid.test",
            display_name="John Tan",
            context_message_id=None,
        )
        
        # Assert reset handler NOT called
        mock_reset.assert_not_called()
