# Task: Human Takeover Detection
> Assigned to: @software-engineer  
> Branch: feat/human-takeover  
> Worktree: ../human-takeover  
> Architecture spec: docs/architecture/human_takeover.md  
> Test plan: docs/test-plan/features/human_takeover.md  
> Priority: HIGH (client-flagged concern)

---

## Context

Automatically pauses AI responses when a human agent takes over a customer conversation — and resumes AI when the human is done. Uses **reply-to-forwarded-message** mechanism (Option B): engine sends proactive monitoring alerts to `human_agent_number` whenever AI handles a customer. Human replies "take" to that alert (one word, reply-to-message resolves customer). AI pauses for that customer. Human replies "done" to resume AI.

**Key components:**
- Takeover gate (runs BEFORE escalation gate in pipeline)
- Silent drop behavior (no AI reply while takeover active)
- Message forwarding (all inbound from taken-over customer → human agent)
- Auto-resume safety timeout (APScheduler job clears stale takeovers after 4 hours)
- Status command (`//status` lists all active takeovers)
- Dual-flag clearing ("done" clears both `takeover_flag` AND `escalation_flag`)

**Why Option B:** Meta Cloud API does NOT deliver echo webhooks when human sends a message from WhatsApp Business app. Outbound messages trigger STATUS webhooks (delivery/read receipts) which do NOT contain message content.

---

## Implementation Order

Work in this exact order (dependencies flow downward):

1. **Database migration** (`supabase/migrations/013_human_takeover.sql`)
2. **Takeover gate** (`engine/core/message_handler.py` — new helper + gate insertion)
3. **Conversation alerts** (`engine/core/message_handler.py` — new helper + call after agent)
4. **Reset handler extensions** (`engine/core/reset_handler.py` — takeover/release/status commands)
5. **Auto-resume job** (`engine/core/takeover_auto_resume.py` — new file)
6. **APScheduler registration** (`engine/api/webhook.py` — add job)
7. **Settings extension** (`engine/config/settings.py` — timeout env var)
8. **Client config helper** (`engine/config/client_config.py` — `get_all_active_clients()`)
9. **Unit tests** (`engine/tests/unit/test_takeover_gate.py`, `test_takeover_commands.py`, `test_auto_resume.py`)
10. **Integration tests** (`engine/tests/integration/test_takeover_pipeline.py`)

---

## File 1: supabase/migrations/013_human_takeover.sql

### What to create:
New migration file with DDL for `customers` table columns and `takeover_tracking` audit table.

### Exact changes required:

```sql
-- Migration 013: Human Takeover Detection
-- Adds takeover state tracking and audit trail for manual human agent takeovers.

-- ── Add takeover state columns to customers table ─────────────────────────────
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_flag BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_by TEXT DEFAULT NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_ai_alert_msg_id TEXT DEFAULT NULL;

-- ── Create takeover_tracking audit table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS takeover_tracking (
    id SERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    alert_msg_id TEXT,
    takeover_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    takeover_by TEXT,
    command_type TEXT NOT NULL,
    released_at TIMESTAMPTZ DEFAULT NULL,
    released_by TEXT DEFAULT NULL,
    release_command_type TEXT DEFAULT NULL
);

-- ── Indexes for takeover_tracking ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_takeover_tracking_alert_msg_id 
    ON takeover_tracking(alert_msg_id) 
    WHERE released_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_takeover_tracking_phone_active 
    ON takeover_tracking(phone_number, takeover_at) 
    WHERE released_at IS NULL;

-- ── Index on customers table for takeover gate ────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_customers_takeover_flag 
    ON customers(phone_number) 
    WHERE takeover_flag = TRUE;

-- ── Add column comments for Supabase Studio ───────────────────────────────────
COMMENT ON COLUMN customers.takeover_flag IS 'TRUE if human agent has manually taken over this conversation. AI is paused until released.';
COMMENT ON COLUMN customers.takeover_by IS 'Phone number of human agent who initiated takeover.';
COMMENT ON COLUMN customers.takeover_at IS 'Timestamp when takeover was initiated.';
COMMENT ON COLUMN customers.last_ai_alert_msg_id IS 'wamid of the most recent conversation alert sent to human_agent_number for this customer. Used for reply-to-message takeover detection.';

COMMENT ON TABLE takeover_tracking IS 'Audit trail for manual human agent takeovers. Tracks when human took over, when they released, and how (manual or timeout).';
COMMENT ON COLUMN takeover_tracking.alert_msg_id IS 'wamid of the conversation alert sent to human_agent_number. Used for reply-to-message takeover detection.';
COMMENT ON COLUMN takeover_tracking.command_type IS 'How takeover was initiated: reply_to_alert or auto_timeout.';
COMMENT ON COLUMN takeover_tracking.release_command_type IS 'How takeover was released: manual_done or auto_resume.';

-- Rollback (if needed):
-- DROP INDEX IF EXISTS idx_customers_takeover_flag;
-- DROP INDEX IF EXISTS idx_takeover_tracking_phone_active;
-- DROP INDEX IF EXISTS idx_takeover_tracking_alert_msg_id;
-- DROP TABLE IF EXISTS takeover_tracking;
-- ALTER TABLE customers DROP COLUMN IF EXISTS last_ai_alert_msg_id;
-- ALTER TABLE customers DROP COLUMN IF EXISTS takeover_at;
-- ALTER TABLE customers DROP COLUMN IF EXISTS takeover_by;
-- ALTER TABLE customers DROP COLUMN IF EXISTS takeover_flag;
```

