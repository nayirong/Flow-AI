# Feature Requirements: Manual Human Agent Takeover

> **Requirements Specification**  
> Author: @product-manager  
> Date: 2026-05-12  
> Status: Draft — Pending Founder Approval  
> Priority: HIGH (client-flagged concern)

---

## 1. Feature Overview

### What
A mechanism that automatically pauses AI responses when a human agent takes over a customer conversation — and resumes AI when the human is done. The human agent's workflow should require **zero extra steps** to initiate a takeover. They should not need to type commands or phone numbers.

### Who
**Primary users:** Human agents at HeyAircon who need to proactively handle specific customer conversations (complex negotiations, VIP customers, sensitive complaints) even when the AI is technically capable of responding.

**Affected users:** End customers — they receive responses from either the AI or the human agent, but never both simultaneously. The transition should be seamless from the customer's perspective.

### Why
**Current pain:** When a human agent wants to message a customer directly via WhatsApp Business (outside the AI system), the AI doesn't know this is happening and may continue responding to that customer's messages — creating a confusing double-response scenario where both the human and AI are replying.

**Value delivered:**
- **Eliminates double responses** — AI pauses automatically when human takes over
- **Zero workflow disruption** — human just starts typing to the customer, no extra commands needed
- **Preserves human judgment** — human agents can proactively choose which conversations to handle personally
- **Maintains professional image** — customers experience a single, coherent conversation flow

### Channel
WhatsApp only.

---

## Architecture Note: Dual-Number Setup

**HeyAircon operates with two distinct WhatsApp numbers:**

| Number | Role | Used by |
|--------|------|---------|
| **Business number (88419968)** | Customer-facing | AI agent (via Meta Cloud API) + human agent replying to customers directly from WhatsApp Business app |
| **Human agent personal number** (`human_agent_number` in `clients` table) | Agent-facing control channel | Receives escalation alerts from the engine; human replies from this number to send commands (e.g., "done" resets escalation today) |

**Established pattern (today):** Engine sends escalation alert to `human_agent_number`. Human replies "done" to that thread — one word, reply-to-message gives the engine the customer context automatically. **The human never types a phone number.**

**Design principle for takeover: preserve this UX.** The human should never type a phone number to initiate takeover or resume.

**Two viable mechanisms (architect to determine which is available):**

**Option A — Echo webhook auto-detect (preferred, zero friction):**  
Meta Cloud API may deliver echo webhooks when the human sends a message from the WhatsApp Business app. If available: human just starts messaging the customer → engine detects the outbound echo → AI pauses automatically. No commands. No extra steps. Human types "done" in the customer thread → echo detected → AI resumes.

**Option B — Reply-to-forwarded-message (fallback, one word):**  
When the AI handles a customer message, the engine proactively sends a lightweight "live conversation" alert to `human_agent_number`. Human replies "take" to that alert — one word, reply-to-message resolves the customer. Same UX as "done" for escalation reset today. Resume: reply "done" to any customer message forwarded to personal number.

**OQ-HT-001 (CRITICAL — must resolve first):** `@software-architect` must verify echo webhook availability before any implementation work begins. The correct Phase 1 mechanism depends entirely on this answer.

---

## Direction Check

- **Subject**: Human agents who need to proactively take over customer conversations to handle complex/sensitive situations personally
- **Problem**: AI continues responding even when human wants to handle the conversation directly; creates confusing double-response scenarios
- **Confirmation**: This solution gives the subject (human agents) a command-based mechanism to pause and resume AI handling — it does NOT address the inverse (e.g., making AI escalation easier, giving customers control over who responds, or automating human-to-AI handoffs)

**Important distinction from existing escalation mechanism:**
- **Escalation** = AI-triggered — AI detects it cannot handle something and calls `escalate_to_human` tool
- **Manual takeover** = Human-triggered — Human proactively decides to handle a conversation personally, even if AI could handle it

These are separate flows with separate flags. They must not conflict.

---

## 2. User Stories

### US-HT-001: Human Agent Takes Over
**As a** human agent  
**I want to** take over a customer conversation without any extra steps  
**So that** I can handle their conversation directly without the AI interfering

**Acceptance Criteria:**
- [ ] Human agent starts a conversation with a customer (or sends a message from the business app) — AI automatically pauses for that customer
- [ ] No phone number input required
- [ ] No separate "takeover" command required — the act of messaging the customer is sufficient
- [ ] System logs who initiated takeover (detected human agent) and when
- [ ] AI does not send any further messages to that customer while takeover is active

