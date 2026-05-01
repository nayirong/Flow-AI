# Flow AI Client — Supabase Architecture

**Project:** `flow-ai-crm`
**Purpose:** CRM and agent context store for Flow AI's own WhatsApp agent (lead qualification)
**Phase:** 1

---

## Overview

Flow AI as a client uses the same multi-tenant engine as HeyAircon. The `flow-ai-crm` Supabase project is structurally identical to `hey-aircon-crm` with one difference: **no `bookings` table**. Flow AI's agent qualifies leads and escalates — it does not take bookings.

---

## Tables

### `customers`

Stores every contact that has messaged the Flow AI WhatsApp number. Functions as the lead CRM.

```sql
CREATE TABLE customers (
    id BIGSERIAL PRIMARY KEY,
    phone_number TEXT UNIQUE NOT NULL,
    customer_name TEXT,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    escalation_flag BOOLEAN DEFAULT FALSE,
    escalation_reason TEXT,
    escalation_notified BOOLEAN DEFAULT FALSE,

    -- Lead qualification fields (populated by agent during conversation)
    lead_industry TEXT,
    lead_whatsapp_volume TEXT,
    lead_pain_point TEXT,
    lead_team_size TEXT,
    lead_score INTEGER DEFAULT 0,
    lead_status TEXT DEFAULT 'new'
        CHECK (lead_status IN ('new', 'qualifying', 'qualified', 'escalated', 'nurture', 'disqualified'))
);

CREATE INDEX idx_customers_phone ON customers(phone_number);
CREATE INDEX idx_customers_lead_status ON customers(lead_status);
```

### `interactions_log`

Full conversation history. Required by context_builder for conversation history fetch.

```sql
CREATE TABLE interactions_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    phone_number TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    message_text TEXT,
    message_type TEXT DEFAULT 'text'
);

CREATE INDEX idx_interactions_phone ON interactions_log(phone_number);
CREATE INDEX idx_interactions_timestamp ON interactions_log(timestamp);
```

### `config`

Agent knowledge base — product capabilities, pricing, policies. Fetched by context_builder before every agent call.

```sql
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Seed rows (populate on provisioning):**

| key | value |
|-----|-------|
| `agent_name` | `Kai` |
| `business_name` | `Flow AI` |
| `business_description` | `AI agent platform for service SMEs in Southeast Asia. We automate WhatsApp customer conversations — FAQs, lead qualification, booking — so your team focuses on what needs judgment.` |
| `services` | `WhatsApp AI agent setup and management. Lead qualification. Appointment booking automation. CRM integration. Human escalation flows.` |
| `operating_hours` | `Our agent is available 24/7. The founder is typically available Mon–Fri 9am–6pm SGT.` |
| `website` | `https://flowai.com` |
| `calendly_link` | `[INSERT FOUNDER CALENDLY LINK]` |

### `policies`

Escalation rules, routing thresholds, and agent behavioural constraints.

```sql
CREATE TABLE policies (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Seed rows:**

| key | value |
|-----|-------|
| `escalation_triggers` | `Frustrated customer; requests live demo now; asks technical integration question not in knowledge base; asks to speak to a human` |
| `lead_escalation_score_threshold` | `5` |
| `nurture_message` | `Thanks for reaching out! We'll follow up with some resources about how Flow AI works for businesses like yours. In the meantime, feel free to ask me anything.` |
| `holding_message` | `I've flagged your details to our founder. You'll hear from him directly within a few hours.` |

### `escalation_tracking`

Mirrors the HeyAircon schema exactly. Required by `reset_handler.py`.

```sql
CREATE TABLE escalation_tracking (
    id BIGSERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    escalation_reason TEXT,
    alert_msg_id TEXT,
    escalated_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT
);

CREATE INDEX idx_escalation_phone ON escalation_tracking(phone_number);
CREATE INDEX idx_escalation_alert_msg ON escalation_tracking(alert_msg_id);
CREATE INDEX idx_escalation_resolved ON escalation_tracking(resolved_at);
```

---

## Shared Supabase — `clients` Table Row

Insert this row into the **shared Flow AI Supabase** `clients` table (not the `flow-ai-crm` project):

```sql
INSERT INTO clients (
    client_id,
    display_name,
    meta_phone_number_id,
    meta_verify_token,
    human_agent_number,
    google_calendar_id,
    timezone,
    is_active,
    sheets_sync_enabled,
    sheets_spreadsheet_id,
    sheets_service_account_creds
) VALUES (
    'flow-ai',
    'Flow AI',
    '[INSERT META PHONE NUMBER ID]',
    '[INSERT VERIFY TOKEN — random string]',
    '[INSERT FOUNDER WHATSAPP NUMBER IN E.164 FORMAT]',
    NULL,                   -- no calendar in Phase 1
    'Asia/Singapore',
    TRUE,
    FALSE,                  -- no Sheets sync for internal client
    NULL,
    NULL
);
```

---

## Railway Project — `flow-ai-agent`

**Branch:** `release` (same as HeyAircon)
**Start command:** `uvicorn engine.main:app --host 0.0.0.0 --port $PORT`
**Watch paths:** `engine/` (Railway Watch Paths — same as HeyAircon)

**Environment variables to add:**

| Variable | Value |
|----------|-------|
| `FLOW_AI_META_WHATSAPP_TOKEN` | From Meta Business Manager |
| `FLOW_AI_SUPABASE_URL` | `flow-ai-crm` project URL |
| `FLOW_AI_SUPABASE_SERVICE_KEY` | `flow-ai-crm` service role key |
| `FLOW_AI_ANTHROPIC_API_KEY` | Flow AI's own Anthropic account key |
| `FLOW_AI_OPENAI_API_KEY` | Flow AI's own OpenAI account key |

**Shared env vars (same across all Railway projects):**

| Variable | Value |
|----------|-------|
| `SHARED_SUPABASE_URL` | Shared Supabase project URL |
| `SHARED_SUPABASE_SERVICE_KEY` | Shared Supabase service role key |

---

## Webhook Registration

Once Railway project is deployed:

1. Copy the Railway public URL: `https://<flow-ai-agent>.railway.app`
2. In Meta Business Manager → WhatsApp → Configuration → Webhook:
   - URL: `https://<flow-ai-agent>.railway.app/webhook/whatsapp/flow-ai`
   - Verify token: value from `meta_verify_token` in `clients` table
3. Subscribe to: `messages`
4. Verify webhook passes (GET returns 200 with hub.challenge)

---

## Migration Order

1. Create `flow-ai-crm` Supabase project
2. Run SQL for all tables above (in order: `customers` → `interactions_log` → `config` → `policies` → `escalation_tracking`)
3. Seed `config` and `policies` tables with the rows above
4. Insert row into shared `clients` table
5. Create Railway project `flow-ai-agent`, add all env vars, deploy
6. Register Meta webhook
7. Send test message → verify end-to-end
