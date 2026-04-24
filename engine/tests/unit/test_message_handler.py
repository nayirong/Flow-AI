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
    OPT_OUT_REPLY,
    _is_opt_out_keyword,
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
    """Pipeline returns after escalation gate — customer upsert (step 5) must NOT happen.
    update() IS called once to flip escalation_notified=True — that is the gate itself,
    not the upsert. Assert that the holding reply is sent and step 5 is not reached."""
    mock_load_config.return_value = mock_client_config_obj
    escalated = {"phone_number": "6591234567", "escalation_flag": True, "escalation_notified": False}
    db, chain = _make_db(customer_row=escalated)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # Holding reply sent once.
    mock_send.assert_awaited_once()
    # update() called exactly once — to flip escalation_notified=True (gate, not upsert).
    chain.update.assert_called_once_with({"escalation_notified": True})


@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_escalated_already_notified_silent_drop(
    mock_load_config, mock_get_db, mock_send, mock_run_agent, mock_client_config_obj
):
    """Subsequent messages from an already-notified escalated customer are silently dropped.
    No holding reply, no agent call, no update."""
    mock_load_config.return_value = mock_client_config_obj
    already_notified = {
        "phone_number": "6591234567",
        "escalation_flag": True,
        "escalation_notified": True,
    }
    db, chain = _make_db(customer_row=already_notified)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # No reply sent to customer.
    mock_send.assert_not_awaited()
    # Agent not invoked.
    mock_run_agent.assert_not_awaited()
    # No update calls (nothing to flip — already notified).
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
async def test_current_inbound_removed_from_history_before_agent(
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj,
):
    """The just-logged inbound message must not be duplicated into LLM history."""
    mock_load_config.return_value = mock_client_config_obj
    mock_build_system.return_value = "System message"
    mock_fetch_history.return_value = [
        {"role": "assistant", "content": "Please reply yes to confirm your appointment."},
        {"role": "user", "content": _PARAMS["message_text"]},
    ]
    mock_run_agent.return_value = "Hi! How can I help you?"

    existing = {"phone_number": "6591234567", "escalation_flag": False}
    db, _ = _make_db(customer_row=existing)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    passed_history = mock_run_agent.await_args.kwargs["conversation_history"]
    assert passed_history == [
        {"role": "assistant", "content": "Please reply yes to confirm your appointment."}
    ]


@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
@patch("engine.core.message_handler._get_latest_pending_booking", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_tool_dispatch")
async def test_affirmative_pending_confirmation_bypasses_llm(
    mock_build_tool_dispatch,
    mock_get_pending_booking,
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj,
):
    """A plain yes/confirm reply should confirm the latest pending booking directly."""
    mock_load_config.return_value = mock_client_config_obj
    mock_get_pending_booking.return_value = {
        "booking_id": "HA-20260427-ABCD",
        "service_type": "General Servicing",
        "slot_date": "2026-04-27",
        "slot_window": "AM",
        "address": "123 Test Street",
        "postal_code": "123456",
    }
    mock_confirm = AsyncMock(return_value={
        "status": "confirmed",
        "booking_id": "HA-20260427-ABCD",
        "message": "✅ Your booking is confirmed! Reference: HA-20260427-ABCD.",
    })
    mock_build_tool_dispatch.return_value = {"confirm_booking": mock_confirm}

    existing = {"phone_number": "6591234567", "escalation_flag": False}
    db, _ = _make_db(customer_row=existing)
    mock_get_db.return_value = db

    await handle_inbound_message(
        **{**_PARAMS, "message_text": "yes"}
    )

    mock_confirm.assert_awaited_once_with(booking_id="HA-20260427-ABCD")
    mock_run_agent.assert_not_awaited()
    mock_send.assert_awaited_once_with(
        mock_client_config_obj,
        _PARAMS["phone_number"],
        "✅ Your booking is confirmed! Reference: HA-20260427-ABCD.",
    )


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


# ── Escalation Gate Specific Tests ────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_gate_silences_agent_when_flag_is_true(
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj
):
    """
    Escalation gate: when escalation_flag=True, agent is NOT called,
    holding reply returned instead.
    """
    mock_load_config.return_value = mock_client_config_obj

    escalated = {
        "phone_number": "6591234567",
        "escalation_flag": True,
        "escalation_reason": "Customer complaint",
    }
    db, _ = _make_db(customer_row=escalated)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # Agent should NOT be called at all
    mock_run_agent.assert_not_called()
    mock_build_system.assert_not_called()
    mock_fetch_history.assert_not_called()

    # Holding reply should be sent instead
    mock_send.assert_awaited_once_with(
        mock_client_config_obj,
        _PARAMS["phone_number"],
        HOLDING_REPLY,
    )


