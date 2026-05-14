# Feature Requirements: After-Hours AI Schedule (Configurable)

> **Requirements Specification**  
> Author: @product-manager  
> Date: 2026-05-12  
> Status: Draft — Pending Founder Approval

---

## 1. Feature Overview

### What
Two independently configurable time windows, both stored per-client in Supabase and editable without code changes or redeployment:

1. **AI Operational Hours** — the window when the AI agent is active and handles inbound messages. Outside this window, the engine sends a standard auto-reply and stops (no AI processing).
2. **Business Operational Hours** — the window when human agents are available. This is used exclusively for escalation message context: when the AI escalates a conversation and it is currently outside business hours, the customer is informed that a human will follow up when the team is back.

These two windows are **independent**. Neither implies the other. A client may set:
- AI active 6pm–9am (after-hours only) + Business hours 9am–6pm
- AI active 24/7 (no restriction) + Business hours 9am–6pm (escalation context only)
- Both NULL = AI active 24/7, no business hours context in escalation messages

### Who
**Primary users:** Client admins (HeyAircon management, and future SEA service SME clients) — business owners who want to phase in AI gradually, test performance in low-stakes windows, or reserve peak hours for human-only service.

**Affected users:** 
- End customers — experience AI responses during configured hours, human responses outside those hours
- Human agents — receive messages that arrive outside AI hours (via routing mechanism TBD)

### Why
**Current state:** AI agent is always active (24/7). There is no way to limit when the agent operates without manually toggling the `is_active` flag in Supabase for the entire client — a blunt on/off switch with no temporal granularity.

**Pain:** HeyAircon wants to roll out the AI agent gradually — **AI during after-hours only** (when human agents are off-duty), human agents handle business hours. This staged rollout reduces risk, builds confidence in agent behavior, and preserves human control during peak service hours.

Separately, when AI escalates a conversation during off-hours, the current generic holding reply ("A team member will get back to you shortly") gives the customer no indication of when to expect a response. HeyAircon needs the escalation message to reference actual business hours.

**Value delivered:**
- **Risk mitigation** — clients can pilot AI in low-stakes time windows before full rollout
- **Operational flexibility** — clients maintain human service during critical hours while automating off-hours inquiries
- **Zero-touch configuration** — schedule changes happen in Supabase Studio (no redeploy, no Railway env var changes)
- **Per-client isolation** — each client sets their own schedule, accounting for their timezone and business model

### Channel
WhatsApp and Widget (all inbound channels respect the schedule).

---

## Direction Check

- **Subject**: HeyAircon admin (and future service SME clients) who need to control AI agent availability
- **Problem**: Uncontrolled AI agent availability during initial rollout — want to test AI gradually (after-hours only) before full deployment, to manage risk and maintain human control during peak business hours
- **Confirmation**: This solution gives the subject (client admin) schedule control over when the AI operates — it does NOT address the inverse (e.g., giving customers control over whether they get AI vs. human, or limiting when humans can respond)

---

## 2. User Stories

### US-AS-01: Client Admin — Configure AI Schedule
**As a** client admin (HeyAircon business owner),  
**I want to** set the hours when the AI agent is active (e.g., Mon-Sun 6pm–9am),  
**So that** I can test the AI during after-hours only, while keeping human agents in control during business hours.

**Acceptance Criteria:**
- [ ] I can edit `ai_active_start_time` and `ai_active_end_time` columns in Supabase Studio `clients` table
- [ ] Changes take effect within 5 minutes (cache TTL) without redeploying the engine
- [ ] Setting both fields to `NULL` makes AI active 24/7 (default for new clients)
- [ ] Invalid time formats are caught by the engine and logged as an error (AI defaults to 24/7 active on config error)

---

### US-AS-02: Client Admin — Understand Timezone Behavior
**As a** client admin,  
**I want to** know what timezone the schedule uses,  
**So that** I don't accidentally configure the wrong hours.

