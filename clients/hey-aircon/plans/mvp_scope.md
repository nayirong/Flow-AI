# MVP Scope & Build Plan — HeyAircon
## Phase 1 | Flow AI

**Client:** HeyAircon
**Phase:** 1 — WhatsApp Agent + Basic CRM
**Target Timeline:** Weeks 1–4
**Last Updated:** 7 April 2026
**Source:** Client scope discussion, 4 April 2026 (`04Apr_mvpscopediscussion.md`)

---

## Goal

Deploy a WhatsApp AI agent that can answer basic service inquiries and handle new booking requests end-to-end for straightforward cases (free slot), while escalating to a human agent for conflicts, changes, and out-of-scope queries. All booking and customer data is captured to Supabase Postgres — owned by Flow AI, accessible to the client via Supabase Studio.

---

## ⚡ Stack Migration — Google Sheets → Supabase

**Decision date:** April 2026
**Status:** To-do — migrate before building Component E

### Why

Google Sheets was chosen as a zero-friction interim CRM for Phase 1. Before go-live, we are migrating to Supabase (hosted Postgres) because:

- **Flow AI owns the data** — client data currently lives in a client-managed Google account. Supabase is a Flow AI-owned project. This is the foundation of the data moat.
- **Cross-client intelligence** — once all clients write to Flow AI-owned Supabase, we can aggregate patterns across verticals. This is impossible with per-client Sheets.
- **Scaling** — Google Sheets hits a 10M cell limit. Interactions Log alone exceeds this within months at moderate volume (DT-001). Postgres has no such ceiling.
- **Client access is better** — Supabase Studio gives clients a clean table view and editor. They log in once, see their own data. No sharing Google accounts or managing Sheet permissions.
- **Foundation for SaaS dashboard** — the client-facing dashboard (Phase 2) reads from Supabase. Building that on top of Google Sheets is not viable.

### What Changes

| Layer | Before | After |
|---|---|---|
| Bookings data | `Bookings` Google Sheet | `bookings` Supabase table |
| Customer data | `Customers` Google Sheet | `customers` Supabase table |
| Interaction log | `Interactions Log` Google Sheet | `interactions_log` Supabase table |
| Config (services/pricing) | `Config` Google Sheet | `config` Supabase table |
| Policies | `Policies` Google Sheet | `policies` Supabase table |
| Client data access | Edit Google Sheet directly | Supabase Studio (table editor) |
| n8n credential | Google Sheets OAuth2 | Supabase Postgres credential |
| Chat memory | Railway Postgres — unchanged | Railway Postgres — unchanged |

**n8n orchestration logic is unchanged.** Only the data read/write nodes are swapped. The `Build Context` code node requires minor updates to consume Postgres row output instead of Sheets row output (field names stay identical).

### Client Access Story

**Supabase is always the single source of truth.** Clients access their data in one of two ways depending on their comfort level — but the agent always reads and writes Supabase only. There is no dual-write.

#### Option A — Supabase Studio (default)

Clients log in to Supabase Studio directly. The table editor works like a spreadsheet — click a cell, type, press Enter.

| Data | Client Can... |
|---|---|
| Bookings | View all bookings, booking status, escalation flags |
| Customers | View customer profiles, booking counts, history |
| Interactions Log | View full conversation log per customer |
| Config | Edit directly — add/update/remove services and pricing. Changes take effect on next customer message. |
| Policies | Edit directly — update policy text. Changes take effect on next customer message. |

#### Option B — Read-Only Google Sheets Sync (fallback for Sheets-preferring clients)

If a client is uncomfortable with Supabase Studio and prefers to see their data in Google Sheets, a scheduled n8n sync workflow overwrites a linked Sheet every 15–30 minutes.

**How it works:**
```
Supabase (source of truth)
    ↓  [n8n sync workflow — runs every 15 min]
Google Sheet (read-only mirror — client views this)
```

**Rules:**
- The Sheet is **read-only by convention** — the client views it, never edits it
- The sync overwrites the entire sheet on each run — any manual edits are lost on the next cycle
- Config and policies are **not synced to Sheets** — clients who cannot edit Supabase Studio themselves request changes via WhatsApp/email, and Flow AI updates Supabase as part of the retainer service (a 2-minute task per change)
- The sync workflow is **built on request** — do not build it preemptively. Offer Supabase Studio first; build the sync only if the client explicitly asks for a Sheets view after seeing Studio

**Sync workflow design (when built):**
```
[Schedule Trigger — every 15 min]
    ↓
[Postgres SELECT * FROM bookings ORDER BY created_at DESC LIMIT 500]
    ↓
[Google Sheets — clear sheet + append all rows]  ← bookings tab

[Postgres SELECT * FROM customers]
    ↓
[Google Sheets — clear sheet + append all rows]  ← customers tab

[Postgres SELECT * FROM interactions_log ORDER BY timestamp DESC LIMIT 1000]
    ↓
[Google Sheets — clear sheet + append all rows]  ← interactions tab
```

Three Postgres reads, three Sheets overwrites. No bidirectional sync, no conflict resolution, nothing can diverge.

> **Why config and policies are excluded from sync:** The agent reads config and policies from Supabase at runtime. If the client edits a synced Sheet, the agent would never see the change — the Sheet is overwritten by the next sync anyway. Config and policies must always be edited in Supabase directly, either by the client or by Flow AI on their behalf.

### Migration To-Do List

> Component D is already built against Google Sheets. Complete the migration steps below before building Component E. Component E must be built directly against Supabase — do not build any part of it against Sheets.

#### Step 1 — Supabase Setup
- [ ] Create Supabase project: `heyaircon` (Flow AI account)
- [ ] Create `bookings` table — see schema below
- [ ] Create `customers` table — see schema below
- [ ] Create `interactions_log` table — see schema below
- [ ] Create `config` table — see schema below
- [ ] Create `policies` table — see schema below
- [ ] Seed `config` table with all service and pricing rows from current `Config` sheet
- [ ] Seed `policies` table with all policy rows from current `Policies` sheet
- [ ] Add Supabase Postgres credential in n8n (name: `Supabase HeyAircon`)
- [ ] Create client Supabase login — read + edit access to `config` and `policies` tables only for client self-management; read-only to others

