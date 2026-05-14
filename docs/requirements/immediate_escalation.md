# Feature Requirements: Immediate Escalation Trigger

> **Requirements Specification**  
> Author: @product-manager  
> Date: 2026-05-12  
> Status: Draft — Pending Founder Approval

---

## 1. Feature Overview

### What
When the AI agent clearly does not have the answer to a customer's question — meaning the required information is not available in its knowledge base, policies table, or available tools — it immediately escalates to a human agent rather than giving a generic deflecting answer and waiting for the customer to persist.

### Who
**Primary users:** End customers who ask questions outside the agent's knowledge scope (e.g., real-time dispatch information, account-specific history, pricing exceptions, complaint resolution).

**Affected users:** Human agents — will receive escalation alerts sooner, potentially for more cases than the current gradual escalation model.

### Why
**Current pain:** When a customer asks a question the agent cannot answer (e.g., "What time is the servicing team coming today?"), the agent generates a generic deflecting reply ("I'm not sure about that, let me find out..."). The customer continues asking. After repeated failure, the agent eventually escalates. This feels bot-like and creates customer frustration.

**Value delivered:**
- Faster handoff to human agents — customers reach the right resource immediately, not after 2–3 rounds of bot deflection
- Reduced customer frustration — the agent acknowledges its limitation upfront instead of giving the impression it can help when it cannot
- More transparent AI behavior — the agent clearly signals "this is outside my capability" rather than masking the gap with generic responses

### Channel
WhatsApp and widget — both channels share the same agent core and will benefit from this behavior change.

---

## Direction Check

- **Subject**: Customers who ask questions outside the agent's answerable scope
- **Problem**: Agent gives generic deflecting answers instead of immediately escalating, causing frustration and wasted time
- **Confirmation**: This solution provides the subject (customers) with immediate human handoff when their question is unanswerable by the agent — it does NOT address the inverse (e.g., escalating too aggressively or escalating answerable questions)

---

## 2. Problem Statement

### Current Behavior

When a customer asks a question the agent cannot answer, the current system prompt instructs:

> "If you are uncertain about any information, escalate to a human colleague immediately. Do not guess."

However, in practice, the LLM often generates a **text deflection** before calling `escalate_to_human`:

**Example 1 — Real-time operational question:**
```
Customer: "What time is the servicing team coming today?"
Agent: "I'm not sure about that. Let me find out for you. Our team will get back to you shortly."
[No tool call — agent does not escalate]
Customer: "Can you check now?"
Agent: "I don't have access to that information at the moment. Let me escalate this to our team."
[Finally calls escalate_to_human after second attempt]
```

**Example 2 — Account-specific historical question:**
```
Customer: "What's the status of my previous job?"
Agent: "I don't have that information right now, but I can help you book a new service. Would you like to check availability?"
[Agent pivots instead of escalating]
Customer: "I asked about my previous job, not a new one."
Agent: "I understand. Let me connect you with our team who can look that up for you."
[Escalates only after customer corrects]
```

### Desired Behavior

When the agent detects that a question is **clearly unanswerable** — meaning the information required to respond is not present in:
- The knowledge base (services, pricing, policies, FAQs)
- The policies table (business rules, fees, conditions)
- The available tools (`check_calendar_availability`, `write_booking`, `get_customer_bookings`, `confirm_booking`)

The agent should **immediately call `escalate_to_human`** with a clear reason, rather than generating a text deflection.

**Example 1 — Corrected:**
```
Customer: "What time is the servicing team coming today?"
Agent: [calls escalate_to_human(reason="Customer asked for real-time dispatch information (ETA for today's appointment). This is outside my available data — I do not have live dispatch or scheduling details.")]
Agent: "I don't have access to real-time dispatch information, but our team will reach out to you shortly with an update on your appointment today."
```

**Example 2 — Corrected:**
```
Customer: "What's the status of my previous job?"
Agent: [calls escalate_to_human(reason="Customer asked for status of a past service job. I do not have historical job records or service completion status — only upcoming bookings.")]
Agent: "I don't have access to past job records. Our team will follow up with you shortly to provide that information."
```

### Key Distinction

This is **not confidence-based gradual escalation**. It is **capability-based immediate escalation**.

| Type | Trigger | Example |
|------|---------|---------|
| **Gradual escalation (current)** | Agent tries to help, fails, customer persists → eventually escalates | Customer asks for discount; agent deflects twice; escalates on third attempt |
| **Immediate escalation (this feature)** | Agent detects question is unanswerable from first message → escalates immediately | Customer asks "What time is the technician arriving?" → agent escalates on first detection |

