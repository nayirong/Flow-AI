# Proactive Follow-up Flow — Technical Architecture

**Feature ID:** REQ-FOLLOWUP-001  
**Architecture Version:** 1.0  
**Created:** 2026-04-22  
**Status:** Ready for Implementation  

---

## 1. Executive Summary

This document specifies the complete technical architecture for the Proactive Follow-up Flow feature, which implements automated, timed WhatsApp check-ins for customers who book appointments but remain silent post-confirmation.

**Key architectural decisions:**
- **Scheduler:** APScheduler running in-process (Phase 1; migration path defined)
- **Booking status split:** `write_booking` → `pending_confirmation` (DB only), `confirm_booking` → `confirmed` (DB + calendar)
- **Schema changes:** 3 new columns on `bookings` table
- **Breaking changes:** Tool surface and system prompt require coordinated updates

**Migration risk:** HIGH — `write_booking` behavior change affects all active bookings. Requires DDL-first deployment sequence and backward-compatibility handling.

---

## 2. Scheduler Design

### 2.1 Technology Choice: APScheduler (In-Process)

**Decision:** Use APScheduler running inside the FastAPI application process for Phase 1.

**Rationale:**
1. **Zero new infrastructure** — no Railway Cron (requires Pro plan), no pg_cron (limited logic expressibility, not available on all Supabase tiers)
2. **Simplest deployment** — scheduler lifecycle tied to the FastAPI service; starts/stops automatically
3. **Immediate iteration** — Python-based scheduler logic lives in the codebase; no external job definitions to manage
4. **Acceptable drift** — 1-hour interval produces max 2h 59m delay for T+2h trigger (see §2.3); sufficient for post-booking follow-up use case
5. **Clear migration path** — if uptime or redeploy frequency becomes a concern, move to Railway Cron (Option B) or Supabase pg_cron (Option C) with minimal code changes (scheduler function is already idempotent and stateless)

**Tradeoff:** APScheduler state is in-memory. On Railway service restart/redeploy, the scheduler restarts and recalculates eligible bookings from the database — no job state is lost because eligibility is determined by `bookings` table timestamps and `followup_stage`, not by scheduler memory.

### 2.2 Scheduler Implementation

**File:** `engine/core/followup_scheduler.py` (NEW)

**Initialization (main.py):**
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from engine.core.followup_scheduler import run_followup_scheduler_job

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_scheduler():
    scheduler.add_job(
        run_followup_scheduler_job,
        trigger="interval",
        minutes=60,  # Default — overridable by env var FOLLOWUP_SCHEDULER_INTERVAL_MINUTES
        id="followup_scheduler",
    )
    scheduler.start()
    logger.info("Proactive follow-up scheduler started (interval: 60 minutes)")

@app.on_event("shutdown")
async def shutdown_scheduler():
    scheduler.shutdown()
```

**Job function signature:**
```python
async def run_followup_scheduler_job() -> None:
    """
    Background job: query all active clients, then for each client query their
    per-client Supabase for bookings eligible for follow-up at each stage.
    
    Runs every N minutes (default 60). Idempotent — safe to call multiple times
    in quick succession (followup_stage prevents duplicate sends).
    
    Stages processed per run:
        1. T+2h  (followup_stage IS NULL → update to '2h_sent')
        2. T+24h (followup_stage = '2h_sent' → update to '24h_sent')
        3. T+48h (followup_stage = '24h_sent' → update to 'abandoned')
    
    For each eligible booking:
        - Load per-client config for message template and thresholds
        - Send WhatsApp message (T+2h and T+24h only; T+48h is silent mark)
        - Update booking: last_followup_sent_at, followup_stage, abandoned_at
        - Log outbound to interactions_log
        - Log scheduler run metrics to scheduler_runs table (observability)
    
    All Supabase and Meta API failures are caught and logged — a single booking
    failure does not stop the scheduler run.
    """
```

**Per-client iteration logic:**
1. Query shared Supabase `clients` table for `is_active = true` rows
2. For each client:
   - Load client config (from shared `clients` + per-client env vars)
   - Open per-client Supabase connection
   - Load follow-up config from per-client `config` table (thresholds, templates, enabled flag)
   - If `followup_enabled = false`, skip client
   - Run 3 stage queries (T+2h, T+24h, T+48h) in sequence
   - For each eligible booking: send message (stages 1 & 2) or mark (stage 3), update DB, log
3. Log aggregate metrics to shared `scheduler_runs` table (new table — see §3.3)

**Idempotency guarantee:** `followup_stage` column is the single source of truth. Each stage update is atomic. If the scheduler runs twice in quick succession (e.g., due to a restart), the second run finds zero eligible bookings because `followup_stage` has already been updated.

### 2.3 Timing Characteristics

**Scheduler interval:** 60 minutes (default)

**Maximum follow-up delay formula:**
```
Max delay = threshold + (interval - 1 second)
```

**Examples:**
- **T+2h:** Max delay = 2h 59m 59s (booking at 5:01 PM → follow-up between 7:01 PM and 8:00 PM)
- **T+24h:** Max delay = 24h 59m 59s
- **T+48h:** Max delay = 48h 59m 59s (abandon mark)

**Acceptability:** ✅ YES for Phase 1. Post-booking follow-up does not require sub-hour precision. The psychological difference between a 2h and 2h 45m check-in is negligible for an aircon servicing appointment scheduled days in the future.

**Future tightening (if needed):**
- Reduce interval to 15 minutes (4x overhead, max drift ~15min)
- Event-driven trigger (scheduled jobs per booking; requires new infra like BullMQ or Railway scheduled tasks)

### 2.4 Silence Detection Logic

**Definition of "silent":** A customer is silent when no inbound messages exist from them after the booking row was created (`bookings.created_at`).

**Timestamp reference:** `bookings.created_at` — this is set when the agent calls `write_booking`, which happens immediately before the agent sends the confirmation summary to the customer. It is the natural reference point: any inbound message arriving after this timestamp means the customer replied.

**SQL pattern (used in all 3 stage queries):**
```sql
SELECT b.* FROM bookings b
JOIN customers c ON b.phone_number = c.phone_number
WHERE b.booking_status = 'pending_confirmation'
  AND c.escalation_flag = FALSE  -- Hard gate
  AND b.followup_stage IS NULL  -- Stage-specific condition (T+2h)
  AND b.created_at <= NOW() - INTERVAL '2 hours'  -- Threshold check
  AND NOT EXISTS (
    SELECT 1 FROM interactions_log il
    WHERE il.phone_number = b.phone_number
      AND il.direction = 'inbound'
      AND il.timestamp > b.created_at  -- Any reply after booking row created
  )
