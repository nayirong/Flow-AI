# Feature: Internal Telegram Alert Bot

**Status:** Draft — Pending Founder Approval
**Created:** 2026-04-22
**Owned by:** @product-manager

---

## Feature Summary

When any actionable failure occurs in the production engine, the Flow AI internal team receives a real-time Telegram message identifying the client, the failure point, severity tier, and enough context to act immediately. Every failure also persists to the shared Flow AI Supabase for audit and trend analysis. The Telegram alert stub in `observability.py` already exists and is partially wired — this feature completes the implementation and extends it to cover critical (Tier 1) failures that currently have no Telegram path.

---

## Direction Check

- **Subject:** The Flow AI internal team (the operator), not the end customer.
- **Problem:** Critical and non-critical engine failures are currently silent beyond Railway logs. The team has no real-time signal when a booking fails, an LLM goes down, or a customer query breaks. Issues are discovered reactively.
- **Confirmation:** The solution delivers alerting to the internal team (correct subject) for production engine failures (correct threat). It does not add customer-facing messaging or modify the customer experience in any way.

---

## Failure Taxonomy

### Tier 1 — Critical (immediate action required, customer-facing impact)

| Failure Point | File | Trigger Condition | Supabase Table | Telegram Alert |
|---|---|---|---|---|
| Google Calendar write fails | `engine/core/tools/booking_tools.py` | `create_booking_event()` raises any exception | `api_incidents` | Yes |
| Supabase booking INSERT fails after calendar write succeeds | `engine/core/tools/booking_tools.py` | `db.table("bookings").insert()` raises after `calendar_event_id` is set | `api_incidents` | Yes |
| LLM total failure — both Anthropic and OpenAI fail | `engine/core/agent_runner.py` (logged via `log_incident` with `both_failed=True`) | `both_failed=True` row written to `api_incidents` | `api_incidents` | Yes |
| Supabase customer query fails — escalation gate cannot run | `engine/core/message_handler.py` | `db.table("customers").select()` raises at Step 3 | `api_incidents` | Yes |

**Current state of Tier 1 alerting:**
- Google Calendar failure and Supabase booking INSERT failure: `_alert_booking_failure()` already sends a WhatsApp message to `human_agent_number`. Telegram is NOT currently triggered. Both failures must be added to `api_incidents` AND trigger a Telegram alert.
- LLM total failure: `log_incident(both_failed=True)` already writes to `api_incidents`. Telegram is NOT currently triggered. A Telegram alert must fire when `both_failed=True`.
- Supabase customer query failure: currently logs via `logger.error` only. No Supabase write, no Telegram. Both must be added.

### Tier 2 — Non-critical (team awareness, no customer impact)

| Failure Point | File | Trigger Condition | Supabase Table | Telegram Alert |
|---|---|---|---|---|
| Human agent WhatsApp alert fails during escalation | `engine/core/tools/escalation_tool.py` | `send_message()` raises in Step 2 of `escalate_to_human()` | `noncritical_failures` | Yes |
| Google Sheets customer sync fails | `engine/core/tools/escalation_tool.py`, `engine/core/message_handler.py` | `sync_customer_to_sheets()` raises | `noncritical_failures` | Yes |
| Google Sheets booking sync fails | `engine/core/tools/booking_tools.py` | `sync_booking_to_sheets()` raises | `noncritical_failures` | Yes |

**Current state of Tier 2 alerting:**
- Human agent WhatsApp alert failure: already calls `log_noncritical_failure()` which already calls `_send_telegram_alert()`. **Already wired** — only the stub implementation needs to be completed.
- Google Sheets customer sync failure (from `escalation_tool.py`): already calls `log_noncritical_failure()`. **Already wired** — only the stub implementation needs to be completed.
- Google Sheets customer sync failure (from `message_handler.py`): `sync_customer_to_sheets()` is called as a fire-and-forget `asyncio.create_task()`. Failures inside that task are currently NOT caught at the call site. The task itself must handle failures and call `log_noncritical_failure()`.
- Google Sheets booking sync failure (from `booking_tools.py`): `sync_booking_to_sheets()` is called as a fire-and-forget `asyncio.create_task()`. Same issue — failures are currently silent. The task must handle failures and call `log_noncritical_failure()`.

