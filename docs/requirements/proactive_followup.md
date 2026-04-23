# Proactive Follow-up Flow

**Feature ID:** REQ-FOLLOWUP-001  
**Status:** Draft — Pending Founder Approval  
**Created:** 2026-04-22  
**Owner:** @product-manager

---

## Direction Check

- **Subject:** Customers who book an appointment but then go silent after confirmation
- **Problem:** No engagement post-booking creates uncertainty about whether the customer is still committed, leading to no-shows and wasted technician time slots
- **Confirmation:** This solution provides the subject (silent post-booking customers) with gentle, timed check-ins that keep the conversation warm and offer a rescheduling path — not a notification system for active customers or a churn recovery campaign

---

## Overview

After a booking is confirmed by the AI agent, customers sometimes disengage from the conversation. This creates uncertainty for the business about whether the customer will show up. The Proactive Follow-up Flow is a timed outreach sequence that checks in with silent customers at strategic intervals (T+2h, T+24h) and marks unresponsive bookings as abandoned at T+48h to allow the business to reallocate the slot or deprioritize follow-up.

### Goals

- Reduce booking no-shows by maintaining engagement post-confirmation
- Offer customers a low-friction path to reschedule if plans change
- Give the business visibility into which bookings are likely abandoned before the scheduled appointment date
- Maintain the HeyAircon agent's warm, helpful persona throughout automated outreach

---

## User Story

**As a customer who has just booked an appointment**, I want to receive a friendly check-in message a few hours after booking so that I feel supported and can easily reschedule if my plans change, rather than forgetting about the booking or feeling awkward about reaching out.

**As the HeyAircon admin team**, I want to know which bookings are abandoned early (before the appointment date) so that I can reallocate technician time and not waste follow-up effort on unresponsive customers.

---

## Booking Status Lifecycle

### Full `booking_status` Enum

The `booking_status` column in the `bookings` table uses the following values (snake_case, stored as TEXT):

| Status | Definition | When Set | DB Row Exists? | Calendar Event Exists? |
|--------|------------|----------|----------------|----------------------|
| `pending_confirmation` | Agent has collected all booking info and sent the confirmation summary message; awaiting customer's explicit confirmation reply. **No slot reservation** — slot is not held during this state. | Set when agent calls `write_booking` and sends "Here's your booking summary..." message | ✅ Yes | ❌ No |
| `confirmed` | Customer has replied to confirm (e.g., "yes", "confirm", "ok") — LLM detected confirmation intent | Set when agent calls `confirm_booking` after detecting customer's affirmative reply | ✅ Yes | ✅ Yes |
| `rescheduled` | Booking moved to a new date/time slot by customer or admin | Set when agent processes reschedule request | ✅ Yes (updated) | ✅ Yes (updated or new event) |
| `cancelled` | Customer or admin cancelled the booking | Set when agent processes cancellation or admin cancels in CRM | ✅ Yes | ⚠️ Depends (deleted if was `confirmed`, never existed if was `pending_confirmation`) |
| `completed` | Appointment has occurred and service is done | Set manually by admin after appointment | ✅ Yes | ✅ Yes |
| `abandoned` | Customer never responded through the follow-up sequence | Set automatically at T+48h by scheduler | ✅ Yes | ❌ No (never reached `confirmed`) |

### State Transition Diagram

```
[Agent collects info] 
       ↓
   [write_booking called]
       ↓
pending_confirmation ──→ [confirm_booking called] ──→ confirmed ──→ completed
       ↓                                                   ↓              
       ↓                                                   ↓
       ↓                                               rescheduled ──→ confirmed (new slot)
       ↓                                                   ↓
       ↓                                                cancelled
       ↓
       └──→ abandoned (T+48h, no customer reply)
```

**Key transitions:**
- `pending_confirmation → confirmed`: Customer replies to confirmation message with affirmative intent (detected by LLM) → agent calls `confirm_booking` → Google Calendar slot conflict check → if no conflict, calendar event created + status updated
- `pending_confirmation → cancelled`: Customer says "cancel" or "never mind" before confirming → no calendar event ever created
- `pending_confirmation → abandoned`: 48h pass with no customer response after follow-ups → no calendar event ever created
- `confirmed → rescheduled`: Customer requests a slot change → calendar event updated or deleted + new event created
- `rescheduled → confirmed`: New slot is confirmed by customer (same flow as initial confirmation)
- `confirmed/rescheduled → cancelled`: Customer or admin cancels → calendar event deleted
- `confirmed → completed`: Admin marks complete after appointment

**Important:** 
- A booking at `pending_confirmation` is NOT yet a committed booking. The customer has seen the summary but has not explicitly said "yes." This distinction is critical for inventory management and no-show tracking.
- **No slot reservation (Founder Decision 2026-04-22):** A `pending_confirmation` booking does NOT hold the slot. If two customers are both `pending_confirmation` for the same slot simultaneously, the first to confirm wins. The second gets a conflict error at `confirm_booking` time and is offered alternatives. `check_calendar_availability` queries Google Calendar ONLY — it does not check the `bookings` table.
- **Calendar event timing:** Google Calendar events are created ONLY at `confirmed` status, not at `pending_confirmation`. This prevents calendar clutter from bookings that are never confirmed.

---

## Trigger Conditions

### What Qualifies a Booking for Follow-up?

A booking enters the follow-up sequence when:
1. The booking has `booking_status = 'pending_confirmation'` (not `confirmed` — see Booking Status Lifecycle above)
2. The booking confirmation message has been sent to the customer (logged in `interactions_log` as `direction='outbound'` containing booking details)
3. The customer has sent **zero new inbound messages** to the agent after the confirmation timestamp

### What is "Silent"?

A customer is considered silent when:
- The last message in `interactions_log` for that `phone_number` is the agent's outbound booking confirmation, AND
- The `timestamp` of that confirmation message is ≥ X hours ago (where X = 2, 24, or 48 depending on follow-up stage)

### Scheduler Trigger Logic

The scheduler runs every 1 hour and queries for bookings that meet the following criteria for each stage:

**T+2h (First Follow-up):**
```sql
SELECT * FROM bookings
WHERE booking_status = 'pending_confirmation'
  AND followup_stage IS NULL  -- has not entered follow-up yet
  AND created_at <= NOW() - INTERVAL '2 hours'
  AND phone_number NOT IN (
    SELECT DISTINCT phone_number FROM interactions_log
    WHERE direction = 'inbound'
      AND timestamp > (SELECT MAX(timestamp) FROM interactions_log 
                       WHERE direction = 'outbound' 
                         AND phone_number = bookings.phone_number
                         AND message_text LIKE '%confirmed%')  -- confirmation message heuristic
  )
```

