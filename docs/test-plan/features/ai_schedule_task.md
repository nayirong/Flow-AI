# Task: AI Schedule & Business Hours
> Assigned to: @software-engineer  
> Branch: feat/ai-schedule  
> Worktree: ../ai-schedule  
> Architecture spec: docs/architecture/ai_schedule.md  
> Test plan: docs/test-plan/features/ai_schedule.md

---

## Context

Adds two independently configurable time windows to control AI agent behavior:
1. **AI Operational Hours** — gate in pipeline that sends auto-reply and stops agent invocation when outside hours
2. **Business Operational Hours** — context-only field for escalation messages (tells customer when human agents are available)

Both windows stored per-client in shared Supabase, nullable (NULL = 24/7 active / no business context), support overnight windows (start > end). Changes take effect within 5 minutes via ClientConfig cache.

HeyAircon pilot: AI active 18:00–09:00 SGT (after-hours only), business hours 09:00–18:00 SGT.

---

## Implementation Order

Work in this exact order (dependencies flow downward):

1. **Database migration** (`supabase/migrations/012_ai_schedule.sql`)
2. **ClientConfig extension** (`engine/config/client_config.py`)
3. **Schedule gate helpers** (`engine/core/message_handler.py` — two new functions)
4. **Pipeline integration** (`engine/core/message_handler.py` — insert gate)
5. **Business hours in system prompt** (`engine/core/context_builder.py` — optional enhancement)
6. **Unit tests** (`engine/tests/unit/test_schedule_gate.py`)
7. **Integration tests** (`engine/tests/integration/test_schedule_gate_pipeline.py`)

---

## File 1: supabase/migrations/012_ai_schedule.sql

### What to create:
New migration file with DDL for 5 new columns on `clients` table.

### Exact changes required:

```sql
-- Migration 012: AI Schedule & Business Hours
-- Adds configurable time windows for AI operational hours and business hours context.

-- Add columns (all nullable except timezone)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS ai_active_start_time TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS ai_active_end_time   TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_start_time TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_end_time   TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';

-- Add comments for Supabase Studio
COMMENT ON COLUMN clients.ai_active_start_time IS 'Start of AI active window in 24hr format (e.g., 18:00:00 for 6pm). Leave NULL for 24/7 active. Times interpreted in timezone column.';
COMMENT ON COLUMN clients.ai_active_end_time IS 'End of AI active window in 24hr format (e.g., 09:00:00 for 9am). Leave NULL for 24/7 active. If end < start, window spans midnight (overnight).';
COMMENT ON COLUMN clients.business_start_time IS 'Start of business hours in 24hr format (e.g., 09:00:00). Used for escalation message context only. Leave NULL if not needed.';
COMMENT ON COLUMN clients.business_end_time IS 'End of business hours in 24hr format (e.g., 18:00:00). Used for escalation message context only. Leave NULL if not needed.';
COMMENT ON COLUMN clients.timezone IS 'IANA timezone string (e.g., Asia/Singapore) — applies to all schedule times for this client. Defaults to UTC if not set.';

-- Constraints: both-or-neither for each pair
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

-- Set HeyAircon defaults
UPDATE clients
SET
    ai_active_start_time = '18:00:00',
    ai_active_end_time   = '09:00:00',
    business_start_time  = '09:00:00',
    business_end_time    = '18:00:00',
    timezone             = 'Asia/Singapore'
WHERE client_id = 'hey-aircon';

-- Rollback (if needed):
-- ALTER TABLE clients DROP CONSTRAINT IF EXISTS business_hours_both_or_neither;
-- ALTER TABLE clients DROP CONSTRAINT IF EXISTS ai_hours_both_or_neither;
-- ALTER TABLE clients DROP COLUMN IF EXISTS timezone;
-- ALTER TABLE clients DROP COLUMN IF EXISTS business_end_time;
-- ALTER TABLE clients DROP COLUMN IF EXISTS business_start_time;
-- ALTER TABLE clients DROP COLUMN IF EXISTS ai_active_end_time;
-- ALTER TABLE clients DROP COLUMN IF EXISTS ai_active_start_time;
```

### Apply:
Apply to shared Supabase (`nayhqstuupdsqpltseof`), NOT per-client DB.

---

## File 2: engine/config/client_config.py

