# Chat Widget — Technical Architecture

**Feature:** Embeddable web chat widget (Phase 1 MVP)  
**Status:** Architecture Approved — Ready for Implementation  
**Last Updated:** 2026-04-30  
**Architect:** `@software-architect`

---

## 1. Architecture Overview

### Purpose

The chat widget provides a web-native entry point to the Flow AI agent platform. Website visitors can initiate conversations without WhatsApp, reducing friction for prospects who do not have the app installed or are hesitant to share their phone number before qualifying the service.

Phase 1 deploys the widget on the Flow AI website (`getflowai.co`) only. Phase 2 extends to multi-client deployment (client websites embed the widget to serve their own agent).

### How It Fits Into the Existing Platform

The widget is a **new channel** alongside WhatsApp. It reuses the existing agent engine (`context_builder.py`, `agent_runner.py`, tools, knowledge base) with zero duplication. The only new components are:

1. **Three new FastAPI routes** — session creation, message send, history fetch
2. **Widget JavaScript file** — static `.js` served from `engine/static/`
3. **Three new database tables** — `sessions`, `visitors`, plus schema changes to `interactions_log`, `bookings`, `clients`
4. **CORS middleware** — validates `Origin` header against per-client allowed domains
5. **Session expiry background job** — marks expired sessions via APScheduler

```
┌──────────────────────────────────────────────────────────────┐
│                     Flow AI Platform                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  WhatsApp Channel              Widget Channel (NEW)          │
│  ───────────────               ────────────────             │
│  Meta Cloud API                Client Website                │
│       ↓                             ↓                         │
│  POST /webhook/whatsapp/      POST /chat/{client_id}/message │
│       {client_id}                   ↓                         │
│       ↓                        CORS Middleware                │
│  message_handler.py                 ↓                         │
│       ↓                        widget_handler.py (new)        │
│       ↓                             ↓                         │
│       └─────────────┬───────────────┘                        │
│                     ↓                                         │
│            Escalation Gate Check                              │
│            (customers/visitors tables)                        │
│                     ↓                                         │
│            context_builder.py                                 │
│            (Supabase config + history)                        │
│                     ↓                                         │
│            agent_runner.py                                    │
│            (Claude + tools)                                   │
│                     ↓                                         │
│            Response Delivery                                  │
│       (Meta API)         (HTTP JSON response)                │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Two Runtime Paths

**Path 1 — Anonymous Widget Session:**
1. Visitor opens widget → no pre-chat form submission (clicks "Skip")
2. `POST /chat/{client_id}/session` → generates `session_id`, stores in `localStorage`
3. Visitor sends message → `POST /chat/{client_id}/message` with `session_id`
4. No `visitors` row exists; `interactions_log` rows have `session_id` but no `phone_number`
5. Agent builds context from widget-only history (no cross-channel data)

**Path 2 — Identified Visitor with Linked WhatsApp History:**
1. Visitor submits pre-chat form with phone number (e.g., `+6591234567`)
2. Backend queries per-client `customers` table: `SELECT id FROM customers WHERE phone_number = $1`
3. If match found: `INSERT INTO visitors (..., customer_id, ...)` with FK to `customers.id`
4. Agent context includes prior WhatsApp `interactions_log` history (last 5 exchanges)
5. Agent is aware visitor is a returning customer — adjusts response accordingly

### Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **Sessions in Supabase (not in-memory)** | Conversation continuity requires persistence; session expiry checks must survive Railway restarts |
| **Rate limits in-memory** | Acceptable trade-off for Phase 1 — limits reset on deploy (~once/week), low-severity abuse vector |
| **Vanilla JS (no framework)** | Zero build pipeline; Phase 1 UI is simple enough (text-only, 200 lines of JS) |
| **CORS middleware** | Prevents unauthorized embedding; validates `Origin` against per-client whitelist |
| **Escalation gate identical to WhatsApp** | Same `escalation_flag` check, same holding reply — unified escalation model across channels |
| **Cross-channel identity via phone lookup** | When visitor submits phone, query `customers` table; if match, link via FK — no PII duplication |

---

## 2. Data Model

### 2.1 New Table: `sessions`

Stores all widget sessions (both anonymous and identified). One row per `session_id`.

**Location:** Per-client Supabase (same database as `customers`, `bookings`, `interactions_log`)

```sql
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(client_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expired_at TIMESTAMPTZ,
    user_agent TEXT,
    -- ip_address intentionally omitted in Phase 1 (PDPA — only if visitor consents)
    CONSTRAINT sessions_client_fk FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
);

-- Index: frequent query in message handler (validate session exists and not expired)
CREATE INDEX idx_sessions_client_id ON sessions(client_id);

-- Index: session expiry job scans this (WHERE expired_at IS NULL AND last_active_at < threshold)
CREATE INDEX idx_sessions_last_active ON sessions(last_active_at) WHERE expired_at IS NULL;

