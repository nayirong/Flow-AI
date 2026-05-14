# Immediate Escalation — Test Plan

> **Feature Test Plan**  
> Author: @sdet-engineer  
> Date: 2026-05-13  
> Architecture Spec: `docs/architecture/immediate_escalation.md`  
> Worktree: `../immediate-escalation`  
> Branch: `feat/immediate-escalation`

---

## Feature Summary

Enables the AI agent to detect when a customer question is clearly **unanswerable** (information not in knowledge base, policies, or available tools) and immediately escalate to a human agent rather than generating generic deflecting responses. This is **capability-based immediate escalation** (agent knows it cannot answer) NOT confidence-based gradual escalation (agent tries, fails, then escalates).

**Implementation approach:** System prompt enhancement only — no new code, no database changes. Extends existing `escalate_to_human` tool with clearer trigger instructions and adds 6 explicit unanswerable question categories with examples.

**Key categories:** (1) Real-time operational data, (2) Historical account data, (3) Pricing exceptions, (4) Complaint resolution, (5) Out-of-catalogue services, (6) Business process exceptions.

---

## Implementation Checklist

### 1. System Prompt Enhancement (engine/core/context_builder.py)

**File:** `engine/core/context_builder.py`  
**Constant:** `_IDENTITY_BLOCK` (lines 8–100 approximately)

#### Step 1: Replace Existing Escalation Rule (Point 3)
- [ ] Locate current text: "3. If you are uncertain about any information, escalate to a human colleague immediately. Do not guess."
- [ ] Replace with three new rules:
  - [ ] **Rule 3 (Immediate Escalation Rule):** If question is NOT in knowledge base AND no tool can retrieve it AND certain it's outside capability → call `escalate_to_human` IMMEDIATELY, do NOT generate deflecting text first
  - [ ] **Rule 4 (Tool-First Rule):** If question CAN be answered by a tool → call the tool first, only escalate if tool fails or returns no useful data
  - [ ] **Rule 5 (Uncertain but Answerable Rule):** If uncertain but believe it might be answerable → call relevant tool, if tool fails → THEN escalate

#### Step 2: Add Unanswerable Question Categories Section
- [ ] Insert new section after escalation rules, before "BOOKING RULES"
- [ ] Add header: "UNANSWERABLE QUESTION CATEGORIES (Escalate Immediately):"
- [ ] Add 6 categories with examples and instructions:
  - [ ] **Category 1:** Real-time operational data (ETA, dispatch status, "when is tech coming?") → no live tracking, escalate immediately
  - [ ] **Category 2:** Historical account data (past job cost, last service date, historical status) → `get_customer_bookings` only returns future, escalate immediately
  - [ ] **Category 3:** Pricing exceptions (discounts, price matching, fee waivers) → have pricing but cannot authorize exceptions, escalate immediately
  - [ ] **Category 4:** Complaint resolution (service quality, refunds, "bad job last time") → requires human judgment, escalate immediately
  - [ ] **Category 5:** Out-of-catalogue services (services not in knowledge base, "do you repair fridges?") → if not listed, don't know if offered, escalate immediately
  - [ ] **Category 6:** Business process exceptions (emergency bookings, policy overrides, "can you come tomorrow?" when lead time is 2 days) → know policy but cannot authorize exceptions, escalate immediately

#### Step 3: Add Tool-Answerable Counter-Examples
- [ ] Add subsection: "Tool-answerable questions (Do NOT escalate — call the tool):"
- [ ] List examples:
  - [ ] "Do you have availability next week?" → call `check_calendar_availability`
  - [ ] "What are my upcoming appointments?" → call `get_customer_bookings`
  - [ ] "How much does a 3-unit service cost?" → answer from pricing knowledge base
  - [ ] "What are your operating hours?" → answer from business information in context

#### Step 4: Add Prohibited Responses Section
- [ ] Insert after unanswerable categories, before "BOOKING RULES"
- [ ] Add header: "PROHIBITED RESPONSES (When You Cannot Answer):"
- [ ] List forbidden phrases: "I'm not sure about that. Let me find out for you.", "I don't have that information at the moment.", "Let me check on that for you.", "I'll look into that and get back to you."
- [ ] Explain: these imply retrieval when you're not retrieving
- [ ] Add correct response pattern: Call `escalate_to_human` THEN tell customer what you DON'T have access to
- [ ] List correct examples:
  - [ ] "I don't have access to real-time dispatch information. Our team will reach out shortly with an update on your appointment today."
  - [ ] "I don't have access to past job records. Our team will follow up with you shortly to provide that information."
  - [ ] "I'm not able to offer discounts, but our team can discuss pricing options with you. They'll be in touch shortly."
  - [ ] "I understand this is frustrating. Our team will reach out to resolve this for you."