```

No substring matching. No new columns. `created_at` is always set and indexed.

**OQ-07 resolution:** Use `bookings.created_at` as the reference timestamp. No `message_category` column needed in Phase 1 or Phase 2.

---

## 3. Supabase Schema Changes

### 3.1 `bookings` Table — New Columns

Add 3 new columns to support follow-up state tracking:

```sql
ALTER TABLE bookings
ADD COLUMN last_followup_sent_at TIMESTAMPTZ,
ADD COLUMN followup_stage TEXT,
ADD COLUMN abandoned_at TIMESTAMPTZ;
```

**Column definitions:**

| Column | Type | Nullable | Purpose | Values |
|--------|------|----------|---------|--------|
| `last_followup_sent_at` | `TIMESTAMPTZ` | Yes | Timestamp of the most recent follow-up message sent. Used to calculate when the next follow-up is due. NULL if no follow-ups sent yet. | NULL or ISO 8601 UTC timestamp |
| `followup_stage` | `TEXT` | Yes | Current stage of the follow-up sequence. Controls which stage query includes this booking. | NULL (not started), `'2h_sent'`, `'24h_sent'`, `'abandoned'`, `'opted_out'` |
| `abandoned_at` | `TIMESTAMPTZ` | Yes | Timestamp when the booking was marked as abandoned (T+48h). NULL unless `followup_stage = 'abandoned'`. Used for reporting and cleanup. | NULL or ISO 8601 UTC timestamp |

**Index recommendations:**
```sql
-- Composite index for scheduler stage queries (high read frequency)
CREATE INDEX idx_bookings_followup_stage_created 
ON bookings(booking_status, followup_stage, created_at) 
WHERE booking_status = 'pending_confirmation';

-- Partial index for abandoned bookings reporting
CREATE INDEX idx_bookings_abandoned 
ON bookings(abandoned_at) 
WHERE followup_stage = 'abandoned';
```

### 3.2 `booking_status` Column — Value Migration

**BREAKING CHANGE:** The `booking_status` column values are changing from title-case (`'Confirmed'`) to snake_case (`'pending_confirmation'`, `'confirmed'`).

**Old behavior:**
- Agent calls `write_booking` → DB INSERT with `booking_status = 'Confirmed'` + Google Calendar event created atomically

**New behavior:**
- Agent calls `write_booking` → DB INSERT with `booking_status = 'pending_confirmation'`, NO calendar event
- Customer confirms → agent calls `confirm_booking` → calendar slot conflict check → calendar event created + `booking_status = 'confirmed'`

**Migration query for existing `'Confirmed'` bookings (HeyAircon live data):**

```sql
-- Step 1: Identify bookings that need status normalization
-- Run this query in Supabase Studio to see how many rows will be affected:
SELECT booking_id, phone_number, slot_date, booking_status, created_at
FROM bookings
WHERE booking_status = 'Confirmed'  -- Title case (old)
ORDER BY created_at DESC;

-- Step 2: Update to lowercase 'confirmed' (safe for already-confirmed bookings)
-- These bookings already have calendar events, so they are genuinely confirmed.
UPDATE bookings
SET booking_status = 'confirmed'
WHERE booking_status = 'Confirmed';

-- Step 3: Verify no 'Confirmed' rows remain
SELECT COUNT(*) FROM bookings WHERE booking_status = 'Confirmed';
-- Expected: 0
```

**When to run this migration:**
1. **Before deploying the new code** (DDL-first deployment — see §6)
2. After adding the 3 new columns (`last_followup_sent_at`, `followup_stage`, `abandoned_at`)
3. In the same Supabase Studio session (no code changes yet)

**Why this is safe:**
- All existing `'Confirmed'` bookings already have calendar events (created by the old `write_booking` implementation)
- Renaming them to `'confirmed'` (lowercase) aligns with the new enum and ensures they are not accidentally flagged as `'pending_confirmation'`
- The scheduler query explicitly checks `booking_status = 'pending_confirmation'` — old `'Confirmed'` bookings (even if not migrated) will not trigger follow-ups

**OQ-08 resolution:** The scheduler query uses an exact match on `booking_status = 'pending_confirmation'`. Old-style `'Confirmed'` bookings (title case) will not match and will not enter the follow-up flow. However, for data hygiene and to prevent confusion, the migration query should run immediately after DDL.

### 3.3 New Table: `scheduler_runs` (Observability)

Create a new table in **shared Supabase** (not per-client) to log scheduler run metrics:

```sql
CREATE TABLE scheduler_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  clients_processed INTEGER NOT NULL,
  bookings_t2h INTEGER NOT NULL DEFAULT 0,
  bookings_t24h INTEGER NOT NULL DEFAULT 0,
  bookings_abandoned INTEGER NOT NULL DEFAULT 0,
  messages_sent_success INTEGER NOT NULL DEFAULT 0,
  messages_sent_failed INTEGER NOT NULL DEFAULT 0,
  runtime_ms INTEGER NOT NULL,
  errors TEXT  -- JSON array of error summaries, if any
);

