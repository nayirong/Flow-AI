# Component E — Build Guide
## Escalation Flow

**Goal:** Agent correctly triggers escalation for slot conflicts, reschedule/cancellation requests, and out-of-scope queries. On every escalation: sets `escalation_flag = TRUE` in Supabase, sends a WhatsApp notification to the human agent, and applies a color-coded chat label via Meta Cloud API.
**Acceptance:** All three escalation triggers fire correctly. Human notification sent to configured number. Chat label applied. Agent silenced after escalation.

---

## Prerequisites

- [x] Component D complete — full booking flow working end-to-end
- [ ] `HUMAN_AGENT_WHATSAPP_NUMBER` set as n8n environment variable (use Flow AI number during dev)
- [ ] `LABEL_ID_OUT_OF_SCOPE`, `LABEL_ID_CONFLICT`, `LABEL_ID_CHANGE_REQUEST`, `LABEL_ID_CUSTOMER_DISTRESS` set as n8n environment variables — see Step 1

---

## Step 1 — Create Chat Labels in Meta Business Manager

Labels are created once manually. At runtime, n8n maps escalation type to label ID and fires the API.

1. Go to [business.facebook.com](https://business.facebook.com) → your WhatsApp Business Account
2. Navigate to **WhatsApp Manager** → **Labels**
3. Create four labels:

| Label name | Color | Maps to |
|------------|-------|---------|
| `Out of Scope` | 🔵 Blue | `out_of_scope` escalations |
| `Slot Conflict` | 🟠 Orange | `conflict` escalations |
| `Change Request` | 🟡 Yellow | `change_request` escalations |
| `Customer Distress` | 🔴 Red | `customer_distress` escalations |

4. After creating each label, note its **Label ID** (visible in the URL or via the API)
5. Add each Label ID as an n8n environment variable on **both** Railway services (n8n primary and n8n-worker):

| Variable | Value |
|----------|-------|
| `LABEL_ID_OUT_OF_SCOPE` | Label ID for Out of Scope |
| `LABEL_ID_CONFLICT` | Label ID for Slot Conflict |
| `LABEL_ID_CHANGE_REQUEST` | Label ID for Change Request |
| `LABEL_ID_CUSTOMER_DISTRESS` | Label ID for Customer Distress |

> **Getting Label IDs via API** if not visible in the UI:
> ```
> GET https://graph.facebook.com/v19.0/{phone-number-id}/labels
> Authorization: Bearer {META_WHATSAPP_TOKEN}
> ```

---

## Step 2 — Add Environment Variable for Human Agent Number

In Railway → **both** n8n primary and n8n-worker services → **Variables**:

| Variable | Value |
|----------|-------|
| `HUMAN_AGENT_WHATSAPP_NUMBER` | Human agent's WhatsApp number in full international format, no `+` (e.g. `6591234567`) |

During dev, set this to the Flow AI number. Switch to the client's number before UAT.

---

## Step 3 — Build `Tool - Escalate to Human` Sub-workflow

Create a new workflow named **`Tool - Escalate to Human`**.

### Node 1 — When Executed by Another Workflow (Execute Sub-Workflow Trigger)

> n8n names this node **"When Executed by Another Workflow"** by default. Use this exact name when referencing it in downstream Code nodes: `$('When Executed by Another Workflow').first().json`

Define these input fields:

| Field | Type | Description |
|-------|------|-------------|
| `escalation_type` | String | `out_of_scope`, `conflict`, or `change_request` |
| `reason` | String | Short explanation of why escalation was triggered |
| `customer_name` | String | Customer's name |
| `phone_number` | String | Customer's WhatsApp number |
| `wa_id` | String | WhatsApp internal contact ID (from webhook payload `contacts[0].wa_id`) — required for label API |
| `human_agent_number` | String | Passed from parent — `HUMAN_AGENT_WHATSAPP_NUMBER` env var |
| `phone_number_id` | String | Passed from parent — `META_PHONE_NUMBER_ID` env var |
| `whatsapp_token` | String | Passed from parent — `META_WHATSAPP_TOKEN` env var |
| `label_id_out_of_scope` | String | Passed from parent — `LABEL_ID_OUT_OF_SCOPE` env var |
| `label_id_conflict` | String | Passed from parent — `LABEL_ID_CONFLICT` env var |
| `label_id_change_request` | String | Passed from parent — `LABEL_ID_CHANGE_REQUEST` env var |
| `label_id_customer_distress` | String | Passed from parent — `LABEL_ID_CUSTOMER_DISTRESS` env var |

> `$env` and `process.env` are both blocked inside sub-workflow Code nodes. All env vars must be passed as explicit fields from the parent workflow (`WA Inbound Handler`) — same pattern as `WA Send Message`.

### Node 2 — Update Escalation Flag in Supabase (Postgres)

- Credential: `Supabase HeyAircon`
- Operation: `Execute Query`
- Query:

```sql
UPDATE customers
SET escalation_flag = TRUE, escalation_reason = '{{ $json.escalation_type }}'
WHERE phone_number = '{{ $json.phone_number }}'
```

> Escalation is a **customer state**, not a booking state — it silences the agent for this customer regardless of whether a booking exists. This means E1 (out-of-scope, no booking) correctly sets the flag as long as the customer has sent at least one message (i.e. a `customers` row exists from a prior lookup).

> **Edge case — brand new customer with no prior interaction:** If this is the customer's very first message and no booking or customer record exists yet, the UPDATE affects 0 rows. The WhatsApp notification still fires. For Phase 1 this is acceptable — in practice, an out-of-scope query from a first-time customer is rare.

### Node 3 — Build Notification (Code node — JavaScript)

Assembles the WhatsApp message to send to the human agent:

```javascript
const input = $('When Executed by Another Workflow').first().json;

const typeLabels = {
  out_of_scope: 'Out of Scope Query',
  conflict: 'Slot Conflict',
  change_request: 'Reschedule / Cancellation Request',
  customer_distress: 'Customer Distress',
};

const label = typeLabels[input.escalation_type] || input.escalation_type;

const labelIds = {
  out_of_scope: input.label_id_out_of_scope,
  conflict: input.label_id_conflict,
  change_request: input.label_id_change_request,
  customer_distress: input.label_id_customer_distress,
};

const labelId = labelIds[input.escalation_type] || null;

const message = [
  `*HeyAircon Escalation Alert*`,
  ``,
  `Type: ${label}`,
  `Customer: ${input.customer_name || 'Unknown'}`,
  `Phone: +${input.phone_number}`,
  `Reason: ${input.reason}`,
  ``,
  `Please follow up with the customer directly on WhatsApp.`,
].join('\n');

return [{
  json: {
    ...input,
    label_id: labelId,
    human_number: input.human_agent_number,
    notification_message: message,
  }
}];
```

### Node 4 — Send WhatsApp Notification (Execute Sub-Workflow)

- Workflow: `WA Send Message`
- Inputs:

| Field | Value |
|-------|-------|
| `to` | `{{$json.human_number}}` |
| `message` | `{{$json.notification_message}}` |
| `phone_number_id` | `{{$json.phone_number_id}}` |
| `whatsapp_token` | `{{$json.whatsapp_token}}` |

> `phone_number_id` and `whatsapp_token` are read from `process.env` in Node 3 and passed through here. `$env` expressions are blocked in sub-workflows, but `process.env` in Code nodes works — this is the same pattern used throughout the project.

### Node 5a — Has Label? (IF node)

Guard against escalation types with no mapped label ID (e.g. if an env var is missing).

- Condition: `{{$('Build Notification').first().json.label_id}}` **is not empty**
- TRUE → Node 5b (apply label)
- FALSE → Node 6 (skip label, continue to return result)

### Node 5b — Apply Chat Label (HTTP Request node)

Applies the color-coded label to the customer's WhatsApp chat via Meta Cloud API.

- Method: `POST`
- URL: `https://graph.facebook.com/v19.0/{{$('Build Notification').first().json.phone_number_id}}/contacts/{{$('Build Notification').first().json.wa_id}}/labels`
- Authentication: Generic Credential Type → Header Auth
  - Name: `Authorization`
  - Value: `Bearer {{$('Build Notification').first().json.whatsapp_token}}`
- Body Content Type: `JSON`
- Body (JSON):

```json
{
  "label_id": "{{$('Build Notification').first().json.label_id}}"
}
```

Connect both Node 5b TRUE output and Node 5a FALSE output to Node 6.

### Node 6 — Return Result (Code node — JavaScript)

```javascript
return [{
  json: {
    success: true,
    escalation_type: $('Build Notification').first().json.escalation_type,
    message: 'Customer has been escalated. Our team will reach out to you shortly.'
  }
}];
```

---

## Step 4 — Register `escalate_to_human` Tool on AI Agent

In `WA Inbound Handler` → AI Agent node → **Tools** connector → add **Call n8n Workflow Tool**:

- **Name:** `escalate_to_human`
- **Description:** `Flags the customer for human follow-up. Call when: (1) a requested booking slot has a conflict, (2) a customer wants to reschedule or cancel, (3) a customer asks something you cannot answer after one genuine attempt. Always tell the customer a team member will reach out shortly before ending the conversation.`
- **Workflow:** select `Tool - Escalate to Human`
- **Input Schema:** `escalation_type` (String), `reason` (String), `customer_name` (String)
- Workflow inputs:

| Field | Value |
|-------|-------|
| `escalation_type` | `{{ $fromAI('escalation_type', 'out_of_scope, conflict, or change_request') }}` |
| `reason` | `{{ $fromAI('reason', 'Brief explanation of why escalation was triggered') }}` |
| `customer_name` | `{{ $fromAI('customer_name', 'Customer full name') }}` |
| `phone_number` | `{{ $('Extract Message Fields').first().json.phone_number }}` |
| `wa_id` | `{{ $('Extract Message Fields').first().json.wa_id }}` |
| `human_agent_number` | `{{ $env.HUMAN_AGENT_WHATSAPP_NUMBER }}` |
| `phone_number_id` | `{{ $env.META_PHONE_NUMBER_ID }}` |
| `whatsapp_token` | `{{ $env.META_WHATSAPP_TOKEN }}` |
| `label_id_out_of_scope` | `{{ $env.LABEL_ID_OUT_OF_SCOPE }}` |
| `label_id_conflict` | `{{ $env.LABEL_ID_CONFLICT }}` |
| `label_id_change_request` | `{{ $env.LABEL_ID_CHANGE_REQUEST }}` |
| `label_id_customer_distress` | `{{ $env.LABEL_ID_CUSTOMER_DISTRESS }}` |

`phone_number`, `wa_id`, and all env vars are passed as fixed expressions — not inferred by the LLM. `$env` works here because this input is set in the parent workflow (`WA Inbound Handler`), not inside the sub-workflow.

---

## Step 5 — Update Escalation Policy in Supabase

In Supabase Studio → `policies` table → update the `escalation_policy` row (`policy_text` column):

```
Escalate to a human team member in these three situations only:

1. Slot conflict — the requested date and time window is already booked. Inform the customer the slot is unavailable, call escalate_to_human with escalation_type = conflict, then tell the customer a team member will reach out to arrange an alternative time.

2. Reschedule or cancellation request — the customer wants to change or cancel an existing booking. Share the rescheduling/cancellation policy, call escalate_to_human with escalation_type = change_request, then tell the customer a team member will be in touch.

3. Out-of-scope query — the customer asks something you cannot answer after one genuine attempt. Call escalate_to_human with escalation_type = out_of_scope, then tell the customer a team member will follow up.

Always tell the customer: "A member of our team will reach out to you shortly." before ending the message. Never escalate for routine FAQ questions about pricing or services — answer those directly.
```

---

## Step 6 — Add Holding Reply to `WA Inbound Handler`

In `WA Inbound Handler`, on the `Is Escalated? → TRUE` branch, after `Log Inbound (Escalated)`, add an **Execute Sub-Workflow** node:

- **Workflow:** `WA Send Message`
- **Inputs:**

| Field | Value |
|-------|-------|
| `to` | `{{$('Extract Message Fields').first().json.phone_number}}` |
| `message` | `Our team is currently looking into your request. A member of our team will be in touch with you shortly.` |
| `phone_number_id` | `{{$env.META_PHONE_NUMBER_ID}}` |
| `whatsapp_token` | `{{$env.META_WHATSAPP_TOKEN}}` |

Terminate after this node — no further nodes on the TRUE branch.

---

## Step 7 — Test Escalation Scenarios

Clear Postgres memory before each test:
```sql
DELETE FROM n8n_chat_histories;
```

> **Note on `wa_id` in curl tests:** Real Meta webhooks populate `contacts[0].wa_id` automatically. In curl tests, add it manually as a mock value — it must be present for Node 5b to fire. Use the same value as `from` during dev (real `wa_id` differs in production but this is sufficient for flow testing).

**Test E1 — Out of scope query**

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"Can you help me fix my washing machine?"},"type":"text","id":"e_test_001"}],"contacts":[{"profile":{"name":"Test Customer"},"wa_id":"6582829071"}]}}]}]}'
```

Expected:
- Agent attempts to answer, cannot, calls `escalate_to_human` with `out_of_scope`
- `escalation_flag = TRUE` in Supabase `customers` table — verify:
  ```sql
  SELECT phone_number, escalation_flag, escalation_reason FROM customers WHERE phone_number = '6582829071';
  ```
- WhatsApp notification sent to `HUMAN_AGENT_WHATSAPP_NUMBER`
- Chat label API attempted (Node 5b fires — expect Meta error response since test number doesn't support labels)
- Agent tells customer a team member will reach out

**Test E2 — Slot conflict**

First create a booking for a slot, then try to book the same slot again (different session):

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"I want to book a chemical wash on 15 April AM slot"},"type":"text","id":"e_test_002"}],"contacts":[{"profile":{"name":"Test Customer"},"wa_id":"6582829071"}]}}]}]}'
```