-- Index: history cleanup job (Phase 2 — purge old sessions)
CREATE INDEX idx_sessions_expired ON sessions(expired_at) WHERE expired_at IS NOT NULL;
```

**Field notes:**
- `session_id`: UUID v4 (not guessable, not sequential) — serves as session token stored in browser `localStorage`
- `client_id`: Foreign key to shared `clients` table — all sessions scoped by client
- `last_active_at`: Updated on every `POST /chat/{client_id}/message` — used for expiry calculation
- `expired_at`: NULL = active session; non-NULL = expired (session expiry job sets this)
- `user_agent`: Optional tracking field (from HTTP `User-Agent` header) — not enforced in Phase 1

**Retention:** Sessions older than 12 months purged by scheduled job (PDPA compliance). Phase 2 feature.

---

### 2.2 New Table: `visitors`

Stores identity data for visitors who submit the pre-chat form. No row exists for anonymous sessions.

**Location:** Per-client Supabase

```sql
CREATE TABLE visitors (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    client_id TEXT NOT NULL REFERENCES clients(client_id),
    name TEXT,
    email TEXT,
    phone TEXT,  -- Optional; E.164 format without + prefix (e.g. "6591234567")
    customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,  -- Set if phone matched existing WhatsApp customer
    escalation_flag BOOLEAN NOT NULL DEFAULT FALSE,
    escalation_reason TEXT,
    escalated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT visitors_session_fk FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    CONSTRAINT visitors_customer_fk FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
);

-- Index: enforce one visitor per session (1:1 relationship)
CREATE UNIQUE INDEX idx_visitors_session_id ON visitors(session_id);

-- Index: email-based lookup (Phase 2 — email-based identity linking)
CREATE INDEX idx_visitors_email ON visitors(email) WHERE email IS NOT NULL;

-- Index: cross-channel identity queries (fetch linked WhatsApp customer)
CREATE INDEX idx_visitors_customer_id ON visitors(customer_id) WHERE customer_id IS NOT NULL;

-- Index: escalation gate check (query by session_id to check escalation_flag)
CREATE INDEX idx_visitors_escalation ON visitors(session_id, escalation_flag);
```

**Field notes:**
- `session_id`: Foreign key to `sessions` — 1:1 relationship (one visitor per session)
- `customer_id`: Foreign key to `customers` — set when phone matches existing WhatsApp customer (cross-channel linking)
- `escalation_flag`: Same semantics as `customers.escalation_flag` — when TRUE, agent does not run
- `phone`: Optional field; used for cross-channel identity lookup — stored only if visitor submits form

**Cross-channel identity logic (inline at form submission):**
1. Visitor submits pre-chat form with phone number (e.g., `6591234567`)
2. Backend queries: `SELECT id FROM customers WHERE phone_number = $1 LIMIT 1`
3. If match found: `INSERT INTO visitors (..., customer_id = <matched_id>, ...)`
4. If no match: `INSERT INTO visitors (..., customer_id = NULL, ...)`
5. Agent context builder checks `visitors.customer_id`; if set, fetches prior `interactions_log` for that `phone_number` and prepends to widget conversation history

---

### 2.3 Schema Changes: `interactions_log`

Add two new columns to support widget channel. All existing WhatsApp rows remain unchanged (default values applied).

**Location:** Per-client Supabase

```sql
-- Add channel discriminator (default 'whatsapp' for backward compatibility)
ALTER TABLE interactions_log 
ADD COLUMN channel TEXT NOT NULL DEFAULT 'whatsapp';

-- Add session_id for widget messages (NULL for WhatsApp messages)
ALTER TABLE interactions_log 
ADD COLUMN session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL;

-- Make phone_number nullable (widget messages have no phone if visitor is anonymous)
ALTER TABLE interactions_log 
ALTER COLUMN phone_number DROP NOT NULL;

-- Index: widget conversation history queries (fetch last 20 messages by session_id)
CREATE INDEX idx_interactions_log_session_id ON interactions_log(session_id, created_at DESC);

-- Index: cross-channel history queries (fetch all messages for a customer across both channels)
CREATE INDEX idx_interactions_log_customer_channel ON interactions_log(phone_number, channel, created_at DESC) 
WHERE phone_number IS NOT NULL;
```

**Invariants:**
- WhatsApp messages: `channel='whatsapp'`, `phone_number` NOT NULL, `session_id` NULL
- Widget messages (anonymous): `channel='widget'`, `phone_number` NULL, `session_id` NOT NULL
- Widget messages (identified): `channel='widget'`, `phone_number` NOT NULL (if visitor submitted form), `session_id` NOT NULL

**Backward compatibility:** All existing rows have `channel='whatsapp'` and `session_id=NULL` by default. No data migration required.

---

### 2.4 Schema Changes: `bookings`

Add two new columns to track which channel the booking originated from.

**Location:** Per-client Supabase

```sql
-- Add channel discriminator (default 'whatsapp')
ALTER TABLE bookings 
ADD COLUMN channel TEXT NOT NULL DEFAULT 'whatsapp';

-- Add session_id for widget bookings (NULL for WhatsApp bookings)
ALTER TABLE bookings 
ADD COLUMN session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL;

-- Index: widget booking queries (fetch bookings for a session)
CREATE INDEX idx_bookings_session_id ON bookings(session_id) WHERE session_id IS NOT NULL;
```

**Use case:** Enables reporting queries like "How many bookings came from widget vs WhatsApp?" and "What's the conversion rate for widget visitors?"

---

### 2.5 Schema Changes: `clients` Table (Shared Supabase)

Add widget configuration columns to the shared Flow AI `clients` table.

**Location:** Shared Supabase (`flowai-platform`)

```sql
-- Widget feature flag
ALTER TABLE clients 
ADD COLUMN widget_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- Widget branding
ALTER TABLE clients 
ADD COLUMN widget_primary_color TEXT DEFAULT '#4F46E5';