CREATE INDEX idx_scheduler_runs_timestamp ON scheduler_runs(run_timestamp DESC);
```

**Purpose:** Operational monitoring. Each scheduler run inserts one row with aggregate metrics across all clients. Allows answering questions like:
- Is the scheduler running?
- How many bookings are being processed?
- What's the Meta API failure rate?
- What's the average scheduler runtime?

**Logged by:** `run_followup_scheduler_job()` at the end of each run (success or failure).

---

## 4. Tool Surface Changes (BREAKING)

### 4.1 Modified Tool: `write_booking`

**Current behavior (before this feature):**
```python
async def write_booking(...) -> dict:
    # 1. Create Google Calendar event
    calendar_event_id = await create_booking_event(...)
    # 2. INSERT into bookings with booking_status = 'Confirmed'
    await db.table("bookings").insert({..., "booking_status": "Confirmed"}).execute()
    return {
        "booking_id": booking_id,
        "status": "Confirmed",
        "message": "Booking confirmed! Reference: {booking_id}",
        ...
    }
```

**New behavior (after this feature):**
```python
async def write_booking(...) -> dict:
    """
    Create a pending booking: INSERT into DB with status 'pending_confirmation'.
    NO Google Calendar event is created yet.
    
    The agent must send the booking summary to the customer and wait for their
    explicit confirmation before calling confirm_booking.
    
    Returns:
        dict: {
            booking_id: str,
            status: 'pending_confirmation',
            slot_date: str,
            slot_window: str,
            service_type: str,
            message: str  -- Updated to reflect pending state
        }
    """
    booking_id = _generate_booking_id(slot_date)
    _created_at = datetime.now(timezone.utc).isoformat()
    
    booking_row = {
        "booking_id": booking_id,
        "phone_number": phone_number,
        "service_type": service_type,
        "unit_count": unit_count,
        "address": address,
        "postal_code": postal_code,
        "slot_date": slot_date,
        "slot_window": slot_window,
        "booking_status": "pending_confirmation",  # NEW STATUS
        "created_at": _created_at,
    }
    if aircon_brand:
        booking_row["aircon_brand"] = aircon_brand
    if notes:
        booking_row["notes"] = notes
    
    await db.table("bookings").insert(booking_row).execute()
    
    # NO calendar event creation
    # NO customer name update (deferred to confirm_booking)
    
    return {
        "booking_id": booking_id,
        "status": "pending_confirmation",
        "slot_date": slot_date,
        "slot_window": slot_window,
        "service_type": service_type,
        "message": (
            f"Booking details recorded (Reference: {booking_id}). "
            "Please send the booking summary to the customer and ask them to confirm. "
            "Once they confirm, call confirm_booking with this booking_id."
        ),
    }
```

**What changes:**
1. **No calendar event creation** — calendar write moves to `confirm_booking`
2. **Status is `'pending_confirmation'`** instead of `'Confirmed'`
3. **Return message updated** — instructs the agent to send summary and wait for confirmation
4. **No customer name update** — moved to `confirm_booking` (customer record only updated after successful confirmation)

**Impact on agent behavior:**  
The agent receives `booking_id` in the tool result and must hold it in context until the customer confirms. The system prompt (§4.3) is updated to enforce this flow.

### 4.2 New Tool: `confirm_booking`

**File:** `engine/core/tools/confirm_booking_tool.py` (NEW)

**Function signature:**
```python
async def confirm_booking(
    db,
    client_config,
    phone_number: str,
    booking_id: str,
) -> dict:
    """
    Finalize a pending booking: check calendar for slot conflict, create event,
    update status to 'confirmed'.
    
    This tool is called by the agent AFTER the customer has replied to the booking
    summary with affirmative intent (detected by the LLM).
    
    Args:
        db:            Supabase async client (injected).
        client_config: ClientConfig with calendar credentials (injected).
        phone_number:  Customer phone number (injected — used for validation).
        booking_id:    Booking ID returned by write_booking (supplied by Claude).
    
    Returns:
        dict: {
            booking_id: str,
            status: 'confirmed',
            calendar_event_id: str,
            message: str  -- Success message with booking_id for agent to relay
        }
        
        OR (on slot conflict):
        
        dict: {
            booking_id: str,
            status: 'conflict',
            error: 'slot_no_longer_available',
            message: str  -- Agent should offer alternative slots
        }
        
        OR (on other errors):
        
        dict: {
            booking_id: str,
            status: 'error',
            error: str,
            message: str  -- Agent should escalate to human
        }
    
    Raises:
        Exception on critical DB or calendar API failures (caller catches and
        returns error dict to Claude).
    """