---

## 3. User Stories

### US-IE-01: Customer asks real-time operational question
**As a** customer who has booked an appointment,  
**I want** to ask "What time is the technician coming today?" and receive a clear answer or immediate human handoff,  
**So that** I don't waste time repeating my question to a bot that cannot help me.

**Acceptance Criteria:**
- Agent detects that "real-time dispatch information" is not in its knowledge scope
- Agent calls `escalate_to_human` immediately (first turn, no deflection)
- Agent replies: "I don't have access to real-time dispatch information, but our team will reach out to you shortly with an update on your appointment today."
- Human agent receives escalation alert with reason: "Customer asked for real-time dispatch information (ETA for today's appointment). This is outside my available data."

---

### US-IE-02: Customer asks about historical account data
**As a** returning customer,  
**I want** to ask "What's the status of my previous service?" and receive a helpful response,  
**So that** I don't have to ask multiple times before reaching someone who can answer.

**Acceptance Criteria:**
- Agent detects that "historical job status" is not available via `get_customer_bookings` (which returns future bookings only)
- Agent calls `escalate_to_human` immediately
- Agent replies: "I don't have access to past job records. Our team will follow up with you shortly to provide that information."
- Human agent receives escalation alert with reason: "Customer asked for status of a past service job. I do not have historical job records."

---

### US-IE-03: Customer asks pricing exception question
**As a** potential customer,  
**I want** to ask "Can I get a discount?" and receive a clear answer or handoff,  
**So that** I'm not given generic deflections when the agent cannot make pricing decisions.

**Acceptance Criteria:**
- Agent detects that "discount authorization" is a policy-dependent decision outside its capability
- Agent calls `escalate_to_human` immediately
- Agent replies: "I'm not able to offer discounts, but our team can discuss pricing options with you. They'll be in touch shortly."
- Human agent receives escalation alert with reason: "Customer requested a discount. Pricing exceptions require human approval."

---

### US-IE-04: Human agent receives immediate escalation alert
**As a** human agent,  
**I want** to receive escalation alerts immediately when a customer asks a question the AI cannot answer,  
**So that** I can follow up while the customer is still engaged, rather than after they've asked 2–3 times and become frustrated.

**Acceptance Criteria:**
- Escalation alert is sent via WhatsApp within 10 seconds of the customer's unanswerable question
- Alert includes the full question and a clear reason (not generic "customer needs help")
- Alert triggers on first detection, not after repeated customer attempts

---

## 4. Functional Requirements — Escalation Trigger Conditions

### REQ-IE-001: Unanswerable Question Detection

**Priority:** Critical  
**Description:** The agent must distinguish between "I need to look this up" (answerable via tools) and "I do not have access to this information" (unanswerable).

**Categories of Unanswerable Questions:**

| Category | Examples | Why Unanswerable |
|----------|----------|------------------|
| **Real-time operational data** | "What time is the technician coming?", "Is the team on the way?", "How long until they arrive?" | Agent has no live dispatch tracking, GPS, or ETA system |
| **Historical account data** | "What was the cost of my last service?", "When did you last service my unit?", "What's the status of my previous job?" | `get_customer_bookings` returns upcoming bookings only — no historical records |
| **Pricing exceptions** | "Can I get a discount?", "Do you price match?", "Can you waive the fee?" | Agent has pricing from knowledge base but cannot authorize exceptions — requires human approval |
| **Complaint resolution** | "The technician did a bad job last time", "I want a refund", "Your service was poor" | Requires human judgment and service recovery — agent cannot resolve complaints |
| **Out-of-catalogue services** | "Do you repair refrigerators?", "Can you install a new unit?", "Do you service commercial buildings?" | If service is not in knowledge base, agent does not know the answer |
| **Business process exceptions** | "Can I book for tomorrow morning?" (when lead time is 2 days), "Can you do an emergency visit tonight?" | Agent knows the policy (2-day lead time) but cannot authorize exceptions |

**Decision Rule:**

When a customer question falls into one of these categories AND the agent has confirmed:
1. The information is not in the knowledge base (services, pricing, FAQs)
2. The information is not in the policies table
3. No available tool can retrieve the information

Then the agent MUST call `escalate_to_human` immediately.

---

### REQ-IE-002: No Deflection Text Before Escalation

