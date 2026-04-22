"""
Escalation tool unit tests — escalate_to_human() function.

Tests the escalation workflow:
- Supabase escalation_flag is set
- WhatsApp alert sent to human agent
- Return dict structure
- Error handling (DB failure continues, sends alert anyway)
- Alert skipped when no human_agent_number configured
- Alert contains the reason string
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_db():
    """Chainable Supabase mock that captures the last execute() call."""
    chain = MagicMock()
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    db = MagicMock()
    db.table.return_value = chain
    return db, chain


def _make_client_config(human_agent_number: str = "6590000001"):
    """Mock ClientConfig with human_agent_number."""
    cfg = MagicMock()
    cfg.client_id = "hey-aircon"
    cfg.human_agent_number = human_agent_number
    cfg.meta_phone_number_id = "123456789"
    cfg.meta_whatsapp_token = "test_token"
    return cfg


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_escalate_sets_flag_in_supabase():
    """Call escalate_to_human() → assert escalation_flag=True UPDATE is executed."""
    from engine.core.tools.escalation_tool import escalate_to_human

    db, chain = _make_db()
    cfg = _make_client_config()

    with patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock):
        result = await escalate_to_human(
            db=db,
            client_config=cfg,
            phone_number="6591234567",
            reason="Customer requested to speak to a person",
        )

    # Assert the UPDATE call was made
    chain.update.assert_called_once()
    update_data = chain.update.call_args[0][0]
    assert update_data["escalation_flag"] is True
    assert update_data["escalation_reason"] == "Customer requested to speak to a person"
    assert "last_seen" in update_data

    # eq() is called at least once for the UPDATE filter.
    # (A second call occurs for the post-update SELECT that feeds Sheets sync.)
    from unittest.mock import call
    assert call("phone_number", "6591234567") in chain.eq.call_args_list

    # execute() is called at least once (UPDATE). SELECT may add a second call.
    assert chain.execute.await_count >= 1


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_escalate_sends_whatsapp_alert(mock_send):
    """WhatsApp alert sent to human_agent_number with customer phone and reason."""
    from engine.core.tools.escalation_tool import escalate_to_human

    db, _ = _make_db()
    cfg = _make_client_config(human_agent_number="6590000001")

    await escalate_to_human(
        db=db,
        client_config=cfg,
        phone_number="6591234567",
        reason="Customer is angry",
    )

    # Assert send_message was called with human agent number
    mock_send.assert_awaited_once()
    call_args = mock_send.call_args
    assert call_args[1]["client_config"] == cfg
    assert call_args[1]["to_phone_number"] == "6590000001"

    # Assert alert text contains customer phone and reason
    alert_text = call_args[1]["text"]
    assert "6591234567" in alert_text
    assert "Customer is angry" in alert_text


@pytest.mark.asyncio
async def test_escalate_returns_correct_dict():
    """Return dict has status == 'escalated' and non-empty message field."""
    from engine.core.tools.escalation_tool import escalate_to_human

    db, _ = _make_db()
    cfg = _make_client_config()

    with patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock):
        result = await escalate_to_human(
            db=db,
            client_config=cfg,
            phone_number="6591234567",
            reason="Booking conflict",
        )

    assert result["status"] == "escalated"
    assert "message" in result
    assert len(result["message"]) > 0
    assert isinstance(result["message"], str)


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_escalate_continues_if_db_fails(mock_send):
    """Mock DB update to raise exception → function does NOT raise, still sends alert."""
    from engine.core.tools.escalation_tool import escalate_to_human

    db, chain = _make_db()
    chain.execute = AsyncMock(side_effect=Exception("Supabase connection lost"))
    cfg = _make_client_config()

    # Must not raise
    result = await escalate_to_human(
        db=db,
        client_config=cfg,
        phone_number="6591234567",
        reason="Test reason",
    )

    # Still attempts to send WhatsApp alert despite DB failure
    mock_send.assert_awaited_once()

    # Still returns success dict
    assert result["status"] == "escalated"


@pytest.mark.asyncio
async def test_escalate_skips_alert_if_no_human_agent_number():
    """Set human_agent_number = None → send_message NOT called, function still returns."""
    from engine.core.tools.escalation_tool import escalate_to_human

    db, _ = _make_db()
    cfg = _make_client_config(human_agent_number=None)

    with patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock) as mock_send:
        result = await escalate_to_human(
            db=db,
            client_config=cfg,
            phone_number="6591234567",
            reason="Test reason",
        )

    # send_message should NOT be called
    mock_send.assert_not_called()

    # Function still returns successfully
    assert result["status"] == "escalated"
    assert "message" in result


@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_escalate_message_contains_reason(mock_send):
    """Assert WhatsApp alert text contains the reason string."""
    from engine.core.tools.escalation_tool import escalate_to_human

    db, _ = _make_db()
    cfg = _make_client_config()

    custom_reason = "Slot conflict on 30 Apr AM"

    await escalate_to_human(
        db=db,
        client_config=cfg,
        phone_number="6591234567",
        reason=custom_reason,
    )

    # Assert the alert text contains the reason
    call_args = mock_send.call_args
    alert_text = call_args[1]["text"]
    assert custom_reason in alert_text


# ── Escalation routing tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_escalate_alert_routes_to_human_not_customer(mock_send):
    """
    Regression test: WhatsApp alert must go to human_agent_number, NEVER to the customer.

    This test catches the 2026-04-21 production bug where human_agent_number in the
    clients table was set to the test customer's own number, causing escalation alerts
    to be delivered to the customer instead of the human agent.

    The customer phone number (6591234567) and the human agent number (6590000001) are
    intentionally different. Assert the alert goes only to the human agent.
    """
    from engine.core.tools.escalation_tool import escalate_to_human

    customer_phone = "6591234567"
    human_agent_phone = "6590000001"

    db, _ = _make_db()
    cfg = _make_client_config(human_agent_number=human_agent_phone)

    await escalate_to_human(
        db=db,
        client_config=cfg,
        phone_number=customer_phone,
        reason="Customer wants to speak to a person",
    )

    # Alert must be sent exactly once
    mock_send.assert_awaited_once()

    # Destination MUST be the human agent number
    call_kwargs = mock_send.call_args[1]
    assert call_kwargs["to_phone_number"] == human_agent_phone, (
        f"Alert routed to wrong number: expected {human_agent_phone}, "
        f"got {call_kwargs['to_phone_number']}"
    )

    # Destination must NOT be the customer's own number
    assert call_kwargs["to_phone_number"] != customer_phone, (
        "Alert was incorrectly routed to the customer's own number"
    )


@pytest.mark.asyncio
@patch("engine.integrations.google_sheets.sync_customer_to_sheets", new_callable=AsyncMock)
@patch("engine.integrations.meta_whatsapp.send_message", new_callable=AsyncMock)
async def test_escalate_triggers_sheets_sync_on_success(mock_send, mock_sheets_sync):
    """
    After setting escalation_flag=True, the updated customer row must be synced
    to Google Sheets so the Sheets mirror reflects the escalation state.

    Regression test for the 2026-04-22 bug: escalation_flag=True in Supabase
    but still FALSE in Google Sheets because sync was never triggered.
    """
    from engine.core.tools.escalation_tool import escalate_to_human
    import asyncio

    customer_phone = "6591234567"
    db, chain = _make_db()

    # Wire select/limit back to the chain so the post-update SELECT also
    # resolves through chain.execute (same pattern as update/eq).
    chain.select.return_value = chain
    chain.limit.return_value = chain

    # SELECT after UPDATE returns the updated customer row
    updated_row = {
        "id": 1,
        "phone_number": customer_phone,
        "customer_name": "Test User",
        "escalation_flag": True,
        "escalation_reason": "Test reason",
        "total_bookings": 0,
    }
    chain.execute = AsyncMock(return_value=MagicMock(data=[updated_row]))

    cfg = _make_client_config()
    cfg.sheets_sync_enabled = True

    await escalate_to_human(
        db=db,
        client_config=cfg,
        phone_number=customer_phone,
        reason="Test reason",
    )

    # Give asyncio.create_task a chance to run
    await asyncio.sleep(0)

    # Sheets sync must have been triggered with the updated row
    mock_sheets_sync.assert_awaited_once()
    call_kwargs = mock_sheets_sync.call_args[1]
    assert call_kwargs["client_id"] == "hey-aircon"
    assert call_kwargs["customer_data"]["escalation_flag"] is True
