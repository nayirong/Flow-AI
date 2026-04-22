"""
Flow AI Engine — application entrypoint.

This module:
1. Configures structured logging from settings.log_level.
2. Re-exports the FastAPI app so uvicorn can be pointed at engine.main:app.
3. Logs startup context (provider, model, log level) for observability.

Run locally:
    uvicorn engine.main:app --reload --port 8000

Run on Railway:
    uvicorn engine.main:app --host 0.0.0.0 --port $PORT --workers 1
"""
import logging
import os
import sys

# ── Logging configuration ─────────────────────────────────────────────────────
# Read LOG_LEVEL directly from env (not via settings proxy) so logging is
# configured before any settings import that could fail noisily at startup.

_log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_str, logging.INFO)

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

# ── Import the FastAPI app ────────────────────────────────────────────────────
# This import triggers the full module graph — settings, client_config, etc.
# Any missing required env var will raise here (at startup) rather than
# silently failing mid-request in production.

from engine.api.webhook import app  # noqa: E402 — must come after logging setup

# ── Startup validation ────────────────────────────────────────────────────────
# Run config checks before the server accepts traffic. Raises on critical issues
# (missing required env vars, test number in human_agent_number, Supabase down).

@app.on_event("startup")
async def _run_startup_validation() -> None:
    """Validate config at startup. Critical failures abort the service."""
    try:
        from engine.config.startup_validator import validate_startup_config
        await validate_startup_config(abort_on_fatal=True)
    except RuntimeError as e:
        logger.critical("Startup validation aborted: %s", e)
        raise  # Let Railway mark the deploy as failed

# Re-export for uvicorn: `uvicorn engine.main:app`
__all__ = ["app"]

# ── Startup log ───────────────────────────────────────────────────────────────

_provider = os.getenv("LLM_PROVIDER", "anthropic")
_model_override = os.getenv("LLM_MODEL_OVERRIDE", "")
_model_display = _model_override if _model_override else "(provider default)"

logger.info("Flow AI engine starting up")
logger.info(f"  LLM provider : {_provider}")
logger.info(f"  LLM model    : {_model_display}")
logger.info(f"  Log level    : {_log_level_str}")
