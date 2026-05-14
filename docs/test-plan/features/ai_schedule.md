# AI Schedule & Business Hours — Test Plan

> **Feature Test Plan**  
> Author: @sdet-engineer  
> Date: 2026-05-13  
> Architecture Spec: `docs/architecture/ai_schedule.md`  
> Worktree: `../ai-schedule`  
> Branch: `feat/ai-schedule`

---

## Feature Summary

Adds two independently configurable time windows to control AI agent behavior:
1. **AI Operational Hours** — gate in pipeline that sends auto-reply and stops agent invocation when outside hours
2. **Business Operational Hours** — context-only field for escalation messages (tells customer when human agents are available)

Both stored per-client in shared Supabase `clients` table, TIME data type (HH:MM:SS), with timezone string. Nullable (NULL = 24/7 active for AI hours, no business context for business hours). Supports overnight windows (start > end). Changes take effect within 5 minutes (cached in ClientConfig).

HeyAircon pilot: AI active 18:00–09:00 SGT (after-hours only), business hours 09:00–18:00 SGT.

---

## Implementation Checklist

### 1. Database Migration (supabase/migrations/012_ai_schedule.sql)
- [ ] Create migration file with all 5 columns: `ai_active_start_time`, `ai_active_end_time`, `business_start_time`, `business_end_time`, `timezone`
- [ ] All columns are `TIME` type (not TIMESTAMPTZ), nullable except `timezone` (defaults to 'UTC')
- [ ] Add two constraints: `ai_hours_both_or_neither`, `business_hours_both_or_neither` (prevents one field set while other is NULL)
- [ ] Add column comments for Supabase Studio inline help
- [ ] Update hey-aircon row with pilot defaults (18:00–09:00 AI, 09:00–18:00 business, Asia/Singapore)
- [ ] Include rollback SQL in comments
- [ ] Apply migration to shared Supabase (`nayhqstuupdsqpltseof`)

### 2. ClientConfig Extension (engine/config/client_config.py)
- [ ] Add 5 new fields to `ClientConfig` dataclass: `ai_active_start_time: str | None = None`, `ai_active_end_time: str | None = None`, `business_start_time: str | None = None`, `business_end_time: str | None = None`, `timezone: str = "UTC"`
- [ ] Update `load_client_config()` to read these 5 fields from `clients` table row
- [ ] Existing cache mechanism (5-min TTL) applies — no new cache logic needed

### 3. Schedule Gate (engine/core/message_handler.py)
- [ ] Add new helper function `_is_within_ai_hours(client_config: ClientConfig) -> bool`
  - [ ] Returns True if both AI hours columns are NULL (24/7 active)
  - [ ] Returns True and logs warning if only one AI hours column is set (defensive fallback)
  - [ ] Parses timezone string with ZoneInfo — defaults to UTC if invalid/missing
  - [ ] Gets current time in client timezone
  - [ ] Parses TIME strings (HH:MM:SS format)
  - [ ] Supports daytime windows (start <= end): `start <= current_time < end`
  - [ ] Supports overnight windows (start > end): `current_time >= start or current_time < end`
  - [ ] If start == end, returns False (no active window) and logs warning
- [ ] Add new helper function `_handle_out_of_hours_message()` (async)
  - [ ] Builds auto-reply message — includes business hours if configured (12-hour format with am/pm)
  - [ ] Falls back to generic message if business hours are NULL
  - [ ] Sends auto-reply via `send_message()`
  - [ ] Logs outbound to `interactions_log`
  - [ ] Non-fatal error handling on send/log failures
- [ ] Insert schedule gate in pipeline AFTER escalation gate (Step 4)
  - [ ] Call `_is_within_ai_hours(client_config)` — if False, call `_handle_out_of_hours_message()` and return (stop pipeline)
  - [ ] If True, pipeline continues to agent as normal

