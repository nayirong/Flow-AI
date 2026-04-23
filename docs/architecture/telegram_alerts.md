# Architecture Spec: Internal Telegram Alert Bot

**Status:** Ready for implementation
**Created:** 2026-04-22
**Requirement source:** `docs/requirements/telegram_alerts.md`

---

## Overview

This spec completes the observability alerting pipeline. The `_send_telegram_alert()` no-op stub in `observability.py` is upgraded to a real HTTP implementation. Four Tier 1 (critical) failure points are wired to both `api_incidents` (Supabase) and Telegram. Three Tier 2 (non-critical) failure points — two of which already call `log_noncritical_failure()` — are completed by closing fire-and-forget task gaps.

The feature has zero customer-facing effect. No changes to the WhatsApp channel, agent behaviour, or customer reply logic.

---

## Dependency Order for Implementation

The engineer must implement files in this order. Each step depends on the previous.

```
1. supabase/migrations/005_observability_tables.sql
   — tables and columns must exist before any Supabase writes are added

2. engine/config/settings.py
   — Telegram env vars must be importable before observability.py reads them

3. engine/integrations/observability.py
   — _send_telegram_alert() and send_telegram_alert() must exist before callers are updated

4. engine/core/tools/booking_tools.py
   — depends on send_telegram_alert() from observability.py

5. engine/core/message_handler.py
   — depends on send_telegram_alert() from observability.py

6. engine/core/agent_runner.py
   — depends on send_telegram_alert() from observability.py
```

---

## 1. Migration: `supabase/migrations/005_observability_tables.sql`

This migration creates all three observability tables from scratch (safe to run against a production DB that may already have them manually — all statements use IF NOT EXISTS / IF NOT EXISTS guards) and adds the two new columns to `api_incidents`.

### Full DDL

```sql
-- ============================================================
-- 005_observability_tables.sql
-- Observability tables for Flow AI shared Supabase.
-- Safe to run against production — all statements are idempotent.
-- Rollback: see comments at end of file.
-- ============================================================

-- api_incidents: one row per LLM provider failure or Tier 1 engine failure
CREATE TABLE IF NOT EXISTS api_incidents (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT NOW(),
    provider      TEXT NOT NULL,           -- 'anthropic' | 'openai' | 'agent_guardrail' | 'engine'
    error_type    TEXT NOT NULL,           -- Exception class name
    error_message TEXT,
    client_id     TEXT,
    fallback_used BOOLEAN DEFAULT FALSE,
    both_failed   BOOLEAN DEFAULT FALSE,
    source        TEXT,                   -- NEW: failure point identifier (see canonical values below)
    context       JSONB                   -- NEW: structured context (booking_id, customer_phone, calendar_event_id)
);

-- api_usage: one row per successful LLM call
CREATE TABLE IF NOT EXISTS api_usage (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ DEFAULT NOW(),
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    client_id       TEXT,
    input_tokens    INT,
    output_tokens   INT,
    total_tokens    INT
);

-- noncritical_failures: one row per Tier 2 failure
CREATE TABLE IF NOT EXISTS noncritical_failures (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT NOW(),
    source        TEXT NOT NULL,
    error_type    TEXT NOT NULL,
    error_message TEXT,
    client_id     TEXT,
    context       JSONB
);

-- Add new columns to api_incidents if they don't already exist
-- (handles case where table was created manually without these columns)
ALTER TABLE api_incidents ADD COLUMN IF NOT EXISTS source  TEXT;
ALTER TABLE api_incidents ADD COLUMN IF NOT EXISTS context JSONB;

-- Indexes
CREATE INDEX IF NOT EXISTS api_incidents_ts        ON api_incidents (ts DESC);
CREATE INDEX IF NOT EXISTS api_incidents_provider  ON api_incidents (provider, ts DESC);
CREATE INDEX IF NOT EXISTS api_incidents_source    ON api_incidents (source, ts DESC);
CREATE INDEX IF NOT EXISTS api_usage_provider      ON api_usage     (provider, ts DESC);
CREATE INDEX IF NOT EXISTS api_usage_client        ON api_usage     (client_id, ts DESC);
CREATE INDEX IF NOT EXISTS noncritical_ts          ON noncritical_failures (ts DESC);
CREATE INDEX IF NOT EXISTS noncritical_client      ON noncritical_failures (client_id, ts DESC);
CREATE INDEX IF NOT EXISTS noncritical_source      ON noncritical_failures (source, ts DESC);

-- ============================================================
-- ROLLBACK (manual — execute in reverse order if needed):
--   DROP INDEX IF EXISTS noncritical_source;
--   DROP INDEX IF EXISTS noncritical_client;
--   DROP INDEX IF EXISTS noncritical_ts;
--   DROP INDEX IF EXISTS api_usage_client;
--   DROP INDEX IF EXISTS api_usage_provider;
--   DROP INDEX IF EXISTS api_incidents_source;
--   DROP INDEX IF EXISTS api_incidents_provider;
--   DROP INDEX IF EXISTS api_incidents_ts;
--   ALTER TABLE api_incidents DROP COLUMN IF EXISTS context;
--   ALTER TABLE api_incidents DROP COLUMN IF EXISTS source;
--   DROP TABLE IF EXISTS noncritical_failures;
--   DROP TABLE IF EXISTS api_usage;
--   DROP TABLE IF EXISTS api_incidents;
-- ============================================================
```