### US-HT-002: AI Paused Behavior
**As a** customer whose conversation has been taken over by a human agent  
**I want to** receive no responses from the AI while the human is handling my case  
**So that** I don't get confused by multiple people responding

**Acceptance Criteria:**
- [ ] When AI is paused for a customer, all inbound messages from that customer are silently dropped (no AI reply, no holding message)
- [ ] Messages are still logged to `interactions_log` for audit purposes
- [ ] Customer has no indication that AI is paused (seamless transition)
- [ ] Human agent receives notification of any new messages from that customer while takeover is active (via forwarding or alert)

### US-HT-003: Human Agent Resumes AI
**As a** human agent  
**I want to** signal that I'm done handling a customer conversation  
**So that** AI takes back over without me needing to remember to do anything complex

**Acceptance Criteria:**
- [ ] Human agent sends a single short keyword ("done") in the customer thread or to their personal alert channel
- [ ] AI resumes responding to that customer's messages immediately
- [ ] No phone number input required
- [ ] System logs who resumed and when
- [ ] If human forgets to resume, AI auto-resumes after timeout (see US-HT-004)

### US-HT-004: Auto-Resume Safety Timeout
**As a** system operator  
**I want** the AI to automatically resume after a timeout period if human forgets to send resume command  
**So that** customers don't experience indefinite silence if human agent forgets to re-enable AI

**Acceptance Criteria:**
- [ ] If takeover flag remains active for longer than X hours (configurable, default 24 hours), system automatically resumes AI
- [ ] Auto-resume is logged with reason "timeout"
- [ ] Human agent receives notification when auto-resume happens

### US-HT-005: View Takeover Status
**As a** human agent  
**I want to** query which customers currently have active takeover flags  
**So that** I can remember who I'm still handling manually

**Acceptance Criteria:**
- [ ] Human agent can send a status command (e.g., "//status") to receive a list of all customers with active takeover
- [ ] List includes customer name/phone and how long takeover has been active
- [ ] If no active takeovers, receive confirmation message

---

## 3. Functional Requirements

> **⚠️ IMPLEMENTATION PATH NOT YET DETERMINED**  
> The specific implementation below branches based on echo webhook availability (OQ-HT-001). `@software-architect` must verify this before any code is written. Both paths share the same takeover gate logic, database schema, and resume behavior — they differ only in the *detection trigger*.

---

### REQ-HT-000: Pre-requisite — Echo Webhook Verification

Before implementation begins, `@software-architect` must empirically verify: does Meta Cloud API deliver webhook events when the human agent sends a message from the WhatsApp Business app on a Cloud API-registered number?

**Test procedure:**
1. Subscribe the webhook to the `messages` field in Meta App Dashboard
2. Human agent sends a test message from the WhatsApp Business app to any customer
3. Check webhook logs — does an event arrive with `from = business_phone_number`?

**If YES → implement Option A (echo auto-detect, Section 3A)**  
**If NO → implement Option B (reply-to-forwarded-message, Section 3B)**

---

### 3A: Option A — Echo Webhook Auto-Detect (preferred)

*Requires echo webhooks to be available. Zero extra steps for the human agent.*

#### REQ-HT-001A: Takeover Detection via Echo

**Trigger:** Webhook receives an event where `from == client_config.business_phone_number` (outbound echo — human agent sent a message from the WhatsApp Business app to a customer).

**Detection logic:**
1. Engine identifies this as an echo (outbound), not an inbound customer message
2. Extracts the customer's phone number from the `to` field
3. Checks: is `takeover_flag=FALSE` for this customer?
4. If so: set `takeover_flag=TRUE` — AI is now paused for this customer
5. Log to `takeover_tracking` with `command_type='echo_auto'`
6. **No confirmation message sent** — the human agent is mid-conversation, a notification would be disruptive

**Edge cases:**
- Human sends a brief follow-up message to an already-escalated customer (e.g. "We'll call you tomorrow") → escalation and takeover flags coexist; escalation gate runs first, takeover auto-sets as secondary state
- Human agent sends test message / admin message not intended as a takeover → takeover still sets (acceptable — auto-timeout handles cleanup)

#### REQ-HT-002A: Resume Detection via Echo

