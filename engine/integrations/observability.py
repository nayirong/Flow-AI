"""
Observability — LLM provider incident logging, usage tracking, and non-critical failure logging.

Writes to tables in the shared Flow AI Supabase (not per-client):
  - api_incidents:        one row per provider failure (outage detection, frequency)
  - api_usage:            one row per successful LLM call (token usage, cost tracking)
  - noncritical_failures: one row per non-critical integration failure (Sheets sync,
                          human-agent alerts, config mismatches). Eventually routed
                          to a Telegram group chat via bot.

DDL (run once in shared Supabase):

    CREATE TABLE api_incidents (
        id            BIGSERIAL PRIMARY KEY,
        ts            TIMESTAMPTZ DEFAULT NOW(),
        provider      TEXT NOT NULL,           -- 'anthropic' | 'openai'
        error_type    TEXT NOT NULL,           -- e.g. 'APIConnectionError'
        error_message TEXT,
        client_id     TEXT,
        fallback_used BOOLEAN DEFAULT FALSE,   -- TRUE if other provider succeeded
        both_failed   BOOLEAN DEFAULT FALSE    -- TRUE if both providers failed
    );

    CREATE TABLE api_usage (
        id              BIGSERIAL PRIMARY KEY,
        ts              TIMESTAMPTZ DEFAULT NOW(),
        provider        TEXT NOT NULL,         -- 'anthropic' | 'openai'
        model           TEXT NOT NULL,
        client_id       TEXT,
        input_tokens    INT,
        output_tokens   INT,
        total_tokens    INT
    );

    CREATE TABLE noncritical_failures (
        id            BIGSERIAL PRIMARY KEY,
        ts            TIMESTAMPTZ DEFAULT NOW(),
        source        TEXT NOT NULL,           -- e.g. 'sheets_sync_customer', 'escalation_human_alert'
        error_type    TEXT NOT NULL,           -- Exception class name
        error_message TEXT,
        client_id     TEXT,
        context       JSONB                    -- arbitrary key-value context (phone_number, row_id, etc.)
    );

    CREATE INDEX ON api_incidents (ts DESC);
    CREATE INDEX ON api_incidents (provider, ts DESC);
    CREATE INDEX ON api_usage (provider, ts DESC);
    CREATE INDEX ON api_usage (client_id, ts DESC);
    CREATE INDEX ON noncritical_failures (ts DESC);
    CREATE INDEX ON noncritical_failures (client_id, ts DESC);
    CREATE INDEX ON noncritical_failures (source, ts DESC);

Telegram bot extension point
─────────────────────────────
When you're ready to route non-critical failures to a Telegram group chat, add
a call to `_send_telegram_alert()` inside `log_noncritical_failure()` after the
Supabase insert. The function signature is prepared below (no-op stub until wired).
Required env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_ALERT_CHAT_ID.
"""
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Telegram extension point (no-op until wired) ──────────────────────────────

