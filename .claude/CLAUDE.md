# Flow AI — Project CLAUDE.md

## What this project is

Flow AI is a vertical AI agent platform for service SMEs in SEA. It automates customer engagement, booking, and CRM via WhatsApp. The primary channel is Meta Cloud API (WhatsApp Business).

**Pilot client:** HeyAircon — Singapore aircon servicing company.
**Current state (as of 2026-04-19):** Python orchestration engine is live in production receiving real WhatsApp traffic for HeyAircon. Meta webhook verified. Per-client LLM billing keys implemented. Shared Supabase provisioned. Google Calendar integration blocked on service account access (fix pending). n8n decommission pending 48h verification + calendar fix.
**Migration target:** Replace n8n with a Flow AI-owned Python/FastAPI orchestration engine — engine is now live; n8n still running in parallel until decommission gate passed.

---

## Tech Stack (locked decisions)

| Layer | Choice | Notes |
|-------|--------|-------|
| Orchestration engine | FastAPI (Python, async) | Replaces n8n |
| LLM (primary) | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | Starting model — eval performance before upgrading to Sonnet |
| LLM (fallback) | GPT-4o-mini (OpenAI SDK) | Activated when Anthropic API is unreachable |
| Database | Supabase (Postgres) | All client data + shared config DB |
| WhatsApp | Meta Cloud API direct | No BSP (no 360dialog) |
| Calendar | Google Calendar API (service account) | Add-only from agent |
| Deployment | Railway | Engine as a new service alongside n8n during transition |
| Observability | Langfuse (planned) | Agent trace monitoring and cost tracking |
| Testing | pytest + pytest-asyncio + httpx | Standard async Python stack |

**Do not use LangChain.** Use the Anthropic SDK directly. The agent loop is simple enough to own explicitly.

---

## LLM Strategy

### Starting model: Claude Haiku 4.5
The engine launches with `claude-haiku-4-5-20251001`. Rationale: lower cost per conversation during early production, fast response times, and sufficient capability for structured booking flows. The eval pipeline runs against every build to measure real performance across intent classification, tool use accuracy, escalation correctness, safety, and response quality.

**Upgrade path:** If eval scores fall below acceptable thresholds (defined in `engine/tests/eval/thresholds.yaml`), upgrade to `claude-sonnet-4-6`. Model is controlled by a single env var `LLM_MODEL` — no code changes needed to switch.

| Model | When to use | Env var value |
|-------|-------------|---------------|
| Claude Haiku 4.5 | Default — start here | `claude-haiku-4-5-20251001` |
| Claude Sonnet 4.6 | If Haiku eval scores insufficient | `claude-sonnet-4-6` |

### Fallback: GPT-4o-mini (OpenAI)
When the Anthropic API is unreachable (timeout, 5xx, rate limit exhausted), the engine falls back to GPT-4o-mini via the OpenAI SDK. The fallback is transparent to the customer — same system prompt, same tool definitions, same response format.

**Fallback logic (in `agent_runner.py`):**
1. Attempt Anthropic call with 10-second timeout
2. On `anthropic.APIConnectionError`, `anthropic.APIStatusError` (5xx), or timeout → log warning, switch to OpenAI GPT-4o-mini
3. On OpenAI failure → log error, send customer a graceful "we're experiencing issues" reply, do not crash

**Fallback is not a permanent switch.** Each new inbound message retries Anthropic first. The fallback activates per-request only.

**Required env vars for fallback:**
- `OPENAI_API_KEY` — required for fallback to work
- `OPENAI_FALLBACK_MODEL` — default `gpt-4o-mini`
- `LLM_FALLBACK_ENABLED` — default `true` (set to `false` to disable fallback during testing)

---

## Key Design Principles

### Context engineering
Business data (services, pricing, policies) lives in Supabase `config` and `policies` tables — never hardcoded in prompts. The `context_builder` fetches these at runtime before every Claude call. Client updates content in Supabase Studio. Zero code changes needed for content updates.

### Multi-client isolation
The engine is client-agnostic. Client config is loaded at runtime by `client_id` from the webhook path (`POST /webhook/whatsapp/{client_id}`).

**Hybrid config approach (decided April 2026):**
- Non-sensitive fields (`meta_phone_number_id`, `meta_verify_token`, `human_agent_number`, `google_calendar_creds`, `is_active`) → shared Flow AI Supabase `clients` table
- High-sensitivity secrets (`meta_whatsapp_token`, `supabase_url`, `supabase_service_key`, `anthropic_api_key`, `openai_api_key`) → Railway env vars, namespaced by client (`{CLIENT_ID_UPPER}_{VAR}`). LLM keys are per-client — each client is billed separately on their own Anthropic and OpenAI accounts.
- Cache `clients` table lookups in-process (5-min TTL minimum) — shared config DB cannot be a per-request dependency
- Migration path: move secrets to a secrets manager (AWS/GCP) at 10–20 clients

Adding a new client = INSERT into `clients` table + add 5 env vars to Railway. No engine changes. No redeploy for non-secret config updates.

### Escalation gate
The escalation gate (`customers.escalation_flag`) is a hard programmatic check that runs before the agent. If true: send holding reply, log, stop. The agent never decides whether it is escalated. This is not configurable.

### Calendar write rules
The agent adds calendar events only. It never modifies or deletes. All changes go through human escalation.