#### Step 2 — Update n8n Workflows

**`WA Inbound Handler` — update 3 nodes:**
- [ ] `Read Escalation Flag`: replace Google Sheets Get Rows → Postgres node
  - Query: `SELECT escalation_flag, escalation_reason FROM bookings WHERE phone_number = '{{phone_number}}' ORDER BY created_at DESC LIMIT 1`
- [ ] `Fetch Config`: replace Google Sheets Get Rows → Postgres node
  - Query: `SELECT key, value FROM config ORDER BY sort_order`
- [ ] `Fetch Policies`: replace Google Sheets Get Rows → Postgres node
  - Query: `SELECT policy_name, policy_text FROM policies ORDER BY sort_order`
- [ ] `Build Context` Code node: update field access from Sheets row format to Postgres row format (field names are identical — only the n8n item wrapper differs)

**`WA Log Interaction` sub-workflow — update 1 node:**
- [ ] Replace Google Sheets Append → Postgres INSERT
  - `INSERT INTO interactions_log (timestamp, phone_number, direction, message_text, message_type) VALUES (...)`

**`Tool - Write Booking` sub-workflow — update 4 nodes (rename workflow to `Tool - Write Booking`):**
- [ ] `Lookup Customer`: replace Google Sheets Get Rows → Postgres SELECT
  - `SELECT * FROM customers WHERE phone_number = '{{phone_number}}' LIMIT 1`
- [ ] `Update Customer`: replace Google Sheets Update → Postgres UPDATE
  - `UPDATE customers SET customer_name=..., address=..., last_seen=..., total_bookings=total_bookings+1 WHERE phone_number=...`
- [ ] `Append New Customer`: replace Google Sheets Append → Postgres INSERT
  - `INSERT INTO customers (...) VALUES (...)`
- [ ] `Append Booking`: replace Google Sheets Append → Postgres INSERT
  - `INSERT INTO bookings (...) VALUES (...)`

**`Tool - Get Customer Bookings` sub-workflow — update 1 node:**
- [ ] Replace Google Sheets Get Rows → Postgres SELECT
  - `SELECT booking_id, service_type, slot_date, slot_window, booking_status FROM bookings WHERE phone_number = '{{phone_number}}' ORDER BY created_at DESC`

**`Tool - Escalate to Human` sub-workflow (Component E — build directly against Supabase):**
- [ ] Build escalation flag update as Postgres UPDATE from the start — do not build against Sheets
  - `UPDATE bookings SET escalation_flag=TRUE, escalation_reason=... WHERE phone_number=... AND booking_status != 'Cancelled' ORDER BY created_at DESC LIMIT 1`

#### Step 3 — Cleanup
- [ ] Verify all 5 workflow changes working end-to-end via curl tests
- [ ] Remove `HeyAircon Sheets` Google Sheets credential from n8n (after all nodes migrated)
- [ ] Archive Google Sheet `HeyAircon CRM` — do not delete (backup reference)
- [ ] Provision client Supabase login and walk client through Studio
- [ ] Update client onboarding doc with Supabase Studio access instructions

#### Step 4 — Optional: Google Sheets Sync Workflow (build only if client requests)

> Do not build this preemptively. Show the client Supabase Studio first. If they explicitly ask for a Sheets view after seeing Studio, build this.

- [ ] Create a new Google Sheet `HeyAircon CRM (View)` — three tabs: `Bookings`, `Customers`, `Interactions Log`
- [ ] Build n8n workflow `HeyAircon Sheets Sync`:
  - Schedule trigger: every 15 minutes
  - Three Postgres SELECT → Google Sheets clear + append blocks (bookings, customers, interactions_log)
  - No config or policies sync — those are Supabase-only
- [ ] Share Sheet with client as view-only
- [ ] Add note in Sheet header row: "This sheet is auto-refreshed every 15 minutes. Do not edit."
- [ ] Test: confirm Sheet reflects a new booking made via WhatsApp within 15 minutes

### Supabase Table Schemas

**`bookings`**
```sql
CREATE TABLE bookings (
  id              SERIAL PRIMARY KEY,
  booking_id      TEXT UNIQUE NOT NULL,          -- HA-YYYYMMDD-XXXX
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  phone_number    TEXT NOT NULL,
  service_type    TEXT,
  unit_count      TEXT,
  aircon_brand    TEXT,
  slot_date       DATE,
  slot_window     TEXT,                           -- AM or PM
  calendar_event_id TEXT,
  booking_status  TEXT DEFAULT 'Confirmed',
  escalation_flag BOOLEAN DEFAULT FALSE,
  escalation_reason TEXT,
  notes           TEXT
);
```

**`customers`**
```sql
CREATE TABLE customers (
  id              SERIAL PRIMARY KEY,
  phone_number    TEXT UNIQUE NOT NULL,           -- primary key / foreign key from bookings
  customer_name   TEXT,
  address         TEXT,
  postal_code     TEXT,
  first_seen      TIMESTAMPTZ DEFAULT NOW(),
  last_seen       TIMESTAMPTZ DEFAULT NOW(),
  total_bookings  INTEGER DEFAULT 0,
  notes           TEXT
);
```

**`interactions_log`**
```sql
CREATE TABLE interactions_log (
  id              SERIAL PRIMARY KEY,
  timestamp       TIMESTAMPTZ DEFAULT NOW(),
  phone_number    TEXT NOT NULL,
  direction       TEXT NOT NULL,                  -- inbound or outbound
  message_text    TEXT,
  message_type    TEXT DEFAULT 'text'
);
CREATE INDEX ON interactions_log (phone_number);  -- fast lookup per customer
```

