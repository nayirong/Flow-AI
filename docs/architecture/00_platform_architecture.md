# Flow AI — Python Orchestration Engine Architecture
## Platform Architecture Reference | Flow AI

**Last Updated:** 2026-04-19
**Status:** Live in production — Python engine receiving real WhatsApp traffic for HeyAircon
**Replaces:** `clients/hey-aircon/plans/build/00_architecture_reference.md` (n8n reference — preserved until decommission confirmed)

---

## 1. System Overview

### Purpose

The Python orchestration engine replaces n8n as the workflow execution layer for the Flow AI WhatsApp agent platform. It receives inbound WhatsApp messages from Meta Cloud API, runs an escalation gate, builds agent context from Supabase, invokes the Claude agent loop with tools, and sends the reply back via Meta Cloud API.

The engine is **client-agnostic**. All client-specific behaviour is loaded at runtime from Supabase and Railway env vars by `client_id`. A single deployed service handles all clients simultaneously.

### How It Fits Into Existing Infrastructure

| Layer | Current (n8n) | Target (Python engine) |
|-------|--------------|----------------------|
| Webhook receiver | n8n primary service on Railway | FastAPI service `flow-engine` on Railway |
| Message execution | n8n worker service on Railway | FastAPI `BackgroundTasks` (same pattern) |
| LLM | GPT-4o-mini via OpenAI | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) primary; GPT-4o-mini (OpenAI SDK) silent fallback per-request when Anthropic API unreachable |
| Supabase reads/writes | n8n Postgres credential nodes | `supabase-py` async client |
| Meta API | n8n HTTP Request node | `httpx` async HTTP client |
| Google Calendar | n8n HTTP Request node (Week 3) | Google API Python client |
| Deployment | `n8n` + `n8n-worker` services | `flow-engine` service (added alongside n8n during transition) |

### End-to-End Message Flow

```
Meta Cloud API
    ↓  POST /webhook/whatsapp/{client_id}
FastAPI Webhook Receiver (webhook.py)
    ↓  returns 200 OK immediately
    ↓  dispatches BackgroundTask
Message Handler (message_handler.py)
    ↓  log inbound to interactions_log
    ↓  load client config (ClientConfig from cache/Supabase + env)
    ↓
Escalation Gate ─── escalation_flag = TRUE ──→ send holding reply → log → stop
    ↓ FALSE
    ↓  new customer? → create customers row
Context Builder (context_builder.py)
    ↓  fetch config + policies from client Supabase
    ↓  fetch last 20 messages from interactions_log
    ↓  assemble system_message
    ↓
Claude Agent Loop (agent_runner.py)
    ↓  messages.create() with tool definitions
    ↓  tool_use block? → execute tool → append result → loop
    ↓  end_turn or stop_sequence → extract final text
    ↓
Meta Cloud API (send reply)
    ↓  log outbound to interactions_log
```

---

## 2. Tech Stack

Locked decisions from `CLAUDE.md`. Do not deviate.

| Layer | Technology | Notes |
|-------|-----------|-------|
| Web framework | FastAPI (Python, async) | All routes are async |
| LLM (primary) | Anthropic SDK — `claude-haiku-4-5-20251001` | Direct SDK, no LangChain |
| LLM (fallback) | OpenAI SDK — `gpt-4o-mini` | Activated per-request when Anthropic API is unreachable (timeout, 5xx, rate limit); transparent to customer |
| Database client | `supabase-py` | Async client for all Supabase reads/writes |
| HTTP client | `httpx` | Async — Meta Cloud API calls |
| Config/env | `pydantic-settings` | Typed env var loading via `Settings` model |
| Calendar | Google API Python client | Service account auth, add-only |
| Testing | `pytest` + `pytest-asyncio` | Async test support |
| Observability | Langfuse | Agent trace monitoring and cost tracking (planned) |

**Hard rule:** Do not use LangChain. The Claude tool-use loop is simple enough to own explicitly.

---

## 3. Folder Structure

```
engine/
├── api/
│   └── webhook.py              # FastAPI app — POST + GET /webhook/whatsapp/{client_id}, GET /health
├── core/
│   ├── message_handler.py      # Inbound message orchestration: escalation gate → context → agent → send reply
│   ├── context_builder.py      # Assembles system_message from Supabase config/policies + conversation history
│   ├── agent_runner.py         # Claude agent loop: tool_use handling, loop until end_turn
│   └── tools/
│       ├── __init__.py         # Exports tool definitions list and tool dispatch map
│       ├── definitions.py      # Anthropic tool definition dicts (name, description, input_schema)
│       ├── calendar_tools.py   # check_calendar_availability, create_calendar_event
│       ├── booking_tools.py    # write_booking, get_customer_bookings
│       └── escalation_tool.py  # escalate_to_human
├── integrations/
│   ├── meta_whatsapp.py        # Meta Cloud API: send_message(), verify_webhook_token()
│   ├── supabase_client.py      # Supabase factory: get_client_db(client_id), get_shared_db()
│   └── google_calendar.py      # Google Calendar: check_availability(), create_event()
├── config/
│   ├── settings.py             # pydantic-settings — loads Railway env vars into Settings model
│   └── client_config.py        # ClientConfig model, load_client_config(), in-process TTL cache
└── tests/
    ├── unit/
    │   ├── test_context_builder.py
    │   ├── test_escalation_gate.py
    │   ├── test_booking_tools.py
    │   └── test_calendar_tools.py
    ├── integration/
    │   └── test_message_handler.py  # Full flow with mocked Meta, real Supabase test project
    └── conftest.py                  # Shared fixtures: mock Meta, test Supabase client, sample payloads
```