**Trigger:** Echo webhook received AND message text matches a configured resume keyword.

**Resume keywords (stored in per-client `config` table as `resume_phrases` JSON array):**
- Default: `["done", "//done", "ai take over", "handing back"]`
- Case-insensitive

**Logic:**
1. Echo received from human agent to customer
2. Message text matches resume keyword
3. Clear `takeover_flag=FALSE` for that customer
4. Log resolution to `takeover_tracking`
5. Engine sends brief confirmation to `human_agent_number`: "✅ AI resumed for {customer_name}."

**Auto-resume fallback:** If no resume echo detected within `TAKEOVER_TIMEOUT_HOURS` (default: 4 hours), auto-resume (see REQ-HT-008).

---

### 3B: Option B — Reply-to-Forwarded-Message (fallback if no echo webhooks)

*Used if echo webhooks are not available. Extends the existing reply-to-message pattern. Human never types a phone number.*

#### REQ-HT-001B: Proactive Conversation Alerts to Human Agent

When the AI handles an inbound customer message, the engine sends a lightweight monitoring alert to `human_agent_number`:

```
📨 AI handling: {customer_name}

"{first 80 chars of customer message}"

Reply "take" to this message to take over.
```

**This alert is sent ONCE per customer conversation session** (not per message). A "session" resets if the customer hasn't messaged in 4+ hours. This prevents alert spam.

**The alert message ID is stored** in a new `last_ai_alert_msg_id` column on `customers` table — the same reply-to-message lookup used for escalation reset.

#### REQ-HT-002B: Takeover via Reply-to-Alert

**Trigger:** Message FROM `human_agent_number` with:
- `context_message_id` matches a `last_ai_alert_msg_id` for a customer
- Message text matches a takeover keyword: `"take"`, `"mine"`, `"me"`, `"takeover"` (case-insensitive)

**Logic:**
1. Look up customer by `last_ai_alert_msg_id = context_message_id`
2. Set `takeover_flag=TRUE` for that customer
3. Log to `takeover_tracking`
4. Send confirmation to `human_agent_number`: "✅ Taking over {customer_name}. AI paused. Reply \"done\" to this thread when finished."

**The human agent types ONE word. The reply-to-message context resolves the customer automatically — no phone number needed.**

#### REQ-HT-003B: Resume via Reply-to-Alert

**Trigger:** Message FROM `human_agent_number` with `context_message_id` matching any alert associated with a customer where `takeover_flag=TRUE`, AND message text matches a resume keyword: `"done"`, `"resume"`, `"finished"` (case-insensitive).

**This is identical to the existing escalation reset pattern.** The human replies "done" to a thread — engine resolves the customer from the reply context.

---

### REQ-HT-004: AI Pause Behavior (Takeover Gate) — Both Options

Regardless of which detection mechanism is used, the takeover gate behavior is identical:

**Pipeline execution order:**
```
1. Log inbound message (always)
2. Check takeover_flag → if TRUE: forward to human agent, return (silent drop)
3. Check escalation_flag → if TRUE: send holding reply, return
4. Run schedule gate
5. Run agent loop
```

**Takeover gate behavior:**
- AI sends **no reply** to the customer (complete silence — no holding message)
- Inbound message is logged to `interactions_log`
- Customer's message is forwarded to `human_agent_number` in real-time (see REQ-HT-005)
- Pipeline stops

**Rationale for silence:** Human agent is actively in the conversation. An AI holding reply would confuse the customer who is already talking to a human.


### REQ-HT-005: Message Forwarding During Takeover

While `takeover_flag=True`, all inbound messages from that customer MUST be forwarded to `human_agent_number` in real-time.

**Forward message format (Option A — echo):**
```
📥 {customer_name} just replied:

"{message_text}"

(AI is paused. Reply "done" to resume AI.)
```

**Forward message format (Option B — reply-to-alert):**
```
📥 {customer_name} just replied:

"{message_text}"

Reply "done" to this message to resume AI.
```

**Technical notes:**
- Forward is sent via `send_message()` to `human_agent_number`
- Forward happens AFTER inbound logging, BEFORE any other processing
- If forward fails (Meta API error), log incident but do NOT block the pipeline
- Do NOT forward if message is from `human_agent_number` itself (prevents loops)

### REQ-HT-006: Status Command

**Trigger (both options):** Human agent sends "//status" or "status" from `human_agent_number` (standalone, not a reply).

