# Embeddable Chat Widget — Requirements Document

**Feature Owner:** `@product-manager`  
**Date Created:** 2026-04-28  
**Last Updated:** 2026-04-29  
**Status:** Draft — Awaiting Architect Review  
**Priority:** High (Strategic Phase)  
**Phase:** Phase 1 MVP (Flow AI website only)  

---

## Direction Check

- **Subject:** Website visitors on `getflowai.co` (and future client websites in Phase 2) who need to ask questions or book services
- **Problem/Threat:** WhatsApp-only contact creates friction — requires app install, phone number sharing, Meta platform dependency; website visitors need immediate, low-friction engagement without leaving the browser
- **Confirmation:** Solution provides the subject (website visitors) with a web-native chat interface that eliminates WhatsApp friction — not a replacement for WhatsApp (that channel stays active), not an admin tool. Cross-channel identity linking (widget visitor ↔ existing WhatsApp customer) is in Phase 1 scope via optional phone capture in the pre-chat form.

---

## 1. Problem Statement

### Why the Chat Widget Exists

Flow AI's current website directs all inquiries to a WhatsApp "Contact Us" button. This creates three barriers to engagement:

1. **Platform friction:** Visitors must have WhatsApp installed and be willing to share their phone number
2. **Trust barrier:** B2B prospects (SME owners) are hesitant to message an unknown business number before qualifying the service
3. **Compliance exposure:** WhatsApp conversations are subject to Meta's terms of service and data residency policies — some clients cannot accept this for their websites

