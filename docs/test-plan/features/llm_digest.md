# Test Plan: LLM Observability — Fallback Warning + Daily Digest

**Status:** Ready for Implementation
**Created:** 2026-04-22
**Feature source:** N/A (founder-specified scope, documented in dispatch brief)

---

## Scope

This test plan covers two shipped-together changes:

**Part 1 — Fallback Warning Alert**
- `engine/core/agent_runner.py` — add `log_noncritical_failure(source="llm_anthropic_fallback")` call after a successful OpenAI fallback
- `engine/integrations/observability.py` — add `"llm_anthropic_fallback"` action note to `_TIER2_ACTION_NOTES`

**Part 2 — Daily LLM Digest**
- `engine/core/daily_digest.py` — new file; queries Supabase, formats digest message, calls `_send_telegram_alert()`
- `engine/api/webhook.py` — APScheduler wired into FastAPI lifespan
- `engine/config/settings.py` — two new optional env var fields: `daily_digest_enabled`, `daily_digest_utc_hour`
- `engine/requirements.txt` — add `apscheduler>=3.10.0`

---

## Pre-Implementation Verification Findings (SDET)

Verified against codebase before dispatch:

1. **Fallback insertion point confirmed:** The successful-fallback `log_usage` call completes at `agent_runner.py` line 446–451. The `except Exception as fallback_err:` block starts at line 453. The `finally:` at line 480 restores the provider. The `log_noncritical_failure` call must be inserted between lines 451 and 453 — after the fallback `log_usage`, before the `except` that handles both-failed.

2. **`log_noncritical_failure` import path:** Currently not imported inside `run_agent`. The existing import line at line 366 reads `from engine.integrations.observability import log_incident, log_usage, extract_usage, send_telegram_alert`. The engineer must add `log_noncritical_failure` to this import.

3. **`_TIER2_ACTION_NOTES` dict:** Located in `engine/integrations/observability.py`. The existing `log_noncritical_failure` function currently uses a generic Tier 2 format string. The architect spec requires adding `"llm_anthropic_fallback"` as a key with its action note. The engineer must verify whether `_TIER2_ACTION_NOTES` already exists in the current file (as of the worktree baseline) or must be created. Given the current observability.py has a generic Telegram format, the engineer must introduce this dict and wire it into the `log_noncritical_failure` Telegram message formatter.

4. **`apscheduler` not in requirements.txt:** Confirmed absent. Engineer must add `apscheduler>=3.10.0` to `engine/requirements.txt`.

5. **FastAPI lifespan not yet present in `webhook.py`:** The current `webhook.py` has no `lifespan` context manager. The `app = FastAPI()` is a bare instantiation at line 22. The engineer must add the `lifespan` context manager and pass it to `FastAPI(lifespan=lifespan)`.

6. **`api_usage` schema:** Confirmed present. Has columns: `id`, `ts`, `provider`, `model`, `client_id`, `input_tokens`, `output_tokens`, `total_tokens`. No `conversation_id` column exists. The digest spec calls for "unique conversations count (distinct conversation_id in `api_usage`)" — this column does not exist in the current DDL. The engineer must use `distinct conversation_id` only if the column is added via migration, or omit that metric and substitute with `total_calls`. **Resolution: omit `conversation_id` metric from digest; use total unique `client_id` values as a proxy. No schema migration needed.**

7. **Haiku 4.5 pricing constants:** input `$0.80/1M`, output `$4.00/1M`. These must be defined as named constants, not inline magic numbers, in `daily_digest.py`.

8. **`settings` proxy object:** `engine/config/settings.py` uses a lazy `_SettingsProxy` class. New fields added to `Settings` are accessible via `settings.daily_digest_enabled` and `settings.daily_digest_utc_hour` through the proxy without any changes to the proxy class. Fields declared with defaults do not require the env var to be set.

---

## Test File Locations

- `engine/tests/unit/test_agent_runner.py` — additions to existing file
- `engine/tests/unit/test_daily_digest.py` — new file

