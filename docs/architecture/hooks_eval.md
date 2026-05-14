# Hooks Evaluation — Improving Agent Accuracy and Determinism

**Date:** 2026-05-12 (Updated: 2026-05-12 — revised against official Anthropic hooks docs)  
**Status:** Evaluation  
**Owner:** software-architect  
**Purpose:** Evaluate hooks architecture for improving agent accuracy and determinism in high-stakes tool calls (booking creation, confirmation, cancellation, rescheduling)

---

## 0. Scope Disambiguation — Two Separate Hook Concerns

**This evaluation covers two distinct hook scopes that must not be conflated.**

### Scope A: Claude Code Hooks (Dev Workflow)

Claude Code hooks are configured in `.claude/settings.json` and fire at lifecycle events **during a developer's Claude Code session** (e.g., `PreToolUse` fires before Claude Code uses its own `Bash`, `Edit`, or `Write` tools). These hooks run on the developer's machine.

**What they control:** Claude Code's *own* tool calls during development (file edits, bash commands, git operations).  
**What they do NOT control:** The production Flow AI WhatsApp agent running on Railway.  
**Official schema:** `PreToolUse`, `PostToolUse`, `Stop`, `PostToolBatch`, etc. — configured via JSON in `.claude/settings.json`. Exit code 0 = proceed, exit code 2 = block. Structured JSON output controls `permissionDecision`, `updatedInput`, `updatedToolOutput`, `additionalContext`.  
**Relevant for us:** Enforcing AGENTS.md git discipline rules (commit before done, SDET merge gate, deploy branch push).

### Scope B: Engine Hooks (Production Runtime)

Engine hooks are Python functions that run inside the Flow AI FastAPI orchestration engine (`agent_runner.py`, `message_handler.py`) before and after the agent calls its tools (booking, calendar, escalation).

**What they control:** The production WhatsApp agent's tool calls in real customer conversations.  
**What they do NOT control:** Claude Code's development-time actions.  
**Relevant for us:** Eliminating non-determinism, preventing bad bookings, auto-escalating conflicts, observability.

**The original evaluation only addressed Scope B. This revision adds Scope A and updates Scope B with patterns from the official Anthropic docs.**

---

### Key Patterns from the Official Anthropic Docs That Change the Analysis

The official Claude Code hooks schema introduces several capabilities that the original evaluation didn't account for. These patterns should be adopted for the Python engine (Scope B), not just Claude Code (Scope A):

| Pattern | Official Schema Field | What It Enables |
|---------|----------------------|-----------------|
| Modify tool input before execution | `updatedInput` (PreToolUse) | Fix/sanitize inputs instead of just blocking. Slot TOCTOU: update slot window to available slot instead of returning error. |
| Replace what Claude sees after a tool | `updatedToolOutput` (PostToolUse) | Override `write_booking` result to add re-validation confirmation, reducing LLM confusion about booking state. |
| Inject context alongside tool result | `additionalContext` (PostToolUse) | Add "Slot re-validated at execution time: confirmed available" next to tool result without replacing it. Claude reads this before its next call. |
| Batch hook after all parallel tool calls | `PostToolBatch` | Run once after all tools in a batch complete, before the next Claude call. More efficient than per-tool hooks for multi-tool validation. |
| Block Claude from stopping | `Stop` hook with `decision: "block"` | Replace current reprompt-injection guardrails entirely. Stop hook checks "was booking flow completed?" and keeps Claude working if not. Far cleaner than injecting system messages mid-loop. |
| Prompt-based evaluation | `type: "prompt"` (Haiku model) | For complex validation that requires judgment (e.g., "is this cancellation request ambiguous?"), run a secondary Haiku call. Same cost profile as the agent, composable. |
| Multiple handlers, most restrictive wins | Parallel hook resolution | Multiple hooks can run concurrently; `deny` overrides `allow`. The Python engine currently evaluates sequentially — switch to concurrent evaluation with deny-wins merge. |
| HTTP hooks | `type: "http"` | The validation logic can live as FastAPI middleware endpoints, matching the engine's existing architecture. The agent loop POSTs to these endpoints before/after tool calls. |

---

## 1. Current State — How Tool Calls Flow Today

### 1.1 End-to-End Message Flow

```
Meta Webhook (webhook.py)
    ↓
Message Handler (message_handler.py)
    ↓ log inbound
    ↓ escalation gate (programmatic)
    ↓ customer upsert
    ↓ opt-out detection (backend bypass)
    ↓ fetch lead_time_days, appointment_windows
    ↓ build tool_dispatch (closures with db, client_config, phone_number injected)
    ↓ build tool_definitions (phase-based: Phase A vs Phase B)
    ↓
Context Builder (context_builder.py)
    ↓ fetch config + policies from Supabase
    ↓ fetch last 20 messages from interactions_log
    ↓ assemble system_message
    ↓
Agent Runner (agent_runner.py)
    ↓ call Anthropic/OpenAI with system + history + tools
    ↓ if stop_reason == "tool_use":
    ↓     for each tool_use block:
    ↓         _execute_tool() → tool_dispatch[name](**input)
    ↓         catch Exception → return error JSON to Claude
    ↓         append tool_result to messages
    ↓     loop (max 10 iterations)
    ↓ if stop_reason == "end_turn":
    ↓     extract final text
    ↓     apply booking guardrails (reprompt if confirmation language without write_booking)
    ↓     apply pending booking guardrail (reprompt if confirmation without confirm_booking)
    ↓     return text
    ↓
Meta Reply (message_handler.py)
    ↓ send_message()
    ↓ log outbound
```

**Key file locations:**
- Tool execution: `engine/core/agent_runner.py` lines 650–750 (`_execute_tool()`)
- Tool dispatch factory: `engine/core/tools/__init__.py` `build_tool_dispatch()` — injects db, client_config, phone_number, lead_time_days, appointment_windows into closures
- Tool definitions: `engine/core/tools/definitions.py` — static Anthropic-format dicts
- Tool implementations: `engine/core/tools/booking_tools.py`, `confirm_booking_tool.py`, `calendar_tools.py`, `escalation_tool.py`
- Backend bypass examples: `engine/core/message_handler.py` (opt-out detection lines 165–190), `engine/core/reset_handler.py` (escalation reset)

### 1.2 Current Guardrails

Two guardrails are implemented in `agent_runner.py` as reprompt-injection loops:

#### Booking Confirmation Guardrail (lines 140–240)
**Trigger:** `calendar_check_succeeded=True` AND `booking_write_succeeded=False` AND final text contains confirmation keywords ("your booking is confirmed", "all set", etc.)  
**Action:** Inject system correction message asking agent to call `write_booking` or `escalate_to_human`  
**Fallback:** After 1 reprompt, if still no `write_booking` call, escalate + return `_BOOKING_GUARDRAIL_FALLBACK`

#### Pending Booking Guardrail (lines 530–575)
**Trigger:** `pending_booking_id` exists AND `confirm_booking_succeeded=False` AND final text contains confirmation keywords  
**Action:** Inject system correction message requiring `confirm_booking(booking_id=...)` call  
**Fallback:** After 1 reprompt, if still no `confirm_booking` call, escalate + return `_BOOKING_GUARDRAIL_FALLBACK`

Both guardrails are **reactive** — they catch errors after the agent has already produced bad output, then attempt recovery via reprompt.

### 1.3 Current Backend Bypass Patterns

Two backend bypass implementations exist today:

#### Opt-Out Detection (`message_handler.py` lines 165–190)
**Pattern:** keyword match (`_OPT_OUT_KEYWORDS`) + precondition check (`_get_active_followup_booking()`)  
**Action:** mark `followup_stage='opted_out'` directly, send `OPT_OUT_REPLY`, return (agent never runs)  
**Rationale:** Intent is unambiguous + single deterministic action → no LLM needed

#### Escalation Reset (`reset_handler.py`)
**Pattern:** phone_number == human_agent_number + context_message_id matches escalation alert + keyword match ("done", "resolved", "ok")  
**Action:** clear `escalation_flag` + `escalation_notified`, mark `resolved_at` in `escalation_tracking`, sync to Sheets, return (agent never runs)  
**Rationale:** Intent is unambiguous (human agent closing loop) → no LLM needed

**Hard rule (from `AGENTS.md`):** "For high-frequency deterministic flows where intent is unambiguous (confirmation, cancellation, yes/no branching, single-action shortcuts), prefer backend logic over LLM orchestration."

---

## 2. Gap Analysis — Where Non-Determinism and Failures Occur

### 2.1 Race Condition Gaps