```

**Implementation logic:**

1. **Fetch booking row from DB:**
   ```python
   result = await db.table("bookings").select("*").eq("booking_id", booking_id).execute()
   if not result.data:
       return {"status": "error", "error": "booking_not_found", ...}
   booking = result.data[0]
   ```

2. **Validation checks:**
   ```python
   # Must be pending_confirmation
   if booking["booking_status"] != "pending_confirmation":
       return {"status": "error", "error": "booking_already_confirmed_or_cancelled", ...}
   
   # Must match phone_number (prevent cross-customer confirmation attacks)
   if booking["phone_number"] != phone_number:
       return {"status": "error", "error": "booking_phone_mismatch", ...}
   ```

3. **Calendar slot conflict check:**
   ```python
   from engine.integrations.google_calendar import check_slot_availability
   
   availability = await check_slot_availability(
       google_calendar_creds=client_config.google_calendar_creds,
       calendar_id=client_config.google_calendar_id,
       slot_date=booking["slot_date"],
       timezone="Asia/Singapore",
   )
   
   slot_key = "am_available" if booking["slot_window"] == "AM" else "pm_available"
   if not availability[slot_key]:
       # Slot is now taken (race condition or another customer confirmed first)
       return {
           "booking_id": booking_id,
           "status": "conflict",
           "error": "slot_no_longer_available",
           "message": (
               f"I'm sorry, the {booking['slot_window']} slot on {booking['slot_date']} "
               "is no longer available. Another customer booked it just moments ago. "
               "Let me check other available slots for you."
           ),
       }
   ```

4. **Create calendar event:**
   ```python
   from engine.integrations.google_calendar import create_booking_event
   
   calendar_event_id = await create_booking_event(
       google_calendar_creds=client_config.google_calendar_creds,
       calendar_id=client_config.google_calendar_id,
       booking_id=booking_id,
       customer_name=booking.get("customer_name", phone_number),
       phone_number=phone_number,
       service_type=booking["service_type"],
       unit_count=booking["unit_count"],
       address=booking["address"],
       postal_code=booking["postal_code"],
       slot_date=booking["slot_date"],
       slot_window=booking["slot_window"],
       aircon_brand=booking.get("aircon_brand"),
       notes=booking.get("notes"),
   )
   ```

5. **Update booking status + customer name:**
   ```python
   await db.table("bookings").update({
       "booking_status": "confirmed",
       "calendar_event_id": calendar_event_id,
   }).eq("booking_id", booking_id).execute()
   
   # Update customer name (same as old write_booking behavior)
   await db.table("customers").update({
       "customer_name": booking.get("customer_name", phone_number),
   }).eq("phone_number", phone_number).execute()
   ```

6. **Return success:**
   ```python
   return {
       "booking_id": booking_id,
       "status": "confirmed",
       "calendar_event_id": calendar_event_id,
       "message": (
           f"Your booking is confirmed! 🎉\n\n"
           f"Reference: {booking_id}\n"
           f"Date: {booking['slot_date']} ({booking['slot_window']} slot)\n"
           f"Service: {booking['service_type']} ({booking['unit_count']} units)\n\n"
           "We'll send you a reminder before the appointment. "
           "Looking forward to serving you!"
       ),
   }
   ```

**Error handling:**
- Calendar API failure: alert human agent (same pattern as `write_booking`), return error dict to agent
- DB update failure after calendar event created: alert human (booking is in inconsistent state — calendar event exists but DB still says `'pending_confirmation'`)

### 4.3 Tool Definition Updates

**File:** `engine/core/tools/definitions.py` (MODIFIED)

Add the new `confirm_booking` tool definition to `TOOL_DEFINITIONS` list:

```python
{
    "name": "confirm_booking",
    "description": (
        "Finalize a pending booking after the customer has confirmed. This tool checks "
        "for calendar slot conflicts, creates the Google Calendar event, and updates "
        "the booking status to 'confirmed'. Only call this AFTER the customer has "
        "replied to your booking summary with affirmative intent (e.g., 'yes', 'confirm', "
        "'ok', 'sounds good'). You must have the booking_id from the write_booking result."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "booking_id": {
                "type": "string",
                "description": (
                    "The booking reference ID returned by write_booking. Format: HA-YYYYMMDD-XXXX."
                ),
            },
        },
        "required": ["booking_id"],
    },
},
```

**Update `write_booking` tool definition description:**

OLD:
```
"Confirm and write a booking. Creates a Google Calendar event and records the booking in the database."
```

NEW:
```
"Record a pending booking in the database. This does NOT create a calendar event or confirm the booking. After calling this, you must send the booking summary to the customer and wait for their explicit confirmation. Once they confirm, call confirm_booking."
```

### 4.4 Tool Dispatch Update

**File:** `engine/core/tools/__init__.py` (MODIFIED)

Add `confirm_booking` to the `build_tool_dispatch()` closure:

```python
from engine.core.tools.confirm_booking_tool import confirm_booking

def build_tool_dispatch(db, client_config, phone_number: str) -> dict:
    # ... existing closures ...
    
    async def _confirm_booking(booking_id: str) -> dict:
        return await confirm_booking(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            booking_id=booking_id,
        )
    
    return {
        "check_calendar_availability": _check_calendar_availability,
        "write_booking": _write_booking,
        "get_customer_bookings": _get_customer_bookings,
        "escalate_to_human": _escalate_to_human,
        "confirm_booking": _confirm_booking,  # NEW
    }