**`config`**
```sql
CREATE TABLE config (
  id          SERIAL PRIMARY KEY,
  key         TEXT UNIQUE NOT NULL,
  value       TEXT NOT NULL,
  sort_order  INTEGER DEFAULT 0
);
```

> Seed with the same key/value rows currently in the Config Google Sheet. `sort_order` controls display order in agent context — matches the row order from Sheets.

**`policies`**
```sql
CREATE TABLE policies (
  id          SERIAL PRIMARY KEY,
  policy_name TEXT UNIQUE NOT NULL,
  policy_text TEXT NOT NULL,
  sort_order  INTEGER DEFAULT 0
);
```

> Seed with the same rows currently in the Policies Google Sheet.

### What This Resolves

- **DT-001** (Interactions Log Google Sheets ceiling) — resolved. `interactions_log` is a Postgres table with no row limit.
- **DT-002** (Policy text in spreadsheet cells) — resolved. Supabase Studio's table editor handles long prose cleanly. Google Docs migration no longer needed.
- **Dual-write risk** — eliminated by design. Supabase is the only write target. Google Sheets (if used at all) is a one-way sync mirror — it can never diverge from Supabase in a way that affects the agent.

---

---

## Phase 1 — In Scope

| # | Feature | Notes |
|---|---------|-------|
| 1 | WhatsApp AI agent — inquiry handling | Answers questions on services, pricing, and company info. English only. |
| 2 | WhatsApp AI agent — new booking flow | Collects date, preferred time window, address, service type. Checks single Google Calendar for conflicts. |
| 3 | Slot availability check (single calendar) | Two fixed daily windows: **9am–1pm** and **1pm–6pm**. If the requested slot has zero bookings → agent books directly. |
| 4 | Direct booking (free slot) | Agent creates Google Calendar event and sends booking confirmation to customer. Agent only **adds** events — never removes or updates. |
| 5 | Escalation — slot conflict | If requested slot already has ≥1 booking → agent informs customer and notifies human agent to reach out and arrange. |
| 6 | Escalation — reschedule / cancellation request | Agent shares rescheduling/cancellation policy and escalates to human for all changes. No automated changes to calendar or bookings. |
| 7 | Escalation — out-of-scope queries | Agent escalates when customer asks something outside the provided context (after good-faith attempt to answer). |
| 8 | Human agent notification | On any escalation: agent sends a WhatsApp notification to the human agent with customer details and reason. *(Exact notification method TBC — see open items.)* |
| 9 | Basic CRM data capture | All customer info and booking details written to Google Sheets. Phone number is the unique customer identifier. |

## Phase 1 — Out of Scope

> Items below were descoped from Phase 1 during client discussion on 4 April 2026. Targeted for Phase 2.

- Deposit and payment flow (payment instruction, screenshot receipt, admin CONFIRM command, payment deadline cron)
- Pre-appointment reminders (24h reminder workflow)
- Post-service feedback and Google review request
- Multi-team calendar management (round-robin, Teams config sheet)
- Admin keyword commands (CONFIRM, COMPLETE, RESOLVED)
- Calendar event removal or update by agent (human handles all changes)
- Past booking / upcoming booking lookup by customer
- Out-of-hours auto-reply *(not discussed — see open items)*
- Bookkeeping module
- CRM web interface
- Invoice generation
- Sales reporting dashboard
- Campaign / upsell automation
- Technician-facing views
- Multi-language support

---

## 🔁 Design Decisions to Revisit

> These are known gaps or oversimplifications in the current Phase 1 design that need client input and a build decision before UAT. They are not blockers for the current build week but must be resolved before go-live.

### DR-001 — Escalation gate is too blunt (binary silence vs. partial agent access)

**Current behaviour:**
When `escalation_flag = TRUE`, the agent is completely silenced. The customer receives zero response to any message until a human manually clears the flag in Sheets.

**Problem identified:**
A customer may be escalated for a specific reason (e.g. booking slot conflict) but later ask an unrelated question (e.g. "what's your price for chemical wash?"). Under the current design, the agent ignores this entirely — leaving the customer with no response and a poor experience.

**Proposed improved behaviour:**

| Customer message type | Current behaviour | Proposed behaviour |
|----------------------|-------------------|-------------------|
| Message related to escalated topic (e.g. "I want to change my booking") | ❌ Silent | Inform customer: "This has been escalated to our team. They will reach out shortly." |
| Message unrelated to escalation (e.g. "What is your price?") | ❌ Silent | ✅ Agent responds normally with FAQ answer |
| New booking request (different slot/date) | ❌ Silent | TBC — discuss with client |

**Design options:**

**Option A — Intent-based routing (LLM decides)**
- Remove the hard gate entirely
- Add `escalation_flag` and `escalation_reason` to the agent's context (via `read_booking_from_sheets` tool or injected into prompt)
- System prompt instructs agent:
  - If `escalation_flag = true` AND message is related to the escalated topic → respond with escalation holding message only
  - If `escalation_flag = true` AND message is unrelated → respond normally
- Pros: nuanced, good UX
- Cons: relies on LLM to correctly classify intent — not 100% reliable; could accidentally respond to an escalated topic

**Option B — Hard gate with fixed holding reply (current + improvement)**
- Keep the hard gate (agent blocked)
- Instead of silence, send a fixed holding message:
  `"Hi! Your request has been passed to our team and they'll be in touch shortly. For general inquiries about our services, feel free to reach out again once our team has followed up with you."`
- Pros: deterministic, zero risk of agent responding to escalated topic incorrectly
- Cons: poor UX for unrelated FAQ questions — customer still can't get a price quote while waiting

**Option C — Hybrid (recommended for Phase 1.5)**
- Keep hard gate for booking-related messages (conflict, reschedule, cancel)
- Allow agent to respond to pure FAQ messages (pricing, services, company info) even when escalated
- Implement via Layer 1: check `escalation_reason` — if reason is booking-related AND message contains booking intent keywords → block; otherwise → allow agent
- Pros: best UX balance; deterministic keyword check for blocking
- Cons: slightly more complex Layer 1 logic; keyword matching can miss edge cases