### n8n preservation rule
All n8n build documents are living references — do not archive or modify them until the Python engine has passed its 48h production verification window, the Google Calendar integration is confirmed working, and explicit decommission approval is given. Python engine is live as of 2026-04-19 and Meta webhook cutover is confirmed — but the 48h window and calendar fix are not yet cleared. If the migration is scrapped, n8n docs must be sufficient to deliver the full MVP.

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
    invoices/              # generated PDF invoices (output of finance/invoice_generator.py)
    reports/               # client-facing status reports (YYYY-MM-DD named markdown files)

finance/
  invoice_generator.py     # reusable PDF invoice generator (CLI + importable module)

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
| Generating a client invoice | Run `/generate-invoice` skill; script at `finance/invoice_generator.py` |
| Client invoice history | `clients/{client_id}/invoices/` |
| Generating a client status report | Use chief-of-staff to draft; write to `clients/{client_id}/reports/` with filename `{client_id}_status_YYYY-MM-DD.md` |
| Client status report history | `clients/{client_id}/reports/` |
| Understanding which code file handles what | `docs/architecture/code_map.md` |

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

## Bespoke vs Core Feature Framework

Every new client requirement must pass through this evaluation before any code is written. **Not implemented yet — framework is parked for when the first multi-client scenario arises.**

### Decision tests (run in order, stop at first match)

| Test | Question | YES | NO |
|------|----------|-----|----|
| T1: Universality | Useful to every future client regardless of industry? | **Core** — add to `engine/core/` | T2 |
| T2: Portability | Same pattern reusable across clients, even if content differs? | **Core** — abstract pattern, configure content via Supabase | T3 |
| T3: Isolation | Uniquely tied to one client's product or business process? | **Bespoke** — lives in `clients/{client_id}/` | Revisit |

### When implemented, the structure will be:
- `engine/config/bespoke_loader.py` — loads client extensions, merges into core at request time
- `clients/{client_id}/tools/` — bespoke tool definitions and functions
- `clients/{client_id}/prompts/` — static prompt extensions (fallback for logic-heavy cases)
- `prompt_extensions` table in per-client Supabase — client-managed prompt additions (no redeploy)

### Promotion pathway (bespoke → core)
Trigger: feature live 30+ days with one client AND a second client independently requests the same capability. Owner (founder) decides promotion. Pattern moves to `engine/core/`; content moves to Supabase `config`.

### Hard rule
Nothing inside `engine/core/` imports from `clients/`. Dependency is one-directional.

---

## Hard Rules

- Never dispatch `@software-engineer` directly. All implementation goes through `@sdet-engineer`.
- Never build client-specific logic inside `engine/`. Client isolation belongs in config only.
- Never modify or delete Google Calendar events from the agent. Add only.
- The escalation gate is a hard programmatic check — never an agent decision.
- All Claude calls go through the context builder first. Never call Claude with a hardcoded system prompt.
- Supabase is the only write target for business data. Google Sheets is read-only sync mirror if used at all.
- n8n build docs (`clients/hey-aircon/plans/build/`) are preserved and untouched until Python migration is confirmed live in production.
- Update `docs/architecture/code_map.md` after any change to engine file responsibilities, new files added, or architectural changes.

---

## Railway Deployment Model (decided 2026-04-18)

**Option A — one Railway project per client, single monorepo.**

- One Railway account hosts N projects (no per-client account needed).
- Each client = one Railway project with its own service, env vars, and deploy history.
- All Railway projects connect to the same GitHub repo (`flow-ai`).
- **5 env vars per client:** `{CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN`, `_SUPABASE_URL`, `_SUPABASE_SERVICE_KEY`, `_ANTHROPIC_API_KEY`, `_OPENAI_API_KEY`
- **Branch strategy:** each Railway project tracks the `release` branch, not `main`. Promotes to release when ready — controls blast radius.
  - Develop/merge freely on `main`.
  - `git push origin main:release` when ready to deploy to all active clients.
  - Can deploy to one client first (update that project's branch to a feature branch) before promoting to all.
- Adding a new client = create Railway project + add 3 env vars (`{CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN`, `_SUPABASE_URL`, `_SUPABASE_SERVICE_KEY`) + INSERT into shared `clients` table. No engine changes.
- Switch to manual deploy (Railway toggle) if stricter per-client rollout control is needed at scale.

---

## Current Blockers (as of 2026-04-19)

| Blocker | Impact |
|---------|--------|
| Google Calendar service account access | `write_booking` tool fails with 404. Fix: share `agent.heyaircon@gmail.com` calendar with the service account `client_email` from `HEY_AIRCON_GOOGLE_CALENDAR_CREDS`. User action required. |
| n8n Component E (escalate-to-human) | Not yet built. Waiting on Google Calendar fix and 48h production verification of Python engine before proceeding. |
| 48h production verification | Python engine is live as of 2026-04-19. Monitoring before n8n decommission decision. |

---

## n8n → Python Migration Status

| Phase | Status |
|-------|--------|
| n8n Components A–C | Built and running on Railway |
| n8n Component D (booking tools) | Built in Python engine; partially live — blocked on Google Calendar 404 |
| n8n Component E (escalate-to-human) | Not yet built — awaiting Google Calendar fix + 48h verification |
| Python engine: architecture design | Complete — `docs/architecture/00_platform_architecture.md` (update in progress as of 2026-04-19) |
| Python engine: build | Complete |
| Python engine: parallel test | Skipped — went straight to production cutover |
| Meta webhook cutover to Python | Complete — live as of 2026-04-19 |
| n8n decommission + doc archive | Pending — requires 48h verification + Google Calendar fix + explicit approval |
