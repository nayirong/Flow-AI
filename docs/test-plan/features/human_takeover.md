# Human Takeover Detection — Test Plan

> **Feature Test Plan**  
> Author: @sdet-engineer  
> Date: 2026-05-13  
> Architecture Spec: `docs/architecture/human_takeover.md`  
> Worktree: `../human-takeover`  
> Branch: `feat/human-takeover`  
> Priority: HIGH (client-flagged concern)

---

## Feature Summary

Automatically pauses AI responses when a human agent takes over a customer conversation — and resumes AI when the human is done. The human agent workflow requires **zero extra steps** to initiate takeover (one-word reply-to-message command) and no phone number input.

**Mechanism:** Reply-to-forwarded-message (Option B) — engine sends proactive monitoring alerts to `human_agent_number` whenever AI handles a customer. Human replies "take" to that alert (one word, reply-to-message resolves customer). AI pauses for that customer. Human replies "done" to any customer message alert to resume AI.

**Key features:**
- **Takeover gate** — runs BEFORE escalation gate in pipeline (Step 2, after inbound log)
- **Silent drop behavior** — no AI reply sent while takeover is active
- **Message forwarding** — all inbound from taken-over customer forwarded to `human_agent_number` in real-time
- **Auto-resume safety timeout** — APScheduler job clears stale takeovers after 4 hours (configurable)
- **Status command** — `//status` lists all active takeovers
- **Dual-flag clearing** — "done" command clears both `takeover_flag` AND `escalation_flag` if present

**Why Option B (not echo webhook auto-detect):** Meta Cloud API does NOT deliver echo webhooks when human sends a message from WhatsApp Business app. Outbound messages trigger STATUS webhooks (delivery/read receipts) which do NOT contain message content or sender context.

---

## Implementation Checklist

### 1. Database Migration (supabase/migrations/013_human_takeover.sql)

**Target database:** Per-client Supabase (customer-level state)

