"""
Claude agent runner — tool-use loop for the Flow AI engine.

Provider shim
─────────────
Production (Railway):       LLM_PROVIDER=anthropic  → Anthropic SDK directly
Local eval / testing:       LLM_PROVIDER=github_models → GitHub Models API
                                                          (OpenAI-compatible, uses
                                                           GITHUB_TOKEN, covered by
                                                           Copilot subscription)
Unit tests:                 LLM client is mocked entirely — provider never matters.

The shim is internal to this module. No other part of the engine knows about it.

Tool-use loop
─────────────
1. Call LLM with system message, history + current message, and tool definitions.
2. If stop_reason == "tool_use": extract tool blocks, execute each, append results, loop.
3. If stop_reason == "end_turn": extract final text response, return.
4. Hard cap of MAX_TOOL_ITERATIONS (10) to prevent infinite loops.
5. Any LLM API error propagates to the caller (message_handler catches it).
"""
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10
_FALLBACK_RESPONSE = (
    "I'm sorry, I wasn't able to complete your request right now. "
    "Please try again in a moment, or our team will be happy to assist you directly."
)


# ── Provider shim ─────────────────────────────────────────────────────────────

def _get_llm_client() -> Any:
    """
    Return the appropriate LLM client based on LLM_PROVIDER env var.

    LLM_PROVIDER=anthropic (default):
        Returns anthropic.AsyncAnthropic — uses ANTHROPIC_API_KEY.

    LLM_PROVIDER=github_models:
        Returns openai.AsyncOpenAI pointed at GitHub Models inference endpoint.
        Uses GITHUB_TOKEN. Covered by GitHub Copilot subscription.
        No separate billing needed for local eval runs.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider == "github_models":
        try:
            import openai  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "openai package required for LLM_PROVIDER=github_models. "
                "Run: pip install openai"
            )
        github_token = os.environ.get("GITHUB_TOKEN", "")
        if not github_token:
            raise ValueError(
                "GITHUB_TOKEN env var required when LLM_PROVIDER=github_models"
            )
        logger.info("Using GitHub Models provider (Copilot subscription)")
        return openai.AsyncOpenAI(
            api_key=github_token,
            base_url="https://models.inference.ai.azure.com/v1",
        )

    # Default: Anthropic SDK
    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "anthropic package required. Run: pip install anthropic"
        )
    logger.info("Using Anthropic provider")
    return anthropic.AsyncAnthropic()


def _get_model_name() -> str:
    """
    Return the model identifier for the active provider.

    Can be overridden via LLM_MODEL_OVERRIDE env var for testing.
    Defaults:
        anthropic      → claude-sonnet-4-6
        github_models  → claude-sonnet-4-6-20250219  (GitHub Models catalog name)
    """
    override = os.environ.get("LLM_MODEL_OVERRIDE", "")
    if override:
        return override

    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "github_models":
        return "claude-sonnet-4-6-20250219"
    return "claude-sonnet-4-6"


# ── Provider-normalised call ──────────────────────────────────────────────────

async def _call_llm(
    client: Any,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
) -> Any:
    """
    Make one LLM call, normalised across providers.

    Returns a response object. For Anthropic it's the native response.
    For GitHub Models (OpenAI-compatible) it's wrapped into an Anthropic-shaped
    object so the rest of the loop code is provider-agnostic.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider == "github_models":
        # GitHub Models uses the OpenAI chat completions API.
        # We build an openai-compatible call and normalise the response.
        openai_messages = [{"role": "system", "content": system}] + messages
        openai_tools = _tools_to_openai_format(tools) if tools else []

        kwargs: dict = {
            "model": model,
            "messages": openai_messages,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        raw = await client.chat.completions.create(**kwargs)
        return _normalise_openai_response(raw)

    # Anthropic SDK — native call
    kwargs = {
        "model": model,
        "max_tokens": 1024,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    return await client.messages.create(**kwargs)


def _tools_to_openai_format(anthropic_tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool definitions to OpenAI function-calling format."""
    openai_tools = []
    for tool in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return openai_tools


def _normalise_openai_response(raw: Any) -> Any:
    """
    Wrap an OpenAI ChatCompletion into an Anthropic-shaped response object
    so the tool-use loop code is provider-agnostic.
    """
    choice = raw.choices[0]
    msg = choice.message

    # Build content blocks
    content: list[dict] = []

    if msg.content:
        content.append({"type": "text", "text": msg.content})

    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                input_data = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                input_data = {}
            content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.function.name,
                "input": input_data,
            })

    # Map finish_reason to Anthropic stop_reason
    finish_reason = choice.finish_reason or "stop"
    stop_reason_map = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
    }
    stop_reason = stop_reason_map.get(finish_reason, "end_turn")

    # Lightweight wrapper — just needs .stop_reason and .content
    class _NormalisedResponse:
        pass

    resp = _NormalisedResponse()
    resp.stop_reason = stop_reason
    resp.content = [_block_from_dict(b) for b in content]
    return resp


def _block_from_dict(d: dict) -> Any:
    """Wrap a content block dict into an object with attribute access."""
    class _Block:
        pass
    b = _Block()
    for k, v in d.items():
        setattr(b, k, v)
    return b


# ── Public API ────────────────────────────────────────────────────────────────

async def run_agent(
    system_message: str,
    conversation_history: list[dict],
    current_message: str,
    tool_definitions: list[dict],
    tool_dispatch: dict,
) -> str:
    """
    Run the Claude tool-use loop and return the final text response.

    Args:
        system_message:       Assembled system prompt from context_builder.
        conversation_history: Previous messages for this customer (oldest first).
        current_message:      The customer's current inbound message text.
        tool_definitions:     Anthropic-format tool dicts. Empty list = no tools (Slice 4).
        tool_dispatch:        Maps tool name → async callable. Empty dict = no tools.

    Returns:
        Final agent response text to send to the customer.

    Raises:
        Exception: LLM API errors propagate — caller (message_handler) handles them.
    """
    client = _get_llm_client()
    model = _get_model_name()

    # Build initial messages list: history + current inbound
    messages: list[dict] = list(conversation_history) + [
        {"role": "user", "content": current_message}
    ]

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = await _call_llm(
            client=client,
            model=model,
            system=system_message,
            messages=messages,
            tools=tool_definitions,
        )

        # ── End turn — extract text and return ────────────────────────────────
        if response.stop_reason in ("end_turn", "stop_sequence"):
            final_text = _extract_text(response.content)
            logger.info(
                f"Agent response generated (iter={iteration + 1}, "
                f"chars={len(final_text)})"
            )
            return final_text or _FALLBACK_RESPONSE

        # ── Tool use — execute tools and loop ─────────────────────────────────
        if response.stop_reason == "tool_use":
            # Append assistant's response (including tool_use blocks) to messages
            messages.append({
                "role": "assistant",
                "content": _content_to_list(response.content),
            })

            # Execute each tool and collect results
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    tool_result = await _execute_tool(
                        block=block,
                        tool_dispatch=tool_dispatch,
                    )
                    tool_results.append(tool_result)

            # Append tool results as a user turn
            messages.append({
                "role": "user",
                "content": tool_results,
            })
            continue

        # Unknown stop reason — treat as end turn
        logger.warning(f"Unexpected stop_reason: {response.stop_reason!r} — treating as end_turn")
        final_text = _extract_text(response.content)
        return final_text or _FALLBACK_RESPONSE

    # Max iterations reached — return fallback
    logger.error(
        f"Agent hit MAX_TOOL_ITERATIONS ({MAX_TOOL_ITERATIONS}) — returning fallback"
    )
    return _FALLBACK_RESPONSE


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_text(content: list) -> str:
    """Extract the first text block from a content list."""
    for block in content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return ""


def _content_to_list(content: list) -> list[dict]:
    """Convert content block objects to serialisable dicts for the messages array."""
    result = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            result.append({"type": "text", "text": getattr(block, "text", "")})
        elif block_type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": getattr(block, "input", {}),
            })
    return result


async def _execute_tool(block: Any, tool_dispatch: dict) -> dict:
    """
    Execute a single tool call and return a tool_result block.

    Any exception from the tool function is caught and returned as an error
    dict to Claude — the loop never crashes on tool failure.
    """
    tool_name = getattr(block, "name", "unknown")
    tool_input = getattr(block, "input", {})
    tool_id = getattr(block, "id", "")

    tool_fn = tool_dispatch.get(tool_name)

    if tool_fn is None:
        logger.warning(f"Tool not found in dispatch: {tool_name!r}")
        content = json.dumps({"error": "tool_not_found", "tool": tool_name})
    else:
        try:
            result = await tool_fn(**tool_input)
            content = json.dumps(result) if not isinstance(result, str) else result
        except Exception as e:
            logger.error(f"Tool {tool_name!r} raised: {e}", exc_info=True)
            content = json.dumps({"error": "tool_execution_failed", "message": str(e)})

    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": content,
    }