**T+24h (Second Follow-up):**
```sql
SELECT * FROM bookings
WHERE booking_status = 'pending_confirmation'
  AND followup_stage = '2h_sent'
  AND last_followup_sent_at <= NOW() - INTERVAL '22 hours'  -- 24h since booking, 22h since last follow-up
  AND phone_number NOT IN (...)  -- same silence check
```

**T+48h (Abandon Mark):**
```sql
SELECT * FROM bookings
WHERE booking_status = 'pending_confirmation'
  AND followup_stage = '24h_sent'
  AND last_followup_sent_at <= NOW() - INTERVAL '24 hours'
  AND phone_number NOT IN (...)  -- same silence check
```

---

## Message Copy

All messages must match the HeyAircon persona: warm, professional, straightforward, reassuring, with a touch of Singlish-lite naturalness. Messages are sent via Meta Cloud API WhatsApp message endpoint as plain text (no buttons or interactive elements in Phase 1).

### T+2h Message

> **Purpose:** Warm check-in, reinforce confirmation, offer easy reschedule path

```
Hi [Customer Name]! 😊

Just checking in on your aircon servicing booking for [Date] ([AM/PM slot]).

Could you confirm so we can lock it in? If anything's changed or you'd like a different time, just let me know. 😊
```

**Tone rationale:** Friendly and low-pressure. No urgency language about slot holds — the customer is being gently prompted to confirm without creating false scarcity. The emoji keeps the tone warm.

### T+24h Message

> **Purpose:** Gentle reminder with a bit more urgency, reinforce that help is available

```
Hi [Customer Name],

Checking in again about your appointment on [Date] ([AM/PM slot]). We'd love to lock this in for you!

If you need to reschedule or have any questions, feel free to reach out. We want to make sure everything works for you. 👍
```

**Tone rationale:** Slightly more direct than T+2h (no "just wanted to"). Still warm and supportive. "We'd love to lock this in for you" prompts action without implying the slot is being held.

### T+48h (No Message — Internal Mark Only)

At T+48h, **no message is sent to the customer**. Instead:
- `booking_status` is updated to `'abandoned'`
- `abandoned_at` is set to `NOW()`
- `followup_stage` is set to `'abandoned'`
- An internal log entry is created for admin visibility

**Rationale:** Sending a third message risks feeling spammy. At this point, the customer has had two opportunities to respond. Marking the booking as abandoned internally gives the business the data they need without further customer contact.

---

## Schema Changes Required

### Modifications to `bookings` Table

Add three new columns:

```sql
ALTER TABLE bookings
ADD COLUMN last_followup_sent_at TIMESTAMPTZ,
ADD COLUMN followup_stage TEXT,  -- NULL | '2h_sent' | '24h_sent' | 'abandoned' | 'opted_out'
ADD COLUMN abandoned_at TIMESTAMPTZ;
```

**Critical Schema Note: `booking_status` Column Values**

The `booking_status` column must be updated to support the new enum values defined in the "Booking Status Lifecycle" section. This is a **breaking change** that requires data migration:

- **Old behavior:** Agent set `booking_status = 'Confirmed'` immediately after sending the confirmation summary message
- **New behavior:** Agent sets `booking_status = 'pending_confirmation'` after sending confirmation summary, then updates to `'confirmed'` only when customer replies with affirmative intent

**Migration Required:**
- Existing bookings with `booking_status = 'Confirmed'` where the customer HAS replied after the confirmation message → no change needed (or update to lowercase `'confirmed'`)
- Existing bookings with `booking_status = 'Confirmed'` where the customer has NOT replied → these should be marked `'pending_confirmation'` to enter the follow-up flow
- Agent code in `core/agent_runner.py` and tool implementations must be updated to use the new two-phase status flow

**Transition Plan:** The software-architect must design a migration script or add backward-compatibility handling (e.g., scheduler queries `WHERE booking_status IN ('pending_confirmation', 'Confirmed')` temporarily) until all existing bookings are migrated.

---

**Column Definitions:**

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| `last_followup_sent_at` | `TIMESTAMPTZ` | Yes | Timestamp of the most recent follow-up message sent. Used to calculate when the next follow-up is due. NULL if no follow-ups sent yet. |
| `followup_stage` | `TEXT` | Yes | Current stage of the follow-up sequence. Values: `NULL` (not started), `'2h_sent'`, `'24h_sent'`, `'abandoned'`, `'opted_out'`. |
| `abandoned_at` | `TIMESTAMPTZ` | Yes | Timestamp when the booking was marked as abandoned. NULL unless `followup_stage = 'abandoned'`. |
| `booking_status` | `TEXT` | No | **(EXISTING COLUMN — VALUES CHANGED)** See "Critical Schema Note" above. Now uses snake_case enum: `'pending_confirmation'`, `'confirmed'`, `'rescheduled'`, `'cancelled'`, `'completed'`, `'abandoned'`. |

**Why not a separate `booking_followups` table?**  
The follow-up state is 1:1 with a booking and directly affects how the business views and acts on that booking. Keeping it in the `bookings` table avoids JOIN complexity in queries and keeps the data model simple for Phase 1. If follow-up sequences become more complex in Phase 2 (e.g., multiple sequences per booking), we can migrate to a dedicated table.

---

## Re-Engagement Guard

### If the Customer Replies at Any Point

If the customer sends an inbound message at any stage of the follow-up sequence (including after the 48h abandon mark), the agent handles it end-to-end with no admin intervention required.

### Case A: Customer Replies Before T+48h Abandon Mark

**Context:** Booking is still `pending_confirmation`, follow-up sequence in progress.

**Agent behavior:**
1. The agent receives the inbound message through the normal message handler flow
2. The scheduler's silence check will exclude this booking from future follow-up trigger queries (customer is no longer silent)
3. The agent determines whether the customer's message is a confirmation or something else:
   - **If confirmation intent detected** (e.g., "yes", "ok", "confirm", "can", "👍", Singlish affirmatives): Agent calls `confirm_booking` directly — same flow as normal confirmation. If successful, `booking_status` → `confirmed` and calendar event is created. If slot conflict, agent offers alternatives.
   - **If NOT a confirmation** (e.g., question, reschedule request, clarification): Agent handles normally via standard conversation flow (answers question, initiates reschedule, etc.)
4. The booking's `followup_stage` remains at its current value — no reset or rollback. If the customer later confirms, status transitions to `confirmed`.

**No human admin intervention required.**

### Case B: Customer Replies After T+48h Abandon Mark

**Context:** Booking is `abandoned`, customer re-engages days or weeks later.

**Agent behavior:**
1. The agent receives the inbound message through the normal message handler flow
2. The agent does NOT attempt to resurrect or update the abandoned booking row
3. The agent treats this as a **fresh booking inquiry** and proceeds through the normal booking flow:
   - Collects or reconfirms booking details (service, date, slot, address)
   - Checks availability via `check_calendar_availability`
   - Calls `write_booking` to create a NEW `pending_confirmation` booking row (new `booking_id`)
   - Sends confirmation summary and waits for customer's explicit confirmation
   - When customer confirms, calls `confirm_booking` to finalize
