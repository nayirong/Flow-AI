# Component A — Build Guide
## WhatsApp Channel & n8n Setup

**Goal:** Messages flowing in and out of WhatsApp before any agent logic.
**Acceptance:** Send "Hello" from your WhatsApp → n8n logs it → auto-reply received.

---

## Project URLs

| Service | URL |
|---------|-----|
| n8n UI | `https://primary-production-c09dd.up.railway.app` |
| Webhook base URL | `https://primary-production-c09dd.up.railway.app/webhook` |
| WhatsApp inbound webhook | `https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound` |

---

## WhatsApp Channel Approach

> **We are using Meta WhatsApp Cloud API directly — no BSP (no 360dialog).** This eliminates the monthly BSP fee. You only pay Meta's conversation fees when real customer conversations happen, which are free during development using the test number.

| Phase | Channel | Cost |
|-------|---------|------|
| Development | Meta test number (free, no verification needed) | Free |
| UAT / Production | Meta Cloud API with verified business number | Meta conversation fees only (~$0.01–0.06 per conversation depending on type) |

---

## Step 1 — Railway Setup

### 1.1 Confirm services are running
1. Open n8n at `https://primary-production-c09dd.up.railway.app` ✅
2. Open Railway → **n8n-worker** service → confirm **Active**
3. Open Railway → **Postgres** service → **Connect** tab → note credentials if needed

### 1.2 Verify or set required n8n variables
Check the **n8n service Variables** tab. Confirm `N8N_ENCRYPTION_KEY` is present and identical on both `n8n` and `n8n-worker` services.

> ⚠️ Set this once and never change it. If it changes after credentials are saved, all stored credentials become unreadable.

### 1.3 Set application environment variables
Add the following to the **n8n service Variables** tab in Railway:

| Variable | Value for now |
|----------|--------------|
| `HUMAN_AGENT_WHATSAPP_NUMBER` | Your Flow AI WhatsApp number (country code, no +, e.g. `6591234567`) |
| `DEV_WHATSAPP_NUMBER` | Same as above |
| `MIN_BOOKING_NOTICE_DAYS` | `2` |
| `BOOKING_WINDOW_AM_START` | `09:00` |
| `BOOKING_WINDOW_AM_END` | `13:00` |
| `BOOKING_WINDOW_PM_START` | `13:00` |
| `BOOKING_WINDOW_PM_END` | `18:00` |
| `BUSINESS_HOURS_START` | `09:00` *(placeholder)* |
| `BUSINESS_HOURS_END` | `18:00` *(placeholder)* |
| `BUSINESS_DAYS` | `MON,TUE,WED,THU,FRI,SAT` *(placeholder)* |
| `OPERATE_ON_PUBLIC_HOLIDAYS` | `false` |
| `META_PHONE_NUMBER_ID` | *(add after Step 2)* |
| `META_WHATSAPP_TOKEN` | *(add after Step 2)* |
| `META_VERIFY_TOKEN` | Any string you choose — used to verify webhook with Meta (e.g. `heyaircon_webhook_2026`) |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | Must be set to `false` to allow workflows to read env vars via `$env` expressions | `false` |

> If the worker has an isolated Variables tab, duplicate the above there too.

---

## Step 2 — Meta WhatsApp Cloud API Setup