---

## Test Suite: `engine/tests/unit/test_agent_runner.py` (additions)

### TC-AR-FB-01: Successful fallback fires `log_noncritical_failure`

**What it verifies:** When Anthropic fails with a retryable error and OpenAI fallback succeeds, `log_noncritical_failure(source="llm_anthropic_fallback")` is called exactly once before the loop continues.

**Setup:**
- Set env vars: `LLM_PROVIDER=anthropic`, `LLM_FALLBACK_ENABLED=true`, `OPENAI_API_KEY=test-key`.
- Patch `engine.core.agent_runner._call_llm` as `AsyncMock` with `side_effect`:
  - First call raises a class that has `"APIConnectionError"` in its MRO name (simulate Anthropic failure).
  - Second call (fallback) returns an `end_turn` response successfully.
- Patch `engine.core.agent_runner._get_llm_client` to return a `MagicMock`.
- Patch `engine.core.agent_runner._get_openai_fallback_client` to return a `MagicMock`.
- Patch `engine.core.agent_runner.log_noncritical_failure` as `AsyncMock`.
- Patch `engine.core.agent_runner.log_incident` as `AsyncMock`.
- Patch `engine.core.agent_runner.log_usage` as `AsyncMock`.
- Patch `engine.core.agent_runner.extract_usage` to return `(10, 5)`.

**Steps:**
1. Call `run_agent(system_message="Sys.", conversation_history=[], current_message="Hi.", tool_definitions=[], tool_dispatch={})`.
2. Assert the return value is the fallback response text (not `_FALLBACK_RESPONSE`).
3. Assert `log_noncritical_failure` was called exactly once.
4. Assert `log_noncritical_failure` was called with `source="llm_anthropic_fallback"`.
5. Assert `log_noncritical_failure` was called with `client_id` matching the value passed to `run_agent`.
6. Assert `log_noncritical_failure` context contains `"fallback_to": "OpenAI (gpt-4o-mini)"`.

**Pass criteria:** `log_noncritical_failure` fires once with correct arguments. Run completes successfully.

---

### TC-AR-FB-02: `log_noncritical_failure` exception on fallback path does not crash the loop

**What it verifies:** If `log_noncritical_failure` itself raises, the loop continues normally and the customer receives the fallback response.

**Setup:** Same as TC-AR-FB-01, but `log_noncritical_failure` raises `Exception("observability down")`.

**Steps:**
1. Call `run_agent(...)`.
2. Assert the return value is the agent response text (not `_FALLBACK_RESPONSE`).
3. Assert no exception propagated to the caller.

**Pass criteria:** Exception in `log_noncritical_failure` is swallowed. Customer served normally.

---

### TC-AR-FB-03: Both LLMs fail — `log_noncritical_failure` is NOT called (only both-failed path)

**What it verifies:** When Anthropic fails and OpenAI fallback also fails, `log_noncritical_failure(source="llm_anthropic_fallback")` is NOT called — only the existing `send_telegram_alert(source="llm_both_failed")` fires.

**Setup:**
- Patch `_call_llm` to raise on first call (Anthropic failure).
- Patch `_get_openai_fallback_client` to return a mock client whose call also raises.
- Patch `log_noncritical_failure` as `AsyncMock`.
- Patch `send_telegram_alert` as `AsyncMock`.
- Patch `log_incident` as `AsyncMock`.

**Steps:**
1. Call `run_agent(...)`.
2. Assert return value is `_FALLBACK_RESPONSE`.
3. Assert `log_noncritical_failure` was NOT called.
4. Assert `send_telegram_alert` was called (both-failed path).

**Pass criteria:** `log_noncritical_failure` absent from both-failed path. `send_telegram_alert` fires as before.

---

### TC-AR-FB-04: Non-retryable error — `log_noncritical_failure` not called

**What it verifies:** When `_call_llm` raises a generic `ValueError` (not an Anthropic API error), the fallback branch is NOT entered and `log_noncritical_failure` is NOT called.