4. The old `abandoned` booking row remains in the database unchanged — it serves as an audit record of the original booking attempt

**No human admin intervention required.** The agent autonomously handles late re-engagement by creating a new booking.

---

## Opt-Out Handling

### Customer Opt-Out Keywords

If the customer replies to a follow-up message with any of the following phrases (case-insensitive, partial match):
- "stop"
- "unsubscribe"
- "no more messages"
- "don't message me"
- "leave me alone"

The system must:
1. Immediately update the booking: `followup_stage = 'opted_out'`
2. Stop all future follow-ups for this booking
3. Send a confirmation reply to the customer:
   ```
   Understood! We won't send any more follow-up messages about this booking. If you need anything, feel free to reach out anytime. 😊
   ```
4. **Do NOT change `booking_status`** — the booking is still `'pending_confirmation'` (or `'confirmed'` if already confirmed) unless the customer explicitly cancels

### Where Opt-Out Detection Happens

Opt-out keyword detection is implemented in `core/message_handler.py` as a pre-processing step before the agent is invoked:
- After logging the inbound message, check if the message text matches opt-out keywords
- If match: update `followup_stage`, send confirmation reply, log outbound, stop (do not invoke agent)
- If no match: proceed with normal escalation gate + agent flow

**Rationale:** Opt-out must be deterministic and cannot rely on the LLM to detect intent. A simple keyword check is fast, reliable, and prevents accidental opt-outs from being interpreted as other intents by the agent.

---

## Interaction with Escalation

### Escalation Gate Takes Precedence

If a customer has `escalation_flag = True` in the `customers` table:
- **No follow-up messages are sent** — the follow-up scheduler query MUST exclude bookings where the customer's `escalation_flag = True`
- The booking's `followup_stage` remains at its current value (does not advance)
- The human agent owns the conversation and is responsible for any follow-up

**Scheduler Query Update (All Stages):**
```sql
SELECT b.* FROM bookings b
JOIN customers c ON b.phone_number = c.phone_number
WHERE b.booking_status = 'pending_confirmation'
  AND c.escalation_flag = FALSE  -- <-- escalation gate
  AND ...  -- (rest of stage-specific conditions)
```

**Rationale:** The escalation flag is a hard gate (see `mvp_scope.md` DR-001). Once a customer is escalated, the agent is silenced and all automated outreach stops. The human agent must clear `escalation_flag` before automated follow-ups resume.

---

## Client-Configurable Variables

### Overview

All timing thresholds, feature toggles, and message templates for the proactive follow-up feature are stored in the **Supabase `config` table** as per-client key-value rows. This allows each client to customize the follow-up behavior without code changes or redeployment.

### Full Variable List

| Variable | Config Key | Type | Default | Description |
|----------|------------|------|---------|-------------|
| **T+2h threshold** | `followup_t1_hours` | INTEGER | `2` | Hours after booking creation to send first follow-up |
| **T+24h threshold** | `followup_t2_hours` | INTEGER | `24` | Hours after T1 to send second follow-up |
| **Abandon threshold** | `followup_abandon_hours` | INTEGER | `48` | Hours after T2 to mark booking as abandoned |
| **Feature kill switch** | `followup_enabled` | BOOLEAN | `true` | Master toggle to enable/disable follow-ups for this client |
| **Scheduler interval** | `followup_scheduler_interval_minutes` | INTEGER | `60` | How often the scheduler checks for eligible bookings (minutes) |
| **T+2h message template** | `followup_t1_message_template` | TEXT | *(see below)* | Message sent at T+2h with `{customer_name}`, `{date}`, `{slot}` placeholders |
| **T+24h message template** | `followup_t2_message_template` | TEXT | *(see below)* | Message sent at T+24h with same placeholders |
| **Opt-out confirmation** | `followup_optout_reply` | TEXT | *(see below)* | Message sent when customer opts out |

### Supabase `config` Table Row Format

The `config` table schema:
```sql
CREATE TABLE config (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,  -- stored as text; cast to appropriate type at read time
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(client_id, key)
);
```

**Example rows for HeyAircon:**
```sql
INSERT INTO config (client_id, key, value) VALUES
  ('hey-aircon', 'followup_t1_hours', '2'),
  ('hey-aircon', 'followup_t2_hours', '24'),
  ('hey-aircon', 'followup_abandon_hours', '48'),
  ('hey-aircon', 'followup_enabled', 'true'),
  ('hey-aircon', 'followup_scheduler_interval_minutes', '60'),
  ('hey-aircon', 'followup_t1_message_template', 'Hi {customer_name}! 😊\n\nJust checking in on your aircon servicing booking for {date} ({slot}).\n\nCould you confirm so we can lock it in? If anything''s changed or you''d like a different time, just let me know. 😊'),
  ('hey-aircon', 'followup_t2_message_template', 'Hi {customer_name},\n\nChecking in again about your appointment on {date} ({slot}). We''d love to lock this in for you!\n\nIf you need to reschedule or have any questions, feel free to reach out. We want to make sure everything works for you. 👍'),
  ('hey-aircon', 'followup_optout_reply', 'Understood! We won''t send any more follow-up messages about this booking. If you need anything, feel free to reach out anytime. 😊');
```

### Message Template Interpolation

Message templates are stored as strings with `{placeholder}` syntax. At send time, the scheduler replaces placeholders with booking-specific data:

| Placeholder | Source | Example |
|-------------|--------|---------||
| `{customer_name}` | `customers.name` or `customers.phone_number` if name unavailable | "Sarah" or "+65 1234 5678" |
| `{date}` | `bookings.slot_date` formatted as "25 April" | "25 April" |
| `{slot}` | `bookings.slot_time` mapped to AM/PM/Evening | "AM slot" |

**Implementation notes:**
- Use Python `str.format()` or f-string interpolation at send time
- If a placeholder value is NULL or missing, use a fallback (e.g., `{customer_name}` → "there" if name is NULL)
- Escape single quotes in config values as `''` (SQL standard) when inserting

### Why Supabase `config` Table (Not Env Vars)?

- **Per-client values:** Each client has their own timing preferences and message copy. Env vars are infrastructure-level and don't support per-client keying without namespacing chaos.
- **No redeploy needed:** Changing a threshold or message template is a Supabase Studio update, live immediately on next scheduler run.
- **Consistency:** The `config` table is already used for business data (services, pricing, policies) loaded by `context_builder`. Follow-up config follows the same pattern.
- **Admin-editable in Phase 2:** The CRM interface (Phase 2) can expose these as form fields for client self-service editing.

---

## Scheduler Design Requirements

### Functional Requirements

