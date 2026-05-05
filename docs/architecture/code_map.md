# Flow AI Engine — Code Map

**Last Updated:** 2026-04-19
**Purpose:** Cold-start reference. Read this before touching any engine file.

---

## 1. End-to-End Message Flow

1. Meta Cloud API POSTs to `POST /webhook/whatsapp/{client_id}` (`api/webhook.py`)
2. Webhook parses the payload, extracts `phone_number`, `message_text`, `message_type`, `message_id`, `display_name`, then immediately returns 200 OK to Meta (`api/webhook.py`)
3. A FastAPI `BackgroundTask` invokes `handle_inbound_message()` — all remaining steps run after the 200 is sent (`core/message_handler.py`)
4. Client config is loaded (shared Supabase `clients` table + Railway env vars, 5-min TTL cache) and a per-client Supabase connection is opened (`config/client_config.py`, `integrations/supabase_client.py`)
5. Inbound message is logged to per-client `interactions_log` table — always first, unconditionally (`core/message_handler.py`)
6. Escalation gate: query per-client `customers` table; if `escalation_flag=True`, send holding reply, log outbound, stop — agent never runs (`core/message_handler.py`)
7. Customer upsert: INSERT new row or UPDATE `last_seen` for returning customer (`core/message_handler.py`)
8. Context builder fetches `config` + `policies` tables from per-client Supabase and last 20 messages from `interactions_log`, assembles system prompt (`core/context_builder.py`)
9. Agent runner calls Anthropic Haiku 4.5; on `tool_use` stop, executes tools and loops (max 10 iterations); on `end_turn`, returns final text; on Anthropic failure, silently retries with GPT-4o-mini; on both-fail, returns graceful error string (`core/agent_runner.py`)
10. Reply sent to customer via Meta Cloud API; outbound logged to `interactions_log`; token usage logged to shared Supabase `api_usage` (`integrations/meta_whatsapp.py`, `core/message_handler.py`, `integrations/observability.py`)

---

## 2. File Index

### Core Platform Files (WhatsApp Channel)

| File | What it does | Flow step(s) |
|------|-------------|--------------|
| `api/webhook.py` | FastAPI app: health check, Meta webhook verification (GET), inbound message receiver (POST); APScheduler setup for follow-up + session expiry jobs; always returns 200 to Meta | 1–2 |
| `core/message_handler.py` | Full pipeline orchestrator: log inbound, escalation gate, customer upsert, invoke context builder + agent runner, send reply, log outbound | 3–10 |
| `core/context_builder.py` | Builds Claude system prompt from per-client `config` + `policies` tables; fetches last 20 messages from `interactions_log` as conversation history; supports `channel` parameter to adjust prompt for widget vs WhatsApp | 8 |
| `core/agent_runner.py` | Claude tool-use loop: LLM provider shim (Anthropic primary / GPT-4o-mini fallback / GitHub Models for eval), executes tools, handles fallback logic, logs usage and incidents | 9 |
| `core/tools/__init__.py` | Exports `TOOL_DEFINITIONS` and `build_tool_dispatch()`; `build_tool_dispatch()` injects `db`, `client_config`, `phone_number` into tool closures per request | 9 |
| `core/tools/definitions.py` | Static list of 4 Anthropic-format tool dicts: `check_calendar_availability`, `write_booking`, `get_customer_bookings`, `escalate_to_human` | 9 |
| `core/tools/calendar_tools.py` | `check_calendar_availability()` — wraps `integrations/google_calendar.py`; returns AM/PM availability + human-readable message for Claude | 9 |
| `core/tools/booking_tools.py` | `write_booking()` — calendar event + Supabase INSERT into `bookings` (incl. `address`, `postal_code`, `channel`, `session_id` params) + customer name update; `get_customer_bookings()` — reads last 5 bookings; alerts human agent on backend failure | 9 |
| `core/tools/escalation_tool.py` | `escalate_to_human()` — sets `escalation_flag=True` on customer row, sends WhatsApp alert to `human_agent_number` | 9 |
| `config/settings.py` | `Settings` (pydantic-settings): platform-level env vars — `SHARED_SUPABASE_URL`, `SHARED_SUPABASE_SERVICE_KEY`, `LOG_LEVEL`; lazy singleton via `get_settings()` | 4 |
| `config/client_config.py` | `ClientConfig` dataclass + `load_client_config()`: reads shared `clients` table + 5 per-client env vars (incl. widget config fields); in-process TTL cache (5 min) | 4 |
| `integrations/meta_whatsapp.py` | `send_message()` — POST to Meta Graph API v19.0; `verify_webhook_token()` — token comparison for GET verification | 2, 10 |
| `integrations/supabase_client.py` | `get_shared_db()` — shared Flow AI Supabase client; `get_client_db(client_id)` — per-client Supabase client; no caching, new client per call | 4, 5–10 |
| `integrations/google_calendar.py` | `check_slot_availability()` — freebusy query for AM/PM windows; `create_booking_event()` — insert-only calendar event; sync Google API wrapped in `run_in_executor` | 9 |
| `integrations/observability.py` | `log_incident()` — writes to shared `api_incidents` on LLM failure; `log_usage()` — writes to shared `api_usage` on every successful LLM call; `extract_usage()` — normalises token counts across providers | 9–10 |