ALTER TABLE clients 
ADD COLUMN widget_agent_name TEXT DEFAULT 'Assistant';

ALTER TABLE clients 
ADD COLUMN widget_welcome_message TEXT DEFAULT 'Hi! How can I help you today?';

-- CORS origin whitelist (comma-separated domains)
ALTER TABLE clients 
ADD COLUMN widget_allowed_origins TEXT;

-- Session TTL (minutes of inactivity before expiry)
ALTER TABLE clients 
ADD COLUMN widget_session_ttl_minutes INTEGER NOT NULL DEFAULT 30;
```

**Field notes:**
- `widget_enabled`: Master switch — if FALSE, all widget endpoints return `403 Forbidden`
- `widget_allowed_origins`: Comma-separated list of allowed domains (e.g., `https://getflowai.co,https://www.getflowai.co`) — CORS middleware validates `Origin` header against this list
- `widget_session_ttl_minutes`: Configurable session expiry threshold (default 30 minutes of inactivity)

**Example row (Flow AI pilot):**
```sql
INSERT INTO clients (
    client_id, 
    widget_enabled, 
    widget_primary_color, 
    widget_agent_name, 
    widget_welcome_message, 
    widget_allowed_origins, 
    widget_session_ttl_minutes
) VALUES (
    'flow-ai',
    TRUE,
    '#4F46E5',
    'Kai',
    'Hi! I''m Kai, your AI assistant. How can I help you today?',
    'https://getflowai.co,https://www.getflowai.co',
    30
);
```

---

## 3. API Design

All widget endpoints are mounted under `/chat/{client_id}/`. The `client_id` path parameter scopes all operations to a specific client.

### 3.1 Endpoint: Create Session

**Route:** `POST /chat/{client_id}/session`

**Purpose:** Generate a new widget session. Called when visitor opens widget for the first time (no `session_id` in `localStorage`).

**Request:**

```
POST /chat/flow-ai/session HTTP/1.1
Host: flow-engine.railway.app
Content-Type: application/json
Origin: https://getflowai.co

{}
```

**Request schema:**
```json
{}
```
(Empty body — `session_id` is server-generated, not client-provided.)

**Response (200 OK):**
```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "welcome_message": "Hi! I'm Kai, your AI assistant. How can I help you today?"
}
```

**Response schema:**
- `session_id` (string, UUID v4): Unique session identifier — client stores in `localStorage`
- `welcome_message` (string): First message displayed in chat window (from `clients.widget_welcome_message`)

**Error responses:**

| Status | Condition | Body |
|--------|-----------|------|
| `403 Forbidden` | `clients.widget_enabled = FALSE` for this `client_id` | `{"error": "Widget not enabled for this client"}` |
| `403 Forbidden` | `Origin` header not in `clients.widget_allowed_origins` | `{"error": "Origin not allowed"}` |
| `404 Not Found` | `client_id` does not exist or `is_active = FALSE` | `{"error": "Client not found"}` |
| `500 Internal Server Error` | Database insert failure | `{"error": "Failed to create session"}` |

**Logic:**
1. Validate CORS: extract `Origin` header, load `ClientConfig` for `client_id`, check if `Origin` in `widget_allowed_origins` list
2. Check `clients.widget_enabled = TRUE`
3. Generate `session_id` (UUID v4)
4. INSERT into `sessions`: `(session_id, client_id, created_at, last_active_at)`
5. Return `session_id` and `widget_welcome_message` from `ClientConfig`

**Rate limit:** 10 session creations per IP per hour (in-memory tracking).

---

### 3.2 Endpoint: Send Message

**Route:** `POST /chat/{client_id}/message`

**Purpose:** Send a message from the visitor and receive an agent reply. This is the core conversation endpoint.

**Request:**

```
POST /chat/flow-ai/message HTTP/1.1
Host: flow-engine.railway.app
Content-Type: application/json
Origin: https://getflowai.co

{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "message": "How much does a general servicing cost?"
}
```

**Request schema:**
```json
{
    "session_id": "string (UUID)",
    "message": "string (max 2000 characters)"
}
```

**Response (200 OK):**
```json
{
    "reply": "General servicing for a single unit starts at $60...",
    "escalated": false
}
```

**Response schema:**
- `reply` (string): Agent's text response (or holding message if escalated)
- `escalated` (boolean): TRUE if this message triggered escalation; FALSE otherwise

**Error responses:**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | `message` empty or exceeds 2000 characters | `{"error": "Message must be between 1 and 2000 characters"}` |
| `403 Forbidden` | `Origin` header not in `clients.widget_allowed_origins` | `{"error": "Origin not allowed"}` |
| `404 Not Found` | `session_id` not found in `sessions` table | `{"error": "Session not found"}` |
| `410 Gone` | Session expired (`expired_at` IS NOT NULL) | `{"error": "Session expired — please refresh and start a new conversation"}` |
| `429 Too Many Requests` | Rate limit exceeded (10 messages/minute per session) | `{"error": "Rate limit exceeded", "retry_after": 45}` |
| `500 Internal Server Error` | Agent failure or database error | `{"error": "We're experiencing a technical issue. Please try again in a moment."}` |

