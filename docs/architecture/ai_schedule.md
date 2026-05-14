# AI Schedule & Business Hours — Architecture Specification

> **Architecture Decision Record & Implementation Specification**  
> Author: @software-architect  
> Date: 2026-05-13  
> Status: Approved for implementation

---

## Table of Contents

1. [Summary](#summary)
2. [Design Decisions](#design-decisions)
3. [Database Changes](#database-changes)
4. [Code Changes](#code-changes)
5. [Pipeline Integration](#pipeline-integration)
6. [Cross-Feature Dependencies](#cross-feature-dependencies)
7. [Open Questions Resolved](#open-questions-resolved)
8. [Implementation Notes for sdet-engineer](#implementation-notes-for-sdet-engineer)

---

## Summary

**What this feature does:**  
Adds two independently configurable time windows to control AI agent behavior, both stored per-client in Supabase and editable without code changes:

1. **AI Operational Hours** — the window when the AI agent is active. Outside this window, the engine sends an auto-reply and does NOT invoke the agent.
2. **Business Operational Hours** — used exclusively for escalation message context. When the AI escalates outside business hours, the customer is informed that a human will follow up during business hours.

**Key design principles:**
- Both windows are **independent** — one does not imply the other
- Both are **nullable** — NULL = 24/7 active (AI operational) or no business hours context (business hours)
- Timezone-aware — all times interpreted in the client's configured timezone
- Zero-touch configuration — changes in Supabase Studio take effect within 5 minutes (cache TTL)

**HeyAircon default configuration:**
- AI operational: 18:00–09:00 SGT (after-hours only, overnight window)
- Business hours: 09:00–18:00 SGT (human agents available)
- Timezone: `Asia/Singapore`

---

## Design Decisions

### Decision 1: Two Independent Time Windows

**Choice:** Create two separate pairs of columns (`ai_active_start_time` / `ai_active_end_time` vs. `business_start_time` / `business_end_time`) rather than one unified "schedule" structure.

**Rationale:**
- **Use cases are orthogonal:**
  - AI operational hours → controls message routing (schedule gate in pipeline)
  - Business hours → controls customer-facing messaging only (no routing impact)
- **Flexibility:** Client may want AI active 24/7 (both AI columns NULL) while still having business hours context for escalations (business columns populated)
- **Simplicity:** Two nullable pairs are easier to reason about than a complex JSON schedule structure with multiple purposes

**Alternative rejected:** Store a JSON schedule like `{"ai_hours": {"start": "18:00", "end": "09:00"}, "business_hours": {...}}`. Rejected because it makes Supabase Studio editing harder (manual JSON editing is error-prone) and adds unnecessary parsing complexity.

---

### Decision 2: TIME Type (Not TIMESTAMPTZ)

**Choice:** Use Postgres `TIME` type (24-hour HH:MM:SS) rather than `TIMESTAMPTZ` or storing hours/minutes as integers.

**Rationale:**
- **Semantic clarity:** `TIME` represents "time of day" without a date — exactly what we need
- **Timezone independence:** Store local time (e.g., `18:00:00`), interpret via `timezone` column at runtime
- **Validation:** Postgres enforces HH:MM:SS format automatically — rejects invalid inputs like `25:00:00`
- **Simplicity:** No arithmetic needed to convert integers to time — just parse `TIME` and compare to current local time

**Alternative rejected:** Store `start_hour INTEGER` and `start_minute INTEGER`. Rejected because it splits one concept (time) into two columns and requires manual validation (hour 0-23, minute 0-59).

---

### Decision 3: Single Timezone Column for Both Windows

**Choice:** One `timezone` column (IANA string like `Asia/Singapore`) applies to both AI operational hours AND business hours.

**Rationale:**
- **Operational reality:** A business operates in one timezone. AI hours and business hours are both expressions of that same timezone.
- **Simplicity:** Avoids the edge case where AI hours use one timezone and business hours use another (would require complex time conversion logic)
- **Auditability:** All times for a client are interpreted the same way — reduces cognitive load when debugging

**Default value:** `UTC` (fail-safe). If a client does not set `timezone`, all times are interpreted as UTC. This prevents silent failures — the schedule will be wrong (off by N hours) but the system will not crash.

**Validation:** If `timezone` is invalid (not in IANA database), log an error and default to UTC. Do NOT crash the pipeline.

---

### Decision 4: Overnight Window Support (Start > End)

**Choice:** When `ai_active_start_time > ai_active_end_time` (e.g., 18:00 → 09:00), the window **spans midnight**.

**Check logic:**
```python
if start_time <= end_time:
    # Daytime window (e.g., 09:00 → 18:00)
    active = start_time <= current_time < end_time
else:
    # Overnight window (e.g., 18:00 → 09:00)
    active = current_time >= start_time or current_time < end_time
```

**Rationale:**
- HeyAircon's pilot use case is after-hours AI (18:00–09:00) — this is the primary pattern
- Explicit support for overnight windows avoids the need for two separate rows (18:00–23:59 + 00:00–09:00) which would complicate configuration

**Edge case:** If `start_time == end_time` (e.g., both 09:00), interpret as **no window** (AI inactive 24/7). Log a warning.

---

### Decision 5: Cache AI Operational Hours in ClientConfig

**Choice:** Load `ai_active_start_time`, `ai_active_end_time`, `business_start_time`, `business_end_time`, and `timezone` into the in-memory `ClientConfig` object (5-minute TTL).

**Rationale:**
- **Performance:** Schedule check happens on EVERY inbound message. Cannot afford a Supabase query per message.
- **Consistency:** All client config is already cached (meta tokens, human_agent_number, etc.) — schedule is just more config
- **Simplicity:** No additional caching layer needed — use existing `load_client_config()` mechanism

**Cache invalidation:** Changes in Supabase Studio take effect within 5 minutes (next cache refresh). This is acceptable — schedule changes are infrequent (maybe once at pilot start, then never).

**Implementation:** Add 5 new fields to the `ClientConfig` dataclass in `engine/config/client_config.py`. Load them in `load_client_config()` from the shared `clients` table.

---

### Decision 6: Out-of-Hours Routing — Silent Queue (Option D)

**Choice:** When a message arrives outside AI operational hours:
1. Send auto-reply to customer ("Thanks for reaching out! Our team operates [business hours]. A team member will respond shortly.")
2. Log inbound + outbound to `interactions_log`
3. Do NOT forward to human agent — assume human monitors WhatsApp Business inbox during business hours
4. Stop pipeline (do NOT invoke agent)

**Rationale:**
- **Simplicity:** No additional routing logic, no Telegram integration, no WhatsApp forwarding spam
- **Existing workflow:** HeyAircon already monitors WhatsApp Business inbox during business hours — this is their current workflow
- **Fail-safe:** If human misses a message, the customer still received an auto-reply setting expectations (not left hanging)

**Future enhancement (Phase 2):** If HeyAircon requests active routing, implement forwarding to `human_agent_number` with a batched alert (1 notification per 5 messages to reduce noise).

**Open Question OQ-AS-01 resolved:** Start with Option D (silent queue). Collect feedback from HeyAircon during pilot. If they report missing messages, upgrade to Option A (forward to human_agent_number).

---

### Decision 7: Business Hours in Auto-Reply Message

**Choice:** Auto-reply message dynamically substitutes business hours from config.

**Format logic:**
```python
if business_start_time and business_end_time:
    hours_text = f"Our team operates {format_time(business_start_time)}–{format_time(business_end_time)}."
else:
    hours_text = "Our team will respond shortly."
```

**Example outputs:**
- Business hours set (09:00–18:00): "Thanks for reaching out! Our team operates 9am–6pm. A team member will respond shortly."
- Business hours NULL: "Thanks for reaching out! Our team will respond shortly."

**Rationale:** If business hours are not configured, fall back to a generic message. Do not crash or send a broken template.

---

## Database Changes

### Migration 012: Add Schedule Columns to `clients` Table

**Target database:** Shared Flow AI Supabase (`nayhqstuupdsqpltseof` — contains the shared `clients` table)

**Migration file:** `supabase/migrations/012_ai_schedule.sql`

```sql
-- Migration 012: AI Schedule & Business Hours
-- Adds configurable time windows for AI operational hours and business hours context.
-- Both are independently nullable — NULL = 24/7 active (AI) or no business hours context.

-- ── Add AI operational hours columns ──────────────────────────────────────────
ALTER TABLE clients ADD COLUMN IF NOT EXISTS ai_active_start_time TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS ai_active_end_time   TIME DEFAULT NULL;

-- ── Add business hours columns (escalation context only) ──────────────────────
ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_start_time TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_end_time   TIME DEFAULT NULL;

-- ── Add timezone column ───────────────────────────────────────────────────────
ALTER TABLE clients ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';

-- ── Add column comments for Supabase Studio inline help ───────────────────────
COMMENT ON COLUMN clients.ai_active_start_time IS 'Start of AI active window in 24hr format (e.g., 18:00:00 for 6pm). Leave NULL for 24/7 active. Times interpreted in timezone column.';
COMMENT ON COLUMN clients.ai_active_end_time IS 'End of AI active window in 24hr format (e.g., 09:00:00 for 9am). Leave NULL for 24/7 active. If end < start, window spans midnight (overnight).';
COMMENT ON COLUMN clients.business_start_time IS 'Start of business hours in 24hr format (e.g., 09:00:00). Used for escalation message context only. Leave NULL if not needed.';
COMMENT ON COLUMN clients.business_end_time IS 'End of business hours in 24hr format (e.g., 18:00:00). Used for escalation message context only. Leave NULL if not needed.';
COMMENT ON COLUMN clients.timezone IS 'IANA timezone string (e.g., Asia/Singapore) — applies to all schedule times for this client. Defaults to UTC if not set.';

-- ── Set HeyAircon defaults ────────────────────────────────────────────────────
-- AI operational: 18:00–09:00 SGT (after-hours only, overnight)
-- Business hours: 09:00–18:00 SGT (human agents available)
-- All other clients: NULL (24/7 AI active, no business hours context)
UPDATE clients
SET
    ai_active_start_time = '18:00:00',
    ai_active_end_time   = '09:00:00',
    business_start_time  = '09:00:00',
    business_end_time    = '18:00:00',
    timezone             = 'Asia/Singapore'
WHERE client_id = 'hey-aircon';

-- ── Validation constraint (optional, recommended) ─────────────────────────────
-- Ensures both AI operational hours are set together (not one NULL, one set)
-- and both business hours are set together.
-- Allows (NULL, NULL) for each pair — this is the 24/7 active / no business hours case.
ALTER TABLE clients ADD CONSTRAINT ai_hours_both_or_neither
    CHECK (
        (ai_active_start_time IS NULL AND ai_active_end_time IS NULL)
        OR
        (ai_active_start_time IS NOT NULL AND ai_active_end_time IS NOT NULL)
    );

ALTER TABLE clients ADD CONSTRAINT business_hours_both_or_neither
    CHECK (
        (business_start_time IS NULL AND business_end_time IS NULL)
        OR
        (business_start_time IS NOT NULL AND business_end_time IS NOT NULL)
    );
```

**Safe to re-run:** All `ADD COLUMN IF NOT EXISTS` and `ADD CONSTRAINT` with named constraints (idempotent).

**Rollback (if needed):**
```sql
ALTER TABLE clients DROP CONSTRAINT IF EXISTS business_hours_both_or_neither;
ALTER TABLE clients DROP CONSTRAINT IF EXISTS ai_hours_both_or_neither;
ALTER TABLE clients DROP COLUMN IF EXISTS timezone;
ALTER TABLE clients DROP COLUMN IF EXISTS business_end_time;
ALTER TABLE clients DROP COLUMN IF EXISTS business_start_time;
ALTER TABLE clients DROP COLUMN IF EXISTS ai_active_end_time;
ALTER TABLE clients DROP COLUMN IF EXISTS ai_active_start_time;
```

---

## Code Changes

### 1. `engine/config/client_config.py` — Add Schedule Fields to ClientConfig

**File:** `engine/config/client_config.py`  
**Change type:** Add 5 new fields to `ClientConfig` dataclass

**Current dataclass (partial):**

```python
@dataclass
class ClientConfig:
    client_id: str
    meta_phone_number_id: str
    meta_verify_token: str
    human_agent_number: str | None
    # ... other fields
```

**New fields to add:**

```python
@dataclass
class ClientConfig:
    client_id: str
    meta_phone_number_id: str
    meta_verify_token: str
    human_agent_number: str | None
    
    # Schedule fields (added in migration 012)
    ai_active_start_time: str | None = None  # HH:MM:SS format
    ai_active_end_time: str | None = None    # HH:MM:SS format
    business_start_time: str | None = None   # HH:MM:SS format
    business_end_time: str | None = None     # HH:MM:SS format
    timezone: str = "UTC"                    # IANA timezone string
    
    # ... other fields
```

**Load these fields in `load_client_config()`:**

```python
async def load_client_config(client_id: str) -> ClientConfig:
    """Load client config from shared Supabase clients table (cached 5-min TTL)."""
    
    # ... existing cache check logic ...
    
    # Query shared Supabase
    result = await shared_db.table("clients").select("*").eq("client_id", client_id).execute()
    
    if not result.data:
        raise ClientNotFoundError(f"Client '{client_id}' not found")
    
    row = result.data[0]
    
    config = ClientConfig(
        client_id=row["client_id"],
        meta_phone_number_id=row["meta_phone_number_id"],
        # ... existing fields ...
        
        # Schedule fields (safe to access — migration 012 adds defaults)
        ai_active_start_time=row.get("ai_active_start_time"),  # None if NULL in DB
        ai_active_end_time=row.get("ai_active_end_time"),
        business_start_time=row.get("business_start_time"),
        business_end_time=row.get("business_end_time"),
        timezone=row.get("timezone", "UTC"),  # Defaults to UTC if NULL
    )
    
    # ... cache and return ...
```

---

### 2. `engine/core/message_handler.py` — Add Schedule Gate

**File:** `engine/core/message_handler.py`  
**Function:** `handle_inbound_message()`  
**Location:** Insert new gate **after escalation gate, before context builder** (currently Step 5 in pipeline)

**New pipeline order:**

```python
# Current Step 3: Escalation gate
if customer_row and customer_row.get("escalation_flag") is True:
    # ... send holding reply, return ...
    return

# NEW Step 4: Schedule gate (AI operational hours check)
if not _is_within_ai_hours(client_config):
    await _handle_out_of_hours_message(
        db=db,
        client_config=client_config,
        phone_number=phone_number,
        display_name=display_name,
        message_text=message_text,
    )
    return  # Stop pipeline — do NOT invoke agent

# Current Step 5 (now Step 5): Upsert customer record
# ... continues as before ...
```

**New helper function 1: `_is_within_ai_hours()`**

```python
def _is_within_ai_hours(client_config: ClientConfig) -> bool:
    """
    Check if current time is within AI operational hours for this client.
    
    Returns:
        True if AI should handle this message, False if out-of-hours.
        Returns True (always active) if ai_active_start_time and ai_active_end_time are both None.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    start_time = client_config.ai_active_start_time
    end_time = client_config.ai_active_end_time
    
    # If both NULL, AI is active 24/7
    if start_time is None and end_time is None:
        return True
    
    # If only one is set (should not happen due to DB constraint, but handle gracefully)
    if start_time is None or end_time is None:
        logger.warning(
            f"Client {client_config.client_id} has partial AI hours config "
            f"(start={start_time}, end={end_time}) — defaulting to 24/7 active"
        )
        return True
    
    # Parse timezone (default to UTC if invalid)
    try:
        tz = ZoneInfo(client_config.timezone)
    except Exception as e:
        logger.error(
            f"Invalid timezone '{client_config.timezone}' for client {client_config.client_id}: {e} "
            f"— defaulting to UTC"
        )
        tz = ZoneInfo("UTC")
    
    # Get current time in client's timezone
    now = datetime.now(tz)
    current_time = now.time()
    
    # Parse start/end times (format: "HH:MM:SS")
    try:
        from datetime import time as dt_time
        start_hour, start_min, start_sec = map(int, start_time.split(":"))
        end_hour, end_min, end_sec = map(int, end_time.split(":"))
        start = dt_time(start_hour, start_min, start_sec)
        end = dt_time(end_hour, end_min, end_sec)
    except Exception as e:
        logger.error(
            f"Failed to parse AI hours for client {client_config.client_id}: {e} "
            f"— defaulting to 24/7 active"
        )
        return True
    
    # Check if current time is within window
    if start <= end:
        # Daytime window (e.g., 09:00 → 18:00)
        return start <= current_time < end
    else:
        # Overnight window (e.g., 18:00 → 09:00)
        return current_time >= start or current_time < end
```

**New helper function 2: `_handle_out_of_hours_message()`**

```python
async def _handle_out_of_hours_message(
    db,
    client_config: ClientConfig,
    phone_number: str,
    display_name: str,
    message_text: str,
) -> None:
    """
    Handle a message that arrived outside AI operational hours.
    
    Steps:
    1. Build auto-reply message (with business hours if configured)
    2. Send auto-reply to customer
    3. Log outbound message
    4. Return (do NOT invoke agent)
    """
    from datetime import datetime, timezone
    from engine.integrations.meta_whatsapp import send_message
    
    # Build auto-reply message
    if client_config.business_start_time and client_config.business_end_time:
        # Format business hours (strip seconds for customer-facing text)
        start = client_config.business_start_time[:5]  # "09:00:00" -> "09:00"
        end = client_config.business_end_time[:5]
        
        # Convert to 12-hour format with am/pm for readability
        def format_12hr(time_str: str) -> str:
            hour, minute = map(int, time_str.split(":"))
            period = "am" if hour < 12 else "pm"
            hour_12 = hour if hour <= 12 else hour - 12
            hour_12 = 12 if hour_12 == 0 else hour_12  # midnight = 12am
            return f"{hour_12}:{minute:02d}{period}"
        
        start_12hr = format_12hr(start)
        end_12hr = format_12hr(end)
        hours_text = f"Our team operates {start_12hr}–{end_12hr}."
    else:
        hours_text = "Our team will respond shortly."
    
    auto_reply = f"Thanks for reaching out! {hours_text} A team member will respond shortly."
    
    # Send auto-reply
    try:
        await send_message(client_config, phone_number, auto_reply)
        logger.info(
            f"Out-of-hours auto-reply sent to {phone_number} (client: {client_config.client_id})"
        )
    except Exception as e:
        logger.error(
            f"Failed to send out-of-hours auto-reply to {phone_number}: {e}",
            exc_info=True,
        )
        # Continue to logging even if send failed
    
    # Log outbound
    try:
        now = datetime.now(timezone.utc).isoformat()
        await db.table("interactions_log").insert({
            "timestamp": now,
            "phone_number": phone_number,
            "direction": "outbound",
            "message_text": auto_reply,
            "message_type": "text",
        }).execute()
    except Exception as e:
        logger.error(
            f"Failed to log out-of-hours auto-reply for {phone_number}: {e}",
            exc_info=True,
        )
```

---

### 3. `engine/core/context_builder.py` — Pass Business Hours to System Prompt (Optional Enhancement)

**File:** `engine/core/context_builder.py`  
**Function:** `build_system_message()`  
**Change type:** Add business hours context to system prompt (only if configured)

**This is an enhancement for the escalation tool.** When the agent calls `escalate_to_human`, it can reference business hours in its customer-facing message.

**Add to the end of `build_system_message()` before returning:**

```python
async def build_system_message(db: Any, client_config: ClientConfig) -> str:
    """
    Assemble the Claude system prompt from Supabase config and policies tables.
    
    Args:
        db: Supabase async client.
        client_config: ClientConfig with business hours (if configured).
    
    Returns:
        Assembled system message string.
    """
    # ... existing logic to build sections ...
    
    # ── Business hours context (if configured) ────────────────────────────────
    if client_config.business_start_time and client_config.business_end_time:
        # Format for customer-facing messages
        start = client_config.business_start_time[:5]  # "09:00:00" -> "09:00"
        end = client_config.business_end_time[:5]
        
        def format_12hr(time_str: str) -> str:
            hour, minute = map(int, time_str.split(":"))
            period = "am" if hour < 12 else "pm"
            hour_12 = hour if hour <= 12 else hour - 12
            hour_12 = 12 if hour_12 == 0 else hour_12
            return f"{hour_12}:{minute:02d}{period}"
        
        start_12hr = format_12hr(start)
        end_12hr = format_12hr(end)
        
        business_hours_section = (
            f"\n\nBUSINESS HOURS:\n"
            f"Our team operates {start_12hr}–{end_12hr}. "
            f"When you escalate a conversation outside these hours, inform the customer that "
            f"a team member will follow up during business hours."
        )
        system_message += business_hours_section
    
    return system_message
```

**Note:** This requires updating the `build_system_message()` function signature to accept `client_config`. The current signature is `build_system_message(db)`. Update all call sites in `message_handler.py`:

```python
# OLD
system_message = await build_system_message(db)

# NEW
system_message = await build_system_message(db, client_config)
```

---

## Pipeline Integration

**Updated pipeline order after schedule gate insertion:**

```
1. Load client config + DB connection
2. Human agent routing (if phone_number == human_agent_number)
3. Log inbound to interactions_log
4. Query customer record from customers table
5. Escalation gate — if escalation_flag=True, send holding reply (once), then silent drop
6. SCHEDULE GATE (NEW) — if outside AI operational hours, send auto-reply, log outbound, return
7. Upsert customer record (INSERT new or UPDATE last_seen)
8. Opt-out detection gate (if opt-out keyword + active pending booking, mark opted_out, return)
9. Acquire per-customer lock (serialize concurrent messages from same customer)
10. Context builder → agent runner → tool loop
11. Send reply, log outbound
```

**Key placement decision:** Schedule gate runs AFTER escalation gate, not before.

**Rationale:**
- Escalated customers should remain silent 24/7 (no auto-reply, just holding reply on first message)
- If schedule gate ran first, an escalated customer outside AI hours would receive an auto-reply ("Our team operates 9am-6pm...") even though they're escalated
- Escalation takes priority over schedule — once escalated, the customer is in human-only mode until cleared

**Edge case:** Customer is escalated AND message arrives outside AI hours. Current behavior:
1. Escalation gate catches it first
2. Sends holding reply (if `escalation_notified=False`) or silently drops (if already notified)
3. Schedule gate never runs (pipeline returned at Step 5)
4. Customer does NOT receive out-of-hours auto-reply (correct — they're escalated, not out-of-hours)

---

## Cross-Feature Dependencies

### Dependency 1: Immediate Escalation (Task 1)

**Integration point:** Business hours context is passed to the agent via system prompt (see Code Changes section 3 above). The agent can reference business hours in its escalation response.

**Example escalation message (with business hours):**
```
"I don't have access to real-time dispatch information. Our team operates 9am–6pm and will follow up during business hours."
```

**No blocking dependency.** If Task 1 is implemented first, escalations work fine without business hours context (agent just says "Our team will reach out shortly"). Business hours context is an enhancement.

---

### Dependency 2: Human Takeover Detection (Task 3)

**No direct dependency.** Takeover and schedule are independent:
- Schedule gate controls whether AI runs at all (time-based)
- Takeover gate controls whether AI runs for a specific customer (flag-based)

**Pipeline order (when both are implemented):**
```
1. Log inbound
2. Takeover gate (if takeover_flag=True, forward to human, return)
3. Escalation gate (if escalation_flag=True, send holding reply, return)
4. Schedule gate (if outside AI hours, send auto-reply, return)
5. Agent runs
```

**Rationale:** Takeover runs first because it's customer-specific and takes absolute priority. Escalation and schedule both apply to AI-eligible customers.

**Edge case:** Customer is in takeover mode AND message arrives outside AI hours. Current behavior:
1. Takeover gate catches it first
2. Forwards message to `human_agent_number`
3. Schedule gate never runs
4. Customer does NOT receive out-of-hours auto-reply (correct — human is handling, not AI)

---

## Open Questions Resolved

### OQ-AS-01: How should messages outside AI hours be routed to human agents?

**Resolution:** Option D (Silent Queue) — send auto-reply to customer, log the message, do NOT forward to human agent.

**Rationale:**
- HeyAircon already monitors WhatsApp Business inbox during business hours (existing workflow)
- No additional integration complexity needed (no Telegram bot, no WhatsApp forwarding)
- Fail-safe — customer receives auto-reply setting expectations (not left hanging)

**Migration path:** If HeyAircon reports missing messages during pilot, implement Option A (forward to `human_agent_number`) in a follow-up phase. This requires adding a forwarding step to `_handle_out_of_hours_message()` (5 lines of code, no schema changes).

---

### OQ-AS-02: Should the grace period for mid-conversation transitions be configurable per client, or fixed at 5 minutes platform-wide?

**Resolution:** Fixed at 5 minutes platform-wide for Phase 1. Make configurable if requested.

**Rationale:**
- Grace period is an edge case mitigation (customer mid-conversation when AI hours end) — unlikely to need per-client tuning
- Adding a config column now increases complexity for no validated benefit
- If a client requests a different grace period (e.g., "give me 10 minutes"), add a `schedule_grace_period_minutes INTEGER DEFAULT 5` column to `clients` table

**Implementation decision:** Grace period logic is NOT implemented in Phase 1. Requirement REQ-AS-004 is deferred to Phase 2 after pilot feedback.

**Simplified Phase 1 behavior:** When AI hours end, ALL subsequent messages are out-of-hours (no grace period). If customer is mid-conversation at 8:59am and sends another message at 9:01am, they receive the out-of-hours auto-reply.

**Rationale for deferral:** Grace period logic adds complexity (needs to check `interactions_log` for recent messages, determine conversation sessions). HeyAircon pilot will reveal if this is a real pain point. If customers complain about abrupt cutoffs, implement grace period in Phase 2.

---

### OQ-AS-03: Should the out-of-hours auto-reply be configurable per client?

**Resolution:** Fixed template for Phase 1. Make configurable if requested.

**Fixed template:**
```
"Thanks for reaching out! {business_hours_text} A team member will respond shortly."
```

**Rationale:**
- The template is neutral and professional — works for any service SME
- Adding a config column now increases complexity without validated need
- If a client wants a custom auto-reply (e.g., "We're closed right now, but we'll get back to you ASAP!"), add an `out_of_hours_message TEXT` column to `clients` table

**Migration path:** If custom auto-replies are requested, update `_handle_out_of_hours_message()` to check `client_config.out_of_hours_message` first, fall back to fixed template if NULL.

---

## Implementation Notes for sdet-engineer

### Test Scenarios

#### TS-AS-01: Message during AI hours (daytime window)
- **Given:** Client config: `ai_active_start_time=09:00`, `ai_active_end_time=18:00`, `timezone=Asia/Singapore`
- **When:** Customer sends message at 14:00 SGT (2pm)
- **Then:** Schedule gate passes (14:00 is within 09:00–18:00)
- **And:** Agent processes the message normally
- **And:** Customer receives AI response

#### TS-AS-02: Message during AI hours (overnight window)
- **Given:** Client config: `ai_active_start_time=18:00`, `ai_active_end_time=09:00`, `timezone=Asia/Singapore`
- **When:** Customer sends message at 22:00 SGT (10pm)
- **Then:** Schedule gate passes (22:00 >= 18:00 in overnight logic)
- **And:** Agent processes the message normally

#### TS-AS-03: Message outside AI hours (daytime window)
- **Given:** Client config: `ai_active_start_time=09:00`, `ai_active_end_time=18:00`, `timezone=Asia/Singapore`
- **When:** Customer sends message at 20:00 SGT (8pm)
- **Then:** Schedule gate blocks (20:00 is NOT within 09:00–18:00)
- **And:** Customer receives auto-reply: "Thanks for reaching out! Our team operates 9am–6pm. A team member will respond shortly."
- **And:** Outbound auto-reply is logged to `interactions_log`
- **And:** Agent does NOT run

#### TS-AS-04: Message outside AI hours (overnight window)
- **Given:** Client config: `ai_active_start_time=18:00`, `ai_active_end_time=09:00`, `timezone=Asia/Singapore`
- **When:** Customer sends message at 14:00 SGT (2pm)
- **Then:** Schedule gate blocks (14:00 is NOT >= 18:00 AND NOT < 09:00)
- **And:** Customer receives auto-reply
- **And:** Agent does NOT run

#### TS-AS-05: 24/7 AI active (both columns NULL)
- **Given:** Client config: `ai_active_start_time=NULL`, `ai_active_end_time=NULL`
- **When:** Customer sends message at any time
- **Then:** Schedule gate always passes (`_is_within_ai_hours()` returns `True`)
- **And:** Agent processes the message normally

#### TS-AS-06: Business hours in auto-reply message
- **Given:** Client config: `business_start_time=09:00`, `business_end_time=18:00`
- **When:** Schedule gate sends auto-reply
- **Then:** Auto-reply contains "Our team operates 9am–6pm."

#### TS-AS-07: No business hours configured (NULL)
- **Given:** Client config: `business_start_time=NULL`, `business_end_time=NULL`
- **When:** Schedule gate sends auto-reply
- **Then:** Auto-reply contains "Our team will respond shortly." (no specific hours mentioned)

#### TS-AS-08: Escalated customer outside AI hours
- **Given:** Customer has `escalation_flag=True` and `escalation_notified=False`
- **And:** Client config: AI active 09:00–18:00, current time 20:00 (outside hours)
- **When:** Customer sends message
- **Then:** Escalation gate runs first (Step 5), sends holding reply, returns
- **And:** Schedule gate does NOT run (pipeline returned early)
- **And:** Customer receives holding reply ("A member of our team will get back to you today."), NOT out-of-hours auto-reply

#### TS-AS-09: Midnight crossing (overnight window edge case)
- **Given:** Client config: `ai_active_start_time=18:00`, `ai_active_end_time=09:00`
- **When:** Customer sends message at 00:30 SGT (12:30am)
- **Then:** Schedule gate passes (00:30 < 09:00 in overnight logic)
- **And:** Agent processes the message normally

#### TS-AS-10: Invalid timezone falls back to UTC
- **Given:** Client config: `timezone=InvalidTimezone`
- **When:** Customer sends message
- **Then:** `_is_within_ai_hours()` logs warning and defaults to UTC
- **And:** Schedule check proceeds using UTC time
- **And:** System does NOT crash

---

### Edge Cases to Verify

1. **Partial AI hours config (one NULL, one set)** — If DB constraint is violated somehow (manual edit), `_is_within_ai_hours()` logs warning and defaults to 24/7 active (fail-open)
2. **Timezone parsing failure** — Invalid IANA string → logs error, defaults to UTC
3. **Time parsing failure** — Malformed HH:MM:SS → logs error, defaults to 24/7 active
4. **Start time == end time** — E.g., both 09:00 → treat as no window (AI inactive 24/7), log warning
5. **Business hours formatting** — Verify 12-hour conversion: 00:00 → 12am, 12:00 → 12pm, 13:00 → 1pm, 23:00 → 11pm

---

### Verification Checklist

- [ ] Migration 012 applied to shared Supabase (5 new columns on `clients` table)
- [ ] HeyAircon row updated with AI hours 18:00–09:00, business hours 09:00–18:00, timezone Asia/Singapore
- [ ] `ClientConfig` dataclass contains 5 new fields
- [ ] `load_client_config()` loads schedule fields from DB
- [ ] `_is_within_ai_hours()` function added to `message_handler.py`
- [ ] `_handle_out_of_hours_message()` function added to `message_handler.py`
- [ ] Schedule gate inserted in pipeline after escalation gate (Step 6)
- [ ] Business hours context added to system prompt (optional enhancement)
- [ ] All 10 test scenarios pass
- [ ] Edge cases handled gracefully (no crashes on invalid config)
- [ ] Out-of-hours auto-reply logged to `interactions_log` with `direction='outbound'`

---

### Performance Targets

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Schedule gate latency | <10ms per message | Time `_is_within_ai_hours()` in prod logs |
| Config cache hit rate | >99% | Log cache hits vs. misses in `load_client_config()` |
| Auto-reply delivery rate | >99% | Count out-of-hours messages vs. logged auto-replies |
| Escalated customer out-of-hours handling | 0 auto-replies sent | Verify escalation gate runs before schedule gate |

---

**End of AI Schedule & Business Hours Architecture Specification**