### 4. Business Hours in System Prompt (engine/core/context_builder.py) — Optional Enhancement
- [ ] Add business hours context block to `build_system_message()` if both business_start_time and business_end_time are set
- [ ] Format: "Business hours: 9am–6pm (Asia/Singapore). Reference these when escalating outside business hours."
- [ ] This helps agent include business hours in escalation responses (not blocking for core feature)

---

## Unit Tests

### File: `engine/tests/unit/test_schedule_gate.py` (new file)

#### Test 1: `test_is_within_ai_hours_24_7_active`
- **Given:** `ai_active_start_time=None`, `ai_active_end_time=None`
- **When:** `_is_within_ai_hours()` called at any time
- **Then:** Returns `True`

#### Test 2: `test_is_within_ai_hours_daytime_window_inside`
- **Given:** AI hours 09:00–18:00, timezone UTC, current time 12:00 UTC
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `True`

#### Test 3: `test_is_within_ai_hours_daytime_window_outside`
- **Given:** AI hours 09:00–18:00, timezone UTC, current time 20:00 UTC
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `False`

#### Test 4: `test_is_within_ai_hours_overnight_window_inside_before_midnight`
- **Given:** AI hours 18:00–09:00, timezone UTC, current time 20:00 UTC (after start)
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `True`

#### Test 5: `test_is_within_ai_hours_overnight_window_inside_after_midnight`
- **Given:** AI hours 18:00–09:00, timezone UTC, current time 06:00 UTC (before end)
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `True`

#### Test 6: `test_is_within_ai_hours_overnight_window_outside`
- **Given:** AI hours 18:00–09:00, timezone UTC, current time 12:00 UTC (between end and start)
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `False`

#### Test 7: `test_is_within_ai_hours_edge_at_start`
- **Given:** AI hours 09:00–18:00, current time exactly 09:00:00
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `True` (start time is inclusive)

#### Test 8: `test_is_within_ai_hours_edge_at_end`
- **Given:** AI hours 09:00–18:00, current time exactly 18:00:00
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `False` (end time is exclusive)

#### Test 9: `test_is_within_ai_hours_timezone_conversion`
- **Given:** AI hours 18:00–09:00, timezone Asia/Singapore (UTC+8), current wall clock time is 20:00 SGT
- **When:** `_is_within_ai_hours()` called (system time might be 12:00 UTC)
- **Then:** Returns `True` (correctly interprets 20:00 in SGT as within window)

#### Test 10: `test_is_within_ai_hours_invalid_timezone_defaults_utc`
- **Given:** AI hours 09:00–18:00, timezone "Invalid/Bogus"
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns result based on UTC interpretation, logs error about invalid timezone

#### Test 11: `test_is_within_ai_hours_partial_config_logs_warning`
- **Given:** `ai_active_start_time="09:00:00"`, `ai_active_end_time=None`
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `True` (24/7 fallback), logs warning about partial config

#### Test 12: `test_is_within_ai_hours_same_start_end_no_window`
- **Given:** AI hours 09:00–09:00 (start == end)
- **When:** `_is_within_ai_hours()` called
- **Then:** Returns `False`, logs warning

#### Test 13: `test_handle_out_of_hours_message_with_business_hours`
- **Given:** Business hours 09:00–18:00 configured
- **When:** `_handle_out_of_hours_message()` called
- **Then:** Auto-reply includes "Our team operates 9:00am–6:00pm."
- **And:** Message sent via `send_message()`, logged to `interactions_log` with direction='outbound'

#### Test 14: `test_handle_out_of_hours_message_no_business_hours`
- **Given:** Business hours NULL
- **When:** `_handle_out_of_hours_message()` called
- **Then:** Auto-reply says "Our team will respond shortly." (no hours mentioned)
- **And:** Message sent and logged