**Priority:** Critical  
**Description:** When the agent detects an unanswerable question, it must call `escalate_to_human` **before** generating a text reply to the customer.

**Current (incorrect) pattern:**
```
Agent: "I'm not sure about that. Let me find out for you."
[No tool call — agent waits for customer to ask again]
```

**Required pattern:**
```
Agent: [calls escalate_to_human(reason="...")]
Agent: "I don't have access to [specific type of information]. Our team will reach out to you shortly."
```

**Rationale:** Generic deflections ("I'm not sure", "Let me check") set false expectations that the agent is retrieving information. Immediate escalation paired with a clear capability statement ("I don't have access to real-time dispatch") is more transparent.

---

### REQ-IE-003: Escalation Reason Clarity

**Priority:** High  
**Description:** When calling `escalate_to_human`, the `reason` parameter must clearly state:
1. What the customer asked for
2. Why the agent cannot answer (which specific data source or capability is missing)

**Good reason examples:**
- "Customer asked for real-time dispatch information (ETA for today's appointment). This is outside my available data — I do not have live dispatch or scheduling details."
- "Customer requested a discount. Pricing exceptions require human approval."
- "Customer asked for status of a past service job (March 2026). I do not have historical job records — only upcoming bookings."

**Bad reason examples (do NOT use):**
- "Customer needs help" (too vague)
- "I don't know the answer" (does not explain why)
- "Outside my scope" (not specific enough)

---

### REQ-IE-004: Tool-Answerable Questions Must Not Escalate

**Priority:** Critical  
**Description:** Questions that CAN be answered using available tools must NOT trigger immediate escalation.

**Tool-answerable examples (do NOT escalate):**
- "Do you have availability next week?" → answerable via `check_calendar_availability`
- "What are my upcoming appointments?" → answerable via `get_customer_bookings`
- "How much does a 3-unit service cost?" → answerable from pricing knowledge base
- "What are your operating hours?" → answerable from business information in context

**Decision gate:** Before escalating, the agent must confirm that no available tool can retrieve the requested information.

---

## 5. Functional Requirements — System Prompt Changes

### REQ-IE-005: Updated Escalation Instructions

**Priority:** Critical  
**Description:** The system prompt in `context_builder.py` must be updated with new escalation instructions that distinguish "uncertain" from "unanswerable".

**Current instruction (in `_IDENTITY_BLOCK`):**
```
2. You must stay within your defined knowledge scope. Do not speculate or hallucinate facts about services, pricing, or availability.
3. If you are uncertain about any information, escalate to a human colleague immediately. Do not guess.
```

**Proposed updated instruction:**
```
2. You must stay within your defined knowledge scope. Do not speculate or hallucinate facts about services, pricing, or availability.
3. **Immediate Escalation Rule:** If a customer asks a question and you determine that:
   - The information is NOT in your knowledge base (services, pricing, FAQs, policies)
   - AND no available tool can retrieve the information
   - AND you are certain the information is outside your capability (not just uncertain)
   Then you MUST call escalate_to_human IMMEDIATELY with a clear reason. Do NOT generate a deflecting text response first.
4. **Tool-First Rule:** If a customer's question CAN be answered by calling a tool (check_calendar_availability, get_customer_bookings), always call the tool first. Only escalate if the tool fails or returns no useful data.
5. If you are uncertain about ANY information but believe it might be answerable, call the relevant tool. If the tool fails or you still cannot answer, THEN escalate.
```

**Rationale:** The current "if you are uncertain" language is ambiguous — the LLM interprets "uncertain" as "I should try to help" rather than "I should escalate". The new instruction explicitly defines the trigger condition.

---

### REQ-IE-006: Unanswerable Question Examples in System Prompt

**Priority:** High  
**Description:** The system prompt should include concrete examples of unanswerable questions to guide the LLM's decision-making.

**Proposed addition to system prompt (after the rules above):**
```
**Examples of questions you CANNOT answer (escalate immediately):**
- "What time is the technician coming today?" → No live dispatch data
- "What's the status of my previous job?" → No historical records (get_customer_bookings only returns upcoming)
- "Can I get a discount?" → Cannot authorize pricing exceptions
- "The technician did a bad job last time" → Complaint resolution requires human judgment

**Examples of questions you CAN answer (use tools or knowledge base, do NOT escalate):**
- "Do you have availability next week?" → Call check_calendar_availability
- "What are my upcoming appointments?" → Call get_customer_bookings
- "How much does a 3-unit service cost?" → Answer from pricing knowledge base
- "What are your operating hours?" → Answer from business information in context
```