#### Gap 2.1a: Slot Availability TOCTOU (Time-of-Check Time-of-Use)
**Location:** `message_handler.py` → `agent_runner.py` → `write_booking()`  
**Failure mode:**
1. Agent calls `check_calendar_availability(date="2026-05-15")` → AM slot available
2. Agent tells customer "AM slot is available"
3. Concurrent booking from another customer takes the AM slot (real WhatsApp traffic or widget channel)
4. Agent calls `write_booking(slot_window="AM")` → **no conflict check, writes to Supabase**
5. `confirm_booking()` runs later → **conflict detected, booking cancelled**
6. Customer receives: "I'm sorry, the AM slot on 2026-05-15 is no longer available — it was just taken."

**Impact:** Customer frustration (they were told the slot was available), wasted agent turns, escalation

**Current mitigation:** None — `write_booking()` has no availability revalidation before DB write

**Frequency:** Low in Phase 1 (single client, low volume), **high risk in Phase 2** (multi-client, widget + WhatsApp parallel channels)

#### Gap 2.1b: Double-Booking on Rapid Confirmation
**Location:** `message_handler.py` → `agent_runner.py` → `confirm_booking()`  
**Failure mode:**
1. Customer sends "yes" to confirm pending booking HA-20260515-A3F2
2. WhatsApp delivers message twice (Meta double-delivery, known issue)
3. Two concurrent `handle_inbound_message()` background tasks start
4. Both read `pending_booking` from DB (status still `pending_confirmation`)
5. Both call `confirm_booking(booking_id="HA-20260515-A3F2")`
6. Both check slot availability (both see slot available)
7. Both create Google Calendar events (two events for the same slot)
8. Both update Supabase `booking_status='confirmed'`

**Impact:** Two calendar events for one booking, customer confusion, manual cleanup required

**Current mitigation:** `_get_customer_lock(phone_number)` serializes agent invocations per customer — **prevents this scenario**

**Status:** Already mitigated

### 2.2 Agent Tool Selection Gaps

#### Gap 2.2a: Affirmative Confirmation Not Bypassed (Phase B)
**Location:** `message_handler.py` lines 400–450 (Phase B flow)  
**Failure mode:**
1. Customer has pending booking, receives summary from agent
2. Customer replies "yes" (unambiguous affirmative)
3. **Agent still invoked** → LLM must interpret "yes" → call `confirm_booking`
4. LLM occasionally fails to call tool (produces text only, triggers pending booking guardrail)
5. Reprompt injected, second LLM call needed

**Impact:** Wasted LLM cost (2 calls instead of 0), added latency (~2–4 seconds), guardrail noise in logs

**Current mitigation:** Pending booking guardrail catches this via reprompt

**Backend bypass opportunity:** High — affirmative keywords ("yes", "ok", "confirm", "go ahead") + `pending_booking` exists + no question in message → deterministic intent

**Reference:** Opt-out detection already uses this pattern (keyword + precondition → direct action)

#### Gap 2.2b: Wrong Tool Selected (get_bookings vs confirm_booking)
**Location:** `agent_runner.py` tool_use loop  
**Failure mode:**
1. Customer has pending booking, says "yes"
2. Agent calls `get_customer_bookings(filter="all")` instead of `confirm_booking`
3. Returns booking list, agent sees pending booking in tool result
4. Second iteration: agent calls `confirm_booking`

**Impact:** Wasted LLM iteration, added latency

**Frequency:** Low (observed in eval logs, ~5% of Phase B affirmatives)

**Current mitigation:** System prompt emphasizes `confirm_booking` for affirmatives

**Hook opportunity:** Pre-LLM intent classifier could bypass LLM entirely for high-confidence affirmatives

### 2.3 Tool Execution Validation Gaps

#### Gap 2.3a: write_booking Success Not Validated
**Location:** `agent_runner.py` `_execute_tool()` lines 820–850  
**Failure mode:**
1. Agent calls `write_booking(...)`
2. Supabase INSERT succeeds, returns `booking_id="HA-20260515-A3F2"`
3. `_execute_tool()` serialises result to JSON, appends to messages
4. Agent receives tool_result, extracts `booking_id` from JSON
5. Agent replies: "✅ Your booking is confirmed! Reference: HA-20260515-A3F2"
6. **Agent never called `confirm_booking`** — calendar event not created, booking still `pending_confirmation`

**Impact:** Customer believes booking is confirmed, but it's not — escalation on booking day

**Current mitigation:** Booking confirmation guardrail catches this via reprompt (reactive)

**Hook opportunity:** Post-tool validation hook could assert `booking_id` is non-null before returning result to agent

#### Gap 2.3b: confirm_booking Conflict Not Escalated
**Location:** `confirm_booking_tool.py` lines 100–120  
**Failure mode:**
1. Agent calls `confirm_booking(booking_id="HA-20260515-A3F2")`
2. Slot conflict detected (slot taken between `write_booking` and `confirm_booking`)
3. `confirm_booking()` returns `{status: "conflict", error: "slot_no_longer_available", message: "..."}`
4. Agent reads tool_result, tells customer slot is no longer available
5. Agent offers to check alternative dates
6. **No escalation triggered** — customer now in multi-turn negotiation with agent

**Impact:** Customer frustration (they were told slot was available), potential abandonment

**Current mitigation:** None — escalation is optional (agent decision)

**Hook opportunity:** Post-tool hook on `confirm_booking` could auto-escalate on `status="conflict"`

### 2.4 Observability Gaps

#### Gap 2.4a: No Structured Audit Trail for Tool Calls
**Location:** `agent_runner.py` `_execute_tool()` lines 820–850  
**Current logging:** `logger.info(f"Executing tool: {tool_name!r} with input: {tool_input}")`  
**What's missing:**
- Tool execution outcome (success/failure)
- Tool execution duration
- Tool result summary (e.g., booking_id created, slot conflict detected)
- Correlation ID linking tool call to conversation turn

**Impact:** Hard to diagnose tool failures in production, no metrics for tool success rate

**Hook opportunity:** Pre-tool + post-tool audit hooks could log structured events to `api_usage` or new `tool_audit_log` table

#### Gap 2.4b: No Incident Recording for Tool Failures
**Location:** `agent_runner.py` `_execute_tool()` lines 840–850  
**Current behavior:** Exception caught, JSON error returned to agent, logged to `logger.error()`  
**What's missing:** No write to `api_incidents` table (only LLM provider failures are recorded)

**Impact:** Tool failures invisible to observability layer, no alerting, no aggregation

**Hook opportunity:** Post-tool error hook could call `log_incident(provider="tool_execution", error_type=..., client_id=...)`

---

## 3. Hook Catalogue — Types, Locations, and What They Fix

### 3.1 Pre-Tool-Call Hooks

**Definition:** Validation logic that runs **before** the tool function is invoked, after Claude has selected the tool and provided inputs.

**Location in codebase:** `agent_runner.py` `_execute_tool()` — insert between lines 830–835 (before `tool_fn(**tool_input)`)

**Implementation pattern:**
```python
async def _execute_tool(block: Any, tool_dispatch: dict, pre_hooks: dict = None) -> dict:
    tool_name = getattr(block, "name", "unknown")
    tool_input = getattr(block, "input", {})
    tool_id = getattr(block, "id", "")

    # NEW: Pre-tool hook
    if pre_hooks and tool_name in pre_hooks:
        validation_result = await pre_hooks[tool_name](tool_input)
        if validation_result.get("blocked"):
            logger.warning(f"Pre-hook blocked {tool_name}: {validation_result['reason']}")
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": json.dumps({
                    "error": "pre_validation_failed",
                    "message": validation_result["message"],
                }),
            }

    tool_fn = tool_dispatch.get(tool_name)
    # ... rest of existing logic
```

**What it fixes:**

| Hook | Fixes Gap | Implementation |
|------|-----------|----------------|
| `write_booking` pre-hook | 2.1a (slot TOCTOU) | Re-check slot availability immediately before Supabase INSERT. If unavailable, return error to agent without writing. |
| `confirm_booking` pre-hook | (none — validation already in tool) | Redundant — `confirm_booking` already checks slot conflict before calendar event creation |
| `escalate_to_human` pre-hook | (nice-to-have) | Check if customer already escalated. If `escalation_flag=True`, return idempotent success (prevents duplicate escalation alerts). |

**Tradeoff:**
- **Complexity cost:** Medium — requires hook registry in `agent_runner.py`, hook functions in `core/tools/hooks.py`, hook dispatch map passed to `_execute_tool()`
- **Reliability gain:** High for `write_booking` (eliminates slot TOCTOU race), Low for others
- **Performance cost:** 1 additional calendar API call per `write_booking` invocation (~200–500ms)

**Recommendation:** Implement `write_booking` pre-hook only. Other pre-hooks have low ROI.

---

### 3.2 Post-Tool-Call Hooks

**Definition:** Validation logic that runs **after** the tool function completes, before the result is returned to Claude.

**Location in codebase:** `agent_runner.py` `_execute_tool()` — insert between lines 845–850 (after `result = await tool_fn(**tool_input)`, before `content = json.dumps(result)`)