#### Step 5: Add Special Case Handling for Out-of-Catalogue
- [ ] Add note after Category 5: "Special case — Out-of-catalogue services"
- [ ] Instruct: If service not in SERVICES section → first tell customer what you DO offer (list briefly)
- [ ] Then: if customer still wants out-of-catalogue service → escalate with reason "Customer requested [service] which is not in our service catalogue"
- [ ] Do NOT escalate immediately — give customer chance to pivot
- [ ] Include example conversation:
  - Customer: "Do you repair refrigerators?"
  - Agent: "We specialize in aircon servicing, chemical cleaning, and gas top-ups for residential units. We don't currently service refrigerators. Would you like to book an aircon service instead?"
  - Customer: "No, I need a fridge repair."
  - Agent: [calls escalate_to_human] "I understand. Our team will reach out to see if we can assist you with that."

### 2. Tool Description Enhancement (engine/core/tools/definitions.py)

**File:** `engine/core/tools/definitions.py`  
**Constant:** `_ESCALATE_TOOL` (or wherever `escalate_to_human` tool is defined)

- [ ] Locate current tool description for `escalate_to_human`
- [ ] Replace with new description:
  - [ ] "Escalate the conversation to a human agent. Use this tool in TWO scenarios:"
  - [ ] "1. IMMEDIATE (capability-based): You have determined the customer's question is unanswerable because the required information is not in your knowledge base, policies, or available tools. See the UNANSWERABLE QUESTION CATEGORIES in your system instructions for examples."
  - [ ] "2. GRADUAL (customer-requested): The customer explicitly asks to speak to a person, or expresses frustration/anger that requires human judgment."
  - [ ] "After calling this, you must inform the customer that a team member will follow up. Include a clear reason parameter explaining which category applies (e.g., 'Customer asked for real-time dispatch information (Category 1)' or 'Customer requested to speak to a human')."

---

## Unit Tests

**No new unit tests required.** This feature is prompt engineering only. Verification happens via eval pipeline (see Integration Tests below).

---

## Integration Tests

### File: `engine/tests/eval/test_immediate_escalation.py` (new file)