@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_gate_allows_agent_when_flag_is_false(
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj
):
    """
    Escalation gate: when escalation_flag=False, agent IS called normally.
    """
    mock_load_config.return_value = mock_client_config_obj
    mock_build_system.return_value = "System message"
    mock_fetch_history.return_value = []
    mock_run_agent.return_value = "Hi! How can I help you?"

    non_escalated = {
        "phone_number": "6591234567",
        "escalation_flag": False,
    }
    db, _ = _make_db(customer_row=non_escalated)
    mock_get_db.return_value = db

    await handle_inbound_message(**_PARAMS)

    # Agent SHOULD be called
    mock_run_agent.assert_awaited_once()
    mock_build_system.assert_awaited_once()
    mock_fetch_history.assert_awaited_once()

    # Agent response should be sent (not holding reply)
    mock_send.assert_awaited_once_with(
        mock_client_config_obj,
        _PARAMS["phone_number"],
        "Hi! How can I help you?",
    )


# ── Concurrency / Per-Customer Lock Tests ─────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_concurrent_messages_same_customer_are_serialized(
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj,
):
    """
    Three rapid messages from the same customer must be processed one at a time.

    Regression test for the concurrency race condition (2026-04-21):
    concurrent background tasks read stale history in parallel, causing premature
    tool invocations and duplicate/conflicting replies.

    Verifies: the per-customer asyncio.Lock in message_handler serializes tasks so
    each agent invocation completes (including reply logging) before the next starts.
    """
    import asyncio
    from engine.core import message_handler as mh

    # Clear any stale lock state from previous tests.
    mh._customer_locks.clear()

    mock_load_config.return_value = mock_client_config_obj
    mock_build_system.return_value = "System message"
    mock_fetch_history.return_value = []

    execution_order: list[int] = []

    # Each run_agent call records its start index, sleeps briefly to simulate LLM
    # latency, then records its finish index. If tasks run in parallel the
    # start/finish indices interleave; if serialized they appear in pairs.
    call_index = {"n": 0}

    async def tracked_run_agent(*args, **kwargs):
        idx = call_index["n"]
        call_index["n"] += 1
        execution_order.append(("start", idx))
        await asyncio.sleep(0.05)   # simulate LLM latency
        execution_order.append(("end", idx))
        return f"Reply {idx}"

    mock_run_agent.side_effect = tracked_run_agent

    non_escalated = {"phone_number": "6591234567", "escalation_flag": False}
    db, _ = _make_db(customer_row=non_escalated)
    mock_get_db.return_value = db

    phone = "6591234567"
    tasks = [
        asyncio.create_task(handle_inbound_message(
            client_id="hey-aircon",
            phone_number=phone,
            message_text=f"Message {i}",
            message_type="text",
            message_id=f"wamid.test{i}",
            display_name="Test User",
        ))
        for i in range(3)
    ]
    await asyncio.gather(*tasks)

    # With the lock, each task's end event must come before the next task's start.
    # i.e. execution_order must be: (start,0),(end,0),(start,1),(end,1),(start,2),(end,2)
    # Extract just the (action, call_idx) tuples to assert ordering.
    assert len(execution_order) == 6, f"Expected 6 events, got {execution_order}"
    for i in range(0, 6, 2):
        action_a, idx_a = execution_order[i]
        action_b, idx_b = execution_order[i + 1]
        assert action_a == "start", f"Expected start at position {i}, got {execution_order}"
        assert action_b == "end", f"Expected end at position {i+1}, got {execution_order}"
        assert idx_a == idx_b, (
            f"Start/end indices mismatch at position {i}: {execution_order}"
        )

    # All 3 agent invocations must have completed.
    assert mock_run_agent.await_count == 3