### What to change:
Add 5 new fields to `ClientConfig` dataclass, load them in `load_client_config()`.

### Location:
Find the `@dataclass class ClientConfig:` definition (around line 10-30).

### Exact changes:

**Step 1: Add fields to dataclass**

After existing fields (e.g., `human_agent_number`), add:

```python
# Schedule fields (migration 012)
ai_active_start_time: str | None = None  # HH:MM:SS format
ai_active_end_time: str | None = None    # HH:MM:SS format
business_start_time: str | None = None   # HH:MM:SS format
business_end_time: str | None = None     # HH:MM:SS format
timezone: str = "UTC"                    # IANA timezone string
```

**Step 2: Load fields in load_client_config()**

Find the line where `ClientConfig(...)` is instantiated (inside `load_client_config` function). Add these field assignments:

```python
config = ClientConfig(
    client_id=row["client_id"],
    # ... existing fields ...
    
    # Schedule fields (safe to access — migration 012 adds defaults)
    ai_active_start_time=row.get("ai_active_start_time"),
    ai_active_end_time=row.get("ai_active_end_time"),
    business_start_time=row.get("business_start_time"),
    business_end_time=row.get("business_end_time"),
    timezone=row.get("timezone", "UTC"),  # Default to UTC if NULL
)
```

---

## File 3: engine/core/message_handler.py (Helper Functions)

### What to create:
Two new helper functions: `_is_within_ai_hours()` and `_handle_out_of_hours_message()`.

### Location:
Add these functions BEFORE `handle_inbound_message()` (module-level functions).

### Function 1: _is_within_ai_hours()

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
    
    # Edge case: start == end → no active window
    if start == end:
        logger.warning(
            f"Client {client_config.client_id} has AI hours start == end ({start}) — "
            f"no active window (AI inactive 24/7)"
        )
        return False
    
    # Check if current time is within window
    if start <= end:
        # Daytime window (e.g., 09:00 → 18:00)
        return start <= current_time < end
    else:
        # Overnight window (e.g., 18:00 → 09:00)
        return current_time >= start or current_time < end
```

### Function 2: _handle_out_of_hours_message()

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

## File 4: engine/core/message_handler.py (Pipeline Integration)

### What to change:
Insert schedule gate check AFTER escalation gate, BEFORE agent invocation.

### Location:
Find the `handle_inbound_message()` function. Locate the escalation gate check (around line 100-150, looks for `if customer_row and customer_row.get("escalation_flag") is True:`).

### Exact change:

**Insert this block immediately AFTER the escalation gate block (after its `return` statement):**

```python
# ── Schedule gate: AI operational hours check ──────────────────────────────────
if not _is_within_ai_hours(client_config):
    await _handle_out_of_hours_message(
        db=db,
        client_config=client_config,
        phone_number=phone_number,
        display_name=display_name,
        message_text=message_text,
    )
    return  # Stop pipeline — do NOT invoke agent
```

**Pipeline order after this change:**
1. Load config + DB
2. Human agent routing
3. Log inbound
4. Escalation gate (existing)
5. **Schedule gate (NEW)**
6. Upsert customer
7. Opt-out detection
8. Agent runs

---

## File 5: engine/core/context_builder.py (Optional Enhancement)

### What to change:
Add business hours context block to system prompt IF both business hours fields are configured.

### Location:
Find `build_system_message()` function, near the end before the return statement.

### Exact change:

**Add this block before `return system_message`:**

```python
# Add business hours context if configured
if client_config.business_start_time and client_config.business_end_time:
    start_12hr = _format_time_12hr(client_config.business_start_time[:5])
    end_12hr = _format_time_12hr(client_config.business_end_time[:5])
    business_hours_block = f"""

**BUSINESS HOURS:**
Our business hours are {start_12hr}–{end_12hr} ({client_config.timezone}). When escalating outside these hours, inform the customer that a team member will follow up during business hours.
"""
    system_message += business_hours_block
```

**Also add helper function at module level:**

```python
def _format_time_12hr(time_str: str) -> str:
    """Convert HH:MM to 12-hour format with am/pm."""
    hour, minute = map(int, time_str.split(":"))
    period = "am" if hour < 12 else "pm"
    hour_12 = hour if hour <= 12 else hour - 12
    hour_12 = 12 if hour_12 == 0 else hour_12
    return f"{hour_12}:{minute:02d}{period}"
