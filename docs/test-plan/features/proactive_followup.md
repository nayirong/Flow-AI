# Proactive Follow-up Flow — Test Plan

**Feature ID:** REQ-FOLLOWUP-001  
**Test Plan Version:** 1.0  
**Created:** 2026-04-23  
**Owner:** @sdet-engineer  
**Status:** Ready for Implementation

---

## Feature Overview

The Proactive Follow-up Flow implements automated, timed WhatsApp check-ins for customers who book appointments but remain silent post-confirmation. The feature introduces a two-phase booking confirmation flow (`write_booking` → pending, `confirm_booking` → confirmed) and a background scheduler that sends follow-up messages at T+2h, T+24h, and marks bookings abandoned at T+48h if no customer response.

**Key architectural components:**
- **Tool refactor:** `write_booking` no longer creates calendar events (breaking change)
- **New tool:** `confirm_booking` — slot conflict check + calendar event creation
- **Scheduler:** APScheduler running in-process, queries per-client Supabase every 60 minutes
- **Opt-out handling:** Keyword detection in `message_handler.py` (pre-agent gate)

**Migration risk:** HIGH — `write_booking` behavior change affects all active booking flows. Requires DDL-first deployment and backward-compatibility handling.

---

## Test Scenarios

### Scenario 1: Happy Path — Two-Phase Booking Confirmation

**Context:** Customer books an appointment and confirms immediately when prompted.

**Steps:**
1. Customer sends: "I need aircon servicing"
2. Agent collects details (service, units, address, postal code)
3. Agent calls `check_calendar_availability` for customer's requested date
4. Customer selects a slot (e.g., "25 April PM slot")
5. Agent calls `write_booking` with collected details
6. Agent receives `{booking_id, status: 'pending_confirmation', ...}`
7. Agent sends booking summary to customer: "Here's your booking summary... Please confirm."
8. Customer replies: "yes, confirm"
9. Agent detects confirmation intent, calls `confirm_booking(booking_id)`
10. Tool checks Google Calendar for slot conflict (none found)
11. Tool creates calendar event, updates `booking_status = 'confirmed'`
12. Agent replies: "✅ Your booking is confirmed! Reference: [booking_id]"

**Expected outcomes:**
- `bookings` table: 1 row with `booking_status = 'confirmed'`, `calendar_event_id` populated
- Google Calendar: 1 event created for the slot
- `interactions_log`: inbound + outbound messages logged
- No follow-up messages triggered (customer replied after booking creation)

**Validation:**
```bash
cd engine
pytest tests/unit/test_booking_tools.py::test_write_booking_creates_pending_booking -v
pytest tests/unit/test_confirm_booking_tool.py::test_confirm_booking_success_path -v
pytest tests/integration/test_two_phase_booking_flow.py::test_happy_path -v
```

---

### Scenario 2: Slot Conflict at Confirmation Time

**Context:** Two customers create pending bookings for the same slot; first to confirm wins.