**Current Phase 1 decision:**
Keeping **Option B** (hard gate + fixed holding reply instead of silence) as the safe default for MVP. This is a one-line change from the current behaviour — replace "stop silently" with "send fixed holding message."

**Action required before UAT:**
- [ ] Confirm with client: should escalated customers receive a holding reply or true silence?
- [ ] Confirm with client: should escalated customers be able to ask unrelated FAQ questions?
- [ ] If yes to above: decide between Option A and Option C and schedule as Phase 1.5 build item

**Impact on current build:**
- **Immediate change (low effort):** Add a `Send Holding Reply` node on the TRUE branch of `Is Escalated?` instead of stopping silently
- **Future change (medium effort):** Implement Option C hybrid logic in Layer 1 pre-checks

---

## Open Items — Status Update (4 April 2026)

| # | Item | Status | Decision / Value |
|---|------|--------|-----------------|
| 1 | **Human agent notification method** | ⚠️ Pending confirmation | See recommendation below. Build as configurable variable: `HUMAN_AGENT_WHATSAPP_NUMBER`. Defaulting to WhatsApp message. |
| 2 | **Business operating hours** | ⚠️ Pending client input | Leaving open. Stored as configurable n8n env var: `BUSINESS_HOURS_START`, `BUSINESS_HOURS_END`. OOH handling deferred. |
| 3 | **Days of operation** | ⚠️ Pending client input | Leaving open. Stored as configurable n8n env var: `BUSINESS_DAYS` (e.g. `MON,TUE,WED,THU,FRI,SAT`). |
| 4 | **Public holiday operation** | ⚠️ Pending client input | Leaving open. Configurable flag: `OPERATE_ON_PUBLIC_HOLIDAYS = false` as safe default. |
| 5 | **Minimum notice period** | ✅ Set to 2 days | Configurable n8n env var: `MIN_BOOKING_NOTICE_DAYS = 2`. Agent will not accept bookings for dates fewer than 2 days from today. |
| 6 | **Out-of-hours handling** | ⚠️ Pending client input | Leaving open. Not blocking Phase 1 build — agent will not check OOH until this is resolved. |
| 7 | **Information required for booking** | ⚠️ Pending client input | Using default required fields for now: name, phone, address, postal code, service type, unit count, date, time window preference. Aircon brand marked optional. |
| 8 | **Rescheduling policy** | ⚠️ Placeholder in use | See placeholder doc below. Swap in real content before UAT. |
| 9 | **Cancellation policy** | ⚠️ Placeholder in use | See placeholder doc below. Swap in real content before UAT. |
| 10 | **Pricing doc** | ⚠️ Placeholder in use | See placeholder doc below. Swap in real content before UAT. |
| 11 | **Service catalogue** | ⚠️ Placeholder in use | See placeholder doc below. Swap in real content before UAT. |
| 12 | **Time windows** | ✅ Confirmed | **9am–1pm (AM slot)** and **1pm–6pm (PM slot)**. Hardcoded in booking logic. |

### Confirmed: Human Agent Notification Approach

Both actions fire on every escalation:

1. **WhatsApp message to `HUMAN_AGENT_WHATSAPP_NUMBER`** — structured message with customer name, phone, escalation reason, and requested slot (if applicable). Human can reply directly to the customer from the same app.
2. **Color-coded chat label via Meta Cloud API** — labels are created once manually in Meta Business Manager during client onboarding. At runtime, the `escalate_to_human` tool passes an `escalation_type` parameter; n8n maps it to the correct label ID and fires the label API call.

**Escalation type → label color mapping:**

| Escalation Type | Label Color | Rationale |
|----------------|------------|-----------|
| `out_of_scope` | 🔵 Blue | Informational gap, lower urgency |
| `conflict` | 🟠 Orange | Slot taken, attention needed |
| `change_request` | 🟡 Yellow | Reschedule/cancellation, pending human action |
| `customer_distress` | 🔴 Red | Anger or distress, immediate human response required |

> Green is reserved for resolved/completed states — do not use for escalation labels.

> **Config variable:** `HUMAN_AGENT_WHATSAPP_NUMBER` stored as n8n environment variable. Changeable without touching workflow logic.

---

## Configurable Variables (n8n Environment Variables)

> These are set in the Railway n8n environment and can be changed without modifying any workflow.

| Variable | Description | Phase 1 Default |
|----------|-------------|-----------------|
| `HUMAN_AGENT_WHATSAPP_NUMBER` | WhatsApp number to receive escalation notifications | TBC by client |
| `MIN_BOOKING_NOTICE_DAYS` | Minimum days ahead a booking can be made | `2` |
| `BUSINESS_HOURS_START` | Opening time (24hr, e.g. `09:00`) | TBC by client |
| `BUSINESS_HOURS_END` | Closing time (24hr, e.g. `18:00`) | TBC by client |
| `BUSINESS_DAYS` | Comma-separated days (e.g. `MON,TUE,WED,THU,FRI,SAT`) | TBC by client |
| `OPERATE_ON_PUBLIC_HOLIDAYS` | Whether bookings are accepted on public holidays | `false` |
| `BOOKING_WINDOW_AM_START` | AM slot start time | `09:00` |
| `BOOKING_WINDOW_AM_END` | AM slot end time | `13:00` |
| `BOOKING_WINDOW_PM_START` | PM slot start time | `14:00` |
| `BOOKING_WINDOW_PM_END` | PM slot end time | `18:00` |
| `DEV_WHATSAPP_NUMBER` | Developer/test WhatsApp number (Flow AI number during dev) | Flow AI business number |
| `LABEL_ID_OUT_OF_SCOPE` | Meta label ID for Blue (out-of-scope) | Set during client onboarding |
| `LABEL_ID_CONFLICT` | Meta label ID for Orange (slot conflict) | Set during client onboarding |
| `LABEL_ID_CHANGE_REQUEST` | Meta label ID for Yellow (reschedule/cancellation) | Set during client onboarding |
| `LABEL_ID_CUSTOMER_DISTRESS` | Meta label ID for Red (anger/distress) | Set during client onboarding |