**Response:**
```
Active takeovers (2):

1. John Tan (+6591234567)
   Taken over: 3 hours ago

2. Mary Lim (+6598765432)
   Taken over: 45 minutes ago

Reply "done" to any of their forwarded messages to release.
```

If no active takeovers:
```
No active takeovers. All customers are handled by AI.
```

**Implementation:**
- Query `customers WHERE takeover_flag=TRUE ORDER BY takeover_at DESC`
- Format as numbered list with customer name, phone, and duration since `takeover_at`
- Limit to 10 customers (paginate if more)

### REQ-HT-007: Auto-Resume Timeout (Safety Net)

**Requirement:** If `takeover_flag=TRUE` for longer than `TAKEOVER_TIMEOUT_HOURS`, auto-resume AI to prevent customers experiencing indefinite silence if human agent forgets to resume.

**Timeout reference:** `takeover_at` column. For Option A (echo), `@software-architect` may evaluate using `last_human_echo_at` (time of last detected outbound human message) for a more adaptive timeout.

**Suggested default:** 4 hours (after-hours context — human agent is likely done within the night).

**Implementation approach:**
- APScheduler job runs every 15 minutes
- Query `customers WHERE takeover_flag=TRUE AND takeover_at < (NOW() - INTERVAL '4 hours')`
- For each match:
  1. Set `takeover_flag=FALSE, takeover_by=NULL, takeover_at=NULL`
  2. Log to `takeover_tracking`: `resolved_at={NOW()}, resolved_by='system', resolution_reason='timeout'`
  3. Send notification to `human_agent_number`: "⏰ Auto-resumed AI for {customer_name} after {TAKEOVER_TIMEOUT_HOURS}h timeout."

**Configurable timeout:**
- `TAKEOVER_TIMEOUT_HOURS` env var (integer, default 4)
- Minimum allowed value: 1 hour
- Maximum allowed value: 48 hours

### REQ-HT-008: Conflict Resolution Between Takeover and Escalation

**Scenario 1: Escalation exists, echo/reply triggers takeover**
- Rule: Set both flags independently (they are independent states)
- Escalation gate runs first, holds customer with holding reply
- Takeover gate was checked first (and set) but human is now also the escalation handler
- **No error** — human has actively entered the conversation; let them handle it

**Scenario 2: Takeover active, AI tries to escalate**
- Rule: Cannot escalate while takeover is active
- `escalate_to_human` tool returns error: "Cannot escalate — customer is under manual takeover"
- No alert sent to `human_agent_number` (they are already handling it)

**Scenario 3: Human resumes — does escalation also clear?**
- Rule: Resume ("done") clears **both** `takeover_flag` AND `escalation_flag` if both are set
- Rationale: If the human is fully done with the customer, both AI pause mechanisms should release simultaneously
- Consistent with how "done" works today for escalation reset

### REQ-HT-009: Takeover Tracking Table (Audit Trail)

**Table:** `takeover_tracking` (per-client Supabase database)

**Schema:**
```sql
CREATE TABLE takeover_tracking (
  id              SERIAL PRIMARY KEY,
  phone_number    TEXT NOT NULL,
  initiated_by    TEXT NOT NULL,          -- 'echo_auto', 'reply_to_alert'
  initiated_at    TIMESTAMPTZ DEFAULT NOW(),
  command_type    TEXT,                   -- 'echo_auto' or 'reply_to_alert'
  resolved_at     TIMESTAMPTZ,
  resolved_by     TEXT,                   -- 'echo_done', 'reply_done', 'system' (timeout)
  resolution_reason TEXT                  -- 'manual' or 'timeout'
);

CREATE INDEX idx_takeover_tracking_phone 
  ON takeover_tracking(phone_number) 
  WHERE resolved_at IS NULL;
```



## 4. Non-Functional Requirements

### REQ-HT-NFR-001: Performance
- Takeover gate check must complete in <50ms (same as escalation gate)
- No impact on message processing latency for non-takeover customers

### REQ-HT-NFR-002: Reliability
- Takeover flag updates are atomic (no race conditions)
- If takeover flag write fails, send error to human agent and do NOT block customer message processing
- Message forwarding failure is logged but does NOT block pipeline

### REQ-HT-NFR-003: Observability
- All takeover events, resume events, and auto-resumes are logged to `takeover_tracking`
- Dashboard query (Phase 2): "Show all customers with active takeover older than 4 hours"
- Alert if more than 10 customers have active takeover simultaneously