**Logic (mirrors WhatsApp `message_handler.py`):**
1. Validate CORS (same as session endpoint)
2. Validate `session_id` exists and `expired_at IS NULL`
3. Update `sessions.last_active_at = NOW()`
4. Log inbound message to `interactions_log`: `(channel='widget', session_id, message_text, direction='inbound')`
5. **Escalation gate:** Query `visitors` table by `session_id` — if `escalation_flag = TRUE`, return holding reply immediately (agent does not run)
6. Fetch conversation history: last 20 messages from `interactions_log` WHERE `session_id` ORDER BY `created_at` DESC
7. If `visitors.customer_id` IS NOT NULL: fetch prior WhatsApp history (last 5 exchanges) and prepend to context
8. Call `context_builder.py` with `channel='widget'` parameter (adjusts system prompt)
9. Call `agent_runner.py` (same Claude loop as WhatsApp)
10. Log outbound reply to `interactions_log`: `(direction='outbound')`
11. Return agent reply

**Channel parameter in context builder:**
- `channel='widget'`: System prompt includes: "You are responding via the Flow AI website chat widget. The visitor may be anonymous (no name/email provided)."
- Booking confirmation message adjusted: "You'll receive email confirmation" (if visitor provided email) instead of "You'll receive SMS confirmation"

**Rate limit:** 10 messages per minute per `session_id` (in-memory tracking, keyed by `session_id`).

---

### 3.3 Endpoint: Fetch Conversation History

**Route:** `GET /chat/{client_id}/history`

**Purpose:** Retrieve conversation history for a session. Called when visitor refreshes page (session recovery via `localStorage`).

**Request:**

```
GET /chat/flow-ai/history?session_id=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Host: flow-engine.railway.app
Origin: https://getflowai.co
```

**Query parameters:**
- `session_id` (required, string, UUID): Session identifier from `localStorage`

**Response (200 OK):**
```json
{
    "messages": [
        {
            "role": "assistant",
            "text": "Hi! I'm Kai, your AI assistant. How can I help you today?",
            "timestamp": "2026-04-30T10:00:00Z"
        },
        {
            "role": "user",
            "text": "How much does a general servicing cost?",
            "timestamp": "2026-04-30T10:00:15Z"
        },
        {
            "role": "assistant",
            "text": "General servicing for a single unit starts at $60...",
            "timestamp": "2026-04-30T10:00:18Z"
        }
    ],
    "escalated": false
}
```

**Response schema:**
- `messages` (array): Conversation history in chronological order (oldest first)
  - `role` (string): `"user"` or `"assistant"`
  - `text` (string): Message content
  - `timestamp` (string, ISO 8601): Message timestamp
- `escalated` (boolean): TRUE if session is currently escalated; FALSE otherwise

**Error responses:**

| Status | Condition | Body |
|--------|-----------|------|
| `403 Forbidden` | `Origin` header not in `clients.widget_allowed_origins` | `{"error": "Origin not allowed"}` |
| `404 Not Found` | `session_id` not found | `{"error": "Session not found"}` |
| `410 Gone` | Session expired | `{"error": "Session expired"}` |

**Logic:**
1. Validate CORS
2. Validate `session_id` exists and `expired_at IS NULL`
3. Query `interactions_log` WHERE `session_id` ORDER BY `created_at` ASC LIMIT 50
4. Transform to frontend format: `direction='inbound'` → `role='user'`, `direction='outbound'` → `role='assistant'`
5. Query `visitors` table by `session_id` to check `escalation_flag`
6. Return messages array and escalation status

**Rate limit:** 5 history fetches per minute per `session_id` (prevents polling abuse).

---

### 3.4 Endpoint: Widget JavaScript Delivery

**Route:** `GET /widget/{client_id}.js`

**Purpose:** Serve the widget JavaScript file with inlined `client_id`. This is the script tag URL embedded on client websites.

**Request:**

```
GET /widget/flow-ai.js HTTP/1.1
Host: flow-engine.railway.app
```

**Response (200 OK):**
```javascript
// Widget JavaScript (minified, single file, vanilla JS)
(function() {
    window.FLOWAI_CLIENT_ID = 'flow-ai';
    // ... rest of widget code ...
})();
```

**Response headers:**
- `Content-Type: application/javascript`
- `Cache-Control: public, max-age=3600` (1 hour — widget updates propagate within 1 hour of deploy)

**Error responses:**

| Status | Condition | Body |
|--------|-----------|------|
| `404 Not Found` | `client_id` not found or `widget_enabled = FALSE` | `// Widget not enabled` |

**Logic:**
1. Load `ClientConfig` for `client_id`
2. Check `widget_enabled = TRUE`
3. Read static file from `engine/static/widget.js`
4. Inject `window.FLOWAI_CLIENT_ID = '{client_id}';` at the top of the script
5. Return with caching headers

**File location:** `engine/static/widget.js` — single vanilla JS file, no build pipeline required for Phase 1.

**Phase 2 upgrade:** Add minification and bundling (Webpack/Rollup) when widget complexity increases.

---

## 4. Widget JavaScript Delivery

### File Structure

```
engine/
├── static/
│   └── widget.js          # Vanilla JS, single file, ~200 lines
└── api/
    └── widget_routes.py   # FastAPI routes for /widget/{client_id}.js
```

### How Client ID is Inlined

The `GET /widget/{client_id}.js` endpoint performs **server-side template injection**:

1. Read `engine/static/widget.js` as a string
2. Prepend `window.FLOWAI_CLIENT_ID = '{client_id}';` at the top
3. Return with `Content-Type: application/javascript`

**No build-time configuration.** The widget code is client-agnostic. All client-specific behavior is controlled by the inlined `FLOWAI_CLIENT_ID` variable, which determines:
- Which API endpoints to call (`POST /chat/{FLOWAI_CLIENT_ID}/session`)
- Session storage key in `localStorage` (`flowai_session_{FLOWAI_CLIENT_ID}`)

### Cache Strategy

**Cache-Control header:** `public, max-age=3600` (1 hour)

**Rationale:**
- Widget updates propagate within 1 hour of Railway deploy (acceptable for Phase 1)
- No CDN caching in Phase 1 — Railway serves static files directly
- Phase 2 migration: Deploy widget to CDN (Cloudflare/CloudFront) and extend cache TTL to 24 hours

**Cache invalidation (manual):**
- Deploy triggers Railway restart → new widget version served after 1 hour TTL expires
- Critical hotfix: manually purge Railway cache (if supported) or set `max-age=0` temporarily

---

## 5. CORS Middleware Design

### Purpose

Prevent unauthorized embedding of the widget on domains not owned by the client. The CORS middleware validates that the `Origin` header of every widget API request matches the client's whitelist.

### Implementation Pattern

**FastAPI middleware function** (not a library — custom implementation):

```python
# Pseudocode — actual implementation in engine/api/cors_middleware.py

@app.middleware("http")
async def validate_widget_cors(request: Request, call_next):
    # 1. Extract path and check if it's a widget endpoint
    if not request.url.path.startswith("/chat/"):
        # Not a widget endpoint — skip CORS check
        return await call_next(request)
    
    # 2. Extract client_id from path (/chat/{client_id}/...)
    path_parts = request.url.path.split("/")
    if len(path_parts) < 3:
        return Response(status_code=400, content="Invalid path")
    client_id = path_parts[2]
    
    # 3. Load ClientConfig (uses 5-min TTL cache)
    try:
        client_config = await load_client_config(client_id)
    except ClientNotFoundError:
        return Response(status_code=404, content="Client not found")
    
    # 4. Parse allowed origins from comma-separated string
    allowed_origins = [
        origin.strip() 
        for origin in (client_config.widget_allowed_origins or "").split(",")
        if origin.strip()
    ]
    
    # 5. Development bypass: allow localhost
    if os.getenv("ENVIRONMENT") == "development":
        allowed_origins.extend([
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000"
        ])
    
    # 6. Extract Origin header
    origin = request.headers.get("Origin")
    if not origin:
        # No Origin header — allow (same-origin requests from curl/Postman)
        return await call_next(request)
    
    # 7. Validate Origin against whitelist
    if origin not in allowed_origins:
        return Response(status_code=403, content="Origin not allowed")
    
    # 8. Origin validated — proceed to route handler
    response = await call_next(request)
    
    # 9. Add CORS headers to response (required for browser)
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    
    return response
```

### Handling OPTIONS Preflight Requests

Browsers send `OPTIONS` requests before `POST` requests (CORS preflight). The middleware must handle these:

```python
# Pseudocode — preflight handler in cors_middleware.py

@app.options("/chat/{client_id}/{path:path}")
async def handle_widget_preflight(client_id: str):
    # Load client config (validates client_id exists)
    client_config = await load_client_config(client_id)
    
    # Extract Origin header
    origin = request.headers.get("Origin")
    
    # Validate against allowed origins
    allowed_origins = [...]  # Same logic as middleware
    if origin not in allowed_origins:
        return Response(status_code=403)
    
    # Return preflight approval
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400"  # Cache preflight for 24 hours
        }
    )
```

### Development Override

When `ENVIRONMENT=development` (Railway env var), the middleware automatically appends `http://localhost:*` to the allowed origins list. This allows local frontend development without modifying the database.

**Production:** `ENVIRONMENT=production` (default) — no localhost bypass.

---

## 6. Cross-Channel Identity Matching

### Purpose

When a visitor submits the pre-chat form with a phone number, link them to an existing WhatsApp customer (if a match exists). This enables the agent to access prior conversation history and avoid re-asking for information the customer already provided.

### Flow

**Step 1 — Visitor submits pre-chat form**

Widget calls `POST /chat/{client_id}/session` with form data:

```json
{
    "name": "John Tan",
    "email": "john@example.com",
    "phone": "6591234567"
}
```

(Alternative design: create a new `POST /chat/{client_id}/identify` endpoint instead of overloading the session endpoint. Decision: use session endpoint with optional body fields.)

**Step 2 — Backend queries `customers` table**

```sql
SELECT id, customer_name, phone_number
FROM customers
WHERE phone_number = $1
LIMIT 1
```

**Step 3a — Match found (existing WhatsApp customer)**

```sql
INSERT INTO visitors (
    session_id,
    client_id,
    name,
    email,
    phone,
    customer_id,  -- Set to matched customers.id
    created_at
) VALUES (
    $1, $2, $3, $4, $5, $6, NOW()
);
```

**Step 3b — No match found (new visitor)**