@pytest.mark.asyncio
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
async def test_concurrent_messages_different_customers_are_independent(
    mock_load_config, mock_get_db, mock_send,
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_client_config_obj,
):
    """
    Messages from different customers must NOT block each other.

    The per-customer lock is keyed by phone number. Two customers messaging
    simultaneously should both be processed concurrently, not queued behind
    each other.
    """
    import asyncio
    from engine.core import message_handler as mh

    mh._customer_locks.clear()

    mock_load_config.return_value = mock_client_config_obj
    mock_build_system.return_value = "System message"
    mock_fetch_history.return_value = []

    start_times: dict[str, float] = {}
    end_times: dict[str, float] = {}

    async def tracked_run_agent(*args, **kwargs):
        phone = kwargs.get("current_message", args[2] if len(args) > 2 else "unknown")
        # Use the message text as a proxy for phone in this mock context.
        # We'll record based on call count instead.
        await asyncio.sleep(0.1)
        return "Reply"

    mock_run_agent.side_effect = tracked_run_agent

    task_start: dict[int, float] = {}
    task_end: dict[int, float] = {}

    async def timed_handle(idx: int, phone: str):
        task_start[idx] = asyncio.get_event_loop().time()
        db, _ = _make_db(customer_row={"phone_number": phone, "escalation_flag": False})
        mock_get_db.return_value = db
        await handle_inbound_message(
            client_id="hey-aircon",
            phone_number=phone,
            message_text="Hello",
            message_type="text",
            message_id=f"wamid.test{idx}",
            display_name="Test",
        )
        task_end[idx] = asyncio.get_event_loop().time()

    # Run 2 different customers concurrently.
    await asyncio.gather(
        timed_handle(0, "6591111111"),
        timed_handle(1, "6592222222"),
    )

    # Both tasks should have started before either finished (i.e. they ran in parallel).
    # If they were serialized, task 1 would start only after task 0 ends.
    assert task_start[1] < task_end[0], (
        "Different-customer tasks should run concurrently, not sequentially. "
        f"Task 0: {task_start[0]:.3f}–{task_end[0]:.3f}, "
        f"Task 1: {task_start[1]:.3f}–{task_end[1]:.3f}"
    )
    assert mock_run_agent.await_count == 2


# ── Opt-Out Detection Tests ───────────────────────────────────────────────────


