"""
Claude agent runner — tool-use loop for the Flow AI engine.

Provider shim
─────────────
Production (Railway):       LLM_PROVIDER=anthropic  → Anthropic SDK (Haiku 4.5 primary)
                            Fallback:                → GPT-4o-mini via OpenAI SDK
                                                       (silent, per-request, on Anthropic error)
Local eval / testing:       LLM_PROVIDER=github_models → GitHub Models API
                                                          (OpenAI-compatible, uses
                                                           GITHUB_TOKEN, covered by
                                                           Copilot subscription)
Unit tests:                 LLM client is mocked entirely — provider never matters.

The shim is internal to this module. No other part of the engine knows about it.

Tool-use loop
─────────────
1. Call primary LLM (Anthropic Haiku 4.5) with system message, history + current message, and tool definitions.
2. On Anthropic APIConnectionError, APIStatusError(5xx), or timeout → silent switch to GPT-4o-mini.
3. If stop_reason == "tool_use": execute tools, append results, loop (up to MAX_TOOL_ITERATIONS).
4. If stop_reason == "end_turn": return final text response.
5. Fallback is per-request only — next message retries Anthropic first.
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

# Guardrail: block confirmation language if write_booking never succeeded in this turn.
# Prevents the agent from telling a customer their booking is confirmed when no
# calendar event was created and no Supabase row was written.
_BOOKING_GUARDRAIL_FALLBACK = (
    "I'm sorry, I wasn't able to complete your booking right now. "
    "A member of our team will follow up with you today to confirm your appointment."
)
_BOOKING_CONFIRMATION_KEYWORDS = [
    "confirmed",
    "booked",
    "booking reference",
    "booking id",
    "booking summary",
    "appointment summary",
    "here's your booking summary",
    "here is your booking summary",
    "reply yes to confirm",
    "reply *yes* to confirm",
    "confirm your appointment",
    "confirm the appointment",
    "confirm your booking",
    "all set",
    "appointment is set",
    "see you on",
    "has been scheduled",
    "we'll see you",
    "we will see you",
]


def _contains_booking_confirmation(text: str) -> bool:
    """Return True if text contains booking confirmation language."""
    lower = text.lower()
    return any(keyword in lower for keyword in _BOOKING_CONFIRMATION_KEYWORDS)


# ── Booking guardrail ─────────────────────────────────────────────────────────

class _GuardrailAction:
    """Return type from _apply_booking_guardrail — one of four outcomes."""
    PASS_THROUGH = "pass_through"       # No guardrail concern — return final_text as-is
    INJECT_REPROMPT = "inject_reprompt" # Guardrail caught premature confirm — inject correction
    ESCALATED = "escalated"             # Agent escalated after re-prompt — valid, return text
    FIRE_FALLBACK = "fire_fallback"     # Guardrail exhausted — return safe fallback text


def _apply_booking_guardrail(
    final_text: str,
    calendar_check_succeeded: bool,
    booking_write_succeeded: bool,
    booking_reprompt_used: bool,
    escalation_called: bool,
    iteration: int,
    client_id: str,
) -> tuple[str, str]:
    """
    Apply the booking confirmation guardrail to an end-turn agent response.

    The guardrail is ONLY active when:
      - check_calendar_availability succeeded this invocation (we are genuinely
        in the booking phase — prevents false positives on casual "all set" language)
      - write_booking has NOT succeeded

    Returns:
        (action, detail) where action is one of _GuardrailAction constants.
        detail is a log message for the caller.

    The caller decides what to do based on the action:
      PASS_THROUGH   → return final_text
      INJECT_REPROMPT → inject correction messages and continue the loop
      ESCALATED       → return final_text (agent resolved via escalation)
      FIRE_FALLBACK   → escalate + return _BOOKING_GUARDRAIL_FALLBACK
    """
    if not (calendar_check_succeeded and not booking_write_succeeded):
        return _GuardrailAction.PASS_THROUGH, ""

    if _contains_booking_confirmation(final_text):
        if not booking_reprompt_used:
            return (
                _GuardrailAction.INJECT_REPROMPT,
                f"agent skipped write_booking (iter={iteration}, client_id={client_id}) — re-prompt injected",
            )
        # Re-prompt was used but still confirmation language — guardrail exhausted
        return (
            _GuardrailAction.FIRE_FALLBACK,
            f"write_booking not called after re-prompt (iter={iteration}, client_id={client_id})",
        )

    if booking_reprompt_used:
        if escalation_called:
            # Agent escalated in response to re-prompt — valid resolution
            return (
                _GuardrailAction.ESCALATED,
                f"agent escalated after re-prompt (iter={iteration}, client_id={client_id})",
            )
        # Re-prompt injected but agent produced plain text — internal reasoning leaked
        return (
            _GuardrailAction.FIRE_FALLBACK,
            f"agent produced text after re-prompt without calling write_booking (iter={iteration}, client_id={client_id})",
        )

    return _GuardrailAction.PASS_THROUGH, ""


# ── Provider shim ─────────────────────────────────────────────────────────────

def _get_llm_client(anthropic_api_key: str = "") -> Any:
    """
    Return the appropriate LLM client based on LLM_PROVIDER env var.

    LLM_PROVIDER=anthropic (default):
        Returns anthropic.AsyncAnthropic — uses per-client anthropic_api_key.

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

    # Default: Anthropic SDK — use per-client key
    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "anthropic package required. Run: pip install anthropic"
        )
    logger.info("Using Anthropic provider")
    return anthropic.AsyncAnthropic(api_key=anthropic_api_key or None)


