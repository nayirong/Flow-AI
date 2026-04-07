# Component E — Build Guide
## Escalation Flow

**Goal:** Agent correctly triggers escalation for slot conflicts, reschedule/cancellation requests, and out-of-scope queries. On every escalation: sets `escalation_flag = TRUE` in Sheets, sends a WhatsApp notification to the human agent, and applies a color-coded chat label via Meta Cloud API.
**Acceptance:** All three escalation triggers fire correctly. Human notification sent to configured number. Agent silenced after escalation.

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
5. Add each Label ID as an n8n environment variable on the Railway primary service:

| Variable | Value |
|----------|-------|
| `LABEL_ID_OUT_OF_SCOPE` | Label ID for Out of Scope |
| `LABEL_ID_CONFLICT` | Label ID for Slot Conflict |
| `LABEL_ID_CHANGE_REQUEST` | Label ID for Change Request |
| `LABEL_ID_CUSTOMER_DISTRESS` | Label ID for Customer Distress |

> **Getting Label IDs via API** if not visible in the UI:
> ```
> GET https://graph.facebook.com/v18.0/{phone-number-id}/labels
> Authorization: Bearer {WHATSAPP_TOKEN}
> ```

---

## Step 2 — Add Environment Variable for Human Agent Number

In Railway → primary service → **Variables**:

| Variable | Value |
|----------|-------|
| `HUMAN_AGENT_WHATSAPP_NUMBER` | Human agent's WhatsApp number in full international format, no `+` (e.g. `6591234567`) |

During dev, set this to the Flow AI number. Switch to the client's number before UAT.

---

## Step 3 — Build `Tool - Escalate to Human` Sub-workflow

Create a new workflow named **`Tool - Escalate to Human`**.

### Node 1 — Execute Sub-Workflow Trigger

Define these input fields:

| Field | Type | Description |
|-------|------|-------------|
| `escalation_type` | String | `out_of_scope`, `conflict`, or `change_request` |
| `reason` | String | Short explanation of why escalation was triggered |
| `customer_name` | String | Customer's name |
| `phone_number` | String | Customer's WhatsApp number |

### Node 2 — Set Escalation Flag in Sheets (Google Sheets)

- Operation: `Update`
- Sheet: `Customers`
- **Column to Match On:** `phone_number`
- Fields to update:

| Field | Value |
|-------|-------|
| `escalation_flag` | `TRUE` |
| `escalation_reason` | `{{$json.escalation_type}}` |

> This is what silences the agent for future messages — the Layer 1 gate in `WA Inbound Handler` reads this flag.

### Node 3 — Build Notification (Code node — JavaScript)

Assembles the WhatsApp message to send to the human agent:

```javascript
const input = $input.first().json;

const typeLabels = {
  out_of_scope: 'Out of Scope Query',
  conflict: 'Slot Conflict',
  change_request: 'Reschedule / Cancellation Request',
  customer_distress: 'Customer Distress',
};

const label = typeLabels[input.escalation_type] || input.escalation_type;

const labelIds = {
  out_of_scope: process.env.LABEL_ID_OUT_OF_SCOPE,
  conflict: process.env.LABEL_ID_CONFLICT,
  change_request: process.env.LABEL_ID_CHANGE_REQUEST,
  customer_distress: process.env.LABEL_ID_CUSTOMER_DISTRESS,
};

const labelId = labelIds[input.escalation_type] || null;

const humanNumber = process.env.HUMAN_AGENT_WHATSAPP_NUMBER;

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
    human_number: humanNumber,
    notification_message: message,
  }
}];
```

### Node 4 — Send WhatsApp Notification (Execute Sub-Workflow)

- Workflow: `WA Send Message`
- Inputs:
  - `to`: `{{$json.human_number}}`
  - `message`: `{{$json.notification_message}}`

This reuses the existing `WA Send Message` sub-workflow — no new HTTP Request node needed.

### Node 5 — Apply Chat Label (HTTP Request node)

Applies the color-coded label to the customer's WhatsApp chat via Meta Cloud API.

- Method: `POST`
- URL: `https://graph.facebook.com/v18.0/{{$env.WHATSAPP_PHONE_NUMBER_ID}}/messages`
- Authentication: Generic Credential Type → Header Auth
  - Name: `Authorization`
  - Value: `Bearer {{$env.WHATSAPP_TOKEN}}`
- Body Content Type: `JSON`
- Body (JSON):

```json
{
  "messaging_product": "whatsapp",
  "to": "{{$('Build Notification').first().json.phone_number}}",
  "type": "reaction",
  "reaction": {
    "message_id": "placeholder",
    "emoji": ""
  }
}
```

> **Note:** WhatsApp Cloud API uses a **label** endpoint, not the messages endpoint. The correct call is:
> ```
> POST https://graph.facebook.com/v18.0/{phone-number-id}/contacts/{wa_id}/labels
> Body: { "label_id": "{label_id}" }
> ```
> However this endpoint requires the WhatsApp contact ID (`wa_id`), not just the phone number. For Phase 1, **skip the label API call** and rely on the WhatsApp notification to the human agent alone. Add the label API in Phase 1.5 once you have confirmed the correct endpoint and wa_id mapping. See Note below.