```sql
INSERT INTO visitors (
    session_id,
    client_id,
    name,
    email,
    phone,
    customer_id,  -- NULL (no match)
    created_at
) VALUES (
    $1, $2, $3, $4, $5, NULL, NOW()
);
```

**Step 4 — Agent context includes prior WhatsApp history**

When `context_builder.py` is invoked for a widget message:

1. Query `visitors` table by `session_id` to check if `customer_id` IS NOT NULL
2. If set: fetch prior `interactions_log` rows WHERE `phone_number = <customer's phone>` AND `channel = 'whatsapp'` ORDER BY `created_at` DESC LIMIT 5
3. Prepend WhatsApp history to widget conversation history (with channel context string: "[Prior WhatsApp conversation]")
4. Agent is aware the visitor is a returning customer — adjusts response accordingly

**Example context (with cross-channel history):**

```
System: You are responding via the Flow AI website chat widget. The visitor has had prior WhatsApp conversations with you.

[Prior WhatsApp conversation]
Customer: I need to book a servicing.
Assistant: Sure! When would you like to schedule it?
Customer: Next Tuesday, 2pm slot.
Assistant: Perfect. What's your address?
...

[Widget conversation]
Visitor: Hi, I'm interested in booking a servicing.
Assistant: Hi John! I see you've booked with us before via WhatsApp. Would you like to schedule another appointment?
```

### Where This Logic Lives

**Option A (recommended):** Inline in `POST /chat/{client_id}/session` route handler

- Fewer moving parts
- No separate module to maintain
- Identity lookup is a single SQL query (low complexity)

**Option B:** New `engine/core/identity_matcher.py` module

- Cleaner separation of concerns
- Reusable if Phase 2 adds email-based identity matching
- Testable in isolation

**Decision:** Option A for Phase 1 (inline). Refactor to Option B in Phase 2 if email-based matching is added.

---

## 7. Session Expiry Background Job

### Purpose

Automatically mark sessions as expired after `widget_session_ttl_minutes` of inactivity. Expired sessions cannot send new messages — visitor must refresh and start a new session.

### Scheduler Integration

The engine already uses **APScheduler** for follow-up message scheduling (`engine/core/followup_scheduler.py`). The session expiry job extends the same scheduler.

### Job Logic

```python
# Pseudocode — actual implementation in engine/core/session_expiry_job.py

async def expire_inactive_sessions():
    """
    Mark sessions as expired if last_active_at exceeds TTL.
    
    Runs every 5 minutes via APScheduler.
    """
    # 1. Iterate over all active clients
    shared_db = await get_shared_db()
    clients = await shared_db.table("clients").select("client_id, widget_session_ttl_minutes").eq("is_active", True).execute()
    
    for client_row in clients.data:
        client_id = client_row["client_id"]
        ttl_minutes = client_row["widget_session_ttl_minutes"]
        
        try:
            # 2. Get per-client Supabase connection
            client_db = await get_client_db(client_id)
            
            # 3. Calculate expiry threshold
            threshold = NOW() - INTERVAL '{ttl_minutes} minutes'
            
            # 4. Mark expired sessions
            result = await client_db.rpc(
                "expire_sessions_before",
                {"threshold_timestamp": threshold}
            )
            
            if result.data and result.data["count"] > 0:
                logger.info(f"Expired {result.data['count']} sessions for client '{client_id}'")
        
        except Exception as e:
            logger.error(f"Failed to expire sessions for client '{client_id}': {e}", exc_info=True)
            continue
```

### Database Function (Supabase RPC)

Create a Postgres function in each client's Supabase for efficient batch updates:

```sql
CREATE OR REPLACE FUNCTION expire_sessions_before(threshold_timestamp TIMESTAMPTZ)
RETURNS TABLE(count BIGINT) AS $$
    UPDATE sessions
    SET expired_at = NOW()
    WHERE last_active_at < threshold_timestamp
      AND expired_at IS NULL
    RETURNING 1;
    
    SELECT COUNT(*) FROM sessions WHERE expired_at IS NOT NULL;
$$ LANGUAGE sql;
```

### Scheduler Configuration

In `engine/api/webhook.py` (existing scheduler setup):

```python
scheduler.add_job(
    expire_inactive_sessions,
    trigger="interval",
    minutes=5,
    id="session_expiry",
    replace_existing=True,
)
```

**Interval:** 5 minutes (configurable via env var `SESSION_EXPIRY_JOB_INTERVAL_MINUTES`).

**Trade-off:** Sessions expire within 5 minutes of TTL threshold (not immediately) — acceptable delay for Phase 1.

---

## 8. Widget Message Processing Pipeline

### Full Flow Diagram