**Acceptance Criteria:**
- [ ] The `clients` table documentation (or Supabase Studio column comment) clearly states: "Times are interpreted in the timezone set in the `timezone` column (e.g., `Asia/Singapore` = UTC+8)."
- [ ] If `timezone` is `NULL` or invalid, the engine logs an error and defaults to UTC (safe fallback)

---

### US-AS-03: Customer — Message During AI Hours
**As a** customer,  
**I want to** send a WhatsApp message during AI active hours (e.g., 9pm),  
**So that** I receive an immediate AI-powered response.

**Acceptance Criteria:**
- [ ] Message arrives at 9pm (after-hours, AI active) → AI agent processes the message normally
- [ ] Response is sent within 10 seconds (same as current behavior)
- [ ] No visible difference to the customer — they don't know they're talking to AI vs. human

---

### US-AS-04: Customer — Message Outside AI Hours
**As a** customer,  
**I want to** send a WhatsApp message outside AI active hours (e.g., 2pm, during business hours),  
**So that** my message is handled appropriately (by a human agent or queued for later).

**Acceptance Criteria:**
- [ ] Message arrives at 2pm (business hours, AI inactive) → AI agent does NOT respond
- [ ] Customer receives an auto-reply: "Thanks for reaching out! Our team operates [business hours]. A team member will respond shortly."
- [ ] Message is forwarded to human agent via [routing mechanism TBD — see Open Questions]

---

### US-AS-05: Customer — Mid-Conversation Transition (AI Hours End)
**As a** customer currently in a conversation with the AI agent,  
**I want to** continue my conversation smoothly even if AI hours end mid-exchange,  
**So that** I don't experience a jarring service interruption.

**Acceptance Criteria:**
- [ ] If AI hours end during an active conversation (e.g., AI active until 9am, customer sends message at 8:58am), the **current message is processed by the AI** (do not cut off mid-exchange)
- [ ] Subsequent messages after 9am are handled per US-AS-04 (auto-reply + human routing)
- [ ] Definition of "active conversation": any exchange where the customer's last message was within 30 minutes of the current message

---

### US-AS-06: Human Agent — Receive Out-of-Hours Messages
**As a** human agent,  
**I want to** receive customer messages that arrive outside AI hours,  
**So that** I can respond during my shift.

**Acceptance Criteria:**
- [ ] When a message arrives outside AI hours, I receive a notification via [mechanism TBD — see Open Questions]
- [ ] The notification includes: customer phone number, customer name (if known), message text, timestamp
- [ ] I can reply to the customer directly (via WhatsApp Business inbox or other interface)

---

## 3. Functional Requirements

### REQ-AS-001: Schedule Data Model (Supabase `clients` Table)

Add **five** new columns to the shared Supabase `clients` table, split into two independent groups:

**Group 1 — AI Operational Hours (schedule gate)**

| Column Name | Type | Nullable | Default | Description |
|-------------|------|----------|---------|-------------|
| `ai_active_start_time` | `TIME` | YES | `NULL` | Start of AI active window (24hr format, e.g., `18:00:00` for 6pm). NULL = no restriction. |
| `ai_active_end_time` | `TIME` | YES | `NULL` | End of AI active window (24hr format, e.g., `09:00:00` for 9am). NULL = no restriction. |
| `timezone` | `TEXT` | NO | `'UTC'` | IANA timezone (e.g., `Asia/Singapore`) — used to interpret ALL schedule times for this client |

**Group 2 — Business Operational Hours (escalation context only)**

| Column Name | Type | Nullable | Default | Description |
|-------------|------|----------|---------|-------------|
| `business_start_time` | `TIME` | YES | `NULL` | Start of human agent availability window (e.g., `09:00:00`). NULL = no business hours context in escalation messages. |
| `business_end_time` | `TIME` | YES | `NULL` | End of human agent availability window (e.g., `18:00:00`). NULL = no business hours context in escalation messages. |