```

---

## File 6: engine/tests/unit/test_schedule_gate.py (new file)

### What to create:
Unit test file with 15 tests covering `_is_within_ai_hours()` and `_handle_out_of_hours_message()`.

### Test structure:
Use existing test patterns from `engine/tests/unit/test_message_handler.py`. Mock `ClientConfig`, datetime, and `send_message()`.

### Tests to implement:
1. `test_is_within_ai_hours_24_7_active` — both AI hours NULL → returns True
2. `test_is_within_ai_hours_daytime_window_inside` — 09:00–18:00, current 12:00 → True
3. `test_is_within_ai_hours_daytime_window_outside` — 09:00–18:00, current 20:00 → False
4. `test_is_within_ai_hours_overnight_window_inside_before_midnight` — 18:00–09:00, current 20:00 → True
5. `test_is_within_ai_hours_overnight_window_inside_after_midnight` — 18:00–09:00, current 06:00 → True
6. `test_is_within_ai_hours_overnight_window_outside` — 18:00–09:00, current 12:00 → False
7. `test_is_within_ai_hours_edge_at_start` — start time inclusive → True
8. `test_is_within_ai_hours_edge_at_end` — end time exclusive → False
9. `test_is_within_ai_hours_timezone_conversion` — SGT timezone correctly interpreted
10. `test_is_within_ai_hours_invalid_timezone_defaults_utc` — invalid tz → logs error, uses UTC
11. `test_is_within_ai_hours_partial_config_logs_warning` — one field NULL → logs warning, returns True
12. `test_is_within_ai_hours_same_start_end_no_window` — start == end → returns False, logs warning
13. `test_handle_out_of_hours_message_with_business_hours` — includes hours in auto-reply
14. `test_handle_out_of_hours_message_no_business_hours` — generic message
15. `test_handle_out_of_hours_send_failure_non_fatal` — exception caught, doesn't propagate

---

## File 7: engine/tests/integration/test_schedule_gate_pipeline.py (new file)

### What to create:
Integration test file with 8 tests covering full webhook → schedule gate → response flow.

### Test structure:
Use existing test patterns from `engine/tests/integration/test_webhook_to_reply.py`. Mock Meta webhook payload, Supabase responses, and verify pipeline behavior.

### Tests to implement:
1. `test_out_of_hours_message_sends_auto_reply_stops_pipeline` — outside hours → auto-reply sent, agent NOT run
2. `test_within_hours_message_runs_agent_normally` — within hours → agent runs, no auto-reply
3. `test_24_7_active_no_gate_interference` — NULL AI hours → agent always runs
4. `test_overnight_window_before_midnight` — 20:00 in 18:00–09:00 window → agent runs
5. `test_overnight_window_after_midnight` — 03:00 in 18:00–09:00 window → agent runs
6. `test_overnight_window_outside_midday` — 12:00 outside 18:00–09:00 → auto-reply sent
7. `test_schedule_gate_runs_after_escalation_gate` — escalated customer within AI hours → escalation gate fires first
8. `test_escalated_customer_outside_ai_hours` — escalated customer outside hours → escalation gate fires, not schedule gate

---

## Constraints

- Work only inside the worktree (../ai-schedule)
- No direct commits to master
- Run existing tests before starting to confirm clean baseline: `cd engine && python -m pytest tests/unit/test_message_handler.py -v`
- After implementation: `git add`, `git commit -m "feat: AI schedule & business hours gate"`, `git log --oneline -3` to confirm
- Format code before committing: `cd engine && python -m black . && python -m isort .`

---

## Validate

After all files changed and tests written:

1. Run new unit tests: `cd engine && python -m pytest tests/unit/test_schedule_gate.py -v`
2. Run new integration tests: `cd engine && python -m pytest tests/integration/test_schedule_gate_pipeline.py -v`
3. Run regression tests: `cd engine && python -m pytest tests/unit/test_message_handler.py -v`
4. Confirm all pass before reporting done

---

## Report Back With

1. Files changed (list with line counts: `wc -l <file>`)
2. Tests added (count: `grep -c "^def test_" tests/unit/test_schedule_gate.py tests/integration/test_schedule_gate_pipeline.py`)
3. Test results (paste pytest output showing pass/fail counts)
4. Git log entry (paste output of `git log --oneline -3`)