The scheduler must:
1. Run on a fixed interval (recommended: every 1 hour)
2. Query the `bookings` and `customers` tables for eligible bookings at each follow-up stage (T+2h, T+24h, T+48h)
3. Send WhatsApp messages via Meta Cloud API for T+2h and T+24h stages
4. Update `last_followup_sent_at`, `followup_stage`, and optionally `abandoned_at` for each processed booking
5. Log all outbound follow-up messages to `interactions_log` (same as agent-generated messages)
6. Handle Meta API failures gracefully — if a message send fails, log the failure and retry on the next scheduler run (do not mark as sent)

### Implementation Options

The software-architect must choose one of the following approaches based on platform constraints and maintainability:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. APScheduler (in-process)** | Python APScheduler runs inside the FastAPI app as a background task, triggered at fixed intervals | Simple to deploy (no new infra); uses existing FastAPI + Supabase stack | Requires the FastAPI service to stay alive 24/7; scheduler state is in-memory (lost on redeploy) |
| **B. Railway Cron Job** | Railway Cron triggers a standalone script endpoint (e.g., `POST /internal/cron/followup`) at fixed intervals | Decoupled from main service; stateless (no in-memory concerns); Railway manages scheduling | Requires Railway Pro plan for cron (cost increase); endpoint must be secured (API key check) |
| **C. Supabase pg_cron** | Postgres extension `pg_cron` runs SQL-based jobs inside Supabase, calls FastAPI webhook endpoint | Fully serverless; no in-memory state; database-native scheduling | Limited logic expressibility in SQL; pg_cron not available on all Supabase tiers; harder to test locally |

**Recommendation for Architecture Phase:**  
The product-manager recommends **Option A (APScheduler)** as the simplest path for Phase 1, with a clear migration path to Option B or C if the service uptime or redeploy frequency becomes a concern. The scheduler logic is straightforward enough that moving it between options requires minimal code changes.

### Timing Characteristics

**Maximum drift window:**

Because the scheduler runs on a fixed interval (default: 1 hour), there is a maximum delay between when a booking becomes eligible for follow-up and when the follow-up is actually sent.

**Formula:**  
`Max wait time = threshold + (interval - 1 second)`

**Examples:**
- **T+2h threshold with 1h interval:**  
  Max wait = 2h + 59m 59s = **2h 59m 59s**  
  *Scenario:* Customer goes silent at 5:01 PM. Scheduler runs at 5:00, 6:00, 7:00 (1h 59m elapsed, not eligible yet), 8:00 PM (2h 59m elapsed, triggers).

- **T+24h threshold with 1h interval:**  
  Max wait = 24h + 59m 59s = **24h 59m 59s**

- **T+48h threshold with 1h interval:**  
  Max wait = 48h + 59m 59s = **48h 59m 59s**

**Is this acceptable for Phase 1?**  
✅ **Yes.** For a post-booking follow-up on an aircon servicing appointment, sub-hour precision is not critical. The psychological difference between a follow-up arriving at 2h vs. 2h 45m is negligible. The tradeoff is:
- **Lower infrastructure cost:** 1-hour interval scheduler is lightweight and doesn't require always-on event listeners
- **Simpler implementation:** Fixed-interval batch processing is easier to test and debug than event-driven triggers

**What would be needed to reduce drift?**
- **15-min interval scheduler:** Reduces max drift to ~15min but increases scheduler overhead 4x
- **Event-driven trigger:** On booking creation, schedule a delayed job (e.g., using Railway scheduled tasks, Supabase pg_cron, or a job queue like BullMQ) that fires exactly at T+2h. Adds architectural complexity and new infra dependencies.

**Recommendation:** Keep 1-hour interval for Phase 1. Evaluate tighter timing only if customer feedback indicates that follow-up timing is a pain point.

---

### Non-Functional Requirements

- **Idempotency:** Running the scheduler multiple times in quick succession (e.g., due to a service restart) must not send duplicate follow-up messages. Use `followup_stage` as the idempotency key.
- **Timezone Handling:** All timestamps must be stored in UTC and converted to Singapore Time (GMT+8) for customer-facing display (e.g., "Your appointment on 25 April (AM slot)").
- **Retry Logic:** If Meta API returns a 5xx error or times out, the scheduler should not mark the booking as having received the follow-up. On the next scheduler run, the booking will be eligible again. Exponential backoff is not required for Phase 1.
- **Observability:** Each scheduler run must log:
  - Number of bookings processed at each stage
  - Number of successful message sends
  - Number of Meta API failures
  - Total runtime
  - Recommend writing these to a new `scheduler_runs` table in shared Supabase for monitoring

---

## Booking Status State Machine — Implementation Impact

### Current Implementation vs. Required Design

**Current State (as of 2026-04-22):**
- The `write_booking` tool (`engine/core/tools/booking_tools.py`) is a single atomic operation:
  1. Creates Google Calendar event
  2. INSERTs booking row into Supabase `bookings` table with `booking_status = 'Confirmed'` (capital C)
- There is **no two-step flow** — the booking is confirmed immediately when the agent calls `write_booking`
- `check_calendar_availability` queries **Google Calendar only** — it does not check the `bookings` table
- This means: if a booking row exists in Supabase without a calendar event, `check_calendar_availability` would not detect that slot as taken (race condition)

**Required Design (Founder Decision 2026-04-22):**

To prevent slot conflicts during the window between when the agent sends the booking summary and when the customer confirms, the booking flow must be split into a **two-step write**:

### Two-Step Write Flow

#### Step 1: At `pending_confirmation` Status (Agent Sends Booking Summary)

**When:** The agent has collected all booking details and is ready to send the confirmation summary message to the customer

**What happens:**
1. Agent calls a **modified `write_booking` tool** (or renamed tool like `create_pending_booking`)
2. Tool INSERTs booking row into `bookings` table with:
   - `booking_status = 'pending_confirmation'`
   - All booking details (service, date, slot, address, etc.)
   - `created_at` timestamp
3. **No Google Calendar event is created yet**
4. Tool returns `{booking_id, status: 'pending_confirmation', ...}` to the agent
5. Agent sends confirmation summary message to customer: "Here's your booking summary... [details]. Please confirm to finalize."

**Purpose:** The DB row holds the slot — prevents double-booking during the confirmation window.

#### Step 2: At `confirmed` Status (Customer Confirms Intent)

**When:** The customer replies to the booking summary with affirmative intent (detected by the LLM agent — see "Confirmation Detection" section below)

**What happens:**
1. Agent calls a **new `confirm_booking` tool** with the `booking_id`
2. Tool performs a **Google Calendar slot conflict check** (not `bookings` table):
   - Query Google Calendar API for events on the slot's `slot_date` and `slot_window`
   - If an event exists for that slot: conflict detected (another customer has confirmed this slot first)
