# Flow AI — Project CLAUDE.md

## What this project is

Flow AI is a vertical AI agent platform for service SMEs in SEA. It automates customer engagement, booking, and CRM via WhatsApp. The primary channel is Meta Cloud API (WhatsApp Business).

**Pilot client:** HeyAircon — Singapore aircon servicing company.
**Current state (as of April 2026):** Phase 1 MVP in progress. Components A–C running on n8n + Railway. Components D–E pending Meta credentials. Migration to Python engine planned — n8n build continues until Python engine is verified in production.
**Migration target:** Replace n8n with a Flow AI-owned Python/FastAPI orchestration engine.

---

## Tech Stack (locked decisions)

| Layer | Choice | Notes |
|-------|--------|-------|
| Orchestration engine | FastAPI (Python, async) | Replaces n8n |
| LLM | Claude claude-sonnet-4-6 (Anthropic SDK) | Direct SDK — no LangChain |
| Database | Supabase (Postgres) | All client data + shared config DB |
| WhatsApp | Meta Cloud API direct | No BSP (no 360dialog) |
| Calendar | Google Calendar API (service account) | Add-only from agent |
| Deployment | Railway | Engine as a new service alongside n8n during transition |
| Observability | Langfuse (planned) | Agent trace monitoring and cost tracking |
| Testing | pytest + pytest-asyncio + httpx | Standard async Python stack |

**Do not use LangChain.** Use the Anthropic SDK directly. The agent loop is simple enough to own explicitly.

---

## Key Design Principles

### Context engineering
Business data (services, pricing, policies) lives in Supabase `config` and `policies` tables — never hardcoded in prompts. The `context_builder` fetches these at runtime before every Claude call. Client updates content in Supabase Studio. Zero code changes needed for content updates.

### Multi-client isolation
The engine is client-agnostic. Client config is loaded at runtime by `client_id` from the webhook path (`POST /webhook/whatsapp/{client_id}`).

**Hybrid config approach (decided April 2026):**
- Non-sensitive fields (`meta_phone_number_id`, `meta_verify_token`, `human_agent_number`, `google_calendar_creds`, `is_active`) → shared Flow AI Supabase `clients` table
- High-sensitivity secrets (`meta_whatsapp_token`, `supabase_url`, `supabase_service_key`) → Railway env vars, namespaced by client (`{CLIENT_ID_UPPER}_{VAR}`)
- Cache `clients` table lookups in-process (5-min TTL minimum) — shared config DB cannot be a per-request dependency
- Migration path: move secrets to a secrets manager (AWS/GCP) at 10–20 clients

Adding a new client = INSERT into `clients` table + add 3 env vars to Railway. No engine changes. No redeploy for non-secret config updates.

### Escalation gate
The escalation gate (`customers.escalation_flag`) is a hard programmatic check that runs before the agent. If true: send holding reply, log, stop. The agent never decides whether it is escalated. This is not configurable.

### Calendar write rules
The agent adds calendar events only. It never modifies or deletes. All changes go through human escalation.

### n8n preservation rule
All n8n build documents are living references — do not archive or modify them until the Python engine is verified in production and the Meta webhook cutover is confirmed. If the migration is scrapped, n8n docs must be sufficient to deliver the full MVP.

---

## Folder Structure