**Key distinction:**
- `ai_active_start_time` / `ai_active_end_time` → controls the **schedule gate** in `message_handler.py`. Determines whether the AI processes a message at all.
- `business_start_time` / `business_end_time` → used **only** by the escalation tool to populate the customer-facing holding message. Has no effect on message routing.
- Both groups use the same `timezone` field. One timezone per client.

**Both groups are independently nullable.** Setting one group to NULL has no effect on the other.

**Schedule Semantics:**

| `ai_active_start_time` | `ai_active_end_time` | Interpretation |
|------------------------|----------------------|----------------|
| `NULL` | `NULL` | AI active 24/7 (default for new clients) |
| `18:00:00` | `09:00:00` | AI active 6pm–9am (overnight window — start > end) |
| `09:00:00` | `18:00:00` | AI active 9am–6pm (daytime window — start < end) |
| `00:00:00` | `23:59:59` | AI active 24/7 (explicit) |
| `18:00:00` | `NULL` | **INVALID** — logs error, falls back to 24/7 |
| `NULL` | `09:00:00` | **INVALID** — logs error, falls back to 24/7 |

**Overnight Window Handling:**  
When `ai_active_start_time > ai_active_end_time` (e.g., 18:00 → 09:00), the active window **spans midnight**. Check logic:
- Current time >= 18:00 OR current time < 09:00 → AI active
- Current time >= 09:00 AND current time < 18:00 → AI inactive

**Migration Note:**  
For all existing clients in the `clients` table, set all four time fields to `NULL`. HeyAircon will be the first client to configure both windows:
- AI operational: `18:00:00` → `09:00:00` (after-hours active, overnight)
- Business hours: `09:00:00` → `18:00:00` (human agents available 9am–6pm)

---

### REQ-AS-002: Schedule Checking at Runtime

**Where:** `engine/core/message_handler.py` — new check **after escalation gate, before context builder**.

**Pipeline Order (updated):**
1. Load client config + DB connection
2. Log inbound to `interactions_log`
3. **Escalation gate** — query `customers` table; if escalated, send holding reply and stop
4. **Schedule gate (NEW)** — check if current time is within AI active hours; if not, route to out-of-hours handler and stop
5. Upsert customer record
6. Invoke context builder + agent runner
7. Send reply, log outbound

**Implementation Requirements:**
- [ ] Schedule check uses the `timezone` field from `client_config` to convert current UTC time to client-local time
- [ ] **AI operational hours** (`ai_active_start_time`, `ai_active_end_time`) are loaded as part of `ClientConfig` (cached 5-min TTL — no per-message Supabase query)
- [ ] **Business operational hours** (`business_start_time`, `business_end_time`) are also loaded into `ClientConfig` (same cache) — consumed only by the escalation tool, not the schedule gate
- [ ] If `ai_active_start_time` and `ai_active_end_time` are both `NULL`, skip the schedule gate entirely (AI always active)
- [ ] `business_start_time` / `business_end_time` being `NULL` does NOT affect the schedule gate — only affects escalation message content
- [ ] If AI operational hours fields are invalid (one NULL, one set; or unparseable), log error to `api_incidents` and default to 24/7 active (fail-open, not fail-closed)
- [ ] If current time is outside AI operational hours, invoke out-of-hours handler (see REQ-AS-003) and stop

**Performance Constraint:**  
Schedule check must add **<10ms latency** to message processing. Since schedule is cached in `ClientConfig` (in-process, 5-min TTL), the check is a simple time comparison — no database query.

---

### REQ-AS-003: Out-of-Hours Behavior (When Message Arrives Outside AI Hours)

When a message arrives outside AI active hours, the system executes the following:

**Step 1: Send Auto-Reply to Customer**

Send a fixed holding message:

```
Thanks for reaching out! Our team operates [business hours]. A team member will respond shortly.
```