---

## Telegram Message Format Specification

### Required fields — every alert (both tiers)

| Field | Description |
|---|---|
| Severity header | `CRITICAL` (Tier 1) or `WARNING` (Tier 2) |
| Client | `client_id` slug (e.g. `hey-aircon`) |
| Source | Short identifier matching the `source` field in Supabase (e.g. `calendar_write_failure`) |
| Timestamp | UTC ISO 8601, rounded to seconds |
| Error type | Exception class name |
| Description | `error_message` truncated to 200 characters |
| Context | Relevant keys only — `booking_id`, `customer_phone`, `calendar_event_id` where applicable |

### Tier 1 message example — calendar write failure

```
CRITICAL | Booking Backend Failure
Client: hey-aircon
Source: calendar_write_failure
Time: 2026-04-22T08:14:32Z

Error: GoogleAPIError — 404 calendar not found
Customer: 6591234567
Booking: HA-20260430-A3F2

Calendar event was NOT created. Booking NOT recorded.
Manual booking required — customer has been told to expect a callback.
```

### Tier 1 message example — Supabase booking INSERT fails after calendar success

```
CRITICAL | Booking Backend Failure
Client: hey-aircon
Source: booking_db_insert_failure
Time: 2026-04-22T08:15:01Z

Error: PostgrestAPIError — duplicate key violation
Customer: 6591234567
Booking: HA-20260430-A3F2
Calendar Event: cal_event_abc123 (ALREADY CREATED)

Calendar event exists but DB row is missing.
Manual Supabase insert required to prevent orphaned calendar event.
```

### Tier 1 message example — LLM total failure

```
CRITICAL | LLM Total Failure
Client: hey-aircon
Source: llm_both_failed
Time: 2026-04-22T08:16:45Z

Error: APIConnectionError — connection timeout
Providers failed: Anthropic + OpenAI
Customer: 6591234567

Customer received fallback reply. Agent could not respond.
Monitor Anthropic/OpenAI status pages.
```

### Tier 1 message example — Supabase customer query failure

```
CRITICAL | DB Query Failure — Escalation Gate Blocked
Client: hey-aircon
Source: customer_query_failure
Time: 2026-04-22T08:17:10Z

Error: ConnectionError — Supabase unreachable
Customer: 6591234567

Escalation gate could not run. Customer received fallback reply.
Check Supabase status and per-client DB connectivity.
```

### Tier 2 message example

```
WARNING | Non-critical Failure
Client: hey-aircon
Source: escalation_human_alert
Time: 2026-04-22T08:18:00Z

Error: HTTPStatusError — 400 bad request
Customer: 6591234567

Human agent WhatsApp alert failed. Escalation flag is still set in DB.
Manual follow-up required.
```

### Formatting rules

- Use plain text only — no Markdown bold or italic formatting. Telegram `parse_mode` must remain `"Markdown"` in `_send_telegram_alert()` but the message body must not use `*`, `_`, or backtick characters that would render unpredictably. Exception: backtick-wrapped values are acceptable for IDs and error types only if the architect confirms Telegram Markdown rendering is stable in the target group.
- Tier 1 alerts open with `CRITICAL |`. Tier 2 alerts open with `WARNING |`. No emoji in the header line. (Existing `_BOOKING_FAILURE_ALERT_TEMPLATE` and `log_noncritical_failure` alert text use emoji — these will be replaced with the standardised format above.)
- Every alert must include `client_id` — no alert may be sent without a client identifier.
- Alerts must never include PII beyond the customer's WhatsApp phone number. Do not include full address or customer name in Telegram messages. Those fields remain in the WhatsApp alert to `human_agent_number` only.