### Apply:
Apply to per-client Supabase (hey-aircon DB), NOT shared config DB.

---

## File 2: engine/core/message_handler.py (Takeover Gate)

### What to create:
New helper function `_handle_takeover_inbound()` and insert takeover gate check in pipeline.

### Location:
Add helper function BEFORE `handle_inbound_message()` (module-level).

### Function: _handle_takeover_inbound()

```python
async def _handle_takeover_inbound(
    db,
    client_config,
    phone_number: str,
    display_name: str,
    message_text: str,
) -> None:
    """
    Handle a message from a customer who is currently in takeover mode.
    
    Steps:
    1. Forward the message to human_agent_number in real-time
    2. Return (do NOT send AI reply, do NOT invoke agent)
    """
    from datetime import datetime, timezone
    from engine.integrations.meta_whatsapp import send_message
    
    logger.info(
        f"Takeover gate ACTIVE for {phone_number} (client: {client_config.client_id}) — "
        "forwarding to human agent, AI will not respond"
    )
    
    # Format forward message
    customer_name = display_name or phone_number
    forward_text = (
        f"📥 *{customer_name}* just replied:\n\n"
        f'"{message_text}"\n\n'
        f"(AI is paused. Reply \"done\" to resume AI.)"
    )
    
    # Send forward to human agent
    if client_config.human_agent_number:
        try:
            await send_message(
                client_config=client_config,
                to_phone_number=client_config.human_agent_number,
                text=forward_text,
            )
            logger.info(
                f"Takeover inbound forwarded to {client_config.human_agent_number} "
                f"for customer {phone_number}"
            )
        except Exception as e:
            logger.error(
                f"Failed to forward takeover inbound for {phone_number}: {e}",
                exc_info=True,
            )
            # Non-fatal — continue (human may see message in WhatsApp Business inbox)
    
    # Do NOT send any reply to the customer — complete silence
    # Message is already logged to interactions_log (Step 3 in pipeline)
```

### Pipeline Integration:

**Find the `handle_inbound_message()` function. Locate the escalation gate check (looks for `if customer_row and customer_row.get("escalation_flag") is True:`).**

**Insert this block BEFORE the escalation gate (after Step 3 "Log inbound", before Step 4 "Escalation gate"):**

```python
# ── Takeover gate: if human has taken over, forward message and stop ───────────
if customer_row and customer_row.get("takeover_flag") is True:
    await _handle_takeover_inbound(
        db=db,
        client_config=client_config,
        phone_number=phone_number,
        display_name=display_name,
        message_text=message_text,
    )
    return  # Stop pipeline — AI does NOT run
```

**Pipeline order after this change:**
1. Load config + DB
2. Human agent routing
3. Log inbound
4. **Takeover gate (NEW)** — runs BEFORE escalation
5. Escalation gate (existing)
6. Schedule gate (Task 1)
7. Agent runs