**Phase 1 Node 5 — Skip label, use a Code node as placeholder:**

```javascript
// Label API deferred to Phase 1.5 — wa_id mapping required
// For now, log the intended label for manual reference
const input = $('Build Notification').first().json;
return [{
  json: {
    success: true,
    escalation_type: input.escalation_type,
    label_id: input.label_id,
    note: 'Label API deferred — apply label manually in Meta Business Manager for now'
  }
}];
```

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

`phone_number` is passed as a fixed expression — not inferred by the LLM.

---

## Step 5 — Update Escalation Policy in Sheets

In `HeyAircon CRM` → `Policies` sheet → update the `escalation_policy` row:

```
Escalate to a human team member in these three situations only:

1. Slot conflict — the requested date and time window is already booked. Inform the customer the slot is unavailable, call escalate_to_human with escalation_type = conflict, then tell the customer a team member will reach out to arrange an alternative time.

2. Reschedule or cancellation request — the customer wants to change or cancel an existing booking. Share the rescheduling/cancellation policy, call escalate_to_human with escalation_type = change_request, then tell the customer a team member will be in touch.

3. Out-of-scope query — the customer asks something you cannot answer after one genuine attempt. Call escalate_to_human with escalation_type = out_of_scope, then tell the customer a team member will follow up.

Always tell the customer: "A member of our team will reach out to you shortly." before ending the message. Never escalate for routine FAQ questions about pricing or services — answer those directly.
```

---

## Step 6 — Test Escalation Scenarios

Clear Postgres memory before each test:
```sql
DELETE FROM n8n_chat_histories;
```

**Test E1 — Out of scope query**

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"Can you help me fix my washing machine?"},"type":"text","id":"e_test_001"}],"contacts":[{"profile":{"name":"Test Customer"}}]}}]}]}'
```

Expected:
- Agent attempts to answer, cannot, calls `escalate_to_human` with `out_of_scope`
- `escalation_flag = TRUE` written to Customers sheet
- WhatsApp notification sent to `HUMAN_AGENT_WHATSAPP_NUMBER`
- Agent tells customer a team member will reach out

**Test E2 — Slot conflict**

First create a booking for a slot, then try to book the same slot again (different session):

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"I want to book a chemical wash on 15 April AM slot"},"type":"text","id":"e_test_002"}],"contacts":[{"profile":{"name":"Test Customer"}}]}}]}]}'
```

Expected:
- `check_calendar_availability` returns `available: false`
- Agent calls `escalate_to_human` with `conflict`
- Notification sent to human agent
- Customer told team will reach out to arrange alternative

**Test E3 — Reschedule request**

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"I need to reschedule my booking"},"type":"text","id":"e_test_003"}],"contacts":[{"profile":{"name":"Test Customer"}}]}}]}]}'
```

Expected:
- Agent shares rescheduling policy (48 hours notice)
- Calls `escalate_to_human` with `change_request`
- Notification sent
- Customer told team will be in touch

**Test E4 — Agent silenced after escalation**

Immediately after Test E1/E2/E3, send another message from the same number:

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"What is your price for general servicing?"},"type":"text","id":"e_test_004"}],"contacts":[{"profile":{"name":"Test Customer"}}]}}]}]}'
```

Expected:
- Layer 1 reads `escalation_flag = TRUE`
- Workflow stops — no agent response sent
- Execution log shows stop at `Is Escalated?` node

---

## Acceptance Criteria

- [ ] `HUMAN_AGENT_WHATSAPP_NUMBER` env var set
- [ ] Label IDs created in Meta (can be placeholder values for Phase 1)
- [ ] `Tool - Escalate to Human` sub-workflow built and published
- [ ] `escalate_to_human` tool registered on AI Agent
- [ ] `escalation_policy` updated in Policies sheet
- [ ] Test E1 passed — out of scope escalation fires correctly
- [ ] Test E2 passed — conflict escalation fires correctly
- [ ] Test E3 passed — change request escalation fires correctly
- [ ] Test E4 passed — agent silenced after escalation flag set
- [ ] WhatsApp notification received on human agent number for each test
- [ ] `escalation_flag = TRUE` visible in Customers sheet after each test

---

## Deferred: Chat Label API (Phase 1.5)

The Meta Cloud API label endpoint requires a `wa_id` (internal WhatsApp contact ID) which differs from the customer's phone number. Mapping phone number → wa_id requires either:
- Storing `wa_id` from the initial webhook payload (it's present in `contacts[0].wa_id`)
- Or making a contacts lookup API call before applying the label

**Phase 1.5 fix:**
1. In `Extract Message Fields` Set node — add `wa_id` field: `{{$json.entry[0].changes[0].value.contacts[0].wa_id}}`
2. Pass `wa_id` through to the escalation tool
3. Replace the Node 5 placeholder Code node with the actual HTTP Request:
   - `POST https://graph.facebook.com/v18.0/{phone-number-id}/contacts/{wa_id}/labels`
   - Body: `{ "label_id": "{label_id}" }`

---

## Next: End-to-End Testing
Once all escalation scenarios pass, proceed to full E2E scripted testing across Components A–E before client walkthrough.
