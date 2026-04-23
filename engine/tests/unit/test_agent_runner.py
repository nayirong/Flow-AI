"""
Slice 4 — Agent runner unit tests.

Tests the tool-use loop logic in engine/core/agent_runner.py.
All LLM client calls are mocked — no real Anthropic/GitHub Models API calls.
Provider env var is set to 'anthropic' for all tests (mocked anyway).
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers to build mock LLM responses ───────────────────────────────────────

def _make_block(**kwargs):
    """Create a mock content block with attribute access."""
    b = MagicMock()
    for k, v in kwargs.items():
        setattr(b, k, v)
    return b


def _end_turn_response(text: str = "This is the agent reply."):
    """Mock response with stop_reason='end_turn' and a text block."""
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [_make_block(type="text", text=text)]
    return resp


def _tool_use_response(tool_name: str, tool_id: str, tool_input: dict):
    """Mock response with stop_reason='tool_use' and one tool_use block."""
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [
        _make_block(
            type="tool_use",
            id=tool_id,
            name=tool_name,
            input=tool_input,
        )
    ]
    return resp


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_run_agent_end_turn_returns_text(mock_call_llm, mock_get_client):
    """Single LLM call with end_turn returns the text block content."""
    from engine.core.agent_runner import run_agent

    mock_call_llm.return_value = _end_turn_response("Sure, I can help with aircon servicing.")

    result = await run_agent(
        system_message="You are a helpful agent.",
        conversation_history=[],
        current_message="What services do you offer?",
        tool_definitions=[],
        tool_dispatch={},
    )

    assert result == "Sure, I can help with aircon servicing."
    assert mock_call_llm.call_count == 1


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_run_agent_includes_history_in_messages(mock_call_llm, mock_get_client):
    """Conversation history is prepended to the messages passed to the LLM."""
    from engine.core.agent_runner import run_agent

    mock_call_llm.return_value = _end_turn_response("Got it.")

    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    await run_agent(
        system_message="System.",
        conversation_history=history,
        current_message="Book me in tomorrow.",
        tool_definitions=[],
        tool_dispatch={},
    )

    call_kwargs = mock_call_llm.call_args[1]
    messages = call_kwargs["messages"]
    assert messages[0] == {"role": "user", "content": "Hello"}
    assert messages[1] == {"role": "assistant", "content": "Hi there!"}
    assert messages[-1] == {"role": "user", "content": "Book me in tomorrow."}


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_run_agent_tool_use_then_end_turn(mock_call_llm, mock_get_client):
    """Tool-use loop: first call returns tool_use, second call returns end_turn."""
    from engine.core.agent_runner import run_agent

    tool_resp = _tool_use_response(
        tool_name="check_calendar_availability",
        tool_id="tool_001",
        tool_input={"date": "2026-04-30", "timezone": "Asia/Singapore"},
    )
    end_resp = _end_turn_response("The AM slot on 30 April is available.")

    mock_call_llm.side_effect = [tool_resp, end_resp]

    async def mock_check_calendar(**kwargs):
        return {"am_available": True, "pm_available": False, "date": "2026-04-30"}

    result = await run_agent(
        system_message="System.",
        conversation_history=[],
        current_message="Is 30 April AM available?",
        tool_definitions=[{"name": "check_calendar_availability"}],
        tool_dispatch={"check_calendar_availability": mock_check_calendar},
    )

    assert result == "The AM slot on 30 April is available."
    assert mock_call_llm.call_count == 2


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_run_agent_tool_result_appended_to_messages(mock_call_llm, mock_get_client):
    """Tool result must be appended to messages before the second LLM call."""
    from engine.core.agent_runner import run_agent

    tool_resp = _tool_use_response("fake_tool", "tid_001", {"arg": "value"})
    end_resp = _end_turn_response("Done.")
    mock_call_llm.side_effect = [tool_resp, end_resp]

    async def fake_tool(**kwargs):
        return {"result": "ok"}

    await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Do something.",
        tool_definitions=[{"name": "fake_tool"}],
        tool_dispatch={"fake_tool": fake_tool},
    )

    # Second call's messages should include the tool_result user turn
    second_call_messages = mock_call_llm.call_args_list[1][1]["messages"]
    # Last user turn must contain the tool_result
    last_user_turn = second_call_messages[-1]
    assert last_user_turn["role"] == "user"
    content = last_user_turn["content"]
    assert isinstance(content, list)
    assert any(b.get("type") == "tool_result" for b in content)


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_run_agent_unknown_tool_returns_error_to_claude(mock_call_llm, mock_get_client):
    """Tool not in dispatch returns error dict to Claude — loop does not crash."""
    from engine.core.agent_runner import run_agent

    tool_resp = _tool_use_response("nonexistent_tool", "tid_002", {})
    end_resp = _end_turn_response("Sorry, I cannot do that.")
    mock_call_llm.side_effect = [tool_resp, end_resp]

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Do something.",
        tool_definitions=[],
        tool_dispatch={},  # empty — tool not found
    )

    assert result == "Sorry, I cannot do that."
    # Verify error was returned to Claude
    second_messages = mock_call_llm.call_args_list[1][1]["messages"]
    last_turn_content = second_messages[-1]["content"]
    tool_result_content = last_turn_content[0]["content"]
    error_dict = json.loads(tool_result_content)
    assert error_dict["error"] == "tool_not_found"


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_run_agent_tool_exception_returns_error_to_claude(mock_call_llm, mock_get_client):
    """Tool raising an exception returns error dict to Claude — loop does not crash."""
    from engine.core.agent_runner import run_agent

    tool_resp = _tool_use_response("crashing_tool", "tid_003", {})
    end_resp = _end_turn_response("I encountered an issue.")
    mock_call_llm.side_effect = [tool_resp, end_resp]

    async def crashing_tool(**kwargs):
        raise ValueError("Simulated tool failure")

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Do something.",
        tool_definitions=[{"name": "crashing_tool"}],
        tool_dispatch={"crashing_tool": crashing_tool},
    )

    assert result == "I encountered an issue."
    second_messages = mock_call_llm.call_args_list[1][1]["messages"]
    last_turn_content = second_messages[-1]["content"]
    error_dict = json.loads(last_turn_content[0]["content"])
    assert error_dict["error"] == "tool_execution_failed"
    assert "Simulated tool failure" in error_dict["message"]


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_run_agent_max_iterations_returns_fallback(mock_call_llm, mock_get_client):
    """Hitting MAX_TOOL_ITERATIONS returns fallback string, not an exception."""
    from engine.core.agent_runner import run_agent, MAX_TOOL_ITERATIONS, _FALLBACK_RESPONSE

    # Always return tool_use — forces max iteration hit
    mock_call_llm.return_value = _tool_use_response("loop_tool", "tid_loop", {})

    async def loop_tool(**kwargs):
        return {"ok": True}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Loop forever.",
        tool_definitions=[{"name": "loop_tool"}],
        tool_dispatch={"loop_tool": loop_tool},
    )

    assert result == _FALLBACK_RESPONSE
    assert mock_call_llm.call_count == MAX_TOOL_ITERATIONS


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_run_agent_llm_error_propagates(mock_call_llm, mock_get_client):
    """LLM API error must propagate so message_handler can send fallback reply."""
    from engine.core.agent_runner import run_agent

    mock_call_llm.side_effect = Exception("Anthropic API unavailable")

    with pytest.raises(Exception, match="Anthropic API unavailable"):
        await run_agent(
            system_message="Sys.",
            conversation_history=[],
            current_message="Hello.",
            tool_definitions=[],
            tool_dispatch={},
        )


@pytest.mark.asyncio
async def test_github_models_provider_shim(monkeypatch):
    """LLM_PROVIDER=github_models builds an OpenAI client pointed at GitHub Models."""
    monkeypatch.setenv("LLM_PROVIDER", "github_models")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")

    # Reset any cached module state
    import engine.core.agent_runner as ar_mod

    with patch("openai.AsyncOpenAI") as mock_openai_cls:
        mock_openai_cls.return_value = MagicMock()
        client = ar_mod._get_llm_client()

    mock_openai_cls.assert_called_once_with(
        api_key="ghp_test_token",
        base_url="https://models.inference.ai.azure.com/v1",
    )

    monkeypatch.delenv("LLM_PROVIDER")
    monkeypatch.delenv("GITHUB_TOKEN")


@pytest.mark.asyncio
async def test_model_name_override(monkeypatch):
    """LLM_MODEL_OVERRIDE takes precedence over defaults."""
    monkeypatch.setenv("LLM_MODEL_OVERRIDE", "claude-custom-model")
    import engine.core.agent_runner as ar_mod
    assert ar_mod._get_model_name() == "claude-custom-model"
    monkeypatch.delenv("LLM_MODEL_OVERRIDE")


# ── Booking confirmation guardrail tests ──────────────────────────────────────

@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_no_false_positive_without_calendar_check(mock_call_llm, mock_get_client):
    """
    Agent returns confirmation-like language but check_calendar_availability was
    never called (non-booking conversational turn). Guardrail must NOT fire.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    casual_text = "No worries, all set — let me know which service you'd like!"
    mock_call_llm.return_value = _end_turn_response(casual_text)

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="I am not sure about the BTU.",
        tool_definitions=[],
        tool_dispatch={},
    )

    # No calendar check → guardrail inactive → response passes through unchanged
    assert result == casual_text
    assert result != _BOOKING_GUARDRAIL_FALLBACK
    assert mock_call_llm.call_count == 1


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_fires_when_write_booking_not_called(mock_call_llm, mock_get_client):
    """
    Agent calls check_calendar_availability (calendar phase entered), then skips
    write_booking and returns confirmation language.
    Guardrail injects a re-prompt. Agent still skips write_booking.
    Guardrail fires and returns the safe fallback.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    # Sequence: calendar checked → agent skips write_booking and says confirmed
    # → re-prompt injected → agent says confirmed again → fallback
    calendar_resp = _tool_use_response(
        tool_name="check_calendar_availability",
        tool_id="tool_cal_001",
        tool_input={"date": "2026-04-30", "timezone": "Asia/Singapore"},
    )
    confirmation_text = "Your booking is confirmed for 30 April AM. See you on the day!"
    end_resp = _end_turn_response(confirmation_text)

    mock_call_llm.side_effect = [calendar_resp, end_resp, end_resp]

    async def mock_check_calendar(**kwargs):
        return {"am_available": True, "pm_available": False}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[{"name": "check_calendar_availability"}],
        tool_dispatch={"check_calendar_availability": mock_check_calendar},
    )

    assert result == _BOOKING_GUARDRAIL_FALLBACK
    # call 1: calendar tool → call 2: premature confirm → re-prompt → call 3: still no write_booking → fallback
    assert mock_call_llm.call_count == 3


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_passes_when_write_booking_succeeded(mock_call_llm, mock_get_client):
    """
    Agent calls check_calendar_availability then write_booking (returns a booking_id),
    then returns confirmation language. Guardrail must NOT intercept.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    calendar_resp = _tool_use_response(
        tool_name="check_calendar_availability",
        tool_id="tool_cal_002",
        tool_input={"date": "2026-04-30", "timezone": "Asia/Singapore"},
    )
    write_resp = _tool_use_response(
        tool_name="write_booking",
        tool_id="tool_wb_001",
        tool_input={"service_type": "Aircon Chemical Wash", "slot_date": "2026-04-30"},
    )
    confirmation_text = "Your booking is confirmed for 30 April AM. See you on the day!"
    end_resp = _end_turn_response(confirmation_text)

    mock_call_llm.side_effect = [calendar_resp, write_resp, end_resp]

    async def mock_check_calendar(**kwargs):
        return {"am_available": True, "pm_available": False}

    async def mock_write_booking(**kwargs):
        return {"booking_id": "BK-2026-001", "status": "confirmed"}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[{"name": "check_calendar_availability"}, {"name": "write_booking"}],
        tool_dispatch={
            "check_calendar_availability": mock_check_calendar,
            "write_booking": mock_write_booking,
        },
    )

    assert result == confirmation_text
    assert result != _BOOKING_GUARDRAIL_FALLBACK
    assert mock_call_llm.call_count == 3


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_fires_when_write_booking_returns_error(mock_call_llm, mock_get_client):
    """
    Agent calls check_calendar_availability then write_booking, but write_booking
    returns an error. Agent then returns confirmation language — guardrail re-prompts
    once, agent still skips write_booking, so guardrail fires and returns fallback.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    calendar_resp = _tool_use_response(
        tool_name="check_calendar_availability",
        tool_id="tool_cal_003",
        tool_input={"date": "2026-04-30", "timezone": "Asia/Singapore"},
    )
    write_resp = _tool_use_response(
        tool_name="write_booking",
        tool_id="tool_wb_002",
        tool_input={"service_type": "Aircon Service", "slot_date": "2026-04-30"},
    )
    end_resp = _end_turn_response("Your booking is confirmed!")

    mock_call_llm.side_effect = [calendar_resp, write_resp, end_resp, end_resp]

    async def mock_check_calendar(**kwargs):
        return {"am_available": True, "pm_available": False}

    async def mock_write_booking_fail(**kwargs):
        return {"error": "calendar_unavailable", "message": "Could not create calendar event"}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[{"name": "check_calendar_availability"}, {"name": "write_booking"}],
        tool_dispatch={
            "check_calendar_availability": mock_check_calendar,
            "write_booking": mock_write_booking_fail,
        },
    )

    assert result == _BOOKING_GUARDRAIL_FALLBACK


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_reprompt_recovers_booking(mock_call_llm, mock_get_client):
    """
    Agent calls check_calendar_availability, then skips write_booking (confirmation
    language detected). Guardrail injects re-prompt. On retry agent calls write_booking
    successfully — confirmation passes through cleanly.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    confirmation_text = "Your booking is confirmed! Reference: BK-2026-002."

    # Sequence:
    # 1. tool_use: check_calendar_availability called
    # 2. end_turn: premature confirmation (no write_booking) → re-prompt injected
    # 3. tool_use: write_booking called
    # 4. end_turn: confirmation — write_booking succeeded, passes through
    calendar_resp = _tool_use_response(
        tool_name="check_calendar_availability",
        tool_id="tool_cal_004",
        tool_input={"date": "2026-04-30", "timezone": "Asia/Singapore"},
    )
    premature_confirm = _end_turn_response(confirmation_text)
    write_booking_call = _tool_use_response(
        tool_name="write_booking",
        tool_id="tool_wb_003",
        tool_input={"service_type": "Aircon Service", "slot_date": "2026-04-30"},
    )
    final_confirm = _end_turn_response(confirmation_text)

    mock_call_llm.side_effect = [calendar_resp, premature_confirm, write_booking_call, final_confirm]

    async def mock_check_calendar(**kwargs):
        return {"am_available": True, "pm_available": False}

    async def mock_write_booking(**kwargs):
        return {"booking_id": "BK-2026-002", "status": "confirmed"}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[{"name": "check_calendar_availability"}, {"name": "write_booking"}],
        tool_dispatch={
            "check_calendar_availability": mock_check_calendar,
            "write_booking": mock_write_booking,
        },
    )

    assert result == confirmation_text
    assert result != _BOOKING_GUARDRAIL_FALLBACK
    assert mock_call_llm.call_count == 4


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_fires_when_summary_sent_without_write_booking(mock_call_llm, mock_get_client):
    """
    Agent calls check_calendar_availability, then sends a booking summary asking
    the customer to reply yes, but never calls write_booking. Guardrail must catch
    this as a premature booking summary and return the safe fallback.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    calendar_resp = _tool_use_response(
        tool_name="check_calendar_availability",
        tool_id="tool_cal_006",
        tool_input={"date": "2026-04-30", "timezone": "Asia/Singapore"},
    )
    premature_summary = _end_turn_response(
        "Here's your booking summary:\n"
        "Service: General Servicing\n"
        "Date: 2026-04-30\n"
        "Please reply yes to confirm your appointment."
    )

    mock_call_llm.side_effect = [calendar_resp, premature_summary, premature_summary]

    async def mock_check_calendar(**kwargs):
        return {"am_available": True, "pm_available": False}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[{"name": "check_calendar_availability"}],
        tool_dispatch={"check_calendar_availability": mock_check_calendar},
    )

    assert result == _BOOKING_GUARDRAIL_FALLBACK
    assert mock_call_llm.call_count == 3


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_reprompt_text_response_blocked(mock_call_llm, mock_get_client):
    """
    Agent calls check_calendar_availability, then returns premature confirmation
    language (no write_booking). Guardrail injects re-prompt. On the next iteration
    the agent responds with plain text (internal reasoning — no confirmation keywords,
    no write_booking call). That text must NOT be returned to the customer;
    run_agent must return _BOOKING_GUARDRAIL_FALLBACK instead.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    # Sequence:
    # 1. tool_use: check_calendar_availability
    # 2. end_turn: premature confirmation → re-prompt injected (_booking_reprompt_used = True)
    # 3. end_turn: internal reasoning text (no confirmation keywords, no write_booking)
    #    → must be blocked and return fallback, NOT sent to customer
    calendar_resp = _tool_use_response(
        tool_name="check_calendar_availability",
        tool_id="tool_cal_005",
        tool_input={"date": "2026-04-30", "timezone": "Asia/Singapore"},
    )
    premature_confirm = _end_turn_response(
        "Your booking is confirmed for 30 April AM. See you on the day!"
    )
    # Internal reasoning text — no confirmation keywords, no write_booking call
    internal_reasoning = _end_turn_response(
        "I appreciate you pointing that out, but I need to clarify the situation with you."
    )

    mock_call_llm.side_effect = [calendar_resp, premature_confirm, internal_reasoning]

    async def mock_check_calendar(**kwargs):
        return {"am_available": True, "pm_available": False}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[{"name": "check_calendar_availability"}],
        tool_dispatch={"check_calendar_availability": mock_check_calendar},
    )

    # Internal reasoning must not leak to customer
    assert result == _BOOKING_GUARDRAIL_FALLBACK
    assert "I appreciate you pointing that out" not in result
    assert mock_call_llm.call_count == 3