---

## File 3: engine/core/message_handler.py (Conversation Alerts)

### What to create:
New helper function `_maybe_send_conversation_alert()` and call it after agent runs successfully.

### Location:
Add helper function BEFORE `handle_inbound_message()` (module-level).

### Function: _maybe_send_conversation_alert()

```python
async def _maybe_send_conversation_alert(
    db,
    client_config,
    phone_number: str,
    display_name: str,
    message_text: str,
) -> None:
    """
    Send a proactive conversation alert to human_agent_number if this is a new session.
    
    A "new session" = no inbound message from this customer in the last 4 hours.
    
    Alert is sent ONCE per session (not per message) to prevent spam.
    """
    from datetime import datetime, timezone, timedelta
    from engine.integrations.meta_whatsapp import send_message
    
    SESSION_TIMEOUT_HOURS = 4
    
    # Check last inbound message timestamp
    try:
        cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=SESSION_TIMEOUT_HOURS)).isoformat()
        result = await (
            db.table("interactions_log")
            .select("timestamp")
            .eq("phone_number", phone_number)
            .eq("direction", "inbound")
            .gt("timestamp", cutoff_time)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        
        if result.data:
            # Recent inbound found — session is active, do NOT send alert
            logger.debug(
                f"Conversation session active for {phone_number} — skipping alert"
            )
            return
    except Exception as e:
        logger.error(
            f"Failed to check conversation session for {phone_number}: {e}",
            exc_info=True,
        )
        # On error, do NOT send alert (fail-safe — prefer no alert over spam)
        return
    
    # New session detected — send alert
    if not client_config.human_agent_number:
        return  # No human agent configured, skip alert
    
    customer_name = display_name or phone_number
    alert_text = (
        f"📨 AI handling: *{customer_name}*\n\n"
        f'"{message_text[:80]}{"..." if len(message_text) > 80 else ""}"\n\n'
        f"Reply \"take\" to this message to take over."
    )
    
    try:
        alert_msg_id = await send_message(
            client_config=client_config,
            to_phone_number=client_config.human_agent_number,
            text=alert_text,
        )
        
        if alert_msg_id:
            logger.info(
                f"Conversation alert sent to {client_config.human_agent_number} "
                f"for customer {phone_number}, wamid={alert_msg_id}"
            )
            
            # Store alert wamid for reply-to-message detection
            await db.table("customers").update({
                "last_ai_alert_msg_id": alert_msg_id,
            }).eq("phone_number", phone_number).execute()
        else:
            logger.warning(
                f"Failed to send conversation alert for {phone_number} — "
                "alert_msg_id is NULL"
            )
    except Exception as e:
        logger.error(
            f"Failed to send conversation alert for {phone_number}: {e}",
            exc_info=True,
        )
        # Non-fatal — AI still handled the message successfully
```

### Pipeline Integration:

**Find in `handle_inbound_message()` where the agent runs and replies are sent (near end of function, after agent runner completes, before sending reply to customer).**

**Insert this call AFTER agent runs successfully, BEFORE sending reply:**

```python
# ── Send conversation alert (if new session) ───────────────────────────────────
await _maybe_send_conversation_alert(
    db=db,
    client_config=client_config,
    phone_number=phone_number,
    display_name=display_name,
    message_text=message_text,
)
```

---

## File 4: engine/core/reset_handler.py (Extensions)

### What to change:
Add takeover command detection, dual-flag clearing, and status command.

### Changes in order:

#### Step 1: Add keyword sets (module level, near top)

**After existing `RESET_KEYWORDS`, add:**

```python
# Takeover command keywords
TAKEOVER_KEYWORDS = frozenset([
    "take", "mine", "me", "takeover", "i'll handle", "ill handle", "take over"
])
```

#### Step 2: Update `handle_human_agent_message()` function

**Find the function and update routing logic to handle 3 command types:**

