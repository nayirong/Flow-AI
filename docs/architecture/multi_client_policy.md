# Flow AI — Multi-Client Management Policy

**Last Updated:** 2026-04-28
**Status:** Canonical Reference — Authoritative
**Replaces:** Scattered client management decisions across `AGENTS.md`, `CLAUDE.md`, and architecture docs

---

## 1. Overview & Principles

### What Multi-Client Means

Flow AI operates a **single monorepo engine** that serves **N independent clients** simultaneously. Each client is a service SME (HeyAircon, Flow AI itself, etc.) running their own AI agent for WhatsApp customer engagement. The engine receives inbound messages for all clients via distinct webhook URLs, processes each message in isolation, and maintains absolute data separation between clients.

**Key property:** Client A's data, configuration, LLM keys, and database connections are architecturally isolated from Client B. No code path exists where Client A's agent can read or write Client B's customer data.

### Core Design Principles

| Principle | Meaning |
|-----------|---------|
| **Client-agnostic engine** | Zero client-specific logic inside `engine/`. All client behaviour is loaded at runtime from config. |
| **Config-driven isolation** | Client identity (`client_id`) is the routing key. All client-specific state is keyed by `client_id` in Supabase or Railway env vars. |
| **One engine, many clients** | A single deployed service handles all clients. Adding a new client requires no code changes and no redeployment (unless secrets are Railway-managed — see deployment model). |
| **Supabase separation** | Each client has their own Supabase project containing customer PII, conversation history, bookings, and business data. The shared Flow AI Supabase contains only the `clients` table and platform-level observability tables (`api_usage`, `api_incidents`). |
| **Per-client billing** | Each client brings their own Anthropic and OpenAI API keys. LLM usage is billed to the client's account, not Flow AI's. |
| **Zero cross-client data access** | No tool, agent, or database query can read or write data across client boundaries. Isolation is enforced by per-request database connection instantiation and tool closure injection. |

### The Contract: Shared vs Isolated

| Layer | Shared | Isolated (per client) |
|-------|--------|----------------------|
| **Codebase** | `engine/` Python code, tests, architecture docs | `clients/{client_id}/` — context, product docs, plans, knowledge base |
| **Database** | Flow AI Supabase (`flowai-platform`) — `clients`, `api_usage`, `api_incidents` | Per-client Supabase project — `customers`, `interactions_log`, `bookings`, `config`, `policies`, `escalation_tracking` |
| **LLM keys** | None (all per-client) | `{CLIENT_ID_UPPER}_ANTHROPIC_API_KEY`, `{CLIENT_ID_UPPER}_OPENAI_API_KEY` from Railway env vars |
| **Deployment** | Railway service code (from `release` branch) | Railway project per client (env vars, webhook URL, watch paths) |
| **Observability** | Shared `api_usage` and `api_incidents` tables log all LLM calls and failures across clients | Per-client `interactions_log` contains full conversation history |

---

## 2. Client Identity & Naming

### `client_id` — The Routing Key

Every client is identified by a unique `client_id` string:
- **Format:** Lowercase, hyphenated (e.g., `hey-aircon`, `flow-ai`, `acme-corp`)
- **Usage:** Webhook URL path parameter, Supabase primary key, config cache key, Railway project name prefix, directory name under `clients/`
- **Immutability:** Once set, `client_id` never changes. Renaming a client requires a full migration (new Supabase project, new Railway project, new webhook registration).

### `client_id_upper` — Env Var Namespacing

All per-client environment variables use an uppercase, underscored variant:
- **Transformation:** `hey-aircon` → `HEY_AIRCON`, `flow-ai` → `FLOW_AI`
- **Pattern:** `{CLIENT_ID_UPPER}_{SECRET_NAME}`
- **Examples:**
  - `HEY_AIRCON_META_WHATSAPP_TOKEN`
  - `FLOW_AI_SUPABASE_URL`
  - `ACME_CORP_ANTHROPIC_API_KEY`

### Client Registry — `.flow/config.yaml`

The `.flow/config.yaml` file is the master index of all clients in the workspace:

```yaml
clients:
  hey-aircon:
    path: clients/hey-aircon
    context: clients/hey-aircon/context.md
    product: clients/hey-aircon/product
    knowledge_base: clients/hey-aircon/product/knowledge
    persona: clients/hey-aircon/product/persona.md
  flow-ai:
    path: clients/flow-ai
    context: clients/flow-ai/context.md
    product: clients/flow-ai/product
    knowledge_base: clients/flow-ai/product/knowledge
    persona: clients/flow-ai/product/persona.md
```

**Purpose:** Workspace-level reference for documentation and agent orchestration. Not used by the runtime engine (engine reads from Supabase `clients` table).

### Shared Supabase `clients` Table

The `clients` table in the shared Flow AI Supabase project (`flowai-platform`) is the runtime registry:

```sql
CREATE TABLE clients (
    id BIGSERIAL PRIMARY KEY,
    client_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    meta_phone_number_id TEXT NOT NULL,
    meta_verify_token TEXT NOT NULL,
    human_agent_number TEXT NOT NULL,
    google_calendar_id TEXT,
    timezone TEXT DEFAULT 'Asia/Singapore',
    is_active BOOLEAN DEFAULT TRUE,
    sheets_sync_enabled BOOLEAN DEFAULT FALSE,
    sheets_spreadsheet_id TEXT,
    sheets_service_account_creds JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Key rule:** `is_active = TRUE` is required for the engine to process messages for that client. Setting `is_active = FALSE` immediately stops message processing (soft deactivation).

---

## 3. Data Isolation Architecture

### Two-Tier Database Model

Flow AI uses a **shared/per-client split** for data storage:

#### Shared Supabase — `flowai-platform`

**Purpose:** Platform-level registry and observability.

**Tables:**

| Table | Contents | Access |
|-------|----------|--------|
| `clients` | Client registry (non-sensitive config fields) | Engine reads on every inbound message (cached 5 min) |
| `api_usage` | LLM token usage log (all clients, all models) | Engine writes after every successful LLM call |
| `api_incidents` | LLM provider failures (timeout, 5xx, rate limit) | Engine writes on Anthropic/OpenAI failure |

**Connection:** Created by `get_shared_db()` in `engine/integrations/supabase_client.py` using `SHARED_SUPABASE_URL` and `SHARED_SUPABASE_SERVICE_KEY` (platform-level env vars).

#### Per-Client Supabase — `{client-name}-crm`

**Purpose:** All customer PII, conversation history, bookings, and business knowledge.

**Tables:**

| Table | Contents |
|-------|----------|
| `customers` | Phone number, name, address, escalation state, lead scoring (if applicable) |
| `interactions_log` | Full conversation history (inbound + outbound messages) |
| `bookings` | Confirmed bookings (service type, date, slot, address, calendar event ID) |
| `config` | Agent knowledge base (services, pricing, hours, Calendly link) — fetched by context builder |
| `policies` | Escalation triggers, routing rules, agent behavioural constraints — fetched by context builder |
| `escalation_tracking` | Escalation event log (alert message ID, resolved timestamp, resolved by) |

**Connection:** Created by `get_client_db(client_id)` in `engine/integrations/supabase_client.py` using `{CLIENT_ID_UPPER}_SUPABASE_URL` and `{CLIENT_ID_UPPER}_SUPABASE_SERVICE_KEY` (per-client env vars).

**Hard rule:** `get_client_db()` instantiates a fresh `AsyncClient` on every call — no connection pooling across clients. This ensures client A's database handle cannot be accidentally reused for client B.

### Cross-Client Data Access Guarantee

**Architectural enforcement points:**

1. **Webhook routing:** `client_id` is extracted from the URL path (`/webhook/whatsapp/{client_id}`) and passed through every function in the pipeline. No global state.
2. **Per-request config:** `load_client_config(client_id)` fetches the client's config at the start of `handle_inbound_message()`. Config is cached per `client_id` key (see cache assertion guard below).
3. **Per-request DB connection:** `get_client_db(client_id)` constructs a new Supabase client using that client's env vars. No shared connection pool.
4. **Tool closure injection:** `build_tool_dispatch(db, client_config, phone_number)` injects the per-client `db` and `client_config` into tool closures. Tools receive only their client's database handle — no access to other clients' databases.
5. **LLM key isolation:** Each client's `anthropic_api_key` and `openai_api_key` are loaded from `{CLIENT_ID_UPPER}_*` env vars and passed to the agent runner. No shared API key — each client is billed on their own Anthropic/OpenAI account.

**Data that must never cross client boundaries:**
- Customer phone numbers, names, addresses, conversation history
- Booking data (dates, services, locations)
- Agent knowledge base (`config`, `policies` tables)
- Escalation state and tracking
- LLM API keys (Anthropic, OpenAI)
- Meta WhatsApp tokens
- Supabase credentials

---

## 4. Configuration Model

### Hybrid Config Approach

Client configuration is split across two storage layers: **non-sensitive fields in shared Supabase** and **sensitive secrets in Railway env vars**.

#### Non-Sensitive Fields (Shared Supabase `clients` Table)

| Field | Type | Description |
|-------|------|-------------|
| `client_id` | `TEXT` | Unique client identifier (primary key) |
| `display_name` | `TEXT` | Human-readable client name |
| `meta_phone_number_id` | `TEXT` | Meta WhatsApp phone number ID |
| `meta_verify_token` | `TEXT` | Meta webhook verification token (generated once, static) |
| `human_agent_number` | `TEXT` | WhatsApp number for escalation alerts (E.164 format) |
| `google_calendar_id` | `TEXT` | Google Calendar ID for booking events (nullable if no booking flow) |
| `timezone` | `TEXT` | Client timezone (IANA, e.g. `Asia/Singapore`) |
| `is_active` | `BOOLEAN` | Soft activation flag — `FALSE` stops all message processing |
| `sheets_sync_enabled` | `BOOLEAN` | Enable Google Sheets sync for CRM visibility |
| `sheets_spreadsheet_id` | `TEXT` | Google Sheets spreadsheet ID (if sync enabled) |
| `sheets_service_account_creds` | `JSONB` | Google service account credentials JSON (if sync enabled) |

**Update workflow:** Edit row in Supabase Studio → changes take effect within 5 minutes (cache TTL). No redeploy required.

#### Sensitive Secrets (Railway Env Vars)

Each client requires **5 environment variables** in Railway:

| Env Var | Purpose |
|---------|---------|
| `{CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN` | Meta Cloud API access token |
| `{CLIENT_ID_UPPER}_SUPABASE_URL` | Client's Supabase project URL |
| `{CLIENT_ID_UPPER}_SUPABASE_SERVICE_KEY` | Client's Supabase service role key |
| `{CLIENT_ID_UPPER}_ANTHROPIC_API_KEY` | Client's Anthropic API key (per-client billing) |
| `{CLIENT_ID_UPPER}_OPENAI_API_KEY` | Client's OpenAI API key (per-client billing for fallback) |

**Update workflow:** Update env var in Railway dashboard → triggers redeploy for that Railway project only.

### `ClientConfig` Dataclass

`engine/config/client_config.py` defines the `ClientConfig` dataclass, which merges both sources:

```python
@dataclass
class ClientConfig:
    client_id: str
    display_name: str
    meta_phone_number_id: str
    meta_verify_token: str
    meta_whatsapp_token: str              # from env
    human_agent_number: str
    google_calendar_id: str | None
    google_calendar_creds: dict           # from env
    supabase_url: str                     # from env
    supabase_service_key: str             # from env
    anthropic_api_key: str                # from env
    openai_api_key: str                   # from env
    timezone: str
    is_active: bool
    sheets_sync_enabled: bool
    sheets_spreadsheet_id: str | None
    sheets_service_account_creds: dict | None
```

**Construction logic (in `load_client_config()`):**
1. Query shared Supabase `clients` table by `client_id` where `is_active = TRUE`
2. Raise `ClientNotFoundError` if no row found or `is_active = FALSE`
3. Load 5 secrets from Railway env vars using `{CLIENT_ID_UPPER}_*` pattern
4. Raise `ClientConfigError` if any required env var is missing
5. Construct `ClientConfig` dataclass merging both sources
6. Cache with 5-minute TTL (see cache section below)

### TTL Cache — 5-Minute In-Process Cache

**Location:** `engine/config/client_config.py` — module-level dict `_cache`

**Structure:**
```python
_cache: Dict[str, Tuple[ClientConfig, float]] = {}
# Key: client_id
# Value: (ClientConfig, expiry_timestamp)
```

**TTL:** `CACHE_TTL_SECONDS = 300` (5 minutes)

**Cache hit logic:**
1. Check if `client_id` exists in `_cache` and `now < expiry`
2. **Defensive assertion (as of 2026-04-27):** `assert config.client_id == client_id` on every cache hit. If the cached config has a different `client_id` than the cache key, raise `AssertionError` immediately. This catches cache corruption bugs before they cause cross-client data leakage.
3. Return cached `ClientConfig` if assertion passes
4. On cache miss or expiry: query Supabase + load env vars, construct fresh `ClientConfig`, cache with new expiry

**Why cached:** Shared Supabase `clients` table is a central dependency — cannot be a per-request blocking query. Cache reduces latency and Supabase query load.

**Why 5-minute TTL:** Balances config update responsiveness (non-secret changes take effect within 5 minutes) and cache hit rate (most clients send messages more frequently than every 5 minutes).

### Config Update Workflows

| Change Type | Storage Location | Update Process | Redeploy Required? |
|-------------|------------------|----------------|-------------------|
| Non-secret field (e.g., `human_agent_number`, `timezone`) | Shared Supabase `clients` table | UPDATE row in Supabase Studio | No — cache expires within 5 min |
| Secret (e.g., `META_WHATSAPP_TOKEN`, `ANTHROPIC_API_KEY`) | Railway env vars | Update env var in Railway dashboard | Yes — Railway triggers redeploy |
| Add new client | Both | INSERT into `clients` table + add 5 env vars | Yes — env var change triggers redeploy |
| Deactivate client | Shared Supabase `clients` table | SET `is_active = FALSE` | No — cache expires within 5 min, then `ClientNotFoundError` on next message |

---

## 5. Deployment Model

### Railway — One Project Per Client

Flow AI uses **Railway Option A** (decided 2026-04-18):
- **One Railway account** hosts N Railway projects (not one Railway account per client)
- **Each client = one Railway project** with its own:
  - Service name (e.g., `hey-aircon-agent`, `flow-ai-agent`)
  - Environment variables (5 per client + shared platform vars)
  - Deploy history and logs
  - Public webhook URL
- **All Railway projects connect to the same GitHub monorepo** (`flow-ai`)
- **No per-client engine code:** Nothing inside `engine/` imports from `clients/`. One-directional dependency.

### Branch Strategy

**Tracked branch:** All Railway projects track the `release` branch, **not** `main`.

**Rationale:**
- Develop and merge freely on `main` without triggering production deploys
- Explicitly promote to `release` when ready to deploy to all clients: `git push origin main:release`
- For per-client testing before full rollout: temporarily change that Railway project's tracked branch to a feature branch, deploy, verify, then switch back to `release`
- Controlled blast radius: a bad merge to `main` does not immediately affect production until explicitly promoted to `release`

**Manual deploy toggle:** Railway allows disabling auto-deploy and switching to manual deploys. Use this if stricter per-client rollout control is needed at scale (10+ clients).

### Watch Paths

**Setting:** Each Railway project has `Watch Paths` set to `engine/` only.

**Effect:**
- Changes to `engine/**` trigger a redeploy
- Changes to `docs/`, `clients/`, `.flow/`, `README.md` do NOT trigger a redeploy
- Reduces unnecessary deploys when updating non-engine files

**Where to configure:** Railway dashboard → Project → Settings → Deploy → Watch Paths

### Deployment Scope

**When `release` branch is updated:** All active Railway projects receive the new code simultaneously.

**Acceptable for:** Engine bug fixes, new tools, performance improvements, platform-level changes (all clients benefit from engine upgrades).

**Not acceptable for:** Per-client A/B testing, client-specific feature flags, breaking changes that need gradual rollout.

**Mitigation for gradual rollout:** Deploy to a single Railway project first by switching that project's tracked branch to the feature branch, verify, then merge to `release` for full rollout.

### Adding a New Client — Deployment Checklist

When adding a new client, the deployment sequence is:

1. **INSERT into shared `clients` table** (Supabase Studio)
2. **Create new Railway project** — name: `{client-id}-agent` (e.g., `acme-corp-agent`)
3. **Set Railway project settings:**
   - Tracked branch: `release`
   - Watch paths: `engine/`
   - Start command: `uvicorn engine.api.webhook:app --host 0.0.0.0 --port $PORT`
4. **Add Railway env vars:**
   - `{CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN`
   - `{CLIENT_ID_UPPER}_SUPABASE_URL`
   - `{CLIENT_ID_UPPER}_SUPABASE_SERVICE_KEY`
   - `{CLIENT_ID_UPPER}_ANTHROPIC_API_KEY`
   - `{CLIENT_ID_UPPER}_OPENAI_API_KEY`
   - **Shared platform vars:** `SHARED_SUPABASE_URL`, `SHARED_SUPABASE_SERVICE_KEY`, `LOG_LEVEL` (copy from existing project)
5. **Deploy** — Railway auto-deploys on first env var addition
6. **Copy Railway public URL** (e.g., `https://acme-corp-agent.railway.app`)
7. **Register Meta webhook:**
   - URL: `https://acme-corp-agent.railway.app/webhook/whatsapp/acme-corp`
   - Verify token: value from `meta_verify_token` in `clients` table
   - Subscribe to: `messages`
8. **Verify end-to-end:** Send test message → check Railway logs → verify Supabase write

---

## 6. Runtime Isolation Guarantees

As of 2026-04-27, the engine implements **code-level isolation mechanisms** to prevent cross-client data leakage:

### Isolation Guarantee 1: Config Cache Assertion

**File:** `engine/config/client_config.py`

**Mechanism:** On every cache hit, the engine asserts that the cached `ClientConfig.client_id` matches the requested `client_id`:

```python
if client_id in _cache:
    config, expiry = _cache[client_id]
    if now < expiry:
        assert config.client_id == client_id, (
            f"Cache key mismatch: expected '{client_id}', got '{config.client_id}'. "
            "Cache is corrupted — this is a bug, not a client error."
        )
        return config
```

**Purpose:** If a cache corruption bug causes client A's config to be stored under client B's cache key, the assertion raises `AssertionError` immediately. The engine crashes loudly rather than silently serving one client's config (including database credentials and LLM keys) to another client.

**Test:** `engine/tests/integration/test_concurrent_clients.py::test_cache_assertion_raises_on_mismatch`

### Isolation Guarantee 2: Post-Load Mismatch Guard

**File:** `engine/core/message_handler.py`

**Mechanism:** After `load_client_config(client_id)` returns, `message_handler.py` validates that `client_config.client_id == client_id`. If mismatch, log critical error and abort:

```python
client_config = await load_client_config(client_id)
if client_config.client_id != client_id:
    logger.critical(
        f"Config mismatch: requested '{client_id}', received '{client_config.client_id}'. "
        "Aborting pipeline to prevent cross-client data access."
    )
    return
```

**Purpose:** Defense-in-depth check that catches cache corruption or config loading bugs before any database operation or agent invocation.

### Isolation Guarantee 3: Per-Client Error Boundary

**File:** `engine/core/message_handler.py`

**Mechanism:** `handle_inbound_message()` is wrapped in a try-except at the outer level. Any unhandled exception in client A's pipeline is caught, logged, and absorbed. Client B's concurrent pipeline is unaffected.

**Effect:** A crash in one client's tool execution, LLM call, or database query does not bring down the entire service or leak into another client's request.

**Test:** `engine/tests/integration/test_concurrent_clients.py::test_client_exception_does_not_affect_other_client`

### Isolation Guarantee 4: Per-Client DB Connection

**File:** `engine/integrations/supabase_client.py`

**Mechanism:** `get_client_db(client_id)` constructs a fresh Supabase `AsyncClient` on every call using `{CLIENT_ID_UPPER}_SUPABASE_URL` and `{CLIENT_ID_UPPER}_SUPABASE_SERVICE_KEY` from env vars. No connection pooling. No global shared client.

```python
async def get_client_db(client_id: str) -> AsyncClient:
    config = await load_client_config(client_id)
    return await create_async_client(
        supabase_url=config.supabase_url,
        supabase_key=config.supabase_service_key,
    )
```

**Guarantee:** Each `db` handle returned by `get_client_db(client_id)` connects only to that client's Supabase project. Passing client A's `db` handle to client B's pipeline is architecturally impossible — each pipeline constructs its own `db` from its own `client_id`.

### Isolation Guarantee 5: Tool Dispatch Closure Injection

**File:** `engine/core/tools/__init__.py`

**Mechanism:** `build_tool_dispatch(db, client_config, phone_number)` returns a dict mapping tool names to closures. Each closure captures the per-request `db`, `client_config`, and `phone_number`:

```python
def build_tool_dispatch(db: AsyncClient, client_config: ClientConfig, phone_number: str):
    return {
        "write_booking": lambda **kwargs: write_booking(db=db, client_config=client_config, phone_number=phone_number, **kwargs),
        "get_customer_bookings": lambda **kwargs: get_customer_bookings(db=db, phone_number=phone_number, **kwargs),
        "escalate_to_human": lambda **kwargs: escalate_to_human(db=db, client_config=client_config, phone_number=phone_number, **kwargs),
        "check_calendar_availability": lambda **kwargs: check_calendar_availability(client_config=client_config, **kwargs),
    }
```

**Guarantee:** When Claude calls a tool, it receives only the `db` and `client_config` that were injected for its client. Tools have no access to other clients' databases or configurations.

### Isolation Guarantee 6: LLM Key Isolation

**File:** `engine/core/agent_runner.py`

**Mechanism:** Each client's Anthropic and OpenAI API keys are loaded from `{CLIENT_ID_UPPER}_ANTHROPIC_API_KEY` and `{CLIENT_ID_UPPER}_OPENAI_API_KEY` env vars, passed as parameters to `run_agent()`, and used to construct client-specific SDK instances:

```python
anthropic_client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)
openai_client = AsyncOpenAI(api_key=openai_api_key)
```

**Guarantee:** Each client's LLM usage is billed to their own Anthropic/OpenAI account. No shared API key. No cross-client billing.

### Per-Customer Concurrency Lock

**File:** `engine/core/message_handler.py`

**Mechanism:** A per-phone-number `asyncio.Lock` serializes agent invocations for the same customer across all clients:

```python
_customer_locks: dict[str, asyncio.Lock] = {}

async def handle_inbound_message(...):
    lock = _get_customer_lock(phone_number)
    async with lock:
        # All processing happens inside the lock
        ...
```

**Purpose:** Prevents race conditions when a customer sends multiple messages in rapid succession. Without this, concurrent background tasks could read stale conversation history and produce duplicate or conflicting responses.

**Scope:** Lock key is `phone_number` (not `client_id + phone_number`). If two different clients happen to serve the same phone number (edge case), the lock serializes them globally. Acceptable trade-off for correctness.

---

## 7. Adding a New Client — Step-by-Step Runbook

This is the complete operational checklist for onboarding a new client. Any engineer can execute this.

### Step 1: Define `client_id`

**Naming rules:**
- Lowercase
- Hyphenated (no underscores, spaces, or capital letters)
- Derived from business name: "Acme Corporation" → `acme-corp`
- Unique across all clients

**Generate `client_id_upper`:** `acme-corp` → `ACME_CORP`

### Step 2: Scaffold Client Directory

From the workspace root, run:

```bash
bash .flow/scripts/new-client.sh <client-id> "<Client Display Name>"
```

**Example:**
```bash
bash .flow/scripts/new-client.sh acme-corp "Acme Corporation"
```

**Output:**
```
clients/acme-corp/
├── context.md
├── product/
│   ├── PRD.md
│   ├── persona.md
│   └── knowledge/
│       ├── pricing.md
│       ├── hours.md
│       ├── services/
│       ├── policies/
│       └── faqs/
└── plans/
    └── architecture.md
```

### Step 3: Register in `.flow/config.yaml`

Add the new client entry under `clients:`:

```yaml
clients:
  acme-corp:
    path: clients/acme-corp
    context: clients/acme-corp/context.md
    product: clients/acme-corp/product
    knowledge_base: clients/acme-corp/product/knowledge
    persona: clients/acme-corp/product/persona.md
```

Commit and push to `main`.

### Step 4: Provision Per-Client Supabase Project

1. **Create new Supabase project** — name: `acme-corp-crm`
2. **Region:** Singapore/Southeast Asia (for PDPA compliance)
3. **Run SQL migrations** (in order):

```sql
-- Table: customers
CREATE TABLE customers (
    id BIGSERIAL PRIMARY KEY,
    phone_number TEXT UNIQUE NOT NULL,
    customer_name TEXT,
    address TEXT,
    postal_code TEXT,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    escalation_flag BOOLEAN DEFAULT FALSE,
    escalation_reason TEXT,
    escalation_notified BOOLEAN DEFAULT FALSE,
    total_bookings INTEGER DEFAULT 0
);
CREATE INDEX idx_customers_phone ON customers(phone_number);

-- Table: interactions_log
CREATE TABLE interactions_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    phone_number TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    message_text TEXT,
    message_type TEXT DEFAULT 'text',
    message_id TEXT,
    channel TEXT DEFAULT 'whatsapp' CHECK (channel IN ('whatsapp', 'widget'))
);
CREATE INDEX idx_interactions_phone ON interactions_log(phone_number);
CREATE INDEX idx_interactions_timestamp ON interactions_log(timestamp);

-- Table: bookings (if client has booking flow)
CREATE TABLE bookings (
    id BIGSERIAL PRIMARY KEY,
    booking_id TEXT UNIQUE NOT NULL,
    phone_number TEXT NOT NULL,
    service_type TEXT NOT NULL,
    unit_count INTEGER,
    slot_date DATE NOT NULL,
    slot_window TEXT NOT NULL CHECK (slot_window IN ('AM', 'PM')),
    address TEXT NOT NULL,
    postal_code TEXT,
    calendar_event_id TEXT,
    booking_status TEXT DEFAULT 'Confirmed',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_bookings_phone ON bookings(phone_number);

-- Table: config
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table: policies
CREATE TABLE policies (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table: escalation_tracking
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

4. **Seed `config` table** with client knowledge base:

```sql
INSERT INTO config (key, value, sort_order) VALUES
    ('agent_name', '[Client Agent Name]', 10),
    ('business_name', '[Client Business Name]', 20),
    ('services', '[Comma-separated service list]', 30),
    ('pricing_general', '[Pricing info]', 40),
    ('appointment_window_am', '9:00 AM - 1:00 PM', 50),
    ('appointment_window_pm', '2:00 PM - 6:00 PM', 60),
    ('booking_lead_time_days', '2', 70);
```

5. **Seed `policies` table** with escalation rules:

```sql
INSERT INTO policies (key, value, sort_order) VALUES
    ('escalation_triggers', 'Customer frustrated; requests immediate callback; technical issue outside agent scope', 10),
    ('cancellation_policy', '[Client cancellation terms]', 20);
```

6. **Copy Supabase URL and service key** from project settings.

### Step 5: Insert into Shared `clients` Table

In the shared Flow AI Supabase Studio (`flowai-platform` project), run:

```sql
INSERT INTO clients (
    client_id,
    display_name,
    meta_phone_number_id,
    meta_verify_token,
    human_agent_number,
    google_calendar_id,
    timezone,
    is_active
) VALUES (
    'acme-corp',
    'Acme Corporation',
    '[Meta Phone Number ID from Meta Business Manager]',
    '[Generate random 32-char string for verify token]',
    '[Human agent WhatsApp in E.164 format, e.g., +6591234567]',
    '[Google Calendar ID if booking flow enabled, else NULL]',
    'Asia/Singapore',
    TRUE
);
```

### Step 6: Create Railway Project

1. **Create new Railway project** — name: `acme-corp-agent`
2. **Link to GitHub repo:** `flow-ai`
3. **Set tracked branch:** `release` (not `main`)
4. **Set Watch Paths:** `engine/`
5. **Set start command:** `uvicorn engine.api.webhook:app --host 0.0.0.0 --port $PORT`

### Step 7: Add Railway Env Vars

In Railway dashboard for `acme-corp-agent`, add:

**Per-client secrets:**

| Variable | Value |
|----------|-------|
| `ACME_CORP_META_WHATSAPP_TOKEN` | From Meta Business Manager → WhatsApp → API Setup |
| `ACME_CORP_SUPABASE_URL` | From `acme-corp-crm` Supabase project settings |
| `ACME_CORP_SUPABASE_SERVICE_KEY` | From `acme-corp-crm` Supabase project settings (service_role key) |
| `ACME_CORP_ANTHROPIC_API_KEY` | From client's Anthropic account (or Flow AI's if client doesn't have one) |
| `ACME_CORP_OPENAI_API_KEY` | From client's OpenAI account (or Flow AI's if client doesn't have one) |

**Shared platform vars (copy from existing project):**

| Variable | Value |
|----------|-------|
| `SHARED_SUPABASE_URL` | Shared Flow AI Supabase URL |
| `SHARED_SUPABASE_SERVICE_KEY` | Shared Flow AI Supabase service key |
| `LOG_LEVEL` | `INFO` |

Railway auto-deploys after env vars are added.

### Step 8: Register Meta Webhook

1. **Copy Railway public URL** from Railway dashboard (e.g., `https://acme-corp-agent.railway.app`)
2. **In Meta Business Manager:**
   - Go to: WhatsApp → Configuration → Webhook
   - Callback URL: `https://acme-corp-agent.railway.app/webhook/whatsapp/acme-corp`
   - Verify token: value from `meta_verify_token` in `clients` table
   - Subscribe to: `messages`
   - Click "Verify and Save"
3. **Verify webhook passes:** Meta sends GET request, Railway returns `hub.challenge`, Meta confirms with green checkmark.

### Step 9: Verify End-to-End

Send a test message from a WhatsApp number to the client's WhatsApp Business number:

- [ ] Railway logs show `Inbound message received for client 'acme-corp'`
- [ ] Shared Supabase `api_usage` table receives a new row with `client_id='acme-corp'`
- [ ] Per-client Supabase `interactions_log` receives 2 rows (1 inbound, 1 outbound)
- [ ] Test phone receives agent reply
- [ ] Per-client Supabase `customers` table receives 1 row with test phone number

If all checks pass, client is live.

---

## 8. Client Offboarding

### Soft Deactivation (Recommended)

1. **Set `is_active = FALSE`** in shared Supabase `clients` table:
   ```sql
   UPDATE clients SET is_active = FALSE WHERE client_id = 'acme-corp';
   ```
2. **Effect:** Within 5 minutes (cache TTL), all inbound messages for that client return `ClientNotFoundError` and are dropped. Railway service remains running, but no messages are processed.
3. **Reversible:** Set `is_active = TRUE` to re-enable.

### Hard Teardown

1. **Deregister Meta webhook:**
   - Meta Business Manager → WhatsApp → Configuration → Webhook
   - Change URL to a dummy URL or delete subscription
2. **Delete Railway project:** `acme-corp-agent`
3. **Remove Railway env vars:** All 5 `ACME_CORP_*` env vars (if Railway project is deleted, this is automatic)
4. **Archive or delete per-client Supabase project:** `acme-corp-crm`
   - **Data retention policy:** See Section 10 (compliance). Default: keep project paused for 90 days, then delete.
5. **DELETE from shared `clients` table:**
   ```sql
   DELETE FROM clients WHERE client_id = 'acme-corp';
   ```
6. **Archive client directory:** Move `clients/acme-corp/` to `clients/_archived/acme-corp/`

---

## 9. Multi-Channel Considerations (Forward-Looking)

### Current State: WhatsApp Only

As of 2026-04-28, all clients use the **WhatsApp channel** exclusively. The engine receives messages from Meta Cloud API and replies via Meta Cloud API.

### Planned: Chat Widget Channel (Track 3 — Phase 1 MVP Approved 2026-04-28)

**Vision:** Clients can embed a Flow AI chat widget on their website. Customers interact with the same agent via the widget instead of (or in addition to) WhatsApp.

**Architecture (planned):**
- New route: `POST /webhook/widget/{client_id}` receives inbound widget messages
- Widget backend uses WebSocket or Server-Sent Events for real-time bidirectional communication
- `interactions_log.channel` field distinguishes `whatsapp` vs `widget`
- Same agent, same tools, same Supabase tables — only the transport layer differs

**Multi-channel per client:** A client can have:
- WhatsApp only
- Widget only
- Both WhatsApp and Widget (same agent, shared conversation history keyed by `phone_number` for WhatsApp, `session_id` for Widget)

**Config flags (planned):**
- `whatsapp_enabled` (boolean in `clients` table)
- `widget_enabled` (boolean in `clients` table)

### Cross-Channel Identity (Phase 3 Concern — Not Yet Implemented)

**Problem:** If a customer messages via WhatsApp and later returns via the website widget, how does the agent recognize them as the same person?

**Approaches under consideration:**
1. **Phone number re-entry:** Widget prompts for phone number on first message → matches against `customers.phone_number`
2. **Email-based identity:** Widget collects email → new `customers.email` field → join on email
3. **No cross-channel identity:** Treat WhatsApp and Widget as separate customer profiles (simpler, acceptable for Phase 1)

**Decision:** Deferred to Phase 3. Phase 1 and Phase 2 assume no cross-channel identity linking.

---

## 10. Compliance & Data Governance

### Applicable Framework

**Primary jurisdiction:** Singapore
**Compliance framework:** **Personal Data Protection Act (PDPA) Singapore**

All clients are assumed to be Singapore-based or serving Singapore customers unless explicitly stated otherwise. GDPR does not apply unless a client specifically requests EU compliance.

### Customer PII Stored

| Data Type | Stored Where | Retention |
|-----------|-------------|-----------|
| Phone number (WhatsApp) | Per-client Supabase `customers.phone_number` | Indefinite (until client offboarding or customer requests deletion) |
| Display name | Per-client Supabase `customers.customer_name` | Indefinite |
| Conversation history | Per-client Supabase `interactions_log` | Indefinite |
| Booking details (service, date, address) | Per-client Supabase `bookings` | Indefinite |
| Escalation state and reason | Per-client Supabase `customers.escalation_flag`, `escalation_reason` | Cleared when escalation resolved |
| LLM API keys (client's keys) | Railway env vars | Persistent until client offboarded |

**IP addresses and device fingerprints:** NOT stored (confirmed 2026-04-28).

### Data Residency

**Supabase region:** Singapore / Southeast Asia
**Railway region:** Default (US-based, but engine does not store customer data — only routes messages)
**LLM providers:**
- Anthropic: US-based (data sent to `api.anthropic.com` for inference)
- OpenAI: US-based (data sent to `api.openai.com` for fallback inference)

**PDPA compliance stance:** Conversation data is sent to US-based LLM providers for inference. This is disclosed in client agreements. If a client requires data residency within Singapore, Flow AI cannot serve them until a Singapore-based LLM provider is available (future consideration).

### Data Retention Policy

**Status:** TBD (not yet formally defined as of 2026-04-28)

**Current practice:**
- Customer data persists indefinitely in per-client Supabase projects
- No automated deletion or archival after inactivity
- On client offboarding: Supabase project paused for 90 days (in case of reactivation), then manually deleted

**Required before 10+ clients:** Formal data retention policy documented in client agreements, with automated purge workflows.

### Audit Trail

**Authoritative record:** Per-client Supabase `interactions_log` table.

**Contents:**
- Every inbound message (timestamp, phone number, message text, message type, channel)
- Every outbound message (timestamp, phone number, message text)
- Direction field (`inbound` / `outbound`) distinguishes customer vs agent messages

**Immutability:** `interactions_log` rows are never updated or deleted (append-only log). This ensures tamper-proof audit trail for disputes or compliance reviews.

### Access Control

**Per-client Supabase credentials:** Each client's Supabase project uses its own `service_role` key stored in Railway env vars. Flow AI founders have access to all client Supabase projects via Supabase Dashboard (org admin), but the engine itself has no cross-client database access.

**Shared Supabase credentials:** Flow AI Supabase `service_role` key is stored in Railway env vars. Only the engine and Flow AI founders have access.

**Railway env vars:** Only Flow AI founders have access to Railway dashboard and env vars. Client secrets are not shared with clients (clients provide secrets once during onboarding, Flow AI stores them).

### Customer Data Deletion Requests

**PDPA Right to Deletion:** If a customer requests deletion of their data under PDPA:

1. Client receives deletion request from customer
2. Client notifies Flow AI with phone number
3. Flow AI founder manually deletes rows from per-client Supabase:
   ```sql
   DELETE FROM customers WHERE phone_number = '+6591234567';
   DELETE FROM interactions_log WHERE phone_number = '+6591234567';
   DELETE FROM bookings WHERE phone_number = '+6591234567';
   DELETE FROM escalation_tracking WHERE phone_number = '+6591234567';
   ```
4. No automated deletion workflow exists yet (acceptable for <10 clients; must be automated before scaling further)

---

## 11. Current Clients

| client_id | Display Name | Status | Channels | Railway Project | Supabase Project | Notes |
|-----------|--------------|--------|----------|-----------------|-----------------|-------|
| `hey-aircon` | HeyAircon | **Live in production** | WhatsApp | `hey-aircon-agent` | `heyaircon` (legacy name) | Pilot client — aircon servicing bookings |
| `flow-ai` | Flow AI | **Scaffolded — infra pending** | WhatsApp (pending) | Not yet created | Not yet created | Flow AI's own lead qualification agent (second client) |

### HeyAircon — Production Client

**Onboarded:** 2026-04-15
**Supabase project:** `heyaircon` (legacy name; predates `{client-id}-crm` naming convention)
**Railway project:** `hey-aircon-agent` (live at `https://hey-aircon-agent.railway.app`)
**Webhook URL:** `https://hey-aircon-agent.railway.app/webhook/whatsapp/hey-aircon`
**Agent purpose:** Aircon servicing bookings (general servicing, chemical cleaning, repair)
**Booking flow:** Yes (Google Calendar integration)
**Sheets sync:** Yes (enabled — `heyaircon` Google Sheet)
**Phase:** Phase 1 MVP complete; Phase 2 address schema migration complete (2026-04-23)

### Flow AI — Internal Client (Scaffolded)

**Onboarded:** 2026-04-28 (scaffolded only — infra pending)
**Purpose:** Flow AI's own lead qualification agent (qualify inbound WhatsApp leads, escalate high-fit prospects to founder for demo)
**Booking flow:** No (escalation to Calendly link instead)
**Supabase project:** Not yet created
**Railway project:** Not yet created
**Status:** Directory structure scaffolded; `clients/flow-ai/plans/architecture.md` written; awaiting infrastructure provisioning (Steps 4–9 from Section 7)

---

## Appendix A: Migration Pathway to Secrets Manager (Future)

**Current approach:** Secrets stored as Railway env vars (5 per client).

**Acceptable until:** 10–20 clients.

**Migration trigger:** When managing 50+ env vars across 10+ Railway projects becomes operationally painful.

**Target solution:** AWS Secrets Manager or GCP Secret Manager.

**Migration path:**
1. Provision Secrets Manager instance
2. Create secret per client: `/flow-ai/clients/{client_id}/secrets` (JSON containing all 5 secrets)
3. Add `SECRETS_MANAGER_URL` and `SECRETS_MANAGER_KEY` to Railway (shared across all projects — replaces 5 per-client vars)
4. Update `load_client_config()` to fetch secrets from Secrets Manager instead of env vars
5. Deploy to one Railway project (test), then roll out to all projects
6. Remove per-client env vars from Railway once migration confirmed

**Benefit:** Centralized secret rotation, audit logs, programmatic secret updates (no Railway redeploy required for secret changes).

---

## Appendix B: Adding a Third Client — Validation Checklist

Before adding the third client, validate that all processes and docs are accurate by walking through the full onboarding runbook (Section 7) with a real client. Update this policy doc with any gaps or deviations discovered during the third client onboarding.

Expected gaps to address before client 3:
- [ ] Automated data deletion workflow (PDPA compliance)
- [ ] Formal data retention policy documented in client agreements
- [ ] Client-facing onboarding doc (this policy is internal; clients need a simplified version)
- [ ] Monitoring dashboard for per-client LLM usage and costs (currently logs exist in `api_usage`, but no dashboard)
- [ ] Alerting on per-client escalation rate spikes (currently manual log review)

---

**End of Document**

*Last reviewed: 2026-04-28*
*Next review due: When third client is onboarded, or 2026-06-01, whichever comes first*