**Setup:**
- Patch `_call_llm` to raise `ValueError("bad request")` — this class has no `APIConnectionError` in its MRO.
- Patch `log_noncritical_failure` as `AsyncMock`.

**Steps:**
1. Call `run_agent(...)` and expect `ValueError` to propagate.
2. Assert `log_noncritical_failure` was NOT called.

**Pass criteria:** Non-retryable errors bypass the fallback path entirely.

---

## Test Suite: `engine/tests/unit/test_daily_digest.py` (new file)

### TC-DD-01: Digest sends when data exists

**What it verifies:** When `api_usage`, `api_incidents`, and `noncritical_failures` return rows, `send_daily_digest()` calls `_send_telegram_alert()` exactly once with a non-empty message.

**Setup:**
- Patch `engine.core.daily_digest.get_shared_db` to return a chainable mock that returns:
  - `api_usage` query: three rows — `[{"provider": "anthropic", "input_tokens": 100, "output_tokens": 50, "client_id": "hey-aircon"}, {"provider": "openai", "input_tokens": 200, "output_tokens": 80, "client_id": "hey-aircon"}, {"provider": "anthropic", "input_tokens": 50, "output_tokens": 20, "client_id": "demo-client"}]`
  - `api_incidents` query (both_failed): one row — `[{"provider": "anthropic", "error_type": "APIConnectionError"}]`
  - `api_incidents` query (anthropic errors): one row — `[{"error_type": "APIConnectionError"}]`
  - `noncritical_failures` query: one row — `[{"source": "llm_anthropic_fallback"}]`
- Patch `engine.core.daily_digest._send_telegram_alert` as `AsyncMock`.

**Steps:**
1. Call `await send_daily_digest()`.
2. Assert `_send_telegram_alert` was called exactly once.
3. Assert the message argument is a non-empty string.
4. Assert message contains `"Total LLM calls"` or equivalent header text.
5. Assert message contains `"anthropic"` (provider breakdown present).
6. Assert message contains `"openai"` (fallback provider present).
7. Assert message contains `"hey-aircon"` (per-client cost present).

**Pass criteria:** Digest sent with data-populated content.

---

### TC-DD-02: Digest sends "quiet day" message when no calls in last 24h

**What it verifies:** When all queries return empty lists, `_send_telegram_alert` is still called once with a "quiet day" message rather than being skipped.

**Setup:**
- Patch `get_shared_db` to return empty lists for all queries.
- Patch `_send_telegram_alert` as `AsyncMock`.

**Steps:**
1. Call `await send_daily_digest()`.
2. Assert `_send_telegram_alert` was called exactly once.
3. Assert the message contains text indicating no activity (e.g., "quiet", "no calls", "0 calls").

**Pass criteria:** Telegram called even on zero-activity day. Message signals quiet status.

---

### TC-DD-03: Cost estimate correct for known token counts

**What it verifies:** The per-client cost calculation matches the Haiku 4.5 pricing exactly.

**Pricing constants:** input `$0.80/1M tokens`, output `$4.00/1M tokens`

**Setup:**
- Construct a known set of usage rows for client `"hey-aircon"`:
  - Row 1: `provider=anthropic`, `input_tokens=1_000_000`, `output_tokens=0` → expected cost `$0.80`
  - Row 2: `provider=anthropic`, `input_tokens=0`, `output_tokens=1_000_000` → expected cost `$4.00`
  - Combined expected: `$4.80`
- Patch `get_shared_db` to return these rows for the `api_usage` query, empty for all others.
- Patch `_send_telegram_alert` to capture the message.

**Steps:**
1. Call `await send_daily_digest()`.
2. Capture the message string.
3. Assert the message contains `"4.80"` or `"$4.80"` for `"hey-aircon"`.

**Pass criteria:** Computed cost equals `$4.80` for the known token counts.

---

### TC-DD-04: Supabase failure on usage query does not raise — sends error-state digest