async def _send_telegram_alert(message: str) -> None:
    """
    Send an alert message to the configured Telegram group chat.

    No-op stub — activate by setting TELEGRAM_BOT_TOKEN and TELEGRAM_ALERT_CHAT_ID
    env vars. When both are present, sends via the Telegram Bot API.
    Never raises.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
    if not bot_token or not chat_id:
        return  # Not yet configured — silent no-op
    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            })
    except Exception as e:
        logger.warning("Telegram alert failed (non-critical): %s", e)


async def log_incident(
    provider: str,
    error_type: str,
    error_message: str,
    client_id: str = "",
    fallback_used: bool = False,
    both_failed: bool = False,
) -> None:
    """
    Log a provider failure to api_incidents in the shared Supabase.

    Non-blocking — failures are logged but never raise.

    Args:
        provider:      'anthropic' or 'openai'
        error_type:    Exception class name (e.g. 'APIConnectionError')
        error_message: str(exception)
        client_id:     Which client's conversation triggered this
        fallback_used: True if the other provider succeeded after this failure
        both_failed:   True if both Anthropic and OpenAI both failed
    """
    try:
        from engine.integrations.supabase_client import get_shared_db
        db = await get_shared_db()
        await db.table("api_incidents").insert({
            "provider": provider,
            "error_type": error_type,
            "error_message": str(error_message)[:500],
            "client_id": client_id or None,
            "fallback_used": fallback_used,
            "both_failed": both_failed,
        }).execute()
        logger.debug("Incident logged: provider=%s error=%s", provider, error_type)
    except Exception as e:
        # Observability must never crash the agent
        logger.error("Failed to log incident to Supabase: %s", e)


async def log_usage(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    client_id: str = "",
) -> None:
    """
    Log token usage to api_usage in the shared Supabase.

    Non-blocking — failures are logged but never raise.

    Args:
        provider:      'anthropic' or 'openai'
        model:         Model identifier string
        input_tokens:  Prompt token count
        output_tokens: Completion token count
        client_id:     Which client's conversation this belongs to
    """
    try:
        from engine.integrations.supabase_client import get_shared_db
        db = await get_shared_db()
        await db.table("api_usage").insert({
            "provider": provider,
            "model": model,
            "client_id": client_id or None,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }).execute()
        logger.debug(
            "Usage logged: provider=%s model=%s in=%d out=%d",
            provider, model, input_tokens, output_tokens,
        )
    except Exception as e:
        logger.error("Failed to log usage to Supabase: %s", e)


def extract_usage(response: Any, provider: str) -> tuple[int, int]:
    """
    Extract (input_tokens, output_tokens) from a provider response object.

    Returns (0, 0) if usage data unavailable — non-fatal.
    """
    try:
        if provider == "anthropic":
            usage = response.usage
            return usage.input_tokens, usage.output_tokens
        else:
            # OpenAI / GitHub Models
            usage = response.usage
            return usage.prompt_tokens, usage.completion_tokens
    except Exception:
        return 0, 0


async def log_noncritical_failure(
    source: str,
    error_type: str,
    error_message: str,
    client_id: str = "",
    context: Optional[dict] = None,
) -> None:
    """
    Log a non-critical integration failure to the shared Supabase.

    Non-critical = failure that does NOT prevent the customer from completing
    their booking. Examples: Sheets sync failure, failed human-agent WhatsApp
    alert (non-booking), config warning.

    Critical failures (booking write or calendar event failure) use
    _alert_booking_failure() in booking_tools.py instead.

    Also fires a Telegram alert if TELEGRAM_BOT_TOKEN + TELEGRAM_ALERT_CHAT_ID
    are configured (no-op until then).

    Never raises.

    Args:
        source:        Short identifier for where the failure occurred.
                       e.g. "sheets_sync_customer", "escalation_human_alert",
                            "escalation_sheets_sync", "pre_deploy_config"
        error_type:    Exception class name (e.g. "ConnectionError")
        error_message: str(exception) — truncated to 500 chars
        client_id:     Client slug this failure is associated with
        context:       Optional dict of extra diagnostic keys (phone_number, row_id, etc.)
    """
    try:
        from engine.integrations.supabase_client import get_shared_db
        db = await get_shared_db()
        await db.table("noncritical_failures").insert({
            "source": source,
            "error_type": error_type,
            "error_message": str(error_message)[:500],
            "client_id": client_id or None,
            "context": context or {},
        }).execute()
        logger.debug(
            "Non-critical failure logged: source=%s error=%s client=%s",
            source, error_type, client_id,
        )
    except Exception as e:
        # Observability must never crash the caller — fall back to local log only
        logger.error(
            "Failed to log non-critical failure to Supabase "
            "(source=%s error=%s): %s", source, error_type, e,
        )

    # Telegram alert (no-op until TELEGRAM_BOT_TOKEN + TELEGRAM_ALERT_CHAT_ID are set)
    try:
        alert_text = (
            f"⚠️ *Non-critical failure* | `{source}`\n"
            f"Client: `{client_id or 'unknown'}`\n"
            f"Error: `{error_type}` — {str(error_message)[:200]}"
        )
        await _send_telegram_alert(alert_text)
    except Exception:
        pass  # Telegram path must never propagate
