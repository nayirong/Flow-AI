UPDATE clients SET
  sheets_sync_enabled = TRUE,
  sheets_spreadsheet_id = '<your-spreadsheet-id>',
  sheets_service_account_creds = (
    SELECT google_calendar_creds FROM clients WHERE client_id = 'hey-aircon'
  )
WHERE client_id = 'hey-aircon';"""
Observability — LLM provider incident logging and usage tracking.

Writes to two tables in the shared Flow AI Supabase (not per-client):
  - api_incidents: one row per provider failure (outage detection, frequency)
  - api_usage:     one row per successful LLM call (token usage, cost tracking)

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

    CREATE INDEX ON api_incidents (ts DESC);
    CREATE INDEX ON api_incidents (provider, ts DESC);
    CREATE INDEX ON api_usage (provider, ts DESC);
    CREATE INDEX ON api_usage (client_id, ts DESC);
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


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