### 2.1 Create Meta Developer App
1. Go to [developers.facebook.com](https://developers.facebook.com) → **My Apps** → **Create App**
2. Select **Business** as app type
3. Name it: `HeyAircon Agent` (or any name)
4. Once created: in the left sidebar → **Add Product** → find **WhatsApp** → click **Set Up**

### 2.2 Get your test credentials
1. In the WhatsApp product → **API Setup**
2. You will see:
   - **Phone number ID** → copy this → add to Railway as `META_PHONE_NUMBER_ID`
   - **Temporary access token** → copy this → add to Railway as `META_WHATSAPP_TOKEN`
   - **Test phone number** — Meta provides a free sandbox number for dev (e.g. `+1 555 XXX XXXX`)
3. Under **To** field → click **Add phone number** → add your personal WhatsApp number as a test recipient
   - Meta will send a verification code to your WhatsApp — enter it to confirm

> ⚠️ The temporary access token expires every 24 hours. It's fine for dev/testing. For production, you'll generate a **permanent System User token** via Meta Business Manager — we'll do that before go-live.

### 2.3 Configure webhook
1. In WhatsApp → **Configuration** → **Webhook** section → click **Edit**
2. Set:
   - **Callback URL:** `https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound`
   - **Verify token:** the value you set for `META_VERIFY_TOKEN` (e.g. `heyaircon_webhook_2026`)
3. Click **Verify and Save** — Meta will send a GET request to your webhook URL to verify it
   - ⚠️ Your n8n webhook workflow must be **active** before you do this (see Step 3 — build Workflow 1 first, then come back to verify)
4. After saving → under **Webhook Fields** → subscribe to **messages**

### 2.4 Test: send a message
1. In Meta API Setup → use the **Send a test message** panel → send "Hello" to your personal WhatsApp number
2. Confirm it arrives on your phone

---

## Step 3 — n8n Workflows

> **Workers behaviour:** Webhook node returns 200 OK immediately to Meta. Worker processes the rest async. Check **Executions** tab to see completed runs — not the live webhook view.

### Workflow 1 — `WA Inbound Handler` (main workflow)

**Trigger:** Webhook node
- Method: `POST`
- Path: `whatsapp-inbound`
- Authentication: None
- Response mode: `Respond Immediately` ← **critical; must be set**

> **Why GET + POST on same path:** Meta first sends a **GET** request to verify your webhook (Step 2.3). You need to handle this in n8n. Add a second trigger or use an IF node on HTTP method:

```
[Webhook - POST + GET]
    → [IF: HTTP method = GET]
         YES → [Respond to Webhook] 
               Return: $query.hub_challenge (Meta's verification handshake)
               Headers: verify META_VERIFY_TOKEN matches $query.hub_verify_token
         NO (POST) → continue inbound flow below
```

**For the GET verification response node:**
- Node type: `Respond to Webhook`
- Response code: `200`
- Response body: `{{$json.query["hub.challenge"]}}`
- Add IF check: `{{$json.query["hub.verify_token"]}}` equals `{{$env.META_VERIFY_TOKEN}}`

**POST inbound flow (after GET check passes):**

```
[Webhook - POST]
    → [Set: Extract fields]
    → [Google Sheets: Read escalation_flag]
    → [IF: escalation_flag = true]
         YES → [WA Log Interaction] → [Stop]
         NO  → [WA Send Message] (test reply for now)
```

**Set node — field extraction:**
Meta Cloud API webhook payload shape:

```javascript
// n8n Webhook node wraps the POST body under $json.body
// All paths must include .body. prefix:

phone_number = {{$json.body.entry[0].changes[0].value.messages[0].from}}
message_text = {{$json.body.entry[0].changes[0].value.messages[0].text?.body ?? ""}}
message_type = {{$json.body.entry[0].changes[0].value.messages[0].type}}
message_id   = {{$json.body.entry[0].changes[0].value.messages[0].id}}
display_name = {{$json.body.entry[0].changes[0].value.contacts[0]?.profile?.name ?? ""}}
```

> Guard condition for `Has Message?` IF node:
```javascript
// Use "exists" operation, not !== undefined
{{$json.body.entry[0].changes[0].value.messages}}
```

**Google Sheets node — Read escalation_flag:**
- Operation: `Lookup`
- Sheet: `Bookings`
- Lookup column: `phone_number`
- Lookup value: `{{$node["Set: Extract fields"].json.phone_number}}`
- Return fields: `escalation_flag`
- If no row found: treat as `false`

**IF node:**
- Condition: `{{$json.escalation_flag}}` equals `true`
- Yes → log + stop
- No → send test reply

---

### Workflow 2 — `WA Send Message` (reusable sub-workflow)

**Trigger:** Execute Sub-Workflow
- Input schema fields:
  - `to` — String
  - `message` — String
  - `phone_number_id` — String *(passed from parent, avoids env var access issue in sub-workflow)*
  - `whatsapp_token` — String *(passed from parent)*

**HTTP Request node config:**
- Method: `POST`
- URL: `https://graph.facebook.com/v19.0/{{$json.phone_number_id}}/messages`
- Authentication: `None`
- Headers → Add Header:
  - Name: `Authorization`
  - Value: `Bearer {{$json.whatsapp_token}}`
- Body (JSON):
```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "{{$json.to}}",
  "type": "text",
  "text": {
    "body": "{{$json.message}}"
  }
}
```

> ⚠️ **Why not use `$env` in sub-workflows:** n8n sub-workflows run in an isolated context and cannot access `$env` variables directly. Always read env vars in the parent workflow and pass them as explicit fields to any sub-workflow that needs them.

---

### Workflow 3 — `WA Log Interaction` (reusable sub-workflow)

> Appends every inbound and outbound message to the Interactions log sheet.

**Trigger:** Execute Workflow Trigger node
- Expected input fields: `phone_number`, `direction`, `message_text`, `message_type`

**Nodes:**

```
[Execute Workflow Trigger]
    → [Google Sheets: Append row to Interactions Log]
```

**Google Sheets node:**
- Operation: `Append`
- Sheet: `Interactions Log` (Sheet 2)
- Fields:
  - `timestamp`: `{{new Date(new Date().getTime() + 8*60*60*1000).toISOString().replace('T',' ').replace(/\.\d{3}Z$/,'') + ' SGT'}}`
  - `phone_number`: `{{$json.phone_number}}`
  - `direction`: `{{$json.direction}}`
  - `message_text`: `{{$json.message_text}}`
  - `message_type`: `{{$json.message_type}}`

---

## Step 4 — Google Sheets Setup

Create a Google Sheet named `HeyAircon CRM` with the following sheets:

### Sheet 1: `Bookings`
```
booking_id | created_at | phone_number | service_type | unit_count | aircon_brand | slot_date | slot_window | calendar_event_id | booking_status | escalation_flag | escalation_reason | notes
```

### Sheet 2: `Interactions Log`
```
timestamp | phone_number | direction | message_text | message_type
```

### Sheet 3: `Customers`
```
phone_number | customer_name | address | postal_code | first_seen | last_seen | total_bookings | notes
```

> `phone_number` is the primary key in the Customers sheet. One row per customer, never duplicated. The Bookings sheet references it as a foreign key.

### Sharing:
- Share the Google Sheet with the Google account / service account you'll connect to n8n
- In n8n: add Google Sheets credential (OAuth2 or Service Account) — name it `HeyAircon Sheets`

---

## Step 5 — Test Round-Trip

1. In Meta API Setup → send a test message to your personal WhatsApp number
2. Reply to it from your personal WhatsApp (this simulates a customer inbound message)
3. Confirm in n8n → **Executions** tab: execution completed
4. Confirm: fields extracted correctly
5. Confirm: Sheets lookup ran
6. Confirm: `WA Send Message` fired → you receive auto-reply on WhatsApp
7. Confirm: interaction logged in Sheet 2

**Test reply message:**
```
Hi! This is HeyAircon's automated assistant. We're currently setting things up. 
We'll be ready to help you soon! 🛠️
```

---

## Acceptance Criteria Checklist

- [x] ✅ n8n main + worker running on Railway
- [x] ✅ `N8N_ENCRYPTION_KEY` identical on both services
- [x] ✅ Google Sheets credential connected (`HeyAircon Sheets`)
- [x] ✅ Google Sheet `HeyAircon CRM` created with correct headers on all 3 sheets
- [x] ✅ `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` set on both Railway services
- [x] ✅ `WA Inbound Handler` workflow built and published
- [x] ✅ `WA Send Message` sub-workflow built and published
- [x] ✅ `WA Log Interaction` sub-workflow built and published
- [x] ✅ Webhook guard (Has Message?) working correctly
- [x] ✅ Field extraction working correctly
- [x] ✅ Escalation gate (Read Escalation Flag + Is Escalated?) working correctly
- [x] ✅ Interaction logging working correctly
- [ ] 🔴 Meta Developer Account — **BLOCKED: SMS OTP not received + rate limited**
  - Workaround: try authenticator app verification, different number, or wait 2+ hours
  - Build is NOT blocked — proceed to Component C while waiting
- [ ] ⏳ `META_PHONE_NUMBER_ID` and `META_WHATSAPP_TOKEN` env vars *(pending Meta account)*
- [ ] ⏳ Meta webhook verified *(pending Meta account)*
- [ ] ⏳ Full round-trip test via real WhatsApp *(pending Meta account)*
- [ ] ⏳ Escalation gate test with real WhatsApp reply *(pending Meta account)*

### Workflow 1 Build Progress
- [ ] Webhook node added (path: `whatsapp-inbound`, Respond Immediately)
- [ ] `Has Message?` guard IF node
- [ ] `GET or POST?` IF node for Meta verification handshake
- [ ] `Return Hub Challenge` Respond to Webhook node
- [ ] `Extract Message Fields` Set node (all 5 fields)
- [ ] `Read Escalation Flag` Google Sheets Get Rows node
- [ ] `Is Escalated?` IF node
- [ ] `Log Inbound (Escalated)` Execute Workflow node
- [ ] `Send Test Reply` Execute Sub-Workflow node
- [ ] Simulated payload test via curl/Postman passed

---

### Test 1 — Simulated inbound message (no Meta needed)

> ⚠️ **Important:** Do not wrap the payload in an extra `body` key. n8n's Webhook node already exposes the POST body at `$json` directly. The payload below matches exactly what Meta sends in production.

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "6582829071",
            "text": { "body": "Hello I want to book" },
            "type": "text",
            "id": "test_msg_001"
          }],
          "contacts": [{
            "profile": { "name": "Test Customer" }
          }]
        }
      }]
    }]
  }'
```

---

### Test 2 — Status update guard test

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "statuses": [{ "id": "msg_001", "status": "delivered" }]
        }
      }]
    }]
  }'
```

---

### Test 3 — Status update guard test

```bash
curl -X POST https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "statuses": [{ "id": "msg_001", "status": "delivered" }]
        }
      }]
    }]
  }'
```

---

## Production Go-Live Note (for later)

When switching from dev to production:
1. **Replace temporary token** with a permanent System User token from Meta Business Manager
2. **Complete Meta Business Verification** on your Meta Business Manager account
3. **Add HeyAircon's real WhatsApp number** to the Meta App and point `META_PHONE_NUMBER_ID` to it
4. No n8n workflow changes needed — only env var updates in Railway

---

## Next: Component B
See `02_component_b_c_setup.md` for next steps.
