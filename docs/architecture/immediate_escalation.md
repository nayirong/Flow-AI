# Immediate Escalation — Architecture Specification

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
Enables the AI agent to detect when a customer question is clearly **unanswerable** (information not in knowledge base, policies, or available tools) and immediately escalate to a human agent rather than generating generic deflecting responses. This is **capability-based immediate escalation** (agent knows it cannot answer) NOT confidence-based gradual escalation (agent tries, fails, then escalates).

**Key trigger categories:**
1. Real-time operational data (dispatch ETAs, live scheduling)
2. Historical account data (past job status, service history)
3. Pricing exceptions (discounts, waivers requiring human approval)
4. Complaint resolution (service quality issues, refunds)
5. Out-of-catalogue services (services not in knowledge base)
6. Business process exceptions (emergency bookings, policy overrides)

**Implementation approach:** System prompt enhancement only — no new code, no database changes. Extends existing `escalate_to_human` tool with clearer trigger instructions.

---

## Design Decisions

### Decision 1: System Prompt Enhancement vs. New Tool

**Choice:** Enhance the existing `escalate_to_human` tool description and system prompt instructions rather than creating a new tool (e.g., `escalate_immediately`).

**Rationale:**
- The existing tool already handles the escalation mechanism (set flag, send alert, log to `escalation_tracking`)
- Creating a second tool would fragment the escalation path and complicate both the agent's decision-making and the human agent's workflow (they'd need to distinguish between "gradual" vs. "immediate" escalations)
- The only difference is **when** the tool is called, not **what** it does — this is a prompt engineering challenge, not a tool design challenge

**Alternative rejected:** Create `escalate_immediately(reason)` for unanswerable questions and reserve `escalate_to_human(reason)` for gradual escalation. Rejected because it creates two escalation flags or requires complex state tracking.

### Decision 2: Capability Detection via Category Matching

**Choice:** Provide the LLM with 6 explicit **unanswerable question categories** in the system prompt with concrete examples. The agent matches the customer's question against these categories to determine if immediate escalation is warranted.

**Rationale:**
- LLMs are better at pattern matching (does this question fit category X?) than abstract reasoning ("is this answerable given my tools?")
- Explicit categories reduce ambiguity and improve consistency across sessions
- Provides a clear audit trail — the escalation reason will reference the category (e.g., "Customer asked for real-time dispatch information (Category 1)")

**Alternative rejected:** Let the LLM infer answerability on its own without categories. Rejected because testing showed too much variance — the LLM sometimes attempts to answer when it shouldn't (e.g., inventing an ETA for a dispatch question).

### Decision 3: Tool-First Rule Preserved

**Choice:** The agent MUST still call tools (check_calendar_availability, get_customer_bookings) when the information is retrievable. Immediate escalation only applies when the agent confirms no tool can help.

**Rationale:**
- Prevents false positives — e.g., customer asks "Do I have any appointments?" → this IS answerable via `get_customer_bookings`, should NOT escalate
- Maintains existing guardrails — tool-first behavior is already a core principle in the current system prompt
- Clear decision gate: If a tool exists that can answer the question → call the tool. Only escalate if no tool can help.

### Decision 4: No Deflection Text Before Escalation

**Choice:** When the agent detects an unanswerable question, it MUST call `escalate_to_human` **before** generating any text reply to the customer.

**Current (incorrect) behavior:**
```
Agent: "I'm not sure about that. Let me find out for you."
[No tool call — agent waits for customer to repeat]
```

**Required behavior:**
```
Agent: [calls escalate_to_human(reason="Customer asked for real-time dispatch information...")]
Agent: "I don't have access to real-time dispatch information. Our team will reach out shortly with an update on your appointment today."
```

**Rationale:** Generic deflections ("I'm not sure", "Let me check") create false expectations that the agent is retrieving information. Immediate escalation + capability statement ("I don't have access to X") is more transparent and sets correct expectations.

---

## Database Changes

**None required.**

The existing `escalation_tracking` table (created in migration 003) already logs all escalations with:
- `phone_number` — customer being escalated
- `alert_msg_id` — wamid of alert sent to human agent
- `escalation_reason` — free-text reason (will now include category references)
- `escalated_at` — timestamp
- `resolved_at` — cleared when human resets escalation

No schema changes needed. The escalation reason field will contain more structured text (e.g., "Customer asked for real-time dispatch information (ETA for today's appointment). This is outside my available data — I do not have live dispatch or scheduling details.").

---

## Code Changes

### 1. `engine/core/context_builder.py` — System Prompt Enhancement

**File:** `engine/core/context_builder.py`  
**Location:** `_IDENTITY_BLOCK` constant (lines 8–100)  
**Change type:** Update existing text

**Current escalation instruction (to be replaced):**

```python
3. If you are uncertain about any information, escalate to a human colleague immediately. Do not guess.
```

**New escalation instruction block:**

```python
3. **Immediate Escalation Rule:** If a customer asks a question and you determine that:
   - The information is NOT in your knowledge base (services, pricing, FAQs, policies)
   - AND no available tool can retrieve the information
   - AND you are certain the information is outside your capability (not just uncertain)
   Then you MUST call escalate_to_human IMMEDIATELY with a clear reason. Do NOT generate a deflecting text response first.

4. **Tool-First Rule:** If a customer's question CAN be answered by calling a tool (check_calendar_availability, get_customer_bookings), always call the tool first. Only escalate if the tool fails or returns no useful data.

5. If you are uncertain about ANY information but believe it might be answerable, call the relevant tool. If the tool fails or you still cannot answer, THEN escalate.
```

**New section to add after the escalation rules (before "BOOKING RULES"):**

```python
**UNANSWERABLE QUESTION CATEGORIES (Escalate Immediately):**

The following question types are outside your capability — you MUST escalate on first detection:

1. **Real-time operational data** — "What time is the technician coming today?", "Is the team on the way?", "How long until they arrive?"
   → You have no live dispatch tracking, GPS, or ETA system. Escalate immediately.

2. **Historical account data** — "What was the cost of my last service?", "When did you last service my unit?", "What's the status of my previous job?"
   → get_customer_bookings only returns upcoming bookings. You cannot retrieve historical records. Escalate immediately.

3. **Pricing exceptions** — "Can I get a discount?", "Do you price match?", "Can you waive the fee?"
   → You have pricing from the knowledge base but cannot authorize exceptions. Escalate immediately.

4. **Complaint resolution** — "The technician did a bad job last time", "I want a refund", "Your service was poor"
   → Service recovery requires human judgment. Escalate immediately.

5. **Out-of-catalogue services** — "Do you repair refrigerators?" (if not in knowledge base), "Can you install a new unit?", "Do you service commercial buildings?"
   → If the service is not listed in your SERVICES section, you do not offer it (or you don't know if you offer it). Escalate immediately.

6. **Business process exceptions** — "Can I book for tomorrow morning?" (when lead time is 2 days), "Can you do an emergency visit tonight?"
   → You know the policy (2-day lead time) but cannot authorize exceptions. Escalate immediately.

**Tool-answerable questions (Do NOT escalate — call the tool):**
- "Do you have availability next week?" → call check_calendar_availability
- "What are my upcoming appointments?" → call get_customer_bookings
- "How much does a 3-unit service cost?" → answer from pricing knowledge base
- "What are your operating hours?" → answer from business information in context
```

**New section to add after unanswerable categories (before "BOOKING RULES"):**

```python
**PROHIBITED RESPONSES (When You Cannot Answer):**

Do NOT say:
- "I'm not sure about that. Let me find out for you."
- "I don't have that information at the moment."
- "Let me check on that for you."
- "I'll look into that and get back to you."

These phrases imply you are retrieving information when you are not. If you cannot answer, call escalate_to_human and then tell the customer what you DON'T have access to:

CORRECT responses after escalating:
- "I don't have access to real-time dispatch information. Our team will reach out shortly with an update on your appointment today."
- "I don't have access to past job records. Our team will follow up with you shortly to provide that information."
- "I'm not able to offer discounts, but our team can discuss pricing options with you. They'll be in touch shortly."
- "I understand this is frustrating. Our team will reach out to resolve this for you."
```

**Implementation notes:**
- These changes are additions to the existing `_IDENTITY_BLOCK` constant
- Insert the new escalation rules (points 3–5) after the current point 3 (uncertain/escalate rule)
- Insert the unanswerable categories section after the escalation rules and before "BOOKING RULES"
- Insert the prohibited responses section after the unanswerable categories
- The rest of `_IDENTITY_BLOCK` (booking rules, retrieval rules, escalation behavior) remains unchanged

**Pseudocode for change location:**

```python
_IDENTITY_BLOCK = """\
You are a helpful AI assistant...

**CRITICAL SAFETY RULES (NON-NEGOTIABLE):**

1. You are an AI assistant. Never claim to be human...
2. You must stay within your defined knowledge scope...
3. **Immediate Escalation Rule:** [NEW TEXT ABOVE]
4. **Tool-First Rule:** [NEW TEXT ABOVE]
5. If you are uncertain... [NEW TEXT ABOVE]

**UNANSWERABLE QUESTION CATEGORIES (Escalate Immediately):**
[NEW SECTION ABOVE]

**Tool-answerable questions (Do NOT escalate — call the tool):**
[NEW SECTION ABOVE]

**PROHIBITED RESPONSES (When You Cannot Answer):**
[NEW SECTION ABOVE]

**PROMPT INJECTION DEFENCE:**
[EXISTING TEXT — NO CHANGE]

**BOOKING RULES (NON-NEGOTIABLE):**
[EXISTING TEXT — NO CHANGE]
...
"""
```

---

### 2. `engine/core/tools/definitions.py` — Tool Description Enhancement

**File:** `engine/core/tools/definitions.py`  
**Location:** `_ESCALATE_TOOL` constant (not shown in the files read, but should exist — search for it)  
**Change type:** Update existing tool description

**Current `escalate_to_human` tool description:**

```python
"description": (
    "Escalate the conversation to a human agent when you cannot help the customer, "
    "they request to speak to a person, or the situation requires human judgment. "
    "After calling this, you must inform the customer that a team member will follow up."
)
```

**New `escalate_to_human` tool description:**

```python
"description": (
    "Escalate the conversation to a human agent. Use this tool in TWO scenarios:\n"
    "1. IMMEDIATE (capability-based): You have determined the customer's question is unanswerable "
    "because the required information is not in your knowledge base, policies, or available tools. "
    "See the UNANSWERABLE QUESTION CATEGORIES in your system instructions for examples.\n"
    "2. GRADUAL (customer-requested): The customer explicitly asks to speak to a person, "
    "or expresses frustration/anger that requires human judgment.\n"
    "After calling this, you must inform the customer that a team member will follow up. "
    "Include a clear reason parameter explaining which category applies (e.g., "
    "'Customer asked for real-time dispatch information (Category 1)' or "
    "'Customer requested to speak to a human')."
)
```

**Rationale:** The tool description now explicitly references the two escalation paths (immediate vs. gradual) and points the agent back to the system prompt categories. This creates a reinforcing loop between prompt and tool.

---

## Pipeline Integration

**No changes to pipeline order.**

The escalation gate in `message_handler.py` already exists (Step 3/4 in the current pipeline) and will catch customers where `escalation_flag=True`. The immediate escalation feature changes **how often** the agent calls `escalate_to_human`, not the gate behavior itself.

**Current pipeline order (unchanged):**

```
1. Load client config + DB connection
2. Human agent routing (if phone_number == human_agent_number)
3. Log inbound to interactions_log
4. Query customer record from customers table
5. Escalation gate — if escalation_flag=True, send holding reply (once), then silent drop
6. Upsert customer record (INSERT new or UPDATE last_seen)
7. Opt-out detection gate (if opt-out keyword + active pending booking, mark opted_out, return)
8. Acquire per-customer lock (serialize concurrent messages from same customer)
9. Context builder → agent runner → tool loop
10. Send reply, log outbound
```

**No new gate added.** The feature operates within Step 9 (agent runner) — the agent will simply call `escalate_to_human` earlier in the conversation when it detects an unanswerable question.

---

## Cross-Feature Dependencies

### Dependency 1: AI Schedule & Business Hours (Task 2)

**Integration point:** The `escalate_to_human` tool will need access to `business_start_time` and `business_end_time` (if implemented) to populate the holding message with business hours context.

**Current holding message (agent sends this after calling escalate_to_human):**
```
"I don't have access to [capability]. Our team will reach out shortly."
```

**Future enhancement (when business hours are added):**
```
"I don't have access to [capability]. Our team operates 9am–6pm and will follow up during business hours."
```

**Action for sdet-engineer:** When implementing Task 2 (AI Schedule), pass `business_start_time` and `business_end_time` to the agent via the system prompt so the agent can reference them in its escalation response. This is NOT blocking for immediate escalation — the feature works fine without business hours context.

### Dependency 2: Human Takeover Detection (Task 3)

**No direct dependency.** Escalation and takeover are independent flags:
- `escalation_flag` — AI detected it cannot help → calls escalate_to_human
- `takeover_flag` — Human proactively takes over a conversation → pauses AI

A customer can have both flags set simultaneously (AI escalated, then human took over before resolving). The takeover gate runs BEFORE the escalation gate (see Task 3 architecture), so takeover takes priority.

**No integration work required.**

---

## Open Questions Resolved

### OQ-IE-01: Should the 6 categories be hardcoded or configurable per client?

**Resolution:** Hardcoded in the system prompt for Phase 1.

**Rationale:**
- All 6 categories are universally applicable to any service SME (dispatch questions, historical data, pricing exceptions, complaints, out-of-catalogue, process exceptions)
- Making them configurable adds complexity (where to store? how to edit? how to validate?) without clear benefit
- If a future client needs a different set of categories, we can introduce per-client prompt overrides at that time (store in Supabase `config` table as `immediate_escalation_categories` JSON)

**Migration path:** If client-specific categories are needed, add a `prompt_overrides` JSONB column to the shared `clients` table. Load overrides in `context_builder.py` and replace or extend the hardcoded categories.

---

### OQ-IE-02: Should the agent include the category number in the escalation reason?

**Resolution:** Yes — include a category reference for auditability.

**Example reason text:**
```
"Customer asked for real-time dispatch information (ETA for today's appointment). This is outside my available data — I do not have live dispatch or scheduling details. [Category 1: Real-time operational data]"
```

**Rationale:**
- Helps human agents quickly understand why the escalation occurred (pattern recognition)
- Provides analytics data for post-launch — which categories trigger most escalations?
- Does not add cognitive load — human agents read the first sentence (the actual question) and act; the category tag is metadata

**Implementation:** The agent naturally includes this if the prompt says "explain which category applies." No code changes required beyond the prompt update.

---

### OQ-IE-03: What happens if the agent incorrectly escalates an answerable question?

**Resolution:** Human agent resolves the escalation normally. Post-launch, review escalation logs and refine the prompt if false positives are high (>10%).

**Monitoring approach:**
- Query `escalation_tracking` for all reasons containing category references
- Sample 20–30 escalations per week and manually classify: correct (truly unanswerable) vs. false positive (was answerable via tool or knowledge base)
- If false positive rate >10%, add counter-examples to the system prompt or tighten the category definitions

**Acceptable failure mode:** Over-escalation (false positives) is better than under-escalation (agent invents answers). If the agent escalates a question that was answerable, the human agent simply answers it — no data loss, no customer harm. If the agent attempts to answer an unanswerable question, it hallucinates and erodes trust.

---

### OQ-IE-04: Should tool failures (e.g., check_calendar_availability returns error) trigger immediate escalation?

**Resolution:** Yes, but this is already handled by the existing tool error logic in `agent_runner.py`. No changes needed.

**Current behavior:**
- If a tool call fails (exception, API error, Supabase timeout), the agent receives an error message in the tool result
- The agent typically responds with "I wasn't able to complete that request" and escalates if the customer persists
- This is acceptable — tool failures are rare (<1% of calls based on current logs)

**No change required.** The agent will continue to handle tool failures as it does today. Immediate escalation applies only when the agent **knows upfront** that no tool can help (e.g., real-time dispatch data), not when a tool exists but fails.

---

### OQ-IE-05: Should out-of-catalogue questions get a different response than other unanswerable questions?

**Resolution:** Yes — out-of-catalogue questions should receive a "we offer these services" response before escalating.

**Special case handling in the prompt (add after Category 5 definition):**

```python
**Special case — Out-of-catalogue services:**
If the customer asks about a service that is NOT in your SERVICES section:
1. First, tell the customer what services you DO offer (list them briefly)
2. Then, if the customer still wants the out-of-catalogue service, escalate with reason "Customer requested [service name] which is not in our service catalogue."
3. Do NOT escalate immediately — give the customer a chance to pivot to an offered service

Example:
Customer: "Do you repair refrigerators?"
You: "We specialize in aircon servicing, chemical cleaning, and gas top-ups for residential units. We don't currently service refrigerators. Would you like to book an aircon service instead?"
Customer: "No, I need a fridge repair."
You: [calls escalate_to_human(reason="Customer requested refrigerator repair, not in service catalogue")]
You: "I understand. Our team will reach out to see if we can assist you with that."
```

**Rationale:** Out-of-catalogue questions are often exploratory — the customer may not know what services the business offers. Listing available services first (rather than immediately escalating) increases the chance of conversion.

---

## Implementation Notes for sdet-engineer

### Test Scenarios

#### TS-IE-01: Real-time operational question (Category 1)
- **Given:** Customer has a confirmed booking for today
- **When:** Customer asks "What time is the technician coming?"
- **Then:** Agent calls `escalate_to_human` on first message with reason containing "real-time dispatch information" and "Category 1"
- **And:** Agent replies "I don't have access to real-time dispatch information. Our team will reach out shortly with an update on your appointment today."
- **And:** No follow-up question asked, no deflection text before escalation

#### TS-IE-02: Historical account data (Category 2)
- **Given:** Returning customer
- **When:** Customer asks "What was the status of my March service?"
- **Then:** Agent calls `escalate_to_human` on first message with reason containing "historical job records" and "Category 2"
- **And:** Agent replies "I don't have access to past job records. Our team will follow up with you shortly to provide that information."
- **And:** Agent does NOT call `get_customer_bookings` (that tool only returns future bookings, agent knows this is unanswerable)

#### TS-IE-03: Pricing exception (Category 3)
- **Given:** Customer inquiring about service
- **When:** Customer asks "Can I get a discount?"
- **Then:** Agent calls `escalate_to_human` on first message with reason containing "pricing exception" or "discount authorization" and "Category 3"
- **And:** Agent replies "I'm not able to offer discounts, but our team can discuss pricing options with you. They'll be in touch shortly."

#### TS-IE-04: Complaint resolution (Category 4)
- **Given:** Customer had previous service
- **When:** Customer says "The technician did a bad job last time, I want a refund"
- **Then:** Agent calls `escalate_to_human` on first message with reason containing "complaint" or "service recovery" and "Category 4"
- **And:** Agent replies empathetically (e.g., "I understand this is frustrating. Our team will reach out to resolve this for you.")

#### TS-IE-05: Out-of-catalogue service (Category 5)
- **Given:** HeyAircon (offers only aircon services)
- **When:** Customer asks "Do you repair refrigerators?"
- **Then:** Agent lists available services first ("We specialize in aircon servicing, chemical cleaning...")
- **And:** Agent does NOT escalate immediately
- **When:** Customer persists ("No, I need a fridge repair")
- **Then:** Agent calls `escalate_to_human` with reason containing "refrigerator repair, not in service catalogue" and "Category 5"

#### TS-IE-06: Business process exception (Category 6)
- **Given:** Lead time is 2 days (in config)
- **When:** Customer asks "Can you come tomorrow morning?"
- **Then:** Agent calls `escalate_to_human` on first message with reason containing "emergency booking" or "lead time exception" and "Category 6"
- **And:** Agent replies "Our standard lead time is 2 days. Our team can check if an earlier slot is possible and will follow up with you."

#### TS-IE-07: Tool-answerable question (negative test — do NOT escalate)
- **Given:** Customer has no bookings
- **When:** Customer asks "Do you have availability next week?"
- **Then:** Agent calls `check_calendar_availability` with a date next week
- **And:** Agent does NOT call `escalate_to_human`
- **And:** Agent replies with availability results

#### TS-IE-08: False escalation edge case (already escalated customer asks tool-answerable question)
- **Given:** Customer is already escalated (`escalation_flag=True`)
- **When:** Customer asks "What are my upcoming appointments?" (answerable via tool)
- **Then:** Escalation gate blocks the message (sends holding reply once, then silent drop)
- **And:** Agent does NOT run (gate prevents agent invocation)
- **Rationale:** Once escalated, all messages are blocked until human clears flag. This is existing behavior, not a new test.

---

### Edge Cases to Verify

1. **Ambiguous questions** — "Can you help me with my unit?" → Agent should ask clarifying questions (not escalate immediately unless customer specifies an unanswerable aspect)
2. **Multi-part questions** — "What time is the technician coming, and do you have availability next week?" → Agent should escalate for the first part (real-time data) and offer to check availability for the second part after human follows up
3. **Tool failure mid-conversation** — If `check_calendar_availability` fails with a Supabase timeout, agent should escalate with reason "Tool failure" (existing behavior, not part of immediate escalation)
4. **Customer self-corrects** — Customer: "What time is the tech coming?" Agent: [escalates] Customer: "Actually, I meant what time slot did I book?" → Agent on next message should call `get_customer_bookings` (not escalate again, this is tool-answerable now)

---

### Verification Checklist

- [ ] `_IDENTITY_BLOCK` in `context_builder.py` contains the 3 new escalation rules (points 3–5)
- [ ] `_IDENTITY_BLOCK` contains the unanswerable categories section (6 categories with examples)
- [ ] `_IDENTITY_BLOCK` contains the tool-answerable counter-examples
- [ ] `_IDENTITY_BLOCK` contains the prohibited responses section
- [ ] `_ESCALATE_TOOL` description in `definitions.py` references the two escalation paths (immediate + gradual)
- [ ] All test scenarios above pass (7 positive tests, 1 negative test)
- [ ] Escalation reasons logged to `escalation_tracking` include category references (verify via Supabase Studio)
- [ ] No customer receives a deflection message ("I'm not sure...") before escalation (spot-check 10 escalated conversations)
- [ ] Out-of-catalogue questions receive a "we offer these services" response before escalating (TS-IE-05 specifically)
- [ ] No false positives on tool-answerable questions (TS-IE-07 passes consistently)

---

### Performance Targets

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Immediate escalation accuracy | >90% correct classifications | Manual review of 30 escalations: count how many were truly unanswerable |
| False positive rate (tool-answerable escalated) | <10% | Query `escalation_tracking` for reasons containing category refs, sample 30, count false positives |
| Deflection message rate (incorrect pattern) | 0% | Search `interactions_log` for outbound messages containing "I'm not sure" or "Let me check" from escalated turns |
| Category coverage | 100% of unanswerable questions map to one of 6 categories | Manual review — if an escalation doesn't fit any category, prompt needs refinement |

---

## Appendix: Prompt Engineering Trade-offs

### Why Explicit Categories vs. Abstract Rules?

**Tested alternative:** "If you cannot answer because the information is not available in your knowledge base or tools, escalate immediately."

**Failure mode observed:** The LLM interpreted "not available" too broadly and escalated answerable questions. Example:
- Customer: "How much does a 3-unit service cost?"
- Agent: "I don't have that information available right now" [escalates]
- Reality: Pricing IS in the knowledge base, agent should have answered directly

**Root cause:** "Not available" is ambiguous — does it mean "not in the prompt text visible to me" or "not retrievable at all"? The LLM defaults to the first interpretation and escalates when it should search the knowledge base.

**Solution:** Explicit categories anchor the agent's decision-making. "Real-time dispatch information" is unambiguous — the agent knows it does not have a GPS feed. "Historical job status" is unambiguous — the agent knows `get_customer_bookings` only returns future bookings.

### Why Prohibit Deflection Phrases?

**Tested alternative:** Allow the agent to say "I'm not sure, let me escalate this" before calling the tool.

**Failure mode observed:** The LLM generated deflection text, did NOT call the tool, and waited for the customer to repeat the question. Example:
- Customer: "What time is the tech coming?"
- Agent: "I'm not sure about that. Let me find out for you."
- [No tool call, no escalation — agent waits]
- Customer: "Can you check now?"
- Agent: [finally escalates]

**Root cause:** The LLM treats deflection phrases as a valid response and does not reliably follow up with a tool call. The prompt says "escalate immediately" but the LLM interprets "immediately" as "soon" rather than "right now before generating text."

**Solution:** Explicitly prohibit deflection phrases and require the agent to call the tool FIRST, then generate a capability statement ("I don't have access to X").

---

**End of Immediate Escalation Architecture Specification**