---

## Agent Content Management

> Business data is managed through **Supabase Studio** — no n8n access needed. Changes take effect on the next customer message automatically. Client logs into Supabase Studio, navigates to the `config` or `policies` table, clicks a cell to edit, and saves.

### How to update services and pricing — `Config` sheet

Open `HeyAircon CRM` → `Config` sheet. Two columns: `key` and `value`.

**Rules:**
- Rows with `key` starting with `service_` appear in the agent's SERVICES section
- Rows with `key` starting with `pricing_` appear in the agent's PRICING section
- Row order in the sheet controls display order
- To add: insert a new row with the correct prefix. To remove: delete the row. To update: edit the `value` cell.

**Service keys** — `value` should be a complete readable description starting with the service name:
```
service_general_servicing  →  General Servicing: [description]
service_chemical_wash      →  Chemical Wash: [description]
service_chemical_overhaul  →  Chemical Overhaul: [description]
service_gas_topup          →  Gas Top Up: [description]
service_repair             →  Aircon Repair: [description]
```

**Pricing keys** — `value` should be a readable pricing summary:
```
pricing_general_servicing_9_12k   →  1 unit $50, 2 units $60, 3 units $75...
pricing_general_servicing_18_24k  →  1 unit $60, 2 units $80...
pricing_general_servicing_contract→  Annual contract (4 services/year): 1 unit $180...
pricing_chemical_wash_9_12k       →  1 unit $80, 2 units $150...
pricing_chemical_wash_18k         →  1 unit $110, 2 units $210...
pricing_chemical_wash_24k         →  1 unit $130, 2 units $250...
pricing_chemical_overhaul_9_12k   →  1 unit $150, 2 units $280...
pricing_chemical_overhaul_18k     →  1 unit $180, 2 units $340...
pricing_chemical_overhaul_24k     →  1 unit $200, 2 units $380...
pricing_gas_topup                 →  R32: $60-$150. R410A: $60-$150...
pricing_condenser_servicing       →  High Jet Wash $40. Chemical Wash $90...
pricing_repair                    →  Quote provided on-site after inspection.
```

**Appointment and booking config keys:**
```
appointment_window_am    →  9am to 1pm
appointment_window_pm    →  1pm to 6pm
booking_lead_time_days   →  2
```

> ⚠️ Pricing in the Config sheet is currently populated with real data from the HeyAircon website. Confirm all prices with the client before UAT.

---

### How to update policies — `Policies` sheet

Open `HeyAircon CRM` → `Policies` sheet. Two columns: `policy_name` and `policy_text`.

**Rules:**
- `policy_name` is a label for your reference only — the agent does not see it
- `policy_text` is what the agent reads — write as complete, plain prose
- Row order controls the order policies appear to the agent
- To add a new policy: insert a row with any `policy_name` and the full `policy_text`
- To update: edit the `policy_text` cell directly

**Current policy rows:**
```
booking_policy       →  Required fields and collection process
escalation_policy    →  When and how to escalate
rescheduling_policy  →  Rescheduling rules (⚠️ confirm exact wording with client before UAT)
cancellation_policy  →  Cancellation rules and fees (⚠️ confirm exact wording with client before UAT)
```

> ⚠️ Rescheduling and cancellation policy text is currently a placeholder. Replace with confirmed client wording before UAT.

---

## Dev & Testing Setup

> **WhatsApp number for development:** Meta provides a free test number inside the Meta Developer portal. No business verification needed to start. Once verified and tested, switch to HeyAircon's real WhatsApp Business number by updating env vars only.

| Phase | WhatsApp Number Used | API |
|-------|---------------------|-----|
| Development & testing | Meta free test number | Meta Cloud API (dev token) |
| UAT with client | Meta free test number or Flow AI number | Meta Cloud API (dev token) |
| Production go-live | HeyAircon business number | Meta Cloud API (permanent System User token) |

**What this means for build:** No workflow changes needed to switch numbers — only the 360dialog API key and webhook URL need to be updated. Design all workflows and tools to be number-agnostic from day one.

---

## ✅ Build Clearance

Based on the decisions above, the following components are **unblocked and ready to build**:

| Component | Status | Blocker (if any) |
|-----------|--------|-----------------|
| A — WhatsApp channel & n8n setup | ✅ Ready | None — using Flow AI number |
| B — Layer 1 escalation gate | ✅ Ready | None |
| C — AI Agent node + FAQ | ✅ Ready (with placeholders) | Real pricing/service docs needed before UAT |
| D — Booking flow tools | ✅ Ready | Time windows confirmed (9–1, 1–6); min notice = 2 days |
| E — Escalation flow | ✅ Ready | `HUMAN_AGENT_WHATSAPP_NUMBER` needed; use Flow AI number as placeholder during dev |

**Still blocked:**
- OOH handling logic (business hours not yet provided — build shell, activate later)
- Final system prompt content (pending real pricing/service/policy docs)

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Agent responds to new inquiry | < 10 seconds |
| Basic FAQ correctly answered without escalation | > 80% |
| New booking (free slot) completed without human touch | > 70% of free-slot bookings |
| Escalation correctly triggered on conflict or out-of-scope | 100% of qualifying cases |
| All bookings captured to Google Sheets | 100% |

---

## 1. Tech Stack