### Widget Channel Files (Phase 1 — NEW)

| File | What it does | Purpose |
|------|-------------|---------|
| `api/chat_routes.py` | FastAPI routes: `POST /chat/{client_id}/session` (create session), `POST /chat/{client_id}/message` (send message), `GET /chat/{client_id}/history` (fetch conversation history) | Widget API endpoints — session management and message handling |
| `api/widget_routes.py` | FastAPI route: `GET /widget/{client_id}.js` — serves static JavaScript with inlined `client_id` | Widget JavaScript delivery with server-side template injection |
| `api/cors_middleware.py` | FastAPI middleware: validates `Origin` header against `clients.widget_allowed_origins`; handles OPTIONS preflight; development bypass for localhost | CORS validation for all `/chat/*` endpoints |
| `core/widget_handler.py` | Widget message processing pipeline: escalation gate (queries `visitors` table), context builder invocation with `channel='widget'`, agent runner, cross-channel identity matching | Mirrors `message_handler.py` structure for widget channel |
| `core/session_expiry_job.py` | APScheduler job (runs every 5 minutes): marks sessions as expired if `last_active_at` exceeds `widget_session_ttl_minutes` | Session expiry background job for all active clients |
| `static/widget.js` | Vanilla JavaScript (no framework): chat button, chat window, message rendering, localStorage session management, API calls to `/chat/{client_id}/*` | Widget frontend — embedded on client websites via `<script>` tag |

---

## 3. Supabase Data Flow

### Shared Supabase (flowai-platform)

| Table | Operation | When | File |
|-------|-----------|------|------|
| `clients` | SELECT (by `client_id`, `is_active=True`) | Every inbound message (cache miss only, 5-min TTL) | `config/client_config.py` |
| `api_incidents` | INSERT | Every LLM provider failure (Anthropic or OpenAI) | `integrations/observability.py` |
| `api_usage` | INSERT | Every successful LLM call (primary or fallback) | `integrations/observability.py` |

### Per-client Supabase (e.g. heyaircon)

| Table | Operation | When | File |
|-------|-----------|------|------|
| `interactions_log` | INSERT (inbound) | Every inbound message, before any other processing | `core/message_handler.py` |
| `interactions_log` | SELECT (last 20, by phone) | Before every Claude call, to build conversation history | `core/context_builder.py` |
| `interactions_log` | INSERT (outbound) | After agent reply is sent (or holding/fallback reply) | `core/message_handler.py` |
| `customers` | SELECT (by phone) | Escalation gate check, every inbound message | `core/message_handler.py` |
| `customers` | INSERT | First message from a new customer | `core/message_handler.py` |
| `customers` | UPDATE (`last_seen`) | Every message from a returning customer | `core/message_handler.py` |
| `customers` | UPDATE (`escalation_flag`, `escalation_reason`) | When agent calls `escalate_to_human` tool | `core/tools/escalation_tool.py` |
| `customers` | UPDATE (`customer_name`) | After a successful `write_booking` call — address/postal_code moved to `bookings` (see `address_schema_migration.md`) | `core/tools/booking_tools.py` |
| `config` | SELECT (all rows, ordered by `sort_order`) | Before every Claude call, to build system prompt | `core/context_builder.py` |
| `policies` | SELECT (all rows, ordered by `sort_order`) | Before every Claude call, to build system prompt | `core/context_builder.py` |
| `bookings` | INSERT (incl. `address`, `postal_code` after Phase 2 migration) | When agent confirms a booking via `write_booking` tool | `core/tools/booking_tools.py` |
| `bookings` | SELECT (last 5, by phone) | When agent calls `get_customer_bookings` tool | `core/tools/booking_tools.py` |