### REQ-HT-NFR-004: Security
- For Option A (echo): only process echoes where `from == client_config.business_phone_number`; never treat inbound customer messages as echoes
- For Option B (reply-to-alert): only process takeover intent from messages originating from `human_agent_number`
- Phone number matching uses exact E.164 comparison (no SQL injection vector)
- No SQL injection risk in phone number extraction (use parameterised queries)

### REQ-HT-NFR-005: Scalability
- System must support up to 50 concurrent active takeovers per client without performance degradation
- APScheduler timeout job must complete in <5 seconds for 1000-customer database

---

## 5. Interaction with Existing Escalation Mechanism

### How They Differ

| Aspect | Escalation | Manual Takeover |
|--------|-----------|------------------|
| **Trigger** | AI agent (via `escalate_to_human` tool) | Human agent (echo or reply-to-alert) |
| **When** | AI detects it cannot handle request | Human proactively chooses to take over |
| **Flag** | `escalation_flag` on `customers` table | `takeover_flag` on `customers` table |
| **Customer experience** | Receives holding reply | Receives no AI reply (silence) |
| **Reset method** | Reply to escalation alert with "done" | Echo "done" in customer thread (Option A) or reply "done" to alert (Option B) |
| **Timeout** | No auto-reset | Auto-resumes after 4 hours |
| **Tracking table** | `escalation_tracking` | `takeover_tracking` |

### How They Coexist

**Gate execution order (in `message_handler.py`):**
```
1. Log inbound message
2. Check takeover_flag (NEW)
   - If TRUE: forward to human, return (silent drop)
3. Check escalation_flag (EXISTING)
   - If TRUE: send holding reply, return
4. Run agent loop
```

**Takeover gate runs FIRST** because:
- If human has taken over, they are actively managing the conversation
- Customer should see complete silence from AI (no holding replies)
- Escalation gate's holding reply would confuse customers who are already talking to the human

