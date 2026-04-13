# Architecture Reference — HeyAircon Agent
## Living Document | Flow AI

**Last Updated:** 6 April 2026
**Purpose:** Single source of truth for the current system architecture, infrastructure state, known behaviours, and critical decisions made during build. Update this document whenever a decision is made or a behaviour is discovered.

---

## 1. Infrastructure Overview

### Railway Project
| Service | Status | URL / Notes |
|---------|--------|-------------|
| `n8n` (primary) | ✅ Running | `https://primary-production-c09dd.up.railway.app` — UI, webhook receiver, workflow manager |
| `n8n-worker` | ✅ Running | No public URL — executes workflow jobs async in background |
| `Postgres` | ✅ Running | Shared DB for n8n execution data + Postgres Chat Memory (future) |

### How Railway services relate
```
Internet
    ↓
n8n (primary)     ← receives webhook, returns 200 OK immediately
    ↓ queues job
n8n-worker        ← picks up job, executes all workflow nodes
    ↓ reads/writes
Postgres          ← stores execution history, credentials, chat memory
```

> **Critical:** Workflow execution happens in the **worker**, not the primary. Always check the **Executions tab** in n8n UI to see completed runs — not the live canvas.

---

## 2. Environment Variables

### Set on BOTH n8n and n8n-worker services in Railway

> ⚠️ Variables must be on both services. Worker executes nodes but inherits nothing from primary automatically unless explicitly set.

| Variable | Current Value | Notes |
|----------|--------------|-------|
| `N8N_ENCRYPTION_KEY` | *(set in Railway — do not expose)* | Must be identical on both services. Set once, never change. |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | `false` | Required to allow `$env` in workflow expressions. Without this, all `$env` references fail with "access to env vars denied". |
| `HUMAN_AGENT_WHATSAPP_NUMBER` | *(Flow AI number — placeholder)* | WhatsApp number that receives escalation notifications. Update to HeyAircon number before go-live. |
| `DEV_WHATSAPP_NUMBER` | *(Flow AI number)* | Used during dev/testing phase. |
| `MIN_BOOKING_NOTICE_DAYS` | `2` | Minimum days ahead a booking can be made. Configurable. |
| `BOOKING_WINDOW_AM_START` | `09:00` | AM slot start (24hr) |
| `BOOKING_WINDOW_AM_END` | `13:00` | AM slot end (24hr) |
| `BOOKING_WINDOW_PM_START` | `14:00` | PM slot start (24hr) |
| `BOOKING_WINDOW_PM_END` | `18:00` | PM slot end (24hr) |
| `BUSINESS_HOURS_START` | `09:00` | ⚠️ Placeholder — pending client confirmation |
| `BUSINESS_HOURS_END` | `18:00` | ⚠️ Placeholder — pending client confirmation |
| `BUSINESS_DAYS` | `MON,TUE,WED,THU,FRI,SAT` | ⚠️ Placeholder — pending client confirmation |
| `OPERATE_ON_PUBLIC_HOLIDAYS` | `false` | Default closed on public holidays |
| `META_PHONE_NUMBER_ID` | *(pending Meta dev account setup)* | From Meta Developer Portal → WhatsApp → API Setup |
| `META_WHATSAPP_TOKEN` | *(pending Meta dev account setup)* | Temporary token (24hr expiry). Replace with permanent System User token before go-live. |
| `META_VERIFY_TOKEN` | `heyaircon_webhook_2026` | Used for Meta webhook GET verification handshake |

---

## 3. WhatsApp Channel

### Approach: Meta WhatsApp Cloud API (direct, no BSP)
No 360dialog or other BSP. Direct connection to Meta's Graph API.

| Item | Value |
|------|-------|
| API Base URL | `https://graph.facebook.com/v19.0` |
| Send message endpoint | `POST /{{META_PHONE_NUMBER_ID}}/messages` |
| Auth header | `Authorization: Bearer {{META_WHATSAPP_TOKEN}}` |
| Inbound webhook URL | `https://primary-production-c09dd.up.railway.app/webhook/whatsapp-inbound` |
| Webhook verify token | `heyaircon_webhook_2026` |