The chat widget provides a **web-native entry point** with:
- Zero app install requirement
- Optional identity capture (anonymous sessions allowed)
- Full data control (client's Supabase, no Meta infrastructure)
- Same AI agent quality as the WhatsApp channel

### Who It Serves

**Primary:** Website visitors on `getflowai.co` (Phase 1), then client websites (Phase 2+)  
**Secondary:** Flow AI team (monitoring widget conversations for product insights)

### What Success Looks Like

| Metric | Target |
|--------|--------|
| Widget engagement rate | 5%+ of website visitors open the widget |
| Conversation completion rate | 70%+ of visitors who send a message receive a reply within 5 seconds |
| Lead qualification | 80%+ of widget escalations have completed the qualification flow |
| Zero cross-client data leakage | 100% data isolation verified by test suite before Phase 2 multi-client rollout |
| PDPA compliance | 100% of pre-chat form submissions include visible data collection notice |

---

## 2. Scope — Phase 1 (MVP)

### In Scope

| Component | Description |
|-----------|-------------|
| **Single-client deployment** | Flow AI website (`getflowai.co`) only — widget serves Kai (Flow AI's lead qualification agent) |
| **Same agent engine** | Reuses `context_builder.py`, `agent_runner.py`, tools, knowledge base — zero duplication |
| **Optional pre-chat form** | Name, email, and phone capture (all skip-able) — visitor can remain anonymous |
| **Cross-channel identity linking** | When visitor submits phone number in pre-chat form, engine queries per-client `customers` table by `phone_number`; if match found, `visitors.customer_id` FK set — linking widget session to existing WhatsApp history |
| **Text-only conversation** | Visitor types messages, agent replies with text — no file upload, no images |
| **Session-based identity** | `session_id` (UUID) stored in browser `localStorage` — replaces `phone_number` as conversation identifier |
| **Escalation gate** | Same `escalation_flag` check as WhatsApp — escalated visitors see holding message, agent does not run |
| **WhatsApp escalation alert** | When agent calls `escalate_to_human` tool, alert sent to founder's WhatsApp (same as WhatsApp channel) |
| **Conversation logging** | All messages logged to per-client `interactions_log` with `channel='widget'` and `session_id` |
| **PDPA data notice** | Pre-chat form displays data collection notice (what, why, retention, deletion contact) before submission |
| **Responsive UI** | Widget works on desktop (1200px+) and mobile (375px+) — button and chat window adapt to screen size |
| **Client branding** | Widget button color, agent name, welcome message configurable via `clients` table (`widget_*` columns) |

### Out of Scope (Phase 1)

| Feature | Deferred To | Rationale |
|---------|-------------|-----------|
| Multi-client widget | Phase 2 | Pilot on Flow AI site first — validate UX, performance, and data isolation before rolling out to paying clients |

| Cross-channel escalation (widget → WhatsApp handoff) | Phase 3 | Requires real-time message bridge and human agent reply routing — Phase 1 escalations are WhatsApp-alert-only |
| File/image upload | Phase 2 | Requires file storage (S3/Supabase Storage), virus scanning, and multimodal LLM support |
| Typing indicators | Phase 2 | Requires WebSocket persistent connection — Phase 1 uses HTTP polling |
| Read receipts | Phase 2 | Requires read state tracking and real-time sync |
| Proactive messages | Phase 4 | Requires page analytics integration (time on page, cart abandonment) and event triggers |
| Multi-language UI | Phase 4 | Requires i18n framework and translation management — agent can respond in any language Claude supports, but widget UI is English-only |

### Phased Rollout (3 Phases)

| Phase | Scope | Primary Goal |
|-------|-------|--------------|
| **Phase 1** | Flow AI website only; single-client pilot; HTTP polling; anonymous sessions | Validate widget UX, backend architecture, and PDPA compliance |
| **Phase 2** | Multi-client rollout (HeyAircon, 5+ clients); embed on client websites; identity linking (email/phone capture) | Prove multi-tenant data isolation; enable client self-service widget config |
| **Phase 3** | Cross-channel escalation (widget → WhatsApp handoff); WebSocket upgrade; file upload | Unified real-time cross-channel experience (identity linking already done in Phase 1) |

---

## 3. User Stories

### Story 1 — Anonymous Visitor Opens Widget

**As a** website visitor on `getflowai.co`,  
**I want to** click the chat widget button and start a conversation without providing my name or email,  
**So that** I can ask quick questions anonymously before deciding to engage further.

**Acceptance Criteria:**
- [ ] Chat widget button visible in bottom-right corner of every page on `getflowai.co`
- [ ] Click opens chat window (400×600px default, responsive to mobile screens)
- [ ] Pre-chat form displays with Name and Email fields, plus "Skip" button
- [ ] Click "Skip" closes form and shows message input field immediately
- [ ] Visitor can type and send message without filling any form fields
- [ ] Agent reply appears within 5 seconds for 95th percentile requests
- [ ] `session_id` stored in browser `localStorage` under key `flowai_session_flow-ai`
- [ ] No `phone_number`, `ip_address`, or device fingerprint stored in database when visitor skips form

### Story 2 — Visitor Submits Pre-Chat Form

**As a** website visitor who wants personalized follow-up,  
**I want to** provide my name and email in the pre-chat form before starting the conversation,  
**So that** the agent can address me by name and I can receive follow-up if I leave the conversation.

**Acceptance Criteria:**
- [ ] Pre-chat form displays PDPA data collection notice above the submit button (exact text in §6)
- [ ] Notice text is visible without scrolling (fixed at bottom of form)
- [ ] Name and Email fields accept text input (Email validated as valid email format)
- [ ] Submit button disabled until Email is valid format
- [ ] On submit: form data saved to `visitors` table (new table) with `session_id`, `name`, `email`, `phone`, `created_at`
- [ ] If phone submitted: engine queries `customers` table for matching `phone_number`; if found, `visitors.customer_id` FK set
- [ ] Agent's first message includes visitor's name: "Hi {name}, I'm Kai..."
- [ ] Conversation continues identically to anonymous flow after form submission

### Story 3 — Visitor Sends Message and Receives Reply

**As a** website visitor (anonymous or identified),  
**I want to** type a message in the widget and receive an agent reply,  
**So that** I can ask questions, get pricing, or book a service.

**Acceptance Criteria:**
- [ ] Message input field accepts text up to 2000 characters
- [ ] Press Enter or click Send button submits message
- [ ] Message appears immediately in chat window (right-aligned, visitor bubble)
- [ ] Loading indicator appears while waiting for agent reply
- [ ] Agent reply appears within 5 seconds (95th percentile)
- [ ] Agent message displayed left-aligned with "Kai" label and timestamp
- [ ] Conversation history scrolls (newest messages at bottom)
- [ ] `POST /chat/flow-ai/message` called with `{"session_id": "...", "message": "..."}`
- [ ] Inbound and outbound messages logged to `interactions_log` with `channel='widget'`, `session_id`, `direction='inbound'|'outbound'`

### Story 4 — Visitor Triggers Escalation

**As a** website visitor who asks a question outside the agent's scope (e.g., "Can you integrate with Salesforce?"),  
**I want to** the agent to recognize the limitation and route me to a human,  
**So that** I don't get stuck in an unhelpful loop.

**Acceptance Criteria:**
- [ ] Agent calls `escalate_to_human` tool when visitor query is out of scope or visitor explicitly requests human
- [ ] Agent's reply includes: "Let me connect you with our founder — they'll get back to you within a few hours."
- [ ] Backend sets `escalation_flag=TRUE` in `visitors` table for `session_id`
- [ ] WhatsApp alert sent to founder's phone (`human_agent_number` from `clients` table):
  ```
  🚨 Widget escalation — Flow AI

  Session: {session_id}
  Name: {name or "Anonymous"}
  Email: {email or "Not provided"}
  Last message: "{message_text}"
  Conversation: https://getflowai.co/admin/session/{session_id}
  ```
- [ ] Subsequent messages from visitor display holding message: "A member of our team will get back to you today."
- [ ] Agent does not run for escalated sessions (same gate logic as WhatsApp)

### Story 5 — Flow AI Team Monitors Widget Conversations

**As a** Flow AI founder,  
**I want to** receive WhatsApp alerts when widget visitors escalate,  
**So that** I can follow up with qualified leads directly.

**Acceptance Criteria:**
- [ ] Escalation alert received on WhatsApp within 10 seconds of agent calling `escalate_to_human`
- [ ] Alert includes session ID, visitor name/email (or "Anonymous"/"Not provided"), last message, and admin link
- [ ] Admin link (`https://getflowai.co/admin/session/{session_id}`) opens Supabase Studio query filtered by `session_id` (manual URL construction — no admin UI in Phase 1)
- [ ] Founder can view full conversation history in `interactions_log` filtered by `session_id`

### Story 6 — Visitor Session Expires After Inactivity

**As a** website visitor who opened the widget 2 hours ago but never sent a message,  
**I want to** my session to expire automatically,  
**So that** stale sessions don't clutter the database.

**Acceptance Criteria:**
- [ ] Session created on first widget open: `POST /chat/flow-ai/session` returns `session_id` and stores in `sessions` table
- [ ] `last_active_at` updated on every message sent by visitor
- [ ] Backend marks session as expired (`expired_at=NOW()`) if `last_active_at` > 30 minutes ago (configurable via `clients.widget_session_ttl_minutes`, default 30)
- [ ] Expired sessions: agent does not have access to conversation history older than expiration time
- [ ] Visitor who returns after expiration receives new `session_id` (fresh conversation)

---

## 4. Functional Requirements

### Widget UI (Frontend)

**FR-001: Widget Button**
- Widget button fixed to bottom-right corner (20px from right, 20px from bottom)
- Button displays Flow AI logo (SVG) or custom icon (configurable via `clients.widget_icon_url`)
- Button background color from `clients.widget_primary_color` (default `#4F46E5` — Indigo 600)
- Button size: 60×60px on desktop, 56×56px on mobile
- Hover state: button scales to 105% and shows tooltip "Chat with Kai"
- Click opens chat window

**FR-002: Chat Window**
- Opens as overlay (400×600px default, responsive: 100% width on <768px screens)
- Header: displays agent name ("Kai" from `clients.widget_agent_name`), close button (X)
- Body: message list (scrollable, newest at bottom), loading indicator (animated dots when waiting for reply)
- Footer: message input field (text, max 2000 chars), Send button
- Close button (X) hides chat window but does not delete `session_id` — visitor can reopen and resume conversation

**FR-003: Pre-Chat Form**
- Displays on first widget open if visitor has no `session_id` in `localStorage`
- Fields: Name (text, optional), Email (text, email format validation, optional), Phone (text, optional, E.164 format hint)
- PDPA data collection notice displayed above Submit button (exact text in §6)
- Buttons: "Submit" (saves form → starts conversation), "Skip" (bypasses form → starts anonymous conversation)
- If visitor clicks "Skip": `session_id` generated, no `visitors` row created, conversation starts immediately
- If visitor submits form: `session_id` generated, `visitors` row inserted with `name`, `email`, `phone`, `session_id`, conversation starts
- If phone submitted: query `customers` table (`SELECT id, phone_number, customer_name FROM customers WHERE phone_number = $1`); if match found, set `visitors.customer_id = customers.id`

**FR-004: Message Rendering**
- Visitor messages: right-aligned, blue bubble background, white text
- Agent messages: left-aligned, light gray bubble background, black text, "Kai" label above bubble, timestamp below
- Timestamps: relative time ("Just now", "2 min ago", "1 hour ago") until 24 hours, then absolute date
- Markdown support (Phase 2) — Phase 1 plain text only
- URLs in agent messages auto-linked (clickable)

**FR-005: Mobile Responsive**
- Screen <768px: chat window fullscreen (100vw × 100vh)
- Message bubbles max-width 80% of window width
- Input field expands to fill footer width minus Send button
- Virtual keyboard push: chat window body scrolls to keep input field visible

**FR-006: Loading/Typing Indicator**
- When visitor sends message: display "Kai is typing..." indicator (3 animated dots) in message list
- Indicator disappears when agent reply received
- Timeout: if no reply after 10 seconds, show error message "Taking longer than usual — please wait or try again"

**FR-007: Escalation State Display**
- When `escalation_flag=TRUE` for session: display banner at top of chat window: "A team member will get back to you soon."
- Input field disabled (grayed out, placeholder text: "Waiting for team response...")
- Send button disabled
- Visitor can still view conversation history but cannot send new messages

### Widget API (Backend)

**FR-008: Create Session Endpoint**
- **Route:** `POST /chat/{client_id}/session`
- **Request Body:** `{}` (empty — session_id generated server-side)
- **Response:** `{"session_id": "abc-123-...", "welcome_message": "Hi! I'm Kai, Flow AI's assistant..."}`
- **Logic:**
  1. Generate `session_id` (UUID v4)
  2. INSERT into `sessions` table: `(session_id, client_id, created_at, last_active_at)`
  3. Fetch `clients.widget_welcome_message` from shared Supabase
  4. Return `session_id` and welcome message
- **Error handling:** If `clients.widget_enabled=FALSE` for `client_id`, return `403 Forbidden` with message "Widget not enabled for this client"

**FR-009: Send Message Endpoint**
- **Route:** `POST /chat/{client_id}/message`
- **Request Body:** `{"session_id": "abc-123-...", "message": "How much does it cost?"}`
- **Response:** `{"reply": "Flow AI pricing starts at...", "escalated": false}`
- **Logic:**
  1. Validate `session_id` exists in `sessions` table and `expired_at IS NULL`
  2. Update `sessions.last_active_at = NOW()`
  3. Log inbound message to `interactions_log` (`channel='widget'`, `session_id`, `message_text`, `direction='inbound'`)
  4. Check escalation gate: query `visitors` table by `session_id` — if `escalation_flag=TRUE`, return holding reply immediately (do not invoke agent)
  5. Fetch conversation history (last 20 messages from `interactions_log` WHERE `session_id`)
  6. Call `context_builder.py` → `agent_runner.py` (same as WhatsApp flow)
  7. Log outbound message to `interactions_log` (`direction='outbound'`)
  8. Return agent reply
- **Error handling:** If session expired, return `410 Gone` with message "Session expired — please refresh and start a new conversation"

**FR-010: Fetch Conversation History Endpoint**
- **Route:** `GET /chat/{client_id}/history?session_id={session_id}`
- **Response:** `{"messages": [{"role": "user"|"assistant", "text": "...", "timestamp": "2026-04-28T10:30:00Z"}, ...]}`
- **Logic:**
  1. Query `interactions_log` WHERE `session_id` ORDER BY `created_at` DESC LIMIT 50
  2. Transform to frontend format: `direction='inbound'` → `role='user'`, `direction='outbound'` → `role='assistant'`
  3. Return messages array
- **Error handling:** If `session_id` not found, return `404 Not Found`

**FR-011: Widget JavaScript Endpoint**
- **Route:** `GET /widget/{client_id}.js`
- **Response:** JavaScript file (`Content-Type: application/javascript`)
- **Logic:**
  1. Serve static file from `engine/static/widget.js`
  2. Inline `client_id` into script as `window.FLOWAI_CLIENT_ID = '{client_id}'`
  3. Cache-Control header: `public, max-age=3600` (1 hour)
- **Error handling:** If `client_id` not found in `clients` table or `widget_enabled=FALSE`, return `404 Not Found`

**FR-012: CORS Origin Validation**
- All `/chat/{client_id}/*` endpoints MUST validate `Origin` header against `clients.widget_allowed_origins` (comma-separated list of domains)
- If `Origin` not in allowed list, return `403 Forbidden`
- Example: `clients.widget_allowed_origins = 'https://getflowai.co,https://www.getflowai.co'`
- Wildcard (`*`) not allowed in Phase 1 — explicit domain list only

**FR-013: Rate Limiting**
- **Per session:** Max 10 messages per minute
- **Per IP:** Max 50 messages per hour (anonymous sessions)
- If rate limit exceeded, return `429 Too Many Requests` with `Retry-After` header (seconds until reset)
- Rate limit state stored in-memory (lost on Railway restart — acceptable for Phase 1)

**FR-014: Session Timeout**
- Background job (APScheduler, runs every 5 minutes) queries `sessions` WHERE `last_active_at < NOW() - INTERVAL '{widget_session_ttl_minutes} minutes'` AND `expired_at IS NULL`
- For each expired session: UPDATE `sessions` SET `expired_at = NOW()`
- Expired sessions: agent cannot access conversation history (filtered out in context builder query)

### Data Model

**FR-015: New `sessions` Table**

```sql
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(client_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expired_at TIMESTAMPTZ,
    user_agent TEXT,
    ip_address INET  -- NOT stored in Phase 1 (PDPA — only if visitor submits form with explicit consent)
);

CREATE INDEX idx_sessions_client_id ON sessions(client_id);
CREATE INDEX idx_sessions_last_active ON sessions(last_active_at) WHERE expired_at IS NULL;
CREATE INDEX idx_sessions_expired ON sessions(expired_at) WHERE expired_at IS NOT NULL;
```

**FR-016: New `visitors` Table** (Replaces Cookies for Identity)

```sql
CREATE TABLE visitors (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    client_id TEXT NOT NULL REFERENCES clients(client_id),
    name TEXT,
    email TEXT,
    phone TEXT,                          -- Optional; used for cross-channel identity lookup
    customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,  -- Set if phone matched existing WhatsApp customer
    escalation_flag BOOLEAN NOT NULL DEFAULT FALSE,
    escalation_reason TEXT,
    escalated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_visitors_session_id ON visitors(session_id);
CREATE INDEX idx_visitors_email ON visitors(email) WHERE email IS NOT NULL;
CREATE INDEX idx_visitors_customer_id ON visitors(customer_id) WHERE customer_id IS NOT NULL;
```

**Cross-channel identity matching logic (inline at form submission):**
1. Visitor submits pre-chat form with phone number (e.g. `+6591234567`)
2. `POST /chat/{client_id}/session` (or a new `POST /chat/{client_id}/identify` endpoint) queries the **per-client** Supabase: `SELECT id FROM customers WHERE phone_number = $1 LIMIT 1`
3. If a row is found: `UPDATE visitors SET customer_id = $1 WHERE session_id = $2`
4. `context_builder.py` checks `visitors.customer_id`; if set, fetches prior `interactions_log` rows for that `phone_number` and prepends to conversation context (recent history, last 5 exchanges)
5. Agent is aware the visitor is a known customer — adjusts response accordingly (no need to re-ask for service history)

**FR-017: Schema Changes to `interactions_log`**

```sql
-- Add columns (all nullable for backward compatibility with WhatsApp rows)
ALTER TABLE interactions_log ADD COLUMN channel TEXT NOT NULL DEFAULT 'whatsapp';
ALTER TABLE interactions_log ADD COLUMN session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL;

-- Modify phone_number to nullable (widget messages have no phone)
ALTER TABLE interactions_log ALTER COLUMN phone_number DROP NOT NULL;

-- Add index for widget history queries
CREATE INDEX idx_interactions_log_session_id ON interactions_log(session_id, created_at DESC);
```

**FR-018: Schema Changes to `bookings`**

```sql
-- Track which channel the booking came from
ALTER TABLE bookings ADD COLUMN channel TEXT NOT NULL DEFAULT 'whatsapp';
ALTER TABLE bookings ADD COLUMN session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL;

CREATE INDEX idx_bookings_session_id ON bookings(session_id);
```

**FR-019: Schema Changes to `clients` Table (Shared Supabase)**

```sql
-- Widget feature flag and config
ALTER TABLE clients ADD COLUMN widget_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE clients ADD COLUMN widget_primary_color TEXT DEFAULT '#4F46E5';
ALTER TABLE clients ADD COLUMN widget_agent_name TEXT DEFAULT 'Assistant';
ALTER TABLE clients ADD COLUMN widget_welcome_message TEXT DEFAULT 'Hi! How can I help you today?';
ALTER TABLE clients ADD COLUMN widget_allowed_origins TEXT;  -- Comma-separated domains
ALTER TABLE clients ADD COLUMN widget_session_ttl_minutes INTEGER NOT NULL DEFAULT 30;
```

### Agent Behavior

**FR-020: Channel Context in System Prompt**
- `context_builder.py` MUST include channel information in system message:
  ```
  You are responding via the [WhatsApp channel / Flow AI website chat widget].
  ```
- Agent behavior adjusts based on channel:
  - Widget: No phone number available — agent cannot ask "What's your contact number?" if visitor is anonymous (check if `visitors.name` exists)
  - Widget: Booking confirmation SMS not sent — agent says "You'll receive email confirmation" instead (if visitor provided email)

**FR-021: Escalation Alert Format (Widget)**
- When agent calls `escalate_to_human` tool from widget conversation:
  ```
  🚨 Widget escalation — Flow AI

  Session: {session_id}
  Name: {visitors.name or "Anonymous"}
  Email: {visitors.email or "Not provided"}
  Last message: "{message_text}"
  ```
- Alert sent via `meta_whatsapp.send_message()` to `clients.human_agent_number`

**FR-022: Holding Reply (Escalated Sessions)**
- Holding reply text (shown to visitor when `escalation_flag=TRUE`):
  ```
  Thank you for reaching out. A member of our team will get back to you today.
  ```
- Same text as WhatsApp holding reply (`HOLDING_REPLY` constant in `message_handler.py`)

---

## 5. Non-Functional Requirements

### Performance

**NFR-001: Latency**
- Agent reply delivered within **5 seconds** for 95th percentile requests
- Widget button loads within **1 second** of page load (async script tag)
- Widget JavaScript bundle size: **<50KB minified** (Phase 1 vanilla JS, zero framework dependencies)

**NFR-002: Availability**
- **99.9% uptime** (same as WhatsApp engine)
- Railway health check (`GET /health`) must return 200 OK within 2 seconds

### Security

**NFR-003: CORS Origin Validation**
- All `/chat/{client_id}/*` endpoints enforce `Origin` header check
- `clients.widget_allowed_origins` is explicit domain list (no wildcards)
- Prevents widget embedding on unauthorized domains

**NFR-004: Session Token Security**
- `session_id` MUST be UUID v4 (not guessable, not sequential)
- Session tokens stored in browser `localStorage` only (not in cookies — avoids CSRF)
- HTTPS-only in production (Railway enforces this)

**NFR-005: No IP Storage for Anonymous Sessions**
- If visitor skips pre-chat form: `sessions.ip_address` MUST remain NULL
- IP address only stored if visitor explicitly submits form (PDPA consent implied by form submission)

**NFR-006: SQL Injection Prevention**
- All database queries use parameterized queries (Supabase client handles this)
- No raw SQL string interpolation

**NFR-007: XSS Prevention**
- Widget frontend sanitizes all agent reply text before rendering (escape HTML tags)
- URLs auto-linked but `<script>` tags stripped

### PDPA Compliance (Singapore)

**NFR-008: Data Collection Notice**
- Pre-chat form MUST display notice before submission (exact text in §6)
- Notice visible without scrolling (fixed at bottom of form)

**NFR-009: Data Retention**
- Widget conversations retained for **12 months** after `sessions.last_active_at`
- After 12 months: `sessions`, `visitors`, and `interactions_log` rows with `session_id` purged via scheduled job

**NFR-010: Right to Deletion**
- Visitor can request deletion by emailing `privacy@flowai.co` (email address in PDPA notice)
- Manual deletion process (Phase 1) — founder runs SQL: `DELETE FROM sessions WHERE session_id = '...'` (cascades to `visitors` and `interactions_log`)

**NFR-011: No PII for Anonymous Sessions**
- Anonymous sessions (skipped pre-chat form): `visitors` table has no row, `sessions.ip_address=NULL`, `interactions_log` contains only message text
- Message text may contain PII (visitor types name/email in message) — PDPA notice covers this ("messages you send")

### Browser Support

**NFR-012: Desktop Browsers**
- Chrome (last 2 major versions)
- Safari (last 2 major versions)
- Firefox (last 2 major versions)
- Edge (last 2 major versions)

**NFR-013: Mobile Browsers**
- iOS Safari (iOS 15+)
- Android Chrome (Android 10+)

---

## 6. PDPA Data Collection Notice — Draft Copy

**Display location:** Pre-chat form, above Submit button, fixed position  
**Character count:** 58 words (within 60-word target)

```
By submitting this form, you consent to Flow AI collecting your name, email, 
phone number, and messages to respond to your inquiry. We retain this data 
for 12 months. You may request deletion anytime by emailing privacy@flowai.co. 
For details, see our Privacy Policy.
```

**Privacy Policy link:** `https://getflowai.co/privacy` (must be live before widget goes live)

---

## 7. Embed Integration Spec

### How Clients Embed the Widget (Phase 2+)

**Phase 1 (Flow AI website only):**

Add to `<head>` or before closing `</body>` tag on `getflowai.co`:

```html
<script>
  window.FlowAIWidget = {
    clientId: "flow-ai"
  };
</script>
<script src="https://flow-engine.railway.app/widget/flow-ai.js" async></script>
```

**Phase 2 (multi-client):**

Each client uses their own `client_id`:

```html
<script>
  window.FlowAIWidget = {
    clientId: "hey-aircon",  // Client-specific
    primaryColor: "#FF6B35",  // Optional: override widget button color
    agentName: "Sarah",       // Optional: override agent display name
    welcomeMessage: "Hi! Need aircon servicing?"  // Optional: override welcome message
  };
</script>
<script src="https://flow-engine.railway.app/widget/hey-aircon.js" async></script>
```

### Configuration Options

| Property | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `clientId` | String | ✅ Yes | — | Client identifier (must match `clients.client_id` in Supabase) |
| `primaryColor` | String | ❌ No | `#4F46E5` | Hex color for widget button and header (e.g., `#FF6B35`) |
| `agentName` | String | ❌ No | `clients.widget_agent_name` | Display name for agent (e.g., "Kai", "Sarah") |
| `welcomeMessage` | String | ❌ No | `clients.widget_welcome_message` | First message shown when widget opens |

### Widget JavaScript Delivery

- **URL pattern:** `https://{railway-domain}/widget/{client_id}.js`
- **Served by:** FastAPI `StaticFiles` mount at `app.mount("/widget", StaticFiles(directory="engine/static"))`
- **File location:** `engine/static/widget.js` (single file, vanilla JS, minified)
- **Inline client config:** Script injects `window.FLOWAI_CLIENT_ID = '{client_id}'` at runtime
- **Cache policy:** `Cache-Control: public, max-age=3600` (1 hour) — widget updates propagate within 1 hour of deploy

**No CDN in Phase 1.** Railway serves static files directly. Migrate to CDN (Cloudflare, AWS CloudFront) when widget bandwidth exceeds 100GB/month (Phase 2+).

---

## 8. Open Questions (For Architect)

### [OPEN: Session Storage — In-Memory vs Persistent]

**Question:** Should session state (rate limits, active sessions count) be stored in-memory (lost on Railway restart) or in Supabase (persistent)?

**Recommendation:** **In-memory for Phase 1** (acceptable risk — Railway restarts are rare, <5 min downtime). Migrate to Redis in Phase 2 if session state loss becomes a problem (e.g., rate limits reset on every deploy).

**Impact if deferred:** Visitors who hit rate limit can bypass by waiting for Railway restart (low-severity abuse vector).

---

### [OPEN: CORS — How to Validate `Origin` Header]

**Question:** How does the engine validate that the `Origin` header matches `clients.widget_allowed_origins` for the `client_id`?

**Recommendation:** 
1. Parse `clients.widget_allowed_origins` (comma-separated string) into list of allowed domains
2. On every `POST /chat/{client_id}/message`, extract `Origin` from request headers
3. If `Origin` not in allowed list, return `403 Forbidden` with message "Widget not authorized for this domain"
4. Middleware applies to all `/chat/*` routes (FastAPI `@app.middleware("http")`)

**Example allowed origins:** `https://getflowai.co,https://www.getflowai.co` (with and without `www` subdomain)

**Edge case:** Local development — allow `http://localhost:3000` in `widget_allowed_origins` for dev/staging client rows

---

### [OPEN: Widget JS Bundling — Vanilla JS vs Lightweight Framework]

**Question:** Should the widget frontend be vanilla JavaScript (no framework) or use a lightweight framework like Preact (~3KB)?

**Recommendation:** **Vanilla JS for Phase 1** to avoid build pipeline complexity (no Webpack, no Babel, no npm dependencies). Widget is simple enough (200 lines of JS) that a framework adds unnecessary overhead.

**Phase 2 upgrade path:** If widget UI becomes complex (file upload, typing indicators, WebSocket reconnection logic), migrate to Preact or Lit Element.

**Impact if vanilla JS:** Longer development time for interactive features (manual DOM manipulation) — acceptable for Phase 1 text-only UI.

---

### [OPEN: Session Recovery After Page Refresh]

**Question:** How does the widget reconnect if the visitor refreshes the page?

**Recommendation:** **`localStorage` persistence:**
1. On first widget open: `POST /chat/{client_id}/session` generates `session_id`
2. Widget stores in `localStorage` under key `flowai_session_{client_id}`
3. On page refresh: widget checks `localStorage` for existing `session_id`
4. If found and not expired (`GET /chat/{client_id}/history?session_id={session_id}` returns 200), resume conversation
5. If expired (returns `410 Gone`), clear `localStorage` and create new session

**Edge case:** Visitor clears `localStorage` manually → treated as new session (fresh conversation).

---

### [OPEN: How to Handle Escalation State Sync]

**Question:** When a visitor sends a message while escalated, how does the widget know to display holding message without invoking agent?

**Recommendation:** **Escalation flag in API response:**
1. `POST /chat/{client_id}/message` always returns `{"reply": "...", "escalated": true|false}`
2. If `escalated=true`, widget displays holding banner and disables input field
3. Backend checks `visitors.escalation_flag` before agent invocation (same gate logic as WhatsApp)
4. Widget polls `GET /chat/{client_id}/status?session_id={session_id}` every 30 seconds to detect when escalation is cleared (Phase 2 — Phase 1 escalation is permanent until session expires)

**Phase 1 simplification:** Escalation is permanent for the session — visitor must close widget and start new session to talk to agent again.

---

## 9. Acceptance Criteria (Phase 1 Gate)

Before Phase 2 (multi-client rollout) can begin, the following must be verified:

### Functional Completeness
- [ ] Widget live on `getflowai.co` (embedded on homepage, pricing page, about page)
- [ ] 20+ real conversations logged in `flow-ai-crm` Supabase with `channel='widget'`
- [ ] Agent response quality matches WhatsApp (assessed by founder review of 20 conversations)
- [ ] Escalation flow tested end-to-end: widget visitor triggers escalation → holding message displayed → WhatsApp alert sent to founder

### Data Isolation & Security
- [ ] Zero cross-client data leakage confirmed by test suite (simulate widget for `client_id=flow-ai` and `client_id=test-client`, verify no `session_id` collision, no conversation history cross-contamination)
- [ ] CORS origin validation working: embed widget on `test-domain.com` (not in allowed origins) → POST `/chat/flow-ai/message` returns `403 Forbidden`
- [ ] Anonymous sessions: visitor skips pre-chat form → `visitors` table has no row, `sessions.ip_address=NULL`
- [ ] Cross-channel identity: visitor submits form with known WhatsApp phone → `visitors.customer_id` set; agent context includes prior WhatsApp interaction history
- [ ] Cross-channel identity: visitor submits form with unknown phone → `visitors.customer_id=NULL`, conversation starts fresh

### Compliance
- [ ] PDPA notice visible on pre-chat form before submission
- [ ] Notice text matches §6 exactly (58 words, privacy email, retention period stated)
- [ ] Privacy Policy live at `https://getflowai.co/privacy`

### Performance
- [ ] Agent reply latency 95th percentile <5 seconds (measured over 50 conversations)
- [ ] Widget JavaScript bundle size <50KB minified
- [ ] Widget button loads within 1 second of page load (async script tag)

### Phase 2 Readiness
- [ ] Widget code fully client-agnostic (no hardcoded `flow-ai` references in `engine/` code — all via `client_id` route param)
- [ ] Multi-client database schema tested: create test client (`client_id=test-client`), insert row in shared `clients` table with `widget_enabled=TRUE`, add `TEST_CLIENT_SUPABASE_URL` and `TEST_CLIENT_SUPABASE_SERVICE_KEY` env vars, send test message via widget, verify conversation logged to test client's Supabase

---

## Appendix A: Three-Phase Roadmap

| Phase | Timeline | Scope | Success Metrics |
|-------|----------|-------|-----------------|
| **Phase 1** | Week 1–3 | Flow AI website only; single-client pilot; HTTP polling; anonymous sessions | 20+ widget conversations logged; zero escalation failures; PDPA notice visible |
| **Phase 2** | Week 4–8 | Multi-client rollout (HeyAircon + 5 clients); embed on client websites; identity linking (email/phone capture); WebSocket upgrade | 3 clients live; 100+ conversations; 95th percentile latency <3 seconds |
| **Phase 3** | Week 9–12 | Cross-channel escalation (widget → WhatsApp handoff); unified conversation history across channels | 1 client using cross-channel escalation; human agent replies in WhatsApp, customer sees in widget |

---

## Appendix B: Widget vs WhatsApp Feature Comparison

| Feature | WhatsApp Channel | Widget Channel (Phase 1) | Widget Channel (Phase 2+) |
|---------|------------------|--------------------------|---------------------------|
| **Identity** | Phone number (E.164) | Anonymous session (UUID) | Email/phone capture → link to WhatsApp |
| **Conversation history** | Tied to phone; persistent indefinitely | Tied to session; expires after 30 min idle | Unified across channels (if identity linked) |
| **Escalation handoff** | Human replies in WhatsApp thread | WhatsApp alert → visitor sees holding message | Widget → WhatsApp bridge (human replies, visitor sees in widget) |
| **Booking confirmation** | SMS + WhatsApp message | Email only (if visitor provided email) | SMS + email + widget message |
| **File upload** | ✅ Images, documents, location | ❌ Text only | ✅ Images, documents |
| **Typing indicators** | ✅ Native WhatsApp | ❌ Basic loading dots | ✅ Real-time (WebSocket) |
| **Push notifications** | ✅ WhatsApp push | ❌ None | ✅ Browser push API |
| **Compliance** | Meta WhatsApp Business Policy | PDPA Singapore (full control) | PDPA Singapore (full control) |

---

**End of Requirements Document**