**Business hours substitution:**  
Replace `[business hours]` with a human-readable description derived from `ai_active_start_time` and `ai_active_end_time`:
- If AI active 18:00–09:00 (after-hours) → "during business hours (9am–6pm)"
- If AI active 09:00–18:00 (business hours) → "after hours (6pm–9am)"
- If AI active 24/7 (both NULL) → omit the bracketed phrase entirely (this case should not reach the out-of-hours handler, but handle gracefully if it does)

**Step 2: Log Outbound Auto-Reply**

Write to `interactions_log`:
- `direction = 'outbound'`
- `message_text = <auto-reply text>`
- `message_type = 'text'`

**Step 3: Route to Human Agent (Mechanism TBD)**

**Open Question OQ-AS-01:** How should messages outside AI hours be routed to human agents?

**Option A — Forward to Human Agent Number (Immediate Notification):**
- Send a WhatsApp message to `client_config.human_agent_number` with customer details and message text
- Format: "New message from [Name] (+65XXXXXXXX) during business hours:\n\n[message text]\n\nReply directly to the customer to respond."
- **Pros:** Immediate notification, same channel human agents already monitor
- **Cons:** High volume during business hours could spam the human agent's WhatsApp

**Option B — Telegram Alert (Queued Batch Notification):**
- Send a Telegram message to the client's alert channel (if configured)
- Batch multiple messages into a single alert every 5 minutes (if volume is high)
- **Pros:** Reduces noise, separate channel for monitoring
- **Cons:** Requires Telegram bot setup, adds latency

**Option C — Silent Queue (No Immediate Notification):**
- Do nothing — human agents check the WhatsApp Business inbox directly during business hours
- AI holds off, customer gets auto-reply, human sees the message in their inbox
- **Pros:** Zero integration complexity, leverages existing human workflow
- **Cons:** No proactive alerting — human must check inbox manually

**Option D — Hybrid (Auto-Reply + Silent Queue, No Active Routing):**
- Send auto-reply to customer (Step 1)
- Log the message (Step 2)
- Do NOT forward to human agent — assume human agents monitor WhatsApp Business inbox during business hours
- **Pros:** Simplest implementation, no additional routing logic needed
- **Cons:** Assumes human agents are actively monitoring during business hours

**Recommendation for Phase 1:** Start with **Option D (Hybrid)** — auto-reply + silent queue. If HeyAircon requests active routing after pilot, implement Option A (forward to human agent number) in a follow-up phase.

**Step 4: Stop Pipeline (Do Not Invoke Agent)**

After sending auto-reply and routing, return early from `handle_inbound_message()`. Do NOT invoke context builder or agent runner.

---

### REQ-AS-004: Mid-Conversation Transition Handling

**Scenario:** Customer is in an active conversation with the AI (multiple messages exchanged within 30 minutes). AI hours end during the conversation (e.g., AI active until 9am, customer sends message at 8:58am).

**Requirement:**  
The **current message is processed by the AI** (finish the exchange gracefully). Subsequent messages after AI hours end are handled per REQ-AS-003 (auto-reply + routing).

**Implementation:**
- Define "active conversation" as: customer's previous message was sent within **30 minutes** of the current message
- Check the most recent `interactions_log` entry for the customer (direction = 'inbound', timestamp within last 30 minutes)
- If active conversation detected AND AI hours just ended (current time within 5 minutes of `ai_active_end_time`), **allow this message to proceed to the agent**
- This is a **grace period** — prevents jarring mid-exchange cutoff

**Edge Case Handling:**
- If customer sends multiple messages in rapid succession after AI hours end (e.g., 9:01am, 9:02am, 9:03am), only the **first message in the burst** gets the grace period. Subsequent messages are routed per REQ-AS-003.
- Grace period logic applies only when transitioning from active → inactive. When transitioning from inactive → active (e.g., 6pm arrives, AI becomes active), messages are processed immediately with no grace period needed.

