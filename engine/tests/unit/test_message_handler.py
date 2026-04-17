"""
Slice 3 + 4 — Message Handler unit tests.

Tests the inbound message processing pipeline in engine/core/message_handler.py:
- Inbound logging (always first)
- Escalation gate (holding reply, outbound log, pipeline stop)
- New customer INSERT
- Returning customer last_seen UPDATE
- DB failure → fallback reply, no crash
- Meta send failure → no crash
- Unknown client → no crash
- Agent invoked for non-escalated customers (Slice 4)
- Agent reply sent and logged (Slice 4)
- Agent error → fallback reply, no crash (Slice 4)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from engine.core.message_handler import (
    handle_inbound_message,
    HOLDING_REPLY,
    FALLBACK_REPLY,
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_db(customer_row=None):
    """
    Build a fully-chainable mock Supabase client for message_handler queries.

    Returns (db_mock, chain_mock) so individual tests can assert on chain calls.
    All .execute() calls return a response with data=[customer_row] or data=[].
    """
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.order.return_value = chain

    mock_response = MagicMock()
    mock_response.data = [customer_row] if customer_row else []
    chain.execute = AsyncMock(return_value=mock_response)

    db = MagicMock()
    db.table.return_value = chain

    return db, chain


# Shared invocation parameters — valid HeyAircon inbound message.
_PARAMS = dict(
    client_id="hey-aircon",
    phone_number="6591234567",
    message_text="Hello, I need aircon servicing",
    message_type="text",
    message_id="wamid.test123",
    display_name="John Tan",
)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_inbound_logged_before_escalation(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """Inbound message must be written to interactions_log before any other processing."""
    mock_load_config.return_value = mock_client_config_obj
    db, chain = _make_db(customer_row=None)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    table_calls = [c[0][0] for c in db.table.call_args_list]
    assert "interactions_log" in table_calls
    chain.insert.assert_called()


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_escalated_customer_sends_holding_reply(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """Customer with escalation_flag=True receives HOLDING_REPLY."""
    mock_load_config.return_value = mock_client_config_obj
    escalated = {
        "phone_number": "6591234567",
        "escalation_flag": True,
        "escalation_reason": "Customer complaint",
    }
    db, _ = _make_db(customer_row=escalated)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    mock_send.assert_awaited_once_with(
        mock_client_config_obj,
        _PARAMS["phone_number"],
        HOLDING_REPLY,
    )


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_escalated_customer_logs_outbound(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """Holding reply must be written to interactions_log as an outbound interaction."""
    mock_load_config.return_value = mock_client_config_obj
    escalated = {"phone_number": "6591234567", "escalation_flag": True}
    db, _ = _make_db(customer_row=escalated)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # ≥2 interactions_log calls: inbound log + outbound holding-reply log
    log_calls = [c[0][0] for c in db.table.call_args_list if c[0][0] == "interactions_log"]
    assert len(log_calls) >= 2


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_escalated_customer_stops_pipeline(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """Pipeline returns after escalation gate — customer upsert must NOT happen."""
    mock_load_config.return_value = mock_client_config_obj
    escalated = {"phone_number": "6591234567", "escalation_flag": True}
    db, chain = _make_db(customer_row=escalated)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # update() would only be called in step 5 (upsert) — must not be reached.
    chain.update.assert_not_called()


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_new_customer_is_inserted(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """New customer (no existing row) triggers INSERT into customers table."""
    mock_load_config.return_value = mock_client_config_obj
    db, chain = _make_db(customer_row=None)  # no existing customer
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    table_calls = [c[0][0] for c in db.table.call_args_list]
    assert "customers" in table_calls
    chain.insert.assert_called()


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_returning_customer_last_seen_updated(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """Returning non-escalated customer triggers last_seen UPDATE."""
    mock_load_config.return_value = mock_client_config_obj
    existing = {
        "phone_number": "6591234567",
        "customer_name": "John Tan",
        "escalation_flag": False,
    }
    db, chain = _make_db(customer_row=existing)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    chain.update.assert_called()


@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_non_escalated_customer_agent_is_invoked(
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj
):
    """Non-escalated customer triggers agent invocation (Slice 4)."""
    mock_load_config.return_value = mock_client_config_obj
    mock_build_system.return_value = "System message"
    mock_fetch_history.return_value = []
    mock_run_agent.return_value = "Hi! How can I help you?"

    existing = {"phone_number": "6591234567", "escalation_flag": False}
    db, _ = _make_db(customer_row=existing)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    mock_run_agent.assert_awaited_once()
    mock_send.assert_awaited_once_with(
        mock_client_config_obj,
        _PARAMS["phone_number"],
        "Hi! How can I help you?",
    )


@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_agent_reply_is_logged_as_outbound(
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj
):
    """Agent reply must be written to interactions_log as an outbound row."""
    mock_load_config.return_value = mock_client_config_obj
    mock_build_system.return_value = "System message"
    mock_fetch_history.return_value = []
    mock_run_agent.return_value = "Your booking is confirmed!"

    db, _ = _make_db(customer_row={"phone_number": "6591234567", "escalation_flag": False})
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # Should have ≥2 interactions_log calls: inbound log + outbound reply log
    log_calls = [c[0][0] for c in db.table.call_args_list if c[0][0] == "interactions_log"]
    assert len(log_calls) >= 2


@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_agent_error_sends_fallback_does_not_crash(
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj
):
    """LLM API error during run_agent → FALLBACK_REPLY sent, no exception propagated."""
    mock_load_config.return_value = mock_client_config_obj
    mock_build_system.return_value = "System message"
    mock_fetch_history.return_value = []
    mock_run_agent.side_effect = Exception("Anthropic API unavailable")

    db, _ = _make_db(customer_row={"phone_number": "6591234567", "escalation_flag": False})
    mock_get_db.return_value = db

    # Must not raise
    await handle_inbound_message(**_PARAMS)

    mock_send.assert_awaited_once_with(
        mock_client_config_obj,
        _PARAMS["phone_number"],
        FALLBACK_REPLY,
    )


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_db_query_failure_sends_fallback(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """Critical DB failure (customer query) triggers FALLBACK_REPLY and does not crash."""
    mock_load_config.return_value = mock_client_config_obj

    # First execute() call (inbound log) succeeds; second (customer query) raises.
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain

    call_n = {"n": 0}

    async def execute_se():
        call_n["n"] += 1
        if call_n["n"] == 1:
            return MagicMock(data=[])  # inbound log INSERT succeeds
        raise Exception("Supabase connection lost")

    chain.execute = AsyncMock(side_effect=execute_se)

    db = MagicMock()
    db.table.return_value = chain
    mock_get_db.return_value = db

    # Must not raise.
    await handle_inbound_message(**_PARAMS)

    mock_send.assert_awaited_once_with(
        mock_client_config_obj,
        _PARAMS["phone_number"],
        FALLBACK_REPLY,
    )


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_meta_send_failure_does_not_crash(
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """send_message raising during escalated reply must not propagate the exception."""
    mock_load_config.return_value = mock_client_config_obj
    mock_send.side_effect = Exception("Meta API unavailable")

    escalated = {"phone_number": "6591234567", "escalation_flag": True}
    db, _ = _make_db(customer_row=escalated)
    mock_get_db.return_value = db

    # Must not raise despite send_message failure.
    await handle_inbound_message(**_PARAMS)


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_unknown_client_does_not_crash(
    mock_load_config, mock_get_db, mock_send
):
    """ClientNotFoundError from load_client_config must not propagate."""
    from engine.config.client_config import ClientNotFoundError
    mock_load_config.side_effect = ClientNotFoundError("unknown-client")

    # Must not raise.
    await handle_inbound_message(
        client_id="unknown-client",
        phone_number="6591234567",
        message_text="Hello",
        message_type="text",
        message_id="wamid.test456",
        display_name="Unknown",
    )