#### Test 15: `test_handle_out_of_hours_send_failure_non_fatal`
- **Given:** `send_message()` raises exception
- **When:** `_handle_out_of_hours_message()` called
- **Then:** Exception is caught, logged, does NOT propagate
- **And:** Outbound logging still attempted

---

## Integration Tests

### File: `engine/tests/integration/test_schedule_gate_pipeline.py` (new file)

#### Test 1: `test_out_of_hours_message_sends_auto_reply_stops_pipeline`
- **Given:** Client with AI hours 09:00–18:00 UTC, current time 20:00 UTC (outside hours)
- **When:** Inbound webhook arrives ("Hi, I need aircon service")
- **Then:** Auto-reply sent ("Thanks for reaching out! Our team operates 9:00am–6:00pm. A team member will respond shortly.")
- **And:** Inbound logged to `interactions_log`
- **And:** Outbound logged to `interactions_log`
- **And:** Agent does NOT run (no context builder call, no tool calls)
- **And:** Customer does NOT receive agent-generated reply

#### Test 2: `test_within_hours_message_runs_agent_normally`
- **Given:** Client with AI hours 09:00–18:00 UTC, current time 12:00 UTC (within hours)
- **When:** Inbound webhook arrives ("Hi, I need aircon service")
- **Then:** Agent runs normally (context builder → agent runner → tools)
- **And:** Customer receives agent-generated reply (not auto-reply)
- **And:** Schedule gate passes silently (does NOT send auto-reply)

#### Test 3: `test_24_7_active_no_gate_interference`
- **Given:** Client with `ai_active_start_time=NULL`, `ai_active_end_time=NULL`
- **When:** Inbound webhook arrives at any time (test at 03:00 UTC, 15:00 UTC, 23:00 UTC)
- **Then:** Agent runs normally (schedule gate returns True immediately)
- **And:** No auto-reply sent

#### Test 4: `test_overnight_window_before_midnight`
- **Given:** Client with AI hours 18:00–09:00 UTC, current time 20:00 UTC
- **When:** Inbound webhook arrives
- **Then:** Agent runs normally (within window)
- **And:** No auto-reply sent

#### Test 5: `test_overnight_window_after_midnight`
- **Given:** Client with AI hours 18:00–09:00 UTC, current time 03:00 UTC
- **When:** Inbound webhook arrives
- **Then:** Agent runs normally (within window)
- **And:** No auto-reply sent

#### Test 6: `test_overnight_window_outside_midday`
- **Given:** Client with AI hours 18:00–09:00 UTC, current time 12:00 UTC (between 09:00 and 18:00)
- **When:** Inbound webhook arrives
- **Then:** Auto-reply sent, agent does NOT run

#### Test 7: `test_schedule_gate_runs_after_escalation_gate`
- **Given:** Customer with `escalation_flag=True`, AI hours 20:00–23:00, current time 22:00 (within AI hours)
- **When:** Inbound webhook arrives
- **Then:** Escalation gate fires first (holding reply sent, pipeline stops)
- **And:** Schedule gate never runs (pipeline already stopped)
- **And:** Customer does NOT receive auto-reply (already received holding reply)

#### Test 8: `test_escalated_customer_outside_ai_hours`
- **Given:** Customer with `escalation_flag=True`, AI hours 09:00–18:00, current time 20:00 (outside)
- **When:** Inbound webhook arrives
- **Then:** Escalation gate fires first (holding reply sent once if not already notified)
- **And:** Pipeline stops before schedule gate
- **And:** No auto-reply sent (escalation holding reply takes precedence)

---

## Regression Tests

All existing tests must continue to pass:
- [ ] `engine/tests/unit/test_message_handler.py` — ensure existing pipeline tests pass (escalation gate, opt-out detection, lock acquisition)
- [ ] `engine/tests/integration/test_webhook_to_reply.py` — full webhook flow still works when AI hours are NULL (24/7 active)
- [ ] `engine/tests/eval/` — all eval tests pass (agent behavior unchanged within AI hours)

