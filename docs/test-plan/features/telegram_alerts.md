# Test Plan: Internal Telegram Alert Bot

**Status:** Ready for Implementation
**Created:** 2026-04-22
**Feature source:** `docs/requirements/telegram_alerts.md`
**Architecture source:** `docs/architecture/telegram_alerts.md`

---

## Scope

This test plan covers the complete Telegram alerting pipeline:

- `engine/integrations/observability.py` — `_send_telegram_alert()` real implementation, `send_telegram_alert()` new public function, `log_incident()` signature extension, `log_noncritical_failure()` format upgrade
- `engine/core/tools/booking_tools.py` — calendar write failure Tier 1, booking INSERT failure Tier 1, `sync_booking_to_sheets` and `sync_customer_to_sheets` safe wrappers
- `engine/core/message_handler.py` — customer query failure Tier 1, `sync_customer_to_sheets` safe wrappers at both call sites
- `engine/core/agent_runner.py` — LLM both-failed Tier 1
- `supabase/migrations/005_observability_tables.sql` — idempotent DDL

Zero changes to `escalation_tool.py`, customer-facing messages, or agent tool definitions.

---

## Pre-Implementation Verification Findings (SDET)

These were verified against the codebase before dispatch:

1. **`api_incidents`, `api_usage`, `noncritical_failures` tables:** Referenced only in `observability.py` DDL comments and `engine/config/startup_validator.py` (which pings `api_usage` for a health check). No engine code writes to these tables outside of `observability.py` functions. The migration is the correct first step.

2. **`both_failed=True` call sites:** Exactly one location — `agent_runner.py` line 456 inside the `except Exception as fallback_err:` block. No additional call sites exist that would also need the `send_telegram_alert()` addition.

3. **`create_task(sync_*_to_sheets(...))` call sites — full inventory:**
   - `message_handler.py` lines 215 and 234 — both `sync_customer_to_sheets` — covered by spec Section 5b
   - `booking_tools.py` line 231 — `sync_booking_to_sheets` — covered by spec Section 4c
   - `booking_tools.py` line 276 — `sync_customer_to_sheets` (Step 3, post-booking customer refresh) — covered by spec Section 4c
   - `escalation_tool.py` line 87 — `sync_customer_to_sheets` — **already has a `try/except` that calls `log_noncritical_failure(source="escalation_sheets_sync")`** at the outer level; however the bare `create_task` inside the try block still silently drops task-internal exceptions. The architecture spec classifies `escalation_tool.py` as zero-changes. The engineer must NOT touch `escalation_tool.py`.
   - `reset_handler.py` line 193 — `sync_customer_to_sheets` — only logs a `logger.warning` on failure, does NOT call `log_noncritical_failure()`. Architecture spec does not mention this call site. It is out of scope for this feature — do not change `reset_handler.py`.

4. **`httpx` availability:** Already imported in the `_send_telegram_alert()` stub body. Confirm it is in `requirements.txt` before the engineer proceeds.

5. **Settings fields:** `telegram_bot_token` and `telegram_alert_chat_id` are already present in `engine/config/settings.py` as optional fields. No settings changes required.

---

## Test File Location

All new tests live in: `engine/tests/unit/test_observability.py`

This file does not yet exist. The engineer creates it.

---

## Test Suite: `engine/tests/unit/test_observability.py`

### TC-OBS-01: `_send_telegram_alert()` — sends correct HTTP POST when vars set

**What it verifies:** The function issues one `POST` to `https://api.telegram.org/bot{token}/sendMessage` with the correct JSON body when both env vars are configured.

**Setup:**
- Patch `engine.integrations.observability.settings` so that `settings.telegram_bot_token = "test-bot-token"` and `settings.telegram_alert_chat_id = "-100123456"`.
- Mock `httpx.AsyncClient` to capture the `post()` call without making a real HTTP request.

**Steps:**
1. Call `await _send_telegram_alert("Test alert message")`.
2. Assert `httpx.AsyncClient.__aenter__` was invoked (context manager entered).
3. Assert `post` was called exactly once.
4. Assert `post` was called with URL `"https://api.telegram.org/bottest-bot-token/sendMessage"`.
5. Assert the `json` argument to `post` equals:
   ```python
   {
       "chat_id": "-100123456",
       "text": "Test alert message",
       "parse_mode": "Markdown",
       "disable_web_page_preview": True,
   }
   ```