```
1. Widget sends POST /chat/{client_id}/message
   ↓
2. CORS middleware validates Origin header
   ↓ (Origin allowed)
3. Route handler: load ClientConfig + client Supabase connection
   ↓
4. Validate session_id exists and expired_at IS NULL
   ↓ (Session valid)
5. Update sessions.last_active_at = NOW()
   ↓
6. Log inbound message to interactions_log
   (channel='widget', session_id, direction='inbound')
   ↓
7. Escalation gate check:
   Query: SELECT escalation_flag FROM visitors WHERE session_id = $1
   ↓
   ├─ escalation_flag = TRUE → Send holding reply, log outbound, return {"escalated": true}
   └─ escalation_flag = FALSE or no row → Continue
   ↓
8. Fetch conversation history:
   Query: SELECT * FROM interactions_log WHERE session_id = $1 ORDER BY created_at DESC LIMIT 20
   ↓
9. Cross-channel history (if applicable):
   Query: SELECT customer_id FROM visitors WHERE session_id = $1
   ↓
   └─ IF customer_id IS NOT NULL:
      Query: SELECT * FROM interactions_log 
             WHERE phone_number = (SELECT phone_number FROM customers WHERE id = $1)
               AND channel = 'whatsapp'
             ORDER BY created_at DESC LIMIT 5
      Prepend to conversation history
   ↓
10. Call context_builder.py with channel='widget' parameter
    (System prompt includes: "You are responding via the website chat widget")
    ↓
11. Call agent_runner.py (same Claude tool-use loop as WhatsApp)
    ↓
12. Log outbound reply to interactions_log (direction='outbound')
    ↓
13. Return {"reply": "...", "escalated": false}
```

### Error Handling at Each Step

| Step | Error Condition | Response | HTTP Status |
|------|----------------|----------|-------------|
| 2 | Origin not in whitelist | `{"error": "Origin not allowed"}` | `403 Forbidden` |
| 3 | client_id not found | `{"error": "Client not found"}` | `404 Not Found` |
| 4 | session_id not found | `{"error": "Session not found"}` | `404 Not Found` |
| 4 | expired_at IS NOT NULL | `{"error": "Session expired"}` | `410 Gone` |
| 6 | Supabase insert failure | `{"error": "Failed to log message"}` | `500 Internal Server Error` |
| 7 | Supabase query failure | `{"reply": "We're experiencing a technical issue..."}` | `200 OK` (graceful degradation) |
| 11 | Agent failure (Claude API timeout) | `{"reply": "I'm taking longer than usual. Please try again."}` | `200 OK` (graceful reply) |
| 11 | Agent failure (both Anthropic and OpenAI fail) | `{"reply": "We're experiencing a technical issue..."}` | `200 OK` (graceful reply) |