```

### 4.5 System Prompt Update (CRITICAL)

**File:** `engine/core/context_builder.py` (MODIFIED)

Replace the `**BOOKING RULES (NON-NEGOTIABLE):**` and `**MANDATORY DECISION RULE — BOOKING STEP 4:**` sections in `_IDENTITY_BLOCK` with the following:

**NEW BOOKING RULES:**
```python
_IDENTITY_BLOCK = """\
You are a helpful AI assistant for HeyAircon, a professional aircon servicing \
company in Singapore. Your role is to answer customer questions about our \
services, pricing, and availability, and to help customers book appointments.

**CRITICAL SAFETY RULES (NON-NEGOTIABLE):**
[...unchanged...]

**PROMPT INJECTION DEFENCE:**
[...unchanged...]

**BOOKING RULES (NON-NEGOTIABLE):**

1. NEVER trust conversation history for availability or booking status. Always use tools.
2. To check if a slot is available: call check_calendar_availability. Never answer from memory.
3. To check a customer's bookings: call get_customer_bookings. Never answer from memory.
4. The booking flow has TWO PHASES — you must follow this sequence exactly:
   
   **PHASE 1: Record Pending Booking**
   - After collecting all required details (service, units, address, postal code, date, slot),
     call write_booking.
   - write_booking returns a booking_id and status='pending_confirmation'.
   - The booking is NOT confirmed yet — NO calendar event has been created.
   - You MUST remember the booking_id for Phase 2.
   
   **PHASE 2: Customer Confirmation**
   - Send the booking summary to the customer and ask them to confirm.
   - Example: "Here's your booking summary: [details]. Is this correct? Please confirm so I can lock in your slot!"
   - WAIT for the customer's reply.
   - When the customer replies with affirmative intent (any agreement: "yes", "ok", "confirm", 
     "go ahead", "that works", "sounds good", "👍"), your ONLY valid next action is to call 
     confirm_booking with the booking_id from Phase 1.
   - confirm_booking will check for slot conflicts and create the calendar event.
   - If confirm_booking returns status='conflict', the slot is no longer available. Offer 
     alternative slots using check_calendar_availability.
   - If confirm_booking returns status='confirmed', tell the customer their booking is confirmed 
     and give them the booking reference.

5. NEVER say words like "confirmed", "booked", "all set", or "locked in" until confirm_booking 
   returns status='confirmed'. If you say these words before calling confirm_booking, you have 
   made an error.

6. If write_booking or confirm_booking fails: tell the customer "I'm sorry, I wasn't able to 
   complete the booking due to a technical issue. Our team has been notified and will follow up 
   with you shortly."

7. The two-tool sequence is MANDATORY for all new bookings:
   - collect details → call write_booking → send summary → wait for customer → detect confirmation 
     → call confirm_booking → tell customer "confirmed" with booking_id

**BOOKING RETRIEVAL RULES:**
[...unchanged...]

**YOUR SERVICES AND KNOWLEDGE:**
"""
```

**What changed:**
- Old rule: "call write_booking first" → booking immediately confirmed
- New rule: Two-phase flow (write_booking → pending, confirm_booking → confirmed)
- Explicit instruction: "WAIT for the customer's reply" — prevents the agent from calling `confirm_booking` before the customer confirms
- Clear trigger: "affirmative intent" examples (yes, ok, confirm, etc.) → call `confirm_booking`
- Slot conflict handling: if `confirm_booking` returns `status='conflict'`, offer alternatives

---

## 5. File Changes Table

| File | Change Type | What Changes |
|------|-------------|--------------|
| **`engine/core/followup_scheduler.py`** | **NEW** | Background scheduler job function. Queries all active clients, loads per-client config, runs 3 stage queries (T+2h, T+24h, T+48h), sends WhatsApp messages, updates DB, logs metrics to `scheduler_runs` table. |
| **`engine/core/tools/booking_tools.py`** | **MODIFIED** | `write_booking()`: Remove calendar event creation, set `booking_status = 'pending_confirmation'`, return updated message instructing agent to wait for customer confirmation. Remove customer name update (moved to `confirm_booking`). |
| **`engine/core/tools/confirm_booking_tool.py`** | **NEW** | New tool function: fetch pending booking, validate phone match, check calendar for slot conflict, create calendar event if no conflict, update `booking_status = 'confirmed'`, update customer name. Return conflict error if slot taken. |
| **`engine/core/tools/definitions.py`** | **MODIFIED** | Add `confirm_booking` tool definition dict. Update `write_booking` description to reflect pending-only behavior. |
| **`engine/core/tools/__init__.py`** | **MODIFIED** | Add `confirm_booking` import. Add `_confirm_booking` closure to `build_tool_dispatch()` return dict. |
| **`engine/core/context_builder.py`** | **MODIFIED** | Replace `**BOOKING RULES**` and `**MANDATORY DECISION RULE**` sections in `_IDENTITY_BLOCK` with new two-phase booking flow instructions (see §4.5). |
| **`engine/core/message_handler.py`** | **MODIFIED (low-impact)** | Add opt-out keyword detection pre-processing step before agent invocation (check message text for "stop", "unsubscribe", etc.; if match: update `followup_stage = 'opted_out'`, send confirmation reply, stop). No changes to main pipeline. |
| **`engine/main.py`** | **MODIFIED** | Add scheduler initialization on `@app.on_event("startup")`: create `AsyncIOScheduler`, add `run_followup_scheduler_job` with 60-min interval, start scheduler. Add `@app.on_event("shutdown")` to stop scheduler gracefully. |
| **`engine/api/webhook.py`** | **NO CHANGE** | Webhook handling is unchanged — still receives inbound, immediately returns 200, dispatches to `handle_inbound_message()`. |
| **`engine/integrations/meta_whatsapp.py`** | **NO CHANGE** | `send_message()` is called by the scheduler with the same API as the agent uses. No modifications needed. |
| **`engine/integrations/supabase_client.py`** | **NO CHANGE** | DB connection logic unchanged — scheduler uses the same `get_client_db()` function as the agent. |
| **`engine/config/settings.py`** | **MODIFIED (optional)** | Add optional env var `FOLLOWUP_SCHEDULER_INTERVAL_MINUTES` (integer, default 60). Used in `main.py` scheduler init. |
| **Supabase (per-client)** | **DDL** | Run DDL: `ALTER TABLE bookings ADD COLUMN last_followup_sent_at TIMESTAMPTZ, ADD COLUMN followup_stage TEXT, ADD COLUMN abandoned_at TIMESTAMPTZ;` + create indexes (see §3.1). Run migration query for `'Confirmed'` → `'confirmed'` (see §3.2). |
| **Supabase (shared)** | **DDL** | Create `scheduler_runs` table (see §3.3). |
| **Per-client `config` table** | **DATA** | Insert 8 new config rows (see requirements doc "Client-Configurable Variables" section): `followup_t1_hours`, `followup_t2_hours`, `followup_abandon_hours`, `followup_enabled`, `followup_scheduler_interval_minutes`, `followup_t1_message_template`, `followup_t2_message_template`, `followup_optout_reply`. |

---

## 6. Backward Compatibility and Migration Risk

### 6.1 Breaking Changes Summary

**This feature introduces a BREAKING CHANGE to the agent's tool surface:**

1. **`write_booking` behavior change:**
   - **Old:** Creates calendar event + DB row with `booking_status = 'Confirmed'` atomically
   - **New:** Creates DB row with `booking_status = 'pending_confirmation'` only; no calendar event

2. **New tool `confirm_booking`:**
   - Required to finalize a booking (calendar event + status update to `'confirmed'`)
   - Agent must call this after detecting customer confirmation intent

3. **System prompt change:**
   - Old prompt: "call write_booking first" (one-step flow)
   - New prompt: "call write_booking → send summary → wait for customer → call confirm_booking" (two-step flow)

**Impact:** Existing bookings in `'Confirmed'` status are safe (they already have calendar events). New bookings after deployment will follow the two-step flow. **In-flight bookings** (customer is mid-conversation when deployment happens) will be handled gracefully by the agent — the agent will adapt to the current conversation state using the new tools.

### 6.2 Handling In-Flight Bookings

**Scenario:** A customer is mid-conversation with the agent when the new code is deployed. The agent has just collected booking details but has not yet called `write_booking` (or has called it but customer hasn't confirmed).

**Mitigation:**
1. **Conversation history is preserved** — the agent sees the full conversation in `interactions_log` and can determine the current state
2. **Tools are idempotent** — `write_booking` can be called after deployment and will use the new behavior
3. **New system prompt takes effect immediately** — the agent will follow the two-phase flow for all new tool invocations
4. **Old `'Confirmed'` bookings in DB** — the agent never tries to call `confirm_booking` on an already-confirmed booking (the agent only calls `confirm_booking` when it has a `booking_id` from the current conversation turn's `write_booking` result)

**Worst-case edge case:** Customer confirms immediately before deployment, agent calls old `write_booking` (calendar event created), deployment happens mid-response, agent reply is lost. Customer sees no confirmation message. **Resolution:** Customer will send a follow-up message ("did my booking go through?"), agent calls `get_customer_bookings`, sees the `'confirmed'` booking (or `'Confirmed'` if migration query hasn't run yet), and tells the customer it's confirmed.

### 6.3 `confirm_booking` on Old-Style `'Confirmed'` Bookings

**Scenario:** Agent receives a `booking_id` for an old-style `'Confirmed'` booking (title case, from before the feature launched) and tries to call `confirm_booking`.

**Mitigation:** `confirm_booking` validation checks `booking_status != 'pending_confirmation'` and returns an error:
```python
if booking["booking_status"] != "pending_confirmation":
    return {
        "status": "error",
        "error": "booking_already_confirmed_or_cancelled",
        "message": "This booking is already confirmed or has been cancelled. No further action needed.",
    }
