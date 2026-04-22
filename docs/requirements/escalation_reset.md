# Feature Requirements: Escalation Reset via WhatsApp Reply

> **Requirements Specification**  
> Author: @product-manager  
> Date: 2026-04-22  
> Status: Draft — Pending Founder Approval

---

## 1. Feature Overview

### What
Human agents can reset the escalation flag for a customer by replying to the escalation alert message on WhatsApp with a simple keyword (e.g., "done", "resolved", "ok"). This programmatically clears the `escalation_flag` in the database and allows the AI agent to resume handling the customer's messages.

### Who
**Primary users:** Human agents at HeyAircon — non-technical field staff who receive escalation alerts on WhatsApp and resolve customer issues directly (via phone call or personal WhatsApp).

**Affected users:** End customers — after the human agent resolves their issue and clears the flag, the next message they send to the business is handled by the AI agent instead of receiving a holding reply.

### Why
**Current pain:** When the AI agent escalates a customer, the escalation flag remains set until someone manually updates the database in Supabase Studio. Human agents have no self-service way to signal "I've resolved this, the AI can take over again."

**Value delivered:** 
- Reduces operational friction — human agents use WhatsApp (the channel they already monitor) to reset escalations, not database admin tools.
- Faster customer service restoration — the AI can resume handling the customer immediately after human resolution, not hours later when someone remembers to clear the flag manually.
- Creates an audit trail — every escalation and resolution is logged with timestamps and the resolving agent's phone number.

### Channel
WhatsApp only. The reset is triggered by replying directly to the escalation alert message thread (reply-to-message gesture).

---

## Direction Check

- **Subject**: Human agents (non-technical field staff) who need to signal completion of escalation resolution
- **Problem**: No programmatic way to clear the escalation flag after resolving a customer issue — agents are blocked from resuming AI service without database access
- **Confirmation**: This solution gives the subject (human agents) a self-service mechanism (WhatsApp keyword reply) to clear the escalation flag — it does NOT address the inverse (e.g., giving customers control over escalation state, or making escalation harder to trigger)

---

## 2. Trigger Conditions

The escalation reset handler activates when **ALL three conditions are true**:

| Condition | Check |
|-----------|-------|
| **C1: Sender is human agent** | `phone_number == client_config.human_agent_number` |
| **C2: Message is a reply** | `message.context.id` is present (WhatsApp reply-to-message) |
| **C3: Reply targets an unresolved escalation alert** | `context.id` matches an `alert_msg_id` in `escalation_tracking` WHERE `resolved_at IS NULL` |

### Condition Failure Handling

| Failed Condition(s) | Engine Response |
|---------------------|-----------------|
| **C1 only** (customer sends message) | Ignore — pass to normal agent pipeline |
| **C1 + C2** (human agent replies, but not to a known alert) | Send help: "No pending escalation found for this alert. It may have already been resolved or this message is not an escalation alert." |
| **C1 + ¬C2** (human agent sends fresh message, not a reply) | Send help: "To clear this escalation, reply with: done, resolved, or ok" |

**Key distinction**: When C1 + C2 are true but C3 is false (reply is to an **unrelated** message or an **already-resolved** alert), the system sends a help reply but does NOT crash or escalate further. This is graceful degradation.

---

## 3. Keyword Matching Rules

### Normalisation Steps (applied in order)

Input text is normalised before comparing against the approved keyword list:

1. **Strip leading/trailing whitespace** — `"  done  "` → `"done"`
2. **Collapse all internal whitespace** — Replace all spaces, tabs, newlines with a single space, then remove all spaces — `"res olved"` → `"res olved"` → `"resolved"`
3. **Lowercase** — `"DONE"` → `"done"`

### Approved Keywords

The following keywords trigger a successful escalation reset:

```
done, resolved, ok, handled, fixed, cleared, completed, closed, finish, finished, okay
```

### Match Definition

After normalisation, the input text must **exactly equal** one of the approved keywords. Partial matches, substrings, and approximate matches are **NOT accepted**.

### Normalisation Case Study