**Pass criteria:** All assertions pass. No exception raised.

---

### TC-OBS-02: `_send_telegram_alert()` — silent no-op when token unset

**What it verifies:** Function returns immediately without touching httpx when `TELEGRAM_BOT_TOKEN` is None.

**Setup:**
- Patch settings so `settings.telegram_bot_token = None` and `settings.telegram_alert_chat_id = "-100123456"`.
- Patch `httpx.AsyncClient` to detect any call.

**Steps:**
1. Call `await _send_telegram_alert("Should not send")`.
2. Assert `httpx.AsyncClient` was NOT called.

**Pass criteria:** httpx is untouched. No exception raised.

---

### TC-OBS-03: `_send_telegram_alert()` — silent no-op when chat ID unset

**What it verifies:** Function returns immediately when `TELEGRAM_ALERT_CHAT_ID` is None.

**Setup:**
- Patch settings so `settings.telegram_bot_token = "test-bot-token"` and `settings.telegram_alert_chat_id = None`.

**Steps:** Same as TC-OBS-02.

**Pass criteria:** httpx is untouched. No exception raised.

---

### TC-OBS-04: `_send_telegram_alert()` — HTTP failure logged at WARNING, never raises

**What it verifies:** A network error is caught and logged; the caller never receives an exception.

**Setup:**
- Patch settings with valid token and chat ID.
- Mock `httpx.AsyncClient.post` to raise `httpx.ConnectError("connection refused")`.
- Capture log output using `pytest`'s `caplog` fixture.

**Steps:**
1. Call `await _send_telegram_alert("Alert")`.
2. Assert no exception was raised.
3. Assert a `WARNING`-level log message was emitted containing the error.

**Pass criteria:** No exception. At least one WARNING log containing the error text.

---

### TC-OBS-05: `send_telegram_alert()` — Tier 1 message format (calendar write failure)

**What it verifies:** The public function formats a Tier 1 message correctly and calls `_send_telegram_alert()` with the exact canonical format.

**Setup:**
- Patch `engine.integrations.observability._send_telegram_alert` with an `AsyncMock` to capture the message string.

**Steps:**
1. Call:
   ```python
   await send_telegram_alert(
       title="Booking Backend Failure",
       source="calendar_write_failure",
       client_id="hey-aircon",
       error_type="GoogleAPIError",
       error_message="404 calendar not found",
       context={"customer_phone": "6591234567", "booking_id": "HA-20260430-A3F2"},
       action_note="Calendar event was NOT created. Booking NOT recorded.\nManual booking required — customer has been told to expect a callback.",
   )
   ```
2. Capture the `message` argument passed to `_send_telegram_alert`.
3. Assert the message starts with `"CRITICAL | Booking Backend Failure"`.
4. Assert the message contains `"Client: hey-aircon"`.
5. Assert the message contains `` "Source: `calendar_write_failure`" ``.
6. Assert the message contains `"Error: GoogleAPIError — 404 calendar not found"`.
7. Assert the message contains `"Customer: 6591234567"`.
8. Assert the message contains `"Booking: HA-20260430-A3F2"`.
9. Assert the message contains `"Calendar event was NOT created."`.
10. Assert the message does NOT contain any customer name or address.

**Pass criteria:** All format assertions pass.

---

### TC-OBS-06: `send_telegram_alert()` — context keys absent are not rendered

**What it verifies:** Keys missing from the context dict produce no blank lines or placeholder lines in the output.

**Setup:** Same patch as TC-OBS-05.

**Steps:**
1. Call `send_telegram_alert` with `context={"providers_failed": "Anthropic + OpenAI"}` (no `customer_phone`, `booking_id`, `calendar_event_id`).
2. Assert message contains `"Providers failed: Anthropic + OpenAI"`.
3. Assert message does NOT contain `"Customer:"`.
4. Assert message does NOT contain `"Booking:"`.
5. Assert message does NOT contain `"Calendar Event:"`.