| Layer | Tool | Rationale |
|-------|------|-----------|
| WhatsApp channel | **Meta WhatsApp Cloud API** (direct, no BSP) | No BSP monthly fee; free during dev with test number; only Meta conversation fees apply in production |
| Orchestration, agent & workflow | **n8n** (self-hosted on Railway) | Native AI Agent node handles LLM calls, tool calling, and memory |
| AI / LLM | **GPT-4o-mini** (OpenAI) | Low latency, low cost |
| Conversation memory | **n8n Postgres Chat Memory node** (Railway PostgreSQL) | Persists conversation history per phone number — stays on Railway Postgres, not Supabase |
| Calendar | **Google Calendar** (native n8n node, used as agent tool) | Availability check + event creation only. No deletion or update by agent. |
| CRM & data layer | **Supabase** (hosted Postgres) | Flow AI-owned. Bookings, customers, interaction log, config, and policies. Client accesses via Supabase Studio. Replaces Google Sheets. |
| Client data access | **Supabase Studio** | Clients log in to view bookings, customers, and interaction history. Edit config and policies directly via table editor. |
| Human agent notification | **WhatsApp via Meta Cloud API HTTP** | Escalation alerts sent to human agent's number |
| Hosting | **Railway** | n8n primary + worker + Railway Postgres (chat memory only); ~$5–10/month |

---

## 2. System Architecture

### Approach: n8n-native AI Agent

Two-layer workflow:
- **Layer 1 — Hard-coded pre-checks** (deterministic, no AI): escalation flag check, inbound message routing
- **Layer 2 — AI Agent node** (LLM + tool calling): inquiry handling, booking flow, escalation decisions

```
Customer (WhatsApp)
        │
        ▼
  360dialog BSP ──── webhook ────▶ n8n Inbound Workflow
                                          │
                          ┌───────────────┤  LAYER 1: Hard-coded pre-checks
                          │               ├─ Is escalation_flag = true?
                          │               │    └─▶ Stop. Log only.
                          │               └─ Pass through to Layer 2
                          │
                          │               LAYER 2: n8n AI Agent Node
                          ▼
                   ┌─────────────────────────────────────────┐
                   │  AI Agent Node                          │
                   │  ├── LLM: Claude Haiku / GPT-4o-mini    │
                   │  ├── Memory: Postgres Chat Memory       │
                   │  │          (keyed by phone number)     │
                   │  ├── System Prompt: persona, services,  │
                   │  │   pricing, booking rules, policies   │
                   │  └── Tools:                             │
                   │      ├── check_calendar_availability    │
                   │      │   (single calendar, 2 windows)   │
                   │      ├── create_calendar_event          │
                   │      │   (adds event only, no edits)    │
                   │      ├── write_booking_to_sheets        │
                   │      ├── read_booking_from_sheets       │
                   │      │   (for conflict check context)   │
                   │      ├── send_human_agent_notification  │
                   │      └── escalate_to_human              │
                   └──────────────────┬──────────────────────┘
                                      │
                                      ▼
                          Send WhatsApp reply
                          (360dialog HTTP node)
```

**Booking flow logic:**

```
Customer requests a slot
        │
        ▼
check_calendar_availability
        │
   ┌────┴────┐
   │         │
Free        ≥1 booking exists
   │         │
   ▼         ▼
create_    Escalate to human
calendar_  send_human_agent_notification
event      → inform customer human will reach out
   │
   ▼
write_booking_to_sheets
   │
   ▼
Send confirmation to customer
```

---

## 3. State & Memory Design

### Conversation memory — Postgres Chat Memory node
Keyed by phone number. Window: last 20 messages. Persists across n8n restarts.

### Booking & customer data — Google Sheets

**Escalation flag** (in Sheets): gates whether agent responds. Set by `escalate_to_human` tool. Cleared manually by human agent.

---

## 4. Component Build Plan

#### Component A — WhatsApp Channel & n8n Setup
**Goal:** Messages flowing in and out.

- [ ] Apply for 360dialog account; submit Meta Business Manager verification
- [ ] Configure 360dialog sandbox for development
- [ ] Set up n8n on Railway with PostgreSQL
- [ ] Create `POST /whatsapp-inbound` webhook workflow
- [ ] Create reusable sub-workflow: send outbound WhatsApp message
- [ ] Test round-trip: send → webhook → log → reply

**Acceptance:** Send "Hello" → receive auto-reply.

---

#### Component B — Layer 1 Pre-check (Escalation Gate)
**Goal:** If customer is escalated, agent is completely silent.

- [ ] At start of workflow, read `escalation_flag` from Google Sheets by phone number
- [ ] If `true` → log inbound message, stop workflow (no agent runs)
- [ ] Human clears flag manually in Sheets to re-enable agent for that customer

**Acceptance:** Escalated customer receives no agent reply. Non-escalated customer passes through.

---

#### Component C — AI Agent Node Setup
**Goal:** Agent handles FAQ correctly and enters booking flow on request.

- [ ] Add AI Agent node (after Layer 1 passes)
- [ ] Configure LLM credential (Claude Haiku or GPT-4o-mini)
- [ ] Add Postgres Chat Memory node, keyed by phone number; window: last 20 messages
- [ ] Write system prompt using placeholder content for pricing, services, and policies (see Placeholder Content section above)
- [ ] Include booking rules in system prompt:
  - Two fixed windows: AM (9am–1pm), PM (1pm–6pm)
  - Minimum notice: `MIN_BOOKING_NOTICE_DAYS = 2` (agent must not accept bookings within 2 days of today)
  - Required fields: name, phone, address, postal code, service type, unit count, date, time window preference
  - Aircon brand: optional, collect if offered
- [ ] Include escalation rules in system prompt
- [ ] Explicit rule in prompt: agent never modifies or cancels calendar events
- [ ] Define tool descriptions precisely
- [ ] Test: agent answers FAQ with placeholder content and routes "I want to book" correctly

**Acceptance:** Agent answers 8/10 FAQs with placeholder content. Rejects booking for dates within 2 days. Memory persists across two separate messages. Replies within 5 seconds.

---

#### Component D — Booking Flow Tools (Calendar + Sheets)

- [ ] Create `check_calendar_availability` tool:
  - Input: date, time window (`AM` or `PM`)
  - Validates date is at least `MIN_BOOKING_NOTICE_DAYS` ahead (double-check; agent also checks)
  - Queries single Google Calendar for any existing events overlapping 9am–1pm or 1pm–6pm on the given date
  - Returns: `available` or `conflict`