```

The agent sees this error message and tells the customer the booking is already confirmed. **No crash, no data corruption.**

### 6.4 Recommended Deployment Sequence

**CRITICAL:** This is a coordinated multi-step deployment. Follow this sequence to minimize risk:

| Step | Action | When | Purpose |
|------|--------|------|---------|
| **1. DDL — Bookings Table** | Run `ALTER TABLE bookings ADD COLUMN ...` (3 new columns) + create indexes | **Before code deploy** | Schema must exist before scheduler runs |
| **2. DDL — Scheduler Runs Table** | Create `scheduler_runs` table in shared Supabase | **Before code deploy** | Scheduler logging target must exist |
| **3. Data Migration** | Run `UPDATE bookings SET booking_status = 'confirmed' WHERE booking_status = 'Confirmed'` | **Immediately after Step 1** | Normalize old bookings to new enum value |
| **4. Config Rows** | Insert 8 new config rows into per-client `config` table (follow-up settings) | **Before code deploy** | Scheduler loads these at runtime; missing rows = crash |
| **5. Code Deploy** | Deploy new engine code to Railway (includes scheduler + tool changes + prompt update) | **After Steps 1–4 complete** | All dependencies are in place |
| **6. Scheduler Start Verification** | Check Railway logs for "Proactive follow-up scheduler started" | **Immediately after deploy** | Confirm scheduler initialized |
| **7. First Scheduler Run** | Wait 60 minutes, check Railway logs for scheduler job execution | **1 hour after deploy** | Confirm scheduler is querying and processing bookings |
| **8. Monitor Incidents Table** | Query shared Supabase `api_incidents` for any scheduler-related errors | **24 hours after deploy** | Catch any runtime issues early |

**Why DDL-first?** The scheduler queries for columns that don't exist yet → crash. The code must be deployed AFTER the schema changes are live.

**Why config rows before deploy?** The scheduler loads `followup_enabled`, `followup_t1_hours`, etc. from the `config` table. Missing keys → KeyError → crash.

**Rollback plan (if scheduler fails):**
1. Set `followup_enabled = false` in per-client `config` table → scheduler skips all clients
2. Investigate errors in Railway logs + shared `api_incidents` table
3. Fix code, redeploy
4. Set `followup_enabled = true` to resume

**Rollback plan (if agent breaks):**
1. Redeploy the previous engine version (old `write_booking` behavior)
2. Agent will use one-step flow again
3. Follow-up scheduler will continue to run (safe — it queries `booking_status = 'pending_confirmation'` which won't match new `'Confirmed'` bookings from the rolled-back agent)
4. Fix forward, redeploy

---

## 7. Open Questions — Resolved

### OQ-07: Timestamp Source for T+2h Calculation

**Question:** Should the scheduler use `bookings.created_at` or the timestamp of the confirmation message from `interactions_log` to calculate T+2h?

**Decision:** Use the **confirmation message timestamp** from `interactions_log`.

**Rationale:**
- The confirmation message is the customer-facing event that triggers the follow-up sequence.
- `created_at` precedes the confirmation message by seconds (DB INSERT happens before agent reply).
- The difference is negligible (<1s typically), but using the confirmation timestamp is semantically correct.

**Implementation:**
```sql
-- T+2h query uses this subquery to get confirmation timestamp:
SELECT MAX(timestamp) FROM interactions_log
WHERE phone_number = bookings.phone_number
  AND direction = 'outbound'
  AND il.timestamp > b.created_at  -- Any reply after booking row created