**Implementation pattern:**
```python
async def _execute_tool(block: Any, tool_dispatch: dict, post_hooks: dict = None) -> dict:
    # ... existing pre-hook logic
    # ... existing tool_fn(**tool_input) call

    # NEW: Post-tool hook
    if post_hooks and tool_name in post_hooks:
        validation_result = await post_hooks[tool_name](result, tool_input)
        if validation_result.get("override"):
            logger.warning(f"Post-hook overrode {tool_name}: {validation_result['reason']}")
            result = validation_result["new_result"]

    content = json.dumps(result) if not isinstance(result, str) else result
    # ... rest of existing logic
```

**What it fixes:**

| Hook | Fixes Gap | Implementation |
|------|-----------|----------------|
| `write_booking` post-hook | 2.3a (booking_id not validated) | Assert `result.get("booking_id")` is non-null and matches `r"^[A-Z]{2,4}-\d{8}-[A-Z0-9]{4}$"`. If missing or malformed, override result with error and auto-escalate. |
| `confirm_booking` post-hook | 2.3b (conflict not escalated) | If `result.get("status") == "conflict"`, auto-call `escalate_to_human(reason="Slot conflict during confirmation")` and append escalation notice to result message. |
| All tools post-hook (audit) | 2.4a, 2.4b (observability) | Log tool execution outcome to structured audit log (success/failure, duration, result summary). On error, call `log_incident()`. |

**Tradeoff:**
- **Complexity cost:** Medium — same hook infrastructure as pre-hooks
- **Reliability gain:** High for `write_booking` (catches missing booking_id before agent sees it), Medium for `confirm_booking` (auto-escalates conflicts), High for audit (full observability)
- **Performance cost:** Negligible (validation + logging only, no external calls)

**Recommendation:** Implement all three post-hooks. High ROI across reliability and observability.

---

### 3.3 Intent Classification Hooks

**Definition:** Pre-LLM logic that detects high-confidence intent and bypasses the agent entirely.

**Location in codebase:** `message_handler.py` — insert after opt-out detection (line 190), before context builder invocation (line 300)

**Implementation pattern:**
```python
async def handle_inbound_message(...):
    # ... existing escalation gate, customer upsert, opt-out detection

    # NEW: Intent classification hook (Phase B affirmative confirmation)
    pending_booking = await _get_latest_pending_booking(db, phone_number)
    if pending_booking and _is_affirmative_keyword(message_text):
        logger.info(
            f"Intent hook: affirmative confirmation detected for {phone_number}, "
            f"bypassing agent, calling confirm_booking directly"
        )
        tool_dispatch = build_tool_dispatch(db, client_config, phone_number, lead_days, windows)
        confirm_result = await tool_dispatch["confirm_booking"](pending_booking["booking_id"])

        if confirm_result.get("status") == "confirmed":
            agent_reply = confirm_result["message"]
        elif confirm_result.get("status") == "conflict":
            # Slot no longer available — escalate + send holding message
            await tool_dispatch["escalate_to_human"](
                reason=f"Slot conflict on confirmation for booking {pending_booking['booking_id']}"
            )
            agent_reply = confirm_result["message"] + "\n\nOur team will reach out to help you reschedule."
        else:
            # Other error — escalate + send fallback
            await tool_dispatch["escalate_to_human"](
                reason=f"confirm_booking failed for {pending_booking['booking_id']}: {confirm_result.get('error')}"
            )
            agent_reply = FALLBACK_REPLY

        _now = datetime.now(timezone.utc).isoformat()
        await send_message(client_config, phone_number, agent_reply)
        await db.table("interactions_log").insert({
            "timestamp": _now,
            "phone_number": phone_number,
            "direction": "outbound",
            "message_text": agent_reply,
            "message_type": "text",
        }).execute()
        return  # Agent never runs
    
    # ... existing context builder + agent invocation
```

**What it fixes:**

| Hook | Fixes Gap | Implementation |
|------|-----------|----------------|
| Affirmative confirmation (Phase B) | 2.2a (LLM cost for deterministic intent) | Keyword match (`_is_affirmative_keyword()`) + `pending_booking` exists + no question mark in message → call `confirm_booking` directly, skip LLM |
| Cancel booking request | (future gap) | Keyword match ("cancel", "cancel my booking") + `get_customer_bookings(filter="upcoming")` returns 1 booking → call `cancel_booking` directly (tool not yet implemented) |

**Affirmative keyword list (proposed):**
```python
_AFFIRMATIVE_KEYWORDS = frozenset({
    "yes", "yep", "yeah", "ok", "okay", "confirm", "confirmed", "correct", "right",
    "go ahead", "proceed", "book it", "sounds good", "looks good", "all good",
    "sure", "definitely", "absolutely", "👍",
})
```

**Tradeoff:**
- **Complexity cost:** Low — similar pattern to opt-out detection (already implemented)
- **Reliability gain:** High — eliminates LLM confusion on affirmatives, always calls correct tool
- **Cost savings:** High — saves 1–2 LLM calls per Phase B confirmation (currently 100% of Phase B flow)
- **Latency improvement:** 2–4 seconds per confirmation (LLM roundtrip eliminated)
- **Risk:** False positives if customer says "yes" to a question instead of confirming booking. Mitigation: require no question mark in message + no agent question in last outbound.

**Recommendation:** Implement affirmative confirmation hook immediately. Highest ROI of all hooks.

---

### 3.4 Guard Hooks

**Definition:** Programmatic checks that **prevent** the agent from making a bad decision by altering available tools or blocking certain actions.

**Location in codebase:** `message_handler.py` — modify `build_tool_definitions(pending_booking)` logic (line 380)

**Implementation pattern:**
```python
def build_tool_definitions(pending_booking: dict | None, customer_escalated: bool = False) -> list[dict]:
    """
    Build phase-appropriate tool list with guard logic.

    Args:
        pending_booking: Latest pending_confirmation booking for this customer.
        customer_escalated: True if customer.escalation_flag is True.

    Returns:
        List of Anthropic tool definition dicts.
    """
    if customer_escalated:
        # Guard: Escalated customers get ZERO tools — agent structurally cannot call anything
        return []

    if pending_booking:
        # Phase B — confirm_booking, get_customer_bookings, escalate_to_human
        return [
            definitions._CONFIRM_BOOKING_TOOL,
            definitions._GET_CUSTOMER_BOOKINGS_TOOL,
            definitions._ESCALATE_TO_HUMAN_TOOL,
        ]
    else:
        # Phase A — check_calendar, write_booking, get_bookings, escalate
        return [
            definitions._CHECK_CALENDAR_TOOL,
            definitions._WRITE_BOOKING_TOOL,
            definitions._GET_CUSTOMER_BOOKINGS_TOOL,
            definitions._ESCALATE_TO_HUMAN_TOOL,
        ]
```

**What it fixes:**

| Guard | Fixes Gap | Implementation |
|-------|-----------|----------------|
| Phase-based tool exclusion | (already implemented) | Phase B excludes `write_booking` (prevents double-booking). Phase A excludes `confirm_booking` (prevents confirming nonexistent booking). |
| Escalated customer zero-tools | (nice-to-have) | If `escalation_flag=True`, return empty tool list. Agent structurally cannot call any tools. Forces pure conversational response or escalation message reinforcement. |
| Already-cancelled booking guard | (future gap) | If customer has `cancelled` booking and requests cancellation again, exclude `cancel_booking` tool, force agent to explain booking is already cancelled. |

**Tradeoff:**
- **Complexity cost:** Very Low — existing pattern, just extends `build_tool_definitions()` logic
- **Reliability gain:** High — structural prevention (agent cannot physically call excluded tools)
- **Risk:** None — exclusion is safe (no tool means no action)

**Recommendation:** Implement escalated customer zero-tools guard. Prevents agent from attempting actions when human handoff has already occurred.

---

### 3.5 Audit/Logging Hooks

**Definition:** Observability hooks that log every tool invocation and outcome for monitoring, debugging, and replay.

**Location in codebase:** `agent_runner.py` `_execute_tool()` — insert at start (line 830) and after tool execution (line 845)