**Pass criteria:** Output contains only the keys present in context.

---

### TC-OBS-07: `send_telegram_alert()` — error message truncated at 200 chars

**What it verifies:** Long error messages are truncated to 200 characters in the formatted output.

**Setup:** Patch `_send_telegram_alert`.

**Steps:**
1. Call `send_telegram_alert` with `error_message="x" * 300`.
2. Assert the captured message contains `"x" * 200` but NOT `"x" * 201` after `"Error: "`.

**Pass criteria:** Error message in Telegram output is at most 200 characters.

---

### TC-OBS-08: `send_telegram_alert()` — `client_id` None renders as `unknown`

**What it verifies:** Empty/None client_id falls back to `"unknown"` in the formatted output.

**Setup:** Patch `_send_telegram_alert`.

**Steps:**
1. Call `send_telegram_alert` with `client_id=""` (or `None`).
2. Assert the message contains `"Client: unknown"`.

**Pass criteria:** `"Client: unknown"` present in formatted output.

---

### TC-OBS-09: `log_incident()` — includes `source` and `context` in Supabase insert when provided

**What it verifies:** The extended `log_incident()` passes `source` and `context` to the Supabase insert dict when non-None.

**Setup:**
- Mock `get_shared_db` to return a chainable mock that captures the dict passed to `.insert()`.

**Steps:**
1. Call:
   ```python
   await log_incident(
       provider="engine",
       error_type="RuntimeError",
       error_message="test error",
       client_id="hey-aircon",
       source="calendar_write_failure",
       context={"booking_id": "HA-001", "customer_phone": "6591234567"},
   )
   ```
2. Capture the dict passed to `.insert()`.
3. Assert `row["source"] == "calendar_write_failure"`.
4. Assert `row["context"] == {"booking_id": "HA-001", "customer_phone": "6591234567"}`.

**Pass criteria:** `source` and `context` present in insert dict.

---

### TC-OBS-10: `log_incident()` — `source` and `context` absent from insert when None

**What it verifies:** Backward-compatibility — existing callers that pass no `source`/`context` are unaffected.

**Setup:** Same mock as TC-OBS-09.

**Steps:**
1. Call `log_incident(provider="anthropic", error_type="APIConnectionError", error_message="err", client_id="hey-aircon")`.
2. Capture insert dict.
3. Assert `"source"` key is NOT in the dict.
4. Assert `"context"` key is NOT in the dict.

**Pass criteria:** Keys absent when not supplied.

---

### TC-OBS-11: `log_noncritical_failure()` — uses Tier 2 canonical format in Telegram alert

**What it verifies:** The Telegram message generated by `log_noncritical_failure()` matches the Tier 2 canonical format (not the legacy emoji format).

**Setup:**
- Patch `_send_telegram_alert` to capture the message.
- Mock `get_shared_db` so the Supabase insert succeeds.

**Steps:**
1. Call:
   ```python
   await log_noncritical_failure(
       source="escalation_human_alert",
       error_type="HTTPStatusError",
       error_message="400 bad request",
       client_id="hey-aircon",
       context={"phone_number": "6591234567"},
   )
   ```
2. Assert the captured message starts with `"WARNING | Non-critical Failure"`.
3. Assert message does NOT start with `"⚠️"` (legacy format must be replaced).
4. Assert message contains `"Client: hey-aircon"`.
5. Assert message contains `` "Source: `escalation_human_alert`" ``.
6. Assert message contains `"Human agent WhatsApp alert failed."` (standard action note).

**Pass criteria:** All Tier 2 format assertions pass. Legacy emoji header absent.

---

### TC-OBS-12: `log_noncritical_failure()` — Supabase failure does not block Telegram

**What it verifies:** Telegram alert fires even when the Supabase insert fails.

**Setup:**
- Patch `get_shared_db` to raise an exception on `.execute()`.
- Patch `_send_telegram_alert` to track calls.
- Patch settings with valid token and chat ID.

**Steps:**
1. Call `log_noncritical_failure(source="sheets_sync_booking", ...)`.
2. Assert `_send_telegram_alert` was called (Telegram still fires).
3. Assert no exception propagated to the caller.