class TestOptOutDetection:
    """Tests for _is_opt_out_keyword helper."""

    def test_stop_is_opt_out(self):
        assert _is_opt_out_keyword("stop") is True

    def test_stop_case_insensitive(self):
        assert _is_opt_out_keyword("STOP") is True
        assert _is_opt_out_keyword("Stop") is True

    def test_stop_with_whitespace(self):
        assert _is_opt_out_keyword("  stop  ") is True

    def test_unsubscribe_is_opt_out(self):
        assert _is_opt_out_keyword("unsubscribe") is True

    def test_opt_out_hyphenated(self):
        assert _is_opt_out_keyword("opt-out") is True
        assert _is_opt_out_keyword("opt out") is True

    def test_regular_message_not_opt_out(self):
        assert _is_opt_out_keyword("I want to cancel my appointment") is False
        assert _is_opt_out_keyword("yes") is False
        assert _is_opt_out_keyword("stop the aircon please") is False

    def test_empty_message_not_opt_out(self):
        assert _is_opt_out_keyword("") is False
        assert _is_opt_out_keyword(None) is False


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
async def test_opt_out_keyword_marks_booking_opted_out(
    mock_run_agent, mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """'stop' with active pending booking → followup_stage set to 'opted_out'."""
    mock_load_config.return_value = mock_client_config_obj

    # Build chains for each table interaction
    # 1. Escalation query returns non-escalated customer
    escalation_chain = MagicMock()
    escalation_chain.select.return_value = escalation_chain
    escalation_chain.eq.return_value = escalation_chain
    escalation_chain.limit.return_value = escalation_chain
    escalation_chain.execute = AsyncMock(return_value=MagicMock(data=[{
        "phone_number": "6591234567",
        "escalation_flag": False,
        "escalation_notified": False,
        "customer_name": "Test User"
    }]))

    # 2. Customer upsert chain
    upsert_chain = MagicMock()
    upsert_chain.update.return_value = upsert_chain
    upsert_chain.eq.return_value = upsert_chain
    upsert_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # 3. Active followup booking query (with .not_)
    not_mock = MagicMock()
    not_mock.eq.return_value = not_mock
    
    booking_query_chain = MagicMock()
    booking_query_chain.select.return_value = booking_query_chain
    booking_query_chain.eq.return_value = booking_query_chain
    booking_query_chain.not_ = not_mock
    not_mock.order = MagicMock(return_value=not_mock)
    not_mock.limit = MagicMock(return_value=not_mock)
    not_mock.execute = AsyncMock(return_value=MagicMock(data=[{
        "booking_id": "HA-TEST-001",
        "followup_stage": "2h_sent",
        "booking_status": "pending_confirmation"
    }]))

    # 4. Booking update chain
    update_chain = MagicMock()
    update_chain.update.return_value = update_chain
    update_chain.eq.return_value = update_chain
    update_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # 5. Interactions log chain (for inbound + outbound)
    log_chain = MagicMock()
    log_chain.insert.return_value = log_chain
    log_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # Table routing logic
    def table_router(table_name):
        if table_name == "customers":
            return escalation_chain
        elif table_name == "bookings":
            if not hasattr(table_router, "booking_call_count"):
                table_router.booking_call_count = 0
            table_router.booking_call_count += 1
            if table_router.booking_call_count == 1:
                return booking_query_chain
            else:
                return update_chain
        elif table_name == "interactions_log":
            return log_chain
        return MagicMock()

    db = MagicMock()
    db.table = MagicMock(side_effect=table_router)
    mock_get_db.return_value = db

    await handle_inbound_message("test-client", "6591234567", "stop", "text", "wamid.001", "Test User")

    # Send_message must be called with OPT_OUT_REPLY
    mock_send.assert_called_once()
    call_args = mock_send.call_args[0]
    assert OPT_OUT_REPLY in call_args[-1]

    # Agent must NOT be called
    mock_run_agent.assert_not_called()


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
@patch("engine.core.message_handler.fetch_conversation_history", new_callable=AsyncMock)
@patch("engine.core.message_handler.build_system_message", new_callable=AsyncMock)
async def test_opt_out_no_active_booking_falls_through_to_agent(
    mock_build_system, mock_fetch_history, mock_run_agent,
    mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """'stop' with no active pending booking → passes through to agent."""
    mock_load_config.return_value = mock_client_config_obj
    mock_build_system.return_value = "System message"
    mock_fetch_history.return_value = []
    mock_run_agent.return_value = "Agent reply"

    # 1. Escalation returns non-escalated customer
    escalation_chain = MagicMock()
    escalation_chain.select.return_value = escalation_chain
    escalation_chain.eq.return_value = escalation_chain
    escalation_chain.limit.return_value = escalation_chain
    escalation_chain.execute = AsyncMock(return_value=MagicMock(data=[{
        "phone_number": "6591234567",
        "escalation_flag": False,
        "escalation_notified": False,
        "customer_name": "Test User"
    }]))

    # 2. Customer upsert chain
    upsert_chain = MagicMock()
    upsert_chain.update.return_value = upsert_chain
    upsert_chain.eq.return_value = upsert_chain
    upsert_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # 3. Active followup booking query returns empty (no pending bookings)
    not_mock_1 = MagicMock()
    not_mock_1.eq.return_value = not_mock_1
    not_mock_1.order = MagicMock(return_value=not_mock_1)
    not_mock_1.limit = MagicMock(return_value=not_mock_1)
    not_mock_1.execute = AsyncMock(return_value=MagicMock(data=[]))  # Empty result

    booking_query_chain = MagicMock()
    booking_query_chain.select.return_value = booking_query_chain
    booking_query_chain.eq.return_value = booking_query_chain
    booking_query_chain.not_ = not_mock_1

    # 4. _get_latest_pending_booking query (also returns empty)
    pending_booking_chain = MagicMock()
    pending_booking_chain.select.return_value = pending_booking_chain
    pending_booking_chain.eq.return_value = pending_booking_chain
    pending_booking_chain.order.return_value = pending_booking_chain
    pending_booking_chain.limit.return_value = pending_booking_chain
    pending_booking_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # 5. Interactions log chain
    log_chain = MagicMock()
    log_chain.insert.return_value = log_chain
    log_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # Table routing
    def table_router(table_name):
        if table_name == "customers":
            return escalation_chain
        elif table_name == "bookings":
            if not hasattr(table_router, "booking_call_count"):
                table_router.booking_call_count = 0
            table_router.booking_call_count += 1
            if table_router.booking_call_count == 1:
                return booking_query_chain  # For _get_active_followup_booking
            else:
                return pending_booking_chain  # For _get_latest_pending_booking
        elif table_name == "interactions_log":
            return log_chain
        return MagicMock()

    db = MagicMock()
    db.table = MagicMock(side_effect=table_router)
    mock_get_db.return_value = db

    await handle_inbound_message("test-client", "6591234567", "stop", "text", "wamid.001", "Test User")

    mock_run_agent.assert_called_once()


@pytest.mark.asyncio
@patch("engine.core.message_handler.send_message", new_callable=AsyncMock)
@patch("engine.core.message_handler.get_client_db", new_callable=AsyncMock)
@patch("engine.core.message_handler.load_client_config", new_callable=AsyncMock)
@patch("engine.core.message_handler.run_agent", new_callable=AsyncMock)
async def test_opt_out_logs_outbound_to_interactions_log(
    mock_run_agent, mock_load_config, mock_get_db, mock_send, mock_client_config_obj
):
    """Opt-out reply must be logged to interactions_log as outbound."""
    mock_load_config.return_value = mock_client_config_obj

    logged_rows = []

    # 1. Escalation query returns non-escalated customer
    escalation_chain = MagicMock()
    escalation_chain.select.return_value = escalation_chain
    escalation_chain.eq.return_value = escalation_chain
    escalation_chain.limit.return_value = escalation_chain
    escalation_chain.execute = AsyncMock(return_value=MagicMock(data=[{
        "phone_number": "6591234567",
        "escalation_flag": False,
        "escalation_notified": False,
        "customer_name": "Test User"
    }]))

    # 2. Customer upsert chain
    upsert_chain = MagicMock()
    upsert_chain.update.return_value = upsert_chain
    upsert_chain.eq.return_value = upsert_chain
    upsert_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # 3. Active followup booking query
    not_mock = MagicMock()
    not_mock.eq.return_value = not_mock
    not_mock.order = MagicMock(return_value=not_mock)
    not_mock.limit = MagicMock(return_value=not_mock)
    not_mock.execute = AsyncMock(return_value=MagicMock(data=[{
        "booking_id": "HA-TEST-001",
        "followup_stage": "2h_sent",
        "booking_status": "pending_confirmation"
    }]))

    booking_query_chain = MagicMock()
    booking_query_chain.select.return_value = booking_query_chain
    booking_query_chain.eq.return_value = booking_query_chain
    booking_query_chain.not_ = not_mock

    # 4. Booking update chain
    update_chain = MagicMock()
    update_chain.update.return_value = update_chain
    update_chain.eq.return_value = update_chain
    update_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # 5. Interactions log chain with capture
    log_chain = MagicMock()

    def capture_insert(row):
        logged_rows.append(row)
        mock_response = MagicMock()
        mock_response.data = []
        return log_chain

    log_chain.insert = MagicMock(side_effect=capture_insert)
    log_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    # Table routing
    def table_router(table_name):
        if table_name == "customers":
            return escalation_chain
        elif table_name == "bookings":
            if not hasattr(table_router, "booking_call_count"):
                table_router.booking_call_count = 0
            table_router.booking_call_count += 1
            if table_router.booking_call_count == 1:
                return booking_query_chain
            else:
                return update_chain
        elif table_name == "interactions_log":
            return log_chain
        return MagicMock()

    db = MagicMock()
    db.table = MagicMock(side_effect=table_router)
    mock_get_db.return_value = db

    await handle_inbound_message("test-client", "6591234567", "stop", "text", "wamid.001", "Test User")

    # Check that OPT_OUT_REPLY was logged as outbound
    outbound_rows = [r for r in logged_rows if r.get("direction") == "outbound"]
    assert any(OPT_OUT_REPLY in r.get("message_text", "") for r in outbound_rows)