**Implementation pattern:**
```python
async def _execute_tool(block: Any, tool_dispatch: dict, client_id: str = "") -> dict:
    tool_name = getattr(block, "name", "unknown")
    tool_input = getattr(block, "input", {})
    tool_id = getattr(block, "id", "")

    # NEW: Pre-execution audit log
    start_time = time.perf_counter()
    logger.info(f"[TOOL_AUDIT] {client_id} | {tool_name} | input={tool_input} | tool_use_id={tool_id}")

    tool_fn = tool_dispatch.get(tool_name)
    if tool_fn is None:
        logger.warning(f"Tool not found: {tool_name}")
        content = json.dumps({"error": "tool_not_found", "tool": tool_name})
    else:
        try:
            result = await tool_fn(**tool_input)
            content = json.dumps(result) if not isinstance(result, str) else result
            
            # NEW: Post-execution audit log
            duration_ms = (time.perf_counter() - start_time) * 1000
            result_summary = _summarize_tool_result(tool_name, result)
            logger.info(
                f"[TOOL_AUDIT] {client_id} | {tool_name} | status=success | "
                f"duration={duration_ms:.0f}ms | {result_summary}"
            )

            # NEW: Write to audit table (async, fire-and-forget)
            asyncio.create_task(_log_tool_execution(
                client_id=client_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=result,
                status="success",
                duration_ms=duration_ms,
            ))

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"[TOOL_AUDIT] {client_id} | {tool_name} | status=error | "
                f"duration={duration_ms:.0f}ms | error={e}",
                exc_info=True,
            )
            content = json.dumps({"error": "tool_execution_failed", "message": str(e)})

            # NEW: Log incident for tool failure
            asyncio.create_task(log_incident(
                provider="tool_execution",
                error_type=f"{tool_name}_failed",
                error_message=str(e),
                client_id=client_id,
                context={"tool_input": tool_input},
            ))

    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": content,
    }
```

**What it fixes:**

| Hook | Fixes Gap | Implementation |
|------|-----------|----------------|
| Structured tool audit log | 2.4a (no audit trail) | Log every tool call with: `client_id`, `tool_name`, `tool_input`, `tool_output`, `status`, `duration_ms`, `timestamp`. Store in new Supabase table `tool_audit_log` (shared DB). |
| Tool failure incident recording | 2.4b (tool failures invisible) | Call `log_incident(provider="tool_execution", ...)` on every tool exception. Makes tool failures visible in `api_incidents` table and alerting pipeline. |
| Tool result summary | (nice-to-have) | Extract key fields from tool result for log readability: `write_booking` → `booking_id`, `confirm_booking` → `status` + `calendar_event_id`, `check_calendar` → `am_available` + `pm_available`. |

**Tradeoff:**
- **Complexity cost:** Low — mostly logging additions, one new Supabase table
- **Reliability gain:** None (does not prevent failures)
- **Observability gain:** Very High — full tool execution history, enables debugging, metrics, alerting
- **Performance cost:** Negligible (async fire-and-forget writes)

**Recommendation:** Implement audit hooks immediately. Critical for production observability.

---

### 3.6 Stop Hook — Replace Reprompt Guardrails (NEW — from Anthropic docs)

**Definition:** A hook that runs after Claude produces its final text response, before the turn ends. Can block Claude from stopping by returning `decision: "block"` with a `reason`.

**What the official docs revealed:** The current reprompt-injection guardrails in `agent_runner.py` (lines 140–575) are a manual reimplementation of what a `Stop` hook provides natively. The Stop hook pattern is cleaner, more composable, and avoids mutation of the message history mid-loop.

**Current approach (reactive reprompt):**
```python
# agent_runner.py lines 140–240 — booking confirmation guardrail
if calendar_check_succeeded and not booking_write_succeeded:
    if any(keyword in final_text.lower() for keyword in CONFIRMATION_KEYWORDS):
        # Inject system correction message, re-run agent loop
        messages.append({"role": "user", "content": "_BOOKING_GUARDRAIL_REPROMPT"})
        # ... repeat loop
```

**Proposed Stop hook approach (declarative):**
```python
async def _stop_hook(
    final_text: str,
    agent_state: AgentState,
    tool_dispatch: dict,
    client_id: str,
) -> dict:
    """
    Run after agent produces final text. Return {"decision": "block", "reason": "..."} 
    to keep agent working, or {} to allow it to stop.
    
    Mirrors Anthropic's Stop hook: decision: "block" prevents stopping,
    reason is fed back to Claude as its next instruction.
    """
    # Gate 1: Was write_booking called but confirm_booking wasn't?
    if agent_state.booking_write_succeeded and not agent_state.confirm_booking_succeeded:
        if any(k in final_text.lower() for k in _CONFIRMATION_KEYWORDS):
            return {
                "decision": "block",
                "reason": (
                    "You wrote the booking but haven't called confirm_booking yet. "
                    f"Call confirm_booking(booking_id='{agent_state.last_booking_id}') "
                    "before telling the customer their booking is confirmed."
                )
            }

    # Gate 2: Was calendar checked but write_booking never called?
    if agent_state.calendar_check_succeeded and not agent_state.booking_write_succeeded:
        if any(k in final_text.lower() for k in _CONFIRMATION_KEYWORDS):
            return {
                "decision": "block",
                "reason": (
                    "You checked calendar availability and used confirmation language, "
                    "but write_booking was never called. Call write_booking() first, "
                    "then confirm_booking(), before confirming to the customer."
                )
            }

    return {}  # Allow Claude to stop
```

**What it fixes:**
- Eliminates mutable message-history injection mid-loop (current approach is fragile)
- Declarative: each gate is a pure function, testable in isolation
- Composable: multiple stop hooks can run; all must return `{}` for Claude to stop
- Mirrors official Anthropic pattern — future maintainers will recognise this

**Tradeoff:**
- **Complexity cost:** Medium — requires refactoring current guardrail logic into stop hook functions
- **Reliability gain:** Same as current guardrails (catches same errors), but more maintainable
- **Risk:** Refactoring guardrails has regression risk — requires full test coverage before shipping

**Recommendation:** Refactor current reprompt guardrails into a Stop hook in Phase 2 (after Phase 1 intent hooks reduce guardrail trigger frequency first).

---

### 3.7 `updatedInput` Pattern — Modify Tool Inputs Before Execution (NEW — from Anthropic docs)

**Definition:** Instead of blocking a tool call when pre-validation finds a problem, MODIFY the tool input to fix the problem and allow execution to proceed.

**What the official docs revealed:** The `updatedInput` field in `PreToolUse` allows rewriting the tool's input parameters before execution. This is more powerful than block-only validation.

**Application to Flow AI — Slot TOCTOU fix alternative:**

Instead of blocking `write_booking` when slot TOCTOU is detected:
```python
# Current approach: BLOCK (original evaluation)
if slot_not_available:
    return {"blocked": True, "reason": "Slot no longer available"}
```

Use `updatedInput` to fix the input:
```python
# New approach: MODIFY (updatedInput pattern)
async def pre_write_booking_hook(tool_input: dict, db, client_config) -> dict:
    """
    Before write_booking executes, re-validate the requested slot.
    If unavailable, find the next available slot and update the input.
    Returns: {"updatedInput": {...}} to modify, {} to proceed unchanged,
             {"blocked": True, "reason": "..."} to deny if no slots available.
    """
    requested_date = tool_input.get("booking_date")
    requested_window = tool_input.get("slot_window")  # "AM" or "PM"
    
    # Re-check slot availability at execution time
    availability = await check_slot_availability(db, client_config, requested_date)
    
    if availability.get(requested_window):
        # Slot still available — proceed unchanged, inject additionalContext
        return {
            "additionalContext": f"Slot {requested_window} on {requested_date} re-validated at execution time: confirmed available."
        }
    
    # Slot taken — try to find an alternative
    alternative = next(
        (w for w in ["AM", "PM"] if w != requested_window and availability.get(w)),
        None
    )
    
    if alternative:
        # Found alternative — modify input instead of blocking
        logger.warning(
            f"Slot TOCTOU: {requested_window} on {requested_date} no longer available. "
            f"Updating input to {alternative}."
        )
        updated = {**tool_input, "slot_window": alternative}
        return {
            "updatedInput": updated,
            "additionalContext": (
                f"The originally requested {requested_window} slot on {requested_date} "
                f"was taken between availability check and booking. "
                f"I've automatically updated your booking to the {alternative} slot."
            )
        }
    
    # No slots available — block
    return {
        "blocked": True,
        "reason": f"Both AM and PM slots on {requested_date} are now fully booked. No alternative available.",
        "message": f"I'm sorry, both slots on {requested_date} have just been taken. Shall we try another date?"
    }
```

**Why this is better than block-only:**
- Customer gets a booking even if their first-choice slot was taken (better UX)
- `additionalContext` tells Claude what changed, preventing confusion
- Block is still available for the no-slots-available case

**Tradeoff:**
- **Complexity cost:** High — requires slot re-validation logic + alternative selection
- **UX gain:** High — automatic slot recovery instead of full rebooking flow
- **Risk:** Medium — the agent must communicate the slot change to the customer; requires prompt context injection (`additionalContext`) to work correctly

**Recommendation:** Implement in Phase 2. The `additionalContext` injection is required alongside `updatedInput` to work correctly.

---

### 3.8 `additionalContext` Pattern — Inject Context Alongside Tool Results (NEW — from Anthropic docs)

**Definition:** After a tool executes, inject a string into Claude's context window alongside the tool result. Claude reads this on its next call. Does not replace the tool output — adds to it.

**What the official docs revealed:** `additionalContext` can be returned from any PostToolUse hook. It's delivered as a system reminder injected next to the tool result, not as a chat message. Claude reads it but the customer doesn't see it.