### Canonical `source` values for `api_incidents`

| source value | Failure point |
|---|---|
| `llm_failure` | Single LLM provider failure (written by existing `log_incident()`) |
| `llm_both_failed` | Both Anthropic and OpenAI failed — triggers Telegram Tier 1 |
| `calendar_write_failure` | `create_booking_event()` raised in `booking_tools.py` |
| `booking_db_insert_failure` | `db.table("bookings").insert()` failed after calendar write succeeded |
| `customer_query_failure` | `db.table("customers").select()` raised in `message_handler.py` Step 3 |
| `agent_guardrail` | Guardrail reprompt / fire (existing — no change) |

### Startup verification requirement

The engine startup sequence (in `webhook.py` or a startup event) must verify that `api_incidents`, `api_usage`, and `noncritical_failures` tables are reachable. On failure: log `WARNING` only — never raise, never crash the service. This matches the existing non-fatal startup validation pattern.

---

## 2. `engine/config/settings.py` changes

### What changes

Add two optional platform-level fields to the `Settings` class. These are not per-client — they use no `{CLIENT_ID_UPPER}_` prefix, consistent with `SHARED_SUPABASE_URL`.

### Field signatures to add

```
telegram_bot_token: str | None = None
    # Env var: TELEGRAM_BOT_TOKEN
    # BotFather-issued token. If None, all Telegram paths are silent no-ops.

telegram_alert_chat_id: str | None = None
    # Env var: TELEGRAM_ALERT_CHAT_ID
    # Numeric Telegram group chat ID. If None, all Telegram paths are silent no-ops.
```

Both fields are `Optional[str]` with `None` defaults. The pydantic-settings `case_sensitive=False` config means Railway env vars `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALERT_CHAT_ID` map automatically.

### No-op safety rule

Any code path that reads these settings must check `if not token or not chat_id: return` before attempting any Telegram HTTP call. This is the existing pattern in `_send_telegram_alert()` — preserve it, but migrate the read source from `os.environ.get()` to `settings.telegram_bot_token` / `settings.telegram_alert_chat_id`.

---

## 3. `engine/integrations/observability.py` changes

### 3a. `_send_telegram_alert()` — upgrade from stub to real implementation

**What changes:** Replace `os.environ.get()` reads with `settings` reads. The HTTP call body is already correctly stubbed — preserve it exactly. The no-op guard, timeout (5.0s), `parse_mode="Markdown"`, and `disable_web_page_preview=True` are all preserved.