Expected:
- `check_calendar_availability` returns `available: false`
- Agent calls `escalate_to_human` with `conflict`
- WhatsApp notification sent, chat label API attempted
- `escalation_flag = TRUE` in Supabase `customers` table — verify:
  ```sql
  SELECT phone_number, escalation_flag, escalation_reason FROM customers WHERE phone_number = '6582829071';
  ```
- Customer told team will reach out to arrange alternative

**Test E3 — Reschedule request**

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"I need to reschedule my booking"},"type":"text","id":"e_test_003"}],"contacts":[{"profile":{"name":"Test Customer"},"wa_id":"6582829071"}]}}]}]}'
```

Expected:
- Agent shares rescheduling policy (48 hours notice)
- Calls `escalate_to_human` with `change_request`
- WhatsApp notification sent, chat label API attempted
- `escalation_flag = TRUE` in Supabase `customers` table — verify:
  ```sql
  SELECT phone_number, escalation_flag, escalation_reason FROM customers WHERE phone_number = '6582829071';
  ```
- Customer told team will be in touch

**Test E4 — Agent silenced after escalation**

Run this immediately after any of E1/E2/E3 (all three now set `escalation_flag = TRUE` on the `customers` row).

Send another message from the same number:

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"What is your price for general servicing?"},"type":"text","id":"e_test_004"}],"contacts":[{"profile":{"name":"Test Customer"},"wa_id":"6582829071"}]}}]}]}'
```