**Application to Flow AI:**

```python
async def post_write_booking_hook(result: dict, tool_input: dict) -> dict:
    """
    After write_booking succeeds, inject context reminding Claude that
    confirm_booking must be called next.
    """
    booking_id = result.get("booking_id")
    if not booking_id:
        return {
            "override": True,
            "new_result": {"error": "booking_id_missing", "message": "Booking creation failed."},
            "additionalContext": "write_booking did not return a booking_id. Do not tell the customer their booking is confirmed. Escalate to human."
        }
    
    return {
        "additionalContext": (
            f"write_booking succeeded and created booking_id={booking_id}. "
            "IMPORTANT: This is a PENDING booking — not yet confirmed. "
            f"You must now call confirm_booking(booking_id='{booking_id}') to create the calendar event. "
            "Do NOT tell the customer their booking is confirmed until confirm_booking succeeds."
        )
    }
```

**Why this matters:** Currently, the agent confuses `write_booking` success (pending state) with booking confirmation. `additionalContext` makes the state unambiguous in Claude's context without modifying the tool output schema.

**Tradeoff:**
- **Complexity cost:** Low — small addition to post-tool hook
- **Reliability gain:** High — directly addresses the agent state confusion that triggers the booking confirmation guardrail
- **Risk:** None — additive only, doesn't break existing output

**Recommendation:** Implement in Phase 1 alongside audit hooks. Very low cost, high signal.

---

### 3.9 Prompt-Based Hooks — Secondary Claude Evaluation (NEW — from Anthropic docs)

**Definition:** Instead of a deterministic rule, use a secondary Haiku call to evaluate a complex condition. The model returns `{"ok": true}` or `{"ok": false, "reason": "..."}`.

**What the official docs revealed:** `type: "prompt"` hooks are a first-class pattern, defaulting to Haiku (fast, cheap). They're designed for exactly the cases where deterministic rules aren't sufficient.

**Application to Flow AI — Reschedule Request Disambiguation:**

When a customer has an upcoming confirmed booking and sends a message, the agent must decide: is this a reschedule request or a service inquiry? This is ambiguous and the LLM sometimes gets it wrong.

```python
# Future: PostToolUse hook on get_customer_bookings — prompt-based evaluation
prompt_hook = {
    "type": "prompt",
    "model": "claude-haiku-4-5-20251001",
    "prompt": """
You are evaluating whether a customer message is a reschedule request.

Customer message: {message_text}
Customer's upcoming confirmed booking: {booking_summary}

Is the customer asking to reschedule this booking?

Respond ONLY with JSON: {"ok": true} if this is NOT a reschedule request (let normal flow continue),
or {"ok": false, "reason": "Customer is requesting to reschedule. Confirmed booking: {booking_id} on {booking_date}"} 
if this IS a reschedule request (so the agent is given a clear reschedule instruction).
"""
}
```

**Tradeoff:**
- **Complexity cost:** Medium — prompt engineering required, adds one Haiku call per ambiguous case
- **Reliability gain:** Medium — reduces wrong tool selection on reschedule flows
- **Cost:** ~$0.01 per evaluation (Haiku pricing)
- **Risk:** Medium — prompt-based hooks can themselves fail; requires fallback to normal agent flow

**Recommendation:** Defer to Phase 3. Reschedule tool not yet built. Design the hook when building reschedule.

---

## 4. Scope A: Claude Code Dev Workflow Hooks (NEW — from Anthropic docs)

These hooks live in `.claude/settings.json` and enforce the hard rules from `AGENTS.md` during development sessions. They do NOT affect the production engine.

### 4.1 SDET Merge Gate Hook (Enforces git worktree discipline hard rule)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(git merge feat/*)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/check-commits-before-merge.sh"
          }
        ]
      }
    ]
  }
}
```

**Script:** `.claude/hooks/check-commits-before-merge.sh`
```bash
#!/bin/bash
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

# Extract branch name from git merge command
BRANCH=$(echo "$COMMAND" | grep -oP 'feat/\S+')
if [ -z "$BRANCH" ]; then
  exit 0  # Not a feature branch merge, proceed
fi

# Check if the branch has any commits not on main
COMMIT_COUNT=$(git log main.."$BRANCH" --oneline 2>/dev/null | wc -l | tr -d ' ')

if [ "$COMMIT_COUNT" -eq 0 ]; then
  echo "SDET MERGE GATE BLOCKED: Branch '$BRANCH' has no commits not on main." >&2
  echo "Run 'git log main..$BRANCH --oneline' to verify." >&2
  echo "The software-engineer must git add + git commit inside the worktree first." >&2
  exit 2
fi