**Pass criteria:** `_send_telegram_alert` was called. No exception raised.

---

## Test Suite: `engine/tests/unit/test_message_handler.py` (additions)

### TC-MH-01: Customer DB query failure fires `log_incident` and `send_telegram_alert`

**What it verifies:** When the Supabase `customers.select()` at Step 3 raises, both `log_incident(source="customer_query_failure")` and `send_telegram_alert(source="customer_query_failure")` are called.

**Setup:**
- Patch `load_client_config` and `get_client_db` as in existing tests.
- Make the chainable DB mock's `.execute()` raise `ConnectionError("Supabase unreachable")` only when `db.table("customers")` is the most recent call (allow `interactions_log` insert to succeed first).
- Patch `engine.core.message_handler.log_incident` as `AsyncMock`.
- Patch `engine.core.message_handler.send_telegram_alert` as `AsyncMock`.

**Steps:**
1. Call `handle_inbound_message(**_PARAMS)`.
2. Assert `log_incident` was called with `source="customer_query_failure"`.
3. Assert `send_telegram_alert` was called with `source="customer_query_failure"`.
4. Assert `send_telegram_alert` was called with `context={"customer_phone": "6591234567"}`.
5. Assert the fallback reply was sent to the customer (i.e., `send_message` was called with `FALLBACK_REPLY`).

**Pass criteria:** Both observability calls fire. Customer receives fallback reply. No exception propagates.

---

### TC-MH-02: Customer DB query failure — observability failure does not suppress fallback

**What it verifies:** If `log_incident` or `send_telegram_alert` itself raises, the fallback reply is still sent.

**Setup:** Same as TC-MH-01, but `log_incident` raises `Exception("observability down")`.

**Steps:**
1. Call `handle_inbound_message(**_PARAMS)`.
2. Assert `send_message` was still called with `FALLBACK_REPLY` (or that no exception propagated).

**Pass criteria:** Function completes. Fallback reply was attempted.

---

### TC-MH-03: `sync_customer_to_sheets` task failure calls `log_noncritical_failure`

**What it verifies:** The `_sync_customer_safe` wrapper catches `sync_customer_to_sheets` exceptions and calls `log_noncritical_failure(source="sheets_sync_customer")`.

**Setup:**
- Set up a normal message flow (no escalation, no DB failure) so the new customer branch is reached.
- Patch `engine.core.message_handler.sync_customer_to_sheets` to raise `RuntimeError("Sheets down")`.
- Patch `engine.core.message_handler.log_noncritical_failure` as `AsyncMock`.

**Steps:**
1. Trigger the new customer path by setting `customer_row=None` in the DB mock.
2. Allow `asyncio` event loop to process pending tasks (use `await asyncio.sleep(0)` or `asyncio.get_event_loop().run_until_complete`).
3. Assert `log_noncritical_failure` was called with `source="sheets_sync_customer"`.
4. Assert `log_noncritical_failure` was called with `error_type="RuntimeError"`.

**Pass criteria:** Wrapper catches the exception and routes to `log_noncritical_failure`.

---

## Test Suite: `engine/tests/unit/test_booking_tools.py` (additions)

### TC-BT-01: Calendar write failure fires `log_incident` and `send_telegram_alert`

**What it verifies:** When `create_booking_event()` raises, both `log_incident(source="calendar_write_failure")` and `send_telegram_alert(source="calendar_write_failure")` are called before the exception is re-raised.

**Setup:**
- Build a mock `client_config` with `google_calendar_creds` and `google_calendar_id` set.
- Patch `engine.core.tools.booking_tools.create_booking_event` (via its import path) to raise `RuntimeError("404 calendar not found")`.
- Patch `engine.core.tools.booking_tools.log_incident` as `AsyncMock`.
- Patch `engine.core.tools.booking_tools.send_telegram_alert` as `AsyncMock`.
- Patch `engine.core.tools.booking_tools._alert_booking_failure` as `AsyncMock` (preserve existing WhatsApp path).