**Open Question OQ-AS-02:** Should the grace period be configurable per client, or fixed at 5 minutes platform-wide?

---

### REQ-AS-005: Schedule Configuration Editability (Supabase Studio)

**Requirement:**  
Client admins must be able to edit `ai_active_start_time`, `ai_active_end_time`, and `timezone` directly in Supabase Studio without SQL knowledge or developer assistance.

**Acceptance Criteria:**
- [ ] All three columns are visible in the `clients` table view in Supabase Studio
- [ ] Column comments (Postgres `COMMENT ON COLUMN`) provide inline help:
  - `ai_active_start_time`: "Start of AI active window in 24hr format (e.g., 18:00:00 for 6pm). Leave NULL for 24/7 active. Times are interpreted in the timezone column."
  - `ai_active_end_time`: "End of AI active window in 24hr format (e.g., 09:00:00 for 9am). Leave NULL for 24/7 active. If end < start, window spans midnight (overnight)."
  - `timezone`: "IANA timezone name (e.g., Asia/Singapore). Used to interpret schedule times. Defaults to UTC."
- [ ] Changes propagate to the engine within **5 minutes** (cache TTL for `ClientConfig`)
- [ ] Invalid time formats (e.g., `25:00:00`, `abc`) are rejected by Postgres `TIME` type validation at insert/update time

---

### REQ-AS-006: Default Behavior for New Clients

**Requirement:**  
When a new client is added to the `clients` table, AI is **active 24/7 by default** (schedule fields are NULL).

**Acceptance Criteria:**
- [ ] Default values in the `clients` table schema:
  - `ai_active_start_time` default = `NULL`
  - `ai_active_end_time` default = `NULL`
  - `timezone` default = `'UTC'`
- [ ] Onboarding documentation (`~/.flow/onboarding.md`) includes a step: "If client wants to restrict AI hours, edit `ai_active_start_time` and `ai_active_end_time` in Supabase Studio."

---

### REQ-AS-007: Error Handling and Observability

**Requirement:**  
All schedule-related errors must be logged to shared Supabase `api_incidents` table and fail gracefully (default to 24/7 active, never block message processing).

**Error Scenarios:**

| Error | Handling |
|-------|----------|
| `timezone` is `NULL` or invalid IANA string | Log incident, default to `UTC`, proceed with schedule check |
| `ai_active_start_time` is set but `ai_active_end_time` is `NULL` (or vice versa) | Log incident, default to 24/7 active (skip schedule check) |
| `ai_active_start_time` or `ai_active_end_time` is unparseable (invalid format) | Log incident, default to 24/7 active (skip schedule check) |
| Schedule check raises an exception (e.g., timezone library crash) | Log incident with stack trace, default to 24/7 active, proceed to agent |

**Incident Log Format:**
- `incident_type = 'schedule_config_error'`
- `client_id = <client_id>`
- `details = { "error": "<error message>", "ai_active_start_time": <value>, "ai_active_end_time": <value>, "timezone": <value> }`

**Observability:**
- [ ] Add a Supabase analytics query (in `docs/observability/sql-reference.md`) to track schedule gate activations:
  ```sql
  -- Count messages blocked by schedule gate per client per day
  SELECT 
    client_id, 
    DATE(timestamp) AS date, 
    COUNT(*) AS out_of_hours_messages
  FROM interactions_log
  WHERE message_text LIKE 'Thanks for reaching out! Our team operates%'  -- auto-reply text
  GROUP BY client_id, DATE(timestamp)
  ORDER BY date DESC;
  ```

---

### REQ-AS-008: Context-Aware Escalation Message Using Business Hours