### Dev vs Production
| Phase | Number | Token type |
|-------|--------|-----------|
| Dev/Testing | Meta free test number | Temporary (24hr expiry) |
| UAT | Meta free test number or Flow AI number | Temporary |
| Production | HeyAircon business number | Permanent System User token |

### Token rotation (dev)
The temporary dev token expires every 24 hours. To refresh:
1. Go to [developers.facebook.com](https://developers.facebook.com) → Your App → WhatsApp → API Setup
2. Copy new temporary access token
3. Update `META_WHATSAPP_TOKEN` in Railway (both n8n and n8n-worker)
4. Services restart automatically

---

## 4. n8n Webhook Behaviour — Critical Discoveries

> These were discovered during build and must be known by anyone working on this system.

### 4.1 POST body is wrapped under `$json.body`
When n8n's Webhook node receives a POST request, it wraps the entire request into a structured object. The POST body is accessible at `$json.body`, not at `$json` directly.

```javascript
// n8n webhook output structure:
{
  headers: { ... },
  params: { ... },
  query: { ... },
  body: { /* YOUR POST BODY IS HERE */ },
  webhookUrl: "...",
  executionMode: "production"
}

// Therefore, Meta's payload fields are accessed as:
$json.body.entry[0].changes[0].value.messages[0].from  // ✅ correct
$json.entry[0].changes[0].value.messages[0].from       // ❌ wrong
```

### 4.2 Meta sends two types of webhook events
Not all Meta webhook POSTs are inbound messages. Status updates (delivery receipts, read receipts) also fire the webhook with a different payload shape.

```javascript
// Inbound message payload has:
$json.body.entry[0].changes[0].value.messages  // array exists

// Status update payload has:
$json.body.entry[0].changes[0].value.statuses  // array exists, no messages
```

The `Has Message?` guard IF node handles this by checking:
- Value: `{{$json.body.entry[0].changes[0].value.messages[0].from}}`
- Operation: `is not empty`

### 4.3 `$env` is blocked in sub-workflows
n8n sub-workflows (triggered via Execute Sub-Workflow node) cannot access `$env` variables. The `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` setting enables `$env` in **parent** workflows only.

**Pattern used throughout this project:**
- Parent workflow reads `$env` values
- Parent passes them as explicit fields to sub-workflows
- Sub-workflow uses `$json.field_name` to access them

```javascript
// In parent workflow (WA Inbound Handler) — works:
{{$env.META_PHONE_NUMBER_ID}}  // ✅

// In sub-workflow (WA Send Message) — fails:
{{$env.META_PHONE_NUMBER_ID}}  // ❌ access denied

// Solution: parent passes it as field, sub-workflow reads:
{{$json.phone_number_id}}      // ✅
```

### 4.4 Google Sheets Get Rows returns no output when no row found
When a Sheets lookup finds no matching row, n8n stops execution (no items to pass forward) unless **Always Output Data** is enabled.

**Fix applied:** On all `Get Rows` Sheets nodes → Options → **Always Output Data = ON**

This outputs `{}` when no row is found, allowing downstream nodes to continue and handle the empty case.

### 4.5 Meta GET webhook verification
When you configure a webhook in Meta Developer Portal, Meta sends a **GET** request (not POST) to verify the URL. This requires a separate Webhook trigger node:

```
[Webhook GET — path: whatsapp-inbound]
    → [Respond to Webhook]
         Respond With: Text
         Body: {{$json.query["hub.challenge"]}}
         Code: 200
         Header: Content-Type = text/plain

[Webhook POST — path: whatsapp-inbound]
    → [Has Message? guard]
    → ... rest of inbound flow
```

Two separate Webhook nodes on the same path but different HTTP methods. n8n routes correctly by method.

---

## 5. Supabase (CRM)

### Project
- **Supabase project:** `heyaircon` (Flow AI account)
- **Credential in n8n:** `Supabase HeyAircon` (Postgres)
- **Client access:** Supabase Studio — read + edit on `config` and `policies` tables; read-only on others

### Tables
| Table | Purpose | Key behaviour |
|-------|---------|--------------|
| `bookings` | One row per booking | Booking records only — no escalation state |
| `interactions_log` | Append-only message log | Every inbound + outbound message logged |
| `customers` | One row per customer | `escalation_flag` column gates agent responses; `phone_number` is unique key |
| `config` | Key-value business config | Fetched at runtime and injected into agent system message |
| `policies` | Policy text by name | Fetched at runtime and injected into agent system message |

> **Context engineering pattern:** Business data (services, pricing, policies) lives in `config` and `policies` tables — not hardcoded in the system prompt. The `Build Context` Code node assembles them into `system_message` before the AI Agent node runs. Client can update content in Supabase Studio without touching n8n.

### Key queries used in workflows

**Layer 1 gate — read escalation flag (`WA Inbound Handler`):**
```sql
SELECT escalation_flag, escalation_reason FROM customers WHERE phone_number = '{{phone_number}}' LIMIT 1
```

**Fetch config (`WA Inbound Handler`):**
```sql
SELECT key, value FROM config ORDER BY sort_order
```

**Fetch policies (`WA Inbound Handler`):**
```sql
SELECT policy_name, policy_text FROM policies ORDER BY sort_order
```

**Set escalation flag (`Tool - Escalate to Human`):**
```sql
UPDATE customers SET escalation_flag = TRUE, escalation_reason = '{{escalation_type}}' WHERE phone_number = '{{phone_number}}'
```

> Full Supabase table schemas (SQL CREATE TABLE statements) are in `mvp_scope.md` → Supabase Table Schemas section.

---

## 6. n8n Workflows — Current State

### Published workflows
| Workflow | Status | Purpose |
|----------|--------|---------|
| `WA Inbound Handler` | ✅ Published | Main entry point — receives all inbound WhatsApp messages |
| `WA Send Message` | ✅ Published | Sub-workflow — sends outbound WhatsApp message via Meta API |
| `WA Log Interaction` | ✅ Published | Sub-workflow — appends message to Interactions Log sheet |

### `WA Inbound Handler` — Node map
```
[Webhook GET]  →  [Return Hub Challenge]   (Meta verification only)

[Webhook POST]
    ↓
[Has Message?]  →  FALSE: [NoOp - stop]   (status updates, delivery receipts)
    ↓ TRUE
[Extract Message Fields]                   (6 fields: phone_number, message_text, message_type, message_id, display_name, wa_id)
    ↓
[Read Escalation Flag]                     (Postgres SELECT from customers, Always Output Data = ON)
    ↓
[Is Escalated?]
    ↓ TRUE                    ↓ FALSE
[Log Inbound (Escalated)] [Log Inbound]    (WA Log Interaction sub-workflow)
[Send Holding Reply]            ↓
[Stop]                    [Fetch Config]   (Postgres SELECT from config)
                                ↓
                          [Fetch Policies] (Postgres SELECT from policies)
                                ↓
                          [Build Context]  (Code node: assembles system_message from Config + Policies)
                                ↓
                           [AI Agent]      (GPT-4o-mini, Postgres Chat Memory, system_message injected)
                                ↓
                        [Send Agent Reply] (WA Send Message sub-workflow)
                                ↓
                       [Log Outbound Reply](WA Log Interaction sub-workflow)
```

### `WA Send Message` — Node map
```
[Execute Sub-Workflow Trigger]
    input schema: to, message, phone_number_id, whatsapp_token
    ↓
[HTTP Request → graph.facebook.com]
    POST /{{phone_number_id}}/messages
    Authorization: Bearer {{whatsapp_token}}
    Body mode: Using Fields Below (JSON)
    Fields: messaging_product=whatsapp, recipient_type=individual,
            to={{$json.to}}, type=text, text.body={{$json.message}}
```

> **Why "Using Fields Below" not raw JSON:** Agent replies contain newlines and special characters from multi-line service descriptions. Raw JSON body breaks on these characters ("Bad control character" error). n8n's "Using Fields Below" mode handles escaping automatically.

### `WA Log Interaction` — Node map
```
[Execute Sub-Workflow Trigger]
    input schema: phone_number, direction, message_text, message_type
    ↓
[Google Sheets Append → Interactions Log]
    timestamp: new Date(new Date().getTime() + 8*60*60*1000).toISOString().replace('T',' ').replace(/\.\d{3}Z$/,'') + ' SGT'
```

---

## 7. Client Content Management

> The agent's knowledge — services, pricing, and policies — is managed entirely through Google Sheets. No n8n access is required. Changes take effect on the next customer message with no restart needed.

### How it works

At runtime, before the AI Agent runs, the flow:
1. Fetches all rows from the `Config` sheet (`Fetch Config` node)
2. Fetches all rows from the `Policies` sheet (`Fetch Policies` node)
3. Assembles a complete `system_message` string (`Build Context` Code node)
4. Injects it into the AI Agent via `{{$json.system_message}}`

### Config sheet — services and pricing

**Sheet name:** `Config` | **Columns:** `key` | `value`

**How the agent reads it:**
- Rows with `key` starting with `service_` → assembled into the SERVICES section
- Rows with `key` starting with `pricing_` → assembled into the PRICING section
- Special keys `appointment_window_am`, `appointment_window_pm`, `booking_lead_time_days` → APPOINTMENT WINDOWS section
- **Row order in the sheet controls the order the agent sees the content**

**To add a new service:**
1. Open `HeyAircon CRM` → `Config` sheet
2. Add a new row: `key` = `service_yourservicename`, `value` = full service description starting with the display name (e.g. `Jet Wash: High-pressure cleaning for condensers...`)
3. Add pricing rows below: `key` = `pricing_yourservicename_variant`, `value` = pricing text
4. No n8n changes needed — takes effect on next message

**To update existing pricing:**
1. Find the relevant `pricing_*` row in the Config sheet
2. Edit the `value` cell directly
3. Takes effect immediately on next message

**To remove a service:**
1. Delete the relevant `service_*` and `pricing_*` rows from the Config sheet
2. Takes effect immediately on next message

**Current Config keys:**

| key | purpose |
|-----|---------|
| `service_general_servicing` | General Servicing description |
| `service_chemical_wash` | Chemical Wash description |
| `service_chemical_overhaul` | Chemical Overhaul description |
| `service_gas_topup` | Gas Top Up description |
| `service_repair` | Aircon Repair description |
| `pricing_general_servicing_9_12k` | General Servicing pricing, 9-12k BTU |
| `pricing_general_servicing_18_24k` | General Servicing pricing, 18-24k BTU |
| `pricing_general_servicing_contract` | Annual contract pricing |
| `pricing_chemical_wash_9_12k` | Chemical Wash pricing, 9-12k BTU |
| `pricing_chemical_wash_18k` | Chemical Wash pricing, 18k BTU |
| `pricing_chemical_wash_24k` | Chemical Wash pricing, 24k BTU |
| `pricing_chemical_overhaul_9_12k` | Chemical Overhaul pricing, 9-12k BTU |
| `pricing_chemical_overhaul_18k` | Chemical Overhaul pricing, 18k BTU |
| `pricing_chemical_overhaul_24k` | Chemical Overhaul pricing, 24k BTU |
| `pricing_gas_topup` | Gas Top Up pricing |
| `pricing_condenser_servicing` | Condenser Servicing pricing |
| `pricing_repair` | Repair pricing note |
| `appointment_window_am` | AM slot display text |
| `appointment_window_pm` | PM slot display text |
| `booking_lead_time_days` | Minimum notice period in days |

---

### Policies sheet — booking, escalation, and other policies

**Sheet name:** `Policies` | **Columns:** `policy_name` | `policy_text`

**How the agent reads it:**
- All rows are read in sheet order and concatenated into a single POLICIES section
- `policy_name` is a label for the client's reference only — the agent does not see it
- `policy_text` is what the agent reads — write it as clear, complete prose
- **Row order in the sheet controls the order policies appear to the agent**

**To add a new policy:**
1. Open `HeyAircon CRM` → `Policies` sheet
2. Add a new row: `policy_name` = any label (e.g. `out_of_hours_policy`), `policy_text` = the full policy text
3. Takes effect immediately on next message

**To update a policy:**
1. Find the relevant row by `policy_name`
2. Edit the `policy_text` cell
3. Takes effect immediately

**Current policy rows:**

| policy_name | purpose |
|-------------|---------|
| `booking_policy` | Required booking fields and collection process |
| `escalation_policy` | When and how to escalate to a human |
| `rescheduling_policy` | Rescheduling rules and process |
| `cancellation_policy` | Cancellation rules and fees |

---

## 8. Key Design Decisions & Rationale

| Decision | Rationale | Date |
|----------|-----------|------|
| Meta Cloud API direct (no BSP) | Eliminates ~$10/month BSP fee; Meta API is free during dev with test number | Apr 2026 |
| n8n workers template on Railway | Splits webhook receipt (instant 200 OK) from execution (async worker) — required for WhatsApp which expects fast response | Apr 2026 |
| Supabase as CRM (migrated from Google Sheets) | Flow AI-owned data; Postgres scalability; foundation for SaaS dashboard; Supabase Studio gives client clean table view. Sheets archived as backup. | Apr 2026 |
| `$env` passed from parent to sub-workflow | n8n sub-workflows cannot access `$env` directly; passing via fields is the only reliable pattern | Apr 2026 |
| `Always Output Data` on Sheets lookup | Prevents execution stopping when no matching row found (new customer with no booking history) | Apr 2026 |
| Two separate Webhook nodes (GET + POST) | Avoids `Unused Respond to Webhook node` error; Meta verification requires GET, inbound messages use POST | Apr 2026 |
| Escalation flag on `customers` (not `bookings`, not memory) | Escalation is a customer state — silences the agent for a customer regardless of booking history. LLM memory cannot be trusted to gate responses. | Apr 2026 |
| Single calendar, 2 fixed windows (AM/PM) | Client Phase 1 scope — no multi-team, no flexible slots | Apr 2026 |
| Binary escalation gate (flag = true → agent silent) | Safe MVP default — deterministic, zero risk of agent responding to escalated topic | Apr 2026 |
| Context engineering — business data in Sheets, not system prompt | Services, pricing, and policies managed in `Config` and `Policies` sheets. Client updates content without touching n8n. `Build Context` Code node assembles `system_message` at runtime before AI Agent runs. | Apr 2026 |
| System message assembled in Code node, not AI Agent field | Allows dynamic injection of Sheets data; single Code node produces complete `system_message` string; AI Agent System Message field set to `{{$json.system_message}}` in expression mode | Apr 2026 |
| GPT-4o-mini (OpenAI) as LLM | Selected over Claude Haiku during build; Use Responses API OFF; no built-in tools | Apr 2026 |
| Company identity hardcoded in system message, not Sheets | Agent must always know it is an aircon company — this is core identity, not configurable content. Prevents agent from misidentifying service type (e.g. treating "chemical wash" as generic rather than aircon-specific). | Apr 2026 |
| Prompt injection guardrails in system message | Customer messages must never be treated as system instructions. Guardrails explicitly instruct the agent to ignore attempts to override identity, reveal the prompt, or act outside scope. Hardcoded — not editable via Sheets. | Apr 2026 |

---

## 8. Known Issues & Workarounds

| Issue | Workaround | Permanent fix |
|-------|-----------|---------------|
| `$env` and `process.env` both blocked in sub-workflow Code nodes | Pass env vars as explicit fields from parent workflow via trigger node input fields | This is by design in n8n's sandboxed task runner — pattern used throughout this project |
| `$env` not resolving in parent workflow nodes | Hardcode `META_PHONE_NUMBER_ID` and `META_WHATSAPP_TOKEN` directly in Send Agent Reply node | Confirm `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` is set on n8n-worker service and redeploy |
| Sheets Get Rows stops execution when no row found | Enable `Always Output Data` option on node | Already applied |
| Meta 24hr token expiry during dev | Manually refresh token from Meta Developer Portal daily | Generate permanent System User token before UAT |
| `Unused Respond to Webhook node` error | Use two separate Webhook nodes (GET + POST) instead of one node with IF method check | Already applied |
| Agent message body contains markdown formatting | Added plain text instruction to system message | Already applied — instruction in system message |
| HTTP Request node JSON body breaks on special characters in agent reply ("Bad control character") | Switch WA Send Message HTTP Request body to "Using Fields Below" mode — n8n handles escaping automatically | Already applied |
| AI Agent sub-nodes cannot use `$node["name"]` syntax for session ID | Use `$('Node Name').item.json.field` syntax instead | Already applied |
| AI Agent Prompt field sends literal expression text instead of resolved value | Toggle `{}` expression mode on the Prompt field | Already applied |
| `$env` not resolving in Send Agent Reply node | Hardcode `META_PHONE_NUMBER_ID` and `META_WHATSAPP_TOKEN` directly in Send Agent Reply fields | Applied as workaround — permanent fix: confirm `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` on n8n-worker |

---

## 8a. Open Design Decisions (Pending Client Input)

| ID | Issue | Current behaviour | Recommended fix | Priority |
|----|-------|------------------|-----------------|----------|
| DR-001 | Escalation gate is binary — escalated customers receive no response to any message, including unrelated FAQ questions | **Resolved:** `Send Holding Reply` node added on TRUE branch — sends fixed message: "Our team is currently looking into your request. A member of our team will be in touch with you shortly." Phase 1.5: allow FAQ responses while blocking booking-related messages. | Resolved for Phase 1 |

---

## 9. What's NOT Built Yet

| Component | Status | Notes |
|-----------|--------|-------|
| AI Agent node (LLM) | ✅ Built | GPT-4o-mini via OpenAI Chat Model sub-node |
| Postgres Chat Memory | ✅ Built | Keyed by phone number; window = 20 messages |
| Config + Policies sheets | ✅ Built | Context engineering — business data externally managed |
| Build Context Code node | ✅ Built | Assembles system_message at runtime from Sheets |
| Google Calendar integration | ⏳ Week 3 | Needs client Google account/service account |
| `write_booking_to_sheets` tool | ⏳ Week 3 | Upserts Customers + appends Bookings |
| `read_booking_from_sheets` tool | ⏳ Week 3 | Agent internal context only |
| `check_calendar_availability` tool | ⏳ Week 3 | Single calendar, AM/PM windows |
| `create_calendar_event` tool | ⏳ Week 3 | Add only, no update/delete |
| `escalate_to_human` tool | ⏳ Week 4 | Sets escalation_flag in Supabase, sends WhatsApp notification to human agent, applies Meta chat label via label API |
| Meta webhook verification (GET) | ⏳ Pending Meta dev account | Webhook node built; waiting for Meta credentials |
| Full round-trip test (real WhatsApp) | ⏳ Pending Meta dev account | curl test passes up to HTTP request |

---

## 10. Go-Live Checklist (Pre-Production)

> Do not go live until all items below are complete.

- [ ] Replace `META_WHATSAPP_TOKEN` with permanent System User token
- [ ] Complete Meta Business Verification
- [ ] Add HeyAircon's WhatsApp Business number to Meta App
- [ ] Update `META_PHONE_NUMBER_ID` to HeyAircon's number ID (remove hardcoded value from Send Agent Reply)
- [ ] Update `HUMAN_AGENT_WHATSAPP_NUMBER` to HeyAircon ops number
- [ ] Update Config sheet pricing — replace any remaining `$X` placeholders with confirmed prices
- [ ] Update Policies sheet — confirm rescheduling and cancellation policy wording with client
- [ ] Confirm `BUSINESS_HOURS_START/END`, `BUSINESS_DAYS` with client
- [ ] Confirm `MIN_BOOKING_NOTICE_DAYS` with client
- [ ] Fix `$env` resolution on n8n-worker (replace hardcoded token/phone ID with `$env` references)
- [ ] Share client's Google account with n8n for Calendar access
- [ ] Confirm `LABEL_ID_*` env vars are set to production label IDs (not dev placeholders) on both Railway services
- [ ] Full scripted E2E test with client as test customer
- [ ] Client sign-off on demo walkthrough