---

## 4. Component Breakdown

### Component 1 — Webhook Receiver

**Replaces:** n8n `Webhook GET` node + n8n `Webhook POST` node + n8n `Has Message?` IF node

**File:** `engine/api/webhook.py`

#### Routes

```
POST /webhook/whatsapp/{client_id}   — receives inbound Meta webhook events
GET  /webhook/whatsapp/{client_id}   — Meta webhook verification handshake
GET  /health                         — Railway health check
```

#### POST handler

```python
async def receive_whatsapp_message(
    client_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    ...
```

- Parses raw JSON body from `request.json()`
- Guards against status update payloads: checks `body["entry"][0]["changes"][0]["value"]` — if no `"messages"` key, return `200 OK` immediately (no processing). This replicates the n8n `Has Message?` IF node.
- Extracts fields: `phone_number`, `message_text`, `message_type`, `message_id`, `display_name`, `wa_id` from `body["entry"][0]["changes"][0]["value"]["messages"][0]`
- Adds `handle_inbound_message(client_id, extracted_fields)` as a `BackgroundTask`
- Returns `Response(status_code=200)` **before** the background task executes. This is the same pattern as the n8n primary/worker split.

#### GET handler (Meta verification)

```python
async def verify_webhook(
    client_id: str,
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify.token"),
) -> Response:
    ...
```

- Loads `ClientConfig` for `client_id`
- Compares `hub_verify_token` against `ClientConfig.meta_verify_token`
- On match: return `PlainTextResponse(hub_challenge, status_code=200)`
- On mismatch: return `Response(status_code=403)`

#### Health check

```python
async def health() -> dict:
    return {"status": "ok"}
```

#### Error handling

- Any exception during payload parsing: log error, return `200 OK` (Meta must always receive 200)
- Unknown `client_id`: log warning, return `200 OK`
- The background task catches and logs all exceptions internally — never propagates to the webhook response

#### Acceptance criteria

- [ ] Meta GET verification responds with `hub.challenge` value
- [ ] Status update payloads (no `messages` array) return `200 OK` with no processing
- [ ] Valid inbound message returns `200 OK` within 500ms before background task completes
- [ ] Unknown `client_id` returns `200 OK` without error response to Meta

---

### Component 2 — Escalation Gate

**Replaces:** n8n `Read Escalation Flag` Postgres node + n8n `Is Escalated?` IF node + n8n `Log Inbound (Escalated)` + n8n `Send Holding Reply` nodes

**File:** `engine/core/message_handler.py` (runs at the start of `handle_inbound_message`)

**Rule:** This is a hard programmatic check. The agent never decides whether it is escalated.

#### Flow

```python
async def handle_inbound_message(
    client_id: str,
    phone_number: str,
    message_text: str,
    message_type: str,
    message_id: str,
    display_name: str,
) -> None:
    ...
```

1. Load `ClientConfig` for `client_id`
2. Get client Supabase client via `get_client_db(client_id)`
3. Log inbound message to `interactions_log` (always — before any gate)
4. Query `customers` table:
   ```sql
   SELECT escalation_flag, escalation_reason
   FROM customers
   WHERE phone_number = $1
   LIMIT 1
   ```
5. **If row found AND `escalation_flag = TRUE`:**
   - Send holding reply via Meta API: `"Our team is currently looking into your request. A member of our team will be in touch with you shortly."`
   - Log outbound holding reply to `interactions_log`
   - Return — stop processing. Agent does not run.
6. **If no row found (new customer):**
   - INSERT into `customers`: `phone_number`, `customer_name` (from `display_name`), `first_seen = NOW()`, `last_seen = NOW()`, `escalation_flag = FALSE`
   - Continue to context builder
7. **If row found AND `escalation_flag = FALSE`:**
   - Update `customers` SET `last_seen = NOW()` WHERE `phone_number = $1`
   - Continue to context builder

#### Error handling

- Supabase query failure: log error, send fallback reply to customer, return (do not invoke agent on DB failure)
- Meta send failure for holding reply: log error, continue (do not crash the handler)

#### Acceptance criteria

- [ ] Escalated customer receives holding reply and agent does not run
- [ ] New customer row is created on first message
- [ ] Non-escalated returning customer proceeds to context builder
- [ ] Supabase failure sends fallback reply and exits cleanly

---

### Component 3 — Context Builder + Claude Agent Loop

**Replaces:** n8n `Fetch Config` Postgres node + n8n `Fetch Policies` Postgres node + n8n `Build Context` Code node + n8n `AI Agent` node + n8n Postgres Chat Memory sub-node

#### Context Builder

**File:** `engine/core/context_builder.py`

```python
async def build_system_message(
    db: AsyncClient,
    client_config: ClientConfig,
) -> str:
    ...
```

**Logic (mirrors n8n `Build Context` Code node exactly):**

1. Fetch config rows:
   ```sql
   SELECT key, value FROM config ORDER BY sort_order
   ```
2. Fetch policy rows:
   ```sql
   SELECT policy_name, policy_text FROM policies ORDER BY sort_order
   ```