**What it verifies:** If `get_shared_db()` raises (or `.execute()` raises), `send_daily_digest()` does not propagate the exception. It still calls `_send_telegram_alert` with either a partial message or an error notice.

**Setup:**
- Patch `get_shared_db` to raise `Exception("Supabase unreachable")`.
- Patch `_send_telegram_alert` as `AsyncMock`.

**Steps:**
1. Call `await send_daily_digest()`.
2. Assert no exception was raised by `send_daily_digest()`.
3. Assert `_send_telegram_alert` was called (even if just with an error message).

**Pass criteria:** No exception propagates. Telegram is called.

---

### TC-DD-05: Fallback rate calculation correct

**What it verifies:** The fallback rate percentage is computed as `(openai_calls / total_calls) * 100`.

**Setup:**
- Patch `get_shared_db` to return 3 anthropic rows and 1 openai row (4 total).
- Patch `_send_telegram_alert` to capture the message.

**Steps:**
1. Call `await send_daily_digest()`.
2. Assert message contains `"25"` (as in "25%" fallback rate) or equivalent representation.

**Pass criteria:** Fallback rate shows `25%` for 1 of 4 calls being OpenAI.

---

### TC-DD-06: Anthropic error type breakdown present in digest

**What it verifies:** When Anthropic incidents exist, the digest includes a per-error-type breakdown.

**Setup:**
- Patch `get_shared_db` to return two `api_incidents` rows for Anthropic:
  - `[{"error_type": "APIConnectionError"}, {"error_type": "APIStatusError"}]`
- Patch `_send_telegram_alert` to capture message.

**Steps:**
1. Call `await send_daily_digest()`.
2. Assert message contains `"APIConnectionError"`.
3. Assert message contains `"APIStatusError"`.

**Pass criteria:** Error type breakdown appears in message.

---

### TC-DD-07: Non-critical failure count by source appears in digest

**What it verifies:** `noncritical_failures` rows are grouped by source and counts appear in the digest.

**Setup:**
- Patch `get_shared_db` to return `noncritical_failures`:
  - `[{"source": "llm_anthropic_fallback"}, {"source": "llm_anthropic_fallback"}, {"source": "escalation_human_alert"}]`
- Patch `_send_telegram_alert` to capture message.

**Steps:**
1. Call `await send_daily_digest()`.
2. Assert message contains `"llm_anthropic_fallback"`.
3. Assert message contains `"escalation_human_alert"`.

**Pass criteria:** Both sources appear in digest with their counts.

---

## Test Suite: Scheduler Wiring (manual verification)

### TC-SCHED-01: Scheduler starts when `DAILY_DIGEST_ENABLED=true`

**What it verifies:** On FastAPI startup, when `DAILY_DIGEST_ENABLED=true`, APScheduler starts and a cron job is registered for `daily_digest_utc_hour`.

**Verification:** Manual — start the engine locally with `DAILY_DIGEST_ENABLED=true` and confirm startup log shows scheduler started. Cannot be automated without a live event loop running for >24h.

---

### TC-SCHED-02: Scheduler does not start when `DAILY_DIGEST_ENABLED=false`

**What it verifies:** When `DAILY_DIGEST_ENABLED=false`, no scheduler is started and no `apscheduler` import path is exercised.

**Verification:** Set env var, start engine, confirm no APScheduler log lines in startup output.

---

### TC-SCHED-03: `daily_digest_utc_hour` controls job schedule hour

**What it verifies:** Setting `DAILY_DIGEST_UTC_HOUR=8` registers the cron job with `hour=8`.

**Verification:** Inspect scheduler's registered jobs after startup. Assert job `hour` matches the env var value.

---

## Settings Test: `engine/tests/unit/test_settings.py` (additions)

### TC-SET-01: Default values for digest settings

**What it verifies:** `daily_digest_enabled` defaults to `True` and `daily_digest_utc_hour` defaults to `0` when env vars are absent.