**Steps:**
1. Call `write_booking(db, client_config, phone_number="6591234567", ...)` and expect a `RuntimeError`.
2. Assert `log_incident` was called with `source="calendar_write_failure"`.
3. Assert `log_incident` was called with `context` containing `"booking_id"` and `"customer_phone"`.
4. Assert `send_telegram_alert` was called with `source="calendar_write_failure"`.
5. Assert `send_telegram_alert` context does NOT contain `customer_name`, `address`, or `postal_code`.
6. Assert `_alert_booking_failure` was ALSO called (existing WhatsApp path must not be removed).
7. Assert `RuntimeError` was re-raised (the observability calls must not suppress the `raise`).

**Pass criteria:** Both observability calls fire. WhatsApp path preserved. Exception re-raised.

---

### TC-BT-02: Supabase booking INSERT failure fires `log_incident` and `send_telegram_alert`

**What it verifies:** When `db.table("bookings").insert().execute()` raises after a successful calendar write, both observability calls fire with `source="booking_db_insert_failure"` and `calendar_event_id` is in context.

**Setup:**
- Patch `create_booking_event` to succeed and return `"cal_event_abc123"`.
- Make `db.table("bookings").insert().execute()` raise `Exception("duplicate key violation")`.
- Patch `log_incident` and `send_telegram_alert` as `AsyncMock`.
- Patch `_alert_booking_failure` as `AsyncMock`.

**Steps:**
1. Call `write_booking(...)` and expect an exception.
2. Assert `log_incident` was called with `source="booking_db_insert_failure"`.
3. Assert `log_incident` context contains `"calendar_event_id": "cal_event_abc123"`.
4. Assert `send_telegram_alert` was called with `source="booking_db_insert_failure"`.
5. Assert `send_telegram_alert` context contains `"calendar_event_id": "cal_event_abc123"`.
6. Assert context does NOT contain `customer_name`, `address`, or `postal_code`.
7. Assert `_alert_booking_failure` was called.
8. Assert exception was re-raised.

**Pass criteria:** All assertions pass. `calendar_event_id` present in both observability calls.

---

### TC-BT-03: `sync_booking_to_sheets` task failure calls `log_noncritical_failure`

**What it verifies:** The `_sync_booking_safe` wrapper catches `sync_booking_to_sheets` exceptions and calls `log_noncritical_failure(source="sheets_sync_booking")`.

**Setup:**
- Patch `create_booking_event` to succeed.
- Patch `db.table("bookings").insert().execute()` to succeed.
- Patch `sync_booking_to_sheets` to raise `RuntimeError("Sheets API down")`.
- Patch `log_noncritical_failure` as `AsyncMock`.

**Steps:**
1. Call `write_booking(...)` to completion (calendar + DB both succeed).
2. Drain task queue (`await asyncio.sleep(0)`).
3. Assert `log_noncritical_failure` was called with `source="sheets_sync_booking"`.
4. Assert `log_noncritical_failure` context contains `"booking_id"`.
5. Assert `log_noncritical_failure` context does NOT contain `customer_name`.

**Pass criteria:** Wrapper logs the failure. Booking was still written to DB successfully.

---

### TC-BT-04: Successful write — no Telegram calls fired

**What it verifies:** On a fully successful booking (calendar + DB both succeed), `send_telegram_alert` and `log_incident` are NOT called for Tier 1 error paths.

**Setup:**
- Patch `create_booking_event` to succeed.
- Patch DB to succeed.
- Patch `send_telegram_alert` as `AsyncMock`.
- Patch `log_incident` as `AsyncMock`.

**Steps:**
1. Call `write_booking(...)` to completion.
2. Assert `send_telegram_alert` was NOT called.
3. Assert `log_incident` was NOT called with `source` in `["calendar_write_failure", "booking_db_insert_failure"]`.

**Pass criteria:** No spurious alerting on the happy path.

---

## Test Suite: `engine/tests/unit/test_agent_runner.py` (additions)

### TC-AR-01: Both LLMs failed — `send_telegram_alert` fires with `source="llm_both_failed"`

**What it verifies:** When the OpenAI fallback also fails (both providers down), `send_telegram_alert` is called with `source="llm_both_failed"` before the fallback response string is returned.