---

## Supabase Schema Requirements

### `noncritical_failures` table — existing schema is sufficient

The existing DDL in `observability.py` covers all Tier 2 failure points. The `context` JSONB column absorbs arbitrary per-failure metadata. No schema changes required.

```sql
-- Existing — no changes needed
CREATE TABLE noncritical_failures (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT NOW(),
    source        TEXT NOT NULL,
    error_type    TEXT NOT NULL,
    error_message TEXT,
    client_id     TEXT,
    context       JSONB
);
```

### `api_incidents` table — two columns must be added

The existing schema covers LLM failures. To cover Tier 1 booking and DB failures, two columns are needed:

```sql
-- Existing columns (no change)
-- id, ts, provider, error_type, error_message, client_id, fallback_used, both_failed

-- Add these two columns:
ALTER TABLE api_incidents ADD COLUMN IF NOT EXISTS source TEXT;
-- Values: 'llm_failure' | 'calendar_write_failure' | 'booking_db_insert_failure' | 'customer_query_failure'

ALTER TABLE api_incidents ADD COLUMN IF NOT EXISTS context JSONB;
-- Carries: booking_id, customer_phone, calendar_event_id where applicable
```

**Rationale:** Without `source` and `context`, non-LLM Tier 1 failures written to `api_incidents` have no way to carry booking-specific data (booking_id, calendar_event_id) and the table cannot be queried by failure type without parsing `error_message`.

**Alternative considered:** Use `noncritical_failures` for all non-LLM Tier 1 failures. Rejected — the table name communicates severity. Booking failures are critical; routing them to `noncritical_failures` would misrepresent their impact and pollute Tier 2 queries.

### Migration file

A single migration `005_observability_tables.sql` must:
1. CREATE the `api_incidents`, `api_usage`, and `noncritical_failures` tables (from existing DDL in `observability.py`)
2. ADD the two new columns to `api_incidents`
3. CREATE all indexes (from existing DDL)

The engine must verify that these tables exist at startup before relying on them — a missing table must log a warning, not crash the service.

---

## New Environment Variables Required

These are platform-level vars (not per-client) — set once in Railway for the shared engine service.

| Env Var | Type | Required | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `str` | Yes (to activate) | Bot token from BotFather. If absent, all Telegram paths are silent no-ops (existing behaviour preserved). |
| `TELEGRAM_ALERT_CHAT_ID` | `str` | Yes (to activate) | Numeric chat ID of the internal team group. If absent, all Telegram paths are silent no-ops. |

**Naming convention:** These are not per-client vars — they do not use the `{CLIENT_ID_UPPER}_*` prefix. They are shared platform vars, consistent with `SHARED_SUPABASE_URL` and `SHARED_SUPABASE_SERVICE_KEY` in `settings.py`.

**Settings model update:** Both vars must be added to `engine/config/settings.py` as optional fields with `None` defaults:

```python
telegram_bot_token: str | None = None
telegram_alert_chat_id: str | None = None
```

`_send_telegram_alert()` should read from `settings` rather than `os.environ.get()` directly, consistent with how other platform config is consumed.

---

## Acceptance Criteria

### Tier 1 — Telegram + Supabase wiring

- [ ] When `create_booking_event()` raises any exception in `booking_tools.py`, a Telegram alert is sent with `source=calendar_write_failure` and a row is inserted into `api_incidents`.
- [ ] When `db.table("bookings").insert()` fails after a successful calendar write, a Telegram alert is sent with `source=booking_db_insert_failure`, the `calendar_event_id` is included in the Telegram message and in `api_incidents.context`, and a row is inserted into `api_incidents`.
- [ ] When `log_incident(both_failed=True)` is called in `agent_runner.py`, a Telegram alert is sent. The existing `api_incidents` row write already happens — only Telegram is missing.
- [ ] When the `db.table("customers").select()` call fails at Step 3 of `message_handler.py`, a Telegram alert is sent with `source=customer_query_failure` and a row is inserted into `api_incidents`.
- [ ] All Tier 1 Telegram messages include: severity=CRITICAL, client_id, source, timestamp, error_type, truncated error_message, and applicable context (booking_id, customer_phone, calendar_event_id).