---

### REQ-IE-007: No Generic Deflections

**Priority:** High  
**Description:** The system prompt must explicitly prohibit generic deflecting phrases when the agent cannot answer.

**Proposed addition:**
```
**Prohibited responses when you cannot answer:**
- "I'm not sure about that. Let me find out for you."
- "I'll check on that for you."
- "Let me look into that and get back to you."
- "I don't have that information right now, but I can help with [other thing]."

If you cannot answer, call escalate_to_human immediately and tell the customer clearly: "I don't have access to [specific type of information]. Our team will reach out to you shortly."
```

---

## 6. Functional Requirements — Tool Interface

### REQ-IE-008: No Changes to `escalate_to_human` Tool

**Priority:** Low (no action required)  
**Description:** The existing `escalate_to_human` tool interface is sufficient for this feature. No changes are needed.

**Current interface:**
```python
escalate_to_human(reason: str) -> dict
```

**Parameters:**
- `reason` (required): Free-text string describing why escalation was triggered

**Rationale:** The current `reason` parameter already supports the level of detail required by REQ-IE-003. No additional fields (e.g., `escalation_type`, `question_category`) are needed — the reason string is sufficient for human agents to understand the context.

---

### REQ-IE-009: Tool Description Update

**Priority:** Medium  
**Description:** The tool description in `engine/core/tools/definitions.py` should be updated to reflect the immediate escalation behavior.

**Current description:**
```
"Escalate the conversation to a human agent. Use this when: "
"(1) the customer explicitly asks to speak to a person, "
"(2) the requested slot is fully booked and the customer wants to arrange an alternative, "
"(3) the customer requests a reschedule or cancellation, "
"(4) the customer raises a complaint or urgent issue, "
"(5) the question is outside the scope of the agent's context. "
"After calling this, inform the customer that the team will follow up."
```

**Proposed updated description:**
```
"Escalate the conversation to a human agent. Call this IMMEDIATELY when: "
"(1) the customer explicitly asks to speak to a person, "
"(2) the customer asks a question you CANNOT answer because the information is not in your knowledge base, policies, or available tools, "
"(3) the requested slot is fully booked and the customer wants to arrange an alternative, "
"(4) the customer requests a reschedule or cancellation, "
"(5) the customer raises a complaint or urgent issue. "
"Do NOT generate a deflecting text response before calling this tool. "
"After calling this, inform the customer clearly what type of information you don't have access to and that the team will follow up."
```

**Rationale:** The updated description reinforces the immediate escalation behavior and adds the prohibition on text deflections.

---

## 7. Non-Functional Requirements

### REQ-IE-010: No Regression on Answerable Questions

**Priority:** Critical  
**Description:** This feature must NOT increase the escalation rate for questions the agent CAN answer.

**Test cases (must NOT escalate):**
- Customer asks: "Do you have availability next week?"
- Customer asks: "What are my upcoming appointments?"
- Customer asks: "How much does a 3-unit service cost?"
- Customer asks: "What are your operating hours?"
- Customer asks: "Do you service residential buildings?"

**Success criteria:** In pre-deployment testing, the agent must correctly answer these questions without escalating in 100% of test runs.

---

### REQ-IE-011: Escalation Latency Unchanged

**Priority:** High  
**Description:** Immediate escalation should NOT add latency compared to the current escalation flow.

**Target:** Escalation alert sent to human agent within 10 seconds of customer message (same as current behavior).

**Rationale:** This is a decision-making change (when to escalate), not a new integration or async process. No additional latency is expected.

---

### REQ-IE-012: Audit Trail Completeness

**Priority:** Medium  
**Description:** All immediate escalations must be logged in `escalation_tracking` with the full reason string so operators can analyze which questions trigger escalation most frequently.

**Success criteria:** After deployment, a Supabase query can retrieve:
- Count of immediate escalations per category (real-time operational, historical account, pricing exceptions, etc.)
- Most common unanswerable questions
- Ratio of immediate escalations to total escalations