3. **If no conflict:**
   - Create Google Calendar event via `create_booking_event()`
   - UPDATE `bookings` SET `booking_status = 'confirmed'`, `calendar_event_id = <event_id>`, `confirmed_at = NOW()`
   - Return success to agent: `{status: 'confirmed', calendar_event_id, ...}`
   - Agent tells customer: "✅ Your booking is confirmed! Booking ID: [booking_id]"
4. **If conflict detected:**
   - UPDATE the current booking: `booking_status = 'cancelled'`, `cancellation_reason = 'slot_conflict'`
   - Return conflict error to agent: `{status: 'conflict', message: 'Slot has been taken by another booking'}`
   - Agent tells customer: "Sorry [name], that slot has just been taken by another booking. Let me check the next available slot for you."
   - Agent immediately calls `check_calendar_availability` to offer alternatives

**Purpose:** Ensures only one booking wins the slot; calendar event is created only after customer confirmation.

### Tool Surface Changes

| Tool | Current Behavior | New Behavior | Breaking Change? |
|------|------------------|--------------|------------------|
| `write_booking` | Creates calendar event + INSERTs DB row with `booking_status='Confirmed'` | Only INSERTs DB row with `booking_status='pending_confirmation'` — **no calendar event** | ✅ **YES** — agents and tests calling `write_booking` will no longer get a calendar event or confirmed status |
| `confirm_booking` | *(Does not exist)* | New tool — checks Google Calendar for slot conflicts, creates calendar event if free, updates status to `'confirmed'` | N/A (new) |
| `check_calendar_availability` | Queries Google Calendar only | **No change** — continues to query Google Calendar only (does NOT check `bookings` table) | ❌ **NO** — availability logic unchanged |

### Impact on `check_calendar_availability` Implementation

**Current query logic:**
```python
# Queries Google Calendar API for events on slot_date
# Returns AM/PM availability based on calendar events only
```

**Required query logic (Founder Decision 2026-04-22 — NO CHANGE):**
```python
# Query Google Calendar API for events on slot_date
# Returns AM/PM availability based on calendar events only
# Does NOT check the bookings table
```

**Why this approach:**
- Simplifies implementation — no need to query both Calendar and DB, merge results, or manage slot hold TTL
- Slot conflicts are detected at `confirm_booking` time (when the customer explicitly says "yes"), not at availability check time
- If two customers both create `pending_confirmation` bookings for the same slot, the first to confirm wins; the second gets a conflict error and is offered alternatives
- Trade-off: Small race window where two customers can both see a slot as available and both think they have it temporarily — resolved definitively at confirmation

### Slot Conflict Scenario (Acceptance Criteria)