- [ ] Add 3 columns to `customers` table: `takeover_flag BOOLEAN NOT NULL DEFAULT FALSE`, `takeover_by TEXT DEFAULT NULL`, `takeover_at TIMESTAMPTZ DEFAULT NULL`
- [ ] Add 1 column to `customers` table: `last_ai_alert_msg_id TEXT DEFAULT NULL` (stores wamid of most recent conversation alert for reply-to-message lookup)
- [ ] Create `takeover_tracking` audit table with columns: `id SERIAL PRIMARY KEY`, `phone_number TEXT NOT NULL`, `alert_msg_id TEXT`, `takeover_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `takeover_by TEXT`, `command_type TEXT NOT NULL` ('reply_to_alert' or 'auto_timeout'), `released_at TIMESTAMPTZ DEFAULT NULL`, `released_by TEXT DEFAULT NULL`, `release_command_type TEXT DEFAULT NULL` ('manual_done' or 'auto_resume')
- [ ] Create 3 indexes:
  - [ ] `idx_takeover_tracking_alert_msg_id` on `takeover_tracking(alert_msg_id) WHERE released_at IS NULL` — fast lookup when human replies to alert
  - [ ] `idx_takeover_tracking_phone_active` on `takeover_tracking(phone_number, takeover_at) WHERE released_at IS NULL` — fast lookup for auto-resume job
  - [ ] `idx_customers_takeover_flag` on `customers(phone_number) WHERE takeover_flag = TRUE` — fast lookup during takeover gate
- [ ] Add column comments for Supabase Studio inline help
- [ ] Include rollback SQL in comments
- [ ] Safe to re-run (all `IF NOT EXISTS`)
- [ ] Apply migration to per-client Supabase (hey-aircon DB, not shared config DB)

### 2. Takeover Gate (engine/core/message_handler.py)

**Insert takeover gate as Step 3 in pipeline (BEFORE escalation gate)**

- [ ] Add new helper function `_handle_takeover_inbound()` (async)
  - [ ] Logs: "Takeover gate ACTIVE for {phone_number} — forwarding to human agent, AI will not respond"
  - [ ] Formats forward message: "📥 *{customer_name}* just replied:\n\n\"{message_text}\"\n\n(AI is paused. Reply \"done\" to resume AI.)"
  - [ ] Sends forward to `human_agent_number` via `send_message()`
  - [ ] Non-fatal error handling on send failure (log error, continue — human may see in WhatsApp Business inbox)
  - [ ] Does NOT send any reply to customer (complete silence)
  - [ ] Does NOT log outbound to `interactions_log` (no outbound sent)
  - [ ] Returns (stops pipeline — agent does NOT run)
- [ ] Insert takeover gate check in `handle_inbound_message()` after inbound log, before escalation gate:
  - [ ] Query `customer_row` for `takeover_flag`
  - [ ] If `takeover_flag=True`, call `_handle_takeover_inbound()` and return (stop pipeline)
- [ ] Pipeline order becomes: (1) Load config/DB → (2) Human agent routing → (3) Log inbound → **(4) Takeover gate** → (5) Escalation gate → (6) Schedule gate → (7) Agent runs

### 3. Conversation Alerts (engine/core/message_handler.py)

**Send proactive monitoring alert after agent runs successfully**

- [ ] Add new helper function `_maybe_send_conversation_alert()` (async)
  - [ ] Check `interactions_log` for this customer's last inbound message in last 4 hours
  - [ ] If recent inbound found (within 4h), return (session active, skip alert)
  - [ ] If no recent inbound (new session), build alert: "📨 AI handling: *{customer_name}*\n\n\"{message_text[:80]}...\"\n\nReply \"take\" to this message to take over."
  - [ ] Send alert to `human_agent_number` via `send_message()`, capture returned `alert_msg_id`
  - [ ] If send succeeds, update `customers.last_ai_alert_msg_id = alert_msg_id` for this customer
  - [ ] Non-fatal error handling on send/update failures
- [ ] Insert conversation alert call in `handle_inbound_message()` AFTER agent runs successfully (Step 9, before send reply)
- [ ] Define session timeout constant: `SESSION_TIMEOUT_HOURS = 4`

### 4. Reset Handler Extensions (engine/core/reset_handler.py)

**Add takeover command detection and dual-flag clearing**

- [ ] Add new keyword set: `TAKEOVER_KEYWORDS = frozenset(["take", "mine", "me", "takeover", "i'll handle", "ill handle", "take over"])`
- [ ] Keep existing: `RESET_KEYWORDS = frozenset(["done", "resolved", "ok", "handled", "fixed", "cleared", "completed", "closed", "finish", "finished", "okay"])`
- [ ] Update `handle_human_agent_message()` to handle 3 command types:
  - [ ] **Status command** (standalone): "//status" or "status" → call `_handle_status_command()`, return
  - [ ] **Takeover command** (requires reply-to-message): keyword in `TAKEOVER_KEYWORDS` → call `_handle_takeover_command()`, return
  - [ ] **Release command** (requires reply-to-message): keyword in `RESET_KEYWORDS` → call `_handle_release_command()`, return
  - [ ] **Invalid keyword or no reply-to-message**: send help text listing valid commands
- [ ] Implement `_handle_takeover_command()` (async):
  - [ ] Query `customers` table: `SELECT phone_number, customer_name, takeover_flag FROM customers WHERE last_ai_alert_msg_id = context_message_id LIMIT 1`
  - [ ] If no match, send: "No active conversation found for this alert. It may have been too long ago."
  - [ ] If already taken over (`takeover_flag=True`), send: "✅ {customer_name} is already in your takeover. AI is paused."
  - [ ] Otherwise, update `customers`: set `takeover_flag=True`, `takeover_by=phone_number`, `takeover_at=now`
  - [ ] Insert into `takeover_tracking`: `phone_number`, `alert_msg_id=context_message_id`, `takeover_by=phone_number`, `command_type='reply_to_alert'`
  - [ ] Send confirmation: "✅ Taking over *{customer_name}*. AI paused.\n\nReply \"done\" to this thread when finished."
  - [ ] Log: "Takeover initiated for {customer_phone} by {phone_number} (client: {client_id})"
- [ ] Implement `_handle_release_command()` (async):
  - [ ] Try takeover lookup first: query `customers` by `last_ai_alert_msg_id = context_message_id`
  - [ ] If match found:
    - [ ] Update `customers`: set `takeover_flag=False`, `takeover_by=None`, `takeover_at=None`, `escalation_flag=False`, `escalation_notified=False`, `escalation_reason=None` (clears BOTH flags)
    - [ ] Update `takeover_tracking`: set `released_at=now`, `released_by=phone_number`, `release_command_type='manual_done'` WHERE `phone_number` AND `released_at IS NULL`
    - [ ] Update `escalation_tracking`: set `resolved_at=now`, `resolved_by=phone_number` WHERE `phone_number` AND `resolved_at IS NULL` (if escalation was active)
    - [ ] Call `sync_customer_to_sheets()` (fire-and-forget)
    - [ ] Send confirmation: "✅ AI resumed for *{customer_name}* (takeover + escalation cleared)." OR "✅ AI resumed for *{customer_name}* (takeover cleared)." depending on which flags were set
    - [ ] Log: "Release command processed for {customer_phone} by {phone_number} (cleared: takeover, escalation)"
    - [ ] Return
  - [ ] If no takeover match, fall back to existing escalation reset logic (lookup by `escalation_tracking.alert_msg_id`)
- [ ] Implement `_handle_status_command()` (async):
  - [ ] Query `customers`: `SELECT phone_number, customer_name, takeover_at FROM customers WHERE takeover_flag = TRUE ORDER BY takeover_at DESC`
  - [ ] If no results, send: "No active takeovers. All conversations are handled by AI."
  - [ ] Otherwise, format response:
    - "Active takeovers ({count}):"
    - For each: "{i}. {customer_name} (+{phone_number})\n   Taken over: {hours}h {minutes}m ago"
    - "\n\nReply \"done\" to any of their forwarded messages to release."
  - [ ] Send formatted status to human agent

### 5. Auto-Resume Job (engine/core/takeover_auto_resume.py) — NEW FILE

- [ ] Create new file: `engine/core/takeover_auto_resume.py`
- [ ] Define constant: `DEFAULT_TIMEOUT_HOURS = 4`
- [ ] Implement `run_takeover_auto_resume()` (async):
  - [ ] Load timeout from settings: `timeout_hours = getattr(settings, "takeover_timeout_hours", DEFAULT_TIMEOUT_HOURS)`
  - [ ] Get all active clients via `get_all_active_clients()`
  - [ ] For each client, call `_auto_resume_for_client(client_config, timeout_hours)`
  - [ ] Non-fatal error handling per client (one failure doesn't block others)
- [ ] Implement `_auto_resume_for_client()` (async):
  - [ ] Calculate cutoff time: `cutoff_time = now - timedelta(hours=timeout_hours)`
  - [ ] Query `customers`: `SELECT phone_number, customer_name, takeover_at FROM customers WHERE takeover_flag = TRUE AND takeover_at < cutoff_time`
  - [ ] For each stale takeover:
    - [ ] Update `customers`: set `takeover_flag=False`, `takeover_by=None`, `takeover_at=None`
    - [ ] Update `takeover_tracking`: set `released_at=now`, `release_command_type='auto_resume'` WHERE `phone_number` AND `released_at IS NULL`
    - [ ] Log: "Auto-resumed takeover for {customer_phone} after {timeout_hours}h timeout"
    - [ ] Send notification to `human_agent_number`: "⏰ AI auto-resumed for *{customer_name}* (+{customer_phone}) after {timeout_hours}-hour timeout."

### 6. APScheduler Registration (engine/api/webhook.py)

- [ ] Update `lifespan()` function to register takeover auto-resume job
- [ ] Add job after existing followup scheduler job:
  - `scheduler.add_job(run_takeover_auto_resume, trigger="interval", minutes=30, id="takeover_auto_resume", replace_existing=True)`
- [ ] Update startup log: "Scheduler started: followup={interval_minutes}min, takeover_auto_resume=30min"

### 7. Settings Extension (engine/config/settings.py)

- [ ] Add field to `Settings` class: `takeover_timeout_hours: int = 4`

### 8. Client Config Helper (engine/config/client_config.py)

- [ ] Implement `get_all_active_clients()` (async):
  - [ ] Get shared DB via `get_shared_db()`
  - [ ] Query `clients` table: `SELECT * FROM clients WHERE is_active = TRUE`
  - [ ] For each row, construct `ClientConfig` object (same fields as `load_client_config()`)
  - [ ] Return list of `ClientConfig` objects
  - [ ] Used by scheduler jobs to iterate over all clients

---

## Unit Tests

### File: `engine/tests/unit/test_takeover_gate.py` (new file)

#### Test 1: `test_takeover_gate_blocks_when_flag_true`
- **Given:** `customer_row` with `takeover_flag=True`
- **When:** Inbound message arrives
- **Then:** `_handle_takeover_inbound()` called, pipeline stops
- **And:** Agent does NOT run (no context builder call)

#### Test 2: `test_takeover_gate_passes_when_flag_false`
- **Given:** `customer_row` with `takeover_flag=False`
- **When:** Inbound message arrives
- **Then:** Takeover gate passes silently
- **And:** Pipeline continues to escalation gate

#### Test 3: `test_takeover_inbound_forwards_to_human_agent`
- **Given:** `takeover_flag=True`, `human_agent_number="+6591234567"`
- **When:** Customer sends "Can you help me?"
- **Then:** Forward message sent to +6591234567
- **And:** Forward contains customer name, message text, and "Reply \"done\" to resume AI"
- **And:** No reply sent to customer

#### Test 4: `test_takeover_inbound_no_customer_reply`
- **Given:** `takeover_flag=True`
- **When:** `_handle_takeover_inbound()` runs
- **Then:** No outbound message logged to `interactions_log` (customer receives nothing)

#### Test 5: `test_conversation_alert_sent_on_new_session`
- **Given:** Customer hasn't messaged in 5 hours (no recent inbound in `interactions_log`)
- **When:** Agent handles message successfully
- **Then:** Conversation alert sent to `human_agent_number`
- **And:** Alert contains customer name, message snippet (80 chars max), and "Reply \"take\" to take over"
- **And:** `last_ai_alert_msg_id` updated in `customers` table

#### Test 6: `test_conversation_alert_skipped_on_active_session`
- **Given:** Customer messaged 2 hours ago (recent inbound exists)
- **When:** Agent handles new message successfully
- **Then:** No conversation alert sent (session still active)

#### Test 7: `test_conversation_alert_send_failure_non_fatal`
- **Given:** `send_message()` raises exception
- **When:** `_maybe_send_conversation_alert()` runs
- **Then:** Exception caught and logged, does NOT propagate
- **And:** Pipeline continues normally

### File: `engine/tests/unit/test_takeover_commands.py` (new file)

#### Test 8: `test_takeover_command_sets_flag`
- **Given:** Human agent replies "take" to conversation alert
- **When:** `_handle_takeover_command()` runs
- **Then:** `customers.takeover_flag` set to `True`
- **And:** `takeover_by` set to human agent phone number
- **And:** `takeover_at` set to current timestamp
- **And:** Row inserted into `takeover_tracking` with `command_type='reply_to_alert'`
- **And:** Confirmation sent to human agent

#### Test 9: `test_takeover_command_already_taken`
- **Given:** Customer already has `takeover_flag=True`
- **When:** Human agent replies "take" again
- **Then:** No database update (flag already set)
- **And:** Confirmation sent: "Already in your takeover. AI is paused."

#### Test 10: `test_takeover_command_no_matching_alert`
- **Given:** `context_message_id` doesn't match any `last_ai_alert_msg_id`
- **When:** Human agent replies "take"
- **Then:** Error message sent: "No active conversation found for this alert"
- **And:** No database changes

#### Test 11: `test_release_command_clears_takeover_only`
- **Given:** Customer has `takeover_flag=True`, `escalation_flag=False`
- **When:** Human agent replies "done" to alert
- **Then:** `takeover_flag` set to `False`, `takeover_by=None`, `takeover_at=None`
- **And:** `escalation_flag` remains `False` (unchanged)
- **And:** `takeover_tracking.released_at` updated with `release_command_type='manual_done'`
- **And:** Confirmation sent: "AI resumed for {customer_name} (takeover cleared)."

#### Test 12: `test_release_command_clears_both_flags`
- **Given:** Customer has `takeover_flag=True` AND `escalation_flag=True`
- **When:** Human agent replies "done"
- **Then:** Both flags set to `False`
- **And:** `escalation_notified` set to `False`, `escalation_reason=None`
- **And:** Both `takeover_tracking` and `escalation_tracking` updated
- **And:** Confirmation sent: "AI resumed for {customer_name} (takeover + escalation cleared)."

#### Test 13: `test_status_command_lists_active_takeovers`
- **Given:** 2 customers with `takeover_flag=True` (taken over 1h ago and 3h ago)
- **When:** Human agent sends "//status"
- **Then:** Response lists both customers with names, phone numbers, and time ago
- **And:** Footer says "Reply \"done\" to any of their forwarded messages to release."

#### Test 14: `test_status_command_no_active_takeovers`
- **Given:** No customers with `takeover_flag=True`
- **When:** Human agent sends "//status"
- **Then:** Response: "No active takeovers. All conversations are handled by AI."

#### Test 15: `test_takeover_keywords_recognized`
- **Given:** Human agent replies with "mine" or "me" or "takeover" (various keywords)
- **When:** Command processed
- **Then:** All variants trigger takeover (same as "take")

#### Test 16: `test_release_keywords_recognized`
- **Given:** Human agent replies with "resolved" or "ok" or "handled" (various keywords)
- **When:** Command processed
- **Then:** All variants trigger release (same as "done")

### File: `engine/tests/unit/test_auto_resume.py` (new file)

#### Test 17: `test_auto_resume_clears_stale_takeovers`
- **Given:** Customer with `takeover_flag=True`, `takeover_at` = 5 hours ago, timeout = 4 hours
- **When:** Auto-resume job runs
- **Then:** `takeover_flag` set to `False`, `takeover_by=None`, `takeover_at=None`
- **And:** `takeover_tracking.released_at` updated with `release_command_type='auto_resume'`
- **And:** Notification sent to `human_agent_number`

#### Test 18: `test_auto_resume_skips_fresh_takeovers`
- **Given:** Customer with `takeover_flag=True`, `takeover_at` = 2 hours ago, timeout = 4 hours
- **When:** Auto-resume job runs
- **Then:** No changes (takeover is fresh, within timeout)

#### Test 19: `test_auto_resume_notification_sent`
- **Given:** Stale takeover cleared by auto-resume
- **When:** Auto-resume job runs
- **Then:** Notification sent to `human_agent_number`: "⏰ AI auto-resumed for {customer_name} after 4-hour timeout."

#### Test 20: `test_auto_resume_per_client_failure_isolated`
- **Given:** 2 active clients, first client DB query fails
- **When:** Auto-resume job runs
- **Then:** First client error logged, second client still processed
- **And:** Job completes (doesn't crash on first failure)

---

## Integration Tests

### File: `engine/tests/integration/test_takeover_pipeline.py` (new file)

#### Test 1: `test_takeover_gate_runs_before_escalation`
- **Given:** Customer with both `takeover_flag=True` AND `escalation_flag=True`
- **When:** Inbound message arrives
- **Then:** Takeover gate fires first (message forwarded to human agent)
- **And:** Escalation gate does NOT run (pipeline already stopped)
- **And:** Customer receives no reply (no holding message, no auto-reply)

#### Test 2: `test_takeover_active_customer_gets_no_ai_reply`
- **Given:** Customer with `takeover_flag=True`
- **When:** Customer sends 3 messages in a row
- **Then:** All 3 messages forwarded to human agent
- **And:** Customer receives zero AI replies (complete silence)

#### Test 3: `test_conversation_alert_triggers_takeover_workflow`
- **Given:** Customer sends first message in 5 hours (new session)
- **When:** Agent handles message successfully
- **Then:** Conversation alert sent to human agent
- **And:** `last_ai_alert_msg_id` stored in customer record
- **When:** Human agent replies "take" to that alert
- **Then:** `takeover_flag` set to `True`
- **When:** Customer sends follow-up message
- **Then:** Message forwarded to human agent, customer gets no AI reply

#### Test 4: `test_takeover_release_resumes_ai`
- **Given:** Customer in takeover mode
- **When:** Human agent replies "done" to any alert
- **Then:** `takeover_flag` cleared
- **When:** Customer sends next message
- **Then:** Takeover gate passes, agent runs normally, customer receives AI reply

#### Test 5: `test_full_takeover_lifecycle`
- **Step 1:** Customer sends message → AI handles → conversation alert sent
- **Step 2:** Human replies "take" → takeover initiated
- **Step 3:** Customer sends 2 more messages → both forwarded, no AI replies
- **Step 4:** Human replies "done" → takeover released
- **Step 5:** Customer sends another message → AI handles normally, customer receives AI reply
- **Verify:** All state transitions logged to `takeover_tracking` and `customers` table

#### Test 6: `test_auto_resume_after_timeout_lifecycle`
- **Step 1:** Human takes over customer at T=0
- **Step 2:** Mock time advance to T=5h (past 4h timeout)
- **Step 3:** Auto-resume job runs → `takeover_flag` cleared
- **Step 4:** Customer sends message → AI handles normally (takeover expired)
- **Step 5:** Human receives timeout notification

---

## Regression Tests

All existing tests must continue to pass:
- [ ] `engine/tests/unit/test_message_handler.py` — escalation gate, schedule gate, opt-out detection
- [ ] `engine/tests/unit/test_reset_handler.py` — escalation reset still works (now also handles takeover release)
- [ ] `engine/tests/integration/test_webhook_to_reply.py` — full webhook flow (when no takeover active)
- [ ] `engine/tests/eval/` — all eval tests pass (agent behavior unchanged when takeover inactive)

### Specific regression checks:
- [ ] Escalation gate still works when takeover inactive
- [ ] Reset handler still clears `escalation_flag` when no takeover involved (backward compatibility)
- [ ] Human agent routing (Step 1b) still works (human agent messages routed to reset handler, not takeover gate)

---

## Manual Verification Steps

### Verify in staging/production (post-merge):

1. **Supabase Studio check:**
   - [ ] Open per-client Supabase (hey-aircon DB) → `customers` table
   - [ ] Confirm new columns exist: `takeover_flag`, `takeover_by`, `takeover_at`, `last_ai_alert_msg_id` (all should be NULL/FALSE for existing customers)
   - [ ] Check `takeover_tracking` table exists with correct schema

2. **Conversation alert (new session):**
   - [ ] Wait 5+ hours after last test message, OR use new test customer
   - [ ] Send message from customer: "Hi, I need service"
   - [ ] AI handles normally (agent reply sent to customer)
   - [ ] Human agent receives alert: "📨 AI handling: {customer_name}\n\n\"Hi, I need service\"\n\nReply \"take\" to this message to take over."

3. **Takeover command:**
   - [ ] Human agent replies "take" to the alert (reply-to-message)
   - [ ] Human receives confirmation: "✅ Taking over {customer_name}. AI paused. Reply \"done\" to this thread when finished."
   - [ ] Check Supabase: `customers.takeover_flag=TRUE`, `takeover_by={human_phone}`, `takeover_at={timestamp}`
   - [ ] Check `takeover_tracking`: new row with `command_type='reply_to_alert'`

4. **Takeover forwarding:**
   - [ ] Customer sends follow-up: "Can you come tomorrow?"
   - [ ] Customer receives NO reply (complete silence)
   - [ ] Human agent receives forward: "📥 {customer_name} just replied:\n\n\"Can you come tomorrow?\"\n\n(AI is paused. Reply \"done\" to resume AI.)"
   - [ ] Human can now reply directly to customer from WhatsApp Business app

5. **Release command (dual-flag):**
   - [ ] If customer was also escalated, both flags should be set (`takeover_flag=TRUE`, `escalation_flag=TRUE`)
   - [ ] Human agent replies "done" to any alert
   - [ ] Human receives confirmation: "✅ AI resumed for {customer_name} (takeover + escalation cleared)."
   - [ ] Check Supabase: both flags now FALSE, `takeover_at=NULL`, `escalation_notified=FALSE`
   - [ ] Check `takeover_tracking`: `released_at` set, `release_command_type='manual_done'`
   - [ ] Check `escalation_tracking`: `resolved_at` set

6. **AI resumes after release:**
   - [ ] Customer sends next message: "What are your prices?"
   - [ ] Customer receives AI reply (agent runs normally, takeover no longer active)

7. **Status command:**
   - [ ] Set up 2 test customers, human takes over both (reply "take" to their alerts)
   - [ ] Human agent sends "//status" (standalone message, not a reply)
   - [ ] Human receives list: "Active takeovers (2):\n\n1. John Tan (+6591234567)\n   Taken over: 15 minutes ago\n\n2. Mary Lim (+6598765432)\n   Taken over: 3 minutes ago\n\nReply \"done\" to any of their forwarded messages to release."

8. **Auto-resume timeout:**
   - [ ] Set `TAKEOVER_TIMEOUT_HOURS=1` in Railway env vars (for faster testing)
   - [ ] Human takes over customer, then waits 65 minutes (do NOT reply "done")
   - [ ] Auto-resume job runs (every 30 min) → detects stale takeover
   - [ ] Check Supabase: `takeover_flag` cleared after timeout
   - [ ] Human receives notification: "⏰ AI auto-resumed for {customer_name} after 1-hour timeout."
   - [ ] Customer sends message: AI handles normally (takeover expired)

9. **Takeover gate priority (before escalation):**
   - [ ] Customer is escalated (`escalation_flag=TRUE`)
   - [ ] Human takes over same customer (`takeover_flag=TRUE`, both flags now set)
   - [ ] Customer sends message
   - [ ] Message forwarded to human (takeover gate fires)
   - [ ] Customer does NOT receive escalation holding reply (escalation gate never runs)

10. **No conversation alert spam:**
    - [ ] Customer sends 5 messages within 10 minutes
    - [ ] Human agent receives only 1 conversation alert (for the first message in the session)
    - [ ] No duplicate alerts for subsequent messages (session still active)

---

## Definition of Done

- [ ] Migration 013 applied to per-client Supabase and verified in Supabase Studio
- [ ] All 4 new columns present in `customers` table
- [ ] `takeover_tracking` audit table created with correct schema and indexes
- [ ] Takeover gate implemented in `message_handler.py` (Step 3, before escalation)
- [ ] `_handle_takeover_inbound()` forwards messages to human agent, no customer reply
- [ ] `_maybe_send_conversation_alert()` sends proactive alerts with 4-hour session detection
- [ ] Reset handler extended with takeover command detection ("take", "done", "//status")
- [ ] `_handle_takeover_command()` sets flag, logs to tracking table, sends confirmation
- [ ] `_handle_release_command()` clears both takeover AND escalation flags if present
- [ ] `_handle_status_command()` lists all active takeovers with time ago
- [ ] Auto-resume job implemented (`takeover_auto_resume.py`) with configurable timeout
- [ ] Auto-resume job registered in APScheduler (30-minute interval)
- [ ] `TAKEOVER_TIMEOUT_HOURS` setting added (default 4)
- [ ] `get_all_active_clients()` helper implemented for scheduler jobs
- [ ] All 20 unit tests pass
- [ ] All 6 integration tests pass
- [ ] All regression tests pass (existing test suite remains green)
- [ ] Manual verification completed for all 10 scenarios above
- [ ] Code formatted (project formatter)
- [ ] No linter errors
- [ ] Merged to main via PR (or direct merge if repo does not use PRs)