| Input | After Step 1 | After Step 2 | After Step 3 | Match? |
|-------|--------------|--------------|--------------|--------|
| `"Resolved"` | `"Resolved"` | `"Resolved"` | `"resolved"` | ✅ MATCH |
| `"DONE"` | `"DONE"` | `"DONE"` | `"done"` | ✅ MATCH |
| `"  done  "` | `"done"` | `"done"` | `"done"` | ✅ MATCH |
| `"res olved"` | `"res olved"` | `"resolved"` | `"resolved"` | ✅ MATCH |
| `"OK"` | `"OK"` | `"OK"` | `"ok"` | ✅ MATCH |
| `"o k"` | `"o k"` | `"ok"` | `"ok"` | ✅ MATCH |
| `"f i n i s h e d"` | `"f i n i s h e d"` | `"finished"` | `"finished"` | ✅ MATCH |
| `"resolvedd"` | `"resolvedd"` | `"resolvedd"` | `"resolvedd"` | ❌ NO MATCH (typo) |
| `"👍"` | `"👍"` | `"👍"` | `"👍"` | ❌ NO MATCH (emoji) |
| `"I'll call them"` | `"I'll call them"` | `"I'llcallthem"` | `"i'llcallthem"` | ❌ NO MATCH |
| `"ok thanks"` | `"ok thanks"` | `"okthanks"` | `"okthanks"` | ❌ NO MATCH |
| `"when did this come in?"` | `"when did this come in?"` | `"whendidthiscomein?"` | `"whendidthiscomein?"` | ❌ NO MATCH |

**Important note on internal spaces:** The normalisation rule removes ALL internal spaces. This means `"res olved"` → `"resolved"` → MATCH. This is intentional — it handles cases where a human agent accidentally types a space mid-word (e.g., on mobile). The founder explicitly approved this behaviour.

---

## 4. Unrecognised Input Handling

### When It Triggers

Unrecognised input handling activates when:
- **Conditions C1 + C2 + C3 are all TRUE** (human agent, reply-to-message, targets an unresolved alert), AND
- **Normalised message text does NOT match any approved keyword**

### What Happens

The engine sends an immediate help reply to the human agent with the approved keyword list. The escalation flag is **NOT cleared** — it remains `TRUE` and the customer continues to receive holding replies.

### Example Help Message

```
To clear this escalation, reply with: done, resolved, or ok
```

> **Note:** The engine keyword list (11 words) is broader than what appears in this message. The help text shows only the 3 most natural keywords to keep it short for field staff. Any of the 11 approved keywords will still trigger a reset.

### Design Note

This is a **user-friendly error message**, not a technical error. The system does not log this as an error condition or send an alert to the operator. It's normal behaviour — the human agent simply typed something the system didn't understand, and the system is teaching them the correct input format.

---

## 5. Happy Path Flow (with example messages)

### Step-by-Step

| Step | Actor | Action | Example Message |
|------|-------|--------|-----------------|
| **1** | AI Agent | Detects escalation condition (e.g., customer complaint, out-of-scope request) and triggers `escalate_to_human` tool | — |
| **2** | Engine | Sets `escalation_flag=TRUE` in `customers` table, inserts row in `escalation_tracking`, sends alert to `human_agent_number` | "🚨 Escalation Alert\n\nCustomer: John Tan (+65 9123 4567)\n\nReason: Customer is requesting a refund for a service they say was not completed properly.\n\nLast message: 'Your technician left without finishing the job, I want my money back'\n\nPlease follow up directly." |
| **3** | Human Agent | Resolves the issue directly with the customer (phone call or personal WhatsApp from their personal number, not the business number) | — |
| **4** | Human Agent | Opens WhatsApp, finds the escalation alert message, taps "Reply" on that specific message, types "done" | Input: `"done"` |
| **5** | Engine | Receives webhook, extracts `context.id` (the `wamid` of the alert message), validates C1 + C2 + C3, normalises "done" → "done", finds match, updates `escalation_flag=FALSE`, populates `resolved_at` and `resolved_by` | — |
| **6** | Engine | Sends confirmation to human agent | "✅ Escalation cleared for John Tan (+65 9123 4567). AI will resume handling their messages." |
| **7** | Customer | Sends a new message to the business WhatsApp | "Hi, when is my next appointment?" |
| **8** | Engine | Checks escalation gate, sees `escalation_flag=FALSE`, passes to agent loop | — |
| **9** | AI Agent | Handles the message normally, responds with appointment details | "Hi John! Your next appointment is scheduled for Saturday, 26 April at 10:00 AM. Let me know if you need to reschedule." |

### Visual Flow