- [ ] Create `create_calendar_event` tool:
  - Input: date, time window, customer name, address, service type
  - Creates Google Calendar event for full window duration (9am–1pm or 1pm–6pm)
  - **Add only** — no update, no delete
  - Returns event ID
- [ ] Create `write_booking_to_sheets` tool:
  - Input: all booking fields + customer fields
  - **Step 1 — Upsert Customers sheet:** check if `phone_number` row exists
    - If exists: update `customer_name`, `address`, `postal_code`, `last_seen`, increment `total_bookings`
    - If not exists: create new row with all customer fields, set `first_seen = now`, `total_bookings = 1`
  - **Step 2 — Append Bookings sheet:** generate booking ID (HA-YYYYMMDD-XXXX), append booking row
- [ ] Create `read_booking_from_sheets` tool:
  - Input: phone number
  - Returns latest booking record (for agent internal context only — not for customer-facing lookup)

**Acceptance:** Agent checks calendar for a real date ≥2 days out, creates event, writes Sheets row, sends confirmation.

---

#### Component E — Escalation Flow

- [ ] Create `send_human_agent_notification` tool:
  - Input: customer name, phone, reason, relevant details
  - Reads `HUMAN_AGENT_WHATSAPP_NUMBER` from env var
  - Sends structured WhatsApp message via 360dialog: customer name, phone, reason, requested slot if applicable
  - During dev: sends to Flow AI number
- [ ] Create `escalate_to_human` tool:
  - Sets `escalation_flag = true` and `escalation_reason` in Sheets
  - Sends customer appropriate message based on reason
  - Calls `send_human_agent_notification`
- [ ] Escalation triggers in system prompt:
  - Slot conflict (`conflict`)
  - Any reschedule or cancellation request (`change_request`)
  - Out-of-scope question after one genuine attempt (`out_of_scope`)
- [ ] Layer 1 (Component B) blocks agent once escalation flag is set

**Acceptance:** All three escalation triggers fire correctly. Human notification sent to configured number. Agent silenced after escalation.

---

## 5. Week-by-Week Sprint Plan

| Week | Focus | Deliverables | Done When |
|------|-------|--------------|-----------|
| **Week 1** | Infrastructure & channel | 360dialog sandbox live, n8n on Railway with Postgres, webhook round-trip, Layer 1 escalation gate | Message sent → reply received; escalation flag test blocks agent |
| **Week 2** | AI Agent + system prompt + FAQ | Agent node with LLM + Postgres memory, system prompt with service/pricing context, FAQ handling | Agent answers 8/10 FAQs; memory persists |
| **Week 3** | Booking flow tools | `check_calendar_availability`, `create_calendar_event`, `write_booking_to_sheets`, `read_booking_from_sheets` live; full free-slot booking end-to-end | Customer goes from "I want to book" → Calendar event created → Sheets row written → confirmation sent |
| **Week 4** | Escalation flow + end-to-end testing | `escalate_to_human`, `send_human_agent_notification`, conflict escalation, change request escalation; scripted E2E test | All escalation scenarios trigger correctly; client walkthrough |
| **Buffer / UAT** | Prompt tuning + edge cases | Client acts as test customer; edge cases resolved | Client sign-off |

---

## 6. Supabase Schema (CRM)

> All five tables live in the `heyaircon` Supabase project. Full schema definitions with SQL are in the **Stack Migration** section above. This section is a summary reference.

**`bookings`** — one row per booking, written by agent tools

| Column | Description | Written by |
|--------|-------------|------------|
| booking_id | HA-YYYYMMDD-XXXX | Agent tool |
| created_at | Timestamp (auto) | Supabase |
| phone_number | FK → customers | Agent tool |
| service_type | e.g. Chemical Wash | Agent tool |
| unit_count | Number of aircon units | Agent tool |
| aircon_brand | Optional | Agent tool |
| slot_date | Date of appointment | Agent tool |
| slot_window | AM or PM | Agent tool |
| calendar_event_id | Google Calendar event ID | `create_calendar_event` tool |
| booking_status | Confirmed / Escalated / Cancelled | Agent tool + human (manual in Studio) |
| escalation_flag | TRUE/FALSE — pauses agent | `escalate_to_human` tool; cleared manually in Studio |
| escalation_reason | conflict / change_request / out_of_scope | `escalate_to_human` tool |
| notes | Admin notes | Manual in Studio |

**`interactions_log`** — append-only, every inbound and outbound message

| Column | Description |
|--------|-------------|
| timestamp | Auto |
| phone_number | |
| direction | inbound / outbound |
| message_text | |
| message_type | text / image / other |

**`customers`** — one row per customer, upserted on every booking

| Column | Description | Written by |
|--------|-------------|------------|
| phone_number | Primary key | Agent tool |
| customer_name | Full name | Agent tool |
| address | Most recent address provided | Agent tool |
| postal_code | Most recent postal code | Agent tool |
| first_seen | First interaction timestamp | Agent tool (create only) |
| last_seen | Most recent interaction | Agent tool |
| total_bookings | Booking count | Agent tool (incremented) |
| notes | Admin notes | Manual in Studio |

**`config`** — key-value business configuration, fetched at runtime

| Column | Description |
|--------|-------------|
| key | e.g. `service_chemical_wash`, `pricing_chemical_wash_9_12k` |
| value | Full description or pricing text |
| sort_order | Controls order in agent context |

> Client edits this table in Supabase Studio to update services, pricing, and appointment windows. Changes take effect on the next customer message — no n8n restart needed.

**`policies`** — policy text, fetched at runtime

| Column | Description |
|--------|-------------|
| policy_name | `booking_policy`, `escalation_policy`, `rescheduling_policy`, `cancellation_policy` |
| policy_text | Full policy text as plain prose |
| sort_order | Controls order in agent context |

> Client edits this table in Supabase Studio to update policy wording. Changes take effect on the next customer message.