**Scenario:** AI is active and processes a conversation. The AI triggers the `escalate_to_human` tool (cannot answer the customer's question).

**Current escalation behavior:** Agent sends a generic holding reply ("A team member will get back to you shortly.") and sets `escalation_flag=TRUE`.

**Required behavior:** The escalation holding reply must check whether the current time is within `business_start_time`–`business_end_time` (the business operational hours window):

- **Escalation raised during business hours** (`business_start_time` ≤ current time < `business_end_time`):
  ```
  Thank you for reaching out. A team member will get back to you shortly.
  ```
  *(Same as current generic reply — human is available, no special framing needed)*

- **Escalation raised outside business hours** (current time < `business_start_time` OR current time ≥ `business_end_time`):
  ```
  Thank you for reaching out. Our team is currently unavailable.
  A team member will follow up with you during business hours ([business_start_time_formatted]–[business_end_time_formatted]).
  ```

- **No business hours configured** (`business_start_time` and `business_end_time` are both `NULL`):
  Use the existing generic holding reply (no change). Business hours context is not available.

**Important:** This logic is driven entirely by `business_start_time` / `business_end_time` — NOT by whether the AI is in its operational window. The escalation tool does not need to know whether AI is in after-hours mode. It only checks the business hours window.

**Business hours formatting:**
Convert `business_start_time` and `business_end_time` from `TIME` (24hr) to human-readable 12hr format with timezone:
- `09:00:00` → `9am`
- `18:00:00` → `6pm`
- Full example: `9am–6pm (SGT)`

**Implementation approach:**
- `escalate_to_human` tool receives `client_config` (already in scope via context builder)
- `client_config` exposes `business_start_time`, `business_end_time`, `timezone` (loaded from `ClientConfig` cache)
- Tool checks current local time against business window, selects message variant accordingly
- All other escalation mechanics (flag, tracking table, alert to human agent) are unchanged

**Acceptance Criteria:**
- [ ] Escalation outside business hours → customer receives message with business hours window (e.g., "9am–6pm (SGT)")
- [ ] Escalation during business hours → customer receives generic holding reply (no regression)
- [ ] No business hours configured → generic holding reply (no regression)
- [ ] Escalation flag, `escalation_tracking`, and human agent alert function identically regardless of message variant

**Open Question OQ-AS-06:** Should this context-aware message template be stored in the `policies` table (per-client configurable) or as a hardcoded platform template with token substitution? Recommendation: hardcoded template for Phase 1, configurable in Phase 2.

---

## 4. Non-Functional Requirements

### NFR-AS-001: Latency
Schedule check must add **<10ms latency** to message processing. Since schedule is cached in `ClientConfig` (in-process, 5-min TTL), the check is a time comparison only — no database query.

### NFR-AS-002: Cache Efficiency
All five schedule fields (`ai_active_start_time`, `ai_active_end_time`, `business_start_time`, `business_end_time`, `timezone`) are loaded as part of `ClientConfig` and cached for 5 minutes. No per-message Supabase query for either window.

### NFR-AS-003: Backward Compatibility
Existing clients with all four time fields NULL continue to operate with AI active 24/7 and generic escalation messages (no behavior change). The two windows are additive — neither is required.

### NFR-AS-004: Timezone Correctness
All schedule checks use the client's configured `timezone` to convert UTC timestamps to local time. No hardcoded assumptions about client location.

---

## 5. Out of Scope (Phase 1)

The following are **explicitly excluded** from Phase 1 and may be considered for future phases:

- **Per-day-of-week schedules** (e.g., AI active Mon-Fri 6pm-9am, but 24/7 on weekends) — Phase 1 uses a single daily recurring schedule
- **Multiple time windows per day** (e.g., AI active 12pm-2pm lunch break + 6pm-9am overnight) — Phase 1 supports one contiguous window only
- **Holiday and exception handling** (e.g., AI inactive on public holidays, custom blackout dates) — Phase 1 has no calendar awareness
- **Client-configurable auto-reply text** — Phase 1 uses a fixed template with business hours substitution only
- **Per-channel schedule overrides** (e.g., WhatsApp follows schedule, but Widget is always active) — Phase 1 schedule applies to all channels uniformly
- **Dynamic schedule changes mid-day** (e.g., client edits schedule at 3pm, new schedule takes effect immediately) — Phase 1 respects 5-minute cache TTL
- **Schedule-based analytics dashboard** (e.g., "Show me AI vs. human response rates by hour") — Phase 1 provides raw data in `interactions_log`, no dashboard

---

## 6. Open Questions for @software-architect

### OQ-AS-01: Out-of-Hours Message Routing Mechanism
**Question:** How should messages arriving outside AI hours be routed to human agents?

**Options:**
- **Option A:** Forward to `human_agent_number` via WhatsApp (immediate notification)
- **Option B:** Send Telegram alert to client's alert channel (batch notification)
- **Option C:** Silent queue — human agents check WhatsApp Business inbox manually (no active routing)
- **Option D:** Auto-reply + silent queue (hybrid — recommended for Phase 1)

**Decision needed before architecture phase.**

---

### OQ-AS-02: Grace Period Duration for Mid-Conversation Transitions
**Question:** Should the 5-minute grace period (allowing one final message to be processed by AI after hours end) be:
1. Fixed at 5 minutes platform-wide, or
2. Configurable per client via a new `clients` table column (`ai_transition_grace_minutes`)?

**Trade-offs:**
- Fixed: simpler, fewer edge cases, sufficient for 95% of clients
- Configurable: more flexible, but adds complexity and another field to manage

**Recommendation:** Start with fixed 5 minutes. If a client requests customization during pilot, add configurability in Phase 2.

---

### OQ-AS-03: Timezone Library Choice (Python)
**Question:** Should we use:
1. `pytz` (widely used, but deprecated in favor of `zoneinfo`)
2. `zoneinfo` (Python 3.9+ standard library, recommended)
3. `dateutil.tz` (also widely used)

**Recommendation:** Use `zoneinfo` (Python 3.9+ stdlib) for timezone handling. Fallback to `pytz` only if `zoneinfo` is unavailable (though Python 3.9 is already the platform minimum).

---

### OQ-AS-04: Schedule Check Before or After Customer Upsert?
**Question:** Should the schedule check happen:
1. **Before customer upsert** (pipeline order: log inbound → escalation gate → schedule gate → upsert customer → agent), or
2. **After customer upsert** (pipeline order: log inbound → escalation gate → upsert customer → schedule gate → agent)?

**Trade-offs:**
- **Before upsert:** Customer record is not updated if message arrives outside AI hours (no `last_seen` update). Pros: cleaner separation (schedule gate stops pipeline early). Cons: `last_seen` becomes inaccurate for out-of-hours messages.
- **After upsert:** Customer record is always updated (including `last_seen`), regardless of schedule. Pros: accurate customer activity tracking. Cons: upsert happens even when agent won't run.

**Recommendation:** **After upsert** (Option 2). Reason: `last_seen` should reflect the customer's last message timestamp, regardless of whether AI or human handled it. Analytics and escalation reset logic depend on accurate `last_seen` values.

---

### OQ-AS-05: Auto-Reply Logging (Direction Field)
**Question:** Should out-of-hours auto-replies be logged to `interactions_log` with:
1. `direction = 'outbound'` (same as agent responses), or
2. `direction = 'system'` (new direction type for automated system messages)?

**Trade-offs:**
- **'outbound':** Simpler (no schema change), consistent with existing holding replies for escalated customers. Cons: harder to distinguish AI responses from system auto-replies in analytics.
- **'system':** More precise labeling, enables analytics queries like "how many system auto-replies vs. AI responses?" Cons: requires schema migration to add new direction type.

**Recommendation:** Start with **'outbound'** (Option 1). If analytics needs emerge, add `message_source` column (values: `agent`, `system`, `human`) in Phase 2.

---

## 7. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-05-12 | @product-manager | Initial draft created |