**Critical rule:** The widget endpoint MUST always return `200 OK` with a reply (even if it's an error message). Never return `500` to the frontend — graceful degradation only.

### Escalation Gate Implementation

The escalation gate is **identical to WhatsApp** but queries the `visitors` table instead of `customers`:

```python
# Pseudocode — actual implementation in engine/core/widget_handler.py

async def check_escalation_gate(db, session_id: str) -> tuple[bool, str | None]:
    """
    Check if the session is escalated.
    
    Returns:
        (is_escalated, escalation_reason)
    """
    result = await db.table("visitors").select("escalation_flag, escalation_reason").eq("session_id", session_id).limit(1).execute()
    
    if not result.data:
        # No visitor row exists (anonymous session) — not escalated
        return (False, None)
    
    visitor = result.data[0]
    return (visitor["escalation_flag"], visitor.get("escalation_reason"))
```

**Holding reply text (same as WhatsApp):**

```
"Thank you for reaching out. A member of our team will get back to you today."
```

---

## 9. File Structure (New Files)

### Files to Create

| File Path | Responsibility | Language-Agnostic Description |
|-----------|---------------|-------------------------------|
| `engine/api/chat_routes.py` | Widget API routes: session creation, message send, history fetch | FastAPI route handlers for all `/chat/{client_id}/*` endpoints |
| `engine/api/widget_routes.py` | Widget JavaScript delivery: `GET /widget/{client_id}.js` | Serves static JS with inlined `client_id` |
| `engine/api/cors_middleware.py` | CORS validation middleware | Validates `Origin` header against `clients.widget_allowed_origins` |
| `engine/core/widget_handler.py` | Widget message processing pipeline | Orchestrates escalation gate, context builder, agent invocation (mirrors `message_handler.py` structure) |
| `engine/core/session_expiry_job.py` | Session expiry background job | APScheduler job that marks expired sessions every 5 minutes |
| `engine/static/widget.js` | Widget frontend (vanilla JS) | Chat button, chat window, message rendering, localStorage session management |
| `supabase/migrations/010_widget_schema.sql` | Widget database schema | All `CREATE TABLE` and `ALTER TABLE` statements from §2 |

### Existing Files to Modify

| File Path | Change Required |
|-----------|----------------|
| `engine/api/webhook.py` | Add session expiry job to APScheduler (alongside existing follow-up scheduler) |
| `engine/core/context_builder.py` | Add `channel` parameter to `build_system_message()`; adjust system prompt when `channel='widget'` |
| `engine/config/client_config.py` | Add widget config fields to `ClientConfig` dataclass: `widget_enabled`, `widget_primary_color`, `widget_agent_name`, `widget_welcome_message`, `widget_allowed_origins`, `widget_session_ttl_minutes` |
| `engine/core/tools/booking_tools.py` | Add `channel` and `session_id` parameters to `write_booking()` tool; log to `bookings` table with widget context |

### Directory Structure After Implementation

```
engine/
├── api/
│   ├── webhook.py                   # (Modified) WhatsApp webhook + APScheduler setup
│   ├── chat_routes.py               # (New) Widget API routes
│   ├── widget_routes.py             # (New) Widget JS delivery
│   └── cors_middleware.py           # (New) CORS validation
├── core/
│   ├── message_handler.py           # (Existing) WhatsApp message pipeline
│   ├── widget_handler.py            # (New) Widget message pipeline
│   ├── context_builder.py           # (Modified) Add channel parameter
│   ├── session_expiry_job.py        # (New) Session expiry background job
│   └── tools/
│       ├── booking_tools.py         # (Modified) Add channel/session_id params
│       └── ...
├── config/
│   ├── client_config.py             # (Modified) Add widget config fields
│   └── ...
├── integrations/
│   └── ...                          # (No changes)
├── static/
│   └── widget.js                    # (New) Widget frontend (vanilla JS)
└── tests/
    ├── unit/
    │   ├── test_widget_handler.py   # (New) Unit tests for widget pipeline
    │   ├── test_cors_middleware.py  # (New) CORS validation tests
    │   └── test_session_expiry.py   # (New) Session expiry job tests
    └── integration/
        └── test_widget_flow.py      # (New) End-to-end widget tests

supabase/
└── migrations/
    └── 010_widget_schema.sql        # (New) Widget schema migration
```

---

## 10. Open Decisions Resolved

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Session storage: In-memory vs Supabase** | **Supabase (persistent)** | Session continuity requires persistence; `session_id` and `expired_at` must survive Railway restarts. Rate limits can be in-memory (acceptable trade-off). |
| **CORS validation: How to implement** | **Custom FastAPI middleware** | Load `ClientConfig` per request (uses 5-min TTL cache), parse comma-separated `widget_allowed_origins`, validate `Origin` header. Development bypass: `http://localhost:*` when `ENVIRONMENT=development`. |
| **Widget JS: Vanilla vs Preact** | **Vanilla JS (Phase 1)** | Phase 1 UI is simple enough (text-only, 200 lines) to avoid framework overhead. No build pipeline needed. Upgrade to Preact in Phase 2 if complexity increases. |
| **Session recovery: localStorage + history fetch** | **Confirmed** | Widget stores `session_id` in `localStorage` under key `flowai_session_{client_id}`. On page refresh: `GET /history` — if 200, resume; if 410, clear and create new session. |

---

## 11. Constraints and Risks

### Constraints

| Constraint | Impact | Mitigation |
|------------|--------|-----------|
| **No WebSocket in Phase 1** | Typing indicators and real-time sync not possible — widget uses HTTP polling (request/response only) | Acceptable for Phase 1 text-only UI. Upgrade to WebSocket in Phase 2. |
| **No file upload in Phase 1** | Visitor cannot send images or documents | Acceptable — WhatsApp channel supports file upload; widget is a lightweight entry point. Phase 2 adds file upload. |
| **Rate limits in-memory** | Rate limits reset on Railway restart (~once/week) — low-severity abuse vector | Acceptable for Phase 1. Migrate to Redis in Phase 2 if abuse becomes a problem. |
| **No admin UI for escalations** | Founder must manually query Supabase Studio to view widget conversations | Acceptable for Phase 1 (low volume). Phase 2 builds CRM interface. |
| **No cross-channel escalation** | Human agent replies in WhatsApp; visitor in widget sees holding message (no message bridge) | Acceptable for Phase 1 — escalation is one-way alert only. Phase 3 adds cross-channel handoff. |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **CORS bypass via proxy** | Medium | Attacker proxies requests to bypass `Origin` validation | Not mitigable at application layer — require HTTPS and monitor for abuse. Phase 2 adds IP-based rate limiting. |
| **Session ID guessing** | Low | Attacker brute-forces UUID v4 session IDs (2^122 space) | Infeasible (UUID v4 is cryptographically strong). No additional mitigation needed. |
| **Widget JS tampering** | High | Attacker modifies widget JS in browser DevTools to send malicious requests | Not mitigable at client layer — validate all inputs on backend. Do not trust client-side logic. |
| **Cross-channel identity collision** | Low | Two visitors submit same phone number, linking to wrong WhatsApp customer | Rare but possible. Phase 2 adds email+phone composite matching to reduce false positives. |
| **Session expiry job lag** | Medium | Sessions expire up to 5 minutes after TTL threshold (APScheduler interval) | Acceptable delay for Phase 1. Reduce interval to 1 minute in Phase 2 if needed. |

---

## 12. Phase 2 Preparation Notes

The following features are out of scope for Phase 1 but must be architecturally compatible:

### Multi-Client Deployment

- Widget code is already client-agnostic (all client-specific logic via `client_id` path parameter)
- New client onboarding: INSERT into shared `clients` table + add 5 env vars to Railway
- Test multi-client isolation before Phase 2 rollout (acceptance criteria in requirements §9)

### WebSocket Upgrade

- Phase 1 endpoints are stateless (HTTP request/response only)
- Phase 2 adds `WebSocket /chat/{client_id}/ws` endpoint for real-time typing indicators and message sync
- Session recovery via WebSocket reconnection (uses same `session_id` from `localStorage`)

### File Upload

- Phase 2 adds `POST /chat/{client_id}/upload` endpoint for images/documents
- File storage: Supabase Storage or S3 (TBD)
- Requires virus scanning and file size limits (10MB per file)

### Cross-Channel Escalation

- Phase 3 adds **message bridge** — human agent replies in WhatsApp, visitor sees reply in widget
- Requires bidirectional sync between `interactions_log` rows for same `customer_id` across channels
- Webhook for WhatsApp outbound messages (detect when human agent replies) — triggers widget push notification

---

**End of Architecture Document**