**Setup:**
- Patch `_call_llm` to raise `Exception("APIConnectionError")` on first call (Anthropic).
- Patch `_get_openai_fallback_client` to return a mock client.
- Patch that mock client's `_call_llm` to also raise `Exception("OpenAI timeout")`.
- Patch `engine.core.agent_runner.log_incident` as `AsyncMock`.
- Patch `engine.core.agent_runner.send_telegram_alert` as `AsyncMock`.

**Steps:**
1. Call `run_agent(...)`.
2. Assert the return value is `_FALLBACK_RESPONSE`.
3. Assert `log_incident` was called with `both_failed=True`.
4. Assert `send_telegram_alert` was called with `source="llm_both_failed"`.
5. Assert `send_telegram_alert` context contains `"providers_failed": "Anthropic + OpenAI"`.

**Pass criteria:** Both `log_incident(both_failed=True)` and `send_telegram_alert(source="llm_both_failed")` fired. Fallback returned.

---

### TC-AR-02: Both LLMs failed — `send_telegram_alert` exception does not prevent fallback return

**What it verifies:** If `send_telegram_alert` itself raises during the both-failed path, `_FALLBACK_RESPONSE` is still returned.

**Setup:** Same as TC-AR-01, but `send_telegram_alert` raises `Exception("Telegram down")`.

**Steps:**
1. Call `run_agent(...)`.
2. Assert return value is `_FALLBACK_RESPONSE` (not an exception).

**Pass criteria:** Fallback returned regardless of Telegram call failure.

---

## Test Suite: Migration (SQL)

### TC-MIG-01: Migration `005` is idempotent

**What it verifies:** Running the migration SQL twice against a real Postgres database does not raise an error or produce duplicate tables/columns.

**File:** `engine/tests/unit/test_observability_migration.py` (new file) or annotated as manual verification steps if a real DB is not available in CI.

**Steps:**
1. Execute `supabase/migrations/005_observability_tables.sql` against a test database.
2. Execute the same file a second time.
3. Assert no error is raised on either run.
4. Assert `api_incidents` table exists with columns: `id`, `ts`, `provider`, `error_type`, `error_message`, `client_id`, `fallback_used`, `both_failed`, `source`, `context`.
5. Assert `noncritical_failures` table exists with columns: `id`, `ts`, `source`, `error_type`, `error_message`, `client_id`, `context`.
6. Assert `api_usage` table exists.
7. Assert named indexes exist: `api_incidents_ts`, `api_incidents_provider`, `api_incidents_source`, `api_usage_provider`, `api_usage_client`, `noncritical_ts`, `noncritical_client`, `noncritical_source`.

**Note:** This test requires a Postgres connection. If CI does not provide one, verify manually before merging. The migration's `IF NOT EXISTS` guards on all CREATE/ALTER statements are the implementation mechanism — the test confirms they work end-to-end.

---

## Integration Smoke Test

### TC-INT-01: Real Telegram delivery — Tier 1 alert reaches the group chat

**Classification:** Integration boundary test (mandatory gate before merge approval per SDET hard rules).

**What it verifies:** With real `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALERT_CHAT_ID` set in the local environment, calling `send_telegram_alert()` directly results in a message appearing in the configured Telegram group chat.

**Requires:**
- `TELEGRAM_BOT_TOKEN` set to the production or staging bot token
- `TELEGRAM_ALERT_CHAT_ID` set to the internal team chat ID
- Internet connectivity

**File:** `engine/tests/integration/test_telegram_smoke.py` (new file, guarded by `pytest.mark.integration` or `skipif` env var check)

**Steps:**
1. If either env var is absent, skip the test with `pytest.skip("TELEGRAM credentials not set")`.
2. Call:
   ```python
   await send_telegram_alert(
       title="[SMOKE TEST] Telegram Alert Integration",
       source="smoke_test",
       client_id="hey-aircon",
       error_type="SmokeTestError",
       error_message="This is a smoke test from the SDET verification suite.",
       context={"customer_phone": "6591234567", "booking_id": "HA-SMOKE-0001"},
       action_note="This is an automated smoke test. No action required.",
   )
   ```