**Example Timeline (no slot hold):**
- 10:00 AM: Customer A creates `pending_confirmation` booking for 25 April PM slot
- 10:05 AM: Customer B asks for availability on 25 April
  - `check_calendar_availability` queries Google Calendar only (does NOT check `bookings` table)
  - No calendar event exists yet (Customer A hasn't confirmed), so returns "PM slot available"
- 10:06 AM: Customer B creates `pending_confirmation` booking for 25 April PM slot (same slot as Customer A)
- 10:10 AM: Customer A confirms → `confirm_booking` checks Google Calendar, sees no conflict, succeeds, creates calendar event
- 10:11 AM: Customer B confirms → `confirm_booking` checks Google Calendar, detects conflict (Customer A's event exists), returns conflict error
  - Customer B's booking updated to `cancelled` (reason: slot conflict)
  - Agent tells Customer B: "Sorry [name], that slot has just been taken by another booking. Let me check the next available slot for you."
  - Agent calls `check_calendar_availability` to offer alternatives

**Edge Case: Customer A and Customer B both confirm at nearly the same time:**
- Both have `pending_confirmation` bookings for the same slot (DB row IDs differ)
- Customer A's `confirm_booking` runs first → succeeds, creates calendar event
- Customer B's `confirm_booking` runs 2 seconds later → Google Calendar slot conflict check detects Customer A's event → returns conflict error to agent → Customer B is offered alternatives

**Edge Case: Customer never confirms, then confirms late:**
- 10:00 AM: Customer A creates `pending_confirmation` booking
- Customer A goes silent → at T+48h, booking marked `abandoned`
- 3 days later: Customer A replies "yes, confirm"
- Agent calls `confirm_booking` → checks Google Calendar:
  - If slot is still free → creates calendar event, updates status to `confirmed`, agent confirms to customer
  - If slot has been taken by another customer → agent informs customer: "Sorry [name], that slot is no longer available. Let me find you another slot."

### Migration Notes for Existing Codebase

**Data Migration Required:**
- Existing bookings with `booking_status = 'Confirmed'` (capital C) should be normalized to lowercase `'confirmed'` for consistency
- Check if any existing bookings are truly pending (confirmation message sent but no customer reply) — those should be updated to `'pending_confirmation'` to enter the follow-up flow

**Code Migration Required:**
- Update agent system prompt to reflect the two-step flow: "After collecting all booking details, call `write_booking` to create a pending booking, send the summary to the customer, and wait for their confirmation. When they confirm, call `confirm_booking` to finalize."
- Update test cases that call `write_booking` — they must now handle `pending_confirmation` status and call `confirm_booking` separately if testing the full flow
- Add `confirm_booking` tool definition to `engine/core/tools/__init__.py`
- Implement `confirm_booking` tool: checks Google Calendar for slot conflicts, creates calendar event if free, offers alternatives if taken

---

## Confirmation Detection

### How Customer Confirmation is Detected

Customer confirmation after the booking summary message is sent is **detected by the LLM agent**, not by keyword matching or regex. This is a natural-language understanding task that LLMs handle well.

**Rationale:**
- Customers reply in many ways: slang, short forms, typos, Singlish variants ("ok lah", "yep", "confirm lor", "ya", "can", "👍", "sure thing", "yes pls")
- A keyword list (e.g., `["yes", "ok", "confirm"]`) will miss too many valid affirmations and may false-positive on unrelated uses of those words (e.g., "ok, but can I change the date?")
- The LLM agent is already processing every customer message — leveraging its intent classification capability is simpler and more robust than building a custom NLP classifier

### Implementation Approach

**Confirmation detection is NOT a separate LLM API call.** It rides on the standard agent turn when the customer replies after receiving the booking summary.

**System Prompt Instructions (to be added to `engine/core/context_builder.py`):**

```
When a customer has a booking in 'pending_confirmation' status:
- If the customer's reply is an affirmation of the booking summary (any form of agreement: yes, ok, confirm, sure, sounds good, including slang, short forms, emojis like 👍, Singlish expressions), call the `confirm_booking` tool with the booking_id to finalize the booking.
- If the customer's reply indicates they do NOT want to proceed (e.g., "wait", "change", "different date", "actually no", "cancel"), do NOT call `confirm_booking`. Instead, handle their intent normally:
  - Reschedule request → ask for new date/time, call `check_calendar_availability`, create new pending booking
  - Cancellation → call `cancel_booking` tool
  - Clarification question → answer the question
- If the customer's reply is ambiguous or unrelated to the booking (e.g., asking about pricing, services), respond to their question and gently prompt for confirmation: "Also, just to confirm — are we good to finalize your booking for [date] ([slot])?"
```

**Tool Definition for `confirm_booking`:**

```python
{
    "name": "confirm_booking",
    "description": "Finalize a pending booking after the customer confirms. Checks for slot conflicts, creates the Google Calendar event, and updates booking status to 'confirmed'. Call this ONLY when the customer has explicitly agreed to the booking summary (e.g., 'yes', 'ok', 'confirm', 'sounds good', including slang and emojis).",
    "input_schema": {
        "type": "object",
        "properties": {
            "booking_id": {
                "type": "string",
                "description": "The booking ID returned by write_booking when the pending booking was created. Format: HA-YYYYMMDD-XXXX."
            }
        },
        "required": ["booking_id"]
    }
}
```

### Agent Decision Tree

```
Customer replies after receiving booking summary
    |
    ├─ Affirmative intent detected? (yes/ok/confirm/👍/etc.)
    |    └─> Call confirm_booking(booking_id)
    |          ├─ Success → tell customer "✅ Confirmed! Booking ID: [id]"
    |          └─ Conflict → tell customer "Slot taken, let me find alternatives"
    |
    ├─ Negative intent detected? (wait/change/cancel/no)
    |    └─> Handle intent (reschedule flow, cancellation, clarification)
    |
    └─ Ambiguous or unrelated?
         └─> Answer question + prompt: "Are we good to finalize your booking?"
```

### Non-Confirmation Examples (Agent Must NOT Call `confirm_booking`)

These replies should NOT trigger `confirm_booking`:
- "Wait, can I change to a different date?"
- "Actually, I need to check with my wife first"
- "How much is the service again?"
- "What if I need to cancel later?"
- "Ok, but I'm not available in the morning"
- "Yes, I understand the pricing, but can I reschedule?"

The agent must distinguish between:
- **Confirmation of the booking** ("yes, let's do it")
- **Acknowledgment without commitment** ("yes, I understand" or "ok, but...")

### Failure Mode: LLM Misclassifies Confirmation

**If the LLM incorrectly calls `confirm_booking` when the customer didn't intend to confirm:**
- The booking is finalized in the DB + calendar event created
- The customer's next message likely indicates confusion or correction ("wait, I didn't confirm that")
- The agent must handle this as a **reschedule or cancellation request** — the standard tools (`cancel_booking`, `write_booking` for new slot) already support this
- **No special error recovery needed** — the customer can reschedule or cancel at any time, even after confirmation

**If the LLM fails to call `confirm_booking` when the customer DID confirm:**
- The booking remains in `pending_confirmation` status
- The follow-up sequence (T+2h, T+24h) will trigger as normal
- The customer will receive a follow-up message asking them to confirm
- The customer can reply again, and the agent gets another chance to detect confirmation
- **Impact:** Minor UX friction (extra follow-up message), but recoverable

**Monitoring Recommendation:**
- Track `pending_confirmation` bookings that transition to `abandoned` without ever reaching `confirmed` — if this rate is high (>20%), investigate whether the LLM is consistently missing confirmation intent and adjust system prompt or add a confirmation guardrail prompt

---

## Acceptance Criteria

### AC-FOLLOWUP-01: T+2h Follow-up Triggers Correctly

**Given:** A booking is created at 10:00 AM with `booking_status='pending_confirmation'` and the customer sends no further messages  
**When:** The scheduler runs at 12:05 PM  
**Then:**  
- The T+2h follow-up message is sent to the customer
- The booking's `followup_stage` is updated to `'2h_sent'`
- The booking's `last_followup_sent_at` is set to 12:05 PM
- The outbound message is logged in `interactions_log` with `direction='outbound'`

---

### AC-FOLLOWUP-02: T+24h Follow-up Triggers Correctly

**Given:** A booking received its T+2h follow-up at 12:00 PM on Day 1 and the customer has not replied  
**When:** The scheduler runs at 12:05 PM on Day 2  
**Then:**  
- The T+24h follow-up message is sent
- The booking's `followup_stage` is updated to `'24h_sent'`
- The booking's `last_followup_sent_at` is updated to 12:05 PM Day 2

---

### AC-FOLLOWUP-03: T+48h Abandon Mark Applied

**Given:** A booking received its T+24h follow-up at 12:00 PM on Day 2 and the customer has not replied  
**When:** The scheduler runs at 12:05 PM on Day 3  
**Then:**  
- No message is sent to the customer
- The booking's `booking_status` is updated to `'abandoned'`
- The booking's `followup_stage` is updated to `'abandoned'`
- The booking's `abandoned_at` is set to 12:05 PM Day 3

---

### AC-FOLLOWUP-04: Customer Reply Stops Follow-up Sequence

**Given:** A booking received its T+2h follow-up at 12:00 PM and the customer replies at 1:00 PM  
**When:** The scheduler runs at 12:05 PM the next day (T+24h)  
**Then:**  
- No T+24h follow-up message is sent
- The booking's `followup_stage` remains `'2h_sent'` (not advanced)

---

### AC-FOLLOWUP-05: Escalated Customers Are Excluded

**Given:** A booking has `booking_status='pending_confirmation'` and the customer is later escalated (`escalation_flag=True`) before the T+2h follow-up runs  
**When:** The scheduler runs at T+2h  
**Then:**  
- No follow-up message is sent
- The booking's `followup_stage` remains `NULL`
- The booking remains eligible for follow-up if `escalation_flag` is later cleared

---

### AC-FOLLOWUP-06: Opt-Out Stops Follow-ups

**Given:** A booking received its T+2h follow-up and the customer replies "stop"  
**When:** The opt-out handler processes the message  
**Then:**  
- The booking's `followup_stage` is updated to `'opted_out'`
- A confirmation message is sent: "Understood! We won't send any more follow-up messages..."
- The scheduler never sends T+24h or T+48h follow-ups for this booking

---

### AC-FOLLOWUP-07: Idempotency — No Duplicate Messages

**Given:** A booking is eligible for the T+2h follow-up and the scheduler runs twice within 5 minutes (e.g., due to a service restart)  
**When:** The second scheduler run queries for eligible bookings  
**Then:**  
- The booking is not returned by the query (because `followup_stage='2h_sent'` after the first run)
- No duplicate message is sent

---

### AC-FOLLOWUP-08: Meta API Failure Handling

**Given:** A booking is eligible for the T+2h follow-up and the Meta API returns a 500 error  
**When:** The scheduler processes the booking  
**Then:**  
- The error is logged to `api_incidents` (shared Supabase)
- The booking's `followup_stage` remains `NULL` (not marked as sent)
- The booking is eligible for retry on the next scheduler run

---

### AC-FOLLOWUP-09: Customer Re-engages After Abandon Mark

**Given:** A booking was marked abandoned at T+48h (`followup_stage='abandoned'`, `booking_status='abandoned'`)  
**When:** The customer sends a message 3 days later: "Hi, is my booking still on?"  
**Then:**  
- The agent responds normally (no error, no special handling)
- The booking's `followup_stage` remains `'abandoned'`
- The booking's `booking_status` remains `'abandoned'` — **human admin must manually revert to `'confirmed'` if re-confirming**

---

### AC-FOLLOWUP-10: Message Copy Matches Persona

**Given:** A follow-up message is sent at T+2h or T+24h  
**When:** A human reviewer reads the message  
**Then:**  
- The message uses the customer's name (if available)
- The message includes the appointment date and time window
- The tone is warm, professional, and reassuring (consistent with HeyAircon persona)
- No technical jargon or cold corporate language

---

### AC-FOLLOWUP-11: Slot Conflict Detection on Confirmation

**Given:** Customer A creates a `pending_confirmation` booking for 25 April PM slot at 10:00 AM and Customer B creates a `pending_confirmation` booking for the same slot at 10:05 AM  
**When:** Customer A confirms at 10:10 AM (calls `confirm_booking` first) and Customer B confirms at 10:11 AM  
**Then:**  
- Customer A's `confirm_booking` succeeds: `booking_status = 'confirmed'`, calendar event created
- Customer B's `confirm_booking` detects conflict: returns `{status: 'conflict', message: '...'}`
- Customer B's booking is updated: `booking_status = 'cancelled'`, `cancellation_reason = 'slot_conflict'`
- Agent tells Customer B: "Sorry [name], that slot has just been taken by another booking. Let me check the next available slot for you."
- Agent immediately calls `check_calendar_availability` to offer Customer B alternatives

---

### AC-FOLLOWUP-12: Slot Conflict Detected at `confirm_booking` Time

**Given:** Customer A creates a `pending_confirmation` booking for 25 April PM slot at 10:00 AM  
**When:** Customer B asks for availability on 25 April at 10:05 AM (Customer A hasn't confirmed yet)  
**Then:**  
- `check_calendar_availability` queries Google Calendar only (does NOT check `bookings` table)
- No calendar event exists yet (Customer A hasn't confirmed), so PM slot is returned as available
- Customer B can create a `pending_confirmation` booking for the same slot

**Follow-up scenario (conflict at confirmation time):**  
**Given:** Both Customer A and Customer B have `pending_confirmation` bookings for 25 April PM slot  
**When:** Customer A confirms at 10:10 AM and Customer B confirms at 10:12 AM  
**Then:**  
- Customer A's `confirm_booking` succeeds → creates calendar event, status → `confirmed`
- Customer B's `confirm_booking` detects conflict (Customer A's calendar event exists) → returns conflict error
- Customer B's booking → `cancelled` (reason: slot conflict)
- Agent offers Customer B alternatives via `check_calendar_availability`

---

### AC-FOLLOWUP-13: LLM Detects Confirmation Intent (Affirmative Cases)

**Given:** A booking is in `pending_confirmation` status and the agent has sent the confirmation summary  
**When:** The customer replies with any of the following: "yes", "ok", "confirm", "yep", "sure", "sounds good", "ok lah", "can", "👍", "let's do it"  
**Then:**  
- The agent calls `confirm_booking` with the `booking_id`
- If no slot conflict: booking is confirmed, calendar event created, agent replies with confirmation message
- The customer does NOT receive a T+2h follow-up (because they replied)

---

### AC-FOLLOWUP-14: LLM Does Not Misclassify Non-Confirmations

**Given:** A booking is in `pending_confirmation` status and the agent has sent the confirmation summary  
**When:** The customer replies with any of the following: "wait", "can I change the date?", "how much is it?", "ok, but I need morning slot", "yes, I understand, but..."  
**Then:**  
- The agent does NOT call `confirm_booking`
- The agent handles the customer's request normally (answers question, offers reschedule flow, etc.)
- The booking remains in `pending_confirmation` status

---

### AC-FOLLOWUP-15: Confirmation Intent Detection Handles Singlish and Slang

**Given:** A booking is in `pending_confirmation` status  
**When:** The customer replies with Singlish or slang affirmations: "ok lor", "can lah", "confirm liao", "shiok", "yup yup"  
**Then:**  
- The agent correctly identifies these as confirmation intent
- The agent calls `confirm_booking`
- Booking is finalized

---

### AC-FOLLOWUP-16: Late Confirmation (Slot Still Free)

**Given:** A booking is in `pending_confirmation` status and the customer has not replied for several days  
**When:** The customer replies "yes, confirm" 5 days later  
**Then:**  
- Agent calls `confirm_booking` with the booking ID
- Tool checks Google Calendar for slot conflicts — no conflicts found
- Calendar event is created
- Booking status updated to `'confirmed'`
- Agent confirms to customer: "✅ Your booking is confirmed! Booking ID: [id]"

---

### AC-FOLLOWUP-17: Late Confirmation (Slot Taken)

**Given:** A booking is in `pending_confirmation` status and another customer has booked the same slot in the meantime  
**When:** The original customer replies "yes, confirm" late  
**Then:**  
- Agent calls `confirm_booking` with the booking ID
- Tool checks Google Calendar — conflict detected (another calendar event exists for that slot)
- Booking status updated to `'cancelled'`, `cancellation_reason = 'slot_conflict'`
- Agent informs customer: "Sorry [name], that slot is no longer available. Let me find you another slot." and offers alternatives

---

## Out of Scope for Phase 1

The following are explicitly **not included** in this feature and should be deferred to Phase 2 or later:

| Item | Rationale |
|------|-----------|
| **SMS or email fallback** | WhatsApp is the only supported channel. Multi-channel outreach adds complexity and cost. |
| **Rescheduling directly in the follow-up message** | The follow-up message only offers the *path* to reschedule ("let me know anytime"). The customer initiates rescheduling in a new conversation thread handled by the agent's standard flow. Inline rescheduling (e.g., WhatsApp quick-reply buttons) requires interactive message support not in Phase 1. |
| **Dynamic per-message timing** | T+2h, T+24h, T+48h intervals are client-configurable via the `config` table (see "Client-Configurable Variables" section), but the *sequence structure* (three stages: T1, T2, abandon) is fixed. Adding a fourth follow-up stage or conditional branching (e.g., send T+12h only if it's a weekend booking) is a Phase 2 enhancement. |
| **Follow-up for other booking states** | Only `'pending_confirmation'` bookings enter the follow-up sequence. Bookings marked `'confirmed'`, `'rescheduled'`, `'cancelled'`, or `'completed'` do not trigger follow-ups (they are already engaged or closed). |
| **Rich message formatting** | Phase 1 uses plain text messages with emoji. WhatsApp rich media (buttons, carousels, images) is not supported. Interactive rescheduling (e.g., "Tap here to reschedule") requires Meta interactive message API support, deferred to Phase 2. |
| **Analytics dashboard for follow-up effectiveness** | Admins can query `followup_stage` and `abandoned_at` in Supabase Studio manually. A dedicated dashboard showing follow-up → re-engagement rates is a Phase 2 CRM feature. |
| **Follow-up reminder for appointments approaching without prior contact** | This spec covers post-booking follow-up only. Pre-appointment reminders (e.g., "Your appointment is tomorrow") are a separate feature. |

---

## Open Questions

| # | Question | Impact | Blocking? |
|---|----------|--------|-----------|
| **OQ-01** | Should the T+2h interval start from `created_at` (when the booking was created) or from the timestamp of the confirmation message in `interactions_log`? | Affects query logic — `created_at` is simpler but less accurate if there's a delay between booking creation and confirmation message send | No — recommend using `created_at` for simplicity in Phase 1; refine in Phase 2 if needed |
| **OQ-02** | Should abandoned bookings automatically cancel the Google Calendar event, or should the human admin decide? | Affects whether `core/scheduler/followup.py` calls `google_calendar.cancel_event()` at T+48h | No — **Not applicable.** Under the two-step flow, abandoned bookings never have a calendar event (they never reached `confirmed` status). This question only applies if we add pre-appointment reminders in Phase 2 and a `confirmed` booking becomes unresponsive. |
| **OQ-03** | If a customer opts out of follow-ups for one booking, should all future bookings by the same customer also skip follow-ups? | Affects whether opt-out is booking-scoped (`followup_stage` column) or customer-scoped (new `customers.followup_opt_out` column) | No — recommend **booking-scoped** for Phase 1; customer-level opt-out is a Phase 2 privacy enhancement |
| **OQ-04** | Should the scheduler run every 1 hour, or more/less frequently? | Affects how soon after eligibility a follow-up is sent (1-hour delay vs. sub-hour delay) | No — 1-hour interval is sufficient for Phase 1; can be tuned based on operational feedback |
| **OQ-05** | Should follow-ups continue if the appointment date has already passed? | Affects query logic — should we add `AND slot_date >= CURRENT_DATE` to scheduler queries? | No — recommend **yes, add date check** to avoid sending follow-ups for past bookings that were never marked completed |
| **OQ-06** | At what point in the conversation does the agent call `write_booking` to create the `pending_confirmation` booking? After `check_calendar_availability` returns available slots, or only after the customer explicitly agrees to a specific slot? | Affects when the slot is reserved in the DB. If created too early (before customer picks a slot), multiple `pending_confirmation` rows might be created and then cancelled, cluttering the DB. If created too late (after customer says "yes"), there's a small race window where another customer could book the slot between `check_calendar_availability` and `write_booking`. | No — **Founder decision needed.** Product-manager recommendation: Create `pending_confirmation` booking ONLY after customer has selected a specific date+slot and the agent has verbally confirmed it back to them (e.g., "Great! I'm booking you for 25 April, PM slot. Let me prepare your confirmation summary."). Then call `write_booking`, send summary, wait for final confirmation. This minimizes abandoned `pending_confirmation` rows while keeping the race window very small (seconds, not minutes). |

---

## Success Metrics (Post-Launch)

Once this feature is live, the following metrics should be tracked to assess effectiveness:

- **Re-engagement rate:** % of bookings that receive a customer reply after T+2h or T+24h follow-up
- **Abandon rate:** % of confirmed bookings that reach T+48h abandoned state
- **No-show rate:** % of abandoned bookings that were no-shows on the scheduled appointment date
- **Opt-out rate:** % of bookings that opt out of follow-ups

These metrics inform whether the timing, messaging, or flow needs adjustment in Phase 2.

---

## Handoff Notes for @software-architect

This spec is ready for architecture design. Key decisions needed from you:

1. **Scheduler implementation choice** (APScheduler vs. Railway Cron vs. pg_cron) — see "Scheduler Design Requirements" section for options and trade-offs
2. **File structure** — recommend creating `core/scheduler/followup.py` for the scheduler logic and `core/scheduler/queries.py` for the SQL queries
3. **Where opt-out detection lives** — specified as `core/message_handler.py` pre-processing, but confirm if you prefer a separate `core/opt_out_handler.py` module
4. **Logging approach for scheduler runs** — recommend a new `scheduler_runs` table in shared Supabase; confirm schema design
5. **Message template storage** — specified as Supabase `config` table (client-configurable), confirm if you prefer a different approach
6. **Tool surface refactor** (BREAKING CHANGE) — see "Booking Status State Machine — Implementation Impact" section:
   - `write_booking` must be modified to only write DB row with `pending_confirmation` status (no calendar event)
   - New `confirm_booking` tool must be created: slot conflict check + calendar event creation + status update to `confirmed`
   - `check_calendar_availability` must be updated to query BOTH Google Calendar AND `bookings` table
   - Confirm file structure for new tool (`engine/core/tools/booking_tools.py` or separate file?)
   - Migration plan for existing `booking_status = 'Confirmed'` rows → normalize to `'confirmed'`
7. **Confirmation detection** — see "Confirmation Detection" section:
   - System prompt must instruct agent to call `confirm_booking` when customer confirms
   - Tool definition for `confirm_booking` must be added to `engine/core/tools/__init__.py`
   - Confirm if additional guardrails or prompt engineering are needed to reduce false positives/negatives

Open Questions OQ-01 through OQ-06 are non-blocking but should be resolved before implementation starts. Recommend founder approval on:
- OQ-02 (auto-cancel calendar events for abandoned bookings) — note: under new flow, abandoned bookings never have calendar events
- OQ-05 (date check to skip follow-ups for past bookings)
- **OQ-06 (when to create `pending_confirmation` booking)** — this affects agent conversation flow and DB write timing, needs founder decision

**Critical path dependencies:**
- The two-step booking flow (Change 5) must be implemented BEFORE the follow-up scheduler, because the scheduler depends on `pending_confirmation` status existing
- The `confirm_booking` tool (Change 4) must be implemented alongside the `write_booking` refactor to maintain a working booking flow
- Recommend implementing in this order: (1) Tool refactor + confirmation detection, (2) Test with manual confirmation, (3) Build scheduler

**Testing requirements:**
- Unit tests for slot conflict detection in `confirm_booking`
- Integration tests for `check_calendar_availability` querying both Calendar + DB
- End-to-end test: two customers booking same slot, first confirms successfully, second gets conflict error
- LLM confirmation detection test cases (see AC-FOLLOWUP-13, 14, 15)

---
