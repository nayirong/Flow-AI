"""
Pre-deploy / startup config validation for the Flow AI engine.

Runs at startup (called from engine.main) before the server begins accepting
traffic. Logs warnings for missing optional config and raises on missing
required config so Railway fails fast rather than serving broken requests.

Checks performed:
  1. Required env vars are present (SUPABASE_URL, SUPABASE_SERVICE_KEY)
  2. Shared Supabase DB is reachable (ping api_usage table)
  3. Per-client config in the clients table is reachable for active clients
  4. human_agent_number is set and does not match known test-number patterns
  5. LLM_PROVIDER is a known value
  6. Telegram alert credentials present if TELEGRAM_ALERT_CHAT_ID is set

All checks are logged. Non-fatal issues log WARNING; fatal issues log CRITICAL
and raise RuntimeError. The caller (main.py) decides whether to abort startup.

Telegram extension point
────────────────────────
When TELEGRAM_BOT_TOKEN + TELEGRAM_ALERT_CHAT_ID are configured, startup
validation failures are also sent to the Telegram alert chat so the team is
notified before any customer traffic arrives.
"""
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Phone numbers that should never be used as human_agent_number in production.
# Pattern: common test numbers seen during HeyAircon pilot (add more as needed).
_KNOWN_TEST_PHONE_PATTERN = re.compile(
    r"^(65829\d{5}|6582829071)$"  # extend with additional test ranges as needed
)

_REQUIRED_SHARED_ENV_VARS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
]

_KNOWN_LLM_PROVIDERS = {"anthropic", "openai", "github_models"}


async def validate_startup_config(abort_on_fatal: bool = True) -> list[dict]:
    """
    Run all startup config checks. Returns a list of issue dicts.

    Each issue dict: {level: "warning"|"critical", check: str, detail: str}

    Args:
        abort_on_fatal: If True (default), raises RuntimeError when any CRITICAL
                        issue is found. Set False in tests to inspect results.

    Returns:
        List of all issues found (warnings + criticals). Empty list = clean.

    Raises:
        RuntimeError: If abort_on_fatal=True and any critical check fails.
    """
    issues: list[dict] = []

    def _warn(check: str, detail: str) -> None:
        issues.append({"level": "warning", "check": check, "detail": detail})
        logger.warning("[startup_validator] WARNING | %s — %s", check, detail)

    def _critical(check: str, detail: str) -> None:
        issues.append({"level": "critical", "check": check, "detail": detail})
        logger.critical("[startup_validator] CRITICAL | %s — %s", check, detail)

    # ── Check 1: Required shared env vars ─────────────────────────────────────
    for var in _REQUIRED_SHARED_ENV_VARS:
        if not os.environ.get(var, "").strip():
            _critical(
                check="required_env_var",
                detail=f"{var} is not set or empty",
            )

    # ── Check 2: LLM_PROVIDER is a known value ────────────────────────────────
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider not in _KNOWN_LLM_PROVIDERS:
        _warn(
            check="llm_provider",
            detail=f"Unknown LLM_PROVIDER='{provider}'. Known values: {sorted(_KNOWN_LLM_PROVIDERS)}",
        )

    # ── Check 3: LLM_FALLBACK_ENABLED=true requires OPENAI_API_KEY ───────────
    fallback_enabled = os.environ.get("LLM_FALLBACK_ENABLED", "true").lower() != "false"
    if fallback_enabled and not os.environ.get("OPENAI_API_KEY", "").strip():
        _warn(
            check="openai_fallback_key",
            detail="LLM_FALLBACK_ENABLED=true but OPENAI_API_KEY is not set — fallback will fail",
        )

    # ── Check 4: Telegram alert config is complete ────────────────────────────
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "").strip()
    if bool(tg_token) != bool(tg_chat):
        _warn(
            check="telegram_config",
            detail=(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_ALERT_CHAT_ID must both be set "
                "or both be absent. Telegram alerts will be disabled."
            ),
        )

    # ── Check 5: Shared Supabase is reachable ─────────────────────────────────
    try:
        from engine.integrations.supabase_client import get_shared_db
        db = await get_shared_db()
        await db.table("api_usage").select("id").limit(1).execute()
        logger.info("[startup_validator] Shared Supabase reachable ✓")
    except Exception as e:
        _critical(
            check="shared_supabase_reachable",
            detail=f"Cannot connect to shared Supabase: {type(e).__name__}: {e}",
        )

    # ── Check 6: Per-client config validation (active clients in shared DB) ───
    try:
        from engine.integrations.supabase_client import get_shared_db
        db = await get_shared_db()
        result = await db.table("clients").select("*").eq("is_active", True).execute()
        clients = result.data or []
        if not clients:
            _warn(
                check="active_clients",
                detail="No active clients found in shared clients table",
            )
        for client in clients:
            client_id = client.get("client_id", "<unknown>")
            _validate_client_row(client, client_id, _warn, _critical)
    except Exception as e:
        _warn(
            check="client_config_fetch",
            detail=f"Could not fetch active clients from shared Supabase: {type(e).__name__}: {e}",
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    critical_issues = [i for i in issues if i["level"] == "critical"]
    warning_issues = [i for i in issues if i["level"] == "warning"]

    if not issues:
        logger.info("[startup_validator] All startup checks passed ✓")
    else:
        logger.info(
            "[startup_validator] Completed: %d critical, %d warning",
            len(critical_issues), len(warning_issues),
        )

    # Telegram summary (best-effort — non-blocking)
    if issues:
        try:
            from engine.integrations.observability import _send_telegram_alert
            lines = [f"🚨 *Flow AI startup validation*"]
            for issue in issues:
                icon = "🔴" if issue["level"] == "critical" else "⚠️"
                lines.append(f"{icon} `{issue['check']}`: {issue['detail']}")
            await _send_telegram_alert("\n".join(lines))
        except Exception:
            pass

    if abort_on_fatal and critical_issues:
        raise RuntimeError(
            f"Startup validation failed with {len(critical_issues)} critical issue(s). "
            "Check logs for details."
        )

    return issues


def _validate_client_row(
    client: dict,
    client_id: str,
    warn_fn,
    critical_fn,
) -> None:
    """Validate a single client row from the clients table."""

    # human_agent_number must be set
    human_number = (client.get("human_agent_number") or "").strip()
    if not human_number:
        warn_fn(
            check=f"client.{client_id}.human_agent_number",
            detail=f"Client '{client_id}' has no human_agent_number configured — escalation alerts will be silently dropped",
        )
    elif _KNOWN_TEST_PHONE_PATTERN.match(human_number):
        critical_fn(
            check=f"client.{client_id}.human_agent_number_test_number",
            detail=(
                f"Client '{client_id}' human_agent_number '{human_number}' matches a known test "
                "phone number. Escalation alerts will reach the test customer, not the human agent. "
                "Update the clients table in Supabase Studio immediately."
            ),
        )

    # meta_phone_number_id must be set
    if not (client.get("meta_phone_number_id") or "").strip():
        critical_fn(
            check=f"client.{client_id}.meta_phone_number_id",
            detail=f"Client '{client_id}' has no meta_phone_number_id — webhook cannot send messages",
        )

    # Google Sheets config: if enabled, spreadsheet_id is required
    if client.get("sheets_sync_enabled") and not (client.get("sheets_spreadsheet_id") or "").strip():
        warn_fn(
            check=f"client.{client_id}.sheets_spreadsheet_id",
            detail=f"Client '{client_id}' has sheets_sync_enabled=true but no sheets_spreadsheet_id",
        )
