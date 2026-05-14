# Task: Immediate Escalation
> Assigned to: @software-engineer  
> Branch: feat/immediate-escalation  
> Worktree: ../immediate-escalation  
> Architecture spec: docs/architecture/immediate_escalation.md  
> Test plan: docs/test-plan/features/immediate_escalation.md

---

## Context

Enables the AI agent to detect when a customer question is clearly **unanswerable** (information not in knowledge base, policies, or available tools) and immediately escalate to a human agent rather than generating generic deflecting responses. This is **capability-based immediate escalation** (agent knows it cannot answer upfront) NOT confidence-based gradual escalation (agent tries, fails, then escalates).

**Key approach:** System prompt enhancement only — no new code, no database changes. Adds 6 explicit unanswerable question categories with examples, clearer escalation rules, and prohibited deflection phrases.

**Categories:** (1) Real-time operational data, (2) Historical account data, (3) Pricing exceptions, (4) Complaint resolution, (5) Out-of-catalogue services, (6) Business process exceptions.

---

## Implementation Order

Work in this exact order:

1. **System prompt enhancement** (`engine/core/context_builder.py` — `_IDENTITY_BLOCK`)
2. **Tool description enhancement** (`engine/core/tools/definitions.py` — `escalate_to_human` tool)
3. **Eval tests** (`engine/tests/eval/test_immediate_escalation.py` — new file with 13 tests)

---

## File 1: engine/core/context_builder.py

### What to change:
Update `_IDENTITY_BLOCK` constant with new escalation rules, categories, counter-examples, and prohibited responses.

### Location:
Find `_IDENTITY_BLOCK = """` near top of file (around line 8-100).

### Exact changes (in order):

#### Step 1: Replace existing escalation rule (Point 3)

**Find this text:**
```
3. If you are uncertain about any information, escalate to a human colleague immediately. Do not guess.
```

**Replace with:**
```
3. **Immediate Escalation Rule:** If a customer asks a question and you determine that:
   - The information is NOT in your knowledge base (services, pricing, FAQs, policies)
   - AND no available tool can retrieve the information
   - AND you are certain the information is outside your capability (not just uncertain)
   Then you MUST call escalate_to_human IMMEDIATELY with a clear reason. Do NOT generate a deflecting text response first.

4. **Tool-First Rule:** If a customer's question CAN be answered by calling a tool (check_calendar_availability, get_customer_bookings), always call the tool first. Only escalate if the tool fails or returns no useful data.

5. If you are uncertain about ANY information but believe it might be answerable, call the relevant tool. If the tool fails or you still cannot answer, THEN escalate.
```

#### Step 2: Add unanswerable categories section

**Insert after the escalation rules (new points 3-5), before "BOOKING RULES" section:**

```
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

**Tool-answerable questions (Do NOT escalate — call the tool):**
- "Do you have availability next week?" → call check_calendar_availability
- "What are my upcoming appointments?" → call get_customer_bookings
- "How much does a 3-unit service cost?" → answer from pricing knowledge base
- "What are your operating hours?" → answer from business information in context
```

#### Step 3: Add prohibited responses section

**Insert after unanswerable categories, before "BOOKING RULES":**

