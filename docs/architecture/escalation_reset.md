# Escalation Reset via WhatsApp Reply-to-Message

> **Architecture Decision Record & Implementation Specification**  
> Author: @software-architect  
> Date: 2026-04-22  
> Status: Approved for implementation

---

## Table of Contents

1. [Architecture Decision Record (ADR)](#architecture-decision-record-adr)
2. [File-by-File Change Specification](#file-by-file-change-specification)
3. [Data Flow Diagram](#data-flow-diagram)
4. [SQL Migration](#sql-migration)
5. [Caller Audit for `send_message()` Return Type Change](#caller-audit-for-send_message-return-type-change)
6. [Implementation Checklist](#implementation-checklist)

---

## Architecture Decision Record (ADR)

### Problem Statement

**Current state:**  
When the agent escalates a customer (`escalation_flag=True`), the agent is silenced for all subsequent messages from that customer until a human manually clears the flag in Supabase Studio. There is no programmatic reset mechanism.

**Operational pain:**  
Human agents receive an escalation alert on WhatsApp but have no way to confirm resolution and re-enable the AI agent without direct database access. This creates friction for non-technical operators and increases the time customers wait before the AI can resume handling their messages.

**Business requirement:**  
Human agents must be able to **clear an escalation by replying directly to the escalation alert message** using a simple keyword (e.g., "done", "resolved"). The reset must be instant, require no technical knowledge, and leave an audit trail.

### Decision

Implement a WhatsApp reply-to-message detection mechanism that:

1. **Tracks escalation alerts** — when the agent escalates, record the `wamid` (WhatsApp message ID) of the alert sent to the human agent in a new `escalation_tracking` table.
2. **Detects reply-to-message gestures** — extract `message.context.id` from the Meta webhook payload (this is the `wamid` of the message being replied to).
3. **Matches alert + keyword** — when a message from `human_agent_number` contains a `context.id` matching a known `alert_msg_id`, check if the message body matches one of the approved reset keywords.
4. **Clears the escalation flag** — if keyword matches, set `escalation_flag=FALSE`, log the resolution, and send a confirmation to the human agent.
5. **Provides help messages** — if the human agent replies with an invalid keyword or sends a message without replying to an alert, send a help message listing the valid keywords.

**Approved reset keywords (case-insensitive, full message text after strip):**  
`done`, `resolved`, `resolve`, `fixed`, `handled`, `cleared`, `clear`, `completed`, `complete`, `closed`, `close`, `ok`, `okay`

### Why This Design

#### Alternative 1: SMS or email-based reset
- **Rejected:** Adds external dependencies (Twilio, email provider) and increases complexity. WhatsApp is already the customer engagement channel — keeping human agent commands in the same channel reduces cognitive load.

#### Alternative 2: Web dashboard reset button
- **Rejected:** Requires building a CRM dashboard (Phase 2). Human agents need to reset escalations **now** (Phase 1). This is the MVP path.

#### Alternative 3: Any message from human agent clears escalation
- **Rejected:** Too brittle. Human agents may send messages to the customer's number for other reasons (e.g., follow-up questions, status updates). Requiring reply-to-message ensures the reset command is explicitly tied to the escalation alert, reducing false positives.

#### Alternative 4: Agent decides when to clear escalation
- **Rejected:** Violates the hard rule that the escalation gate is programmatic, not an agent decision. The agent must never be in a position to self-clear an escalation — this prevents prompt injection and maintains auditability.

#### Alternative 5: Return `wamid` in `send_message()` response object instead of as return value
- **Considered:** Could wrap the result in a dict (`{"success": True, "wamid": "..."}`) or a dataclass. **Rejected** for two reasons:
  1. **Minimalism:** The return type change from `bool` to `Optional[str]` is backward-compatible with all existing callers (non-empty string is truthy, `None` is falsy). No caller changes required.
  2. **Semantic clarity:** The `wamid` is the primary result of a successful send. Returning it directly makes the function signature self-documenting.

### Consequences

#### Positive

1. **Zero external dependencies** — uses Meta's native reply-to-message feature (`message.context.id`).
2. **Low operator friction** — human agents use the same WhatsApp interface they already use. No login, no URL, no dashboard.
3. **Audit trail** — `escalation_tracking` records who cleared the escalation and when (`resolved_by`, `resolved_at`).
4. **Graceful degradation** — if the alert send fails (Meta API error), `alert_msg_id` is `NULL` and the reset mechanism simply doesn't work for that escalation. Human agents can still clear the flag manually in Supabase Studio. System does not crash.
5. **No LLM tokens used** — the reset handler is pure business logic. No Claude call, no agent loop, no token cost.

#### Negative

1. **New table** — adds `escalation_tracking` to the per-client Supabase schema. Increases data model complexity.
2. **Return type change in `send_message()`** — all callers must be audited to ensure they handle `Optional[str]` correctly. Most callers only check truthiness (`if result:`) so no breaking changes expected, but explicit audit is required.
3. **Keyword brittleness** — if a human agent replies with "ok thanks" instead of "ok", the keyword match fails. Mitigated by sending a help message listing valid keywords.
4. **No multi-language support** — keywords are English-only. Acceptable for Singapore (English + Singlish). If client base expands to non-English markets, keywords must be localized per `client_id`.

#### Risks

| Risk | Mitigation |
|------|-----------|
| Human agent replies to the wrong alert message | Reset only clears escalations where `resolved_at IS NULL`. Already-resolved escalations are ignored. If an old alert is replied to, the system sends "No pending escalation found." |
| `alert_msg_id` is `NULL` because alert send failed | Human agent receives no alert, so they have no message to reply to. They must clear the flag manually in Supabase Studio. This is acceptable — alert send failure is already a logged error. |
| Keyword collision with legitimate messages | Extremely low probability — human agents are trained to reply directly to alerts, not to send standalone messages to the customer number. If a collision occurs, the system sends a confirmation ("✅ Escalation cleared for ...") which makes the action visible. |
| Human agent deletes the alert message | Reply-to-message requires the original message to exist in WhatsApp's message history. If deleted, the reply context is lost. Human agent must use Supabase Studio. This is acceptable — message deletion is rare and outside system control. |

---

## File-by-File Change Specification

### 1. New Supabase Table: `escalation_tracking`

**Location:** Per-client Supabase database (not shared config DB).

**Purpose:** Audit trail for all escalations — tracks when an escalation was triggered, what alert was sent, and when/by-whom it was resolved.

**Schema:**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `SERIAL` | `PRIMARY KEY` | Auto-incrementing ID. |
| `phone_number` | `TEXT` | `NOT NULL` | Escalated customer phone number (E.164 without +). |
| `alert_msg_id` | `TEXT` | — | `wamid` of the escalation alert sent to `human_agent_number`. `NULL` if `send_message()` failed. |
| `escalated_at` | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT NOW()` | When the escalation was triggered. |
| `escalation_reason` | `TEXT` | — | Free-text reason provided by Claude via `escalate_to_human(reason=...)`. |
| `resolved_at` | `TIMESTAMPTZ` | — | When the escalation was cleared. `NULL` = pending. |
| `resolved_by` | `TEXT` | — | Phone number of the human agent who cleared the escalation (for audit). `NULL` until resolved. |

**Indexes:**

```sql
CREATE INDEX idx_escalation_tracking_alert_msg_id 
  ON escalation_tracking(alert_msg_id) 
  WHERE resolved_at IS NULL;
```

**Rationale:**  
- `alert_msg_id` is the lookup key when a human agent replies to an alert. The partial index (`WHERE resolved_at IS NULL`) keeps the index small and fast — resolved escalations are never queried by `alert_msg_id`.
- No index on `phone_number` for now — escalations are rare (<5% of customers) and lookups by `phone_number` are not in the hot path. Add later if query performance degrades.

**Migration file path:**  
`supabase/migrations/003_escalation_tracking.sql` (see SQL Migration section below).

**Data retention:**  
No automatic cleanup. Rows are kept indefinitely for audit. If table grows large (>10,000 rows), consider a manual purge of rows older than 90 days where `resolved_at IS NOT NULL`.

---

### 2. `engine/integrations/meta_whatsapp.py` — Return Type Change

**Current signature:**

```python
async def send_message(
    client_config: ClientConfig,
    to_phone_number: str,
    text: str,
) -> bool:
```

**New signature:**

```python
async def send_message(
    client_config: ClientConfig,
    to_phone_number: str,
    text: str,
) -> Optional[str]:
```

**Change rationale:**  
Currently, `send_message()` returns `True` on success, `False` on failure. Callers use this to decide whether to log the outbound message. For escalation tracking, we need the `wamid` of the alert message to enable reply-to-message detection. The `wamid` is returned by Meta in the response body and must be captured.

**Return value semantics:**

- **Returns `wamid` (string)** — message sent successfully. The `wamid` is extracted from `response.json()["messages"][0]["id"]` (Meta API response structure).
- **Returns `None`** — message send failed (HTTP error, timeout, or JSON parse error).

**Backward compatibility:**  
Existing callers that check `if result:` will continue to work:
- `wamid` (non-empty string) is truthy → existing code sees "success"
- `None` is falsy → existing code sees "failure"

**Implementation change:**

```python
async def send_message(
    client_config: ClientConfig,
    to_phone_number: str,
    text: str,
) -> Optional[str]:
    """
    Send a WhatsApp text message via Meta Cloud API.

    Args:
        client_config:   Client configuration with Meta credentials.
        to_phone_number: Recipient phone number (E.164 without +, e.g. "6591234567").
        text:            Message body text.

    Returns:
        wamid (str) if message sent successfully, None otherwise.
        Never raises — caller checks return value.
    """
    text = _convert_markdown_to_whatsapp(text)
    url = (
        f"https://graph.facebook.com/v19.0/"
        f"{client_config.meta_phone_number_id}/messages"
    )
    headers = {
        "Authorization": f"Bearer {client_config.meta_whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone_number,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            # Extract wamid from Meta API response
            try:
                response_data = response.json()
                wamid = response_data["messages"][0]["id"]
                logger.info(f"Message sent successfully to {to_phone_number}, wamid={wamid}")
                return wamid
            except (KeyError, IndexError, ValueError) as e:
                # JSON parse error or unexpected structure — treat as failure
                logger.error(
                    f"Failed to extract wamid from Meta response for {to_phone_number}: {e}, "
                    f"body={response.text[:200]}"
                )
                return None

        logger.error(
            f"Meta API error sending to {to_phone_number}: "
            f"status={response.status_code}, body={response.text[:200]}"
        )
        return None

    except Exception as e:
        logger.error(
            f"Failed to send WhatsApp message to {to_phone_number}: {e}",
            exc_info=True,
        )
        return None
```

**Key changes:**
1. Return type annotation: `-> Optional[str]`
2. On success (200 OK), parse `response.json()["messages"][0]["id"]` to extract `wamid` and return it.
3. On JSON parse error, log the error and return `None` (treat as failure).
4. Update log message to include `wamid` on success.

**Error handling:**  
If `response.json()` raises `ValueError` (invalid JSON), or if the response structure is unexpected (missing `["messages"][0]["id"]`), return `None`. Do not crash. This is a graceful degradation — the message was sent (200 OK) but we failed to parse the response. Caller sees `None` and treats it as a send failure, which is acceptable (escalation flag is still set, human agent alert is delivered to WhatsApp even if we don't have the `wamid`).

---

### 3. `engine/api/webhook.py` — Extract `context.id`

**Current state:**  
The webhook POST handler extracts `phone_number`, `message_id`, `message_type`, `message_text`, and `display_name` from the Meta payload. It does NOT extract `message.context.id` (the `wamid` of the message being replied to).

**Required change:**  
Extract `context.id` from the payload and pass it to `handle_inbound_message()`.

**Meta webhook payload structure (reply-to-message):**

```json
{
  "entry": [
    {
      "changes": [
        {
          "value": {
            "messages": [
              {
                "from": "6512345678",
                "id": "wamid.new_message_id",
                "type": "text",
                "text": {"body": "done"},
                "context": {
                  "from": "6587654321",
                  "id": "wamid.original_message_id"
                }
              }
            ],
            "contacts": [...]
          }
        }
      ]
    }
  ]
}
```

**Extraction logic:**

```python
context_message_id = message.get("context", {}).get("id")
```

**Value semantics:**
- If the message is a reply-to-message, `context_message_id` is a `wamid` string (e.g., `"wamid.HBgLNjU5NzMyMTE4OTkVAgARGBI2OEI3RTRCODM2MTU4NjRGOEMA"`).
- If the message is NOT a reply, `context` key is absent and `context_message_id` is `None`.

**Implementation change (in `receive_whatsapp_message()`):**

```python
# 4. Extract message data
try:
    message = value["messages"][0]
    phone_number = message["from"]
    message_id = message["id"]
    message_type = message["type"]
    
    # NEW: Extract context.id for reply-to-message detection
    context_message_id = message.get("context", {}).get("id")

    if message_type == "text":
        message_text = message["text"]["body"]
    else:
        # Non-text message (image, audio, sticker, etc.) — pass empty string
        message_text = ""
        logger.info(
            f"Non-text message type '{message_type}' from {phone_number} "
            f"(client: {client_id}) — processing with empty text"
        )

    contact = value["contacts"][0]
    display_name = contact["profile"]["name"]

except (KeyError, IndexError, TypeError) as e:
    logger.error(
        f"Failed to extract message fields for client '{client_id}': {e}"
    )
    return Response(status_code=200)

# 5. Spawn background task — runs after 200 is returned to Meta
logger.info(f"Spawning background task for {phone_number} (client: {client_id})")
background_tasks.add_task(
    handle_inbound_message,
    client_id,
    phone_number,
    message_text,
    message_type,
    message_id,
    display_name,
    context_message_id,  # NEW parameter
)
```

**Function signature update:**

```python
async def handle_inbound_message(
    client_id: str,
    phone_number: str,
    message_text: str,
    message_type: str,
    message_id: str,
    display_name: str,
    context_message_id: Optional[str] = None,  # NEW parameter
) -> None:
```

**Why default to `None`:**  
Backward compatibility with any test harnesses or internal callers that don't pass `context_message_id`. New callers must pass it explicitly.

---

### 4. `engine/core/message_handler.py` — Human Agent Routing

**Current pipeline:**

```
1. Load client config + DB connection
2. Log inbound to interactions_log
3. Escalation gate — query customers table
4. If escalation_flag=True: send holding reply, log outbound, return
5. Upsert customer record
6. Build system message (context_builder)
7. Fetch conversation history
8. Run agent
9. Send agent reply
10. Log outbound
```

**Required change:**  
Insert **Step 0** (before Step 2) that checks if the sender is `human_agent_number`. If yes, route to `reset_handler.handle_human_agent_message()` and return immediately.

**Why before Step 2 (inbound log):**  
Human agent commands are **operational messages**, not customer interactions. They should not appear in `interactions_log`, which is the customer conversation history. Logging them would pollute the conversation context and confuse the agent ("Why is the customer saying 'done'?").

**Implementation:**

```python
async def handle_inbound_message(
    client_id: str,
    phone_number: str,
    message_text: str,
    message_type: str,
    message_id: str,
    display_name: str,
    context_message_id: Optional[str] = None,  # NEW parameter
) -> None:
    """
    Full inbound message processing pipeline.

    Runs as a FastAPI background task after the webhook returns 200 to Meta.
    All exceptions are caught — nothing propagates out of this function.
    """
    try:
        # ── Step 1: Load client config and DB connection ──────────────────────
        client_config = await load_client_config(client_id)
        db = await get_client_db(client_id)

        # ── Step 0: Human agent routing (NEW — inserted before inbound log) ───
        if phone_number == client_config.human_agent_number:
            logger.info(
                f"Human agent message detected from {phone_number} (client: {client_id})"
            )
            from engine.core.reset_handler import handle_human_agent_message
            await handle_human_agent_message(
                db=db,
                client_config=client_config,
                phone_number=phone_number,
                message_text=message_text,
                context_message_id=context_message_id,
            )
            return  # Do NOT log to interactions_log, do NOT run agent

        now = datetime.now(timezone.utc).isoformat()

        # ── Step 2: Log inbound (ALWAYS first for customer messages) ──────────
        try:
            await db.table("interactions_log").insert({
                "timestamp": now,
                "phone_number": phone_number,
                "direction": "inbound",
                "message_text": message_text,
                "message_type": message_type,
            }).execute()
            logger.info(
                f"Inbound logged for {phone_number} "
                f"(client: {client_id}, type: {message_type}, id: {message_id})"
            )
        except Exception as e:
            logger.error(
                f"Failed to log inbound message for {phone_number}: {e}",
                exc_info=True,
            )
            # Continue — a logging failure is not fatal.

        # ── Step 3: Escalation gate — query customer record ───────────────────
        # ... (rest of the pipeline unchanged)
```

**Key changes:**
1. Add `context_message_id: Optional[str] = None` parameter to function signature.
2. Insert Step 0 before Step 2 (inbound log).
3. If `phone_number == client_config.human_agent_number`, import and call `reset_handler.handle_human_agent_message()`, then return immediately.
4. Do NOT log human agent messages to `interactions_log`.
5. Do NOT run the agent loop for human agent messages.

**Why check phone number instead of a role flag:**  
The `human_agent_number` is configured per client in the `clients` table. It is the phone number the human agent uses for WhatsApp. This is the simplest and most reliable way to detect human agent messages — no additional role lookup or authentication needed.

**Edge case: human agent sends a message that is NOT a reply:**  
The reset handler will detect `context_message_id is None` and send a help message. See reset handler spec below.

---

### 5. New File: `engine/core/reset_handler.py`

**Purpose:**  
Handle all human agent commands. Currently, only escalation reset is supported. Future commands (e.g., "pause", "resume", "status") can be added here without touching `message_handler.py`.

**Public function:**

```python
async def handle_human_agent_message(
    db,
    client_config,
    phone_number: str,
    message_text: str,
    context_message_id: Optional[str],
) -> None:
```

**Parameters:**
- `db` — Supabase async client for the client's database.
- `client_config` — `ClientConfig` object with client settings.
- `phone_number` — Sender's phone number (always `client_config.human_agent_number` when this function is called).
- `message_text` — Message body text (extracted from Meta webhook).
- `context_message_id` — `wamid` of the message being replied to (None if not a reply).

**Returns:** `None`. Never raises.

**Logic flow:**

```
1. If context_message_id is None:
     → send "To clear an escalation, reply directly to the escalation alert with: done, resolved, ok, or handled."
     → return

2. Query escalation_tracking WHERE alert_msg_id = context_message_id AND resolved_at IS NULL LIMIT 1

3. If no row found:
     → send "No pending escalation found for this alert. It may have already been resolved."
     → return

4. If row found:
     a. Normalize message_text: message_text.strip().lower()
     b. Check if normalized text is in RESET_KEYWORDS
     c. If keyword does NOT match:
          → send "To confirm resolution, reply with one of these keywords: done, resolved, ok, handled, fixed, cleared, clear, completed, complete, closed, close, okay"
          → return
     d. If keyword matches:
          i.   UPDATE customers SET escalation_flag=FALSE WHERE phone_number=row.phone_number
          ii.  UPDATE escalation_tracking SET resolved_at=NOW(), resolved_by=phone_number WHERE id=row.id
          iii. Fetch customer name from customers table (for confirmation message)
          iv.  Send confirmation to human agent: "✅ Escalation cleared for {customer_name or customer_phone}. AI will resume handling their messages."
          v.   Log success
```

**Full implementation:**

```python
"""
Human agent command handler.

Currently supports:
  - Escalation reset via reply-to-message

Future commands (not yet implemented):
  - pause / resume (manual agent silence without escalation flag)
  - status (query customer state)
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Approved reset keywords (case-insensitive, full message text after strip).
RESET_KEYWORDS = frozenset([
    "done", "resolved", "resolve", "fixed", "handled",
    "cleared", "clear", "completed", "complete",
    "closed", "close", "ok", "okay",
])

# Help messages sent to human agent
_HELP_NO_REPLY = (
    "To clear an escalation, reply directly to the escalation alert with: "
    "done, resolved, ok, or handled."
)

_HELP_NO_ESCALATION = (
    "No pending escalation found for this alert. "
    "It may have already been resolved."
)

_HELP_INVALID_KEYWORD = (
    "To confirm resolution, reply with one of these keywords: "
    "done, resolved, ok, handled, fixed, cleared, clear, "
    "completed, complete, closed, close, okay"
)


async def handle_human_agent_message(
    db,
    client_config,
    phone_number: str,
    message_text: str,
    context_message_id: Optional[str],
) -> None:
    """
    Process a message from the human agent.

    Currently only handles escalation reset commands.
    Sends help messages for any invalid usage.

    Args:
        db:                  Supabase async client.
        client_config:       ClientConfig for the active client.
        phone_number:        Human agent's phone number.
        message_text:        Message body from Meta webhook.
        context_message_id:  wamid of the message being replied to (None if not a reply).

    Returns:
        None. Never raises — errors are logged and help messages sent.
    """
    from engine.integrations.meta_whatsapp import send_message

    # ── Step 1: Check if message is a reply ───────────────────────────────────
    if context_message_id is None:
        logger.info(
            f"Human agent message from {phone_number} is not a reply — sending help"
        )
        try:
            await send_message(client_config, phone_number, _HELP_NO_REPLY)
        except Exception as e:
            logger.error(f"Failed to send help message (no reply): {e}", exc_info=True)
        return

    # ── Step 2: Query escalation_tracking for matching alert ──────────────────
    try:
        result = await (
            db.table("escalation_tracking")
            .select("*")
            .eq("alert_msg_id", context_message_id)
            .is_("resolved_at", "null")  # Only unresolved escalations
            .limit(1)
            .execute()
        )
        escalation_row = result.data[0] if result.data else None
    except Exception as e:
        logger.error(
            f"DB error querying escalation_tracking for alert {context_message_id}: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "Failed to process escalation reset — please try again.",
            )
        except Exception:
            pass
        return

    # ── Step 3: Check if escalation exists ────────────────────────────────────
    if escalation_row is None:
        logger.info(
            f"No pending escalation found for alert {context_message_id} — sending help"
        )
        try:
            await send_message(client_config, phone_number, _HELP_NO_ESCALATION)
        except Exception as e:
            logger.error(f"Failed to send help message (no escalation): {e}", exc_info=True)
        return

    # ── Step 4: Validate keyword ──────────────────────────────────────────────
    normalized_text = message_text.strip().lower()
    if normalized_text not in RESET_KEYWORDS:
        logger.info(
            f"Human agent replied with invalid keyword '{message_text}' — sending help"
        )
        try:
            await send_message(client_config, phone_number, _HELP_INVALID_KEYWORD)
        except Exception as e:
            logger.error(f"Failed to send help message (invalid keyword): {e}", exc_info=True)
        return

    # ── Step 5: Clear escalation flag ─────────────────────────────────────────
    customer_phone = escalation_row["phone_number"]
    try:
        # Clear the customer's escalation_flag
        await (
            db.table("customers")
            .update({"escalation_flag": False})
            .eq("phone_number", customer_phone)
            .execute()
        )
        logger.info(f"Escalation flag cleared for customer {customer_phone}")

        # Mark the escalation as resolved in escalation_tracking
        await (
            db.table("escalation_tracking")
            .update({
                "resolved_at": "now()",
                "resolved_by": phone_number,
            })
            .eq("id", escalation_row["id"])
            .execute()
        )
        logger.info(
            f"Escalation {escalation_row['id']} marked as resolved by {phone_number}"
        )

    except Exception as e:
        logger.error(
            f"DB error clearing escalation for customer {customer_phone}: {e}",
            exc_info=True,
        )
        try:
            await send_message(
                client_config,
                phone_number,
                "Failed to clear escalation — please try again or update manually in Supabase.",
            )
        except Exception:
            pass
        return

    # ── Step 6: Fetch customer name for confirmation ──────────────────────────
    try:
        customer_result = await (
            db.table("customers")
            .select("customer_name")
            .eq("phone_number", customer_phone)
            .limit(1)
            .execute()
        )
        customer_name = (
            customer_result.data[0]["customer_name"]
            if customer_result.data and customer_result.data[0].get("customer_name")
            else customer_phone
        )
    except Exception as e:
        logger.warning(f"Failed to fetch customer name for {customer_phone}: {e}")
        customer_name = customer_phone

    # ── Step 7: Send confirmation to human agent ──────────────────────────────
    confirmation_text = (
        f"✅ Escalation cleared for {customer_name}. "
        "AI will resume handling their messages."
    )
    try:
        await send_message(client_config, phone_number, confirmation_text)
        logger.info(f"Confirmation sent to {phone_number} for customer {customer_phone}")
    except Exception as e:
        logger.error(f"Failed to send confirmation to {phone_number}: {e}", exc_info=True)
        # Non-fatal — escalation was already cleared in DB
```

**Key design decisions:**

1. **Keyword normalization:** `message_text.strip().lower()` removes leading/trailing whitespace and converts to lowercase. This allows "Done", "DONE", " done " to all match.

2. **Full message match:** The normalized text must be **exactly** one of the keywords. "done thanks" or "ok got it" will NOT match. This is intentional — keeps the reset command unambiguous. The help message guides the user to use only the keyword.

3. **Help messages are generous:** If the human agent makes any mistake (no reply, invalid keyword, no escalation found), the system sends a help message explaining what to do. This reduces support burden.

4. **`resolved_at` uses Postgres `now()` function:** The UPDATE query passes `"now()"` as a string, which Supabase interprets as a SQL function call. This ensures the timestamp is set by the database server, not the Python client (avoids timezone bugs).

5. **Customer name fallback:** If the customer name is not set in the `customers` table, the confirmation message uses the phone number instead. This prevents crashes and keeps the confirmation message useful.

6. **Never raises:** All DB errors and `send_message()` failures are caught and logged. The function always returns cleanly. The worst case is that the human agent doesn't receive a confirmation message, but the escalation is still cleared in the DB (or if the DB write failed, the help message tells them to try again).

---

### 6. `engine/core/tools/escalation_tool.py` — Capture `wamid` + Insert Tracking Row

**Current state:**  
The `escalate_to_human()` function:
1. Sets `escalation_flag=True` in the `customers` table.
2. Sends a WhatsApp alert to `human_agent_number` via `send_message()`.
3. Returns `{"status": "escalated", "message": "..."}` to Claude.

It does NOT:
- Capture the `wamid` of the alert message.
- Insert a row into `escalation_tracking`.

**Required changes:**

1. After calling `send_message()`, capture the returned `wamid` (or `None` if send failed).
2. After setting `escalation_flag=True`, INSERT a row into `escalation_tracking`:
   ```python
   {
       "phone_number": phone_number,
       "alert_msg_id": wamid or None,  # NULL if send failed
       "escalation_reason": reason,
   }
   ```
3. If the INSERT fails, log a warning but continue. Do not crash. The escalation flag is already set, so the gate will still block the agent.

**Implementation change:**

```python
async def escalate_to_human(
    db,
    client_config,
    phone_number: str,
    reason: str,
) -> dict:
    """
    Trigger human escalation for a customer.

    Steps:
    1. UPDATE customers SET escalation_flag=TRUE, escalation_reason=...
    2. Send WhatsApp alert to human_agent_number with customer details.
    3. INSERT into escalation_tracking for reset mechanism.

    The escalation gate in message_handler.py will then block the agent
    for all subsequent messages from this customer.

    Args:
        db:            Supabase async client (injected).
        client_config: ClientConfig with human_agent_number + WhatsApp creds (injected).
        phone_number:  Customer phone number being escalated (injected).
        reason:        Free-text reason provided by Claude.

    Returns:
        dict: {status: "escalated", message: <confirmation text for Claude>}

    Never raises — escalation failures are logged but do not crash the agent loop.
    """
    now = datetime.now(timezone.utc).isoformat()
    alert_wamid: Optional[str] = None  # Will be set if alert send succeeds

    # ── Step 1: Set escalation flag in Supabase ───────────────────────────────
    try:
        await (
            db.table("customers")
            .update({
                "escalation_flag": True,
                "escalation_reason": reason,
                "last_seen": now,
            })
            .eq("phone_number", phone_number)
            .execute()
        )
        logger.info(
            f"Escalation flag set for {phone_number} — reason: {reason}"
        )

        # Sync updated customer record to Google Sheets (fire-and-forget).
        # ... (Sheets sync code unchanged)

    except Exception as e:
        logger.error(
            f"Failed to set escalation_flag for {phone_number}: {e}",
            exc_info=True,
        )
        # Continue — still send the human agent alert if possible.

    # ── Step 2: Notify human agent via WhatsApp ───────────────────────────────
    if client_config.human_agent_number:
        try:
            from engine.integrations.meta_whatsapp import send_message

            alert_text = _HUMAN_AGENT_ALERT_TEMPLATE.format(
                phone_number=phone_number,
                reason=reason,
            )
            # NEW: capture the wamid returned by send_message()
            alert_wamid = await send_message(
                client_config=client_config,
                to_phone_number=client_config.human_agent_number,
                text=alert_text,
            )
            
            if alert_wamid:
                logger.info(
                    f"Human agent alert sent to {client_config.human_agent_number} "
                    f"for customer {phone_number}, wamid={alert_wamid}"
                )
            else:
                logger.warning(
                    f"Human agent alert send FAILED for customer {phone_number} "
                    f"— wamid is None"
                )

        except Exception as e:
            logger.error(
                f"Failed to send human agent alert for {phone_number}: {e}",
                exc_info=True,
            )
            try:
                from engine.integrations.observability import log_noncritical_failure
                asyncio.create_task(log_noncritical_failure(
                    source="escalation_human_alert",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    client_id=client_config.client_id,
                    context={"phone_number": phone_number, "human_agent_number": client_config.human_agent_number},
                ))
            except Exception:
                pass  # Observability must never crash escalation.
    else:
        logger.warning(
            f"No human_agent_number configured for client {client_config.client_id} "
            "— skipping human agent WhatsApp alert"
        )

    # ── Step 3: Insert escalation tracking row (NEW) ──────────────────────────
    try:
        await db.table("escalation_tracking").insert({
            "phone_number": phone_number,
            "alert_msg_id": alert_wamid,  # NULL if send_message() returned None
            "escalation_reason": reason,
        }).execute()
        logger.info(
            f"Escalation tracking row inserted for {phone_number}, "
            f"alert_msg_id={alert_wamid or 'NULL'}"
        )
    except Exception as e:
        logger.warning(
            f"Failed to insert escalation tracking row for {phone_number}: {e}",
            exc_info=True,
        )
        # Non-fatal — escalation flag is already set, gate will work.
        # Reset mechanism will not work for this escalation (alert_msg_id is NULL),
        # but human can still clear the flag manually.

    # ── Step 4: Return success to Claude ──────────────────────────────────────
    return {
        "status": "escalated",
        "message": (
            "Customer has been escalated. A member of our team will follow up directly. "
            "Please inform the customer that someone will be in touch today."
        ),
    }
```

**Key changes:**
1. Declare `alert_wamid: Optional[str] = None` at the top of the function.
2. Capture the return value of `send_message()` in `alert_wamid`.
3. Log the `wamid` if send succeeded, or log a warning if `alert_wamid is None`.
4. Insert a row into `escalation_tracking` with `alert_msg_id=alert_wamid` (NULL if send failed).
5. If INSERT fails, log a warning but do not crash. The escalation flag is already set, so the gate will work. The reset mechanism will not work for this escalation (human agent will have to clear manually), but this is acceptable.

**Why INSERT is non-fatal:**  
The escalation flag is the primary safety mechanism. If `escalation_flag=True` is set but the tracking row INSERT fails, the agent is still silenced (gate works). The only consequence is that the reset mechanism won't work for this escalation. The human agent will receive the alert on WhatsApp but won't be able to clear it via reply-to-message. They must use Supabase Studio. This is acceptable — it's a degraded experience, not a system failure.

---

## Data Flow Diagram

### Happy Path: Escalation Triggered → Human Agent Clears → AI Resumes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. ESCALATION TRIGGERED BY AGENT                                            │
└─────────────────────────────────────────────────────────────────────────────┘
   │
   ├─▶ escalate_to_human() called by Claude
   │
   ├─▶ UPDATE customers SET escalation_flag=TRUE
   │     WHERE phone_number='6591234567'
   │
   ├─▶ send_message(to=human_agent_number, text=alert)
   │     → Meta returns wamid='wamid.ABC123...'
   │
   ├─▶ INSERT INTO escalation_tracking
   │     (phone_number='6591234567', alert_msg_id='wamid.ABC123...', 
   │      escalation_reason='Customer requested to speak to a person')
   │
   └─▶ Return to Claude: {"status": "escalated", "message": "..."}

┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. CUSTOMER SENDS FOLLOW-UP MESSAGE                                         │
└─────────────────────────────────────────────────────────────────────────────┘
   │
   ├─▶ Meta webhook POST to engine
   │
   ├─▶ handle_inbound_message(phone_number='6591234567', ...)
   │
   ├─▶ Escalation gate: query customers WHERE phone_number='6591234567'
   │     → escalation_flag=TRUE found
   │
   ├─▶ send_message(to='6591234567', text=HOLDING_REPLY)
   │     → "Thank you for reaching out. A member of our team will get back to you today."
   │
   ├─▶ Log outbound to interactions_log
   │
   └─▶ RETURN (agent never runs)

┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. HUMAN AGENT RESOLVES ISSUE AND REPLIES TO ALERT                          │
└─────────────────────────────────────────────────────────────────────────────┘
   │
   ├─▶ Human agent opens WhatsApp, sees alert:
   │     "🔔 HeyAircon Escalation Alert
   │      Customer: 6591234567
   │      Reason: Customer requested to speak to a person"
   │
   ├─▶ Human agent replies to alert message (WhatsApp reply-to-message gesture)
   │     → Message body: "done"
   │
   ├─▶ Meta webhook POST to engine:
   │     {"messages": [{"from": "6587654321", "text": {"body": "done"},
   │      "context": {"id": "wamid.ABC123..."}}]}
   │
   ├─▶ webhook.py extracts:
   │     - phone_number='6587654321'
   │     - message_text='done'
   │     - context_message_id='wamid.ABC123...'
   │
   ├─▶ handle_inbound_message(phone_number='6587654321', 
   │                           context_message_id='wamid.ABC123...', ...)
   │
   ├─▶ Step 0: phone_number == human_agent_number → route to reset_handler
   │
   └─▶ handle_human_agent_message(context_message_id='wamid.ABC123...', 
                                    message_text='done')

┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. RESET HANDLER CLEARS ESCALATION                                          │
└─────────────────────────────────────────────────────────────────────────────┘
   │
   ├─▶ context_message_id is not None → proceed
   │
   ├─▶ Query escalation_tracking 
   │     WHERE alert_msg_id='wamid.ABC123...' AND resolved_at IS NULL
   │     → row found: {id=42, phone_number='6591234567', ...}
   │
   ├─▶ Normalize message_text: 'done'.strip().lower() = 'done'
   │     → 'done' in RESET_KEYWORDS → keyword match
   │
   ├─▶ UPDATE customers SET escalation_flag=FALSE 
   │     WHERE phone_number='6591234567'
   │
   ├─▶ UPDATE escalation_tracking 
   │     SET resolved_at=now(), resolved_by='6587654321'
   │     WHERE id=42
   │
   ├─▶ Query customers to fetch customer_name for confirmation
   │     → customer_name='John Tan'
   │
   ├─▶ send_message(to='6587654321', 
   │                text='✅ Escalation cleared for John Tan. AI will resume...')
   │
   └─▶ RETURN (escalation cleared)

┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. CUSTOMER SENDS NEXT MESSAGE — AI RESUMES                                 │
└─────────────────────────────────────────────────────────────────────────────┘
   │
   ├─▶ Meta webhook POST to engine
   │
   ├─▶ handle_inbound_message(phone_number='6591234567', ...)
   │
   ├─▶ Escalation gate: query customers WHERE phone_number='6591234567'
   │     → escalation_flag=FALSE (cleared by human agent)
   │
   ├─▶ Gate PASSED → upsert customer, build context, run agent
   │
   ├─▶ Agent sends reply
   │
   └─▶ Normal conversation flow resumes
```

### Edge Case: Human Agent Replies with Invalid Keyword

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HUMAN AGENT REPLIES WITH "ok thanks" (not an exact keyword match)           │
└─────────────────────────────────────────────────────────────────────────────┘
   │
   ├─▶ handle_human_agent_message(message_text='ok thanks', 
   │                               context_message_id='wamid.ABC123...')
   │
   ├─▶ Query escalation_tracking → row found
   │
   ├─▶ Normalize message_text: 'ok thanks'.strip().lower() = 'ok thanks'
   │     → 'ok thanks' NOT in RESET_KEYWORDS → keyword mismatch
   │
   ├─▶ send_message(to=human_agent_number, text=_HELP_INVALID_KEYWORD)
   │     → "To confirm resolution, reply with one of these keywords: done, resolved..."
   │
   └─▶ RETURN (escalation NOT cleared)
```

### Edge Case: Human Agent Sends Message Without Reply

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HUMAN AGENT SENDS STANDALONE MESSAGE "done" (no reply-to-message)           │
└─────────────────────────────────────────────────────────────────────────────┘
   │
   ├─▶ webhook.py: context_message_id is None (no "context" in payload)
   │
   ├─▶ handle_human_agent_message(context_message_id=None, message_text='done')
   │
   ├─▶ context_message_id is None → send help
   │
   ├─▶ send_message(to=human_agent_number, text=_HELP_NO_REPLY)
   │     → "To clear an escalation, reply directly to the escalation alert..."
   │
   └─▶ RETURN (escalation NOT cleared)
```

### Edge Case: Alert Send Failed (No `wamid` Captured)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ escalate_to_human() SENDS ALERT BUT Meta API RETURNS ERROR                  │
└─────────────────────────────────────────────────────────────────────────────┘
   │
   ├─▶ send_message(to=human_agent_number, ...) 
   │     → Meta returns 500 error
   │     → send_message() returns None
   │
   ├─▶ alert_wamid = None
   │
   ├─▶ INSERT INTO escalation_tracking (alert_msg_id=NULL, ...)
   │
   └─▶ Reset mechanism will NOT work (no alert_msg_id to match)
       Human agent must clear escalation manually in Supabase Studio
```

---

## SQL Migration

**File:** `supabase/migrations/003_escalation_tracking.sql`

```sql
-- Migration: Escalation Tracking for Reply-to-Message Reset
-- Author: @software-architect
-- Date: 2026-04-22
-- Description: Adds escalation_tracking table to support human agent reset via WhatsApp reply

-- ────────────────────────────────────────────────────────────────────────────
-- Table: escalation_tracking
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE escalation_tracking (
    id SERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    alert_msg_id TEXT,
    escalated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    escalation_reason TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT
);

-- Index on alert_msg_id for fast lookup when human agent replies.
-- Partial index (WHERE resolved_at IS NULL) keeps it small — only unresolved escalations.
CREATE INDEX idx_escalation_tracking_alert_msg_id 
    ON escalation_tracking(alert_msg_id) 
    WHERE resolved_at IS NULL;

-- Optional: Index on phone_number for per-customer escalation history queries.
-- Not critical for the reset flow — add later if needed.
-- CREATE INDEX idx_escalation_tracking_phone_number ON escalation_tracking(phone_number);

-- ────────────────────────────────────────────────────────────────────────────
-- Migration notes
-- ────────────────────────────────────────────────────────────────────────────
-- - This migration is ADDITIVE — no schema changes to existing tables.
-- - Can be applied to production with zero downtime.
-- - Rollback: DROP TABLE escalation_tracking CASCADE;
-- - Data retention: No automatic cleanup. Rows are kept for audit.
--   Consider manual purge of rows WHERE resolved_at IS NOT NULL AND resolved_at < NOW() - INTERVAL '90 days'
--   if table grows >10,000 rows.
```

**Deployment:**

1. **For existing clients (HeyAircon):**  
   Apply the migration to the HeyAircon Supabase database via Supabase Studio SQL editor or CLI:
   ```bash
   supabase db push --db-url <HEYAIRCON_SUPABASE_URL>
   ```

2. **For new clients:**  
   The migration is automatically applied when a new client database is provisioned.

**Rollback:**
```sql
DROP TABLE escalation_tracking CASCADE;
```

**Testing:**  
After applying the migration, verify the table exists and the index is created:
```sql
-- Check table structure
\d escalation_tracking

-- Check indexes
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'escalation_tracking';

-- Insert a test row
INSERT INTO escalation_tracking (phone_number, alert_msg_id, escalation_reason)
VALUES ('6591234567', 'wamid.test123', 'Test escalation');

-- Query by alert_msg_id (should use index)
EXPLAIN ANALYZE
SELECT * FROM escalation_tracking 
WHERE alert_msg_id = 'wamid.test123' 
  AND resolved_at IS NULL;

-- Clean up test row
DELETE FROM escalation_tracking WHERE phone_number = '6591234567';
```

---

## Caller Audit for `send_message()` Return Type Change

**Current return type:** `bool`  
**New return type:** `Optional[str]`  
**Backward compatibility:** Yes — non-empty string is truthy, `None` is falsy.

**All callers of `send_message()` in the codebase:**

| File | Line(s) | Context | Change Required? | Notes |
|------|---------|---------|------------------|-------|
| `engine/core/tools/escalation_tool.py` | 120 | Alert to human agent | **YES** | Must capture the returned `wamid` and pass it to `escalation_tracking` INSERT. See implementation in Section 6. |
| `engine/core/tools/booking_tools.py` | 63 | Booking confirmation to customer | **NO** | Caller only checks truthiness: `if send_result: ...`. No changes needed. |
| `engine/core/message_handler.py` | 124, 144, 250 | Holding reply, fallback reply, agent reply | **NO** | All callers check truthiness or ignore return value. No changes needed. |
| `engine/tests/unit/test_escalation.py` | 50, 75, 90, 125 | Unit tests with mocked `send_message()` | **MAYBE** | Tests currently mock `send_message()` as `AsyncMock`. Must update mocks to return a `wamid` string instead of `True`, or return `None` for failure cases. Review test assertions — if any assert `result is True`, change to assert that result is a non-empty string. |
| `engine/tests/integration/test_sheets_sync_hooks.py` | 20, 76, 179 | Integration tests with patched `send_message()` | **MAYBE** | Same as unit tests — update mocks to return `wamid` string or `None`. |

**Action items:**

1. **Update `escalation_tool.py`** (required) — capture `wamid` and insert into `escalation_tracking`. Specified in Section 6.

2. **Audit all test mocks** (required before merge):
   - `engine/tests/unit/test_escalation.py` — update `@patch("engine.integrations.meta_whatsapp.send_message")` to return `"wamid.test123"` instead of `True`, or `None` for failure cases.
   - `engine/tests/integration/test_sheets_sync_hooks.py` — same as above.
   - Run full test suite after changes: `pytest engine/tests/`

3. **Verify all other callers** (paranoid check):  
   Run a full codebase search to ensure no other files call `send_message()`:
   ```bash
   rg 'send_message\(' --type py
   ```
   If any new callers are found, apply the same analysis: does the caller depend on the return type being a boolean? If yes, update the caller to handle `Optional[str]`.

**Risk assessment:**  
Low risk. The return type change is backward-compatible with all existing callers that only check truthiness. The only breaking change would be if a caller explicitly checks `result is True` or `result is False` (identity checks instead of truthiness). No such checks were found in the codebase audit.

---

## Implementation Checklist

**Pre-implementation:**
- [ ] Read this spec end-to-end
- [ ] Review current codebase files listed in Section 2-6
- [ ] Confirm Supabase access and ability to apply migrations

**Implementation (order matters):**

1. **Database schema:**
   - [ ] Apply SQL migration `003_escalation_tracking.sql` to HeyAircon Supabase database
   - [ ] Verify table creation and index: `\d escalation_tracking`

2. **Core changes (slice 1):**
   - [ ] Update `engine/integrations/meta_whatsapp.py` — return `Optional[str]` from `send_message()`
   - [ ] Extract `wamid` from Meta API response, handle JSON parse errors
   - [ ] Update docstring and log messages

3. **Webhook changes (slice 2):**
   - [ ] Update `engine/api/webhook.py` — extract `context_message_id` from payload
   - [ ] Add `context_message_id` parameter to `handle_inbound_message()` call
   - [ ] Update `handle_inbound_message()` signature in `message_handler.py`

4. **Message handler changes (slice 3):**
   - [ ] Add Step 0 in `handle_inbound_message()` — check if sender is `human_agent_number`
   - [ ] Route to `reset_handler.handle_human_agent_message()` if match
   - [ ] Ensure human agent messages do NOT log to `interactions_log`

5. **Reset handler (slice 4):**
   - [ ] Create `engine/core/reset_handler.py` with `handle_human_agent_message()` function
   - [ ] Implement keyword validation logic (RESET_KEYWORDS)
   - [ ] Implement escalation clearing (UPDATE customers, UPDATE escalation_tracking)
   - [ ] Implement help messages for all error cases

6. **Escalation tool changes (slice 5):**
   - [ ] Update `engine/core/tools/escalation_tool.py` — capture `wamid` from `send_message()`
   - [ ] INSERT into `escalation_tracking` after setting `escalation_flag`
   - [ ] Handle INSERT failures gracefully (log warning, continue)

7. **Test updates:**
   - [ ] Update all `send_message()` mocks in test files to return `wamid` string or `None`
   - [ ] Verify no test failures: `pytest engine/tests/`

8. **Integration testing:**
   - [ ] Deploy to Railway dev environment
   - [ ] Trigger an escalation (send customer message requesting human agent)
   - [ ] Verify alert is sent to `human_agent_number` on WhatsApp
   - [ ] Reply to alert with "done" — verify escalation is cleared
   - [ ] Reply to alert with "ok thanks" — verify help message is sent
   - [ ] Send "done" without replying to alert — verify help message is sent
   - [ ] Verify `escalation_tracking` table has correct rows (alert_msg_id, resolved_at, resolved_by)

9. **Production cutover:**
   - [ ] Apply SQL migration to production HeyAircon database
   - [ ] Deploy code to Railway production service
   - [ ] Monitor logs for errors in reset handler
   - [ ] Test with real WhatsApp account (alert + reset flow)

**Post-implementation:**
- [ ] Update `docs/architecture/README.md` to list this spec file
- [ ] Update `docs/architecture/code_map.md` if any new files were added
- [ ] Document the reset keywords in HeyAircon operator training materials
- [ ] Add monitoring query to `docs/observability/sql-reference.md`:
  ```sql
  -- Unresolved escalations (pending human action)
  SELECT phone_number, escalated_at, escalation_reason
  FROM escalation_tracking
  WHERE resolved_at IS NULL
  ORDER BY escalated_at DESC;
  ```

---

## Appendix: Why Not Use a Web Dashboard?

This question will inevitably come up. Here's the definitive answer to save future debate cycles.

**The reset mechanism is not a dashboard replacement.** It is a **tactical MVP feature** for Phase 1. Here's why:

1. **Phase 1 scope:** The MVP is a WhatsApp agent. Human agents already use WhatsApp for customer follow-up. Adding a reset command to the same channel is a natural extension. No new tools, no new logins, no new training.

2. **Phase 2 roadmap:** The CRM dashboard (Phase 2) will include an escalation queue view with one-click reset buttons. When that's built, the WhatsApp reset mechanism becomes a backup/redundancy feature. But Phase 2 is months away. Human agents need to reset escalations **now**.

3. **Operational reality:** Human agents are often on mobile, responding to customer issues in real-time. Opening a web dashboard on a phone is friction. Replying to a WhatsApp message is zero friction.

4. **Development cost:** Building a web dashboard is a multi-week effort (auth, UI, API, hosting). Implementing reply-to-message reset is a 1-2 day effort. The ROI is clear.

5. **Precedent:** Other WhatsApp-based support platforms (e.g., Zendesk, Intercom) use reply-to-message for agent commands. This is not a novel pattern.

**Bottom line:** The reset mechanism is the right tool for the current phase. It is not a hack. It is not a compromise. It is the simplest solution that solves the problem.