**Updated function signature (unchanged):**
```
async def _send_telegram_alert(message: str) -> None
```

**Updated internals (pseudocode — no implementation code):**
- Read `bot_token` from `settings.telegram_bot_token` (not `os.environ.get()`)
- Read `chat_id` from `settings.telegram_alert_chat_id` (not `os.environ.get()`)
- Guard: `if not bot_token or not chat_id: return`
- POST to `https://api.telegram.org/bot{bot_token}/sendMessage` via `httpx.AsyncClient(timeout=5.0)`
- Body: `{"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}`
- Catch all exceptions — log at `WARNING`, never raise

**Import addition:** `from engine.config.settings import settings` at module level (lazy import inside the function is also acceptable to avoid circular imports — match existing patterns in the file).

### 3b. `log_noncritical_failure()` — replace Telegram alert text

The existing `log_noncritical_failure()` already calls `_send_telegram_alert()` after the Supabase insert. The alert text format must be replaced with the standardised Tier 2 format (see Section 6).

**What changes in the alert text block (lines 243–250 of current file):**
Replace the existing `⚠️ *Non-critical failure*` template string with the Tier 2 canonical format defined in Section 6 of this spec. The `await _send_telegram_alert(alert_text)` call itself is unchanged.

### 3c. `log_incident()` — add Tier 1 Telegram trigger for `both_failed=True`

**What changes:** After the existing Supabase insert succeeds (or fails — Telegram must fire regardless), add a conditional Telegram call when `both_failed=True`.

**Logic (pseudocode):**
```
if both_failed:
    alert_text = format_tier1_alert(
        title="LLM Total Failure",
        source="llm_both_failed",
        client_id=client_id,
        error_type=error_type,
        error_message=error_message,
        context={"providers_failed": "Anthropic + OpenAI"},
        action_note="Customer received fallback reply. Agent could not respond.\nMonitor Anthropic/OpenAI status pages."
    )
    await _send_telegram_alert(alert_text)
```

The Telegram call must be wrapped in its own `try/except` — observability must never crash the caller.

### 3d. New public function: `send_telegram_alert()`

This is the Tier 1 entry point. It does NOT write to Supabase — callers handle their own Supabase write via `log_incident()` or a direct table insert. It only formats and sends the Telegram message.

**Function signature:**
```
async def send_telegram_alert(
    title: str,
    source: str,
    client_id: str,
    error_type: str,
    error_message: str,
    context: dict | None = None,
    action_note: str | None = None,
) -> None
```

**Behaviour:**
- Formats a Tier 1 message using the canonical format defined in Section 6
- Calls `_send_telegram_alert(formatted_message)`
- Never raises — all exceptions caught internally
- `context` dict may include: `customer_phone`, `booking_id`, `calendar_event_id`
- `error_message` is truncated to 200 characters in the formatted output
- `action_note` is the fixed instruction line at the bottom of each Tier 1 message (e.g. "Calendar event was NOT created. Booking NOT recorded.")

---

## 4. `engine/core/tools/booking_tools.py` changes

### 4a. Calendar write failure — add `api_incidents` write + Telegram

**Location:** The existing `except Exception as calendar_err:` block inside `write_booking()` (currently lines 183–200).

**What changes:** After the existing `await _alert_booking_failure(...)` call (WhatsApp to human agent — preserved unchanged), add:

```
# 1. Write to api_incidents
await log_incident(
    provider="engine",
    error_type=type(calendar_err).__name__,
    error_message=str(calendar_err),
    client_id=client_config.client_id,
    source="calendar_write_failure",
    context={"booking_id": booking_id, "customer_phone": phone_number},
)
# 2. Send Tier 1 Telegram alert
await send_telegram_alert(
    title="Booking Backend Failure",
    source="calendar_write_failure",
    client_id=client_config.client_id,
    error_type=type(calendar_err).__name__,
    error_message=str(calendar_err),
    context={"booking_id": booking_id, "customer_phone": phone_number},
    action_note="Calendar event was NOT created. Booking NOT recorded.\nManual booking required — customer has been told to expect a callback.",
)
```