3. Assert the function returned without raising.
4. Manually confirm the message appeared in the Telegram chat (or assert via Telegram Bot API `getUpdates` if preferred).

**Pass criteria:** Function returns without exception. Message appears in Telegram chat.

**Blocking gate:** This test must pass before merge approval is granted. If `TELEGRAM_BOT_TOKEN` is not yet available (e.g. bot not yet created), hold the worktree open and document the block in the PR.

---

## PII Verification Checklist

These are checked manually during code review and are blocking:

- [ ] `send_telegram_alert()` context dicts in `booking_tools.py` contain ONLY: `customer_phone`, `booking_id`, `calendar_event_id` — never `customer_name`, `address`, `postal_code`
- [ ] `send_telegram_alert()` context dict in `message_handler.py` contains ONLY: `customer_phone`
- [ ] `send_telegram_alert()` context dict in `agent_runner.py` contains ONLY: `providers_failed`
- [ ] `_BOOKING_FAILURE_ALERT_TEMPLATE` in `booking_tools.py` is unchanged (still includes `customer_name` and `address` — WhatsApp path only)
- [ ] No `customer_name` or address data passes through `send_telegram_alert()` at any call site

---

## Acceptance Criteria Summary

| ID | Criteria | Verified by |
|---|---|---|
| AC-1 | `_send_telegram_alert()` sends correct HTTP POST when vars set | TC-OBS-01 |
| AC-2 | `_send_telegram_alert()` is silent no-op when vars unset | TC-OBS-02, TC-OBS-03 |
| AC-3 | HTTP failure logged at WARNING, never raises | TC-OBS-04 |
| AC-4 | `send_telegram_alert()` produces correct Tier 1 format | TC-OBS-05 |
| AC-5 | Context keys absent produce no blank lines | TC-OBS-06 |
| AC-6 | Error message truncated at 200 chars | TC-OBS-07 |
| AC-7 | Empty `client_id` renders as `unknown` | TC-OBS-08 |
| AC-8 | `log_incident()` passes `source`/`context` to Supabase when provided | TC-OBS-09 |
| AC-9 | `log_incident()` backward-compatible — keys absent when None | TC-OBS-10 |
| AC-10 | `log_noncritical_failure()` uses Tier 2 canonical format | TC-OBS-11 |
| AC-11 | Supabase failure does not block Telegram in `log_noncritical_failure()` | TC-OBS-12 |
| AC-12 | Customer DB query failure → Tier 1 alert fires | TC-MH-01 |
| AC-13 | Observability failure in Step 3 does not suppress fallback reply | TC-MH-02 |
| AC-14 | `sync_customer_to_sheets` task failure → `log_noncritical_failure` | TC-MH-03 |
| AC-15 | Calendar write failure → Tier 1 alert fires, exception re-raised | TC-BT-01 |
| AC-16 | Booking INSERT failure → Tier 1 alert fires with `calendar_event_id` | TC-BT-02 |
| AC-17 | `sync_booking_to_sheets` task failure → `log_noncritical_failure` | TC-BT-03 |
| AC-18 | Happy path: no spurious Tier 1 alerts | TC-BT-04 |
| AC-19 | Both LLMs failed → `send_telegram_alert(source="llm_both_failed")` fires | TC-AR-01 |
| AC-20 | Telegram failure on both-failed path does not prevent fallback return | TC-AR-02 |
| AC-21 | Migration `005` is idempotent | TC-MIG-01 |
| AC-22 | Real Telegram message delivered to group chat | TC-INT-01 |
| AC-23 | No PII beyond `customer_phone` in Telegram context dicts | PII checklist |
| AC-24 | `escalation_tool.py` has zero changes | Code review |
| AC-25 | Customer-facing messages unchanged | Code review |

---

## Out of Scope

- Alert deduplication or rate limiting
- Per-tier or per-client Telegram chat routing
- `reset_handler.py` — the `create_task(sync_customer_to_sheets(...))` at line 193 is not part of this feature
- `escalation_tool.py` — already has a `log_noncritical_failure` call for `source="escalation_sheets_sync"` at the outer except block; the bare `create_task` at line 87 (inside the try) is a known gap but out of scope per architecture spec