Expected:
- Layer 1 reads `escalation_flag = TRUE` from Supabase `customers` table
- Workflow stops after sending holding reply — no AI agent invoked
- Customer receives: "Our team is currently looking into your request. A member of our team will be in touch with you shortly."
- Execution log shows: `Is Escalated?` → TRUE → `Log Inbound (Escalated)` → `Send Holding Reply` → stop

---

## Acceptance Criteria

- [ ] `HUMAN_AGENT_WHATSAPP_NUMBER` env var set on both Railway services
- [ ] `LABEL_ID_*` env vars set with real Meta label IDs on both Railway services
- [ ] `wa_id` field added to `Extract Message Fields` node in `WA Inbound Handler`
- [ ] `Tool - Escalate to Human` sub-workflow built and published
- [ ] `escalate_to_human` tool registered on AI Agent (including `wa_id` fixed input)
- [ ] `escalation_policy` updated in Supabase `policies` table
- [ ] `Send Holding Reply` node added to `WA Inbound Handler` TRUE branch
- [ ] Test E1 passed — out of scope escalation fires correctly
- [ ] Test E2 passed — conflict escalation fires correctly
- [ ] Test E3 passed — change request escalation fires correctly
- [ ] Test E4 passed — agent silenced after escalation flag set
- [ ] WhatsApp notification received on human agent number for each test
- [ ] Chat label applied via Meta API for each test (visible in n8n execution log)
- [ ] `escalation_flag = TRUE` visible in Supabase `customers` table after each test

---

## Next: End-to-End Testing
Once all escalation scenarios pass, proceed to full E2E scripted testing across Components A–E before client walkthrough.
