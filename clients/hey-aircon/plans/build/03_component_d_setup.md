# Component D — Build Guide
## Booking Flow Tools

**Goal:** Agent can check calendar availability, create bookings, and write records to Sheets end-to-end for a free slot.
**Acceptance:** Customer goes from "I want to book" → calendar checked → event created → Sheets row written → confirmation message sent.

---

## Prerequisites

- [x] Component B + C complete — AI Agent responding correctly via curl tests
- [x] `agent.heyaircon@gmail.com` Google account created
- [x] `HeyAircon CRM` Google Sheet owned by `agent.heyaircon@gmail.com`
- [ ] Google Calendar created under `agent.heyaircon@gmail.com` — see Step 1
- [ ] Google Calendar credential added in n8n — see Step 2
- [ ] Build Context code node updated to inject today's date — see note in `02_component_b_c_setup.md`. **Required before testing** — without this the agent cannot correctly evaluate the 2-day minimum notice requirement and will incorrectly reject valid dates.

---

## Step 1 — Create Google Calendar

1. Log in to Google Calendar at [calendar.google.com](https://calendar.google.com) as `agent.heyaircon@gmail.com`
2. In the left sidebar → **Other calendars** → click **"+"** → **Create new calendar**
3. Name it: `HeyAircon Bookings`
4. Click **Create calendar**
5. Once created, click the three-dot menu next to `HeyAircon Bookings` → **Settings and sharing**
6. Scroll to **Integrate calendar** → copy the **Calendar ID** (looks like `xxxxxxxx@group.calendar.google.com` or the Gmail address for the primary calendar)
7. **Calendar ID: `agent.heyaircon@gmail.com`** — use this when selecting the calendar in Google Calendar nodes in n8n

---

## Step 2 — Add Google Calendar Credential in n8n

The existing `HeyAircon Sheets` credential uses **Google Sheets OAuth2 API** which is Sheets-specific and does not have Calendar scope. A separate Calendar credential is required.

1. In n8n → **Credentials** → **Add** → search `Google Calendar` → select **Google Calendar OAuth2 API**
2. Sign in with `agent.heyaircon@gmail.com`
3. Grant the requested Calendar permissions
4. Name it: `HeyAircon Calendar`

> **Enable Calendar API first:** The Google Cloud project used for HeyAircon Sheets must also have the **Google Calendar API** enabled. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Enable APIs → search **Google Calendar API** → Enable. If you used n8n's built-in OAuth (no custom Google Cloud project), this step is not needed — n8n handles it automatically.

---

## Important — How Tool Inputs Work ($fromAI Pattern)

When a workflow is called as a tool via **Call n8n Workflow Tool**, the correct way to pass values from the AI Agent into the sub-workflow is via **`$fromAI()`** expressions set directly on the workflow input fields in the **Call n8n Workflow Tool** node — not by parsing a JSON string inside the sub-workflow.

**Do NOT use a Parse Tool Input Code node.** Earlier versions of this guide used that approach; it produced null values. The `$fromAI()` approach is correct.

### How to configure Call n8n Workflow Tool inputs

For each input field defined in the sub-workflow's Execute Sub-Workflow Trigger, set the value in the Call n8n Workflow Tool node using:

```
{{ $fromAI('fieldname', 'description of what this field is') }}
```

Example for the `date` field:
```
{{ $fromAI('date', 'Booking date in YYYY-MM-DD format') }}
```

The field name in `$fromAI()` must exactly match the field name defined in the trigger node. See each tool section below for the full list of `$fromAI()` expressions to use.

### Null guard in sub-workflow Code nodes

n8n sends a schema probe call before the real call — inputs arrive as null. Add a null guard at the top of any Code node that uses these inputs:

```javascript
const date = $input.first().json.date;
const window = $input.first().json.window;
if (!date || !window) return [{ json: { available: false, reason: 'probe' } }];
```

---

## Step 3 — Overview of Tools to Build

Each tool is a **sub-workflow** triggered by the AI Agent via the Tools connector. The AI Agent calls a tool by name, passes input parameters, and receives a result it uses to continue the conversation.

| Sub-workflow name | Tool name in Agent | What it does |
|-------------------|--------------------|--------------|
| `Tool - Check Calendar Availability` | `check_calendar_availability` | Checks if AM or PM slot on a given date has any existing bookings |
| `Tool - Create Calendar Event` | `create_calendar_event` | Creates a Google Calendar event for the confirmed booking |
| `Tool - Write Booking to Sheets` | `write_booking_to_sheets` | Upserts Customers sheet + appends Bookings sheet |
| `Tool - Get Customer Bookings` | `get_customer_bookings` | Returns existing booking records for the customer |

Build order: 3.1 → 3.2 → 3.3 → 3.4. Test each before moving to the next.

---

## Step 3.1 — `Tool - Check Calendar Availability`

### Sub-workflow nodes

**Node 1 — Execute Sub-Workflow Trigger**
- Input fields to define:

| Field | Type | Description |
|-------|------|-------------|
| `date` | String | Requested date in YYYY-MM-DD format |
| `window` | String | `AM` or `PM` |

**Node 2 — Set Window Times (Code node — JavaScript)**

Converts AM/PM to actual time ranges for the calendar query. Includes a null guard for n8n's schema probe call (which sends null values before the real call):

```javascript
const date = $input.first().json.date;
const windowRaw = $input.first().json.window;

// Null guard — n8n sends a schema probe call with null inputs before the real call
if (!date || !windowRaw) {
  return [{ json: { available: false, reason: 'probe' } }];
}

const window = windowRaw.toUpperCase();

const windowTimes = {
  AM: { start: '09:00', end: '13:00' },
  PM: { start: '14:00', end: '18:00' },
};

if (!windowTimes[window]) {
  throw new Error(`Invalid window: ${window}. Must be AM or PM.`);
}

// Also enforce minimum 2-day notice
const requestedDate = new Date(date);
const today = new Date();
today.setHours(0, 0, 0, 0);
const diffDays = Math.floor((requestedDate - today) / (1000 * 60 * 60 * 24));

if (diffDays < 2) {
  return [{
    json: {
      available: false,
      reason: 'insufficient_notice',
      message: `Bookings require at least 2 days notice. The earliest available date is ${new Date(today.getTime() + 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]}.`
    }
  }];
}

const timeMin = `${date}T${windowTimes[window].start}:00+08:00`;
const timeMax = `${date}T${windowTimes[window].end}:00+08:00`;

return [{
  json: {
    date,
    window,
    timeMin,
    timeMax,
  }
}];
```

**Node 3 — IF: Insufficient Notice?**
- Condition: `{{$json.reason}}` equals `insufficient_notice`
- TRUE → go to Node 4 (return unavailable)
- FALSE → go to Node 5 (check calendar)

**Node 4 — Return Unavailable (Code node — JavaScript)**

> Must be a Code node — Set nodes don't always return output the tool runner recognises.

```javascript
return [{
  json: {
    available: false,
    reason: 'insufficient_notice',
    message: $input.first().json.message,
  }
}];
```

**Node 5 — Google Calendar: Get Events**
- Credential: `HeyAircon Calendar`
- Operation: `Get Many`
- Calendar: `HeyAircon Bookings` (select from dropdown or enter Calendar ID)
- **After** (Time Min): `{{$json.timeMin}}`
- **Before** (Time Max): `{{$json.timeMax}}`
- Turn on **Always Output Data** (under Options) — required so the node outputs something even when no events exist

**Node 6 — IF: Events Found?**
- Condition: `{{$json.id}}` **exists**
- TRUE → Node 7a (return conflict)
- FALSE → Node 7b (return available)

> This IF node is needed because "Always Output Data" outputs one item with empty fields when no events exist. Check for the `id` field — real events always have one.

**Node 7a — Return Conflict (Code node — JavaScript)**

```javascript
const inputData = $('Set Window Times').first().json;

return [{
  json: {
    available: false,
    date: inputData.date,
    window: inputData.window,
    reason: 'conflict',
    message: `The ${inputData.window} slot on ${inputData.date} is already booked. Please choose a different date or time window.`
  }
}];
```

**Node 7b — Return Available (Code node — JavaScript)**

```javascript
const inputData = $('Set Window Times').first().json;

return [{
  json: {
    available: true,
    date: inputData.date,
    window: inputData.window,
    reason: null,
    message: `The ${inputData.window} slot on ${inputData.date} is available.`
  }
}];
```

### Tool registration on AI Agent

In `WA Inbound Handler` → AI Agent node → **Tools** connector → add **Call n8n Workflow Tool**:
- Workflow: `Tool - Check Calendar Availability`
- Tool name: `check_calendar_availability`
- Description: `Checks if the AM (9am-1pm) or PM (1pm-6pm) slot on a given date is available. Input: date (YYYY-MM-DD), window (AM or PM). Returns available true/false and a message.`
- Input Schema: `date` (String), `window` (String)
- Workflow inputs — set each value using $fromAI():

| Field | Value expression |
|-------|-----------------|
| `date` | `{{ $fromAI('date', 'Requested booking date in YYYY-MM-DD format') }}` |
| `window` | `{{ $fromAI('window', 'Time window: AM or PM') }}` |

---

## Step 3.2 — `Tool - Create Calendar Event`

### Sub-workflow nodes

**Node 1 — Execute Sub-Workflow Trigger**

| Field | Type | Description |
|-------|------|-------------|
| `date` | String | YYYY-MM-DD |
| `window` | String | `AM` or `PM` |
| `customer_name` | String | Full name |
| `address` | String | Full address |
| `postal_code` | String | Postal code |
| `service_type` | String | e.g. Chemical Wash |
| `unit_count` | String | Number of aircon units |
| `phone_number` | String | Customer phone number |
| `aircon_brand` | String | Optional |

**Node 2 — Build Event Details (Code node — JavaScript)**

```javascript
const input = $input.first().json;

// Null guard — n8n sends a schema probe call with all-null inputs before the real call
if (!input.date || !input.window) {
  return [{ json: { probe: true } }];
}

const windowTimes = {
  AM: { start: '09:00:00', end: '13:00:00', label: '9am-1pm' },
  PM: { start: '14:00:00', end: '18:00:00', label: '2pm-6pm' },
};

const w = windowTimes[input.window.toUpperCase()];

const title = `[HeyAircon] ${input.service_type} — ${input.customer_name}`;
const description = [
  `Service: ${input.service_type}`,
  `Units: ${input.unit_count}`,
  input.aircon_brand ? `Brand: ${input.aircon_brand}` : null,
  `Address: ${input.address}, Singapore ${input.postal_code}`,
  `Phone: ${input.phone_number}`,
].filter(Boolean).join('\n');

return [{
  json: {
    ...input,
    title,
    description,
    startDateTime: `${input.date}T${w.start}+08:00`,
    endDateTime: `${input.date}T${w.end}+08:00`,
    windowLabel: w.label,
  }
}];
```

**Node 2b — IF: Real Call? (IF node)**
- Condition: `{{$json.date}}` **exists**
- TRUE → Node 3 (Google Calendar Create Event)
- FALSE → Node 4 (Return Result) — probe call bypasses calendar creation

**Node 3 — Google Calendar: Create Event**
- Credential: `HeyAircon Calendar`
- Operation: `Create`
- Calendar: `HeyAircon Bookings`
- **Summary** (Title): `{{$json.title}}`
- **Start**: `{{$json.startDateTime}}`
- **End**: `{{$json.endDateTime}}`
- **Description**: `{{$json.description}}`
- Options → **Location:** `{{$json.address}}, Singapore {{$json.postal_code}}`

**Node 4 — Return Result (Code node — JavaScript)**

Both the TRUE branch (after Google Calendar) and the FALSE branch (probe call) connect here.

```javascript
const buildDetails = $('Build Event Details').first().json;

// Probe call — return a safe stub so the tool runner doesn't error
if (buildDetails.probe) {
  return [{ json: { success: false, calendar_event_id: null } }];
}

const event = $input.first().json;

return [{
  json: {
    success: true,
    calendar_event_id: event.id,
    date: buildDetails.date,
    window: buildDetails.window,
    window_label: buildDetails.windowLabel,
    customer_name: buildDetails.customer_name,
    service_type: buildDetails.service_type,
    address: buildDetails.address,
    postal_code: buildDetails.postal_code,
    unit_count: buildDetails.unit_count,
    aircon_brand: buildDetails.aircon_brand || null,
    phone_number: buildDetails.phone_number,
  }
}];
```

### Tool registration on AI Agent

Add **Call n8n Workflow Tool**:
- **Name:** `create_calendar_event`
- **Description:** `Creates a confirmed booking on the HeyAircon Google Calendar. Only call after check_calendar_availability confirms the slot is available AND the customer has explicitly confirmed all details. Input: date, window, customer_name, address, postal_code, service_type, unit_count, phone_number. aircon_brand is optional.`
- **Workflow:** select `Tool - Create Calendar Event`
- **Input Schema:** all fields from the trigger node above
- Workflow inputs — set each value using $fromAI():

| Field | Value expression |
|-------|-----------------|
| `date` | `{{ $fromAI('date', 'Booking date in YYYY-MM-DD format') }}` |
| `window` | `{{ $fromAI('window', 'Time window: AM or PM') }}` |
| `customer_name` | `{{ $fromAI('customer_name', 'Full name of the customer') }}` |
| `address` | `{{ $fromAI('address', 'Full street address') }}` |
| `postal_code` | `{{ $fromAI('postal_code', 'Singapore postal code') }}` |
| `service_type` | `{{ $fromAI('service_type', 'Type of aircon service e.g. Chemical Wash') }}` |
| `unit_count` | `{{ $fromAI('unit_count', 'Number of aircon units') }}` |
| `phone_number` | `{{ $fromAI('phone_number', 'Customer WhatsApp phone number') }}` |
| `aircon_brand` | `{{ $fromAI('aircon_brand', 'Brand of aircon units, optional') }}` |

---

## Step 3.3 — `Tool - Write Booking to Sheets`

### Sub-workflow nodes

**Node 1 — Execute Sub-Workflow Trigger**

| Field | Type | Description |
|-------|------|-------------|
| `calendar_event_id` | String | From create_calendar_event output |
| `date` | String | YYYY-MM-DD |
| `window` | String | AM or PM |
| `customer_name` | String | |
| `address` | String | |
| `postal_code` | String | |
| `service_type` | String | |
| `unit_count` | String | |
| `phone_number` | String | |
| `aircon_brand` | String | Optional |

**Node 2 — Generate Booking ID (Code node — JavaScript)**

```javascript
const input = $input.first().json;
const date = input.date.replace(/-/g, '');
const random = Math.floor(1000 + Math.random() * 9000);
const bookingId = `HA-${date}-${random}`;

const now = new Date();
const sgt = new Date(now.getTime() + 8 * 60 * 60 * 1000);
const created_at = sgt.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, '') + ' SGT';

return [{
  json: {
    ...input,
    booking_id: bookingId,
    created_at,
  }
}];
```

**Node 3 — Google Sheets: Lookup Customer (Get Row(s))**
- Credential: `HeyAircon Sheets`
- Operation: `Get Row(s)`
- Sheet: `Customers`
- Filters → `phone_number` equals `{{$json.phone_number}}`

> No "Always Output Data" option available — the IF node below handles the empty case.

**Node 4 — IF: Customer Exists?**
- Condition: `{{$json.phone_number}}` **exists**
- TRUE → Node 5 (update customer)
- FALSE → Node 6 (create customer)

> When no row is found, n8n passes no items — `phone_number` won't exist, so the condition evaluates FALSE and goes to the create branch.

**Node 5 — Google Sheets: Update Customer Row**
- Operation: `Update`
- Sheet: `Customers`
- Column to Match On: `phone_number`
- Fields to update:

| Field | Value |
|-------|-------|
| `customer_name` | `{{$('Generate Booking ID').item.json.customer_name}}` |
| `address` | `{{$('Generate Booking ID').item.json.address}}` |
| `postal_code` | `{{$('Generate Booking ID').item.json.postal_code}}` |
| `last_seen` | `{{new Date(new Date().getTime() + 8*60*60*1000).toISOString().replace('T',' ').replace(/\.\d{3}Z$/,'') + ' SGT'}}` |
| `total_bookings` | `{{($json.total_bookings || 0) + 1}}` |

**Node 6 — Google Sheets: Append New Customer**
- Operation: `Append`
- Sheet: `Customers`
- Fields:

| Field | Value |
|-------|-------|
| `phone_number` | `{{$('Generate Booking ID').item.json.phone_number}}` |
| `customer_name` | `{{$('Generate Booking ID').item.json.customer_name}}` |
| `address` | `{{$('Generate Booking ID').item.json.address}}` |
| `postal_code` | `{{$('Generate Booking ID').item.json.postal_code}}` |
| `first_seen` | `{{new Date(new Date().getTime() + 8*60*60*1000).toISOString().replace('T',' ').replace(/\.\d{3}Z$/,'') + ' SGT'}}` |
| `last_seen` | `{{new Date(new Date().getTime() + 8*60*60*1000).toISOString().replace('T',' ').replace(/\.\d{3}Z$/,'') + ' SGT'}}` |
| `total_bookings` | `1` |

**Node 7 — Google Sheets: Append Booking**

Connect both Node 5 and Node 6 to this node.

- Operation: `Append`
- Sheet: `Bookings`
- Fields:

| Field | Value |
|-------|-------|
| `booking_id` | `{{$('Generate Booking ID').item.json.booking_id}}` |
| `created_at` | `{{$('Generate Booking ID').item.json.created_at}}` |
| `phone_number` | `{{$('Generate Booking ID').item.json.phone_number}}` |
| `service_type` | `{{$('Generate Booking ID').item.json.service_type}}` |
| `unit_count` | `{{$('Generate Booking ID').item.json.unit_count}}` |
| `aircon_brand` | `{{$('Generate Booking ID').item.json.aircon_brand \|\| ''}}` |
| `slot_date` | `{{$('Generate Booking ID').item.json.date}}` |
| `slot_window` | `{{$('Generate Booking ID').item.json.window}}` |
| `calendar_event_id` | `{{$('Generate Booking ID').item.json.calendar_event_id}}` |
| `booking_status` | `Confirmed` |

**Node 8 — Return Result (Code node — JavaScript)**

> Use a Code node, not a Set node — Set nodes don't always return output that the tool runner recognises.

```javascript
const bookingId = $('Generate Booking ID').first().json.booking_id;
return [{ json: { success: true, booking_id: bookingId } }];
```

### Tool registration on AI Agent

Add **Call n8n Workflow Tool**:
- **Name:** `write_booking_to_sheets`
- **Description:** `Writes the confirmed booking to the CRM. Call immediately after create_calendar_event succeeds. Pass all booking fields including the calendar_event_id returned by create_calendar_event.`
- **Workflow:** select `Tool - Write Booking to Sheets`
- **Input Schema:** all fields from the trigger node above
- Workflow inputs — set each value using $fromAI():

| Field | Value expression |
|-------|-----------------|
| `calendar_event_id` | `{{ $fromAI('calendar_event_id', 'Google Calendar event ID from create_calendar_event') }}` |
| `date` | `{{ $fromAI('date', 'Booking date in YYYY-MM-DD format') }}` |
| `window` | `{{ $fromAI('window', 'Time window: AM or PM') }}` |
| `customer_name` | `{{ $fromAI('customer_name', 'Full name of the customer') }}` |
| `address` | `{{ $fromAI('address', 'Full street address') }}` |
| `postal_code` | `{{ $fromAI('postal_code', 'Singapore postal code') }}` |
| `service_type` | `{{ $fromAI('service_type', 'Type of aircon service') }}` |
| `unit_count` | `{{ $fromAI('unit_count', 'Number of aircon units') }}` |
| `phone_number` | `{{ $fromAI('phone_number', 'Customer WhatsApp phone number') }}` |
| `aircon_brand` | `{{ $fromAI('aircon_brand', 'Brand of aircon units, optional') }}` |

---

## Step 3.4 — `Tool - Get Customer Bookings`

### Sub-workflow nodes

**Node 1 — Execute Sub-Workflow Trigger**

| Field | Type | Description |
|-------|------|-------------|
| `phone_number` | String | Customer phone number |

**Node 2 — Google Sheets: Get Bookings**
- Credential: `HeyAircon Sheets`
- Operation: `Get Row(s)`
- Sheet: `Bookings`
- Filters → `phone_number` equals `{{$json.phone_number}}`

> No "Always Output Data" option available — the IF node below handles the empty case.

**Node 3 — IF: Bookings Found?**
- Condition: `{{$json.booking_id}}` **exists**
- TRUE → Node 4 (Format Results)
- FALSE → Node 5 (Return Not Found)

> When no rows are found, n8n passes no items so `booking_id` won't exist → evaluates FALSE.

**Node 4 — Format Results (Code node — JavaScript)**

```javascript
const items = $input.all();

const bookings = items.map(item => ({
  booking_id: item.json.booking_id,
  service_type: item.json.service_type,
  slot_date: item.json.slot_date,
  slot_window: item.json.slot_window,
  booking_status: item.json.booking_status,
}));

return [{
  json: {
    found: true,
    count: bookings.length,
    bookings,
    message: `Found ${bookings.length} booking(s) for this customer.`
  }
}];
```

**Node 5 — Return Not Found (Code node — JavaScript)**

> Must be a Code node — Set nodes don't always return output the tool runner recognises.

```javascript
return [{ json: { found: false, message: 'No booking records found for this customer.' } }];
```

### Tool registration on AI Agent

Add **Call n8n Workflow Tool**:
- **Name:** `get_customer_bookings`
- **Description:** `Returns existing booking records for the customer by phone number. Call this when a customer asks about their bookings, upcoming appointments, or previous services.`
- **Workflow:** select `Tool - Get Customer Bookings`
- **Input Schema:** `phone_number` (string)
- Workflow inputs — set each value using $fromAI():

| Field | Value expression |
|-------|-----------------|
| `phone_number` | `{{ $fromAI('phone_number', 'Customer WhatsApp phone number') }}` |

---

## Step 4 — Booking Confirmation Message Template

> **Where to update this:** The confirmation message is sent by the AI Agent as part of its natural response — it is guided by the system prompt, not a fixed template node. To change the tone or content of the confirmation, update the `booking_policy` row in the Policies sheet with instruction on what the confirmation should include.

Add this to the `booking_policy` text in the Policies sheet (append to the existing text):

```
After successfully creating a booking (after write_booking_to_sheets completes), send the customer a confirmation message containing:
- A warm confirmation that the booking is confirmed
- The booking ID
- The service type
- The date and time window (e.g. 9am-1pm or 1pm-6pm)
- The address
- A note that the team will be in touch closer to the appointment
- The cancellation/rescheduling policy reminder (48 hours notice required)

Example format:
Your booking is confirmed! Here are your details:
Booking ID: HA-20260410-1234
Service: Chemical Wash
Date: 10 April 2026, AM slot (9am - 1pm)
Address: [address], Singapore [postal code]
Our team will be in touch closer to your appointment. If you need to reschedule or cancel, please let us know at least 48 hours in advance.
```

---

## Step 5 — Test the Full Booking Flow

Clear Postgres memory before testing:
```sql
DELETE FROM n8n_chat_histories WHERE session_id LIKE '6582829071%';
```

**Test A — Full successful booking**

Send messages in sequence (wait for each reply before sending next):

```bash
# Message 1
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"I want to book a chemical wash"},"type":"text","id":"d_test_001"}],"contacts":[{"profile":{"name":"Test Customer"}}]}}]}]}'
```

Expected: Agent asks for details one at a time (name, address, postal code, units, date, window)

```bash
# Message 2 — provide all details at once to speed up testing
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"My name is John Tan, address is 123 Orchard Road #04-01, postal code 238858, 2 units, I prefer 15 April AM slot"},"type":"text","id":"d_test_002"}],"contacts":[{"profile":{"name":"Test Customer"}}]}}]}]}'
```

Expected: Agent summarises details and asks for confirmation

```bash
# Message 3 — confirm
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"Yes confirmed"},"type":"text","id":"d_test_003"}],"contacts":[{"profile":{"name":"Test Customer"}}]}}]}]}'
```

Expected:
- `check_calendar_availability` tool called → available
- `create_calendar_event` tool called → event created in Google Calendar
- `write_booking_to_sheets` tool called → row in Bookings sheet, row in Customers sheet
- Agent sends confirmation message with booking ID

**Test B — Date within 2 days rejected**

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"6582829071","text":{"body":"I want to book a chemical wash for tomorrow"},"type":"text","id":"d_test_004"}],"contacts":[{"profile":{"name":"Test Customer"}}]}}]}]}'
```

Expected: Agent declines, states 2-day minimum notice, asks for alternative date.

---

## Acceptance Criteria

- [ ] Google Calendar `HeyAircon Bookings` created under `agent.heyaircon@gmail.com`
- [ ] Google Calendar credential added in n8n (`HeyAircon Calendar`)
- [ ] `Tool - Check Calendar Availability` sub-workflow built and published
- [ ] `Tool - Create Calendar Event` sub-workflow built and published
- [ ] `Tool - Write Booking to Sheets` sub-workflow built and published
- [ ] `Tool - Get Customer Bookings` sub-workflow built and published
- [ ] All 4 tools registered on the AI Agent node in `WA Inbound Handler`
- [ ] Confirmation message template added to Policies sheet `booking_policy`
- [ ] Test A passed — full booking flow end-to-end ✅
- [ ] Test B passed — date within 2 days rejected ✅
- [ ] Google Calendar event visible under `agent.heyaircon@gmail.com`
- [ ] Bookings sheet row created with correct data
- [ ] Customers sheet row created or updated

---

## Next: Component E
Once full booking flow is working, proceed to escalation tools.
See `04_component_e_setup.md` for escalation flow build.