```python
async def handle_human_agent_message(
    db,
    client_config,
    phone_number: str,
    message_text: str,
    context_message_id: Optional[str],
) -> None:
    """
    Process a message from the human agent.
    
    Handles:
    1. Escalation reset (existing)
    2. Takeover command (new) — "take"
    3. Release command (new) — "done" clears both escalation and takeover
    4. Status command (new) — "//status"
    """
    from engine.integrations.meta_whatsapp import send_message
    
    # ── Status command (standalone, not a reply) ──────────────────────────────
    if message_text.strip().lower() in ["//status", "status"]:
        await _handle_status_command(db, client_config, phone_number)
        return
    
    # ── Takeover and reset commands require reply-to-message ──────────────────
    if context_message_id is None:
        # Not a reply — send help
        help_text = (
            "To take over a conversation: Reply \"take\" to an AI alert.\n"
            "To release a conversation: Reply \"done\" to a customer message.\n"
            "To see active takeovers: Send \"//status\"."
        )
        try:
            await send_message(client_config, phone_number, help_text)
        except Exception:
            pass
        return
    
    # Normalize message text
    normalized = _normalise(message_text)
    
    # ── Path 1: Takeover command ──────────────────────────────────────────────
    if normalized in TAKEOVER_KEYWORDS:
        await _handle_takeover_command(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            context_message_id=context_message_id,
        )
        return
    
    # ── Path 2: Release/reset command ─────────────────────────────────────────
    if normalized in RESET_KEYWORDS:
        # This handles BOTH escalation reset AND takeover release
        await _handle_release_command(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            context_message_id=context_message_id,
        )
        return
    
    # ── Invalid keyword ───────────────────────────────────────────────────────
    help_text = (
        "Valid commands:\n"
        "• \"take\" — take over a conversation\n"
        "• \"done\" — release a conversation\n"
        "• \"//status\" — list active takeovers"
    )
    try:
        await send_message(client_config, phone_number, help_text)
    except Exception:
        pass
```

#### Step 3: Implement `_handle_takeover_command()` (new function, module level)

**SEE ARCHITECTURE SPEC for full implementation** — this function:
1. Queries `customers` by `last_ai_alert_msg_id = context_message_id`
2. Sets `takeover_flag=True`, `takeover_by`, `takeover_at`
3. Inserts into `takeover_tracking`
4. Sends confirmation to human agent

#### Step 4: Implement `_handle_release_command()` (new function, module level)

**SEE ARCHITECTURE SPEC for full implementation** — this function:
1. Tries takeover lookup first (`last_ai_alert_msg_id`)
2. Clears BOTH `takeover_flag` AND `escalation_flag` if found
3. Updates both `takeover_tracking` and `escalation_tracking`
4. Calls `sync_customer_to_sheets()` (fire-and-forget)
5. Falls back to existing escalation reset logic if no takeover match

#### Step 5: Implement `_handle_status_command()` (new function, module level)

**SEE ARCHITECTURE SPEC for full implementation** — this function:
1. Queries all customers with `takeover_flag=True`
2. Formats response listing each customer, time ago
3. Sends formatted status to human agent

---

## File 5: engine/core/takeover_auto_resume.py (NEW FILE)

### What to create:
New module with auto-resume job that clears stale takeovers after timeout.

**SEE ARCHITECTURE SPEC for full implementation.** Key components:
1. `run_takeover_auto_resume()` — main job function (called by APScheduler)
2. `_auto_resume_for_client()` — per-client logic
3. Queries customers with `takeover_flag=True` AND `takeover_at < (now - timeout)`
4. Clears flag, updates tracking, sends notification

---

## File 6: engine/api/webhook.py (APScheduler Registration)

### What to change:
Add takeover auto-resume job to scheduler in `lifespan()` function.

### Location:
Find `@asynccontextmanager async def lifespan(app: FastAPI):` — this is where APScheduler jobs are registered.

### Exact change:

**After the existing followup scheduler job, add:**

```python
# Job 2: Takeover auto-resume (new)
scheduler.add_job(
    run_takeover_auto_resume,
    trigger="interval",
    minutes=30,  # Run every 30 minutes
    id="takeover_auto_resume",
    replace_existing=True,
)
```

**Update the startup log line:**

```python
logger.info(
    f"Scheduler started: followup={interval_minutes}min, takeover_auto_resume=30min"
)
```

**Add import at top of file:**