Both calls are wrapped in their own `try/except` — observability must never suppress the `raise` that follows.

**Note:** `log_incident()` signature must be extended to accept `source` and `context` kwargs (see Section 3 — `log_incident()` currently does not have these params). The engineer adds them as optional kwargs with `None` defaults and includes them in the Supabase insert dict only when non-None.

### 4b. Supabase booking INSERT failure — add `api_incidents` write + Telegram

**Location:** The existing `except Exception as db_err:` block inside `write_booking()` (currently lines 236–254).

**What changes:** After `await _alert_booking_failure(...)`, add:

```
# 1. Write to api_incidents
await log_incident(
    provider="engine",
    error_type=type(db_err).__name__,
    error_message=str(db_err),
    client_id=client_config.client_id,
    source="booking_db_insert_failure",
    context={
        "booking_id": booking_id,
        "customer_phone": phone_number,
        "calendar_event_id": calendar_event_id,
    },
)
# 2. Send Tier 1 Telegram alert
await send_telegram_alert(
    title="Booking Backend Failure",
    source="booking_db_insert_failure",
    client_id=client_config.client_id,
    error_type=type(db_err).__name__,
    error_message=str(db_err),
    context={
        "booking_id": booking_id,
        "customer_phone": phone_number,
        "calendar_event_id": calendar_event_id,
    },
    action_note="Calendar event exists but DB row is missing.\nManual Supabase insert required to prevent orphaned calendar event.",
)
```

### 4c. `sync_booking_to_sheets()` fire-and-forget — add failure handler

**Location:** The `asyncio.create_task(sync_booking_to_sheets(...))` call in `write_booking()` Step 2 (currently line 231–235).

**What changes:** The current pattern wraps `sync_booking_to_sheets` in a bare `create_task`. A wrapper coroutine must be introduced that catches any exception and calls `log_noncritical_failure()`.

**Wrapper shape (pseudocode):**
```
async def _sync_booking_safe(client_id, client_config, booking_data):
    try:
        await sync_booking_to_sheets(client_id=client_id, client_config=client_config, booking_data=booking_data)
    except Exception as e:
        await log_noncritical_failure(
            source="sheets_sync_booking",
            error_type=type(e).__name__,
            error_message=str(e),
            client_id=client_id,
            context={"booking_id": booking_data.get("booking_id"), "phone_number": booking_data.get("phone_number")},
        )
```

`asyncio.create_task` then wraps `_sync_booking_safe(...)`. The same pattern applies to the `sync_customer_to_sheets` call in Step 3 of `write_booking()`.

**Import addition:** `from engine.integrations.observability import log_incident, send_telegram_alert, log_noncritical_failure`

---

## 5. `engine/core/message_handler.py` changes

### 5a. Supabase customer query failure (Step 3) — add `api_incidents` write + Telegram

**Location:** The existing `except Exception as e:` block at Step 3 (currently lines 133–151).

**What changes:** After `logger.error(...)` and before the fallback reply block, add:

```
# Write to api_incidents
await log_incident(
    provider="engine",
    error_type=type(e).__name__,
    error_message=str(e),
    client_id=client_id,
    source="customer_query_failure",
    context={"customer_phone": phone_number},
)
# Send Tier 1 Telegram alert
await send_telegram_alert(
    title="DB Query Failure — Escalation Gate Blocked",
    source="customer_query_failure",
    client_id=client_id,
    error_type=type(e).__name__,
    error_message=str(e),
    context={"customer_phone": phone_number},
    action_note="Escalation gate could not run. Customer received fallback reply.\nCheck Supabase status and per-client DB connectivity.",
)
```

Both calls must be wrapped in their own `try/except`. The `return` after the fallback reply is not affected.

### 5b. `sync_customer_to_sheets()` fire-and-forget — add failure handler