**Steps:**
1. Customer A creates pending booking for 25 April PM slot at 10:00 AM
2. Customer B creates pending booking for same slot at 10:05 AM (no conflict yet — `check_calendar_availability` sees no calendar event)
3. Customer A confirms at 10:10 AM → `confirm_booking` succeeds, calendar event created
4. Customer B confirms at 10:11 AM → `confirm_booking` detects conflict (Customer A's event exists)
5. Agent tells Customer B: "Sorry, that slot has just been taken. Let me check alternatives."
6. Agent calls `check_calendar_availability` to offer Customer B other slots

**Expected outcomes:**
- Customer A: `booking_status = 'confirmed'`, calendar event created
- Customer B: `booking_status = 'cancelled'`, `cancellation_reason = 'slot_conflict'`
- Customer B receives conflict message + alternative slot options
- No data corruption, no orphaned calendar events

**Validation:**
```bash
pytest tests/unit/test_confirm_booking_tool.py::test_confirm_booking_slot_conflict -v
pytest tests/integration/test_two_phase_booking_flow.py::test_slot_conflict_race_condition -v
```

---

### Scenario 3: T+2h Follow-up Triggered

**Context:** Customer creates a pending booking but never replies to the confirmation summary.

**Steps:**
1. Customer creates pending booking at 10:00 AM (`booking_status = 'pending_confirmation'`)
2. Agent sends booking summary, customer goes silent
3. Scheduler runs at 12:05 PM (T+2h 5min elapsed)
4. Scheduler query finds eligible booking (no inbound messages after `created_at`)
5. Scheduler sends T+2h follow-up message to customer
6. Scheduler updates: `followup_stage = '2h_sent'`, `last_followup_sent_at = 12:05 PM`
7. Outbound message logged to `interactions_log`

**Expected outcomes:**
- `bookings` table: `followup_stage = '2h_sent'`, `last_followup_sent_at` populated
- `interactions_log`: 1 outbound message with T+2h template text
- Customer receives WhatsApp message matching T+2h template
- `scheduler_runs` table: 1 row logged with `bookings_t2h = 1`, `messages_sent_success = 1`

**Validation:**
```bash
pytest tests/unit/test_followup_scheduler.py::test_t2h_eligibility_query -v
pytest tests/unit/test_followup_scheduler.py::test_t2h_message_send -v
pytest tests/integration/test_followup_flow.py::test_t2h_trigger -v
```

---

### Scenario 4: T+24h Follow-up Triggered

**Context:** Customer received T+2h follow-up but still hasn't replied.

**Steps:**
1. Booking received T+2h follow-up at 12:00 PM Day 1 (`followup_stage = '2h_sent'`)
2. Customer sends no inbound messages
3. Scheduler runs at 12:05 PM Day 2 (T+24h 5min elapsed since last follow-up)
4. Scheduler query finds eligible booking (no inbound messages after `last_followup_sent_at`)
5. Scheduler sends T+24h follow-up message
6. Scheduler updates: `followup_stage = '24h_sent'`, `last_followup_sent_at = 12:05 PM Day 2`

**Expected outcomes:**
- `bookings` table: `followup_stage = '24h_sent'`, `last_followup_sent_at` updated
- Customer receives T+24h message
- `scheduler_runs` table: `bookings_t24h = 1`

**Validation:**
```bash
pytest tests/unit/test_followup_scheduler.py::test_t24h_eligibility_query -v
pytest tests/unit/test_followup_scheduler.py::test_t24h_message_send -v
```

---

### Scenario 5: T+48h Abandon Mark Applied

**Context:** Customer received T+24h follow-up but still hasn't replied.

**Steps:**
1. Booking received T+24h follow-up at 12:00 PM Day 2 (`followup_stage = '24h_sent'`)
2. Customer sends no inbound messages
3. Scheduler runs at 12:05 PM Day 3 (T+48h 5min elapsed since last follow-up)
4. Scheduler query finds eligible booking
5. Scheduler marks booking: `booking_status = 'abandoned'`, `followup_stage = 'abandoned'`, `abandoned_at = NOW()`
6. **No message sent to customer**

**Expected outcomes:**
- `bookings` table: `booking_status = 'abandoned'`, `followup_stage = 'abandoned'`, `abandoned_at` populated
- No outbound message sent
- `scheduler_runs` table: `bookings_abandoned = 1`

**Validation:**
```bash
pytest tests/unit/test_followup_scheduler.py::test_t48h_eligibility_query -v
pytest tests/unit/test_followup_scheduler.py::test_t48h_abandon_mark -v
```

---

### Scenario 6: Customer Reply Stops Follow-up Sequence

**Context:** Customer replies after receiving T+2h follow-up.

**Steps:**
1. Booking received T+2h follow-up at 12:00 PM (`followup_stage = '2h_sent'`)
2. Customer replies at 1:00 PM: "yes, confirm"
3. Agent calls `confirm_booking`, booking confirmed
4. Scheduler runs at 12:05 PM next day (T+24h window)
5. Scheduler query excludes this booking (inbound message exists after `last_followup_sent_at`)
6. No T+24h message sent

**Expected outcomes:**
- Booking progressed to `confirmed` status
- `followup_stage` remains `'2h_sent'` (not advanced to `'24h_sent'`)
- No T+24h or T+48h follow-ups triggered

**Validation:**
```bash
pytest tests/unit/test_followup_scheduler.py::test_customer_reply_stops_followup -v
pytest tests/integration/test_followup_flow.py::test_reply_after_t2h -v
```

---

### Scenario 7: Escalated Customer Excluded from Follow-ups

**Context:** Customer is escalated before T+2h follow-up runs.

**Steps:**
1. Customer creates pending booking at 10:00 AM
2. Customer later escalated (e.g., complaint) → `escalation_flag = True` set at 11:00 AM
3. Scheduler runs at 12:05 PM (T+2h elapsed)
4. Scheduler query excludes booking (escalation gate: `WHERE escalation_flag = FALSE`)
5. No follow-up message sent

**Expected outcomes:**
- Booking remains `pending_confirmation`, `followup_stage = NULL`
- No follow-up messages sent while `escalation_flag = True`
- If `escalation_flag` cleared later, booking becomes eligible again (if still within T+48h window)

**Validation:**
```bash
pytest tests/unit/test_followup_scheduler.py::test_escalated_customer_excluded -v
```

---

### Scenario 8: Opt-Out Keyword Detection

**Context:** Customer replies to a follow-up message with "stop".

**Steps:**
1. Customer receives T+2h follow-up message
2. Customer replies: "stop"
3. `message_handler.py` opt-out detector matches keyword (case-insensitive)
4. Handler updates: `followup_stage = 'opted_out'`
5. Handler sends opt-out confirmation reply: "Understood! We won't send any more follow-up messages..."
6. Handler stops (agent not invoked)
7. Scheduler runs at T+24h window
8. Scheduler query excludes booking (`followup_stage = 'opted_out'`)
9. No further follow-ups sent

**Expected outcomes:**
- `bookings` table: `followup_stage = 'opted_out'`
- Customer receives opt-out confirmation message
- No T+24h or T+48h follow-ups triggered
- `booking_status` unchanged (still `pending_confirmation` unless customer explicitly cancels)

**Validation:**
```bash
pytest tests/unit/test_message_handler.py::test_opt_out_keyword_detection -v
pytest tests/unit/test_followup_scheduler.py::test_opted_out_booking_excluded -v
```

---

### Scenario 9: Scheduler Idempotency — No Duplicate Messages

**Context:** Scheduler runs twice in quick succession (e.g., service restart).

**Steps:**
1. Booking eligible for T+2h follow-up at 12:00 PM
2. Scheduler Run 1 at 12:05 PM: processes booking, sends message, updates `followup_stage = '2h_sent'`
3. Scheduler Run 2 at 12:06 PM (1 minute later): queries for eligible bookings
4. Booking not returned (query excludes `followup_stage = '2h_sent'`)
5. No duplicate message sent

**Expected outcomes:**
- Customer receives exactly 1 T+2h message
- `followup_stage` updated only once
- `scheduler_runs` table: 2 rows (Run 1: `bookings_t2h = 1`, Run 2: `bookings_t2h = 0`)

**Validation:**
```bash
pytest tests/unit/test_followup_scheduler.py::test_idempotency_no_duplicates -v
```

---

### Scenario 10: Meta API Failure Handling

**Context:** Meta API returns 500 error when scheduler tries to send T+2h message.

**Steps:**
1. Booking eligible for T+2h follow-up
2. Scheduler calls `send_message()`, Meta API returns 500 error
3. Scheduler catches exception, logs to `api_incidents` table
4. Booking's `followup_stage` remains `NULL` (not marked as sent)
5. Scheduler run completes, logs metrics: `messages_sent_failed = 1`
6. Scheduler runs again 1 hour later
7. Booking still eligible (retry attempt)
8. Meta API succeeds this time, message sent, `followup_stage = '2h_sent'`

**Expected outcomes:**
- `api_incidents` table: 1 row with error details (provider: 'meta', status_code: 500)
- Booking retried on next run (no permanent failure state)
- Customer eventually receives message after Meta recovers

**Validation:**
```bash
pytest tests/unit/test_followup_scheduler.py::test_meta_api_failure_handling -v
pytest tests/integration/test_followup_flow.py::test_scheduler_resilience -v
```

---

### Scenario 11: Late Customer Confirmation (Slot Still Free)

**Context:** Customer confirms 5 days after creating pending booking.

**Steps:**
1. Customer creates pending booking at 10:00 AM Day 1
2. Booking receives T+2h follow-up (no reply)
3. Booking receives T+24h follow-up (no reply)
4. Booking marked abandoned at T+48h
5. Customer replies "yes, confirm" on Day 6
6. Agent calls `confirm_booking(booking_id)`
7. Tool queries Google Calendar — no conflict (slot still free)
8. Tool creates calendar event, updates `booking_status = 'confirmed'`
9. Agent confirms to customer

**Expected outcomes:**
- Booking status changes from `'abandoned'` → `'confirmed'`
- Calendar event created successfully
- Customer receives confirmation message

**Validation:**
```bash
pytest tests/unit/test_confirm_booking_tool.py::test_late_confirmation_slot_free -v
```

---

### Scenario 12: Late Customer Confirmation (Slot Taken)

**Context:** Customer confirms late, but slot has been booked by another customer.

**Steps:**
1. Customer A creates pending booking, never confirms, marked abandoned at T+48h
2. Customer B books the same slot later, confirms, calendar event created
3. Customer A replies "yes, confirm" days later
4. Agent calls `confirm_booking(booking_id_A)`
5. Tool queries Google Calendar — conflict detected (Customer B's event exists)
6. Tool returns `{status: 'conflict', error: 'slot_no_longer_available', ...}`
7. Agent tells Customer A: "Sorry, that slot is no longer available. Let me find you another slot."
8. Agent calls `check_calendar_availability` to offer alternatives

**Expected outcomes:**
- Customer A's booking: `booking_status = 'cancelled'`, `cancellation_reason = 'slot_conflict'`
- No calendar event created for Customer A
- Customer A receives conflict message + alternative slot options

**Validation:**
```bash
pytest tests/unit/test_confirm_booking_tool.py::test_late_confirmation_slot_taken -v
```

---

### Scenario 13: LLM Confirmation Intent Detection (Affirmative Cases)

**Context:** Agent detects various forms of customer confirmation.

**Test cases:**
- "yes" → calls `confirm_booking` ✅
- "ok" → calls `confirm_booking` ✅
- "confirm" → calls `confirm_booking` ✅
- "sounds good" → calls `confirm_booking` ✅
- "ok lah" (Singlish) → calls `confirm_booking` ✅
- "can" (Singlish) → calls `confirm_booking` ✅
- "👍" (emoji) → calls `confirm_booking` ✅
- "yep yep" → calls `confirm_booking` ✅

**Expected outcome:** Agent correctly identifies affirmative intent and calls `confirm_booking` for all cases.

**Validation:**
```bash
pytest tests/eval/test_confirmation_intent_detection.py::test_affirmative_cases -v
```

---

### Scenario 14: LLM Non-Confirmation Detection

**Context:** Agent must NOT call `confirm_booking` for ambiguous or negative replies.

**Test cases:**
- "wait" → agent does NOT call `confirm_booking` ✅
- "can I change the date?" → agent handles as reschedule request ✅
- "how much is it?" → agent answers question, does not confirm ✅
- "ok, but I need morning slot" → agent offers morning slot, does not confirm original slot ✅
- "yes, I understand, but..." → agent continues conversation, does not confirm ✅

**Expected outcome:** Agent does NOT call `confirm_booking` for any of these cases. Booking remains `pending_confirmation`.

**Validation:**
```bash
pytest tests/eval/test_confirmation_intent_detection.py::test_non_confirmation_cases -v
```

---

## Integration Points Being Tested

### 1. Supabase (Per-Client DB)

**Tables modified/queried:**
- `bookings`: 3 new columns (`last_followup_sent_at`, `followup_stage`, `abandoned_at`), `booking_status` enum change
- `customers`: `escalation_flag` check (escalation gate)
- `interactions_log`: inbound/outbound message logging, silence detection via timestamp queries
- `config`: follow-up config loading (thresholds, templates, feature toggle)

**Key interactions:**
- Scheduler queries `bookings` with complex filters (status, stage, timestamps, NOT EXISTS subquery)
- Scheduler updates `bookings` (stage, timestamps) after processing
- Opt-out handler updates `followup_stage`

**Validation:**
- All queries must return correct result sets (unit tests with mock DB)
- All updates must be atomic (no partial writes)
- Indexes must be used (check query plans in Supabase Studio)

---

### 2. Supabase (Shared DB)

**Tables modified/queried:**
- `clients`: loaded by scheduler to get active client list
- `scheduler_runs`: new table for observability (logs per-run metrics)

**Key interactions:**
- Scheduler iterates over `clients` table (`is_active = true`)
- Scheduler inserts 1 row per run to `scheduler_runs` with aggregate metrics

**Validation:**
- Scheduler must handle client config loading failures gracefully (skip client, log error)
- `scheduler_runs` inserts must never fail (use fire-and-forget pattern)

---

### 3. Meta Cloud API (WhatsApp Messages)

**Endpoints called:**
- `POST /v19.0/{phone_number_id}/messages` — send follow-up messages

**Error scenarios to test:**
- 500 error → logged to `api_incidents`, booking not marked as sent, retried next run
- Timeout → same handling as 500
- Rate limit (429) → same handling as 500
- Success (200) → booking marked as sent, outbound logged

**Validation:**
```bash
pytest tests/integration/test_meta_api_failures.py -v
```

---

### 4. Google Calendar API

**Endpoints called:**
- `events.insert` — create calendar event at confirmation time (`confirm_booking`)
- `freebusy.query` — check slot availability (`confirm_booking` slot conflict check)

**Error scenarios to test:**
- 404 error (calendar not shared) → alert human agent, return error to agent
- 500 error → alert human agent, return error to agent
- Success → calendar event created, `calendar_event_id` returned

**Validation:**
```bash
pytest tests/integration/test_calendar_integration.py::test_confirm_booking_calendar_event -v
```

---

### 5. APScheduler (In-Process Scheduler)

**Lifecycle events:**
- Startup: scheduler initialized in `main.py` `@app.on_event("startup")`
- Runtime: job runs every 60 minutes (configurable via env var)
- Shutdown: scheduler stopped gracefully in `@app.on_event("shutdown")`

**Key interactions:**
- Scheduler job function is async (runs in FastAPI event loop)
- Job function catches all exceptions (never crashes the scheduler)
- Job function logs start/end of each run

**Validation:**
```bash
# Functional tests
pytest tests/unit/test_followup_scheduler.py::test_scheduler_job_runs -v

# Manual verification (Railway logs after deploy)
# Look for: "Proactive follow-up scheduler started (interval: 60 minutes)"
# Look for: "Scheduler run completed: clients=1, t2h=0, t24h=0, abandoned=0, runtime=1234ms"
```

---

## Expected Outcomes Summary

| Scenario | Booking Status | Calendar Event | Follow-up Stage | Customer Message |
|----------|---------------|----------------|-----------------|------------------|
| Happy path (immediate confirm) | `confirmed` | Created | N/A (no follow-ups) | Confirmation message |
| Slot conflict at confirm time | `cancelled` | Not created | N/A | Conflict message + alternatives |
| T+2h follow-up sent | `pending_confirmation` | Not created | `'2h_sent'` | T+2h template |
| T+24h follow-up sent | `pending_confirmation` | Not created | `'24h_sent'` | T+24h template |
| T+48h abandon mark | `abandoned` | Not created | `'abandoned'` | No message |
| Customer reply after T+2h | `confirmed` (if confirms) | Created | `'2h_sent'` (not advanced) | Confirmation message |
| Escalated customer | `pending_confirmation` | Not created | NULL (never advances) | No follow-ups |
| Opt-out | `pending_confirmation` | Not created | `'opted_out'` | Opt-out confirmation |
| Late confirm (slot free) | `confirmed` | Created | Any (doesn't matter) | Confirmation message |
| Late confirm (slot taken) | `cancelled` | Not created | Any | Conflict message |

---

## Acceptance Criteria Mapping

| AC ID | Requirement | Implemented In | Test Coverage |
|-------|-------------|----------------|---------------|
| **AC-FOLLOWUP-01** | T+2h follow-up triggers correctly | Slice 4 (scheduler) | Scenario 3, unit test `test_t2h_eligibility_query` |
| **AC-FOLLOWUP-02** | T+24h follow-up triggers correctly | Slice 4 (scheduler) | Scenario 4, unit test `test_t24h_eligibility_query` |
| **AC-FOLLOWUP-03** | T+48h abandon mark applied | Slice 4 (scheduler) | Scenario 5, unit test `test_t48h_abandon_mark` |
| **AC-FOLLOWUP-04** | Customer reply stops follow-up sequence | Slice 4 (scheduler silence detection) | Scenario 6, unit test `test_customer_reply_stops_followup` |
| **AC-FOLLOWUP-05** | Escalated customers excluded | Slice 4 (scheduler query filter) | Scenario 7, unit test `test_escalated_customer_excluded` |
| **AC-FOLLOWUP-06** | Opt-out stops follow-ups | Slice 3 (opt-out handler) | Scenario 8, unit test `test_opt_out_keyword_detection` |
| **AC-FOLLOWUP-07** | Idempotency — no duplicate messages | Slice 4 (scheduler `followup_stage` check) | Scenario 9, unit test `test_idempotency_no_duplicates` |
| **AC-FOLLOWUP-08** | Meta API failure handling | Slice 4 (scheduler error handling) | Scenario 10, unit test `test_meta_api_failure_handling` |
| **AC-FOLLOWUP-09** | Customer re-engages after abandon mark | Slice 2 (`confirm_booking` tool) | Scenario 11, unit test `test_late_confirmation_slot_free` |
| **AC-FOLLOWUP-10** | Message copy matches persona | Slice 4 (message templates in `config` table) | Manual review of `config` rows |
| **AC-FOLLOWUP-11** | Slot conflict detection on confirmation | Slice 2 (`confirm_booking` tool) | Scenario 2, unit test `test_confirm_booking_slot_conflict` |
| **AC-FOLLOWUP-12** | Slot conflict detected at `confirm_booking` time | Slice 2 (`confirm_booking` slot conflict check) | Scenario 2, unit test `test_confirm_booking_slot_conflict` |
| **AC-FOLLOWUP-13** | LLM detects confirmation intent (affirmative) | Slice 1 (system prompt update) | Scenario 13, eval test `test_affirmative_cases` |
| **AC-FOLLOWUP-14** | LLM does not misclassify non-confirmations | Slice 1 (system prompt update) | Scenario 14, eval test `test_non_confirmation_cases` |
| **AC-FOLLOWUP-15** | Confirmation intent detection handles Singlish | Slice 1 (system prompt update) | Scenario 13, eval test `test_affirmative_cases` |
| **AC-FOLLOWUP-16** | Late confirmation (slot still free) | Slice 2 (`confirm_booking` tool) | Scenario 11, unit test `test_late_confirmation_slot_free` |
| **AC-FOLLOWUP-17** | Late confirmation (slot taken) | Slice 2 (`confirm_booking` tool) | Scenario 12, unit test `test_late_confirmation_slot_taken` |

---

## Deployment Sequence (MANDATORY)

**CRITICAL:** Follow this exact sequence to avoid breaking production. Steps must be executed in order.

| Step | Action | Owner | Gate |
|------|--------|-------|------|
| **1. DDL — Bookings Table** | Run `ALTER TABLE bookings ADD COLUMN last_followup_sent_at TIMESTAMPTZ, ADD COLUMN followup_stage TEXT, ADD COLUMN abandoned_at TIMESTAMPTZ;` + create indexes (see architecture doc §3.1) | Founder (Supabase Studio) | **BEFORE code deploy** |
| **2. DDL — Scheduler Runs Table** | Create `scheduler_runs` table in shared Supabase (see architecture doc §3.3) | Founder (Supabase Studio) | **BEFORE code deploy** |
| **3. Data Migration** | Run `UPDATE bookings SET booking_status = 'confirmed' WHERE booking_status = 'Confirmed';` (normalize old bookings) | Founder (Supabase Studio) | **Immediately after Step 1** |
| **4. Config Rows** | Insert 8 new config rows into per-client `config` table: `followup_t1_hours`, `followup_t2_hours`, `followup_abandon_hours`, `followup_enabled`, `followup_scheduler_interval_minutes`, `followup_t1_message_template`, `followup_t2_message_template`, `followup_optout_reply` (see requirements doc) | Founder (Supabase Studio) | **BEFORE code deploy** |
| **5. Slice 1 Deploy** | Deploy Slice 1 code to Railway (schema-compatible `write_booking` refactor + system prompt update) | SDET (after Slice 1 PR merged) | **After Steps 1–4** |
| **6. Slice 1 Verification** | Verify existing booking flow works end-to-end with new pending status: customer books → pending → confirms → confirmed + calendar event | SDET (manual test in production) | **PASS required before Slice 2** |
| **7. Slice 2 Deploy** | Deploy Slice 2 code (`confirm_booking` tool) | SDET (after Slice 2 PR merged) | **After Slice 1 verification** |
| **8. Slice 2 Verification** | Verify full two-phase booking flow: write → pending → confirm → confirmed + calendar event | SDET (manual test) | **PASS required before Slice 3** |
| **9. Slice 3 Deploy** | Deploy Slice 3 code (opt-out handler) | SDET (after Slice 3 PR merged) | **After Slice 2 verification** |
| **10. Slice 3 Verification** | Test opt-out keywords stop follow-up sequence | SDET (manual test: send "stop" to agent) | **PASS required before Slice 4** |
| **11. Slice 4 Deploy** | Deploy Slice 4 code (scheduler + APScheduler startup) | SDET (after Slice 4 PR merged) | **After Slice 3 verification** |
| **12. Scheduler Start Verification** | Check Railway logs for "Proactive follow-up scheduler started (interval: 60 minutes)" | SDET (Railway logs) | **Immediate after Slice 4 deploy** |
| **13. First Scheduler Run** | Wait 60 minutes, check Railway logs for scheduler job execution ("Scheduler run completed: ...") | SDET (Railway logs) | **1 hour after Slice 4 deploy** |
| **14. Monitor Incidents** | Query shared Supabase `api_incidents` for scheduler-related errors | SDET (Supabase Studio) | **24 hours after Slice 4 deploy** |

**Rollback plan (if Slice 1 breaks existing bookings):**
- Redeploy previous engine version (old `write_booking` behavior)
- Scheduler will not run (no Slice 4 code deployed yet)
- Fix code, repeat Slice 1 verification

**Rollback plan (if scheduler fails):**
- Set `followup_enabled = false` in per-client `config` table → scheduler skips all clients
- Investigate errors in Railway logs + `api_incidents` table
- Fix code, redeploy Slice 4
- Set `followup_enabled = true` to resume

---

## Open Questions / Risks Flagged

### Risk 1: Confirmation Intent Detection False Negatives

**Risk:** LLM fails to detect confirmation when customer uses uncommon phrasing (e.g., regional dialect, typos).

**Impact:** Customer says "yes" but agent doesn't call `confirm_booking` → booking remains pending → follow-up sequence triggers.

**Mitigation:**
- Test with diverse confirmation phrasing in eval suite (Scenario 13)
- Monitor `pending_confirmation` → `abandoned` rate post-launch
- If false negative rate >10%, add explicit confirmation guardrail prompt or fallback keyword check

**Blocker?** No — recoverable via follow-up sequence. Monitor post-launch.

---

### Risk 2: Scheduler Clock Drift (Max Delay ~3h for T+2h)

**Risk:** Scheduler runs every 60 minutes → max delay between eligibility and actual message send is 2h 59m 59s.

**Impact:** Customer might perceive follow-up as "too late" if it arrives 3 hours after booking instead of 2.

**Mitigation:**
- Architecture doc confirms this is acceptable for Phase 1 (§2.3)
- If customer feedback indicates timing issues post-launch, reduce scheduler interval to 15 minutes (4x overhead)

**Blocker?** No — founder has approved 60-minute interval.

---

### Risk 3: Double-Booking Race Window (No Slot Reservation at `pending_confirmation`)

**Risk:** Two customers create `pending_confirmation` bookings for the same slot simultaneously.

**Impact:** Both see the slot as available; first to confirm wins, second gets conflict error.

**Mitigation:**
- `confirm_booking` tool checks Google Calendar for conflicts (catches race condition)
- Agent offers alternatives to losing customer
- Monitor conflict rate via `api_incidents` post-launch

**Blocker?** No — founder decision 2026-04-22 to NOT implement slot reservation in Phase 1.

---

### Risk 4: Meta API Rate Limiting

**Risk:** At scale (100+ bookings/day), follow-up messages might hit Meta's rate limits (1000 msg/day tier).

**Impact:** Messages fail to send, customers don't receive follow-ups.

**Mitigation:**
- Phase 1 volume (HeyAircon): ~10 bookings/day → ~20 follow-up messages/day (well below limit)
- Monitor `scheduler_runs.messages_sent_failed` post-launch
- If rate limits hit, batch messages or upgrade Meta tier

**Blocker?** No — Phase 1 volume is safe.

---

## Total Estimated Test Count

| Test Type | Count | Location |
|-----------|-------|----------|
| Unit tests (Slice 1 — `write_booking` refactor) | 3 | `tests/unit/test_booking_tools.py` |
| Unit tests (Slice 2 — `confirm_booking` tool) | 5 | `tests/unit/test_confirm_booking_tool.py` |
| Unit tests (Slice 3 — opt-out handler) | 2 | `tests/unit/test_message_handler.py` |
| Unit tests (Slice 4 — scheduler job) | 8 | `tests/unit/test_followup_scheduler.py` |
| Integration tests (two-phase booking flow) | 3 | `tests/integration/test_two_phase_booking_flow.py` |
| Integration tests (follow-up flow) | 3 | `tests/integration/test_followup_flow.py` |
| Integration tests (Meta API failures) | 1 | `tests/integration/test_meta_api_failures.py` |
| Eval tests (confirmation intent detection) | 2 | `tests/eval/test_confirmation_intent_detection.py` |
| **Total** | **27** | |

---

**END OF TEST PLAN**