```python
from engine.core.takeover_auto_resume import run_takeover_auto_resume
```

---

## File 7: engine/config/settings.py

### What to change:
Add optional env var for takeover timeout.

### Location:
Find `class Settings(BaseSettings):` definition.

### Exact change:

**Add field after existing fields:**

```python
# Takeover auto-resume timeout (hours)
takeover_timeout_hours: int = 4
```

---

## File 8: engine/config/client_config.py

### What to create:
New helper function `get_all_active_clients()` for scheduler jobs.

### Location:
Add at module level, after `load_client_config()`.

### Function:

```python
async def get_all_active_clients() -> list[ClientConfig]:
    """
    Load all active clients from shared Supabase.
    
    Used by scheduler jobs (followup, takeover auto-resume) to iterate over all clients.
    
    Returns:
        List of ClientConfig objects for all clients where is_active=True.
    """
    from engine.integrations.supabase_client import get_shared_db
    
    shared_db = await get_shared_db()
    
    try:
        result = await (
            shared_db.table("clients")
            .select("*")
            .eq("is_active", True)
            .execute()
        )
    except Exception as e:
        logger.error(f"Failed to load active clients: {e}", exc_info=True)
        raise
    
    if not result.data:
        logger.warning("No active clients found in shared Supabase")
        return []
    
    configs = []
    for row in result.data:
        try:
            config = ClientConfig(
                client_id=row["client_id"],
                # ... all fields (same as load_client_config) ...
            )
            configs.append(config)
        except Exception as e:
            logger.error(
                f"Failed to construct ClientConfig for {row.get('client_id')}: {e}",
                exc_info=True,
            )
            continue
    
    return configs
```

---

## File 9: engine/tests/unit/test_takeover_gate.py (new file)

### What to create:
Unit test file with 7 tests covering takeover gate and conversation alerts.

**Tests:** See test plan for full list. Use existing test patterns from `engine/tests/unit/test_message_handler.py`.

---

## File 10: engine/tests/unit/test_takeover_commands.py (new file)

### What to create:
Unit test file with 9 tests covering takeover/release/status commands in reset handler.

**Tests:** See test plan for full list. Use existing test patterns from `engine/tests/unit/test_reset_handler.py`.

---

## File 11: engine/tests/unit/test_auto_resume.py (new file)

### What to create:
Unit test file with 4 tests covering auto-resume job.

**Tests:** See test plan for full list.

---

## File 12: engine/tests/integration/test_takeover_pipeline.py (new file)

### What to create:
Integration test file with 6 tests covering full takeover lifecycle.

**Tests:** See test plan for full list. Use existing patterns from `engine/tests/integration/test_webhook_to_reply.py`.

---

## Constraints

- Work only inside the worktree (../human-takeover)
- No direct commits to master
- Run existing tests before starting: `cd engine && python -m pytest tests/unit/test_message_handler.py tests/unit/test_reset_handler.py -v`
- After implementation: `git add`, `git commit -m "feat: human takeover detection with reply-to-message"`, `git log --oneline -3` to confirm
- Format code before committing: `cd engine && python -m black . && python -m isort .`

---

## Validate

After all files changed and tests written:

1. Run new unit tests:
   - `cd engine && python -m pytest tests/unit/test_takeover_gate.py -v`
   - `cd engine && python -m pytest tests/unit/test_takeover_commands.py -v`
   - `cd engine && python -m pytest tests/unit/test_auto_resume.py -v`
2. Run new integration tests: `cd engine && python -m pytest tests/integration/test_takeover_pipeline.py -v`
3. Run regression tests:
   - `cd engine && python -m pytest tests/unit/test_message_handler.py -v`
   - `cd engine && python -m pytest tests/unit/test_reset_handler.py -v`
4. Confirm all pass before reporting done

---

## Report Back With

1. Files changed (list with line counts: `wc -l <file>`)
2. Tests added (count: `find tests -name "test_takeover*" -o -name "test_auto_resume*" | xargs grep -c "^async def test_" | awk -F: '{sum+=$2} END {print sum}'`)
3. Test results (paste pytest output showing pass/fail counts)
4. Git log entry (paste output of `git log --oneline -3`)