---

## 4. Where to Look

### WhatsApp Channel

| Task | First file to open |
|------|--------------------|
| Change the agent's system prompt or persona | `core/context_builder.py` — identity block is hardcoded in `_IDENTITY_BLOCK`; services/pricing/policies come from per-client Supabase `config` and `policies` tables |
| Add a new tool | `core/tools/definitions.py` (add Anthropic tool dict) + new function file in `core/tools/` + register in `core/tools/__init__.py` `build_tool_dispatch()` |
| Modify escalation behaviour | `core/message_handler.py` (hard gate logic, holding reply text) + `core/tools/escalation_tool.py` (agent-triggered escalation, human alert template) |
| Change what gets logged | `integrations/observability.py` (LLM usage + incidents) + `core/message_handler.py` (interaction log writes) |
| Add a new client | INSERT row into shared `clients` table + add `{CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN`, `_SUPABASE_URL`, `_SUPABASE_SERVICE_KEY`, `_ANTHROPIC_API_KEY`, `_OPENAI_API_KEY` env vars to Railway — no code changes |
| Modify the LLM fallback logic | `core/agent_runner.py` — fallback trigger conditions, provider shim, `LLM_FALLBACK_ENABLED` env var check |
| Change the booking confirmation message | `core/tools/booking_tools.py` — `write_booking()` return dict `message` field |
| Modify calendar availability logic | `integrations/google_calendar.py` — `check_slot_availability()` freebusy query and `_SLOT_TIMES` windows |
| Change the holding reply text (escalated customers) | `core/message_handler.py` — `HOLDING_REPLY` constant at module level |
| Update services, pricing, or policies (no code change needed) | Supabase Studio — per-client `config` table (keys: `service_*`, `pricing_*`, `appointment_window_am/pm`, `booking_lead_time_days`) and `policies` table |

### Widget Channel (Phase 1)

| Task | First file to open |
|------|--------------------|
| Add a new widget API endpoint | `api/chat_routes.py` — add route handler, register in FastAPI app |
| Change widget button appearance or behavior | `static/widget.js` — button rendering, click handlers, CSS styles || Modify widget button appearance (color, icon) or hover states | `engine/static/widget.js` — `injectStyles()` function for CSS, `injectHTML()` for button icon; config extracted from `window.FLOWAI_CONFIG` at top of IIFE || Modify widget CORS validation logic | `api/cors_middleware.py` — origin whitelist parsing, development bypass logic |
| Change widget escalation behavior | `core/widget_handler.py` — escalation gate logic (queries `visitors` table instead of `customers`) |
| Modify widget session expiry threshold | `clients` table in shared Supabase — update `widget_session_ttl_minutes` column (no code change) |
| Change widget JavaScript delivery or caching | `api/widget.py` — `serve_widget_js()` function; validates and injects `window.FLOWAI_CONFIG` (clientId, primaryColor, buttonIcon), Cache-Control headers |
| Add widget configuration fields | `config/client_config.py` — add fields to `ClientConfig` dataclass + update `load_client_config()` |
| Modify cross-channel identity matching | `core/widget_handler.py` — phone lookup logic, `visitors.customer_id` FK assignment |
| Debug widget session expiry job | `core/session_expiry_job.py` — scheduler logic, expiry SQL query |
| Update widget database schema | `supabase/migrations/010_widget_schema.sql` — add new migration file for schema changes |