```
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

---

## File 2: engine/core/tools/definitions.py

### What to change:
Update `escalate_to_human` tool description to reference two escalation paths (immediate + gradual).

### Location:
Search for the tool definitions. Look for a dict or constant that defines `escalate_to_human` tool (likely a dict with keys `name`, `description`, `input_schema`).

### Exact change:

**Find the `description` field for `escalate_to_human` tool.**

**Replace existing description with:**

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

---

## File 3: engine/tests/eval/test_immediate_escalation.py (new file)

### What to create:
Eval test file with 13 test scenarios covering immediate escalation behavior.

### Test structure:
Use existing eval test patterns from `engine/tests/eval/test_booking_flow.py` or similar. Each test:
1. Constructs a customer message
2. Calls the agent via eval harness
3. Verifies tool calls (presence/absence of `escalate_to_human`)
4. Verifies response text (checks for prohibited phrases, correct capability statements)
5. Verifies escalation reason (if escalated, reason contains category reference)

### Tests to implement:

#### Test 1: test_category_1_real_time_dispatch_escalates_immediately
- **Setup:** Customer with confirmed booking for today
- **Message:** "What time is the technician coming?"
- **Verify:** Agent calls `escalate_to_human` on first message
- **Verify:** Escalation reason contains "real-time dispatch" or "Category 1"
- **Verify:** Agent response: "I don't have access to real-time dispatch information..."
- **Verify:** Agent does NOT say "I'm not sure" or "Let me check"

#### Test 2: test_category_2_historical_data_escalates_immediately
- **Setup:** Returning customer
- **Message:** "What was the cost of my March service?"
- **Verify:** Agent calls `escalate_to_human` on first message
- **Verify:** Reason contains "historical" or "past job records" or "Category 2"
- **Verify:** Response: "I don't have access to past job records..."
- **Verify:** Agent does NOT call `get_customer_bookings`

#### Test 3: test_category_3_pricing_exception_escalates_immediately
- **Setup:** Customer inquiring about service
- **Message:** "Can I get a discount?"
- **Verify:** Escalates immediately
- **Verify:** Reason contains "discount" or "pricing exception" or "Category 3"
- **Verify:** Response: "I'm not able to offer discounts, but our team can discuss pricing options..."

#### Test 4: test_category_4_complaint_resolution_escalates_immediately
- **Setup:** Customer had previous service
- **Message:** "The technician did a bad job last time, I want a refund"
- **Verify:** Escalates immediately
- **Verify:** Reason contains "complaint" or "service recovery" or "refund" or "Category 4"
- **Verify:** Empathetic response: "I understand this is frustrating..."

#### Test 5: test_category_5_out_of_catalogue_lists_services_first
- **Setup:** HeyAircon (aircon services only)
- **Message:** "Do you repair refrigerators?"
- **Verify:** Agent does NOT escalate immediately
- **Verify:** Response lists available services: "We specialize in aircon servicing..."
- **Verify:** Asks if customer wants offered service instead

#### Test 6: test_category_5_out_of_catalogue_escalates_after_persist
- **Setup:** Follow-up to Test 5
- **Message:** "No, I need a fridge repair."
- **Verify:** Agent escalates now
- **Verify:** Reason contains "refrigerator" or "not in service catalogue" or "Category 5"
- **Verify:** Response: "I understand. Our team will reach out..."

#### Test 7: test_category_6_business_process_exception_escalates_immediately
- **Setup:** Lead time is 2 days (from config)
- **Message:** "Can you come tomorrow morning?"
- **Verify:** Escalates immediately
- **Verify:** Reason contains "emergency booking" or "lead time exception" or "Category 6"
- **Verify:** Response: "Our standard lead time is 2 days. Our team can check if an earlier slot is possible..."

#### Test 8: test_tool_answerable_does_not_escalate
- **Setup:** Customer has no bookings
- **Message:** "Do you have availability next week?"
- **Verify:** Agent calls `check_calendar_availability`
- **Verify:** Agent does NOT call `escalate_to_human`
- **Verify:** Agent replies with availability results

#### Test 9: test_tool_answerable_get_bookings_does_not_escalate
- **Setup:** Customer has confirmed booking for next week
- **Message:** "What are my upcoming appointments?"
- **Verify:** Agent calls `get_customer_bookings`
- **Verify:** Agent does NOT call `escalate_to_human`
- **Verify:** Agent replies with booking details

#### Test 10: test_pricing_question_from_knowledge_base_does_not_escalate
- **Setup:** Pricing knowledge base loaded
- **Message:** "How much does a 3-unit aircon service cost?"
- **Verify:** Agent does NOT call `escalate_to_human`
- **Verify:** Agent does NOT call any tool (answer from knowledge)
- **Verify:** Agent replies with price from knowledge base

#### Test 11: test_ambiguous_question_asks_clarification_does_not_escalate
- **Setup:** None
- **Message:** "Can you help me with my unit?"
- **Verify:** Agent does NOT escalate immediately
- **Verify:** Agent asks clarifying question

#### Test 12: test_multi_part_question_handles_escalation_and_tool
- **Setup:** None
- **Message:** "What time is the technician coming, and do you have availability next week?"
- **Verify:** Agent addresses unanswerable part (real-time dispatch → escalate)
- **Verify:** Agent mentions they can help with availability part

#### Test 13: test_no_deflection_phrases_before_escalation
- **Setup:** Use Category 1 scenario
- **Message:** "What time is the tech coming?"
- **Verify:** Agent does NOT say any prohibited phrase: "I'm not sure", "Let me find out", "Let me check on that", "I'll look into that"
- **Verify:** Agent's first action is calling `escalate_to_human`
- **Verify:** Response starts with capability statement: "I don't have access to..."

---

## Constraints

- Work only inside the worktree (../immediate-escalation)
- No direct commits to master
- Run existing eval tests before starting to confirm clean baseline: `cd engine && python -m pytest tests/eval/ -v`
- After implementation: `git add`, `git commit -m "feat: immediate escalation prompt enhancements"`, `git log --oneline -3` to confirm
- Format code before committing: `cd engine && python -m black . && python -m isort .`
- This is a PROMPT ENGINEERING task — no new Python functions, no new database schema. Only text changes in prompt and tool description.

---

## Validate

After all changes made and tests written:

1. Run new eval tests: `cd engine && python -m pytest tests/eval/test_immediate_escalation.py -v`
2. Run regression eval tests: `cd engine && python -m pytest tests/eval/test_booking_flow.py tests/eval/test_tool_use.py tests/eval/test_safety.py -v`
3. Spot-check prompt changes: `grep -A 5 "UNANSWERABLE QUESTION CATEGORIES" engine/core/context_builder.py` (should show the new section)
4. Confirm all pass before reporting done

---

## Report Back With

1. Files changed (list with line counts: `wc -l <file>`)
2. Tests added (count: `grep -c "^async def test_" tests/eval/test_immediate_escalation.py`)
3. Test results (paste pytest output showing pass/fail counts for new + regression tests)
4. Git log entry (paste output of `git log --oneline -3`)
5. Snippet of updated prompt (paste 10 lines from "UNANSWERABLE QUESTION CATEGORIES" section to confirm it's in place)
