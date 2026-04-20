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
async def test_guardrail_fires_when_write_booking_not_called(mock_call_llm, mock_get_client):
    """
    Agent returns booking confirmation language but write_booking was never called.
    Guardrail must intercept and return the safe fallback — NOT the confirmation.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    # Agent skips tools and goes straight to a confirmation reply
    mock_call_llm.return_value = _end_turn_response(
        "Your booking is confirmed for 30 April AM. See you on the day!"
    )

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[],
        tool_dispatch={},
    )

    assert result == _BOOKING_GUARDRAIL_FALLBACK
    assert mock_call_llm.call_count == 1


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_passes_when_write_booking_succeeded(mock_call_llm, mock_get_client):
    """
    Agent calls write_booking (returns a booking_id), then returns confirmation language.
    Guardrail must NOT intercept — the confirmation is legitimate.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    tool_resp = _tool_use_response(
        tool_name="write_booking",
        tool_id="tool_wb_001",
        tool_input={"service_type": "Aircon Chemical Wash", "slot_date": "2026-04-30"},
    )
    confirmation_text = "Your booking is confirmed for 30 April AM. See you on the day!"
    end_resp = _end_turn_response(confirmation_text)

    mock_call_llm.side_effect = [tool_resp, end_resp]

    async def mock_write_booking(**kwargs):
        return {"booking_id": "BK-2026-001", "status": "confirmed"}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[{"name": "write_booking"}],
        tool_dispatch={"write_booking": mock_write_booking},
    )

    # Confirmation should pass through — write_booking succeeded
    assert result == confirmation_text
    assert result != _BOOKING_GUARDRAIL_FALLBACK
    assert mock_call_llm.call_count == 2


@pytest.mark.asyncio
@patch("engine.core.agent_runner._get_llm_client")
@patch("engine.core.agent_runner._call_llm", new_callable=AsyncMock)
async def test_guardrail_fires_when_write_booking_returns_error(mock_call_llm, mock_get_client):
    """
    Agent calls write_booking but it returns an error (no booking_id).
    Agent then returns confirmation language — guardrail must intercept.
    """
    from engine.core.agent_runner import run_agent, _BOOKING_GUARDRAIL_FALLBACK

    tool_resp = _tool_use_response(
        tool_name="write_booking",
        tool_id="tool_wb_002",
        tool_input={"service_type": "Aircon Service", "slot_date": "2026-04-30"},
    )
    end_resp = _end_turn_response("Your booking is confirmed!")

    mock_call_llm.side_effect = [tool_resp, end_resp]

    async def mock_write_booking_fail(**kwargs):
        return {"error": "calendar_unavailable", "message": "Could not create calendar event"}

    result = await run_agent(
        system_message="Sys.",
        conversation_history=[],
        current_message="Book me for 30 April AM.",
        tool_definitions=[{"name": "write_booking"}],
        tool_dispatch={"write_booking": mock_write_booking_fail},
    )

    assert result == _BOOKING_GUARDRAIL_FALLBACK