```

**Note:** Silence is determined by `bookings.created_at` — no content matching or new columns required.

**Fallback:** If no confirmation message is found (e.g., old bookings from before this feature), use `bookings.created_at` as the reference timestamp. Log a warning.

### OQ-08: Existing `'Confirmed'` Bookings in Scheduler Query

**Question:** How to prevent the scheduler from accidentally triggering follow-ups for old-style `'Confirmed'` (title case) bookings that were created before this feature launched?

**Decision:** The scheduler query uses an **exact match** on `booking_status = 'pending_confirmation'`.

**Implementation:**
```sql
WHERE booking_status = 'pending_confirmation'  -- Exact match, case-sensitive
```

Old-style `'Confirmed'` (title case) bookings will not match this query and will not enter the follow-up flow.

**Data hygiene:** Run the migration query (§3.2) immediately after DDL to normalize all existing `'Confirmed'` → `'confirmed'`. This prevents confusion and ensures data consistency.

### OQ-09: `followup_scheduler_interval_minutes` — Per-Client or Platform-Wide?

**Question:** Should the scheduler interval be configurable per-client or a single platform-wide setting?

**Decision:** **Platform-wide** for Phase 1 (env var `FOLLOWUP_SCHEDULER_INTERVAL_MINUTES`), with an optional per-client override path for Phase 2.

**Rationale:**
1. **Scheduler runs once for all clients** — the interval is a property of the scheduler job, not a property of a client's follow-up logic
2. **Infrastructure simplicity** — one scheduler, one interval, one cron-like trigger
3. **Phase 1 use case** — all clients have the same urgency profile (post-booking follow-up for service SMEs); no need for per-client intervals yet
4. **Per-client thresholds are sufficient** — each client can set their own `followup_t1_hours`, `followup_t2_hours`, `followup_abandon_hours` in the `config` table; the scheduler interval determines *how often* the scheduler checks, not *when* follow-ups are triggered (timing is controlled by the threshold values)

**Phase 2 path (if needed):**
- Add `followup_scheduler_interval_minutes` to per-client `config` table
- Scheduler loads this value for each client and uses it to decide whether to process that client on this run (e.g., "last processed this client 45 minutes ago, their interval is 60 minutes, skip for now")
- Requires scheduler to track per-client last-run timestamps (new state in shared DB)

**For now:** Single env var, all clients checked every N minutes (default 60).

---

## 8. Implementation Risks and Constraints

### 8.1 High-Risk Areas

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Tool surface breaking change** | HIGH | Comprehensive system prompt update (§4.5) + tool definition changes (§4.3) deployed atomically. Test with eval suite before production. |
| **In-flight booking edge case** | MEDIUM | Agent conversation history is stateful; new prompt takes effect immediately. Worst case: customer sends follow-up, agent handles gracefully. |
| **Scheduler clock drift** | LOW | Max 2h 59m delay for T+2h is acceptable for use case (§2.3). Monitor via `scheduler_runs` table. If customer feedback indicates timing issues, reduce interval to 15 min. |
| **Schema migration timing** | HIGH | DDL-first deployment (§6.4) is MANDATORY. If code deploys before DDL, scheduler crashes. Test deployment sequence in staging first. |
| **Opt-out keyword false positives** | MEDIUM | Simple keyword check may match customer phrases like "stop asking me" in a different context. Log all opt-outs to `interactions_log` for review. If false positives detected, refine keyword list or move to LLM-based intent detection. |
| **Silence detection reference point** | LOW | Silence is detected via `bookings.created_at`. If `write_booking` is called but the summary message fails to send, `created_at` still advances — scheduler may send a follow-up before the customer ever saw the original summary. Mitigation: the follow-up message is self-contained (includes booking details), so the customer can still confirm from it. |
| **Meta API rate limiting** | LOW | Scheduler sends one message per eligible booking per stage. At 100 bookings/day (aggressive), that's ~4 messages/hour (T+2h stage). Well below Meta's 1000 msg/day tier limit. Monitor via `scheduler_runs.messages_sent_failed`. |
| **Double-booking during `pending_confirmation` window** | MEDIUM | No slot reservation at `pending_confirmation` (founder decision). Two customers can both be `pending_confirmation` for the same slot. First to call `confirm_booking` wins; second gets conflict error. Agent offers alternatives. Monitor conflict rate via `api_incidents`. |

### 8.2 Founder Input Required Before Test Planning

1. **Scheduler interval:** Confirm 60 minutes is acceptable for Phase 1, or specify a tighter interval (15 min = 4x overhead).

2. **Opt-out reply message:** Approve the opt-out confirmation message text (see requirements doc "Opt-Out Handling" section) or provide revisions. This message is stored in per-client `config` table as `followup_optout_reply`.

3. **Follow-up message templates:** Approve T+2h and T+24h message copy (see requirements doc "Message Copy" section) or provide revisions. These are stored in per-client `config` table as `followup_t1_message_template` and `followup_t2_message_template`.

4. **No slot reservation at `pending_confirmation`:** Confirm this is acceptable (double-booking risk = conflict error at `confirm_booking` time). If not acceptable, the architecture must change to reserve slots at `write_booking` time (adds complexity: timeout-based slot release, reservation table, etc.).

5. **Phase 1 confirmation message heuristic:** Confirm text substring match (`message_text LIKE '%booking summary%'`) is acceptable for silence detection, or mandate `message_category` column implementation in Phase 1 (adds migration cost).

---

## 9. Next Steps

1. **Founder reviews this architecture doc** and provides input on the 5 questions in §8.2.

2. **Software-architect updates this doc** based on founder feedback (if any).

3. **Founder approves architecture** → handoff to `@sdet-engineer` for test planning.

4. **SDET reads this doc** + requirements doc + current engine code, writes test plan in `docs/test-plan/proactive_followup.md`.

5. **SDET creates worktree** and dispatches first slice to `@software-engineer` (recommend starting with schema changes + `confirm_booking` tool as Slice 1).

---

## Appendix A: Full Stage Query Examples

### T+2h Query (First Follow-up)

```sql
SELECT b.* FROM bookings b
JOIN customers c ON b.phone_number = c.phone_number
WHERE b.booking_status = 'pending_confirmation'
  AND c.escalation_flag = FALSE
  AND b.followup_stage IS NULL
  AND b.created_at <= NOW() - INTERVAL '2 hours'
  AND NOT EXISTS (
    SELECT 1 FROM interactions_log il
    WHERE il.phone_number = b.phone_number
      AND il.direction = 'inbound'
      AND il.timestamp > (
        SELECT MAX(il2.timestamp) FROM interactions_log il2
        WHERE il2.phone_number = b.phone_number
          AND il2.direction = 'outbound'
          AND il2.message_text LIKE '%booking summary%'
      )
  )