---

## 7. Build Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 360dialog / Meta API approval delayed | HIGH | Blocks everything | Using Flow AI number for dev — no approval needed to start |
| Required docs not provided before UAT | MEDIUM | Agent uses placeholder content | Placeholders in place; clearly marked for swap before client UAT |
| `HUMAN_AGENT_WHATSAPP_NUMBER` not yet set | LOW | Escalation notifications go to wrong number | Default to Flow AI number during dev; update before UAT |
| Agent accepts bookings within 2-day notice window | LOW | Ops issue for HeyAircon | `MIN_BOOKING_NOTICE_DAYS` enforced in both agent prompt and `check_calendar_availability` tool (double guard) |
| Agent escalates too aggressively (poor FAQ coverage) | MEDIUM | Poor customer experience | Iterative prompt tuning in Week 4 using placeholder content first, real content when available |
| Calendar conflict race condition (two simultaneous free-slot bookings) | LOW | Double booking | Acceptable for Phase 1 volume; flag for Phase 2 hardening |
| Number switch (dev → production) causes disruption | LOW | Broken webhook | Design workflows to be number-agnostic; switch is a single 360dialog + n8n env var update |
| **Supabase migration delays Component E build** | MEDIUM | Sheets and Supabase nodes coexist mid-migration, causing confusion | Complete migration Steps 1–3 fully before starting Component E. Component D has already been built; migrate it as part of Step 2 before E begins. |
| **Client edits Sheets sync mirror and expects changes to stick** | LOW | Client confused when Sheets values are overwritten by next sync cycle | Only offer Sheets sync if client explicitly requests it. When setting it up, make clear the Sheet is read-only and add a header note on each tab. Config and policies are excluded from sync entirely — changes must go through Supabase or Flow AI retainer service. |

---

## 8. Pre-Build Checklist

> ✅ = Unblocked. ⚠️ = Can proceed with default/placeholder. 🔴 = Hard blocker.

**Completed:**
- [x] ✅ Dev WhatsApp number confirmed — using Meta free test number
- [x] ✅ Time windows confirmed — 9am–1pm, 1pm–6pm
- [x] ✅ Minimum notice period set — 2 days (configurable)
- [x] ✅ WhatsApp channel confirmed — Meta Cloud API direct (no BSP fee)
- [x] ✅ Components A, B, C built and tested against Google Sheets

**Supabase Migration (complete before starting Component E — Component D already built, migrate it as part of this step):**
- [ ] 🔴 Supabase project `heyaircon` created
- [ ] 🔴 All 5 tables created with correct schema
- [ ] 🔴 `config` table seeded with services and pricing data
- [ ] 🔴 `policies` table seeded with policy rows
- [ ] 🔴 Supabase Postgres credential added to n8n (`Supabase HeyAircon`)
- [ ] 🔴 `WA Inbound Handler` — 3 Sheets nodes replaced with Postgres nodes
- [ ] 🔴 `WA Log Interaction` — Sheets append replaced with Postgres insert
- [ ] 🔴 `Tool - Write Booking` — all 4 Sheets nodes replaced with Postgres nodes
- [ ] 🔴 `Tool - Get Customer Bookings` — Sheets lookup replaced with Postgres select
- [ ] 🔴 End-to-end curl test passed against Supabase

**Still pending (client input):**
- [ ] ⚠️ Human agent WhatsApp number — using dev number as placeholder during build
- [ ] ⚠️ Service catalogue final pricing — placeholder in use
- [ ] ⚠️ Rescheduling policy — placeholder in use
- [ ] ⚠️ Cancellation policy — placeholder in use
- [ ] ⚠️ Business operating hours — pending; OOH logic deferred
- [ ] ⚠️ Days of operation — pending; deferred
- [ ] ⚠️ Public holiday operation — defaulting to closed
- [ ] ⚠️ Out-of-hours handling decision — deferred

**Go-live blockers:**
- [ ] 🔴 Client's Google account — needed for Calendar tool (Component D)
- [ ] 🔴 Meta Business Verification — needed before production go-live
- [ ] 🔴 HeyAircon's WhatsApp Business number — needed before go-live
- [ ] 🔴 Client Supabase login provisioned and tested

---

## Phase 2 — Backlog

> The following items were originally planned but moved to Phase 2 following client scope discussion on 4 April 2026.

| # | Feature |
|---|---------|
| 1 | Deposit and payment flow (payment instruction, screenshot receipt, payment deadline cron) |
| 2 | Admin keyword commands (CONFIRM, COMPLETE, RESOLVED) |
| 3 | Pre-appointment reminders (24h automated WhatsApp reminder) |
| 4 | Post-service feedback request and Google review link |
| 5 | Multi-team calendar management (round-robin assignment, Teams config sheet) |
| 6 | Agent-initiated calendar event updates and deletions |
| 7 | Customer-facing booking lookup (past/upcoming bookings) |
| 8 | Out-of-hours auto-reply |
| 9 | Bookkeeping module |
| 10 | CRM web interface |
| 11 | Invoice generation |
| 12 | Sales reporting dashboard |
| 13 | Campaign / upsell automation |

## Deferred Technical Items

> Known technical problems logged during Phase 1 build.

### DT-001 — Interactions Log storage scaling ✅ RESOLVED

**Resolution:** Resolved by the Supabase migration. `interactions_log` is now a Postgres table with no row ceiling, indexed by `phone_number` for fast per-customer lookups. The `WA Log Interaction` sub-workflow writes to Supabase via Postgres INSERT. No Sheets row limit applies.

---

### DT-002 — Policy content stored in spreadsheet cells ✅ RESOLVED

**Resolution:** Resolved by the Supabase migration. Policy text now lives in the `policies` Supabase table. Supabase Studio's table editor provides a significantly better editing experience for long prose than a Google Sheets cell — full cell expansion, no cell character rendering issues, and clean row management. Version history is available via Supabase's built-in table history. Google Docs migration is no longer required.