3. Assemble `system_message` string with these sections in order:
   - Company identity block — **hardcoded, not from DB**. Contains the agent's identity as an aircon servicing agent. Prompt injection guardrails also hardcoded here.
   - `SERVICES` section: all `key`/`value` rows where `key` starts with `service_`
   - `PRICING` section: all `key`/`value` rows where `key` starts with `pricing_`
   - `APPOINTMENT WINDOWS` section: rows `appointment_window_am`, `appointment_window_pm`, `booking_lead_time_days`
   - `POLICIES` section: all `policy_text` values concatenated in row order
4. Return complete `system_message` string

**Identity and guardrails are hardcoded.** Client can update `config` and `policies` tables; they cannot override the agent's identity or prompt injection defences.

#### Conversation History

**File:** `engine/core/context_builder.py`

```python
async def fetch_conversation_history(
    db: AsyncClient,
    phone_number: str,
    limit: int = 20,
) -> list[dict]:
    ...
```

- Fetches last 20 messages from `interactions_log`:
  ```sql
  SELECT direction, message_text
  FROM interactions_log
  WHERE phone_number = $1
  ORDER BY timestamp DESC
  LIMIT 20
  ```
- Returns rows in reverse chronological order then reversed to ascending — oldest first
- Formats each row as a Claude `messages` array entry:
  - `direction = 'inbound'` → `{"role": "user", "content": message_text}`
  - `direction = 'outbound'` → `{"role": "assistant", "content": message_text}`
- This replaces the n8n Postgres Chat Memory sub-node (which stored history in Railway Postgres keyed by phone number with a 20-message window)

#### Claude Agent Loop

**File:** `engine/core/agent_runner.py`

```python
async def run_agent(
    system_message: str,
    conversation_history: list[dict],
    current_message: str,
    tool_definitions: list[dict],
    tool_dispatch: dict[str, Callable],
    client_config: ClientConfig,
) -> str:
    ...
```

1. Build `messages` list: `conversation_history` + `[{"role": "user", "content": current_message}]`
2. Call `anthropic_client.messages.create()`:
   - `model`: `claude-haiku-4-5-20251001` (primary; falls back to `gpt-4o-mini` via OpenAI SDK on Anthropic API failure)
   - `system`: `system_message`
   - `messages`: built above
   - `tools`: `tool_definitions`
   - `max_tokens`: 1024
3. Loop while `response.stop_reason == "tool_use"`:
   - Extract all `tool_use` content blocks from response
   - For each `tool_use` block: call `tool_dispatch[block.name](**block.input)`
   - Append assistant response + tool result(s) to `messages`
   - Call `anthropic_client.messages.create()` again with updated `messages`
4. On `stop_reason == "end_turn"` or `stop_reason == "stop_sequence"`:
   - Extract final text from `response.content` blocks where `type == "text"`
   - Return the text string

#### Error handling

- Anthropic API error: log, raise to `message_handler` which sends fallback reply
- Tool execution error: return error result dict to Claude (do not crash loop); Claude decides whether to retry or respond gracefully
- Max iterations guard: if loop exceeds 10 tool-use iterations, break and return a fallback string

#### Acceptance criteria

- [ ] `system_message` contains all `config` and `policies` rows from Supabase
- [ ] Identity block and guardrails are present in `system_message` regardless of DB content
- [ ] Conversation history returns last 20 messages in correct role mapping
- [ ] Agent loop correctly handles multi-turn tool use (e.g. check_availability → create_booking)
- [ ] Loop exits cleanly on `end_turn`

---

### Component 4 — Booking Tools

**Replaces:** n8n `Tool - Write Booking` sub-workflow + n8n `Tool - Get Customer Bookings` sub-workflow + n8n `Tool - Check Calendar` sub-workflow (Week 3) + n8n `Tool - Create Calendar Event` sub-workflow (Week 3)

**Files:** `engine/core/tools/calendar_tools.py`, `engine/core/tools/booking_tools.py`

All tools are plain async Python functions. Tool definitions (Anthropic format dicts) live in `engine/core/tools/definitions.py` separately from implementations.

---

#### Tool: `check_calendar_availability`

**File:** `engine/core/tools/calendar_tools.py`

```python
async def check_calendar_availability(
    date: str,          # ISO 8601 date string: "YYYY-MM-DD"
    timezone: str,      # IANA timezone string: "Asia/Singapore"
    calendar_creds: dict,
) -> dict:
    ...
```

**Operation:** Google Calendar API — list events on `date` for the configured calendar ID.

**Logic:**
- Query Google Calendar for all events on the given date within the calendar
- AM window: 09:00–13:00 (configurable via `BOOKING_WINDOW_AM_START` / `BOOKING_WINDOW_AM_END`)
- PM window: 14:00–18:00 (configurable via `BOOKING_WINDOW_PM_START` / `BOOKING_WINDOW_PM_END`)
- A window is **available** if it has zero existing bookings
- A window is **unavailable** if it has ≥1 existing booking

**Return shape:**
```json
{
  "date": "YYYY-MM-DD",
  "am_available": true,
  "pm_available": false,
  "am_window": "9am–1pm",
  "pm_window": "2pm–6pm"
}
```

**Error handling:** On Google API error, return `{"error": "calendar_unavailable", "message": "..."}` — agent informs customer to contact directly.

---

#### Tool: `create_calendar_event`

**File:** `engine/core/tools/calendar_tools.py`

```python
async def create_calendar_event(
    date: str,              # "YYYY-MM-DD"
    slot: str,              # "AM" or "PM"
    customer_name: str,
    phone_number: str,
    service_type: str,
    calendar_creds: dict,
    calendar_id: str,
) -> dict:
    ...
```