def _get_model_name() -> str:
    """
    Return the model identifier for the active provider.

    Can be overridden via LLM_MODEL env var (or LLM_MODEL_OVERRIDE for tests).
    Defaults:
        anthropic      → claude-haiku-4-5-20251001  (primary — eval before upgrading to Sonnet)
        github_models  → claude-haiku-4-5-20251001  (GitHub Models catalog name)
    """
    override = os.environ.get("LLM_MODEL_OVERRIDE", "") or os.environ.get("LLM_MODEL", "")
    if override:
        return override

    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "github_models":
        return "claude-haiku-4-5-20251001"
    return "claude-haiku-4-5-20251001"


def _get_openai_fallback_client(openai_api_key: str = "") -> Any:
    """
    Return an OpenAI AsyncClient for GPT-4o-mini fallback.
    Uses per-client openai_api_key from ClientConfig.
    """
    try:
        import openai  # type: ignore[import]
    except ImportError:
        raise ImportError("openai package required for fallback. Run: pip install openai")
    api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("No OpenAI API key available for GPT-4o-mini fallback")
    return openai.AsyncOpenAI(api_key=api_key)


def _get_fallback_model_name() -> str:
    return os.environ.get("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")


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
    client_id: str = "",
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    pending_booking_id: str | None = None,
) -> str:
    """
    Run the Claude tool-use loop and return the final text response.

    Args:
        system_message:       Assembled system prompt from context_builder.
        conversation_history: Previous messages for this customer (oldest first).
        current_message:      The customer's current inbound message text.
        tool_definitions:     Anthropic-format tool dicts. Empty list = no tools.
        tool_dispatch:        Maps tool name → async callable. Empty dict = no tools.
        client_id:            Client identifier for observability logging.
        anthropic_api_key:    Per-client Anthropic API key.
        openai_api_key:       Per-client OpenAI API key (fallback).

    Returns:
        Final agent response text. Returns _FALLBACK_RESPONSE if both providers fail —
        message_handler will send this to the customer as a technical error message.
    """
    from engine.integrations.observability import log_incident, log_usage, extract_usage, send_telegram_alert, log_noncritical_failure

    client = _get_llm_client(anthropic_api_key=anthropic_api_key)
    model = _get_model_name()
    active_provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    fallback_enabled = os.environ.get("LLM_FALLBACK_ENABLED", "true").lower() != "false"
    _original_llm_provider = os.environ.get("LLM_PROVIDER", "anthropic")

    # Guardrail: tracks booking tool state for this invocation.
    # The confirmation guardrail only activates when check_calendar_availability
    # has succeeded — i.e., we are genuinely in the booking confirmation phase.
    # This prevents false positives from casual confirmation language ("all set",
    # "confirmed") used in non-booking conversational contexts.
    calendar_check_succeeded = False
    booking_write_succeeded = False
    _booking_reprompt_used = False
    escalation_called = False  # True if escalate_to_human ran successfully this turn

    # Second guardrail: tracks confirm_booking when a pending booking exists.
    # Prevents the agent from fabricating a booking confirmation in text without
    # actually calling confirm_booking (the zero-tool, iter=1 hallucination case).
    confirm_booking_succeeded = False
    _confirm_reprompt_used = False

    # Build initial messages list: history + current inbound
    messages: list[dict] = list(conversation_history) + [
        {"role": "user", "content": current_message}
    ]

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = await _call_llm(
                client=client,
                model=model,
                system=system_message,
                messages=messages,
                tools=tool_definitions,
            )
            # Log token usage on every successful call
            in_tok, out_tok = extract_usage(response, active_provider)
            await log_usage(
                provider=active_provider,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                client_id=client_id,
            )
        except Exception as llm_err:
            is_anthropic_primary = active_provider == "anthropic"
            # Match any Anthropic SDK error by checking the class hierarchy, not just
            # the leaf class name. AuthenticationError, RateLimitError, etc. are all
            # subclasses of APIError — all should trigger fallback.
            is_retryable = any(
                "APIConnectionError" in c.__name__
                or "APIStatusError" in c.__name__
                or "APIError" in c.__name__
                or "TimeoutError" in c.__name__
                for c in type(llm_err).__mro__
            )

            if is_anthropic_primary and is_retryable and fallback_enabled:
                # Log Anthropic incident
                await log_incident(
                    provider="anthropic",
                    error_type=type(llm_err).__name__,
                    error_message=str(llm_err),
                    client_id=client_id,
                    fallback_used=True,
                )
                logger.warning(
                    "Anthropic unavailable (%s) — switching to GPT-4o-mini for this request",
                    type(llm_err).__name__,
                )
                try:
                    client = _get_openai_fallback_client(openai_api_key=openai_api_key)
                    model = _get_fallback_model_name()
                    active_provider = "openai"
                    os.environ["LLM_PROVIDER"] = "github_models"  # reuse OpenAI-compat path
                    response = await _call_llm(
                        client=client,
                        model=model,
                        system=system_message,
                        messages=messages,
                        tools=tool_definitions,
                    )
                    # Log usage for the fallback call
                    in_tok, out_tok = extract_usage(response, "openai")
                    await log_usage(
                        provider="openai",
                        model=model,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        client_id=client_id,
                    )
                    # Fallback succeeded — notify team via Telegram
                    try:
                        await log_noncritical_failure(
                            source="llm_anthropic_fallback",
                            error_type=type(llm_err).__name__,
                            error_message=str(llm_err),
                            client_id=client_id,
                            context={"providers_failed": "Anthropic", "fallback_to": "OpenAI (gpt-4o-mini)"},
                        )
                    except Exception:
                        pass
                except Exception as fallback_err:
                    # Both providers failed — log and return graceful error string
                    await log_incident(
                        provider="openai",
                        error_type=type(fallback_err).__name__,
                        error_message=str(fallback_err),
                        client_id=client_id,
                        fallback_used=False,
                        both_failed=True,
                    )
                    logger.error(
                        "Both Anthropic and OpenAI failed — client_id=%s anthropic=%s openai=%s",
                        client_id, type(llm_err).__name__, type(fallback_err).__name__,
                    )
                    try:
                        await send_telegram_alert(
                            title="LLM Total Failure",
                            source="llm_both_failed",
                            client_id=client_id,
                            error_type=type(fallback_err).__name__,
                            error_message=str(fallback_err),
                            context={"providers_failed": "Anthropic + OpenAI"},
                            action_note="Customer received fallback reply. Agent could not respond.\nMonitor Anthropic/OpenAI status pages.",
                        )
                    except Exception:
                        pass
                    os.environ["LLM_PROVIDER"] = _original_llm_provider
                    return _FALLBACK_RESPONSE
            else:
                # Non-retryable error or fallback disabled — log and surface to caller
                await log_incident(
                    provider=active_provider,
                    error_type=type(llm_err).__name__,
                    error_message=str(llm_err),
                    client_id=client_id,
                    fallback_used=False,
                )
                raise

        # ── End turn — extract text and return ────────────────────────────────
        if response.stop_reason in ("end_turn", "stop_sequence"):
            final_text = _extract_text(response.content)
            logger.info(
                f"Agent response generated (iter={iteration + 1}, "
                f"chars={len(final_text)})"
            )

            # Second guardrail: pending booking exists but confirm_booking not called.
            # Catches the case where the agent fabricates a booking confirmation in
            # text (iter=1, zero tools) without calling confirm_booking.
            if pending_booking_id and not confirm_booking_succeeded and _contains_booking_confirmation(final_text):
                if not _confirm_reprompt_used:
                    _confirm_reprompt_used = True
                    logger.warning(
                        "PENDING BOOKING GUARDRAIL: agent confirmed booking %s in text without "
                        "calling confirm_booking (iter=%d, client_id=%s)",
                        pending_booking_id, iteration + 1, client_id,
                    )
                    await log_incident(
                        provider="agent_guardrail",
                        error_type="pending_booking_guardrail_reprompt",
                        error_message=f"agent fabricated confirm for {pending_booking_id} without calling confirm_booking",
                        client_id=client_id,
                    )
                    messages.append({"role": "assistant", "content": [{"type": "text", "text": final_text}]})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"[SYSTEM CORRECTION] You described a booking confirmation without calling confirm_booking. "
                            f"You MUST call confirm_booking with booking_id='{pending_booking_id}' now. "
                            "Do NOT describe or imply the booking is confirmed in text. "
                            "Call the tool — the tool creates the calendar event and updates the database."
                        ),
                    })
                    continue
                else:
                    logger.warning(
                        "PENDING BOOKING GUARDRAIL FIRED: confirm_booking not called after re-prompt "
                        "(pending_booking_id=%s, client_id=%s)",
                        pending_booking_id, client_id,
                    )
                    await log_incident(
                        provider="agent_guardrail",
                        error_type="pending_booking_guardrail_fired",
                        error_message=f"confirm_booking not called after re-prompt for {pending_booking_id}",
                        client_id=client_id,
                    )
                    return _BOOKING_GUARDRAIL_FALLBACK

            # First guardrail: only active when check_calendar_availability succeeded this
            # invocation (i.e., we are in the write_booking phase). Prevents
            # false positives from casual confirmation language in non-booking turns.
            if calendar_check_succeeded and not booking_write_succeeded:
                guardrail_action, guardrail_detail = _apply_booking_guardrail(
                    final_text=final_text,
                    calendar_check_succeeded=calendar_check_succeeded,
                    booking_write_succeeded=booking_write_succeeded,
                    booking_reprompt_used=_booking_reprompt_used,
                    escalation_called=escalation_called,
                    iteration=iteration + 1,
                    client_id=client_id,
                )

                if guardrail_action == _GuardrailAction.INJECT_REPROMPT:
                    _booking_reprompt_used = True
                    logger.warning("GUARDRAIL: %s", guardrail_detail)
                    await log_incident(
                        provider="agent_guardrail",
                        error_type="guardrail_reprompt_injected",
                        error_message=guardrail_detail,
                        client_id=client_id,
                    )
                    messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": final_text}],
                    })
                    messages.append({
                        "role": "user",
                        "content": (
                            "[SYSTEM CORRECTION] You have not called write_booking yet. "
                            "You must take one of the following actions now — do not respond with text: "
                            "If check_calendar_availability already confirmed the customer's requested slot is available, "
                            "that already counts as agreement for write_booking. Do NOT ask for a second confirmation before write_booking. "
                            "(1) The ONLY required fields for write_booking are: customer_name, service_type, "
                            "unit_count, address, postal_code, slot_date, slot_window. BTU size, aircon brand, "
                            "and other optional details are NOT required — do not block on them. "
                            "If you have all 7 required fields, call write_booking immediately. "
                            "CRITICAL: Use the EXACT slot_window (AM or PM) that the customer most recently stated. "
                            "Do NOT switch to a different slot_window. "
                            "(2) Only if one of those 7 required fields is genuinely unknown, call escalate_to_human. "
                            "Do not ask the customer for more information."
                        ),
                    })
                    continue

                elif guardrail_action == _GuardrailAction.ESCALATED:
                    logger.info("GUARDRAIL: %s — returning agent reply", guardrail_detail)
                    return final_text or _FALLBACK_RESPONSE

                elif guardrail_action == _GuardrailAction.FIRE_FALLBACK:
                    logger.warning("GUARDRAIL FIRED: %s", guardrail_detail)
                    await log_incident(
                        provider="agent_guardrail",
                        error_type="guardrail_fired",
                        error_message=guardrail_detail,
                        client_id=client_id,
                    )
                    try:
                        await tool_dispatch["escalate_to_human"](
                            reason=(
                                "Booking guardrail fired — agent could not complete write_booking. "
                                "Customer needs manual follow-up to confirm booking."
                            )
                        )
                    except Exception as esc_err:
                        logger.error("Failed to escalate after guardrail fire: %s", esc_err)
                    return _BOOKING_GUARDRAIL_FALLBACK

                # _GuardrailAction.PASS_THROUGH — fall through to return below

            os.environ["LLM_PROVIDER"] = _original_llm_provider
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

                    # Guardrail tracking: record calendar check and write_booking outcomes.
                    if getattr(block, "name", None) == "check_calendar_availability":
                        try:
                            result_data = json.loads(tool_result["content"])
                            if "error" not in result_data:
                                calendar_check_succeeded = True
                                logger.info("check_calendar_availability succeeded")
                        except (json.JSONDecodeError, TypeError):
                            pass

                    if getattr(block, "name", None) == "escalate_to_human":
                        try:
                            result_data = json.loads(tool_result["content"])
                            if result_data.get("status") == "escalated":
                                escalation_called = True
                        except (json.JSONDecodeError, TypeError):
                            pass

                    if getattr(block, "name", None) == "confirm_booking":
                        try:
                            result_data = json.loads(tool_result["content"])
                            if result_data.get("status") == "confirmed" and "error" not in result_data:
                                confirm_booking_succeeded = True
                                logger.info(
                                    "confirm_booking succeeded (booking_id=%s)",
                                    result_data.get("booking_id", pending_booking_id),
                                )
                        except (json.JSONDecodeError, TypeError):
                            pass

                    if getattr(block, "name", None) == "write_booking":
                        try:
                            result_data = json.loads(tool_result["content"])
                            if "booking_id" in result_data and "error" not in result_data:
                                booking_write_succeeded = True
                                logger.info(
                                    "write_booking succeeded (booking_id=%s)",
                                    result_data["booking_id"],
                                )
                                if _booking_reprompt_used:
                                    # Re-prompt triggered the recovery — log it
                                    await log_incident(
                                        provider="agent_guardrail",
                                        error_type="guardrail_reprompt_success",
                                        error_message=f"write_booking succeeded after re-prompt (booking_id={result_data['booking_id']}).",
                                        client_id=client_id,
                                    )
                        except (json.JSONDecodeError, TypeError):
                            pass

            # Append tool results as a user turn
            messages.append({
                "role": "user",
                "content": tool_results,
            })
            continue

        # Unknown stop reason — treat as end turn
        logger.warning(f"Unexpected stop_reason: {response.stop_reason!r} — treating as end_turn")
        final_text = _extract_text(response.content)
        os.environ["LLM_PROVIDER"] = _original_llm_provider
        return final_text or _FALLBACK_RESPONSE

    # Max iterations reached — return fallback
    logger.error(
        f"Agent hit MAX_TOOL_ITERATIONS ({MAX_TOOL_ITERATIONS}) — returning fallback"
    )
    os.environ["LLM_PROVIDER"] = _original_llm_provider
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
        logger.info(f"Executing tool: {tool_name!r} with input: {tool_input}")
        try:
            result = await tool_fn(**tool_input)
            content = json.dumps(result) if not isinstance(result, str) else result
            logger.info(f"Tool {tool_name!r} succeeded")
        except Exception as e:
            logger.error(f"Tool {tool_name!r} raised: {e}", exc_info=True)
            content = json.dumps({"error": "tool_execution_failed", "message": str(e)})

    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": content,
    }