exit 0
```

**What it enforces:** The SDET merge gate hard rule from AGENTS.md — blocks `git merge feat/*` if the branch has no commits. Prevents the silent loss of uncommitted worktree work that caused two incidents on 2026-04-22 and 2026-05-09.

---

### 4.2 Deploy Branch Push Reminder Hook (Enforces deploy branch push hard rule)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(git merge *)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/remind-deploy-push.sh"
          }
        ]
      }
    ]
  }
}
```

**Script:** `.claude/hooks/remind-deploy-push.sh`
```bash
#!/bin/bash
INPUT=$(cat)

# After any git merge, inject a reminder about the deploy branch push rule
jq -n '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: "DEPLOY REMINDER: git merge to master does not deploy to Railway. If this change is intended for production, push the relevant deploy branch: git push origin master:deploy/hey-aircon and/or git push origin master:deploy/flow-ai. Merged to master ≠ deployed."
  }
}'
```

**What it enforces:** The Deploy Branch Push Rule from AGENTS.md — ensures Claude Code is reminded to push deploy branches after merging to master. Prevents the "merged but not deployed" pattern that caused 3 debug rounds on 2026-05-09.

---

### 4.3 Protected Files Hook (Prevents accidental production config edits)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/protect-files.sh"
          }
        ]
      }
    ]
  }
}
```

**Script:** `.claude/hooks/protect-files.sh`
```bash
#!/bin/bash
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

PROTECTED_PATTERNS=(
  "railway.json"          # Railway deploy config
  "Procfile"              # Process definitions
  ".env"                  # Env files
  "clients/hey-aircon/invoices/"  # Invoice outputs
)

for pattern in "${PROTECTED_PATTERNS[@]}"; do
  if [[ "$FILE_PATH" == *"$pattern"* ]]; then
    echo "PROTECTED FILE: $FILE_PATH matches '$pattern'. Edit manually if intentional." >&2
    exit 2
  fi
done

exit 0
```

---

### 4.4 Implementation: `.claude/settings.json`

All three hooks should be added to `.claude/settings.json` (project-scoped, committed to repo):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(git merge feat/*)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/check-commits-before-merge.sh"
          }
        ]
      },
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/protect-files.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(git merge *)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/remind-deploy-push.sh"
          }
        ]
      }
    ]
  }
}
```

**Note:** Hook scripts must be executable (`chmod +x .claude/hooks/*.sh`). Add `.claude/hooks/` as a directory to the repo. Scripts committed alongside settings.json.

---

## 5. Tradeoffs — Complexity vs Reliability for Each Hook Type

### Summary Table

| Hook Type | Scope | Complexity Cost | Reliability Gain | Observability Gain | Performance Cost | Recommended |
|-----------|-------|----------------|------------------|-------------------|------------------|-------------|
| **Intent: affirmative confirmation bypass** | Engine | Low | High (eliminates LLM confusion) | None | None (saves cost) | ✅ Phase 1 — highest ROI |
| **Post-tool: `additionalContext` on write_booking** | Engine | Low | High (prevents agent state confusion) | None | None | ✅ Phase 1 |
| **Post-tool: audit logging** | Engine | Low | None | Very High | Negligible | ✅ Phase 1 — critical |
| **Guard: escalated customer zero-tools** | Engine | Very Low | High (structural prevention) | None | None | ✅ Phase 1 |
| **Post-tool: write_booking booking_id validation** | Engine | Medium | High (catches missing booking_id) | None | None | ✅ Phase 1 |
| **Post-tool: confirm_booking auto-escalate** | Engine | Medium | Medium (auto-escalates conflicts) | None | None | ✅ Phase 1 |
| **Claude Code: SDET merge gate hook** | Dev workflow | Low | High (prevents worktree commit loss) | None | None | ✅ Phase 1 — critical |
| **Claude Code: deploy branch push reminder** | Dev workflow | Low | High (prevents deploy/code gap) | None | None | ✅ Phase 1 |
| **Claude Code: protected files hook** | Dev workflow | Low | Medium (prevents accidental edits) | None | None | ✅ Phase 1 |
| **Stop hook: replace reprompt guardrails** | Engine | Medium | Same as current (cleaner impl) | None | None | ✅ Phase 2 — refactor |
| **Pre-tool: `updatedInput` slot TOCTOU fix** | Engine | High | High (eliminates TOCTOU + better UX) | None | Medium (calendar call) | ✅ Phase 2 |
| **Prompt-based: reschedule disambiguation** | Engine | Medium | Medium (reduces wrong tool selection) | None | Low (Haiku call) | ⏸️ Phase 3 — reschedule tool first |
| **Intent: cancel booking bypass** | Engine | Low | Medium (future gap) | None | None | ⏸️ Phase 3 — cancel tool first |
| **Guard: already-cancelled booking** | Engine | Very Low | Low (future gap) | None | None | ⏸️ Phase 3 |
| **Pre-tool: escalate_to_human idempotency** | Engine | Low | Low (minor edge case) | None | None | ❌ No (low ROI) |

---

## 6. Recommendation — Implementation Order

### Phase 0 — Dev Workflow Hooks (Zero Production Risk, Implement Immediately)

**Priority 0: Claude Code Hooks — Git Discipline Enforcement**  
**Files:** `.claude/settings.json` (new), `.claude/hooks/check-commits-before-merge.sh` (new), `.claude/hooks/remind-deploy-push.sh` (new), `.claude/hooks/protect-files.sh` (new)  
**Rationale:** SDET merge gate and deploy branch push rule have both been violated in production despite being documented in AGENTS.md. Automating them via Claude Code hooks eliminates human compliance dependency.  
**Complexity:** Low — shell scripts + one JSON config  
**Risk:** None (dev workflow only, no production impact)  
**Testing:** Trigger each hook manually via Claude Code, confirm exit code 2 blocks the operation  
**Done criteria:** `git merge feat/empty-branch` is blocked. `git merge feat/committed-branch` proceeds. After merge, `additionalContext` appears reminding about deploy branch push.

---

### Phase 1 — Engine Hooks: Highest ROI, Lowest Risk (Implement First)

**Priority 1: Affirmative Confirmation Intent Hook**  
**File:** `engine/core/message_handler.py`  
**Lines:** Insert after line 190 (opt-out detection), before line 300 (context builder)  
**Rationale:** Highest ROI — eliminates 100% of LLM calls for affirmatives, saves cost, adds determinism, reduces latency by 2–4 seconds per confirmation  
**Complexity:** Low (same pattern as opt-out detection)  
**Risk:** Low (false positives mitigated by `pending_booking` precondition)

**Priority 2: `additionalContext` Injection on write_booking**  
**File:** `engine/core/agent_runner.py` `_execute_tool()`  
**Lines:** Insert after `tool_fn(**tool_input)` resolves for `write_booking`  
**Rationale:** Directly prevents the "write succeeded but confirm not called" class of booking failures. Low effort, high signal.  
**Complexity:** Low  
**Risk:** None (additive only)

**Priority 3: Audit Logging Hooks (Pre + Post)**  
**File:** `engine/core/agent_runner.py` `_execute_tool()`  
**Lines:** Insert at start and after tool execution  
**Rationale:** Critical for production observability — every tool call in `tool_audit_log`, errors in `api_incidents`  
**Complexity:** Low (mostly logging + 1 new Supabase table)  
**Risk:** None

**Priority 4: Post-Tool Validation Hooks**  
**File:** `engine/core/agent_runner.py` `_execute_tool()`  
**Hooks:**
- `write_booking`: assert `booking_id` non-null and well-formed
- `confirm_booking`: auto-escalate on `status="conflict"`  

**Complexity:** Medium  
**Risk:** Low (validation only)

**Priority 5: Guard — Escalated Customer Zero-Tools**  
**File:** `engine/core/message_handler.py` `build_tool_definitions()`  
**Lines:** Modify line 380 (add `customer_escalated` parameter, return empty list if True)  
**Complexity:** Very Low  
**Risk:** None

---

### Phase 2 — Engine Hooks: High Impact, Medium Complexity (After Phase 1 Validated)

**Priority 6: Stop Hook — Replace Reprompt Guardrails**  
**File:** `engine/core/agent_runner.py` — refactor existing reprompt guardrails into `_stop_hook()`  
**Rationale:** Current reprompt-injection guardrails (lines 140–575) are fragile and hard to test. Stop hook pattern is cleaner, composable, follows official Anthropic pattern.  
**Complexity:** Medium (refactor, not new logic — same gates, different pattern)  
**Risk:** Medium (regression risk — requires full coverage before shipping)  
**Note:** Phase 1 `additionalContext` injection should reduce how often Stop hooks fire; implement Phase 1 first

**Priority 7: Pre-Tool `updatedInput` Slot TOCTOU Fix**  
**File:** `engine/core/agent_runner.py` `_execute_tool()`  
**Lines:** Insert before `tool_fn(**tool_input)` for `write_booking`  
**Rationale:** Eliminates slot TOCTOU race condition with better UX (auto-recover to alternative slot via `updatedInput` rather than blocking + rebooking flow)  
**Complexity:** High (slot re-validation + alternative selection + `additionalContext` injection)  
**Risk:** Medium (adds 200–500ms latency per `write_booking` call; measure P95 before shipping)  
**Must validate:** P95 `write_booking` latency stays below 1s after calendar re-check added

---

### Phase 3 — Future Enhancements (After Cancel/Reschedule Tools Built)

**Priority 8: Cancel Booking Intent Hook**  
**Dependencies:** `cancel_booking` tool implemented  
**Complexity:** Low (same pattern as affirmative bypass)

**Priority 9: Prompt-Based Reschedule Disambiguation Hook**  
**Dependencies:** Reschedule tool implemented  
**Complexity:** Medium (Haiku call per ambiguous case)

**Priority 10: Guard — Already-Cancelled Booking**  
**Dependencies:** Cancel tool + booking status tracking  
**Complexity:** Very Low

---

## 7. Implementation Notes — Specific Code Locations and Patterns

### 7.1 Affirmative Confirmation Intent Hook

**File:** `engine/core/message_handler.py`  
**Insert location:** After line 190 (opt-out detection), before line 300 (context builder invocation)

**New helper function (add to module scope):**
```python
_AFFIRMATIVE_KEYWORDS = frozenset({
    "yes", "yep", "yeah", "ok", "okay", "confirm", "confirmed", "correct", "right",
    "go ahead", "proceed", "book it", "sounds good", "looks good", "all good",
    "sure", "definitely", "absolutely", "👍",
})

def _is_affirmative_keyword(message_text: str) -> bool:
    """Return True if message is a recognised affirmative keyword."""
    normalised = re.sub(r"[^a-z0-9\s]+", "", (message_text or "").lower()).strip()
    return normalised in _AFFIRMATIVE_KEYWORDS
```

**Insert in `handle_inbound_message()` (after opt-out detection):**
```python
# ── Step 5c: Affirmative confirmation intent hook (Phase B bypass) ────
pending_booking = await _get_latest_pending_booking(db, phone_number)
if pending_booking and _is_affirmative_keyword(message_text):
    logger.info(
        f"Intent hook: affirmative confirmation detected for {phone_number}, "
        f"bypassing agent, calling confirm_booking directly"
    )
    lead_days, windows = await asyncio.gather(
        fetch_lead_days(db),
        fetch_appointment_windows(db),
    )
    tool_dispatch = build_tool_dispatch(db, client_config, phone_number, lead_days, windows)
    confirm_result = await tool_dispatch["confirm_booking"](pending_booking["booking_id"])

    if confirm_result.get("status") == "confirmed":
        agent_reply = confirm_result["message"]
    elif confirm_result.get("status") == "conflict":
        await tool_dispatch["escalate_to_human"](
            reason=f"Slot conflict on confirmation for booking {pending_booking['booking_id']}"
        )
        agent_reply = confirm_result["message"] + "\n\nOur team will reach out to help you reschedule."
    else:
        await tool_dispatch["escalate_to_human"](
            reason=f"confirm_booking failed for {pending_booking['booking_id']}: {confirm_result.get('error')}"
        )
        agent_reply = FALLBACK_REPLY

    _now = datetime.now(timezone.utc).isoformat()
    try:
        await send_message(client_config, phone_number, agent_reply)
        await db.table("interactions_log").insert({
            "timestamp": _now,
            "phone_number": phone_number,
            "direction": "outbound",
            "message_text": agent_reply,
            "message_type": "text",
        }).execute()
        logger.info(f"Reply sent via intent hook for {phone_number}")
    except Exception as e:
        logger.error(f"Failed to send/log reply via intent hook: {e}", exc_info=True)
    return  # Agent never runs
```

**Testing checklist:**
- [ ] Customer with pending booking sends "yes" → `confirm_booking` called directly, agent not invoked
- [ ] Customer with pending booking sends "ok" → same behavior
- [ ] Customer with pending booking sends "yes?" (question mark) → agent invoked (false positive mitigation needed — add `"?" not in message_text` guard)
- [ ] Customer with no pending booking sends "yes" → agent invoked (precondition check working)
- [ ] Slot conflict during confirmation → auto-escalate + send conflict message
- [ ] Token usage logged as 0 input / 0 output tokens (agent never called)

---

### 7.2 Audit Logging Hooks

**New Supabase table (shared DB):**
```sql
CREATE TABLE tool_audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_input JSONB NOT NULL,
    tool_output JSONB,
    status TEXT NOT NULL,  -- 'success' | 'error'
    duration_ms NUMERIC(10, 2),
    error_message TEXT
);

CREATE INDEX idx_tool_audit_log_client_timestamp ON tool_audit_log (client_id, timestamp DESC);
CREATE INDEX idx_tool_audit_log_tool_name ON tool_audit_log (tool_name);
CREATE INDEX idx_tool_audit_log_status ON tool_audit_log (status) WHERE status = 'error';
```

**File:** `engine/core/agent_runner.py`  
**Modify:** `_execute_tool()` function (lines 820–850)

**New helper function (add to module scope):**
```python
async def _log_tool_execution(
    client_id: str,
    tool_name: str,
    tool_input: dict,
    tool_output: Any,
    status: str,
    duration_ms: float,
    error_message: str = None,
) -> None:
    """Write tool execution record to shared Supabase tool_audit_log table."""
    try:
        from engine.integrations.supabase_client import get_shared_db
        shared_db = await get_shared_db()
        await shared_db.table("tool_audit_log").insert({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_id": client_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output if isinstance(tool_output, dict) else {"raw": str(tool_output)},
            "status": status,
            "duration_ms": duration_ms,
            "error_message": error_message,
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log tool execution to audit table: {e}")
```

**Modify `_execute_tool()` (insert audit logging):**
```python
async def _execute_tool(block: Any, tool_dispatch: dict, client_id: str = "") -> dict:
    import time
    tool_name = getattr(block, "name", "unknown")
    tool_input = getattr(block, "input", {})
    tool_id = getattr(block, "id", "")

    # NEW: Start timer
    start_time = time.perf_counter()

    tool_fn = tool_dispatch.get(tool_name)

    if tool_fn is None:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(f"Tool not found in dispatch: {tool_name!r}")
        content = json.dumps({"error": "tool_not_found", "tool": tool_name})
        asyncio.create_task(_log_tool_execution(
            client_id=client_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output={"error": "tool_not_found"},
            status="error",
            duration_ms=duration_ms,
            error_message=f"Tool {tool_name} not in dispatch table",
        ))
    else:
        logger.info(f"Executing tool: {tool_name!r} with input: {tool_input}")
        try:
            result = await tool_fn(**tool_input)
            duration_ms = (time.perf_counter() - start_time) * 1000
            content = json.dumps(result) if not isinstance(result, str) else result
            logger.info(f"Tool {tool_name!r} succeeded (duration={duration_ms:.0f}ms)")
            
            # NEW: Audit log success
            asyncio.create_task(_log_tool_execution(
                client_id=client_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=result,
                status="success",
                duration_ms=duration_ms,
            ))
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Tool {tool_name!r} raised: {e}", exc_info=True)
            content = json.dumps({"error": "tool_execution_failed", "message": str(e)})
            
            # NEW: Audit log error + incident
            asyncio.create_task(_log_tool_execution(
                client_id=client_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output={"error": str(e)},
                status="error",
                duration_ms=duration_ms,
                error_message=str(e),
            ))
            from engine.integrations.observability import log_incident
            asyncio.create_task(log_incident(
                provider="tool_execution",
                error_type=f"{tool_name}_failed",
                error_message=str(e),
                client_id=client_id,
                context={"tool_input": tool_input},
            ))

    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": content,
    }
```

**Testing checklist:**
- [ ] Every tool call writes to `tool_audit_log` table (success or error)
- [ ] `duration_ms` is populated and reasonable (<5000ms for all tools)
- [ ] `tool_input` and `tool_output` are stored as JSONB (not stringified)
- [ ] Tool failures write to both `tool_audit_log` and `api_incidents`
- [ ] Logging failure does not crash tool execution (fire-and-forget)

---

### 7.3 Post-Tool Validation Hooks

**File:** `engine/core/agent_runner.py`  
**Modify:** `_execute_tool()` function — insert validation after `result = await tool_fn(**tool_input)`

**New validation functions (add to module scope):**
```python
async def _validate_write_booking_result(result: dict, client_id: str) -> dict | None:
    """
    Validate write_booking result. Returns override dict if validation fails.
    """
    if not isinstance(result, dict):
        return None  # Pass through (unexpected format)
    
    booking_id = result.get("booking_id")
    if not booking_id:
        logger.error(
            f"write_booking returned no booking_id (client_id={client_id}, result={result})"
        )
        from engine.integrations.observability import log_incident
        await log_incident(
            provider="tool_validation",
            error_type="write_booking_missing_booking_id",
            error_message="write_booking succeeded but booking_id is null",
            client_id=client_id,
            context={"result": result},
        )
        return {
            "error": "booking_creation_failed",
            "message": (
                "I'm sorry, I wasn't able to complete your booking due to a technical issue. "
                "Our team has been notified and will follow up with you shortly."
            ),
        }
    
    # Validate booking_id format: <PREFIX>-YYYYMMDD-XXXX
    import re
    if not re.match(r"^[A-Z]{2,4}-\d{8}-[A-Z0-9]{4}$", booking_id):
        logger.error(
            f"write_booking returned malformed booking_id: {booking_id!r} (client_id={client_id})"
        )
        from engine.integrations.observability import log_incident
        await log_incident(
            provider="tool_validation",
            error_type="write_booking_malformed_booking_id",
            error_message=f"booking_id {booking_id!r} does not match expected format",
            client_id=client_id,
            context={"booking_id": booking_id},
        )
        return {
            "error": "booking_creation_failed",
            "message": (
                "I'm sorry, I wasn't able to complete your booking due to a technical issue. "
                "Our team has been notified and will follow up with you shortly."
            ),
        }
    
    return None  # Validation passed


async def _validate_confirm_booking_result(
    result: dict,
    tool_dispatch: dict,
    client_id: str,
) -> dict | None:
    """
    Validate confirm_booking result. Auto-escalates on slot conflict.
    Returns override dict if validation requires action.
    """
    if not isinstance(result, dict):
        return None

    if result.get("status") == "conflict":
        booking_id = result.get("booking_id", "unknown")
        logger.warning(
            f"Slot conflict detected for booking {booking_id} (client_id={client_id}) — auto-escalating"
        )
        try:
            await tool_dispatch["escalate_to_human"](
                reason=f"Slot conflict during confirmation for booking {booking_id}"
            )
        except Exception as e:
            logger.error(f"Failed to auto-escalate on slot conflict: {e}")
        
        # Override message to include escalation notice
        return {
            **result,
            "message": result["message"] + "\n\nOur team will reach out to help you reschedule."
        }
    
    return None  # No override needed
```

**Modify `_execute_tool()` (insert validation after tool execution):**
```python
async def _execute_tool(
    block: Any,
    tool_dispatch: dict,
    client_id: str = "",
) -> dict:
    # ... existing pre-execution logic (audit start, tool_fn lookup)
    
    try:
        result = await tool_fn(**tool_input)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # NEW: Post-tool validation hooks
        if tool_name == "write_booking":
            override = await _validate_write_booking_result(result, client_id)
            if override:
                result = override
        
        if tool_name == "confirm_booking":
            override = await _validate_confirm_booking_result(result, tool_dispatch, client_id)
            if override:
                result = override
        
        content = json.dumps(result) if not isinstance(result, str) else result
        logger.info(f"Tool {tool_name!r} succeeded (duration={duration_ms:.0f}ms)")
        
        # ... existing audit logging
    except Exception as e:
        # ... existing error handling
```

**Testing checklist:**
- [ ] `write_booking` returns null `booking_id` → override to error dict, incident logged
- [ ] `write_booking` returns malformed `booking_id` → override to error dict, incident logged
- [ ] `confirm_booking` returns `status="conflict"` → auto-escalate called, message appended
- [ ] Valid `write_booking` and `confirm_booking` results pass through unchanged
- [ ] Validation failure does not crash agent loop (error returned to Claude)

---

### 7.4 Pre-Tool write_booking Slot Recheck

**File:** `engine/core/agent_runner.py`  
**Modify:** `_execute_tool()` function — insert slot recheck before `tool_fn(**tool_input)` when `tool_name == "write_booking"`

**New validation function (add to module scope):**
```python
async def _recheck_slot_availability(
    tool_input: dict,
    client_config,
    client_id: str,
) -> dict | None:
    """
    Re-check slot availability immediately before write_booking.
    Returns error dict if slot is no longer available.
    """
    slot_date = tool_input.get("slot_date")
    slot_window = tool_input.get("slot_window")
    
    if not slot_date or not slot_window:
        return None  # Missing params — let write_booking handle it
    
    try:
        from engine.integrations.google_calendar import check_slot_availability
        availability = await check_slot_availability(
            google_calendar_creds=client_config.google_calendar_creds,
            calendar_id=client_config.google_calendar_id,
            slot_date=slot_date,
            timezone="Asia/Singapore",
        )
        
        slot_key = "am_available" if slot_window == "AM" else "pm_available"
        if not availability.get(slot_key, False):
            logger.warning(
                f"Pre-hook: slot {slot_window} on {slot_date} no longer available "
                f"(client_id={client_id}) — blocking write_booking"
            )
            return {
                "error": "slot_no_longer_available",
                "message": (
                    f"I'm sorry, the {slot_window} slot on {slot_date} is no longer available — "
                    "it was just taken. Let me check what other slots are open for you."
                ),
            }
    except Exception as e:
        logger.error(f"Pre-hook slot recheck failed: {e}", exc_info=True)
        # Recheck failure is non-fatal — proceed with write_booking
        return None
    
    return None  # Slot still available
```

**Modify `_execute_tool()` (insert pre-hook for write_booking):**
```python
async def _execute_tool(
    block: Any,
    tool_dispatch: dict,
    client_id: str = "",
    client_config = None,  # NEW parameter — pass from agent_runner.run_agent()
) -> dict:
    # ... existing pre-execution logic
    
    tool_fn = tool_dispatch.get(tool_name)
    if tool_fn is None:
        # ... existing tool_not_found logic
    else:
        # NEW: Pre-tool hook for write_booking
        if tool_name == "write_booking" and client_config:
            slot_conflict = await _recheck_slot_availability(tool_input, client_config, client_id)
            if slot_conflict:
                duration_ms = (time.perf_counter() - start_time) * 1000
                content = json.dumps(slot_conflict)
                asyncio.create_task(_log_tool_execution(
                    client_id=client_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output=slot_conflict,
                    status="blocked_by_pre_hook",
                    duration_ms=duration_ms,
                    error_message="Slot no longer available",
                ))
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": content,
                }
        
        logger.info(f"Executing tool: {tool_name!r} with input: {tool_input}")
        try:
            result = await tool_fn(**tool_input)
            # ... existing post-execution logic
```

**Update `run_agent()` signature to pass `client_config` to `_execute_tool()`:**
```python
async def run_agent(
    system_message: str,
    conversation_history: list[dict],
    current_message: str,
    tool_definitions: list[dict],
    tool_dispatch: dict,
    client_id: str = "",
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    pending_booking_id: str | None = None,
    client_config = None,  # NEW parameter
) -> str:
    # ... existing logic
    
    # In tool_use block processing:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_result = await _execute_tool(
                block=block,
                tool_dispatch=tool_dispatch,
                client_id=client_id,
                client_config=client_config,  # NEW: pass config for pre-hooks
            )
            # ... existing logic
```

**Update `message_handler.py` to pass `client_config` to `run_agent()`:**
```python
# In handle_inbound_message():
agent_reply = await run_agent(
    system_message=system_message,
    conversation_history=history,
    current_message=message_text,
    tool_definitions=tool_definitions,
    tool_dispatch=tool_dispatch,
    client_id=client_id,
    anthropic_api_key=client_config.anthropic_api_key,
    openai_api_key=client_config.openai_api_key,
    pending_booking_id=pending_booking["booking_id"] if pending_booking else None,
    client_config=client_config,  # NEW
)
```

**Testing checklist:**
- [ ] `check_calendar_availability` shows AM available, concurrent booking takes slot, `write_booking` blocked by pre-hook
- [ ] Pre-hook returns error dict, agent receives "slot no longer available" message
- [ ] `tool_audit_log` shows `status='blocked_by_pre_hook'`
- [ ] Pre-hook adds 200–500ms latency to `write_booking` (measure P95)
- [ ] If pre-hook fails (calendar API error), `write_booking` proceeds (non-fatal failure)

---

## 8. Risks and Mitigations

### Risk 8.1: False Positives in Intent Classification

**Risk:** Affirmative confirmation hook triggers when customer says "yes" to a question instead of confirming booking.

**Example:**
- Agent: "Would you like to book this service for your office or home?"
- Customer: "yes"
- Hook detects affirmative + pending booking exists → calls `confirm_booking` (wrong action)

**Mitigation 1 (Phase 1):** Add precondition: no question mark in last agent outbound message  
**Mitigation 2 (Phase 2):** NLP intent classifier (low confidence → fall back to LLM)  
**Mitigation 3 (immediate):** Monitor `tool_audit_log` for `confirm_booking` called via intent hook → review conversation context on failures

**Rollback plan:** If false positive rate >5%, disable intent hook via feature flag, revert to LLM orchestration

---

### Risk 8.2: Pre-Hook Latency Impact

**Risk:** `write_booking` pre-hook adds 200–500ms calendar API call latency to every booking creation.

**Impact:** P95 booking confirmation time increases from ~3s to ~3.5s (still acceptable, but measurable)

**Mitigation:**
- Monitor P95 latency before/after deployment via `tool_audit_log.duration_ms`
- If P95 exceeds 5000ms, investigate calendar API performance or disable pre-hook
- Consider async slot recheck (check in background, invalidate booking if conflict detected after write)

---

### Risk 8.3: Hook Infrastructure Complexity

**Risk:** Hook registry adds indirection — harder to trace code flow, harder to debug hook failures.

**Mitigation:**
- Keep hook functions simple (single responsibility, no nested logic)
- Log every hook invocation and outcome (audit trail)
- Document hooks in `code_map.md` with explicit file locations

---

### Risk 8.4: Over-Hooking Fragility

**Risk:** Too many hooks create a brittle system — every new tool requires 3–5 hook functions, maintenance burden grows.

**Mitigation:**
- Only implement hooks with proven ROI (see recommendation table)
- Start with 3 high-impact hooks (affirmative intent, audit, write_booking validation)
- Re-evaluate after 30 days production data — add more hooks only if failure patterns emerge

---

## 9. Success Metrics

Track these metrics before/after hook implementation:

| Metric | Baseline (Pre-Hooks) | Target (Post-Hooks) | Data Source |
|--------|----------------------|---------------------|-------------|
| LLM calls per Phase B confirmation | 1–2 | 0 (bypassed) | `api_usage` table |
| Booking confirmation failures (guardrail fired) | ~2–5% | <1% | `api_incidents` table |
| Slot TOCTOU conflicts (confirm_booking returns conflict) | Unknown | <1% | `tool_audit_log` |
| Tool execution failures invisible to observability | 100% | 0% | `api_incidents` table |
| P95 latency for `write_booking` | ~500ms | <1000ms | `tool_audit_log.duration_ms` |

---

## 10. Conclusion

**This evaluation covers two distinct scopes.** Don't conflate them:

- **Scope A (Claude Code hooks):** Dev workflow hooks in `.claude/settings.json`. Enforce git discipline rules from AGENTS.md automatically. Zero production risk. Implement immediately.
- **Scope B (Engine hooks):** Production Python hooks in `agent_runner.py` and `message_handler.py`. Improve determinism, reliability, and observability of customer conversations.

**Phase 0 (dev workflow) — highest leverage per effort:** Create `.claude/settings.json` with SDET merge gate hook and deploy branch push reminder. Two incidents and multiple wasted debug rounds were caused by violations of these rules. Automation is more reliable than documentation.

**Phase 1 (engine) top 3 priorities:**

1. **Affirmative Confirmation Intent Hook** — Highest ROI. Eliminates 100% of LLM calls for affirmatives, saves cost, adds determinism, improves latency by 2–4s per confirmation. Low complexity, low risk.

2. **`additionalContext` on write_booking** — Very low cost, directly prevents the "write succeeded but confirm not called" agent confusion that triggers reprompt guardrails.

3. **Audit Logging Hooks** — Critical for production observability. Every tool call in `tool_audit_log`, every error in `api_incidents`. Enables all future improvements.

**Phase 2:** Refactor reprompt guardrails into a `Stop` hook (cleaner, composable, follows official Anthropic pattern). Add `updatedInput` slot TOCTOU fix for better booking reliability with automatic slot recovery.

**The `updatedInput` / `additionalContext` / `updatedToolOutput` / `Stop` hook patterns from the official Anthropic Claude Code docs are directly applicable to Scope B.** They describe the *shape* of the right solution. The implementation is Python code in `_execute_tool()`, not `.claude/settings.json` — but the design patterns translate directly.

**Phase 2:** Implement **Pre-Tool write_booking Slot Recheck** after Phase 1 validated. High impact in multi-client environment, but adds latency — measure before committing.

**Not recommended:** Pre-tool escalation idempotency check, already-cancelled guard (future gaps with low ROI).

**Interaction with existing patterns:** Hooks extend the Backend Bypass Preference Rule — intent hooks are the pre-LLM bypass layer, validation hooks are the post-tool safety layer. Both reduce LLM non-determinism while maintaining the simple tool-use loop architecture.