**Operation:** Google Calendar API — `events.insert()` on the configured calendar.

**Event fields:**
- `summary`: `"{service_type} — {customer_name}"`
- `description`: `"Phone: {phone_number}"`
- `start.dateTime`: ISO 8601 — slot AM = `{date}T09:00:00`, PM = `{date}T14:00:00`
- `end.dateTime`: ISO 8601 — slot AM = `{date}T13:00:00`, PM = `{date}T18:00:00`
- `start.timeZone` / `end.timeZone`: `"Asia/Singapore"`

**Return shape:**
```json
{
  "calendar_event_id": "google_event_id_string",
  "date": "YYYY-MM-DD",
  "slot": "AM",
  "summary": "General Servicing — John Tan"
}
```

**Hard rule:** Agent adds events only. It never calls `events.update()` or `events.delete()`. Any modification request goes through human escalation.

**Error handling:** On failure, return `{"error": "calendar_write_failed", "message": "..."}` — agent escalates to human.

---

#### Tool: `write_booking`

**File:** `engine/core/tools/booking_tools.py`

```python
async def write_booking(
    phone_number: str,
    customer_name: str,
    service_type: str,
    booking_date: str,      # "YYYY-MM-DD"
    slot: str,              # "AM" or "PM"
    address: str,
    unit_count: int,
    calendar_event_id: str,
    db: AsyncClient,
) -> dict:
    ...
```

**Operations:**
1. Generate `booking_id`: `"HA-{YYYYMMDD}-{4-digit-random}"`
2. INSERT into `bookings`:
   ```sql
   INSERT INTO bookings (
     booking_id, phone_number, service_type, unit_count,
     slot_date, slot_window, calendar_event_id, booking_status
   ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'Confirmed')
   ```
3. UPSERT into `customers`:
   ```sql
   INSERT INTO customers (phone_number, customer_name, address, last_seen, total_bookings)
   VALUES ($1, $2, $3, NOW(), 1)
   ON CONFLICT (phone_number) DO UPDATE SET
     customer_name = EXCLUDED.customer_name,
     address = EXCLUDED.address,
     last_seen = NOW(),
     total_bookings = customers.total_bookings + 1
   ```

**Return shape:**
```json
{
  "booking_id": "HA-20260415-7823",
  "status": "confirmed",
  "date": "YYYY-MM-DD",
  "slot": "AM",
  "service_type": "General Servicing"
}
```

**Error handling:** On Supabase error, return `{"error": "booking_write_failed", "message": "..."}` — agent escalates to human.

---

#### Tool: `get_customer_bookings`

**File:** `engine/core/tools/booking_tools.py`

```python
async def get_customer_bookings(
    phone_number: str,
    db: AsyncClient,
) -> dict:
    ...
```

**Operation:**
```sql
SELECT booking_id, service_type, slot_date, slot_window, booking_status
FROM bookings
WHERE phone_number = $1
ORDER BY created_at DESC
```

**Return shape:**
```json
{
  "bookings": [
    {
      "booking_id": "HA-20260415-7823",
      "service_type": "General Servicing",
      "slot_date": "2026-04-20",
      "slot_window": "AM",
      "booking_status": "Confirmed"
    }
  ],
  "count": 1
}
```

**Error handling:** On Supabase error, return `{"error": "booking_read_failed", "bookings": [], "count": 0}`.

---

### Component 5 — Escalate-to-Human Tool

**Replaces:** n8n `Tool - Escalate to Human` sub-workflow (Component E)

**File:** `engine/core/tools/escalation_tool.py`

**Distinction from Component 2:** The escalation gate (Component 2) is a programmatic check that runs before the agent. This tool is a **Claude-callable tool** — the agent calls it when it decides escalation is needed based on conversation context. Both result in `escalation_flag = TRUE`.

```python
async def escalate_to_human(
    phone_number: str,
    reason: str,            # agent-provided reason string (logged to customers.escalation_reason)
    db: AsyncClient,
    client_config: ClientConfig,
) -> dict:
    ...
```

**Operations:**

1. SET `escalation_flag = TRUE` in `customers`:
   ```sql
   UPDATE customers
   SET escalation_flag = TRUE,
       escalation_reason = $1
   WHERE phone_number = $2
   ```

2. Send WhatsApp notification to human agent via Meta Cloud API:
   - To: `ClientConfig.human_agent_number`
   - Message: `"[Escalation] Customer {phone_number} needs attention.\nReason: {reason}"`
   - Uses same `send_message()` function as outbound replies

**Return shape:**
```json
{
  "status": "escalated",
  "phone_number": "+6512345678",
  "reason": "Customer requesting reschedule — out of agent scope"
}
```

**Error handling:**
- Supabase UPDATE failure: log error, return `{"error": "escalation_db_failed"}` — agent informs customer to contact directly
- Meta send failure for human notification: log error, return success to agent (escalation flag is still set even if notification fails)

#### Acceptance criteria

- [ ] `escalation_flag` is set to `TRUE` in Supabase after tool call
- [ ] Human agent WhatsApp number receives notification message
- [ ] `escalation_reason` is stored
- [ ] Subsequent messages from same customer are caught by the Component 2 gate

---

## 5. Client Config Loading

### Hybrid Config Pattern

Non-sensitive config lives in the shared Flow AI Supabase `clients` table. High-sensitivity secrets live in Railway env vars namespaced by client.

#### `clients` table (shared Flow AI Supabase)