**Location:** Both `asyncio.create_task(sync_customer_to_sheets(...))` calls in Step 5 — the new customer branch (line 215) and the returning customer branch (line 234).

**What changes:** Same wrapper pattern as Section 4c:

```
async def _sync_customer_safe(client_id, client_config, customer_data):
    try:
        await sync_customer_to_sheets(client_id=client_id, client_config=client_config, customer_data=customer_data)
    except Exception as e:
        await log_noncritical_failure(
            source="sheets_sync_customer",
            error_type=type(e).__name__,
            error_message=str(e),
            client_id=client_id,
            context={"phone_number": customer_data.get("phone_number")},
        )
```

`asyncio.create_task` then wraps `_sync_customer_safe(...)` at both call sites.

**Import addition:** `from engine.integrations.observability import log_incident, send_telegram_alert, log_noncritical_failure`

---

## 6. `engine/core/agent_runner.py` changes

### LLM both-providers failure — add Telegram

**Location:** The `except Exception as fallback_err:` block (currently lines 448–462), specifically after the existing `await log_incident(..., both_failed=True)` call.

**Current state:** `log_incident(both_failed=True)` is called, then the function returns `_FALLBACK_RESPONSE`. Telegram is not triggered.

**What changes:** After the `await log_incident(...)` call, add a Telegram alert call. The `log_incident()` itself does NOT need to be changed here — Section 3c adds the `both_failed` Telegram trigger inside `log_incident()`. That means: no direct change to `agent_runner.py` is required for this trigger IF the engineer implements Section 3c correctly.

However, to keep `agent_runner.py` explicit and testable, the preferred approach is:

After the `await log_incident(...)` call (line 457 area), add a direct call to `send_telegram_alert()` with `source="llm_both_failed"`. This makes the Telegram trigger explicit at the call site rather than hidden inside `log_incident()`.

**Choose one approach — do not implement both.** The SDET test plan must verify which approach was implemented. The architect's preference is the explicit call in `agent_runner.py` (approach 2), because it makes the Tier 1 trigger traceable at the failure site.

**Explicit call shape (pseudocode):**
```
await send_telegram_alert(
    title="LLM Total Failure",
    source="llm_both_failed",
    client_id=client_id,
    error_type=type(fallback_err).__name__,
    error_message=str(fallback_err),
    context={"providers_failed": "Anthropic + OpenAI"},
    action_note="Customer received fallback reply. Agent could not respond.\nMonitor Anthropic/OpenAI status pages.",
)
```

**Import addition:** `from engine.integrations.observability import send_telegram_alert`

---

## 7. `log_incident()` signature extension

The existing `log_incident()` in `observability.py` does not accept `source` or `context`. Two optional kwargs must be added.

**Updated signature:**
```
async def log_incident(
    provider: str,
    error_type: str,
    error_message: str,
    client_id: str = "",
    fallback_used: bool = False,
    both_failed: bool = False,
    source: str | None = None,
    context: dict | None = None,
) -> None
```

**Supabase insert change:** Add `source` and `context` to the insert dict only when non-None:
```
row = {
    "provider": provider,
    "error_type": error_type,
    "error_message": str(error_message)[:500],
    "client_id": client_id or None,
    "fallback_used": fallback_used,
    "both_failed": both_failed,
}
if source is not None:
    row["source"] = source
if context is not None:
    row["context"] = context
```

This is backward-compatible — all existing callers that pass no `source`/`context` continue to work unchanged.

---

## 8. Telegram Message Format Templates

### Format rules (apply to both tiers)

- Plain text only in the message body. `parse_mode="Markdown"` is kept in the HTTP call but the message body must not use `*`, `_`, or backtick wrapping for prose text.
- Exception: backtick wrapping is allowed for values that are identifiers: booking IDs, event IDs, source slugs. These render reliably in Telegram Markdown for group chats.
- `error_message` is truncated to 200 characters in the rendered output.
- Every alert includes `client_id`. If `client_id` is empty or None, render `unknown`.
- `customer_phone` renders as-is (E.164 without `+`). This is the only customer-identifying data allowed in Telegram messages. No customer name, no address.

