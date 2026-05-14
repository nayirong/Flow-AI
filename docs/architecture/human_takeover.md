# Human Takeover Detection — Architecture Specification

> **Architecture Decision Record & Implementation Specification**  
> Author: @software-architect  
> Date: 2026-05-13  
> Status: Approved for implementation  
> Priority: HIGH (client-flagged concern)

---

## Table of Contents

1. [Summary](#summary)
2. [Critical Pre-Implementation Research](#critical-pre-implementation-research)
3. [Design Decisions](#design-decisions)
4. [Database Changes](#database-changes)
5. [Code Changes](#code-changes)
6. [Pipeline Integration](#pipeline-integration)
7. [Cross-Feature Dependencies](#cross-feature-dependencies)
8. [Open Questions Resolved](#open-questions-resolved)
9. [Implementation Notes for sdet-engineer](#implementation-notes-for-sdet-engineer)

---

## Summary

**What this feature does:**  
Automatically pauses AI responses when a human agent takes over a customer conversation — and resumes AI when the human is done. The human agent workflow requires **zero extra steps** to initiate takeover (one-word reply-to-message command) and no phone number input.

**Mechanism:** Reply-to-forwarded-message (Option B)  
When the AI handles a customer message, the engine proactively sends a lightweight monitoring alert to `human_agent_number`. Human agent replies "take" to that alert (one word, reply-to-message resolves customer). The AI pauses for that customer. Human replies "done" to any customer message alert to resume AI.

**Key features:**
- **Takeover gate** — runs BEFORE escalation gate in the pipeline
- **Silent drop behavior** — no AI reply sent while takeover is active
- **Message forwarding** — all inbound messages from taken-over customer are forwarded to `human_agent_number` in real-time
- **Auto-resume safety timeout** — APScheduler job clears stale takeovers after 4 hours (configurable)
- **Status command** — `//status` lists all active takeovers

**Why Option B (not Option A — echo webhook auto-detect):**  
Meta Cloud API does NOT deliver echo webhooks when a human sends a message from the WhatsApp Business app. Outbound messages trigger STATUS webhooks (delivery/read receipts) which do NOT contain message content. See [Critical Pre-Implementation Research](#critical-pre-implementation-research) below.

---

## Critical Pre-Implementation Research

### OQ-HT-001: Echo Webhook Availability

**Question:** Does Meta Cloud API deliver webhook events when the human agent sends a message from the WhatsApp Business app?

**Research method:** Consulted Meta Cloud API webhook documentation (https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components)

**Finding:** Meta Cloud API delivers **two distinct webhook payload structures**:

1. **Incoming messages (customer → business):**  
   Contains `messages` array with `from`, `id`, message `type`, and content (`text`, `image`, etc.)

2. **Outgoing messages (business → customer):**  
   Contains `statuses` array with `id` (wamid), `status` (`sent` / `delivered` / `read`), and `recipient_id`.  
   **Does NOT contain message content or sender context.**

**Quote from documentation:**
> "Messages webhooks describing a message sent by a business to a WhatsApp user have a different structure. You can easily identify these because they include a `statuses` array... each outgoing message can have up to three separate webhooks (one for a status of sent, one for delivered, and one for read)."

**Conclusion:**  
When a human agent sends a message from the WhatsApp Business app, the webhook receives a STATUS update (sent/delivered/read) but NOT a message echo. The status webhook contains:
- `id` — wamid of the message
- `status` — delivery status string
- `recipient_id` — customer phone number

**It does NOT contain:**
- Message text
- Sender context (no way to distinguish "human sent this" vs. "AI sent this")

**Therefore:** Option A (echo webhook auto-detect) is **NOT AVAILABLE**. We cannot detect takeover by listening for echo webhooks because those webhooks do not exist.

**Implementation path:** Use **Option B (reply-to-forwarded-message)** — extend the existing escalation reset pattern. Human agent receives proactive alerts for AI-handled conversations and replies "take" to initiate takeover.

---

## Design Decisions

### Decision 1: Option B (Reply-to-Forwarded-Message) vs. Manual Command

**Choice:** Implement Option B — proactive conversation alerts sent to `human_agent_number` with reply-to-message takeover command.

**Rationale:**
- **Zero phone number input:** Human replies to an alert thread — the reply-to-message context automatically resolves the customer (same UX as escalation reset today)
- **Extends existing pattern:** `reset_handler.py` already implements reply-to-message keyword matching — takeover uses the same detection logic
- **Proactive visibility:** Human receives alerts for AI conversations in real-time, even if they don't want to take over (awareness of what AI is handling)

**Alternative rejected:** Human sends a standalone command like `//take +6591234567`. Rejected because:
- Requires typing a phone number (high friction)
- Human must know the customer's phone number (not always visible in WhatsApp Business inbox)
- Breaks the "zero extra steps" requirement

---

### Decision 2: Proactive Conversation Alerts (Not Reactive)

**Choice:** Engine sends a lightweight monitoring alert to `human_agent_number` whenever the AI handles a customer message.

**Alert format:**
```
📨 AI handling: John Tan

"Hi, can I book an aircon service for next week?"

Reply "take" to this message to take over.
```

**Frequency:** One alert per customer conversation session (not per message). A "session" resets if the customer hasn't messaged in 4+ hours.

**Rationale:**
- **Human has context BEFORE deciding to take over:** Alert shows what the customer asked and who they are
- **Reply-to-message UX requires an existing message:** Without a proactive alert, there's no message for the human to reply to
- **Session-based throttling prevents spam:** If a customer sends 5 messages in 10 minutes, human receives 1 alert (not 5)

**Alternative rejected:** Reactive only — human must manually query "who is the AI talking to right now?" Rejected because:
- Adds friction (human must remember to check)
- No visibility into AI conversations (human doesn't know what they're missing)

---

### Decision 3: Takeover Gate Runs BEFORE Escalation Gate

**Choice:** Takeover gate is Step 2 in the pipeline (after inbound log, before escalation gate).

**Pipeline order:**
```
1. Log inbound
2. Takeover gate (if takeover_flag=True, forward to human, return)
3. Escalation gate (if escalation_flag=True, send holding reply, return)
4. Schedule gate (if outside AI hours, send auto-reply, return)
5. Agent runs
```

**Rationale:**
- **Takeover takes absolute priority:** If a human has explicitly taken over a conversation, they should receive ALL inbound messages — including messages that would otherwise trigger escalation or out-of-hours auto-replies
- **Prevents double-handling:** If takeover ran after escalation, an escalated customer who is also in takeover would receive a holding reply from the escalation gate (confusing — customer is talking to human, not waiting for human)

**Edge case handled:** Customer is escalated (`escalation_flag=True`) and then human takes over (`takeover_flag=True`). Current behavior:
1. Takeover gate runs first → forwards message to human, stops pipeline
2. Escalation gate never runs
3. Customer receives no AI reply (correct — human is handling)

**When takeover ends:** Human replies "done" → both `takeover_flag` and `escalation_flag` can be cleared simultaneously (see reset handler logic).

---

### Decision 4: Silent Drop (No AI Reply) During Takeover

**Choice:** When `takeover_flag=True`, the AI sends **no reply** to the customer (complete silence).

**Rationale:**
- Human agent is actively in the conversation — an AI holding reply would confuse the customer
- Customer sees a single, coherent conversation flow (no "a team member will get back to you" from AI when human is already replying)

**Contrast with escalation gate:** Escalation sends a holding reply ("A team member will get back to you today") because the human is NOT yet in the conversation. Takeover is different — human is already handling, no holding message needed.

---

### Decision 5: Auto-Resume Safety Timeout (APScheduler Job)

**Choice:** New APScheduler job runs every 30 minutes and clears `takeover_flag` for any customer where `takeover_at` is more than 4 hours ago.

**Configurable timeout:** Add `TAKEOVER_TIMEOUT_HOURS` env var (default: 4).

**Rationale:**
- **Fail-safe:** If human forgets to send "done" command, customer doesn't experience indefinite AI silence
- **Graceful degradation:** 4 hours is long enough for a complex conversation but short enough to recover from forgotten takeovers within a working day

**Notification:** When auto-resume triggers, send notification to `human_agent_number`:
```
⏰ AI auto-resumed for John Tan (+6591234567) after 4-hour timeout.
```

**Alternative rejected:** Rely on human to always send "done". Rejected because humans forget, and indefinite AI silence is a worse failure mode than premature auto-resume.

---

### Decision 6: Status Command for Human Agent Awareness

**Choice:** Human can send `//status` or `status` (standalone message, not a reply) to get a list of all active takeovers.

**Response format:**
```
Active takeovers (2):

1. John Tan (+6591234567)
   Taken over: 3 hours ago

2. Mary Lim (+6598765432)
   Taken over: 45 minutes ago

Reply "done" to any of their forwarded messages to release.
```

**Rationale:**
- **Human forgets who they're handling:** Especially at shift change or after a break
- **Prevents accidental indefinite takeovers:** Human sees the list, realizes they forgot to release a customer, replies "done"

**Alternative rejected:** No status command — human must check Supabase Studio. Rejected because we're building for non-technical operators.

---

### Decision 7: "done" Command Clears Both Takeover and Escalation

**Choice:** When human replies "done" to a customer message alert, the reset handler clears BOTH `takeover_flag` and `escalation_flag` (if set).

**Rationale:**
- **Human workflow simplicity:** If a customer was escalated and then taken over, the human resolves both states with one command (not two separate "done" commands)
- **State coherence:** A customer who is both escalated and taken over is effectively in one state: "human is handling". When human is done, both flags should clear.

**Implementation:** Update `reset_handler.py` to clear both flags in the same Supabase UPDATE.

---

## Database Changes

### Migration 013: Takeover Tracking Schema

**Target database:** Per-client Supabase (not shared config DB — this is customer-level state)

**Migration file:** `supabase/migrations/013_human_takeover.sql`

```sql
-- Migration 013: Human Takeover Detection
-- Adds takeover state tracking and audit trail for manual human agent takeovers.

-- ── Add takeover state columns to customers table ─────────────────────────────
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_flag BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_by TEXT DEFAULT NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_at TIMESTAMPTZ DEFAULT NULL;

-- ── Create takeover_tracking audit table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS takeover_tracking (
    id SERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    alert_msg_id TEXT,  -- wamid of the conversation alert sent to human_agent_number (NULL if alert send failed)
    takeover_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    takeover_by TEXT,  -- Phone number of human agent who initiated takeover (for audit)
    command_type TEXT NOT NULL,  -- 'reply_to_alert' or 'auto_timeout'
    released_at TIMESTAMPTZ DEFAULT NULL,
    released_by TEXT DEFAULT NULL,  -- Phone number of human agent who released (for audit)
    release_command_type TEXT DEFAULT NULL  -- 'manual_done' or 'auto_resume'
);

-- ── Indexes for takeover_tracking ─────────────────────────────────────────────
-- Fast lookup when human replies to an alert (by alert_msg_id)
CREATE INDEX IF NOT EXISTS idx_takeover_tracking_alert_msg_id 
    ON takeover_tracking(alert_msg_id) 
    WHERE released_at IS NULL;

-- Fast lookup of active takeovers for auto-resume job (by phone_number)
CREATE INDEX IF NOT EXISTS idx_takeover_tracking_phone_active 
    ON takeover_tracking(phone_number, takeover_at) 
    WHERE released_at IS NULL;

-- ── Index on customers table for takeover gate ────────────────────────────────
-- Fast lookup of customers with active takeover during message handling
CREATE INDEX IF NOT EXISTS idx_customers_takeover_flag 
    ON customers(phone_number) 
    WHERE takeover_flag = TRUE;

-- ── Add column comments for Supabase Studio ───────────────────────────────────
COMMENT ON COLUMN customers.takeover_flag IS 'TRUE if human agent has manually taken over this conversation. AI is paused until released.';
COMMENT ON COLUMN customers.takeover_by IS 'Phone number of human agent who initiated takeover.';
COMMENT ON COLUMN customers.takeover_at IS 'Timestamp when takeover was initiated.';

COMMENT ON TABLE takeover_tracking IS 'Audit trail for manual human agent takeovers. Tracks when human took over, when they released, and how (manual or timeout).';
COMMENT ON COLUMN takeover_tracking.alert_msg_id IS 'wamid of the conversation alert sent to human_agent_number. Used for reply-to-message takeover detection.';
COMMENT ON COLUMN takeover_tracking.command_type IS 'How takeover was initiated: reply_to_alert (human replied "take") or auto_timeout (reserved for future use).';
COMMENT ON COLUMN takeover_tracking.release_command_type IS 'How takeover was released: manual_done (human replied "done") or auto_resume (APScheduler timeout).';
```

**Safe to re-run:** All `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`.

**Rollback (if needed):**
```sql
DROP INDEX IF EXISTS idx_customers_takeover_flag;
DROP INDEX IF EXISTS idx_takeover_tracking_phone_active;
DROP INDEX IF EXISTS idx_takeover_tracking_alert_msg_id;
DROP TABLE IF EXISTS takeover_tracking;
ALTER TABLE customers DROP COLUMN IF EXISTS takeover_at;
ALTER TABLE customers DROP COLUMN IF EXISTS takeover_by;
ALTER TABLE customers DROP COLUMN IF EXISTS takeover_flag;
```

---

## Code Changes

### 1. `engine/api/webhook.py` — Store `last_ai_alert_msg_id` on `customers` Table

**Purpose:** Enable reply-to-message takeover detection. When human replies "take" to an alert, the engine looks up which customer that alert was about.

**Schema change required (add to migration 013):**

```sql
-- Add to migration 013 after the takeover_flag columns
ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_ai_alert_msg_id TEXT DEFAULT NULL;

COMMENT ON COLUMN customers.last_ai_alert_msg_id IS 'wamid of the most recent conversation alert sent to human_agent_number for this customer. Used for reply-to-message takeover detection.';
```

**No code changes in webhook.py.** The `last_ai_alert_msg_id` is updated in `message_handler.py` after sending the conversation alert (see below).

---

### 2. `engine/core/message_handler.py` — Add Takeover Gate and Conversation Alerts

**File:** `engine/core/message_handler.py`  
**Change type:** Insert takeover gate (Step 2), add conversation alert logic (after agent runs)

**Updated pipeline order:**

```python
async def handle_inbound_message(...):
    # Step 1: Load client config + DB connection
    # Step 1b: Human agent routing (if phone_number == human_agent_number)
    # Step 2: Log inbound
    
    # ── NEW Step 3: Takeover gate ─────────────────────────────────────────────
    if customer_row and customer_row.get("takeover_flag") is True:
        await _handle_takeover_inbound(
            db=db,
            client_config=client_config,
            phone_number=phone_number,
            display_name=display_name,
            message_text=message_text,
        )
        return  # Stop pipeline — AI does NOT run
    
    # Step 4: Escalation gate (existing)
    # Step 5: Schedule gate (Task 2)
    # Step 6: Upsert customer
    # Step 7: Opt-out gate
    # Step 8: Agent runs
    
    # ── NEW Step 9: Send conversation alert (if AI handled successfully) ──────
    # Only send if this is a NEW conversation session (no alert sent in last 4 hours)
    await _maybe_send_conversation_alert(
        db=db,
        client_config=client_config,
        phone_number=phone_number,
        display_name=display_name,
        message_text=message_text,
    )
    
    # Step 10: Send reply, log outbound (existing)
```

**New helper function 1: `_handle_takeover_inbound()`**

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
    # Message is already logged to interactions_log (Step 2 in pipeline)
```

**New helper function 2: `_maybe_send_conversation_alert()`**

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
    
    Steps:
    1. Check interactions_log for this customer's last inbound message
    2. If last inbound was >4 hours ago (or no history), send alert
    3. Store alert wamid in customers.last_ai_alert_msg_id for takeover detection
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

---

### 3. `engine/core/reset_handler.py` — Add Takeover Command Detection

**File:** `engine/core/reset_handler.py`  
**Function:** `handle_human_agent_message()`  
**Change type:** Extend to detect takeover commands ("take") and release commands ("done")

**Current behavior:** Handles escalation reset only ("done", "resolved", etc.)

**New behavior:** Also handles:
- Takeover command: "take", "mine", "me", "takeover" → reply-to-message must match a `last_ai_alert_msg_id`
- Release command: "done", "resolved", etc. → clears both `escalation_flag` AND `takeover_flag` if customer has both

**Updated keyword sets:**

```python
# Existing escalation reset keywords (keep as-is)
RESET_KEYWORDS = frozenset([
    "done", "resolved", "ok", "handled", "fixed", "cleared",
    "completed", "closed", "finish", "finished", "okay"
])

# New takeover command keywords
TAKEOVER_KEYWORDS = frozenset([
    "take", "mine", "me", "takeover", "i'll handle", "ill handle", "take over"
])
```

**New logic in `handle_human_agent_message()`:**

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
        # (clears both flags if present)
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

**New helper function 1: `_handle_takeover_command()`**

```python
async def _handle_takeover_command(
    db,
    client_config,
    phone_number: str,
    context_message_id: str,
) -> None:
    """
    Handle takeover command ("take") from human agent.
    
    Steps:
    1. Look up customer by last_ai_alert_msg_id = context_message_id
    2. Set takeover_flag=TRUE
    3. Log to takeover_tracking
    4. Send confirmation to human agent
    """
    from datetime import datetime, timezone
    from engine.integrations.meta_whatsapp import send_message
    
    # Query customers table for matching alert
    try:
        result = await (
            db.table("customers")
            .select("phone_number, customer_name, takeover_flag")
            .eq("last_ai_alert_msg_id", context_message_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error(
            f"Failed to query customer by alert_msg_id={context_message_id}: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "⚠️ Failed to take over — please try again.",
            )
        except Exception:
            pass
        return
    
    if not result.data:
        # No matching alert found
        try:
            await send_message(
                client_config,
                phone_number,
                "No active conversation found for this alert. It may have been too long ago.",
            )
        except Exception:
            pass
        return
    
    customer_row = result.data[0]
    customer_phone = customer_row["phone_number"]
    customer_name = customer_row.get("customer_name", customer_phone)
    already_taken = customer_row.get("takeover_flag", False)
    
    if already_taken:
        # Already in takeover mode
        try:
            await send_message(
                client_config,
                phone_number,
                f"✅ {customer_name} is already in your takeover. AI is paused.",
            )
        except Exception:
            pass
        return
    
    # Set takeover flag
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.table("customers").update({
            "takeover_flag": True,
            "takeover_by": phone_number,
            "takeover_at": now,
        }).eq("phone_number", customer_phone).execute()
        
        logger.info(
            f"Takeover initiated for {customer_phone} by {phone_number} "
            f"(client: {client_config.client_id})"
        )
    except Exception as e:
        logger.error(
            f"Failed to set takeover_flag for {customer_phone}: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "⚠️ Failed to set takeover — please try again.",
            )
        except Exception:
            pass
        return
    
    # Log to takeover_tracking
    try:
        await db.table("takeover_tracking").insert({
            "phone_number": customer_phone,
            "alert_msg_id": context_message_id,
            "takeover_by": phone_number,
            "command_type": "reply_to_alert",
        }).execute()
    except Exception as e:
        logger.error(
            f"Failed to log takeover_tracking for {customer_phone}: {e}",
            exc_info=True,
        )
        # Non-fatal — takeover flag is already set
    
    # Send confirmation
    confirmation = (
        f"✅ Taking over *{customer_name}*. AI paused.\n\n"
        f"Reply \"done\" to this thread when finished."
    )
    try:
        await send_message(client_config, phone_number, confirmation)
    except Exception as e:
        logger.error(
            f"Failed to send takeover confirmation to {phone_number}: {e}",
            exc_info=True,
        )
```

**New helper function 2: `_handle_release_command()`**

```python
async def _handle_release_command(
    db,
    client_config,
    phone_number: str,
    context_message_id: str,
) -> None:
    """
    Handle release command ("done") from human agent.
    
    Clears BOTH escalation_flag AND takeover_flag (if present).
    
    Lookup priority:
    1. Look up by last_ai_alert_msg_id (takeover case)
    2. Fall back to escalation_tracking.alert_msg_id (escalation case)
    """
    from datetime import datetime, timezone
    from engine.integrations.meta_whatsapp import send_message
    from engine.integrations.google_sheets import sync_customer_to_sheets
    import asyncio
    
    # Try takeover lookup first
    try:
        result = await (
            db.table("customers")
            .select("phone_number, customer_name, takeover_flag, escalation_flag")
            .eq("last_ai_alert_msg_id", context_message_id)
            .limit(1)
            .execute()
        )
        
        if result.data:
            customer_row = result.data[0]
            customer_phone = customer_row["phone_number"]
            customer_name = customer_row.get("customer_name", customer_phone)
            had_takeover = customer_row.get("takeover_flag", False)
            had_escalation = customer_row.get("escalation_flag", False)
            
            # Clear both flags
            now = datetime.now(timezone.utc).isoformat()
            await db.table("customers").update({
                "takeover_flag": False,
                "takeover_by": None,
                "takeover_at": None,
                "escalation_flag": False,
                "escalation_notified": False,
                "escalation_reason": None,
            }).eq("phone_number", customer_phone).execute()
            
            # Log release to takeover_tracking
            if had_takeover:
                try:
                    await db.table("takeover_tracking").update({
                        "released_at": now,
                        "released_by": phone_number,
                        "release_command_type": "manual_done",
                    }).eq("phone_number", customer_phone).is_("released_at", "null").execute()
                except Exception as e:
                    logger.error(
                        f"Failed to log takeover release for {customer_phone}: {e}",
                        exc_info=True,
                    )
            
            # Log release to escalation_tracking
            if had_escalation:
                try:
                    await db.table("escalation_tracking").update({
                        "resolved_at": now,
                        "resolved_by": phone_number,
                    }).eq("phone_number", customer_phone).is_("resolved_at", "null").execute()
                except Exception as e:
                    logger.error(
                        f"Failed to log escalation resolution for {customer_phone}: {e}",
                        exc_info=True,
                    )
            
            # Sync to Sheets
            try:
                row_result = await db.table("customers").select("*").eq("phone_number", customer_phone).limit(1).execute()
                if row_result.data:
                    asyncio.create_task(sync_customer_to_sheets(
                        client_id=client_config.client_id,
                        client_config=client_config,
                        customer_data=row_result.data[0],
                    ))
            except Exception:
                pass
            
            # Send confirmation
            flags_cleared = []
            if had_takeover:
                flags_cleared.append("takeover")
            if had_escalation:
                flags_cleared.append("escalation")
            
            if flags_cleared:
                confirmation = f"✅ AI resumed for *{customer_name}* ({' + '.join(flags_cleared)} cleared)."
            else:
                confirmation = f"✅ AI resumed for *{customer_name}*."
            
            try:
                await send_message(client_config, phone_number, confirmation)
            except Exception:
                pass
            
            logger.info(
                f"Release command processed for {customer_phone} by {phone_number} "
                f"(cleared: {', '.join(flags_cleared) if flags_cleared else 'none'})"
            )
            return
    except Exception as e:
        logger.error(
            f"Failed takeover lookup for context_message_id={context_message_id}: {e}",
            exc_info=True,
        )
    
    # Fall back to escalation lookup (existing escalation reset logic)
    # [Use existing escalation reset logic from reset_handler.py — not duplicated here]
    # This path handles cases where human replies "done" to an old escalation alert
    # (not a takeover alert)
```

**New helper function 3: `_handle_status_command()`**

```python
async def _handle_status_command(
    db,
    client_config,
    phone_number: str,
) -> None:
    """
    Handle //status command from human agent.
    
    Returns a list of all customers with active takeover flags.
    """
    from datetime import datetime, timezone
    from engine.integrations.meta_whatsapp import send_message
    
    try:
        result = await (
            db.table("customers")
            .select("phone_number, customer_name, takeover_at")
            .eq("takeover_flag", True)
            .order("takeover_at", desc=True)
            .execute()
        )
    except Exception as e:
        logger.error(
            f"Failed to query active takeovers: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "⚠️ Failed to fetch takeover status — please try again.",
            )
        except Exception:
            pass
        return
    
    if not result.data:
        # No active takeovers
        try:
            await send_message(
                client_config,
                phone_number,
                "No active takeovers. All conversations are handled by AI.",
            )
        except Exception:
            pass
        return
    
    # Format response
    now = datetime.now(timezone.utc)
    lines = [f"Active takeovers ({len(result.data)}):"]
    
    for i, row in enumerate(result.data, start=1):
        customer_name = row.get("customer_name", row["phone_number"])
        takeover_at_str = row.get("takeover_at")
        
        if takeover_at_str:
            takeover_at = datetime.fromisoformat(takeover_at_str.replace("Z", "+00:00"))
            duration = now - takeover_at
            hours_ago = int(duration.total_seconds() / 3600)
            minutes_ago = int((duration.total_seconds() % 3600) / 60)
            
            if hours_ago > 0:
                time_str = f"{hours_ago} hour{'s' if hours_ago > 1 else ''} ago"
            else:
                time_str = f"{minutes_ago} minute{'s' if minutes_ago > 1 else ''} ago"
        else:
            time_str = "unknown"
        
        lines.append(f"\n{i}. {customer_name} (+{row['phone_number']})")
        lines.append(f"   Taken over: {time_str}")
    
    lines.append("\n\nReply \"done\" to any of their forwarded messages to release.")
    
    status_text = "\n".join(lines)
    
    try:
        await send_message(client_config, phone_number, status_text)
    except Exception as e:
        logger.error(
            f"Failed to send status response to {phone_number}: {e}",
            exc_info=True,
        )
```

---

### 4. New File: `engine/core/takeover_auto_resume.py` — APScheduler Job

**File:** `engine/core/takeover_auto_resume.py` (new file)  
**Purpose:** Auto-resume stale takeovers after timeout

```python
"""
Auto-resume job for human takeover timeout.

Runs every 30 minutes via APScheduler (registered in webhook.py lifespan).
Clears takeover_flag for any customer where takeover_at is older than the configured timeout.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from engine.config.client_config import get_all_active_clients
from engine.integrations.supabase_client import get_client_db
from engine.integrations.meta_whatsapp import send_message
from engine.config.settings import get_settings

logger = logging.getLogger(__name__)

# Default timeout: 4 hours
# Override with TAKEOVER_TIMEOUT_HOURS env var
DEFAULT_TIMEOUT_HOURS = 4


async def run_takeover_auto_resume() -> None:
    """
    Auto-resume job — clears stale takeover flags.
    
    For each active client:
    1. Query customers where takeover_flag=True and takeover_at < (now - timeout)
    2. Clear takeover_flag, takeover_by, takeover_at
    3. Log release to takeover_tracking
    4. Send notification to human_agent_number
    """
    settings = get_settings()
    timeout_hours = getattr(settings, "takeover_timeout_hours", DEFAULT_TIMEOUT_HOURS)
    
    logger.info(f"Takeover auto-resume job starting (timeout: {timeout_hours}h)")
    
    # Get all active clients
    try:
        clients = await get_all_active_clients()
    except Exception as e:
        logger.error(f"Failed to load active clients for takeover auto-resume: {e}", exc_info=True)
        return
    
    for client_config in clients:
        try:
            await _auto_resume_for_client(client_config, timeout_hours)
        except Exception as e:
            logger.error(
                f"Takeover auto-resume failed for client {client_config.client_id}: {e}",
                exc_info=True,
            )
            # Continue to next client — don't let one failure block others


async def _auto_resume_for_client(client_config, timeout_hours: int) -> None:
    """Auto-resume stale takeovers for one client."""
    db = await get_client_db(client_config.client_id)
    
    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=timeout_hours)).isoformat()
    
    # Query stale takeovers
    try:
        result = await (
            db.table("customers")
            .select("phone_number, customer_name, takeover_at")
            .eq("takeover_flag", True)
            .lt("takeover_at", cutoff_time)
            .execute()
        )
    except Exception as e:
        logger.error(
            f"Failed to query stale takeovers for {client_config.client_id}: {e}",
            exc_info=True,
        )
        return
    
    if not result.data:
        # No stale takeovers
        logger.debug(f"No stale takeovers for {client_config.client_id}")
        return
    
    now = datetime.now(timezone.utc).isoformat()
    
    for row in result.data:
        customer_phone = row["phone_number"]
        customer_name = row.get("customer_name", customer_phone)
        
        try:
            # Clear takeover flag
            await db.table("customers").update({
                "takeover_flag": False,
                "takeover_by": None,
                "takeover_at": None,
            }).eq("phone_number", customer_phone).execute()
            
            # Log release to takeover_tracking
            await db.table("takeover_tracking").update({
                "released_at": now,
                "release_command_type": "auto_resume",
            }).eq("phone_number", customer_phone).is_("released_at", "null").execute()
            
            logger.info(
                f"Auto-resumed takeover for {customer_phone} (client: {client_config.client_id}) "
                f"after {timeout_hours}h timeout"
            )
            
            # Send notification to human agent
            if client_config.human_agent_number:
                notification = (
                    f"⏰ AI auto-resumed for *{customer_name}* (+{customer_phone}) "
                    f"after {timeout_hours}-hour timeout."
                )
                try:
                    await send_message(client_config, client_config.human_agent_number, notification)
                except Exception as e:
                    logger.error(
                        f"Failed to send auto-resume notification to {client_config.human_agent_number}: {e}",
                        exc_info=True,
                    )
        
        except Exception as e:
            logger.error(
                f"Failed to auto-resume takeover for {customer_phone}: {e}",
                exc_info=True,
            )
            # Continue to next customer
```

---

### 5. `engine/api/webhook.py` — Register Auto-Resume Job

**File:** `engine/api/webhook.py`  
**Function:** `lifespan()`  
**Change type:** Add takeover auto-resume job to APScheduler

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager — starts/stops APScheduler.
    
    Starts two jobs:
    1. Follow-up scheduler (existing)
    2. Takeover auto-resume (new)
    """
    from engine.core.takeover_auto_resume import run_takeover_auto_resume
    
    scheduler = AsyncIOScheduler()
    interval_minutes = get_settings().scheduler_interval_minutes
    
    # Job 1: Follow-up scheduler (existing)
    scheduler.add_job(
        run_followup_scheduler,
        trigger="interval",
        minutes=interval_minutes,
        id="followup_scheduler",
        replace_existing=True,
    )
    
    # Job 2: Takeover auto-resume (new)
    scheduler.add_job(
        run_takeover_auto_resume,
        trigger="interval",
        minutes=30,  # Run every 30 minutes
        id="takeover_auto_resume",
        replace_existing=True,
    )
    
    scheduler.start()
    logger.info(
        f"Scheduler started: followup={interval_minutes}min, takeover_auto_resume=30min"
    )
    yield
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
```

---

### 6. `engine/config/settings.py` — Add Takeover Timeout Env Var

**File:** `engine/config/settings.py`  
**Change type:** Add optional env var for takeover timeout

```python
class Settings(BaseSettings):
    # ... existing fields ...
    
    # Takeover auto-resume timeout (hours)
    takeover_timeout_hours: int = 4
    
    # ... rest of settings ...
```

---

### 7. `engine/config/client_config.py` — Add `get_all_active_clients()` Helper

**File:** `engine/config/client_config.py`  
**Change type:** Add new function for auto-resume job

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
                f"Failed to parse client config for {row.get('client_id')}: {e}",
                exc_info=True,
            )
            # Skip this client, continue to next
    
    return configs
```

---

## Pipeline Integration

**Final pipeline order (with all three features):**

```
1. Load client config + DB connection
2. Human agent routing (if phone_number == human_agent_number)
3. Log inbound to interactions_log
4. Query customer record from customers table
5. TAKEOVER GATE (NEW — Task 3) — if takeover_flag=True, forward to human, return
6. Escalation gate — if escalation_flag=True, send holding reply (once), then silent drop
7. Schedule gate (Task 2) — if outside AI operational hours, send auto-reply, return
8. Upsert customer record (INSERT new or UPDATE last_seen)
9. Opt-out detection gate (if opt-out keyword + active pending booking, mark opted_out, return)
10. Acquire per-customer lock (serialize concurrent messages from same customer)
11. Context builder → agent runner → tool loop
12. Send reply, log outbound
13. CONVERSATION ALERT (NEW — Task 3) — send proactive alert to human_agent_number (once per session)
```

**Key ordering decisions:**

1. **Takeover runs before escalation** — If a customer is both escalated and in takeover, takeover takes priority (human is handling, no holding reply needed)
2. **Takeover runs before schedule** — If AI is outside hours but human took over, forward to human (no out-of-hours auto-reply)
3. **Conversation alert runs after agent** — Only send alert if AI successfully handled the message (don't alert if agent errored out)

---

## Cross-Feature Dependencies

### Dependency 1: Escalation Reset (Existing Feature)

**Integration point:** "done" command clears BOTH `escalation_flag` AND `takeover_flag`.

**Implementation:** Update `reset_handler.py` to clear both flags in the same Supabase UPDATE (see Code Changes section 3 above).

**No breaking changes.** Existing escalation reset logic is preserved — if customer is only escalated (not in takeover), "done" still works as before.

---

### Dependency 2: AI Schedule & Business Hours (Task 2)

**Integration point:** Pipeline order — takeover gate runs BEFORE schedule gate.

**Rationale:** If a human has taken over a conversation, they should receive messages 24/7 (regardless of AI operational hours).

**Edge case:** Customer is in takeover mode AND message arrives outside AI hours. Current behavior:
1. Takeover gate runs first (Step 5) → forwards to human, returns
2. Schedule gate never runs (pipeline returned early)
3. Customer does NOT receive out-of-hours auto-reply (correct — human is handling)

---

### Dependency 3: Immediate Escalation (Task 1)

**No direct dependency.** Escalation and takeover are independent workflows:
- Escalation = AI-triggered (AI detects it cannot help)
- Takeover = Human-triggered (human proactively decides to handle)

**Edge case:** Customer asks an unanswerable question → AI escalates → conversation alert is sent → human sees alert, replies "take" → human is now handling, AI remains silent. Both flags are set (`escalation_flag=True`, `takeover_flag=True`). Human replies "done" → both flags clear.

---

## Open Questions Resolved

### OQ-HT-001: Echo Webhook Availability (CRITICAL — must resolve first)

**Resolution:** Echo webhooks are **NOT AVAILABLE**. Meta Cloud API delivers STATUS webhooks (sent/delivered/read) for business-initiated messages, not message echo webhooks. Status webhooks do NOT contain message content or sender context.

**Implementation path:** Use **Option B (reply-to-forwarded-message)**.

See [Critical Pre-Implementation Research](#critical-pre-implementation-research) above for full details.

---

### OQ-HT-002: Should takeover auto-resume timeout be configurable per client?

**Resolution:** Fixed at 4 hours platform-wide for Phase 1 (override with `TAKEOVER_TIMEOUT_HOURS` env var). Make per-client configurable if requested.

**Rationale:**
- 4 hours is a reasonable default for most service SMEs (covers a full morning or afternoon shift)
- Adding a per-client config column now increases complexity without validated need
- If a client requests a different timeout (e.g., 8 hours for overnight takeovers), add a `takeover_timeout_hours INTEGER` column to `clients` table

**Migration path:** Add `takeover_timeout_hours` column to shared `clients` table, load in `ClientConfig`, pass to auto-resume job.

---

### OQ-HT-003: Should conversation alerts be sent via Telegram instead of WhatsApp?

**Resolution:** WhatsApp for Phase 1 (sent to `human_agent_number`). Telegram alerts can be added in Phase 2 if requested.

**Rationale:**
- HeyAircon human agent already monitors `human_agent_number` for escalation alerts — same channel for takeover alerts
- No additional integration complexity (Telegram bot setup, chat ID management)
- WhatsApp reply-to-message UX is familiar (same as escalation reset)

**Migration path:** If human agent reports alert fatigue (too many WhatsApp notifications), implement Telegram alerts with batching (1 notification per 5 new conversations).

---

### OQ-HT-004: Should "take" command work on any AI alert, or only recent ones?

**Resolution:** Any alert. No time restriction on takeover commands.

**Rationale:**
- Human may want to take over a conversation from 2 hours ago (customer went silent, then returns)
- Time restriction adds complexity (must track alert timestamps, decide cutoff)
- If alert is stale, takeover still works — human just takes over a conversation that may have already ended (harmless)

**Edge case handled:** Human replies "take" to a very old alert (days ago). Takeover flag is set. If customer hasn't messaged in days, takeover may sit idle until customer returns. Auto-resume timeout (4 hours) will eventually clear it.

---

## Implementation Notes for sdet-engineer

### Test Scenarios

#### TS-HT-01: Human takes over via reply-to-alert
- **Given:** AI handles a customer message, sends conversation alert to `human_agent_number`
- **When:** Human agent replies "take" to that alert
- **Then:** `takeover_flag=True` set for that customer
- **And:** Human receives confirmation: "✅ Taking over John Tan. AI paused."
- **And:** Takeover logged to `takeover_tracking` with `command_type='reply_to_alert'`

#### TS-HT-02: AI pauses after takeover
- **Given:** Customer has `takeover_flag=True`
- **When:** Customer sends a new message
- **Then:** Takeover gate blocks (Step 5)
- **And:** Message is forwarded to `human_agent_number`: "📥 John Tan just replied: ..."
- **And:** Agent does NOT run (no AI reply sent to customer)
- **And:** Inbound message is logged to `interactions_log`

#### TS-HT-03: Human releases takeover via "done"
- **Given:** Customer has `takeover_flag=True`
- **When:** Human agent replies "done" to a forwarded message (or conversation alert)
- **Then:** `takeover_flag=False` set for that customer
- **And:** Human receives confirmation: "✅ AI resumed for John Tan (takeover cleared)."
- **And:** Release logged to `takeover_tracking` with `released_at`, `release_command_type='manual_done'`

#### TS-HT-04: Auto-resume timeout clears stale takeover
- **Given:** Customer has `takeover_flag=True` and `takeover_at` is 5 hours ago (timeout = 4 hours)
- **When:** Auto-resume job runs (every 30 minutes)
- **Then:** `takeover_flag=False` set for that customer
- **And:** Human receives notification: "⏰ AI auto-resumed for John Tan after 4-hour timeout."
- **And:** Release logged to `takeover_tracking` with `release_command_type='auto_resume'`

#### TS-HT-05: Status command lists active takeovers
- **Given:** Two customers have `takeover_flag=True` (John Tan, Mary Lim)
- **When:** Human agent sends "//status"
- **Then:** Human receives list:
  ```
  Active takeovers (2):
  
  1. John Tan (+6591234567)
     Taken over: 3 hours ago
  
  2. Mary Lim (+6598765432)
     Taken over: 45 minutes ago
  
  Reply "done" to any of their forwarded messages to release.
  ```

#### TS-HT-06: Conversation alert sent once per session
- **Given:** Customer sends 3 messages in 10 minutes
- **When:** AI handles all 3 messages
- **Then:** Conversation alert is sent to `human_agent_number` for the FIRST message only
- **And:** No alert sent for messages 2 and 3 (session still active, <4 hours since last inbound)

#### TS-HT-07: Takeover + escalation (both flags set)
- **Given:** Customer is escalated (`escalation_flag=True`) and then taken over (`takeover_flag=True`)
- **When:** Human replies "done"
- **Then:** BOTH flags are cleared (`takeover_flag=False`, `escalation_flag=False`)
- **And:** Human receives confirmation: "✅ AI resumed for John Tan (takeover + escalation cleared)."
- **And:** Both `takeover_tracking` and `escalation_tracking` are updated with release timestamps

#### TS-HT-08: Takeover gate runs before escalation gate
- **Given:** Customer has `takeover_flag=True` and `escalation_flag=True`
- **When:** Customer sends a new message
- **Then:** Takeover gate runs first (Step 5) → forwards to human, returns
- **And:** Escalation gate does NOT run (pipeline returned early)
- **And:** Customer receives no AI reply (no holding message)

#### TS-HT-09: Takeover gate runs before schedule gate
- **Given:** Customer has `takeover_flag=True` and message arrives outside AI operational hours
- **When:** Customer sends a message
- **Then:** Takeover gate runs first (Step 5) → forwards to human, returns
- **And:** Schedule gate does NOT run
- **And:** Customer receives no out-of-hours auto-reply

#### TS-HT-10: Invalid takeover command (no reply-to-message)
- **Given:** Human sends "take" as a standalone message (not a reply)
- **When:** Reset handler processes the message
- **Then:** Human receives help message:
  ```
  To take over a conversation: Reply "take" to an AI alert.
  To release a conversation: Reply "done" to a customer message.
  To see active takeovers: Send "//status".
  ```

---

### Edge Cases to Verify

1. **Alert send failure** — If conversation alert send fails (Meta API error), `last_ai_alert_msg_id` is NULL. Human cannot take over via reply-to-message for that customer (would need to use Supabase Studio to manually set `takeover_flag=True`). Acceptable failure mode.
2. **Stale alert (>4 hours old)** — Human replies "take" to a very old alert. Takeover flag is set. If customer hasn't messaged recently, takeover may sit idle. Auto-resume timeout (4 hours from `takeover_at`) will eventually clear it.
3. **Multiple humans reply "take" to the same alert** — First reply wins (sets `takeover_flag=True`). Second reply gets "already in your takeover" confirmation (takeover_flag is idempotent).
4. **Human replies "take" to a customer who is escalated** — Both flags are set (`takeover_flag=True`, `escalation_flag=True`). Takeover gate runs first, escalation gate is skipped. Single "done" command clears both.
5. **Auto-resume during active conversation** — Customer is taken over, human forgets to release, 4-hour timeout triggers, customer sends a new message 5 minutes later → AI responds (takeover was auto-released). Human receives timeout notification.

---

### Verification Checklist

- [ ] Migration 013 applied to per-client Supabase (3 new columns on `customers` table, new `takeover_tracking` table)
- [ ] `takeover_flag`, `takeover_by`, `takeover_at` columns added to `customers` table
- [ ] `last_ai_alert_msg_id` column added to `customers` table
- [ ] `takeover_tracking` table created with indexes
- [ ] Takeover gate added to `message_handler.py` (Step 5, before escalation gate)
- [ ] Conversation alert logic added to `message_handler.py` (after agent runs)
- [ ] `_handle_takeover_inbound()` function added
- [ ] `_maybe_send_conversation_alert()` function added
- [ ] `reset_handler.py` updated with takeover command detection ("take")
- [ ] `reset_handler.py` updated to clear both takeover and escalation flags on "done"
- [ ] `_handle_takeover_command()` function added
- [ ] `_handle_release_command()` function updated
- [ ] `_handle_status_command()` function added
- [ ] `takeover_auto_resume.py` created
- [ ] Auto-resume job registered in `webhook.py` lifespan
- [ ] `TAKEOVER_TIMEOUT_HOURS` env var added to `settings.py`
- [ ] `get_all_active_clients()` helper added to `client_config.py`
- [ ] All 10 test scenarios pass
- [ ] Edge cases handled gracefully (no crashes, appropriate fallback behavior)
- [ ] Conversation alerts are session-throttled (<1 alert per customer per 4 hours)
- [ ] Status command returns accurate list of active takeovers
- [ ] Auto-resume job clears stale takeovers and sends notifications

---

### Performance Targets

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Takeover gate latency | <5ms per message | Time takeover lookup in prod logs |
| Conversation alert delivery rate | >99% | Count AI-handled messages vs. logged alerts |
| Auto-resume job execution time | <30s per run (all clients) | Log job start/end timestamps |
| False takeover rate (alert mis-clicked) | <1% | Manual review — human accidentally replies "take" when they didn't mean to |

---

**End of Human Takeover Detection Architecture Specification**