ORDER BY b.created_at ASC;
```

### T+24h Query (Second Follow-up)

```sql
SELECT b.* FROM bookings b
JOIN customers c ON b.phone_number = c.phone_number
WHERE b.booking_status = 'pending_confirmation'
  AND c.escalation_flag = FALSE
  AND b.followup_stage = '2h_sent'
  AND b.last_followup_sent_at <= NOW() - INTERVAL '22 hours'
  AND NOT EXISTS (
    SELECT 1 FROM interactions_log il
    WHERE il.phone_number = b.phone_number
      AND il.direction = 'inbound'
      AND il.timestamp > b.last_followup_sent_at
  )
ORDER BY b.last_followup_sent_at ASC;
```

### T+48h Query (Abandon Mark)

```sql
SELECT b.* FROM bookings b
JOIN customers c ON b.phone_number = c.phone_number
WHERE b.booking_status = 'pending_confirmation'
  AND c.escalation_flag = FALSE
  AND b.followup_stage = '24h_sent'
  AND b.last_followup_sent_at <= NOW() - INTERVAL '24 hours'
  AND NOT EXISTS (
    SELECT 1 FROM interactions_log il
    WHERE il.phone_number = b.phone_number
      AND il.direction = 'inbound'
      AND il.timestamp > b.last_followup_sent_at
  )
ORDER BY b.last_followup_sent_at ASC;
```

---

**END OF ARCHITECTURE DOCUMENT**