```sql
CREATE TABLE clients (
  id                    SERIAL PRIMARY KEY,
  client_id             TEXT UNIQUE NOT NULL,       -- URL slug: "hey-aircon"
  display_name          TEXT NOT NULL,              -- "HeyAircon"
  meta_phone_number_id  TEXT NOT NULL,              -- Meta phone number ID (not a secret)
  meta_verify_token     TEXT NOT NULL,              -- Webhook verification token (not a secret)
  human_agent_number    TEXT NOT NULL,              -- WhatsApp number for escalation notifications
  google_calendar_id    TEXT,                       -- Google Calendar ID for this client
  timezone              TEXT DEFAULT 'Asia/Singapore',
  is_active             BOOLEAN DEFAULT TRUE,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);
```

**Fields NOT stored here:** `meta_whatsapp_token`, `supabase_url`, `supabase_service_key`, `anthropic_api_key`, `openai_api_key` — these are high-sensitivity secrets that live in Railway env vars only. LLM keys are per-client so each client is billed on their own Anthropic and OpenAI accounts.

#### Railway env vars (per client, on `flow-engine` service)

Pattern: `{CLIENT_ID_UPPER}_{VAR}` where `CLIENT_ID_UPPER` is the `client_id` uppercased with hyphens replaced by underscores.

| Env var | Example for hey-aircon | Notes |
|---------|----------------------|-------|
| `{CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN` | `HEY_AIRCON_META_WHATSAPP_TOKEN` | Bearer token for Meta API |
| `{CLIENT_ID_UPPER}_SUPABASE_URL` | `HEY_AIRCON_SUPABASE_URL` | Client's Supabase project URL |
| `{CLIENT_ID_UPPER}_SUPABASE_SERVICE_KEY` | `HEY_AIRCON_SUPABASE_SERVICE_KEY` | Client's Supabase service role key |

#### `ClientConfig` Pydantic model

**File:** `engine/config/client_config.py`

```python
class ClientConfig(BaseModel):
    client_id: str
    display_name: str
    meta_phone_number_id: str
    meta_verify_token: str
    meta_whatsapp_token: str        # from env var
    human_agent_number: str
    google_calendar_id: str | None
    google_calendar_creds: dict     # service account JSON loaded from env/file
    supabase_url: str               # from env var
    supabase_service_key: str       # from env var
    anthropic_api_key: str          # from {CLIENT_ID_UPPER}_ANTHROPIC_API_KEY — per-client LLM billing
    openai_api_key: str             # from {CLIENT_ID_UPPER}_OPENAI_API_KEY — per-client fallback billing
    timezone: str
    is_active: bool
```

#### `load_client_config` function

**File:** `engine/config/client_config.py`

```python
async def load_client_config(client_id: str) -> ClientConfig:
    ...
```

**Logic:**
1. Check in-process cache: `_cache[client_id]` — if present and not expired (TTL 5 minutes), return cached value
2. Query shared Flow AI Supabase `clients` table: `SELECT * FROM clients WHERE client_id = $1 AND is_active = TRUE`
3. If no row: raise `ClientNotFoundError`
4. Resolve secrets from env vars using `{CLIENT_ID_UPPER}_*` pattern
5. If any required env var is missing: raise `ClientConfigError` with specific missing var name
6. Construct `ClientConfig`, store in cache with `expires_at = now + 300s`
7. Return `ClientConfig`

**Cache structure:**
```python
_cache: dict[str, tuple[ClientConfig, float]] = {}
# key = client_id, value = (ClientConfig, expiry_timestamp)
```

**Fallback on shared DB failure:** If shared Supabase query fails, attempt to serve from stale cache (even if TTL expired) and log a warning. This prevents a shared DB blip from taking down all clients.

---

## 6. Supabase Schema Reference

### Per-client Supabase (one project per client)

**`bookings`**
```sql
CREATE TABLE bookings (
  id                SERIAL PRIMARY KEY,
  booking_id        TEXT UNIQUE NOT NULL,          -- HA-YYYYMMDD-XXXX
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  phone_number      TEXT NOT NULL,
  service_type      TEXT,
  unit_count        TEXT,
  aircon_brand      TEXT,
  slot_date         DATE,
  slot_window       TEXT,                           -- AM or PM
  calendar_event_id TEXT,
  booking_status    TEXT DEFAULT 'Confirmed',
  notes             TEXT
);
```

**`customers`**
```sql
CREATE TABLE customers (
  id                SERIAL PRIMARY KEY,
  phone_number      TEXT UNIQUE NOT NULL,           -- primary key / FK from bookings
  customer_name     TEXT,
  address           TEXT,
  postal_code       TEXT,
  first_seen        TIMESTAMPTZ DEFAULT NOW(),
  last_seen         TIMESTAMPTZ DEFAULT NOW(),
  total_bookings    INTEGER DEFAULT 0,
  escalation_flag   BOOLEAN DEFAULT FALSE,          -- gates agent responses for this customer
  escalation_reason TEXT,
  notes             TEXT
);
```