```
Customer Escalated
      ↓
Human Agent Resolves Issue Directly (outside system)
      ↓
Human Agent replies to alert with "done"
      ↓
Engine detects reply-to-message (context.id matches alert_msg_id)
      ↓
Engine normalises "done" → "done" → MATCH
      ↓
Engine clears escalation_flag, logs resolution
      ↓
Engine sends confirmation: "✅ Escalation cleared..."
      ↓
Next customer message → AI resumes normally
```

---

## 6. Edge Cases

| Scenario | Input | Normalised | Result | Engine Response |
|----------|-------|-----------|--------|-----------------|
| **Uppercase keyword** | `"DONE"` | `"done"` | ✅ MATCH | Clears flag, sends confirmation |
| **Mixed case** | `"Resolved"` | `"resolved"` | ✅ MATCH | Clears flag, sends confirmation |
| **Leading/trailing spaces** | `"  done  "` | `"done"` | ✅ MATCH | Clears flag, sends confirmation |
| **Internal spaces** | `"res olved"` | `"resolved"` | ✅ MATCH | Clears flag, sends confirmation |
| **Internal spaces (multiple words)** | `"o k"` | `"ok"` | ✅ MATCH | Clears flag, sends confirmation |
| **Typo (extra character)** | `"resolvedd"` | `"resolvedd"` | ❌ NO MATCH | Sends help reply with keyword list |
| **Emoji only** | `"👍"` | `"👍"` | ❌ NO MATCH | Sends help reply with keyword list |
| **Sentence instead of keyword** | `"I'll call them"` | `"i'llcallthem"` | ❌ NO MATCH | Sends help reply with keyword list |
| **Keyword + extra words** | `"ok thanks"` | `"okthanks"` | ❌ NO MATCH | Sends help reply with keyword list |
| **Question (not a command)** | `"when did this come in?"` | `"whendidthiscomein?"` | ❌ NO MATCH | Sends help reply with keyword list |
| **Fresh message (no reply)** | `"done"` | N/A | C2 fails | "To clear an escalation, reply directly to the escalation alert message with one of: done, resolved, ok, handled..." |
| **Reply to unrelated message** | `"done"` (reply to customer message) | N/A | C3 fails | "No pending escalation found for this alert. It may have already been resolved or this message is not an escalation alert." |
| **Reply to already-resolved alert** | `"done"` (reply to old alert) | N/A | C3 fails | "No pending escalation found for this alert. It may have already been resolved or this message is not an escalation alert." |
| **Customer sends "resolved"** | `"resolved"` | `"resolved"` | C1 fails | Ignored — passes to normal agent pipeline (agent may respond "I'm here to help, what can I do for you?") |
| **Supabase UPDATE fails** | `"done"` | `"done"` | ✅ MATCH, then DB error | "⚠️ Failed to clear escalation — please try again or contact support." |
| **Alert send failed (alert_msg_id=NULL)** | `"done"` | N/A | C3 fails (no alert exists) | Human agent never received the alert, so they can't reply to it. Must clear flag manually in Supabase Studio. |

### Special Case: Multiple Pending Escalations

If a single customer has been escalated multiple times (e.g., escalated on Monday, resolved, escalated again on Tuesday, not yet resolved), the `escalation_tracking` table will have multiple rows for the same `phone_number`.

**Behaviour:**
- When the human agent replies to the Tuesday alert, the engine queries `WHERE alert_msg_id = <context.id> AND resolved_at IS NULL`.
- This returns exactly one row — the Tuesday escalation.
- Only that escalation is marked resolved.
- The Monday escalation row (already resolved) is untouched.

**No ambiguity** — the reply-to-message gesture uniquely identifies which escalation is being cleared via the `alert_msg_id`.

---

## 7. Out of Scope (Phase 1)

The following capabilities are explicitly excluded from the Phase 1 implementation and should NOT be built:

