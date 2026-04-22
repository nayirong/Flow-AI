# Test Plan: Escalation Reset via WhatsApp Reply

> **Test Specification**  
> Author: @sdet-engineer  
> Date: 2026-04-22  
> Status: Ready for implementation

---

## Overview

This test plan covers the escalation reset feature that allows human agents to clear a customer's escalation flag by replying to the escalation alert message on WhatsApp with an approved keyword.

**Acceptance Criteria:** All 15 ACs from `docs/requirements/escalation_reset.md` must be verified.

**Test Files:**
- `engine/tests/unit/test_reset_handler.py` — new file, 13 tests
- `engine/tests/unit/test_meta_whatsapp.py` — update/create, 2 tests
- `engine/tests/unit/test_escalation.py` — update existing, 2 tests

---

## Test Coverage

### 1. Reset Handler Tests (`test_reset_handler.py`)

#### AC-01: No context_id sends help
**Test:** `test_no_context_id_sends_help`  
**Setup:** Human agent sends a fresh message (not a reply) with text "done"  
**Expected:** Help message sent listing valid keywords, flag NOT cleared

#### AC-02: No matching alert sends not found
**Test:** `test_no_matching_alert_sends_not_found`  
**Setup:** Human agent replies to a message, but `context_message_id` not in `escalation_tracking`  
**Expected:** "No pending escalation found" message sent, flag NOT cleared

#### AC-03: Already resolved alert sends not found
**Test:** `test_already_resolved_alert_sends_not_found`  
**Setup:** Human agent replies to an alert that has `resolved_at` populated  
**Expected:** "No pending escalation found" message sent, flag NOT cleared

#### AC-04: Unrecognised keyword sends help
**Test:** `test_unrecognised_keyword_sends_help`  
**Setup:** Human agent replies with "resolvedd" (typo)  
**Expected:** Help message sent, flag NOT cleared

#### AC-05: Emoji sends help
**Test:** `test_emoji_sends_help`  
**Setup:** Human agent replies with "👍"  
**Expected:** Help message sent, flag NOT cleared

#### AC-06: Keyword "done" clears flag
**Test:** `test_keyword_done_clears_flag`  
**Setup:** Human agent replies to unresolved alert with "done"  
**Expected:** 
- `customers.escalation_flag` = FALSE
- `escalation_tracking.resolved_at` populated
- `escalation_tracking.resolved_by` = human agent phone
- Confirmation message sent

#### AC-07: Keyword uppercase clears flag
**Test:** `test_keyword_uppercase_clears_flag`  
**Setup:** Human agent replies with "DONE"  
**Expected:** Flag cleared (case insensitive)

#### AC-08: Keyword with internal space clears flag
**Test:** `test_keyword_internal_space_clears_flag`  
**Setup:** Human agent replies with "res olved"  
**Expected:** Normalised to "resolved", flag cleared

#### AC-09: Keyword with leading/trailing space clears flag
**Test:** `test_keyword_leading_trailing_space_clears_flag`  
**Setup:** Human agent replies with "  done  "  
**Expected:** Stripped to "done", flag cleared

#### AC-10: Keyword "ok" clears flag
**Test:** `test_keyword_ok_clears_flag`  
**Setup:** Human agent replies with "ok"  
**Expected:** Flag cleared

#### AC-11: Confirmation contains customer info
**Test:** `test_confirmation_contains_customer_info`  
**Setup:** Human agent replies with "done"  
**Expected:** Confirmation message contains customer phone number

#### AC-12: DB failure sends error reply
**Test:** `test_db_failure_sends_error_reply`  
**Setup:** Mock UPDATE to raise exception  
**Expected:** "⚠️ Failed to clear escalation" message sent, no exception raised

#### AC-13: Non-human-agent not routed to reset
**Test:** `test_non_human_agent_not_routed_to_reset`  
**Setup:** Customer (not human agent) sends message  
**Expected:** Passes through normal pipeline, not routed to reset handler

---

### 2. Meta WhatsApp Tests (`test_meta_whatsapp.py`)

#### AC-14: send_message returns wamid on success
**Test:** `test_send_message_returns_wamid_on_success`  
**Setup:** Mock 200 response with `{"messages": [{"id": "wamid.xxx"}]}`  
**Expected:** Returns `"wamid.xxx"` (string)

#### AC-15: send_message returns None on failure
**Test:** `test_send_message_returns_none_on_failure`  
**Setup:** Mock 400 response  
**Expected:** Returns `None`

---

### 3. Escalation Tool Tests (update `test_escalation.py`)

#### Update existing test: escalate sends alert
**Test:** `test_escalate_sends_whatsapp_alert`  
**Change:** Update mock to return wamid string instead of `True`

#### New test: escalate inserts tracking row
**Test:** `test_escalate_inserts_tracking_row`  
**Setup:** Call `escalate_to_human()` with reason  
**Expected:** 
- INSERT into `escalation_tracking` called
- Row contains: `phone_number`, `alert_msg_id` (wamid), `escalation_reason`

---

## Verification Commands

```bash
# Run reset handler tests
cd engine && python -m pytest tests/unit/test_reset_handler.py -v --tb=short

# Run escalation tests
cd engine && python -m pytest tests/unit/test_escalation.py -v --tb=short

# Run all unit tests
cd engine && python -m pytest tests/unit/ -v --tb=short
```

---

## Success Criteria

All 15 acceptance criteria verified ✅  
All tests pass ✅  
No regressions in existing tests ✅