```
engine/                    ← Python orchestration engine (all clients, no client-specific logic)
  core/
    agent_runner.py        # Claude agent loop (tool use handling)
    context_builder.py     # assembles system_message from Supabase config/policies
    message_handler.py     # inbound message orchestration (escalation gate → context → agent)
    tools/                 # tool definitions (check_calendar, create_event, write_booking, escalate)
  integrations/
    meta_whatsapp.py       # Meta Cloud API (send message, webhook verification)
    supabase_client.py     # Supabase reads/writes
    google_calendar.py     # Calendar availability + event creation
  api/
    webhook.py             # FastAPI app — POST + GET /webhook/whatsapp/{client_id}
  config/
    settings.py            # pydantic-settings env var loading

docs/                      ← agent-owned handoff directory
  status_log.md            # chief-of-staff
  requirements/            # product-manager
  architecture/            # software-architect
  test-plan/               # sdet-engineer
  ux-ui-spec/              # ux-ui-designer (Phase 2 CRM build)
  planning/                # planner

clients/
  hey-aircon/
    plans/build/           # n8n architecture reference + component build guides (preserve until migration)
    plans/                 # mvp_scope.md, proj_plan.md
    product/               # PRD, persona, knowledge base
    website/               # static HTML site

Product/docs/              ← platform-level PRDs and standards (rename to platform/ eventually)
.flow/                     ← agent templates, task queue, onboarding guide
```

---

## Agent-to-File Routing

| Task | Read first |
|------|-----------|
| Building or modifying the WhatsApp agent (n8n) | `clients/hey-aircon/plans/build/00_architecture_reference.md` |
| Understanding Phase 1 scope and Supabase schemas | `clients/hey-aircon/plans/mvp_scope.md` |
| Platform vision and 4-product module map | `Product/docs/00_Master_Project_Document.md` |
| AI agent tool design, context engineering, flows | `Product/docs/PRD-02_AI_WhatsApp_Agent.md` |
| Agent persona and tone | `clients/hey-aircon/product/persona.md` |
| Safety guardrails and prompt injection rules | `Product/docs/safety-guardrails.md` |
| Knowledge base format and standards | `Product/docs/knowledge-schema.md`, `Product/docs/knowledge-standards.md` |
| Python engine architecture (once created) | `docs/architecture/00_platform_architecture.md` |
| Current agent task queue | `.flow/tasks/active.md`, `.flow/tasks/blocked.md` |
| Client onboarding process | `.flow/onboarding.md` |

---

## Python Conventions

- All async. Use `async def` and `await` throughout.
- Functional patterns over classes. Classes only for domain models.
- Pydantic models for all request/response types and config.
- Error handling on every external call (Meta API, Supabase, Google Calendar). Never let an exception reach the webhook response — Meta must always receive a `200 OK` immediately.
- Tests live alongside implementation in `engine/tests/`.
- No hardcoded client data anywhere in `engine/`. Everything from env vars or Supabase.
- Tool definitions are dicts in the Anthropic tools format. Tool functions are plain async Python functions. Keep them separate.

---

## Hard Rules

- Never dispatch `@software-engineer` directly. All implementation goes through `@sdet-engineer`.
- Never build client-specific logic inside `engine/`. Client isolation belongs in config only.
- Never modify or delete Google Calendar events from the agent. Add only.
- The escalation gate is a hard programmatic check — never an agent decision.
- All Claude calls go through the context builder first. Never call Claude with a hardcoded system prompt.
- Supabase is the only write target for business data. Google Sheets is read-only sync mirror if used at all.
- n8n build docs (`clients/hey-aircon/plans/build/`) are preserved and untouched until Python migration is confirmed live in production.

---

## Current Blockers (as of 2026-04-15)

| Blocker | Impact |
|---------|--------|
| Meta dev account pending | Blocks real WhatsApp testing and n8n Components D/E |
| Supabase migration in progress | Must complete before Component E (escalation tool) build |
| Python engine not yet built | Migration planning complete; build starts after n8n D/E confirmed |

---

## n8n → Python Migration Status

| Phase | Status |
|-------|--------|
| n8n Components A–C | Built and running on Railway |
| n8n Component D (booking tools) | Pending Meta credentials |
| n8n Component E (escalate-to-human) | Pending Supabase migration + Meta credentials |
| Python engine: architecture design | Next — dispatch `@software-architect` with `00_architecture_reference.md` as input |
| Python engine: build | After n8n D/E are confirmed working |
| Python engine: parallel test | After build |
| Meta webhook cutover to Python | After parallel test passes |
| n8n decommission + doc archive | After cutover confirmed in production |