### Tier 2 — Telegram stub implementation

- [ ] `_send_telegram_alert()` in `observability.py` sends a real HTTP POST to `https://api.telegram.org/bot{token}/sendMessage` when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALERT_CHAT_ID` are set.
- [ ] If either env var is absent, `_send_telegram_alert()` remains a silent no-op.
- [ ] `_send_telegram_alert()` never raises — all HTTP errors are caught and logged at `WARNING` level only.
- [ ] Timeout on the Telegram HTTP call is 5 seconds (already specified in stub — must be preserved).
- [ ] When `log_noncritical_failure()` is called (human agent alert failure, Sheets sync failure), the Supabase insert fires first, then the Telegram alert. If the Supabase insert fails, the Telegram alert still fires.

### Sheets sync failure coverage gaps

- [ ] `sync_customer_to_sheets()` called from `message_handler.py` (new customer upsert path) catches exceptions and calls `log_noncritical_failure(source="sheets_sync_customer")`.
- [ ] `sync_booking_to_sheets()` called from `booking_tools.py` catches exceptions and calls `log_noncritical_failure(source="sheets_sync_booking")`.

### Message format

- [ ] All Telegram messages include `client_id` — no alert is sent without it.
- [ ] Tier 1 messages open with `CRITICAL |`. Tier 2 messages open with `WARNING |`.
- [ ] No customer address or full name is included in Telegram messages.
- [ ] Error messages are truncated to 200 characters in the Telegram body.

### Supabase schema

- [ ] Migration `005_observability_tables.sql` creates `api_incidents`, `api_usage`, and `noncritical_failures` tables.
- [ ] `api_incidents` includes `source TEXT` and `context JSONB` columns.
- [ ] Engine startup logs a warning (does not crash) if any observability table is missing.

### Settings

- [ ] `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALERT_CHAT_ID` are added to `engine/config/settings.py` as optional fields.
- [ ] `_send_telegram_alert()` reads from `settings`, not `os.environ.get()` directly.

---

## Out of Scope

- Customer-facing messaging changes. This feature has zero effect on what customers receive.
- Telegram alerting for non-failure events (successful bookings, usage metrics, customer signups). Alerts are for failures only.
- Alert deduplication or rate limiting (e.g. suppressing repeated calendar errors). Can be added in a future iteration when alert volume is known.
- Telegram alert history or a dashboard. Supabase tables are the audit trail.
- PagerDuty, email, or any channel other than Telegram.
- Alert routing by severity to different Telegram chats. One chat, all tiers. Can be split later.
- Modifying `_BOOKING_FAILURE_ALERT_TEMPLATE` (the WhatsApp alert to `human_agent_number`). That channel is preserved as-is alongside the new Telegram path.
- Per-client Telegram channels. All clients share one internal team chat.

---

## Open Questions

None. All questions raised in the brief are resolved above:

1. **Telegram message fields** — resolved in the format spec section. Seven required fields per alert; booking_id and calendar_event_id included in context where applicable. Address and customer name excluded from Telegram (WhatsApp alert path only).
2. **`api_incidents` for Tier 1 + Telegram** — yes, all Tier 1 failures write to `api_incidents` AND trigger Telegram. Both channels fire for every Tier 1 event.
3. **`noncritical_failures` schema sufficiency** — confirmed sufficient as-is. `api_incidents` requires two new columns (`source`, `context`).
4. **Tier 1 vs Tier 2 formatting** — differentiated by header (`CRITICAL |` vs `WARNING |`) only. No separate chats, no emoji-based differentiation.
5. **Env var naming** — `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALERT_CHAT_ID` are platform-level (no client prefix), consistent with `SHARED_SUPABASE_URL` pattern.