### Tier 1 canonical format template

```
CRITICAL | {title}
Client: {client_id}
Source: `{source}`
Time: {timestamp_utc_iso}

Error: {error_type} — {error_message_truncated_200}
{context_lines}

{action_note}
```

`{context_lines}` expands only the keys present in the `context` dict, in this order:

| Key present | Line rendered |
|---|---|
| `customer_phone` | `Customer: {value}` |
| `booking_id` | `Booking: {value}` |
| `calendar_event_id` | `Calendar Event: {value} (ALREADY CREATED)` |
| `providers_failed` | `Providers failed: {value}` |

Keys absent from the dict are omitted entirely — no blank lines for missing keys.

### Tier 1 examples (verbatim from requirements, confirmed canonical)

**Calendar write failure:**
```
CRITICAL | Booking Backend Failure
Client: hey-aircon
Source: `calendar_write_failure`
Time: 2026-04-22T08:14:32Z

Error: GoogleAPIError — 404 calendar not found
Customer: 6591234567
Booking: HA-20260430-A3F2

Calendar event was NOT created. Booking NOT recorded.
Manual booking required — customer has been told to expect a callback.
```

**Supabase booking INSERT failure:**
```
CRITICAL | Booking Backend Failure
Client: hey-aircon
Source: `booking_db_insert_failure`
Time: 2026-04-22T08:15:01Z

Error: PostgrestAPIError — duplicate key violation
Customer: 6591234567
Booking: HA-20260430-A3F2
Calendar Event: cal_event_abc123 (ALREADY CREATED)

Calendar event exists but DB row is missing.
Manual Supabase insert required to prevent orphaned calendar event.
```

**LLM total failure:**
```
CRITICAL | LLM Total Failure
Client: hey-aircon
Source: `llm_both_failed`
Time: 2026-04-22T08:16:45Z

Error: APIConnectionError — connection timeout
Providers failed: Anthropic + OpenAI
Customer: 6591234567

Customer received fallback reply. Agent could not respond.
Monitor Anthropic/OpenAI status pages.
```

**Customer query failure:**
```
CRITICAL | DB Query Failure — Escalation Gate Blocked
Client: hey-aircon
Source: `customer_query_failure`
Time: 2026-04-22T08:17:10Z

Error: ConnectionError — Supabase unreachable
Customer: 6591234567

Escalation gate could not run. Customer received fallback reply.
Check Supabase status and per-client DB connectivity.
```

### Tier 2 canonical format template

```
WARNING | Non-critical Failure
Client: {client_id}
Source: `{source}`
Time: {timestamp_utc_iso}

Error: {error_type} — {error_message_truncated_200}
{context_lines}

{action_note}
```

`{context_lines}` follows the same key-presence rule as Tier 1.

**Standard `action_note` values by source:**

| source | action_note |
|---|---|
| `escalation_human_alert` | `Human agent WhatsApp alert failed. Escalation flag is still set in DB.\nManual follow-up required.` |
| `escalation_sheets_sync` | `Google Sheets customer sync failed after escalation. DB record is intact.` |
| `sheets_sync_customer` | `Google Sheets customer sync failed. DB record is intact.` |
| `sheets_sync_booking` | `Google Sheets booking sync failed. DB record is intact.` |

**Tier 2 example:**
```
WARNING | Non-critical Failure
Client: hey-aircon
Source: `escalation_human_alert`
Time: 2026-04-22T08:18:00Z

Error: HTTPStatusError — 400 bad request
Customer: 6591234567

Human agent WhatsApp alert failed. Escalation flag is still set in DB.
Manual follow-up required.
```

### Tier 2 format migration note

The existing `log_noncritical_failure()` produces the legacy `⚠️ *Non-critical failure*` format. This must be replaced with the Tier 2 canonical format above. The replacement is a string change only — no structural changes to `log_noncritical_failure()`.