**Rationale:** This data will inform future knowledge base expansions and tool development (e.g., if "What time is the technician coming?" is the #1 escalation trigger, consider building a dispatch tracking integration).

---

## 8. Out of Scope

### What This Feature Does NOT Do

| Out of Scope Item | Rationale |
|-------------------|-----------|
| **Build new tools to answer currently unanswerable questions** | This feature only changes WHEN the agent escalates — it does not add new capabilities. Future work may add a dispatch tracking tool, historical records lookup, etc. |
| **Confidence scoring or probabilistic escalation** | This is capability-based (can the agent answer yes/no), not confidence-based (how sure is the agent). Confidence-based escalation is a separate future feature. |
| **Multi-turn clarification before escalation** | If the agent cannot answer, it escalates immediately. It does NOT ask clarifying questions first (e.g., "Can you tell me more about your previous job?"). Clarification is the human agent's responsibility. |
| **Custom escalation reasons per client** | All clients use the same escalation trigger logic. Client-specific escalation rules (e.g., HeyAircon escalates pricing questions, but AnotherClient does not) are out of scope for Phase 1. |
| **Escalation routing to specific human agents** | All escalations go to `client_config.human_agent_number`. Routing based on question type (e.g., complaints to supervisor, pricing to sales) is a future feature. |

---

## 9. Open Questions for @software-architect

| ID | Question | Why It Matters |
|----|----------|----------------|
| **OQ-IE-01** | Should the system prompt changes be implemented in `context_builder.py` (hardcoded in `_IDENTITY_BLOCK`) or as a new entry in the `policies` table? | If hardcoded, all clients get the new behavior immediately. If in `policies`, clients can opt out or customize. Need to decide: is this a platform-level rule or client-configurable? |
| **OQ-IE-02** | Should we implement a **pre-escalation confirmation check** in `agent_runner.py` that validates the `reason` parameter meets REQ-IE-003 quality standards before calling the tool? | Could prevent vague reasons like "customer needs help" from reaching human agents, but adds latency and complexity. Worth it? |
| **OQ-IE-03** | Should immediate escalations be flagged differently in `escalation_tracking` (e.g., `escalation_type='immediate'` vs `escalation_type='gradual'`)? | Would enable analytics to measure immediate vs gradual escalation rates and validate that the feature is working. Requires schema change. |
| **OQ-IE-04** | Do we need a **fallback pattern** for when the LLM ignores the new system prompt instructions and still generates a text deflection? | If Claude occasionally violates the "call tool first" rule despite clear instructions, should we detect deflection text patterns ("I'm not sure", "Let me check") in `agent_runner.py` and force an escalation? Or accept that prompt compliance is probabilistic? |
| **OQ-IE-05** | Should the updated tool description (REQ-IE-009) include a **negative example** (what NOT to do) to reinforce the behavior? | E.g., "WRONG: Replying 'I'm not sure about that' without calling escalate_to_human. RIGHT: Call escalate_to_human immediately, then reply with a clear capability statement." |

---

## 10. Success Criteria

This feature will be considered successfully implemented when:

1. **Test Coverage:** A test suite with 10 unanswerable question scenarios (real-time operational, historical account, pricing exceptions, complaints, out-of-catalogue) runs successfully, and the agent calls `escalate_to_human` on first turn in 100% of cases.

2. **No Regressions:** A test suite with 10 answerable question scenarios (availability checks, pricing from knowledge base, booking lookups) runs successfully, and the agent does NOT escalate in 100% of cases.

3. **Production Validation:** After deployment, a 7-day observation window shows:
   - Average turns-to-escalation for unanswerable questions decreases from 2–3 turns to 1 turn
   - Total escalation rate increases by no more than 20% (some increase is expected as more edge cases are caught early)
   - Human agent feedback confirms escalation reasons are clear and actionable

4. **Audit Log Quality:** A manual review of 20 random immediate escalations shows that 100% of `reason` strings meet REQ-IE-003 standards (specific question + why unanswerable).

---

## 11. References

- `Product/docs/PRD-02_AI_WhatsApp_Agent.md` — Agent design, tool design, conversation flows
- `Product/docs/safety-guardrails.md` — "Do not speculate or hallucinate" rule
- `docs/architecture/code_map.md` — `context_builder.py` and `agent_runner.py` ownership
- `engine/core/message_handler.py` — Escalation gate (hard programmatic check)
- `engine/core/tools/escalation_tool.py` — Existing escalation tool implementation
- `engine/core/context_builder.py` — System prompt assembly (`_IDENTITY_BLOCK`)
- `engine/core/tools/definitions.py` — Tool definitions and descriptions
- `docs/requirements/escalation_reset.md` — Related feature (human agent resets escalation flag)