| Feature | Why Out of Scope |
|---------|------------------|
| **Fuzzy/approximate matching** | Typos like `"resolvedd"`, `"donee"`, `"okk"` are NOT auto-corrected. The keyword list is short and easy to remember. Fuzzy matching adds complexity and false positives. If a typo occurs, the help message teaches the correct keywords. |
| **LLM-based intent classification** | No Claude call, no agent loop. This is pure string matching. Keeps cost zero and latency <1 second. If the human agent's message is ambiguous, it fails the keyword match and triggers the help reply. |
| **Emoji-as-keyword** | 👍, ✅, ✔️ do NOT trigger escalation reset. Emojis are ambiguous across cultures and easy to send accidentally. Require explicit text keywords for auditability. |
| **Multi-language keywords** | English-only for Phase 1. Acceptable for Singapore (English + Singlish). If client base expands to Bahasa, Mandarin, Tamil markets, add localized keyword sets in Phase 2 via `keywords` table keyed by `client_id` and `language`. |
| **Confirmation step before reset** | No "Are you sure?" prompt. The human agent is explicitly replying to an escalation alert with a known keyword — the intent is clear. An extra confirmation step adds friction. If they reset by mistake, they can manually set the flag back in Supabase Studio. |
| **Bulk reset (clear all escalations at once)** | Out of scope. Each escalation must be explicitly resolved by replying to its specific alert. Bulk reset is a dangerous operation (what if one escalation isn't actually resolved?) and is better handled via a CRM dashboard action in Phase 2. |
| **Reset by any phone number other than `human_agent_number`** | Only the configured `human_agent_number` can clear escalations. If a client has multiple human agents, Phase 2 will introduce a `staff_numbers` array in the `clients` table. For now, one designated agent per client. |
| **WhatsApp label removal as reset trigger** | Meta does not support label-removal webhooks. Labels are client-side only (in WhatsApp Business Manager UI). The system cannot detect when a label is removed. Keyword-based reset is the only supported trigger. |
| **Auto-resume after X hours** | No time-based auto-reset. The escalation flag stays set until explicitly cleared by a human. This is intentional — escalations often require follow-up (refunds, callbacks, etc.) and auto-clearing would lose the escalation state. |
| **Undo reset** | If a human agent clears an escalation by mistake, they must manually set `escalation_flag=TRUE` in Supabase Studio. No "undo" command is provided. This is acceptable — accidental resets are rare and the audit trail (`escalation_tracking`) preserves the history. |

---

## 8. Dependencies

| Dependency | Requirement | Risk |
|------------|-------------|------|
| **Supabase: `escalation_tracking` table** | New table must be created via migration `003_escalation_tracking.sql` | None — table creation is deterministic |
| **Supabase: `customers.escalation_flag`** | Column already exists (Phase 1) | None — already live |
| **Meta Cloud API: `send_message()` must return `wamid`** | Function signature change from `bool` to `Optional[str]` | Low — backward compatible (existing callers check truthiness) |
| **Meta webhook: `message.context.id` extraction** | Webhook payload must include `context.id` when message is a reply | Low — Meta always includes this field for reply-to-message |
| **Engine: `message_handler.py` routing** | Must check `phone_number == human_agent_number` BEFORE logging to `interactions_log` | Low — insertion point is well-defined |
| **Engine: `reset_handler.py` (new file)** | Must be created from scratch | None — greenfield implementation |
| **Engine: `escalation_tool.py`** | Must capture and store `alert_msg_id` when escalation is triggered | Medium — requires change to existing function |

### Caller Audit for `send_message()` Return Type Change

All callers of `send_message()` must be audited to ensure they handle `Optional[str]` correctly. Current callers (as of 2026-04-22):

| Caller | Current Usage | Backward Compatible? |
|--------|---------------|---------------------|
| `escalation_tool.py` (escalate alert send) | `if result: log_outbound(...)` | ✅ Yes — `wamid` is truthy, `None` is falsy |
| `message_handler.py` (agent reply send) | `if result: log_outbound(...)` | ✅ Yes |
| `google_calendar.py` (booking confirmation send) | `if result: log_success(...)` | ✅ Yes |

**Conclusion:** All existing callers are backward compatible. The only caller that MUST change is `escalation_tool.py`, which now needs to capture and store the returned `wamid`.

---

## 9. Acceptance Criteria

| ID | Criterion | Type | Pass Condition |
|----|-----------|------|----------------|
| **AC-01** | Human agent replies to escalation alert with "done" → `escalation_flag` is set to `FALSE` in `customers` table | Pass/Fail | Flag cleared within 5 seconds of reply |
| **AC-02** | Human agent replies with "DONE" (uppercase) → escalation cleared | Pass/Fail | Flag cleared (case-insensitive match) |
| **AC-03** | Human agent replies with "res olved" (internal space) → escalation cleared | Pass/Fail | Flag cleared (normalisation removes space) |
| **AC-04** | Human agent replies with "resolvedd" (typo) → escalation NOT cleared, help reply sent | Pass/Fail | Help message lists approved keywords |
| **AC-05** | Human agent sends fresh message "done" (not a reply) → receives help: "reply directly to the alert" | Pass/Fail | No flag cleared, help message sent |
| **AC-06** | Human agent replies to unrelated message with "done" → receives "No pending escalation found" | Pass/Fail | No flag cleared, informative error sent |
| **AC-07** | Customer sends "resolved" to business number → ignored (not from `human_agent_number`) | Pass/Fail | Passes to agent pipeline, no reset triggered |
| **AC-08** | After reset, next customer message is handled by AI (not holding reply) | Pass/Fail | Agent responds normally, no escalation gate block |
| **AC-09** | `escalation_tracking.resolved_at` and `resolved_by` populated after successful reset | Pass/Fail | DB record updated with timestamp and agent phone |
| **AC-10** | Supabase UPDATE fails → human agent receives error message "Failed to clear escalation — please try again" | Pass/Fail | Error handling prevents silent failure |
| **AC-11** | Human agent replies with "o k" (space between letters) → escalation cleared | Pass/Fail | Normalisation collapses space, matches "ok" |
| **AC-12** | Human agent replies with "👍" (emoji) → help reply sent | Pass/Fail | Emoji NOT recognised, help message sent |
| **AC-13** | Human agent replies with "ok thanks" → help reply sent | Pass/Fail | Keyword + extra words NOT matched |
| **AC-14** | `send_message()` returns `wamid` string on success | Pass/Fail | Return type is `Optional[str]`, not `bool` |
| **AC-15** | Alert send fails (Meta API error) → `alert_msg_id=NULL` in `escalation_tracking`, human agent cannot reset via WhatsApp | Pass/Fail | Graceful degradation — no crash, manual reset required |

---

## 10. Test Scenarios

### Manual QA Test Plan (for @sdet-engineer)

| Scenario | Steps | Expected Result |
|----------|-------|-----------------|
| **Happy path** | 1. Trigger escalation manually in Supabase (`escalation_flag=TRUE`)<br>2. Insert test row in `escalation_tracking` with `alert_msg_id=<known wamid>`<br>3. Send WhatsApp message from `human_agent_number` as reply-to that `wamid` with text "done" | Engine clears flag, sends confirmation "✅ Escalation cleared..." |
| **Uppercase keyword** | Same as happy path, but reply with "DONE" | Flag cleared, confirmation sent |
| **Internal space** | Same as happy path, but reply with "res olved" | Flag cleared (normalised to "resolved") |
| **Typo** | Same as happy path, but reply with "resolvedd" | Help message sent, flag NOT cleared |
| **Fresh message (no reply)** | Send "done" as a fresh message (not reply-to) from `human_agent_number` | Help: "reply directly to the alert" |
| **Unrelated reply** | Reply to a customer message with "done" | "No pending escalation found" |
| **Customer sends keyword** | Customer (not human agent) sends "resolved" | Passes to agent, AI responds normally |
| **Already-resolved alert** | Reply to an old alert (where `resolved_at IS NOT NULL`) with "done" | "No pending escalation found" |
| **Emoji** | Reply with "👍" | Help message sent |
| **Multi-word input** | Reply with "ok thanks" | Help message sent (not matched) |

---

## 11. Future Enhancements (Phase 2+)

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| **Multi-language keywords** | Add Bahasa, Mandarin, Tamil keyword sets via `keywords` table | Medium |
| **Fuzzy matching** | Allow common typos (`"donee"` → `"done"`) with edit distance ≤1 | Low |
| **Multiple human agents** | Support `staff_numbers` array in `clients` table (any listed number can reset) | High |
| **Dashboard reset button** | CRM interface one-click reset (Phase 2 CRM) | High |
| **Auto-resume after follow-up** | After human agent sends a follow-up message to customer, auto-clear the flag after 24h | Medium |
| **Undo reset** | `@undo` command to revert accidental reset | Low |
| **Escalation notes** | Human agent adds resolution notes when clearing: `"done — issued refund"` | Medium |
| **Escalation analytics** | Dashboard showing escalation volume, resolution time, repeat escalations | Medium |

---

## Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-04-22 | @product-manager | Initial draft |