### Specific regression checks:
- [ ] Existing client (hey-aircon) with NULL AI hours (before migration) → behaves as 24/7 active (no auto-reply)
- [ ] Human agent routing still works (if `phone_number == human_agent_number`, routed to reset handler — schedule gate never runs for human agent messages)

---

## Manual Verification Steps

### Verify in staging/production (post-merge):

1. **Supabase Studio check:**
   - [ ] Open shared Supabase (`nayhqstuupdsqpltseof`) → `clients` table
   - [ ] Confirm hey-aircon row shows: `ai_active_start_time=18:00:00`, `ai_active_end_time=09:00:00`, `business_start_time=09:00:00`, `business_end_time=18:00:00`, `timezone=Asia/Singapore`
   - [ ] Edit `ai_active_start_time` to 19:00:00, save — changes should take effect within 5 minutes (wait, then test)

2. **Out-of-hours message (HeyAircon pilot):**
   - [ ] At 12:00 SGT (midday, outside 18:00–09:00 window): send test message from customer phone to HeyAircon WhatsApp number
   - [ ] Customer receives: "Thanks for reaching out! Our team operates 9:00am–6:00pm. A team member will respond shortly."
   - [ ] Check `interactions_log` in Supabase: inbound + outbound both logged
   - [ ] Human agent WhatsApp does NOT receive any alert (silent queue — no forwarding in Phase 1)
   - [ ] Send follow-up message from same customer: still receives auto-reply (agent still not active)

3. **Within-hours message (HeyAircon pilot):**
   - [ ] At 20:00 SGT (evening, within 18:00–09:00 window): send test message from customer phone
   - [ ] Customer receives agent-generated reply (normal booking flow, not auto-reply)
   - [ ] Agent offers slots, asks for address, runs normally

4. **Overnight window (HeyAircon pilot):**
   - [ ] At 01:00 SGT (after midnight, within 18:00–09:00 window): send test message
   - [ ] Customer receives agent-generated reply (not auto-reply)
   - [ ] Confirms overnight window logic works

5. **Business hours in escalation message (manual spot check):**
   - [ ] Trigger an escalation during AI hours (ask unanswerable question, see Task 2)
   - [ ] If business hours are passed in system prompt, agent should naturally reference them: "Our team operates 9am–6pm and will follow up during business hours."
   - [ ] Not a blocking gate — just verify the agent uses context if provided

6. **24/7 client (if testing with a second client):**
   - [ ] Set up a test client with `ai_active_start_time=NULL`, `ai_active_end_time=NULL`
   - [ ] Send messages at various times (03:00, 12:00, 22:00) — agent should always respond, never auto-reply

7. **Config change propagation:**
   - [ ] Edit `ai_active_start_time` in Supabase Studio (e.g., change 18:00 to 17:00)
   - [ ] Wait 6 minutes (cache TTL + 1 min buffer)
   - [ ] Send test message at 17:30 — agent should now be active (respects new config)

---

## Definition of Done

- [ ] Migration 012 applied to shared Supabase and verified in Supabase Studio
- [ ] All 5 new fields present in `ClientConfig` dataclass and loaded correctly
- [ ] `_is_within_ai_hours()` implemented with all edge cases handled (overnight, timezone, partial config, same start/end)
- [ ] `_handle_out_of_hours_message()` implemented with business hours formatting (12-hour am/pm)
- [ ] Schedule gate inserted in correct pipeline position (after escalation, before agent)
- [ ] All 15 unit tests pass
- [ ] All 8 integration tests pass
- [ ] All regression tests pass (existing test suite remains green)
- [ ] Manual verification completed for all 7 scenarios above
- [ ] HeyAircon pilot defaults confirmed in production
- [ ] Code formatted (`mix format` / project formatter)
- [ ] No linter errors
- [ ] Merged to main via PR (or direct merge if repo does not use PRs)