**Setup:**
- Clear `DAILY_DIGEST_ENABLED` and `DAILY_DIGEST_UTC_HOUR` from environment.
- Instantiate `Settings()` directly (not via proxy).

**Steps:**
1. Assert `settings_instance.daily_digest_enabled is True`.
2. Assert `settings_instance.daily_digest_utc_hour == 0`.

**Pass criteria:** Both defaults hold when env vars are absent.

---

### TC-SET-02: Env var overrides work

**What it verifies:** Setting `DAILY_DIGEST_ENABLED=false` and `DAILY_DIGEST_UTC_HOUR=8` propagates into the settings object.

**Setup:**
- Set env vars before instantiating `Settings()`.

**Steps:**
1. Assert `settings_instance.daily_digest_enabled is False`.
2. Assert `settings_instance.daily_digest_utc_hour == 8`.

**Pass criteria:** Env var values override defaults.

---

## Integration Smoke Test

### TC-INT-01: Digest delivers to Telegram (real endpoint)

**Classification:** Integration boundary test (mandatory gate before merge approval).

**What it verifies:** `send_daily_digest()` completes without error and a message appears in the configured Telegram chat when real credentials are set.

**Requires:** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALERT_CHAT_ID` set in local environment.

**File:** `engine/tests/integration/test_digest_smoke.py` (new file, guarded by `pytest.mark.integration`).

**Steps:**
1. If either env var is absent, `pytest.skip("TELEGRAM credentials not set")`.
2. Patch Supabase to return minimal non-empty data (avoid production DB dependency).
3. Call `await send_daily_digest()`.
4. Assert function returns without exception.
5. Manually confirm message appeared in Telegram chat.

**Pass criteria:** No exception. Message visible in Telegram.

**Blocking gate:** This test must pass before merge. Hold worktree open if Telegram credentials are unavailable.

---

## Acceptance Criteria Summary

| ID | Criteria | Verified by |
|---|---|---|
| AC-1 | Successful Anthropic fallback fires `log_noncritical_failure(source="llm_anthropic_fallback")` | TC-AR-FB-01 |
| AC-2 | `log_noncritical_failure` exception on fallback path does not crash loop | TC-AR-FB-02 |
| AC-3 | Both-failed path does NOT fire `log_noncritical_fallback` | TC-AR-FB-03 |
| AC-4 | Non-retryable error bypasses fallback path | TC-AR-FB-04 |
| AC-5 | Digest sends when data exists, includes all required sections | TC-DD-01 |
| AC-6 | Digest sends "quiet day" message when no data | TC-DD-02 |
| AC-7 | Cost estimate matches Haiku 4.5 pricing for known token counts | TC-DD-03 |
| AC-8 | Supabase failure does not raise from `send_daily_digest()` | TC-DD-04 |
| AC-9 | Fallback rate computed correctly | TC-DD-05 |
| AC-10 | Anthropic error type breakdown in digest | TC-DD-06 |
| AC-11 | Non-critical failure count by source in digest | TC-DD-07 |
| AC-12 | Scheduler starts when enabled, skipped when disabled | TC-SCHED-01, TC-SCHED-02 |
| AC-13 | `daily_digest_utc_hour` controls cron hour | TC-SCHED-03 |
| AC-14 | Settings defaults correct | TC-SET-01 |
| AC-15 | Settings env var overrides work | TC-SET-02 |
| AC-16 | Real Telegram delivery confirmed | TC-INT-01 |
| AC-17 | `apscheduler` added to `engine/requirements.txt` | Code review |
| AC-18 | `conversation_id` metric omitted (column does not exist in schema) | Code review |
| AC-19 | Haiku pricing constants named (not inline magic numbers) | Code review |

---

## Out of Scope

- Digest delivery to multiple Telegram chats or per-client channels
- Digest persistence or history (digest is fire-and-forget)
- Alert deduplication for the fallback warning (each fallback event fires independently)
- Conversation-level tracking (no `conversation_id` column in `api_usage` — not added by this feature)
- Schema migrations (no new tables required)