**`interactions_log`**
```sql
CREATE TABLE interactions_log (
  id            SERIAL PRIMARY KEY,
  timestamp     TIMESTAMPTZ DEFAULT NOW(),
  phone_number  TEXT NOT NULL,
  direction     TEXT NOT NULL,                      -- 'inbound' or 'outbound'
  message_text  TEXT,
  message_type  TEXT DEFAULT 'text'
);
CREATE INDEX ON interactions_log (phone_number);    -- fast lookup per customer
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

**`policies`**
```sql
CREATE TABLE policies (
  id          SERIAL PRIMARY KEY,
  policy_name TEXT UNIQUE NOT NULL,
  policy_text TEXT NOT NULL,
  sort_order  INTEGER DEFAULT 0
);
```

### Shared Flow AI Supabase (one project for all clients)

**`clients`**
```sql
CREATE TABLE clients (
  id                    SERIAL PRIMARY KEY,
  client_id             TEXT UNIQUE NOT NULL,
  display_name          TEXT NOT NULL,
  meta_phone_number_id  TEXT NOT NULL,
  meta_verify_token     TEXT NOT NULL,
  human_agent_number    TEXT NOT NULL,
  google_calendar_id    TEXT,
  timezone              TEXT DEFAULT 'Asia/Singapore',
  is_active             BOOLEAN DEFAULT TRUE,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. Message Logging

Every inbound message is logged before the agent runs. Every outbound reply is logged after sending. The log is append-only.

**File:** `engine/core/message_handler.py` (called from within `handle_inbound_message`)

```python
async def log_interaction(
    db: AsyncClient,
    phone_number: str,
    direction: str,         # 'inbound' or 'outbound'
    message_text: str,
    message_type: str = 'text',
) -> None:
    ...
```

**Supabase INSERT:**
```sql
INSERT INTO interactions_log (phone_number, direction, message_text, message_type, timestamp)
VALUES ($1, $2, $3, $4, NOW())
```

**Ordering in `handle_inbound_message`:**
1. `await log_interaction(db, phone_number, 'inbound', message_text)` — always first, before any gate
2. Agent runs (if not escalated)
3. `await send_message(...)` — sends reply to Meta
4. `await log_interaction(db, phone_number, 'outbound', reply_text)` — after send

**Error handling:** Log failure must not crash the handler. Wrap in try/except and log to application logger. Message delivery takes priority over logging.

---

## 8. Deployment on Railway

### New service: `flow-engine`

Add as a new Railway service in the existing HeyAircon Railway project. n8n and n8n-worker remain running until verification is complete.

### Required env vars on `flow-engine` service

**Shared platform vars (all clients):**

| Env var | Value | Notes |
|---------|-------|-------|
| `SHARED_SUPABASE_URL` | Flow AI shared Supabase URL | For `clients` table lookups |
| `SHARED_SUPABASE_SERVICE_KEY` | Flow AI shared Supabase service key | |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | Observability (planned) |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | Observability (planned) |

**Per-client vars (5 vars per client, `{CLIENT_ID_UPPER}_` prefix):**

| Env var pattern | Example for hey-aircon | Notes |
|---------|----------------------|-------|
| `{CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN` | `HEY_AIRCON_META_WHATSAPP_TOKEN` | Bearer token for Meta API |
| `{CLIENT_ID_UPPER}_SUPABASE_URL` | `HEY_AIRCON_SUPABASE_URL` | Client's Supabase project URL |
| `{CLIENT_ID_UPPER}_SUPABASE_SERVICE_KEY` | `HEY_AIRCON_SUPABASE_SERVICE_KEY` | Client's Supabase service role key |
| `{CLIENT_ID_UPPER}_ANTHROPIC_API_KEY` | `HEY_AIRCON_ANTHROPIC_API_KEY` | Client's Anthropic API key — per-client billing |
| `{CLIENT_ID_UPPER}_OPENAI_API_KEY` | `HEY_AIRCON_OPENAI_API_KEY` | Client's OpenAI API key — per-client fallback billing |

Adding a new client requires these 5 per-client env vars plus an INSERT into the shared `clients` table. No engine changes. No redeploy for non-secret config updates.

### Health check

Railway health check endpoint: `GET /health`

Returns `{"status": "ok"}` with HTTP 200.

Configure Railway health check path to `/health`.

### Deployment status (as of 2026-04-19)

The `flow-engine` service is live in production on Railway. Meta webhook is pointed at:

```
https://flow-ai-production-9296.up.railway.app/webhook/whatsapp/hey-aircon
```

Railway deployment uses Option A: one Railway project per client, single monorepo. All Railway projects track the `release` branch. Promote to release with `git push origin main:release`.

n8n (`n8n` + `n8n-worker` services) is still running but decommission is pending completion of the 48h verification window and resolution of the Google Calendar service account access issue. n8n is not receiving Meta webhooks — the webhook URL is pointed at `flow-engine`.

---

## 9. Testing Strategy

### Unit tests

**Target files:** `engine/tests/unit/`

| Test file | What it tests |
|-----------|-------------|
| `test_context_builder.py` | `build_system_message()` with mock Supabase rows — verify section order, identity block present, policy concatenation |
| `test_escalation_gate.py` | Escalated customer → holding reply + stop; new customer → row created; non-escalated → continues |
| `test_booking_tools.py` | `write_booking()` INSERT + UPSERT; `get_customer_bookings()` SELECT; error handling paths |
| `test_calendar_tools.py` | `check_calendar_availability()` with mock Google Calendar responses; AM/PM window logic |

**Mocking approach:**
- Supabase: mock `AsyncClient` with fixture returning controlled row data
- Google Calendar: mock API responses with `unittest.mock.AsyncMock`
- Meta API: not needed for unit tests (only called from `message_handler`)

### Integration tests

**Target file:** `engine/tests/integration/test_message_handler.py`

**What it tests:** Full `handle_inbound_message()` flow:
1. Normal inbound message → context built → agent called → reply sent → logs written
2. Escalated customer → holding reply → no agent call
3. New customer → row created → agent called
4. Tool use path → booking written to Supabase

**Setup:**
- Real Supabase test project (separate from production — `heyaircon-test`)
- Mock Meta API (`httpx.MockTransport` or `respx` library)
- Real Anthropic SDK calls (use a minimal prompt to keep cost low) OR mock for CI

### E2E test checklist (real WhatsApp — scripted conversation)

Run after traffic cutover to flow-engine. Test with a real WhatsApp test number.

| # | Scenario | Expected outcome |
|---|---------|----------------|
| 1 | Send "Hi, what are your prices for general servicing?" | Agent replies with correct pricing from `config` table |
| 2 | Send "I'd like to book a general servicing for 2 units" | Agent begins booking flow, asks for date and address |
| 3 | Complete booking flow with a free slot | Calendar event created, `bookings` row inserted, confirmation message sent |
| 4 | Send "I want to speak to someone about my booking" | Agent calls `escalate_to_human`, human agent WhatsApp receives notification, `escalation_flag = TRUE` in `customers` |
| 5 | Send another message from escalated number | Holding reply sent, agent does not run, interactions_log shows outbound holding reply |
| 6 | Manually set `escalation_flag = FALSE` in Supabase, send new message | Agent runs normally again |
| 7 | Send a status update payload (simulated via curl) | No processing, `200 OK` returned, no log entry |

---

## 10. Key Design Decisions and Rationale

| Decision | Rationale | Date |
|----------|-----------|------|
| No LangChain | The Claude agent loop for this use case is 20–30 lines of explicit Python. LangChain adds abstraction that obscures tool dispatch, makes debugging harder, and couples the codebase to framework upgrade cycles. Direct Anthropic SDK control over every step. | Apr 2026 |
| Conversation history from `interactions_log`, not a separate memory table | `interactions_log` is already append-only and append-on-every-message. A separate memory table would duplicate data. Fetching last 20 rows by `phone_number` with an index is fast. This simplifies the schema and keeps history in the same place as the audit log. Replaces Railway Postgres chat memory from n8n. | Apr 2026 |
| `BackgroundTasks` over Celery/Redis | At current scale (1 client, low message volume), Celery adds Redis infrastructure overhead with no benefit. FastAPI `BackgroundTasks` runs the handler async in the same process — same pattern as n8n primary/worker split. Revisit at 10+ clients or sustained high volume. | Apr 2026 |
| Hybrid config: `clients` table + Railway env vars | Secrets (`meta_whatsapp_token`, `supabase_service_key`) must not be in a database row readable by any DB credential. Non-secrets (`meta_phone_number_id`, `human_agent_number`) can be in DB for easy update without redeploy. Migration path to a secrets manager is clear at 10–20 clients. | Apr 2026 |
| `clients` table does not store `supabase_service_key` | A service key in a database row creates a circular trust problem — the key used to read the DB is stored in the DB. If the shared Supabase project is compromised, all client databases are exposed. Service keys stay in Railway env vars where they are isolated per-service. | Apr 2026 |
| Escalation gate is hard programmatic, not agent-decided | LLM cannot be trusted to gate its own responses. If the agent decides whether it is escalated, a jailbreak or edge case can bypass the gate. The programmatic check is deterministic and always runs before the agent sees the message. | Apr 2026 |
| Claude Haiku 4.5 as primary LLM; GPT-4o-mini as silent fallback | Haiku 4.5 provides lower cost per conversation and fast response times for structured booking flows. GPT-4o-mini fallback activates per-request when Anthropic API is unreachable — transparent to the customer. Each client is billed separately on their own Anthropic and OpenAI accounts. Model is controlled by `LLM_MODEL` env var — no code change needed to upgrade to Sonnet. | Apr 2026 |
| Add-only calendar writes | Phase 1 scope. All reschedule/cancellation requests go through human escalation. Prevents accidental data loss from agent errors. | Apr 2026 |
| 5-minute TTL cache for `clients` table | Shared DB cannot be a per-request dependency — a shared DB blip must not take down all clients. 5 minutes is short enough that config changes (e.g. adding a new client) propagate quickly while protecting against transient failures. | Apr 2026 |

---

## 11. What Changes from n8n and What Stays the Same

| Layer | n8n | Python engine |
|-------|-----|--------------|
| Webhook receiver | n8n primary service — `POST /webhook/whatsapp-inbound` | FastAPI — `POST /webhook/whatsapp/{client_id}` (multi-client) |
| Async execution | n8n-worker service (separate process) | FastAPI `BackgroundTasks` (same process, async) |
| Escalation gate | `Is Escalated?` IF node | Hard programmatic check in `message_handler.py` before agent |
| Config fetch | `Fetch Config` Postgres node | `build_system_message()` Supabase SELECT |
| Policy fetch | `Fetch Policies` Postgres node | `build_system_message()` Supabase SELECT |
| Context assembly | `Build Context` Code node (JavaScript) | `build_system_message()` Python function |
| LLM | GPT-4o-mini via OpenAI | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) via Anthropic SDK — primary; GPT-4o-mini (OpenAI SDK) silent fallback per-request |
| Conversation memory | Postgres Chat Memory sub-node (Railway Postgres) | `fetch_conversation_history()` from `interactions_log` |
| Tool dispatch | Execute Sub-Workflow trigger | `tool_dispatch` dict of async functions in `agent_runner.py` |
| Booking write | `Tool - Write Booking` sub-workflow | `write_booking()` Supabase INSERT + UPSERT |
| Booking read | `Tool - Get Customer Bookings` sub-workflow | `get_customer_bookings()` Supabase SELECT |
| Calendar check | `Tool - Check Calendar` sub-workflow (pending) | `check_calendar_availability()` Google API |
| Calendar write | `Tool - Create Calendar Event` sub-workflow (pending) | `create_calendar_event()` Google API |
| Escalate tool | `Tool - Escalate to Human` sub-workflow (pending) | `escalate_to_human()` Supabase UPDATE + Meta send |
| Meta API send | HTTP Request node (WA Send Message sub-workflow) | `send_message()` httpx async POST |
| Message logging | `WA Log Interaction` sub-workflow → Supabase INSERT | `log_interaction()` Supabase INSERT |
| Multi-client support | Not supported — one workflow per client | Supported — `client_id` from URL path |
| Client config | n8n env vars (single client) | Hybrid: `clients` table + Railway env vars per client |
| Identity + guardrails | Hardcoded in n8n Build Context Code node | Hardcoded in `build_system_message()` — same rule |
| Business data | `config` + `policies` Supabase tables | Same — no change |
| Supabase schema | Defined in `mvp_scope.md` | Same schema — no changes |
| Calendar write rules | Add only (Phase 1 scope) | Add only — same rule |