Use existing eval harness pattern. Each test scenario sends a customer message and verifies:
1. Agent calls `escalate_to_human` tool (or doesn't)
2. Agent's response text matches expected pattern
3. Escalation reason (if escalated) references correct category

#### Test 1: `test_category_1_real_time_dispatch_escalates_immediately`
- **Given:** Customer has confirmed booking for today
- **When:** Customer asks: "What time is the technician coming?"
- **Then:** Agent calls `escalate_to_human` on first message
- **And:** Escalation reason contains "real-time dispatch information" or "Category 1"
- **And:** Agent replies: "I don't have access to real-time dispatch information. Our team will reach out shortly with an update on your appointment today."
- **And:** Agent does NOT say "I'm not sure" or "Let me check"

#### Test 2: `test_category_2_historical_data_escalates_immediately`
- **Given:** Returning customer
- **When:** Customer asks: "What was the cost of my March service?"
- **Then:** Agent calls `escalate_to_human` on first message
- **And:** Escalation reason contains "historical" or "past job records" or "Category 2"
- **And:** Agent replies: "I don't have access to past job records. Our team will follow up with you shortly to provide that information."
- **And:** Agent does NOT call `get_customer_bookings` (knows that tool only returns future bookings)

#### Test 3: `test_category_3_pricing_exception_escalates_immediately`
- **Given:** Customer inquiring about service
- **When:** Customer asks: "Can I get a discount?"
- **Then:** Agent calls `escalate_to_human` on first message
- **And:** Escalation reason contains "discount" or "pricing exception" or "Category 3"
- **And:** Agent replies: "I'm not able to offer discounts, but our team can discuss pricing options with you. They'll be in touch shortly."

#### Test 4: `test_category_4_complaint_resolution_escalates_immediately`
- **Given:** Customer had previous service
- **When:** Customer says: "The technician did a bad job last time, I want a refund"
- **Then:** Agent calls `escalate_to_human` on first message
- **And:** Escalation reason contains "complaint" or "service recovery" or "refund" or "Category 4"
- **And:** Agent replies empathetically (e.g., "I understand this is frustrating. Our team will reach out to resolve this for you.")

#### Test 5: `test_category_5_out_of_catalogue_lists_services_first`
- **Given:** HeyAircon (only offers aircon services)
- **When:** Customer asks: "Do you repair refrigerators?"
- **Then:** Agent does NOT escalate immediately
- **And:** Agent lists available services: "We specialize in aircon servicing, chemical cleaning..."
- **And:** Agent asks: "Would you like to book an aircon service instead?"

#### Test 6: `test_category_5_out_of_catalogue_escalates_after_persist`
- **Given:** Customer asked about fridge repair (Slice 1 above)
- **When:** Customer responds: "No, I need a fridge repair."
- **Then:** Agent calls `escalate_to_human`
- **And:** Escalation reason contains "refrigerator" or "not in service catalogue" or "Category 5"
- **And:** Agent replies: "I understand. Our team will reach out to see if we can assist you with that."

#### Test 7: `test_category_6_business_process_exception_escalates_immediately`
- **Given:** Lead time is 2 days (in config)
- **When:** Customer asks: "Can you come tomorrow morning?"
- **Then:** Agent calls `escalate_to_human` on first message
- **And:** Escalation reason contains "emergency booking" or "lead time exception" or "Category 6"
- **And:** Agent replies: "Our standard lead time is 2 days. Our team can check if an earlier slot is possible and will follow up with you."

#### Test 8: `test_tool_answerable_does_not_escalate`
- **Given:** Customer has no bookings
- **When:** Customer asks: "Do you have availability next week?"
- **Then:** Agent calls `check_calendar_availability` with a date next week
- **And:** Agent does NOT call `escalate_to_human`
- **And:** Agent replies with availability results

#### Test 9: `test_tool_answerable_get_bookings_does_not_escalate`
- **Given:** Customer has confirmed booking for next week
- **When:** Customer asks: "What are my upcoming appointments?"
- **Then:** Agent calls `get_customer_bookings`
- **And:** Agent does NOT call `escalate_to_human`
- **And:** Agent replies with booking details

#### Test 10: `test_pricing_question_from_knowledge_base_does_not_escalate`
- **Given:** Pricing knowledge base loaded
- **When:** Customer asks: "How much does a 3-unit aircon service cost?"
- **Then:** Agent does NOT call `escalate_to_human`
- **And:** Agent does NOT call any tool (answer from knowledge)
- **And:** Agent replies with price from knowledge base

#### Test 11: `test_ambiguous_question_asks_clarification_does_not_escalate`
- **Given:** Customer asks vague question: "Can you help me with my unit?"
- **When:** Agent processes the message
- **Then:** Agent does NOT escalate immediately
- **And:** Agent asks clarifying question: "I'd be happy to help! Are you looking to book a service, check availability, or do you have a question about an existing booking?"

#### Test 12: `test_multi_part_question_handles_escalation_and_tool`
- **Given:** Customer asks: "What time is the technician coming, and do you have availability next week?"
- **When:** Agent processes
- **Then:** Agent addresses unanswerable part first (real-time dispatch → escalate)
- **And:** Agent mentions they can help with availability part: "I don't have real-time dispatch details, but I can check availability for next week if you'd like. Our team will follow up on today's appointment shortly."

#### Test 13: `test_no_deflection_phrases_before_escalation`
- **Given:** Any scenario that triggers immediate escalation (use Category 1 test)
- **When:** Agent responds
- **Then:** Agent does NOT say any prohibited phrase: "I'm not sure", "Let me find out", "Let me check on that", "I'll look into that"
- **And:** Agent's first action is calling `escalate_to_human`
- **And:** Agent's response starts with capability statement: "I don't have access to..."

---

## Regression Tests

All existing eval tests must continue to pass:
- [ ] `engine/tests/eval/test_booking_flow.py` — booking flows unchanged
- [ ] `engine/tests/eval/test_tool_use.py` — tool calling behavior unchanged (except escalation triggers more often)
- [ ] `engine/tests/eval/test_safety.py` — safety guardrails unchanged

### Specific regression checks:
- [ ] Gradual escalation still works — if customer says "I want to speak to a person", agent escalates (not just immediate escalation)
- [ ] Tool-first rule preserved — agent still calls tools when applicable before escalating
- [ ] Existing unanswerable question patterns still escalate (if they did before)

---

## Manual Verification Steps

### Verify in staging/production (post-merge):

1. **Real-time dispatch question (Category 1):**
   - [ ] Send from test customer with confirmed booking today: "What time is the tech coming?"
   - [ ] Customer receives capability statement: "I don't have access to real-time dispatch information..."
   - [ ] Check `escalation_tracking` in Supabase: escalation logged with reason containing "Category 1" or "real-time"
   - [ ] Human agent receives alert: "Customer asked for real-time dispatch information..."

2. **Historical data question (Category 2):**
   - [ ] Send from returning customer: "What was the cost of my last service?"
   - [ ] Customer receives: "I don't have access to past job records..."
   - [ ] Escalation logged with "Category 2" or "historical"
   - [ ] Agent does NOT call `get_customer_bookings` (check interaction log — no tool call before escalation)

3. **Pricing exception (Category 3):**
   - [ ] Send: "Can I get a discount?"
   - [ ] Customer receives: "I'm not able to offer discounts, but our team can discuss pricing options..."
   - [ ] Escalation logged with "Category 3" or "discount"

4. **Complaint (Category 4):**
   - [ ] Send: "The last service was terrible, I want a refund"
   - [ ] Customer receives empathetic response: "I understand this is frustrating..."
   - [ ] Escalation logged with "Category 4" or "complaint"

5. **Out-of-catalogue service (Category 5):**
   - [ ] Send: "Do you repair washing machines?"
   - [ ] Customer first receives list of available services: "We specialize in aircon servicing..."
   - [ ] Reply: "No, I need washing machine repair"
   - [ ] Now customer receives: "I understand. Our team will reach out to see if we can assist..."
   - [ ] Escalation logged with "Category 5" or "not in service catalogue"

6. **Business process exception (Category 6):**
   - [ ] Send: "Can you come today? It's an emergency"
   - [ ] Customer receives: "Our standard lead time is 2 days. Our team can check if an earlier slot is possible..."
   - [ ] Escalation logged with "Category 6" or "emergency booking"

7. **Tool-answerable question (negative test — should NOT escalate):**
   - [ ] Send: "Do you have availability next Tuesday?"
   - [ ] Customer receives availability results (not escalation)
   - [ ] Check `escalation_tracking`: no new escalation for this customer

8. **No deflection phrases:**
   - [ ] Review 10 escalated conversations in `interactions_log`
   - [ ] Confirm agent does NOT say "I'm not sure", "Let me check", "Let me find out", "I'll look into that" before escalating
   - [ ] All escalation responses start with "I don't have access to..." or "I'm not able to..."

9. **Escalation reason includes category:**
   - [ ] Review 10 escalations in `escalation_tracking` table
   - [ ] Confirm `escalation_reason` field contains category reference (e.g., "Category 1", "real-time data", "historical records")
   - [ ] Human agents should see structured reasons (not just "customer requested escalation")

---

## Definition of Done

- [ ] `_IDENTITY_BLOCK` in `context_builder.py` updated with 3 new escalation rules (points 3–5)
- [ ] Unanswerable categories section added (6 categories with examples and instructions)
- [ ] Tool-answerable counter-examples section added
- [ ] Prohibited responses section added
- [ ] Special case handling for out-of-catalogue added
- [ ] `escalate_to_human` tool description updated to reference two escalation paths (immediate + gradual)
- [ ] All 13 integration tests (eval tests) pass
- [ ] All regression tests pass (existing eval suite remains green)
- [ ] Manual verification completed for all 9 scenarios above
- [ ] No deflection phrases found in escalated conversations (spot-check 10 convos)
- [ ] Escalation reasons in `escalation_tracking` include category references (spot-check 10 escalations)
- [ ] Code formatted (project formatter)
- [ ] No linter errors
- [ ] Merged to main via PR (or direct merge if repo does not use PRs)