**They cannot be active simultaneously for the same customer:**
- Takeover command is rejected if escalation exists
- Escalate tool is disabled if takeover exists
- Human must resolve escalation before taking over manually
- Clearing escalation does NOT clear takeover (they're independent)

---

## 7. Out of Scope

### Explicitly NOT Included in Phase 1

1. **Command-based takeover with phone number argument** — rejected due to workflow disruption; not in scope
2. **Multi-agent coordination** — if multiple human agents exist, no handoff protocol between them
3. **Customer-initiated takeover** — customers cannot request human handling via takeover mechanism (they can still trigger AI escalation naturally through conversation)
4. **Takeover scheduling** — no "take over between 9am-5pm" rules
5. **Partial takeover** — no "human handles bookings, AI handles FAQs for same customer" split
6. **Cross-channel takeover** — if customer messages on WhatsApp and website widget, takeover applies independently per channel
7. **Takeover transfer** — no "transfer takeover to another human agent" command

### Future Enhancements (Not Committed)

- Mobile app for human agents with takeover/resume buttons (Phase 2 dashboard)
- Takeover analytics dashboard showing frequency, duration, reasons
- Smart auto-resume based on conversation context (e.g., if customer hasn't messaged in 2 hours, auto-resume)
- Integration with calendar — "auto-resume after my lunch break ends"

---

## 8. Open Questions for @software-architect

### OQ-HT-001: Echo Webhook Availability (CRITICAL — determines implementation path)
**Question:** Does Meta Cloud API deliver webhook events when the human agent sends a message from the WhatsApp Business app on a Cloud API-registered number?

**What to verify:**
- Subscribe to the `messages` webhook field and check if outbound (app-sent) messages appear with the business number as `from`
- Check Meta documentation for "message echoes" or "business-sent messages" in Cloud API webhook payloads
- Test empirically: human agent sends a message from the app → check webhook logs

**Impact:** If YES → implement Option A (echo auto-detect). If NO → implement Option B (reply-to-forwarded-alert).

**This is the first task the architect must complete before any implementation design is finalised.**

---

### OQ-HT-002: Option B Alert Noise Threshold
**Question (Option B only):** Is one alert per customer conversation session (4-hour window) acceptable to the human agent? Or is it still too noisy?

**Context:** At peak, HeyAircon receives ~10–20 customer messages per day. With a 4-hour session window, the human might receive 5–10 alerts per day.

**Recommendation needed before building Option B.**

---

### OQ-HT-003: Takeover Gate Placement (Upsert Order)
**Question:** Should the takeover gate run before or after customer upsert?

**Trade-offs:**
- **Before upsert:** Slightly faster, but `last_seen` won't update for customers under takeover
- **After upsert:** `last_seen` always accurate, adds ~10ms latency when message is dropped

---

### OQ-HT-004: Option A False Positive Risk
**Question:** For Option A, should ANY echo trigger takeover, or only echoes AFTER a customer has already sent an inbound message in the current session?

**Concern:** Human agent might send a proactive outbound message to a customer who hasn't messaged yet (e.g., post-booking follow-up). Should that trigger takeover?

**Recommendation needed.**

---

### OQ-HT-005: "Done" Conflict — Simultaneous Flags
**Question:** If both `escalation_flag` and `takeover_flag` are set, should "done" clear both simultaneously, or require explicit separate resets?

**Proposed rule:** "done" clears both (simpler UX for human agent who is fully done with the customer). Confirm.

---


### Q6: Command Prefix Flexibility
**Question:** Should the system support multiple command prefixes (`//`, `#`, `/`), or standardise on one?

**Trade-offs:**
- **Multiple prefixes:** More flexible, accommodates different user habits, but increases code complexity
- **Single prefix:** Simpler to implement and document, but may frustrate users who expect different syntax

**Recommendation needed:** Which prefix(es) to support?

---

### Q7: Integration with Widget Channel (Future)
**Question:** When the website widget goes live (Phase 1, in progress), should takeover/resume commands work for widget conversations too?

**Context:** Widget uses `visitors` table (separate from `customers` table). Takeover flag would need to be added to `visitors` as well.

**Recommendation needed:** Should Phase 1 takeover support both channels from day 1, or WhatsApp-only initially and extend to widget later?

---

## 9. Success Criteria

Phase 1 implementation is considered successful when:

1. **Functional:**
   - [ ] Human agent initiating takeover requires zero phone number input
   - [ ] AI stops responding to that customer (silent) while takeover is active
   - [ ] Customer messages are forwarded to human agent in real-time
   - [ ] Human agent can resume AI with a single keyword ("done")
   - [ ] AI resumes responding after resume
   - [ ] Auto-resume activates after 4-hour timeout
   - [ ] `//status` command lists all active takeovers
   - [ ] Takeover and escalation mechanisms do not conflict

2. **Non-Functional:**
   - [ ] Takeover gate adds <50ms latency to message processing
   - [ ] All events logged to `takeover_tracking` table
   - [ ] No impact on non-takeover customers
   - [ ] Takeover detection works 99.9% of the time (excluding Meta API failures)

3. **Operational:**
   - [ ] HeyAircon human agent can take over and resume without reading a manual
   - [ ] Human agent successfully uses mechanism in production for 1 week without issues
   - [ ] Zero customer complaints about double responses after implementation
   - [ ] Average takeover duration <4 hours (95th percentile)

---

## 10. Revision History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-05-12 | 0.1 | Initial draft | @product-manager |
| 2026-05-13 | 0.2 | Phase 1 redesign: removed `//takeover +phone` command; replaced with echo webhook auto-detect (Option A) or reply-to-forwarded-alert (Option B); human never types phone number; echo verification is now the first architect gate | @chief-of-staff |

---

## Next Steps

**After founder approval:**

1. **Route to @software-architect:**
   - **First task: verify echo webhook availability (OQ-HT-001)** — test empirically, check Meta docs, answer before designing implementation
   - Based on answer: design Option A (echo auto-detect) or Option B (reply-to-forwarded-alert)
   - Resolve OQ-HT-002 through OQ-HT-005
   - Specify SQL migrations for `takeover_flag`, `takeover_by`, `takeover_at` columns on `customers` table, and `takeover_tracking` table
   - Design takeover gate logic for `message_handler.py`
   - Review conflict resolution between escalation and takeover gates

2. **Route to @sdet-engineer:**
   - Create worktree for implementation
   - Write test plan covering all US-HT-001 through US-HT-005
   - Dispatch to @software-engineer for implementation

3. **Route to @ux-ui-designer (Phase 2 only):**
   - When dashboard is built, design takeover management UI (list active takeovers, one-click resume buttons)