---

## 12. Migration Checklist: n8n → Python Engine

Run these steps in order. Do not proceed past a gate until its criteria are met.

### Pre-migration

- [x] Python engine deployed to Railway as `flow-engine` service
- [x] `GET /health` returns `200 OK`
- [x] All Railway env vars set on `flow-engine` (see Section 8)
- [x] `clients` table populated with HeyAircon row in shared Supabase
- [x] Unit tests passing: `pytest engine/tests/unit/`

### Parallel test (no traffic change)

- [ ] Send test messages directly to `flow-engine` via curl (bypassing Meta)
- [ ] Verify `interactions_log` contains correct inbound + outbound rows
- [ ] Verify `bookings` table writes correctly on booking flow
- [ ] Verify `customers` table UPSERT works for new and returning customers
- [ ] Verify escalation flag is set and holding reply is sent
- [ ] Verify Google Calendar event is created
- [ ] Integration tests passing: `pytest engine/tests/integration/`

### **GATE 1:** Parallel test complete
Criteria: All parallel test cases pass with no errors in Railway `flow-engine` logs.

---

### Traffic cutover

- [x] Update Meta Developer Portal webhook URL to `flow-engine` Railway URL: `https://flow-ai-production-9296.up.railway.app/webhook/whatsapp/hey-aircon`
- [x] Verify Meta GET verification handshake completes (check Railway logs for 200 on GET)
- [x] Send a real WhatsApp test message and confirm response