To produce the `action_note` line from `log_noncritical_failure()`, add a lookup dict mapping `source` values to their standard action notes. Unmapped sources fall back to an empty action_note.

---

## 9. PII Rules (mandatory enforcement)

| Data | Allowed in Telegram | Allowed in WhatsApp alert to human agent |
|---|---|---|
| `customer_phone` (E.164) | Yes | Yes |
| `customer_name` | Never | Yes |
| `address` | Never | Yes |
| `postal_code` | Never | Yes |
| `booking_id` | Yes | Yes |
| `calendar_event_id` | Yes | Yes |
| `error_message` (engine errors) | Yes (truncated 200 chars) | N/A |

The engineer must not add `customer_name`, `address`, or `postal_code` to any `context` dict that is passed to `send_telegram_alert()`.

---

## 10. No-op Safety Spec

The entire Telegram path is a silent no-op if either `TELEGRAM_BOT_TOKEN` or `TELEGRAM_ALERT_CHAT_ID` is unset (None or empty string). This must hold at every layer:

| Layer | No-op guard location |
|---|---|
| `_send_telegram_alert()` | First lines of function body: `if not bot_token or not chat_id: return` |
| `send_telegram_alert()` | Delegates to `_send_telegram_alert()` — guard fires there |
| `log_noncritical_failure()` Telegram block | Guard fires inside `_send_telegram_alert()` |
| `log_incident()` `both_failed` block | Guard fires inside `_send_telegram_alert()` |

No caller outside `observability.py` should check for env var presence — the guard is centralised in `_send_telegram_alert()`. Callers call unconditionally.

**Production with vars unset:** All observability Supabase writes still happen. Only the Telegram HTTP call is skipped. No warnings are logged for the no-op path (silent skip, not a warning).

---

## 11. Pre-Implementation Verification Checklist for SDET

Before dispatching to the software-engineer, the SDET must verify the following against the production environment:

1. **Confirm `api_incidents` table state:** Does the table already exist in shared Supabase? If yes, do the `source` and `context` columns exist? Run migration `005` regardless — `IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS` make it safe.

2. **Confirm `noncritical_failures` table state:** Does the table already exist? Same as above — run migration regardless.

3. **Confirm `api_usage` table state:** Same.

4. **Telegram bot token readiness:** Is `TELEGRAM_BOT_TOKEN` set in Railway for the production service? If not, implementation can proceed — no-op safety means zero impact. Token can be added post-deploy.

5. **Confirm `log_incident()` call sites:** Verify that the two call sites in `agent_runner.py` that use `both_failed=True` are the only ones (there is exactly one: lines 449–457). The SDET must confirm no additional `both_failed=True` calls exist elsewhere that would also need the `send_telegram_alert()` addition.

6. **Confirm `sync_booking_to_sheets` and `sync_customer_to_sheets` call sites:** Verify all `asyncio.create_task(sync_*_to_sheets(...))` call sites across the codebase. The spec covers the ones visible in the source reads. Any additional call sites must receive the same safe-wrapper treatment.

7. **Verify `httpx` is in requirements:** `httpx` is already imported in the stub. Confirm it is in `requirements.txt` or `pyproject.toml` so the Railway build does not regress.

---

## 12. What Is Not Changing

- `_BOOKING_FAILURE_ALERT_TEMPLATE` (the WhatsApp alert to `human_agent_number`) — preserved exactly as-is. Telegram is an additional channel, not a replacement.
- The `_alert_booking_failure()` function in `booking_tools.py` — no changes to its signature or body.
- Customer-facing messages — zero changes.
- Agent tool definitions — zero changes.
- `escalation_tool.py` — no direct changes. The two existing `log_noncritical_failure()` calls already route through the Telegram stub. They become live when `_send_telegram_alert()` is upgraded in Step 3 above.
- Alert routing — all tiers go to the single `TELEGRAM_ALERT_CHAT_ID`. No per-tier chat splitting.
- Alert deduplication or rate limiting — out of scope.