### **GATE 2:** Live traffic verified
Criteria: At least 5 real WhatsApp messages processed end-to-end through `flow-engine` with correct responses and all Supabase rows written correctly.

---

### Verification period (48h minimum)

- [ ] Monitor Railway `flow-engine` logs for errors — zero error rate target
- [ ] Check `interactions_log` — every inbound message has a corresponding outbound reply
- [ ] Check `bookings` table — all test bookings written correctly
- [ ] Confirm n8n is NOT receiving webhooks (Meta webhook URL already pointed at Python)
- [ ] Run E2E test checklist (Section 9) end-to-end

### **GATE 3:** 48h verification passed
Criteria: 48h of real traffic with no processing failures, all E2E test scenarios pass.

---

### n8n decommission (blocked — awaiting 48h verification + Google Calendar fix)

- [ ] Google Calendar service account access confirmed working end-to-end
- [ ] Export all n8n workflow JSONs as backup archive
- [ ] Stop `n8n` and `n8n-worker` Railway services
- [ ] Move n8n build docs to `clients/hey-aircon/plans/build/archive/` (do not delete)
- [ ] Update `CLAUDE.md` migration status
- [ ] Update `clients/hey-aircon/plans/build/00_architecture_reference.md` header: "Archived — migrated to Python engine April 2026. Reference: `docs/architecture/00_platform_architecture.md`"

---

## Appendix A: Meta Webhook Payload Reference

### Inbound message payload (POST body structure)

```json
{
  "entry": [{
    "changes": [{
      "value": {
        "messages": [{
          "from": "<phone_number>",
          "text": { "body": "<message_text>" },
          "type": "text",
          "id": "<message_id>",
          "timestamp": "..."
        }],
        "contacts": [{
          "profile": { "name": "<display_name>" },
          "wa_id": "<wa_id>"
        }]
      }
    }]
  }]
}
```

### Status update payload (guard against this — no `messages` key)

```json
{
  "entry": [{
    "changes": [{
      "value": {
        "statuses": [{ "status": "delivered", ... }]
      }
    }]
  }]
}
```

**Guard:** `if "messages" not in body["entry"][0]["changes"][0]["value"]: return 200 OK`

### Meta send message request

```
POST https://graph.facebook.com/v19.0/{META_PHONE_NUMBER_ID}/messages
Authorization: Bearer {META_WHATSAPP_TOKEN}
Content-Type: application/json

{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "<phone_number>",
  "type": "text",
  "text": { "body": "<message_text>" }
}
```

**Note on special characters:** The `text.body` field must be a valid JSON string. Use the `httpx` JSON serialisation (pass `json=payload` not `content=json.dumps(payload)`) — this handles newlines and special characters automatically. Replicates the n8n "Using Fields Below" fix for the same issue.
