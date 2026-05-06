# Flow AI — Project Status Log

> Owned by: chief-of-staff
> Last Updated: 2026-05-06

---

## Project Overview

**Flow AI** is a vertical AI agent platform for SEA service SMEs. Primary channel: WhatsApp automation via Meta Cloud API. Pilot client: HeyAircon (Singapore aircon servicing company).

---

## Current State Summary

| Layer | Status | Notes |
|-------|--------|-------|
| Platform docs (Product/) | Exists | Master doc, 4 PRDs, knowledge schema, persona framework, safety guardrails |
| hey-aircon client docs | Partial | Architecture reference complete and current; mvp_scope.md complete; proj_plan.md complete; PRD.md is a stub |
| hey-aircon n8n build | In Progress | Components A–C built and running on Railway. Component D (booking tools) pending Meta credentials. Component E (escalation tool) not started. |
| Supabase (shared flowai-platform) | Live | Tables created: `api_incidents`, `api_usage`, `clients`. HeyAircon row inserted with Meta phone ID, verify token, human agent number, Google Calendar ID. |
| Meta webhook | Live | Webhook URL registered and verified with Meta. Real WhatsApp traffic being processed. |
| Python orchestration engine | Live in Production | End-to-end flow confirmed: inbound logged → escalation gate → context builder → Claude Haiku 4.5 → reply via Meta API. |
| Google Calendar integration | Working | Calendar API issue resolved in prior session. Integration confirmed operational. |
| hey-aircon website | Built | Static HTML site at clients/hey-aircon/website/ |
| Observability docs | Current | SQL reference created: `docs/observability/sql-reference.md` (2026-04-21) |
| AGENTS.md | Current | Last updated 2026-04-18 |
| .claude/CLAUDE.md | Current | Last updated 2026-04-19 |

---

## Feature Tracking

### HeyAircon Phase 1 — WhatsApp Agent MVP

| Component | Status | Notes |
|-----------|--------|-------|
| A: Webhook + Meta integration | Complete | Railway running; Meta webhook verified live 2026-04-19 |
| B: Escalation gate | Complete | Binary gate with holding reply on TRUE branch |
| C: AI Agent (Claude Haiku 4.5 + context builder) | Complete | Context engineering working; Config + Policies via Supabase |
| D: Booking tools (calendar + write_booking) | Live | `check_calendar`, `create_event`, and `write_booking` all operational. Google Calendar integration confirmed working. |
| E: Escalate-to-human tool | Complete — Production Verified 2026-04-22 | Full escalation + reset flow implemented and verified. Escalation: `escalation_tool.py` sets flag + sends WhatsApp alert to human agent. Reset: `reset_handler.py` detects reply-to-message + keywords, clears flag. Holding reply sent once only (`escalation_notified` column). Sheets sync immediate on reset. 143 unit tests passing. Migrations 003 + 004 live in production. |
| Supabase (shared platform) | Complete | Tables provisioned; HeyAircon row live |
| Meta dev account | Complete | Webhook verified, real traffic flowing as of 2026-04-19 |
| Google Calendar integration | Working | Resolved in prior session. |
| Per-client LLM keys | Complete | `ClientConfig` carries `anthropic_api_key` and `openai_api_key` from Railway env vars. Shared platform `ANTHROPIC_API_KEY` removed. |
| Go-live / Production release | Scheduled — End April 2026 | Engine live in development. Production release target: end of April 2026. Time allows for thorough edge case testing. |
| Google Sheets sync (client data visibility) | Complete | Requirements: `docs/requirements/google_sheets_sync.md`. Architecture: `docs/architecture/google_sheets_sync.md`. Test plan: `docs/test-plan/features/google_sheets_sync.md`. Implementation: `engine/integrations/google_sheets.py`. 13 tests passing (8 unit + 5 integration). 2026-04-20. |
| Address schema migration (`address` + `postal_code` → `bookings`) | In Progress — Architecture | Schema change approved 2026-04-20. Move fields from `customers` to `bookings` for per-booking address accuracy. `@software-architect` dispatched to produce decision record and migration steps. |

### Platform — Multi-client Engine Migration

| Item | Status | Notes |
|------|--------|-------|
| n8n → Python orchestration engine | Live in Development | Python engine running; real traffic being processed. Production release target end April 2026. n8n was not in production — parallel run characterization corrected. |
| docs/ folder structure | Complete | Established earlier in project lifecycle |
| .claude/CLAUDE.md | Current | Blockers and migration status updated 2026-04-19 |
| Architecture doc (`00_platform_architecture.md`) | Stale — Needs Update | Two drifts identified: (1) `run_agent()` signature in doc uses `client_config: ClientConfig` but implementation uses explicit `anthropic_api_key` + `openai_api_key` + `client_id` params; (2) `LLM_PROVIDER=github_models` eval shim not documented. Delegated to `@software-architect`. |
| n8n decommission | Not a Gate | n8n was not running in production. Not a blocker for production release. Decommission at founder's discretion. |

---

## Feature Tracking

### Evaluation Pipeline — All Clients

| Component | Status | Notes |
|-----------|--------|-------|
| Plan | Complete | `docs/planning/eval_pipeline_plan.md` — approved 2026-04-16 |
| Requirements (`@product-manager`) | Complete | `docs/requirements/eval_pipeline.md` — 75 requirements, 22 user stories |
| Architecture (`@software-architect`) | Complete | `docs/architecture/eval_pipeline.md` — 12 sections, all interfaces + DDL + workflows |
| SDET planning + worktree setup | Complete | `docs/test-plan/eval_pipeline.md` + 60+ scaffold files created |
| `@software-engineer` implementation | Complete | 17 core files implemented, 31 unit tests + 10 integration tests passing |
| Supabase schema (eval_test_cases, eval_results, eval_alerts) | Not Started | Awaiting architecture approval |
| Python framework (EvalRunner, 6 scorers, CLI, reporters) | Not Started | Awaiting architecture |
| Telegram bot alerting | Not Started | `engine/tests/eval/alerts/telegram_notifier.py` |
| Platform YAML test cases | Not Started | safety, escalation_gate, tools, intent |
| HeyAircon YAML test cases | Not Started | booking_flow, faq, rescheduling |
| GitHub Actions CI integration | Not Started | PR gate + daily scheduled monitoring |
| HeyAircon baseline eval | Not Started | Pre-go-live quality gate |
| Langfuse integration (Phase 2) | Future | Trace dashboard + LLM-as-judge persona scoring |

**Architecture decision:** 1 shared pipeline serving all clients. Client isolation via `client_id` in test case metadata. Alerting via Telegram bot (not Slack). Test cases stored hybrid: platform behaviors in YAML/Git, client-specific in Supabase.

---

## Session Log

| Date | Phase | Description | Status |
|------|-------|-------------|--------|
| 2026-05-06 | Infrastructure | Deployment model changed from single `release` branch to per-client `deploy/{client-id}` branches. Reason: single `release` branch deployed to all clients simultaneously, creating risk of cross-client impact. New model: `master` for development, `deploy/hey-aircon` tracked by hey-aircon Railway project, `deploy/flow-ai` tracked by flow-ai Railway project. Promotion: `git push origin master:deploy/{client-id}`. Old `release` branch deprecated. | Complete |
| 2026-04-28 | Status Review | Chief-of-staff status review: All migration gates cleared (48h verification passed, calendar working). Two critical bugs identified: (1) guardrail re-prompt leaking to customers, (2) booking_count not incrementing on first booking. Rescheduling & cancellation feature evaluation complete — classified as **Core**, requires Calendar Write Rules policy change (add modify/delete capability). Awaiting direction frame confirmation before dispatching `@product-manager`. | In Progress |
| 2026-04-24 | Client Report | HeyAircon client-facing status report generated. Content drafted by chief-of-staff; file write delegated to `@sdet-engineer` → `docs/client-reports/heyaircon_status_2026-04-24.md`. | Complete |
| 2026-04-24 | Post-mortem | Slice 2 booking confirmation + Railway deployment isolation + escalation reset fallback + Sheets row key fix — 4 rework clusters, 20 commits | Complete |

---

## Post-mortem — 2026-04-24

### What broke / caused rework

**1. Railway deployment isolation (4 commits, mostly rework)**
- **Root cause:** Jumped to code changes (`railway.json` root to `/engine`, sys.path hack in `engine/main.py`) before checking whether Railway Watch Paths feature was available. Watch Paths was available on the user's plan and solved the problem with zero code changes. All 4 commits were avoidable.
- **Files touched:** `railway.json`, `Procfile`, `engine/main.py`, `.github/workflows/railway-deploy.yml`

**2. Slice 2 booking confirmation loop (3 commits)**
- **Symptoms:** Replying "yes" or "confirm" caused agent to re-ask for confirmation and create duplicate `pending_confirmation` bookings.
- **Root causes:**
  - Current inbound message included twice in conversation history (once fetched, once prepended) — LLM confused about current state
  - LLM couldn't reliably recover `booking_id` from conversation history across turns
  - Prompt ambiguity: "get their agreement before write_booking" caused LLM to ask again even after availability was confirmed
  - Guardrail keyword list too narrow — missed premature summary phrases like "reply yes to confirm"
- **Fixes:** Backend bypass (`message_handler.py` detects affirmative + pending booking → calls `confirm_booking` directly without LLM), dedup history, prompt clarification, broadened guardrail
- **Files touched:** `engine/core/message_handler.py`, `engine/core/context_builder.py`, `engine/core/tools/definitions.py`, `engine/core/agent_runner.py`

**3. Escalation reset failure (1 commit)**
- **Symptom:** Human agent replied "done" to older alert, got "No pending escalation found for this alert"
- **Root cause:** `reset_handler.py` looked up `escalation_tracking` by exact `alert_msg_id`. When newer unresolved escalations existed with different IDs, match failed.
- **Fix:** Fallback recovery — if no row matches `alert_msg_id`, look up phone number from historical alert and find latest unresolved escalation for that customer.
- **Files touched:** `engine/core/reset_handler.py`

**4. Google Sheets duplicate booking rows (1 commit)**
- **Symptom:** Sheets showed 2 rows per booking (one `pending_confirmation`, one `confirmed`). Supabase was correct.
- **Root cause:** `_booking_to_row()` first column used `id or booking_id`. Pending write used `booking_id` (no numeric `id` yet). Confirmed write used numeric `id`. `_sync_row()` matches by first column — treated them as two different rows.
- **Fix:** Changed row key to consistently prefer `booking_id or id` so pending and confirmed states map to same row.
- **Files touched:** `engine/integrations/google_sheets.py`

---

### What went well

- **Backend bypass pattern worked immediately** — Detecting affirmative intent + pending booking before calling LLM eliminated the confirmation loop on first attempt. High-frequency happy paths should bypass LLM where feasible.
- **Regression tests caught all regressions** — Each fix was validated with unit tests (`test_message_handler.py`, `test_reset_handler.py`, `test_context_builder.py`, `test_agent_runner.py`, `test_google_sheets.py`). No silent breakage.
- **Fallback recovery pattern saved escalation reset** — Exact ID matching failed, but fallback to phone number lookup recovered the case without data loss or manual intervention.
- **Railway Watch Paths discovery avoided permanent code smell** — Reverted all sys.path hacks before they became permanent. Clean solution exists and is now in use.

---

### Process gaps

**Gap 1: No "check platform features before implementation" gate**  
Railway Watch Paths was available but never checked. Result: 4 commits of unnecessary code changes that were fully reverted.

**Gap 2: Backend bypass pattern not preferred over prompt engineering for high-frequency flows**  
Confirmation loop was solvable with prompt tuning, but backend bypass (`detect intent → call tool`) was simpler, more reliable, and eliminated entire class of LLM confusion. Should be first choice for deterministic happy paths.

**Gap 3: Integration edge cases lack fallback strategies**  
Escalation reset worked for primary flow (latest alert), but failed for historical alerts. External integrations (reply-to-message, webhooks, third-party APIs) need "what if the primary identifier is stale?" fallback by default.

**Gap 4: External sync layers lack "stable primary key" requirement**  
Google Sheets row key switched between `id` and `booking_id` based on write timing. External sync to systems without native foreign keys needs explicit "key must be stable across all states" rule.

---

### Improvements locked in

- Added **Platform Feature Check Gate (Hard Rule)** to AGENTS.md — Deployment/infrastructure changes must check platform docs first before implementing workarounds. Applies to Railway, Supabase, Meta API, Calendar API.
- Added **Backend Bypass Preference Rule (Hard Rule)** to AGENTS.md — For high-frequency deterministic flows (confirmation, cancellation, simple branching), prefer backend logic over LLM when intent is unambiguous. Backend is faster, cheaper, and eliminates prompt drift.
- Added **Integration Fallback Strategy Rule (Hard Rule)** to AGENTS.md — All external integration points (webhooks, reply-to-message, third-party APIs) must include fallback logic for stale/missing identifiers. Primary path + recovery path required.
- Added **External Sync Primary Key Stability Rule (Hard Rule)** to AGENTS.md — Sync layers to external systems (Sheets, third-party CRMs) must use a primary key that is stable across all record states (pending → confirmed, draft → published, etc.). Key must exist and be consistent from first write.

---

## Feature Tracking

### Internal Telegram Alert Bot — All Clients

| Component | Status | Notes |
|-----------|--------|-------|
| Direction Frame | Pending Founder Approval | Drafted 2026-04-22 — awaiting confirmation before PM dispatch |
| Requirements (`@product-manager`) | Not Started | Awaiting direction frame approval |
| Architecture (`@software-architect`) | Not Started | |
| Test Plan + Implementation (`@sdet-engineer`) | Not Started | |

---

## Go-to-Market Workstream — Multi-Client Expansion

**Opened:** 2026-04-23  
**Owner:** chief-of-staff  
**Objective:** Define target market, client archetypes, and core pitch angle for scaling beyond HeyAircon pilot.

| Component | Status | Notes |
|-----------|--------|-------|
| Market Analysis & Target Verticals | Complete | `@business-strategist` — top 3 archetypes identified: (1) Aesthetics & Wellness Clinics, (2) Real Estate Agencies, (3) Insurance Brokers/IFAs |
| Pitch Brief | Complete | `@business-strategist` — pitch framework (problem/solution/proof/why now/ask), competitive positioning, objection handling, 5-touch outreach sequence. File: `docs/gtm/pitch-brief.md` |
| Messaging Playbook | Complete | `@growth-marketer` — 13,000+ word playbook: value prop (3 versions), vertical hooks, cold outreach templates (5-touch sequence, LinkedIn + email), discovery call script, LinkedIn content templates, website copy framework. File: `docs/messaging-playbook.md` |
| Competitor Analysis | Complete | `@business-strategist` — 27,000+ word standalone analysis: landscape map (4 tiers), 6 battle cards (respond.io, WATI, Yellow.ai, ManyChat, Intercom, Sierra), white space analysis, moat analysis, SEA market sizing (TAM/SAM/SOM), risk watch list. File: `docs/gtm/competitor-analysis.md` |

**Deliverables (all complete):**
- `Product/docs/business-plan.md` (updated) — market analysis, target segments, competitive positioning, HeyAircon repeatable pattern
- `docs/gtm/pitch-brief.md` — core pitch framework and 3 client archetypes (new file)
- `docs/gtm/competitor-analysis.md` — 27,000+ word standalone competitive analysis: landscape map, 6 battle cards, white space analysis, moat analysis, SEA market sizing, risk watch list (new file)
- `docs/messaging-playbook.md` — outbound messaging, value prop, objection handling, discovery call script, LinkedIn posts, website copy (new file)

---

## Backlog — Pending PM Requirements

| Feature | Status | Notes |
|---------|--------|-------|
| Rescheduling & Cancellation | Awaiting Direction Frame Approval | **Direction Frame (2026-04-28):** Subject = Confirmed booking customers who need to change/cancel appointment; Desired Outcome = Customer can reschedule or cancel via WhatsApp without human intervention for standard cases; Threat/Problem = All reschedule/cancel requests currently escalate to human (operational bottleneck). **Classification:** Core (T1: Universality + T2: Portability). **Critical Blocker:** Violates Calendar Write Rules (agent currently cannot modify/delete events) — founder approval required. **Dependencies:** Google Calendar API modify/delete capability, new `booking_status` values (`rescheduled`, `cancelled`), schema migration (5 new `bookings` columns), real policy text from HeyAircon (currently placeholder). **Agents:** PM → Architect (with Calendar Write Rules decision record) → SDET → Engineer. **Risks:** Booking state machine complexity, LLM reasoning load (must extract `booking_id`, distinguish reschedule vs new booking), calendar/DB divergence if API fails mid-operation. Awaiting founder confirmation of direction frame before dispatching `@product-manager`. 2026-04-28. |
| Pending Confirmation booking status + auto-follow-up | Awaiting PM Requirements | New booking status value (`Pending Confirmation`) when agent has gathered all info but not yet received final confirmation. Requires: new `booking_status` value, agent tool/flow change, conversation state tracking, scheduled follow-up mechanism (new infra), message template. Dependency: Postgres trigger for `total_bookings` (migration 002) should only fire on `Confirmed` status inserts. Blocked on `@product-manager` requirements. 2026-04-20. |

---

---

## Strategic Tracks — 2026-04-27

### Track 1: Flow AI as WhatsApp Client ("Eat Our Own Dog Food")

**Context:** Flow AI has built (or is building) a public website with a "Contact Us" WhatsApp button. Since Flow AI is an AI agent platform, the team should use its own product to power that WhatsApp number.

#### Summary

Bootstrapping Flow AI as `client_id = "flow-ai"` is **feasible and recommended**, but requires careful scoping. Flow AI's agent will be fundamentally different from HeyAircon's: no booking tools, no calendar integration, no Google Sheets sync. The agent's role is **lead qualification and sales triage**, not transactional automation.

**Core capability:** Respond to inquiries about the Flow AI product, qualify leads (industry, current pain points, team size, booking volume), route high-fit leads to founder for discovery call, capture low-fit/early-stage leads into CRM for nurture sequence.

**Bespoke vs Core assessment:**
- **Lead qualification conversation flow:** Core (T2: Portability). The *pattern* (multi-turn qualification → route or capture) is reusable across all future clients who sell services rather than deliver them. Content (questions, scoring logic, route conditions) differs by client, stored in Supabase `config`/`policies`. Abstraction lives in `engine/core/`.
- **"Book a discovery call" tool:** Core (T2: Portability). Scheduling integration pattern is portable (Google Calendar, Calendly, Cal.com). Implementation lives in `engine/core/tools/`, configured per client via `ClientConfig` (calendar provider type + credentials).
- **Persona and knowledge base:** Standard client-level config. Flow AI persona: consultative sales agent (professional, concise, probing). Knowledge base: product capabilities, target verticals, pricing model, founder availability.

**No custom code required.** All Flow AI–specific behavior is config-driven.

#### Infrastructure Requirements

| Layer | Action | Owner |
|-------|--------|-------|
| Supabase (shared) | INSERT into `clients` table: `client_id='flow-ai'`, `display_name='Flow AI'`, `meta_phone_number_id`, `meta_verify_token`, `human_agent_number` (founder's number for escalation), `is_active=TRUE`, `timezone='Asia/Singapore'`, `sheets_sync_enabled=FALSE`, `google_calendar_id=NULL` (no booking calendar needed unless discovery call scheduling is implemented) | founder or `@sdet-engineer` |
| Supabase (per-client) | Create new Supabase project `flow-ai-crm` with tables: `customers` (leads), `interactions_log` (conversation history), `config` (agent knowledge), `policies` (escalation rules, qualification scoring). No `bookings` table — Flow AI agent does not take bookings. Optional: `discovery_calls` table if discovery call scheduling is implemented. | `@software-architect` → `@sdet-engineer` |
| Railway | Create new Railway project `flow-ai-agent`, tracks `release` branch. Add 5 env vars: `FLOW_AI_META_WHATSAPP_TOKEN`, `FLOW_AI_SUPABASE_URL`, `FLOW_AI_SUPABASE_SERVICE_KEY`, `FLOW_AI_ANTHROPIC_API_KEY`, `FLOW_AI_OPENAI_API_KEY`. | founder |
| Meta | Register Flow AI WhatsApp Business number, verify webhook `https://<flow-ai-railway-domain>/webhook/whatsapp/flow-ai`. | founder |
| Client artifacts | Create `clients/flow-ai/` directory structure per `.flow/onboarding.md`: `context.md`, `product/persona.md`, `product/knowledge/` (capabilities.md, pricing.md, target-verticals.md, faqs/). | `@product-manager` → `@ux-ui-designer` (persona) |

#### Ordered Agent Dispatch Sequence

1. **`@product-manager`** — Create `clients/flow-ai/product/PRD.md` and `docs/requirements/flow_ai_agent.md` (requirements for lead qualification agent). Define: qualification questions, lead scoring logic, route conditions (when to escalate to founder vs capture for nurture), conversation flows (inquiry → qualify → route).
2. **`@ux-ui-designer`** — Create `clients/flow-ai/product/persona.md` (consultative sales agent persona) grounded in Flow AI brand voice and GTM messaging playbook (`docs/messaging-playbook.md`).
3. **`@software-architect`** — Create `clients/flow-ai/plans/architecture.md` (Supabase schema for `flow-ai-crm` project: `customers`, `interactions_log`, `config`, `policies`, optional `discovery_calls`). No booking tools or calendar integration in Phase 1 unless discovery call scheduling is scoped in.
4. **`@sdet-engineer`** — Provision `flow-ai-crm` Supabase project, run migrations, populate `config`/`policies` tables with Flow AI knowledge base. Create Railway project. Register Meta webhook. Test end-to-end message flow (inbound → escalation gate → context → agent → reply).

#### Artifacts to Create

| Path | Purpose | Owner |
|------|---------|-------|
| `clients/flow-ai/context.md` | Business context, AI agent purpose, constraints, integration points | `@product-manager` |
| `clients/flow-ai/product/PRD.md` | Client PRD (Flow AI as client) | `@product-manager` |
| `clients/flow-ai/product/persona.md` | Agent persona definition | `@ux-ui-designer` |
| `clients/flow-ai/product/knowledge/capabilities.md` | Flow AI product capabilities, features, target use cases | `@product-manager` |
| `clients/flow-ai/product/knowledge/pricing.md` | Flow AI pricing model (if public), or "contact for quote" | `@product-manager` |
| `clients/flow-ai/product/knowledge/target-verticals.md` | 3 target archetypes from GTM playbook (aesthetics clinics, real estate, insurance) | `@product-manager` |
| `clients/flow-ai/product/knowledge/faqs/` | Common objections, competitor comparisons, implementation timeline | `@product-manager` |
| `clients/flow-ai/plans/architecture.md` | Supabase schema for `flow-ai-crm` project | `@software-architect` |
| `docs/requirements/flow_ai_agent.md` | Platform-level requirements for lead qualification agent pattern (if Core promotion pathway is triggered) | `@product-manager` |

#### Gaps and Risks

| Gap/Risk | Impact | Mitigation |
|----------|--------|------------|
| No public Flow AI website yet | Cannot register WhatsApp "Contact Us" button until website is live | Track 1 implementation can proceed in parallel with website build. Deploy Railway + Meta webhook after website goes live. |
| Lead qualification pattern not yet abstracted into Core | Flow AI agent will require manual config setup (Supabase `config`/`policies` population) | Acceptable for client #2. If a third sales-focused client onboards, promote qualification pattern to Core with abstraction layer. |
| Discovery call scheduling integration not yet built | If "book a discovery call" is in scope, requires new tool implementation | Evaluate whether Calendly embed link (no tool needed — agent sends link in message) is sufficient for Phase 1. If native Google Calendar integration is required, add to scope and extend timeline. |
| Founder is the human escalation target | Flow AI agent will escalate directly to founder's WhatsApp | Acceptable for early stage. Migrate to dedicated Flow AI support number when team grows. |

---

### Track 2: Deployment Isolation (Railway Multi-Client Model)

**Context:** Current Railway deployment model (Option A — one Railway project per client, all pointing to same repo, each tracks `release` branch) was decided 2026-04-18. Founder wants to ensure an update to one client's config or code does NOT affect the other.

#### Current Model Assessment

**Isolation is sufficient at the infrastructure level** but has **code-level gaps** that create cross-client failure exposure.

**What is isolated today:**
- Each Railway project has its own service instance, env vars, and deploy history.
- Each Railway project tracks the `release` branch independently — a deploy to `flow-ai-agent` does not trigger a deploy to `hey-aircon-agent` unless `release` branch is updated.
- Each client has separate Supabase projects for customer data, bookings, interactions — full data isolation.
- Each client has separate LLM API keys (Anthropic + OpenAI) — billing isolation.
- Webhook routing is per-client (`/webhook/whatsapp/{client_id}`) — Meta sends traffic to the correct Railway project's public URL.

**What is NOT isolated today (failure modes):**
1. **Shared config cache pollution:** `client_config.py` uses an in-process TTL cache (`_cache` dict) shared across all inbound requests. If HeyAircon's config is corrupted or returns malformed data, the cache could serve stale/bad config to a Flow AI request if both clients share the same FastAPI process. **Failure mode:** Bad HeyAircon config write → cache poisoning → Flow AI agent gets wrong config → replies with HeyAircon knowledge base content to Flow AI lead.
2. **Shared error boundaries:** `message_handler.py`, `agent_runner.py`, `context_builder.py` are stateless but share the same process. An unhandled exception in one client's message flow (e.g., malformed Supabase row, corrupt Google Calendar creds JSON) crashes the entire FastAPI process, taking down all clients. **Failure mode:** HeyAircon Supabase corruption → FastAPI crash → Flow AI webhook returns 500 → Meta disables Flow AI webhook.
3. **Escalation flag bleed:** `customers.escalation_flag` and `escalation_notified` are stored in per-client Supabase, so no data-level bleed. But `reset_handler.py` operates on inbound `context_message_id` without client_id validation before querying `escalation_tracking`. If Meta delivers a malformed or cross-client `context_message_id` (edge case), reset logic could query the wrong Supabase. **Failure mode:** Unlikely but possible — malformed webhook payload references HeyAircon escalation in Flow AI request → wrong Supabase queried → reset fails or clears wrong escalation.
4. **Tool dispatch not client-scoped:** `build_tool_dispatch()` in `core/tools/__init__.py` injects `db` (per-client Supabase) and `client_config` into tool closures per request. This is correct. But if a tool function writes to the wrong `db` due to async context bleed (Python async bug or race condition), one client's tool call could write to another client's Supabase. **Failure mode:** HeyAircon booking written to Flow AI Supabase → data corruption.

#### Gap Analysis

| Gap | Severity | Current Exposure |
|-----|----------|------------------|
| Shared config cache (`_cache` dict in `client_config.py`) | High | Cache TTL is 5 minutes. A bad HeyAircon config write affects HeyAircon only for 5 minutes, then corrects. But if Flow AI request hits during the 5-minute window *and* `_cache` key collision occurs (should not happen if `client_id` is the key), Flow AI could get HeyAircon config. |
| Shared FastAPI process (no per-client error isolation) | Critical | An unhandled exception in any client's message flow crashes the entire process, taking down all clients. This is the highest-priority gap. |
| Escalation reset cross-client query risk | Low | Requires malformed Meta webhook payload. Meta webhook payloads are validated, so this is edge-case only. But no explicit `client_id` validation exists in `reset_handler.py` before querying `escalation_tracking`. |
| Tool dispatch async context bleed | Medium | Python async is generally safe if `db` is passed explicitly (not global). Current implementation passes `db` per request. But no unit test exists to verify `db` isolation under concurrent load (HeyAircon + Flow AI requests hitting simultaneously). |

#### Recommendation

**Keep the current Railway deployment model (Option A — one Railway project per client)**, but apply **code-level hardening** to eliminate cross-client failure exposure.

**Why not split into separate repos or separate Railway accounts:**
- Separate repos: increases maintenance burden, makes shared Core updates harder to deploy, creates version drift risk.
- Separate Railway accounts: no isolation benefit over separate projects in same account, adds billing complexity.
- Current model already provides **deployment isolation** (separate projects, separate URLs, separate env vars). The gaps are **runtime isolation** (shared process, shared cache), which are solvable at the code level.

#### Code Changes Needed

| Change | File(s) | Rationale | Owner |
|--------|---------|-----------|-------|
| **Per-client config cache namespacing** | `engine/config/client_config.py` | Change `_cache` from `Dict[str, Tuple[ClientConfig, float]]` to explicitly namespace by `client_id`. Current implementation already uses `client_id` as key, so this is a defensive assertion. Add unit test to verify cache key collision cannot occur. | `@software-architect` → `@sdet-engineer` |
| **Per-client error boundary in message_handler** | `engine/core/message_handler.py` | Wrap `handle_inbound_message()` in a per-client try/except that catches *all* exceptions, logs to `api_incidents` with `client_id`, and returns gracefully without crashing the process. Do NOT let any client's exception bubble up to FastAPI lifespan. | `@software-architect` → `@sdet-engineer` |
| **Client_id validation in reset_handler** | `engine/core/reset_handler.py` | Before querying `escalation_tracking`, validate that `context_message_id` belongs to the current `client_id` by cross-referencing `interactions_log` first. If mismatch, log warning and abort reset. | `@software-architect` → `@sdet-engineer` |
| **Async context isolation test** | `engine/tests/integration/test_concurrent_clients.py` (new file) | Integration test: spawn 2 concurrent requests (HeyAircon + Flow AI) with different `client_id`, verify each gets correct `db` connection, correct `ClientConfig`, correct Supabase data. Confirm no cross-client bleed under load. | `@sdet-engineer` |

#### Platform Feature Check (Railway)

**Railway native features checked:**
- **Watch Paths:** Already in use (2026-04-24 session). Each Railway project can watch different paths in the repo to trigger deploys. However, all clients currently point to the same `engine/` directory, so Watch Paths does not provide per-client isolation here.
- **Environment Groups:** Railway supports env var grouping, but does not provide process-level isolation — all clients' requests still hit the same FastAPI process.
- **Project-level routing:** Each Railway project has its own public URL. Meta webhooks are registered per-client to the correct URL, so routing isolation already exists.

**Verdict:** Railway provides deployment and routing isolation. Code-level hardening is required for runtime isolation.

---

## Action Plan (Unified)

### Sequenced Task List

| Phase | Task | Dependencies | Owner | Can Parallelize? |
|-------|------|--------------|-------|------------------|
| **Phase A: Track 2 — Deployment Isolation Hardening** | | | | |
| A1 | Architecture decision record: per-client error boundaries, cache namespacing, reset_handler validation, async isolation test plan | None | `@software-architect` | No |
| A2 | Implementation: per-client error boundary in `message_handler.py` | A1 complete | `@sdet-engineer` → `@software-engineer` | No |
| A3 | Implementation: config cache defensive assertion + unit test | A1 complete | `@sdet-engineer` → `@software-engineer` | Yes (parallel with A2) |
| A4 | Implementation: client_id validation in `reset_handler.py` | A1 complete | `@sdet-engineer` → `@software-engineer` | Yes (parallel with A2, A3) |
| A5 | Integration test: concurrent client requests (HeyAircon + dummy `client_id="test-client"`) | A2, A3, A4 complete | `@sdet-engineer` | No |
| A6 | Merge to `main`, promote to `release`, deploy to HeyAircon Railway | A5 passing | `@sdet-engineer` | No |
| **Phase B: Track 1 — Flow AI Client Bootstrap** | | | | |
| B1 | Requirements: `clients/flow-ai/product/PRD.md`, `docs/requirements/flow_ai_agent.md` (if Core promotion warranted) | A6 complete (deployment hardening must be live before adding second client) | `@product-manager` | No |
| B2 | Persona: `clients/flow-ai/product/persona.md` (consultative sales agent) | B1 complete | `@ux-ui-designer` | Yes (parallel with B3) |
| B3 | Architecture: `clients/flow-ai/plans/architecture.md` (Supabase schema for `flow-ai-crm`) | B1 complete | `@software-architect` | Yes (parallel with B2) |
| B4 | Knowledge base: `clients/flow-ai/product/knowledge/` (capabilities, pricing, target-verticals, faqs) | B1 complete | `@product-manager` | Yes (parallel with B2, B3) |
| B5 | Supabase provisioning: create `flow-ai-crm` project, run migrations, populate `config`/`policies` | B3 complete | `@sdet-engineer` | No |
| B6 | Railway provisioning: create `flow-ai-agent` project, add 5 env vars, register Meta webhook | B5 complete, Flow AI website live (external dependency) | founder + `@sdet-engineer` | No |
| B7 | End-to-end test: send test message to Flow AI WhatsApp number, verify agent response | B6 complete | `@sdet-engineer` | No |

### Gate Conditions

| Gate | Condition | Why This Matters |
|------|-----------|------------------|
| **G1: Deployment Isolation Hardening Complete** | Integration test `test_concurrent_clients.py` passing + A2–A4 merged to `release` + deployed to HeyAircon Railway | Adding a second client (Flow AI) to the same engine without runtime isolation creates unacceptable cross-client failure risk. |
| **G2: Flow AI Website Live** | Public Flow AI website deployed with "Contact Us" WhatsApp button | Cannot register Meta webhook for Flow AI WhatsApp number until website button exists and is visible to prospects. |
| **G3: Flow AI Knowledge Base Approved** | Founder review of `clients/flow-ai/product/knowledge/` content | Agent cannot respond accurately to product inquiries without approved knowledge base. |

---

## Session Log

| Date | Event |
|------|-------|
| 2026-04-27 | **Strategic tracks evaluation: Flow AI as WhatsApp client + deployment isolation.** Track 1 (Flow AI as client): feasible, config-driven, no custom code. Bespoke vs Core assessment: lead qualification pattern is Core (T2: Portability). Infrastructure: new Railway project, new Supabase project, 5 env vars, Meta webhook. Ordered dispatch: PM → UX/UI → Architect → SDET. Track 2 (deployment isolation): current Railway model (Option A) provides deployment isolation but has runtime gaps (shared cache, shared process, no per-client error boundaries). Recommendation: keep current model, apply code hardening (per-client error boundary, cache namespacing, reset_handler validation, async isolation test). Action plan: Phase A (Track 2 hardening, 6 tasks) gates Phase B (Track 1 bootstrap, 7 tasks). Report appended to `docs/status_log.md`. |
| 2026-04-23 | **POST-MORTEM: Worktree loss — two incidents (2026-04-22).** Two git worktrees (`feat/telegram-alerts`, `feat/llm-observability`) were built out and test-verified, then lost when `git worktree remove --force` was run. The merge on main was a no-op in both cases because the software-engineer never ran `git commit` inside the worktrees. Tests passed against working-tree files, but no committed objects existed. The sdet-engineer approved merge based on passing tests without first running `git log main..feat/<branch> --oneline` to confirm commits were present. Total loss: ~3 hours of implementation work, twice. A working daily digest feature (24/24 tests passing) was among the losses. **Root cause:** The software-engineer treated "tests pass" as synonymous with "work is saved." The sdet-engineer treated a clean merge as evidence of a fast-forward rather than a no-op. Neither agent ran the one-line check that would have caught it. **Fix applied:** Two new hard rules added to `AGENTS.md` under "Hard Rules — Git Worktree Discipline": (1) sdet-engineer must run `git log main..feat/<branch> --oneline` and confirm at least one commit before running `git merge`; (2) software-engineer must run `git add` + `git commit` + `git log` verification before reporting "done." **Lesson learned:** A passing test suite is evidence that code is correct, not that code is committed. Merge gates and done gates are separate checks. In worktree workflows both must be enforced explicitly — they are not implied by each other. |
| 2026-04-22 | **Escalation + reset flow — production verified ✅.** All 3 test scenarios passed: P1 (customer message while escalated → holding reply once), P2 (customer second message while escalated → silent drop), P3 (human agent reply "done" → flag cleared, AI resumes). Sheets sync on reset confirmed immediate. Implementation: `engine/core/tools/escalation_tool.py` (sets `escalation_flag=True`, sends WhatsApp alert with wamid, inserts `escalation_tracking` row), `engine/core/reset_handler.py` (NEW — reply-to-message detection + keyword matching, clears flag + marks `resolved_at`), `engine/core/message_handler.py` (holding reply once via `escalation_notified` gate, subsequent inbound silently dropped), `engine/integrations/meta_whatsapp.py` (`send_message()` now returns wamid), `engine/api/webhook.py` (extracts `context_message_id`). Migrations 003 + 004 live. 143 unit tests passing. Commits: `3004564` (escalation reset), `75053e6` (holding reply once), `4810631` (Sheets sync on reset). Component E: **Complete**. |
| 2026-04-22 | Supabase migrations 003 and 004 confirmed run against HeyAircon production DB. `003_escalation_tracking.sql` (escalation_tracking table + 3 indexes) and `004_escalation_notified.sql` (`escalation_notified BOOLEAN` column on `customers`) are now live. Engine code (commit `75053e6`) and schema are now in sync. Production verification of escalation + reset flow (P1–P3 test scenarios) is the next pending action. |
| 2026-04-22 | Escalation "holding reply only once" behavior shipped (commit `75053e6`). First inbound from escalated customer → holding reply sent once + `escalation_notified` flipped to `True`. Subsequent inbound → silently dropped, no reply, no agent. On reset → `escalation_notified` reset to `False` for re-escalation. 143 unit tests passing. |
| 2026-04-22 | Internal Telegram Alert Bot feature bootstrapped. Direction frame drafted, failure point audit completed, api_failure table mapping resolved (table is `api_incidents` + `noncritical_failures` in `engine/integrations/observability.py`). Telegram stub already present in `observability.py` — wiring is the primary build task. `@product-manager` dispatch pending direction frame approval. |
| 2026-04-22 | Status corrections: Component E corrected from "Not Started" to "Built, Pending Test Verification" — `escalation_tool.py` was fully implemented but not reflected in status_log. Both bugs from 2026-04-21 session confirmed resolved via code review + git history. BUG (critical) guardrail re-prompt leak: RESOLVED in commit `c70198f` — re-prompt now injected as loop `user` message with `continue`, never returned to customer. BUG (medium) `booking_count` not incremented: RESOLVED in commits `c70198f` + `a464093` — uses `total_bookings` (DB trigger column) with customer re-fetch after booking write. Process gap noted: neither bug was logged in `observation-log.md`, so no formal `#resolved` trail exists. `@sdet-engineer` dispatched to create escalation tool test plan and verify end-to-end workflow. |
| 2026-04-21 | Production test session completed (HeyAircon pilot). 2 passes, 2 bugs filed. PASS: T+2 advance booking policy enforced correctly (agent rejected "tomorrow evening," offered 24 April). PASS: Customer record created on first inbound message (log confirmed `New customer created: 6582829071`). BUG (medium): `booking_count` not incremented on first booking — remained 0 after booking HA-20260424-87RU, incremented to 1 only after second booking HA-20260426-RF02. Suspected race condition between `write_booking` increment PATCH and `message_handler` `last_seen_at` PATCH overwriting the counter. Files: `engine/core/tools/write_booking.py`, `engine/core/message_handler.py`. BUG (critical): Guardrail re-prompt message (agent internal reasoning) delivered to customer as outbound WhatsApp message — interaction log ID 269. Re-prompt in `agent_runner.py` must be injected as internal turn only, never as an outbound reply. Both bugs filed in `.flow/tasks/active.md`. |
| 2026-04-21 | Chemical wash BTU pricing — clarification strategy decision. Evaluated three options (ask-first, range-first, list-all). Decision: Option B (range-first). Agent leads with price range on first reply ("from $80 to $130 for 1 unit depending on BTU size") then asks for BTU. Config-only change: update `variation_hint_chemical_wash` and `variation_hint_chemical_overhaul` rows in Supabase `config` to instruct range-first behaviour. No code change to `context_builder.py`. No Railway redeploy. Two UPDATE statements in Supabase Studio; takes effect on next inbound message. |
| 2026-04-21 | Chemical wash / chemical overhaul BTU pricing fix diagnosed and approved. Root cause: 6 config keys used single underscores (`pricing_chemical_wash_9_12k` etc.) so context_builder rendered them as flat bullets with no BTU label and no clarification prompt. Fix: rename 6 keys to use `__` separator and update 2 `variation_hint_` rows from `"none"` sentinel to active BTU question text. Zero code changes, zero Railway redeploy. SQL statements produced for direct execution in Supabase Studio. Fix takes effect on next inbound message after SQL runs. |
| 2026-04-20 | Architecture evaluation requested: cost-estimate disclaimer feature. Evaluation completed by chief-of-staff — recommendation: policy row injection via `context_builder.py` from Supabase `policies` table. Affects `context_builder.py` only (zero engine logic changes). No implementation dispatched yet — pending approval. |
| 2026-04-20 | New feature request logged: Pending Confirmation booking status + auto-follow-up. Recorded in backlog pending `@product-manager` requirements. Status values agreed: `Confirmed`, `Pending Confirmation`, `Cancelled`, `Rescheduled`, `Completed`, `No-Show`. |
| 2026-04-20 | Status corrections applied: (1) Google Calendar integration confirmed working — removed as blocker. (2) n8n was not in production — removed as decommission gate. (3) Production release target set: end April 2026. Address schema migration approved and in-flight: `@software-architect` dispatched to produce decision record and migration steps for moving `address` + `postal_code` from `customers` to `bookings`. |
| 2026-04-20 | Change request evaluated: move `address` + `postal_code` from `customers` table to `bookings` table. Decision: APPROVED — valid data model fix. Original deferral (48h verification gate) removed; no outstanding blockers. Architecture phase now in progress. |
| 2026-04-19 | Post-session doc review completed. Architecture doc drifts identified: `run_agent()` signature (doc uses `client_config: ClientConfig`; impl uses explicit key params) and `LLM_PROVIDER=github_models` eval shim not documented. Delegated to `@software-architect` for targeted update. `booking_tools.py` hardening confirmed: `write_booking()` now raises `RuntimeError` on missing Calendar creds; atomicity enforced (no DB write without calendar event); human agent alerted on failure. `context_builder.py` prompt fix confirmed: 7 explicit BOOKING RULES replacing vague confirmation block. Google Calendar blocker re-classified: suspected GCP API not enabled (not just service account sharing). |
| 2026-04-19 | Code map created: `docs/architecture/code_map.md` — living quick-reference mapping every `engine/` file to its role in the end-to-end message flow, Supabase data flow, and "where to look" developer routing table. `AGENTS.md` and `.claude/CLAUDE.md` updated with routing entry and hard rule to keep code map current. |
| 2026-04-19 | Python engine confirmed live in production. Meta webhook verified and receiving real WhatsApp traffic for HeyAircon. Per-client LLM keys (`{CLIENT_ID_UPPER}_ANTHROPIC_API_KEY`, `{CLIENT_ID_UPPER}_OPENAI_API_KEY`) implemented in `ClientConfig`; shared `ANTHROPIC_API_KEY` removed from `Settings`. Shared Supabase (`flowai-platform`) fully provisioned with `api_incidents`, `api_usage`, `clients` tables; HeyAircon row live. `status_log.md` and `.claude/CLAUDE.md` updated. |
| 2026-04-18 | HeyAircon billing details recorded: `AGENTS.md` Finance Agent section updated with HeyAircon bill-to fields (contact +65 8841 9968, address TBD, payment terms). Both existing invoices (INV-HA-20260401, INV-HA-20260402) regenerated with updated client contact via `finance/invoice_generator.py` — output to `clients/hey-aircon/invoices/`. |
| 2026-04-18 | Finance agent initiative: `AGENTS.md` updated with `finance-agent` entry. `finance/invoice_generator.py`, `generate-invoice` skill, and `.claude/CLAUDE.md` updates pending — routed to `@sdet-engineer`. PDF proposal unreadable in this environment (poppler not installed) — billing field extraction blocked until PDF is accessible or fields are provided manually. |
| 2026-04-16 | Evaluation pipeline initiative approved. Plan saved to `docs/planning/eval_pipeline_plan.md`. `@product-manager` dispatched to produce `docs/requirements/eval_pipeline.md`. |
| 2026-04-15 | Bootstrap session: full project audit completed. Agent doc gaps identified. Migration plan produced. Project structure proposal made. CLAUDE.md content drafted. |

---

## Strategic Phase: Embeddable Chat Widget

**Opened:** 2026-04-28  
**Owner:** chief-of-staff  
**Requested By:** Founder  
**Objective:** Add embeddable chat widget as a second customer-facing channel alongside WhatsApp. Same AI agent, same knowledge base, different entry point.

---

### 1. Product Definition

#### What It Is

An embeddable JavaScript chat widget (similar to Intercom, Crisp, Drift) that clients install on their website with a `<script>` tag or iframe. Visitors click the widget, type messages in a chat window, and interact with the same AI agent that powers the WhatsApp channel — same persona, same knowledge base, same tools (booking, escalation, calendar).

#### How It Differs from WhatsApp

| Dimension | WhatsApp Channel | Chat Widget Channel |
|-----------|------------------|---------------------|
| **Dependency** | Meta Cloud API, requires WhatsApp Business account | Zero external platform dependency — self-hosted |
| **Installation** | Client registers WhatsApp number + webhook with Meta | Client adds `<script>` tag to website HTML |
| **Identity** | Persistent phone number (E.164 format) | Session-based: browser fingerprint + cookie (Phase 1); email/phone capture optional (Phase 2+) |
| **Conversation history** | Tied to phone number; persists indefinitely | Tied to session ID; retention TBD (7–30 days default) |
| **Access control** | Customer must have WhatsApp installed | Any website visitor with a browser |
| **Compliance concerns** | Meta terms of service, WhatsApp Business Policy, data residency (Meta servers) | Full client control — data stays in client's Supabase, no third-party platform |
| **User experience** | Mobile-native messaging app; push notifications; rich media (images, documents, location) | Web-based; no push notifications (Phase 1); text + buttons only (Phase 1) |
| **Escalation handoff** | Human agent replies directly in WhatsApp thread | Phase 1: escalation stops widget conversation, sends alert to human via WhatsApp/email. Phase 3: escalation bridges widget → WhatsApp (human replies on WhatsApp, customer continues in widget) |

#### Core Capabilities (Phase 1 MVP)

- **Embeddable widget UI:** Floating chat button (bottom-right corner, customizable position). Click opens chat window (400×600px default, responsive). Text input, message bubbles (customer + agent), typing indicator.
- **Session management:** Anonymous session created on first message. Session ID stored in browser cookie/localStorage. 30-minute idle timeout (configurable per client).
- **Message API:** Widget POSTs messages to `POST /chat/{client_id}/message`. Backend processes identically to WhatsApp flow: escalation gate → context builder → agent runner → reply.
- **Same agent engine:** Context builder fetches same `config` + `policies` from Supabase. Agent runner uses same tools (`check_calendar`, `write_booking`, `escalate_to_human`). Booking flow identical.
- **Conversation history:** Last 20 messages stored in `interactions_log` with `channel='chat_widget'` and `session_id` as identifier (instead of `phone_number`).
- **Client branding:** Widget button color, agent name, welcome message configurable per client via Supabase `clients` table (`widget_*` columns).

#### Deferred to Later Phases

- **Rich media:** Image uploads, file attachments, location sharing (Phase 2).
- **Push notifications:** Browser push API for offline messages (Phase 2).
- **Identity linking:** Email/phone capture in widget → link to WhatsApp identity if customer later contacts via WhatsApp (Phase 3).
- **Cross-channel escalation:** Widget escalation → WhatsApp handoff with conversation context (Phase 3).
- **Proactive messages:** Agent initiates conversation based on page visit, time on site, cart abandonment (Phase 4).
- **Multi-language UI:** Widget interface translated to client's target languages (Phase 4).

---

### 2. Architecture Assessment

**Files reviewed:**
- `docs/architecture/00_platform_architecture.md` — Sections 1–4 (System Overview, Tech Stack, Folder Structure, Component Breakdown)
- `docs/architecture/code_map.md` — End-to-end message flow (10 steps), file index (15 files), Supabase data flow
- `engine/api/webhook.py` — Current routes: `POST /webhook/whatsapp/{client_id}`, `GET /webhook/whatsapp/{client_id}`, `GET /health`
- `engine/core/message_handler.py` — Lines 1–50: `handle_inbound_message()` orchestrates escalation gate → context → agent → reply
- `Product/docs/00_Master_Project_Document.md` — 4-product map (Client Website, AI WhatsApp Agent, CRM, Sales Reporting)

#### Reusability Assessment

**Can the existing `message_handler.py` pipeline be reused?**

**YES — with one adapter layer.**

Current `message_handler.py` pipeline (10 steps from `code_map.md`):
1. Load client config (Supabase `clients` + Railway env vars)
2. Log inbound to `interactions_log`
3. Escalation gate (query `customers.escalation_flag`)
4. Customer upsert (INSERT new / UPDATE `last_seen`)
5. Context builder (fetch `config`, `policies`, last 20 messages)
6. Agent runner (Claude tool loop)
7. Send reply via Meta API
8. Log outbound to `interactions_log`
9. Log token usage to `api_usage`
10. (Sheets sync if enabled)

**Steps 1–6 and 9 are channel-agnostic.** They operate on:
- `client_id` (routing key)
- `customer_identifier` (phone number for WhatsApp, session ID for widget)
- `message_text` (user input)
- `client_config` (Supabase + env vars)
- Database reads/writes to per-client Supabase

**Steps 7–8 and 10 are WhatsApp-specific.** They call:
- `meta_whatsapp.send_message()` — sends via Meta Graph API
- `interactions_log` writes with `phone_number` as identifier
- `google_sheets.sync_customer_to_sheets()` — optional post-write

**Adapter pattern (recommended):**

Create `engine/integrations/chat_widget.py` with:
- `send_widget_message(session_id, message_text, client_id)` — returns message to widget frontend via WebSocket or HTTP response
- `log_widget_interaction(session_id, message_text, direction, client_id, db)` — writes to `interactions_log` with `channel='chat_widget'`, `session_id` replaces `phone_number`

**Refactor `message_handler.py`:**
- Extract channel-agnostic orchestration logic into `_handle_message_core(client_id, customer_identifier, message_text, channel)` (private function)
- `handle_inbound_message()` (WhatsApp entry point) calls `_handle_message_core(..., channel='whatsapp')` then calls `meta_whatsapp.send_message()`
- New `handle_widget_message()` (chat widget entry point) calls `_handle_message_core(..., channel='chat_widget')` then calls `chat_widget.send_widget_message()`
- `_handle_message_core()` returns `(reply_text: str, should_escalate: bool)` — caller decides how to deliver the reply

**Zero duplication.** Context builder, agent runner, escalation gate, tool dispatch — all reused.

#### New API Endpoints Needed

| Route | Method | Purpose | Request Body | Response |
|-------|--------|---------|--------------|----------|
| `/chat/{client_id}/message` | POST | Receive chat widget message | `{"session_id": "...", "message_text": "..."}` | `{"reply": "...", "typing": false, "escalated": false}` |
| `/chat/{client_id}/history` | GET | Fetch conversation history (last 20 messages for session) | Query param: `session_id` | `{"messages": [{"role": "user"|"assistant", "text": "...", "timestamp": "..."}]}` |
| `/chat/{client_id}/session` | POST | Initialize new session (returns session_id) | `{}` (empty body; session_id generated server-side) | `{"session_id": "...", "welcome_message": "..."}` |
| `/widget/{client_id}.js` | GET | Serve widget JavaScript bundle | N/A | JavaScript file (`Content-Type: application/javascript`) |

**Routing addition to `engine/api/webhook.py`:**
```python
@app.post("/chat/{client_id}/message")
async def receive_chat_message(client_id: str, request: Request, background_tasks: BackgroundTasks):
    # Parse {"session_id": "...", "message_text": "..."}
    # Add handle_widget_message() as BackgroundTask
    # Return 200 immediately (same pattern as WhatsApp webhook)
```

**No conflict with existing `/webhook/whatsapp/{client_id}` routes.** Widget uses `/chat/` prefix; WhatsApp uses `/webhook/` prefix.

#### Where Does the Widget JS Live?

**Option A (recommended): Railway static serve from `engine/static/widget.js`**

- Widget JavaScript bundle lives at `engine/static/widget.js` (single file, vanilla JS, zero dependencies, ~15KB minified)
- Railway serves static files from `engine/static/` via FastAPI `StaticFiles` mount: `app.mount("/widget", StaticFiles(directory="engine/static"), name="widget")`
- Client embeds: `<script src="https://{client-railway-url}/widget/{client_id}.js"></script>`
- Per-client customization: `widget.js` reads `client_id` from script `src` URL, fetches config from `/chat/{client_id}/config` on load (returns widget colors, welcome message, agent name from Supabase `clients.widget_*` columns)

**Pros:** Zero external CDN dependency. Widget and backend deployed together (version lock). Railway serves static files natively via Nginx.

**Cons:** Railway bandwidth costs if widget is loaded millions of times (acceptable for Phase 1 — <100 clients, <10K widget loads/month).

**Option B: Separate CDN (Cloudflare, AWS CloudFront)**

Deferred to Phase 2+ (when widget traffic justifies CDN). Client embeds from `https://cdn.flowai.app/widget/{version}.js`. Adds deployment complexity (CI/CD must push widget to CDN on every release).

**Verdict:** Option A for Phase 1. Migrate to CDN when aggregate widget bandwidth exceeds 100GB/month or latency becomes a concern (SEA → North America loads).

#### Session/Conversation Tracking Without Phone Number

**Phase 1: Anonymous sessions with browser fingerprint + cookie**

| Field | Storage | Purpose |
|-------|---------|---------|
| `session_id` | `UUID4` generated server-side on first message; stored in browser `localStorage` | Stable identifier for conversation history lookup |
| `fingerprint` | Browser fingerprint (user agent + screen resolution + timezone + language), hashed | Fallback identifier if cookie/localStorage cleared |
| `created_at` | Timestamp of first message | Session age tracking |
| `last_seen_at` | Timestamp of most recent message | Idle timeout enforcement (30 min default) |
| `ip_address` | Extracted from request headers (`X-Forwarded-For`) | Abuse detection, geolocation |

**Session lifecycle:**
1. Visitor opens widget for first time → widget JS calls `POST /chat/{client_id}/session` → backend generates `session_id`, inserts into `sessions` table (new table), returns `session_id` + welcome message
2. Widget stores `session_id` in `localStorage` (key: `flowai_session_{client_id}`)
3. Every message includes `session_id` in POST body
4. Backend queries `sessions` table by `session_id` → if `last_seen_at` > 30 min ago, treat as new session (reset conversation history)
5. Session expires after 30 days of inactivity (configurable per client via `clients.widget_session_ttl_days`)

**No authentication in Phase 1.** Sessions are anonymous. Email/phone capture is optional (agent can ask for it in conversation, store in `customers` table, but not enforced).

**Phase 2+: Identity linking**

When customer provides email/phone in widget conversation:
- Agent extracts email/phone via tool call (`capture_customer_identity`)
- Backend links `session_id` → `customer_id` in new `session_customer_links` table
- If customer later contacts via WhatsApp using same phone number, conversation history is unified (both widget and WhatsApp messages appear in same `interactions_log` query, filtered by `customer_id`)

#### Data Model Changes Needed

**New tables:**

```sql
-- sessions table (one row per widget session)
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL,
    fingerprint_hash TEXT,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expired_at TIMESTAMPTZ
);

CREATE INDEX idx_sessions_client_id ON sessions(client_id);
CREATE INDEX idx_sessions_last_seen ON sessions(last_seen_at) WHERE expired_at IS NULL;
```

**Schema changes to existing tables:**

| Table | Change | Rationale |
|-------|--------|-----------|
| `interactions_log` | Add `channel TEXT NOT NULL DEFAULT 'whatsapp'` | Distinguish WhatsApp vs chat widget messages |
| `interactions_log` | Add `session_id UUID` (nullable, foreign key to `sessions.session_id`) | Chat widget messages reference session instead of phone |
| `interactions_log` | Change `phone_number TEXT NOT NULL` → `phone_number TEXT` (nullable) | Widget messages have no phone number |
| `customers` | Add `session_ids UUID[]` (array, nullable) | Track which sessions belong to a customer (for identity linking in Phase 2+) |
| `bookings` | Add `channel TEXT NOT NULL DEFAULT 'whatsapp'` | Distinguish bookings made via WhatsApp vs widget |
| `bookings` | Add `session_id UUID` (nullable) | Widget bookings reference session |
| `clients` | Add `widget_enabled BOOLEAN NOT NULL DEFAULT FALSE` | Feature flag per client |
| `clients` | Add `widget_primary_color TEXT` (hex color, e.g. `#4F46E5`) | Widget button + header color |
| `clients` | Add `widget_welcome_message TEXT` | First message shown when widget opens |
| `clients` | Add `widget_session_ttl_days INTEGER NOT NULL DEFAULT 30` | Session expiration (days of inactivity) |

**Migration strategy:**

Phase 1 schema changes are **additive only** (new columns with defaults, new table). Existing WhatsApp flow unaffected:
- `interactions_log.channel` defaults to `'whatsapp'` — all existing rows remain valid
- `interactions_log.session_id` nullable — WhatsApp rows leave it NULL
- `interactions_log.phone_number` nullable — widget rows leave it NULL, WhatsApp rows populate it

**Backward compatibility guaranteed.** No breaking changes to existing queries.

---

### 3. Two-Channel Architecture

#### Unified Agent Configuration

The same `config` + `policies` tables in per-client Supabase serve both channels. When a message arrives (WhatsApp or widget), `context_builder.py` fetches:
- All rows from `config` table (services, pricing, appointment windows, booking lead time)
- All rows from `policies` table (escalation rules, confirmation requirements, refund policies)
- Last 20 messages from `interactions_log` filtered by customer identifier (`phone_number` for WhatsApp, `session_id` for widget)

**No channel-specific config needed** except:
- Widget UI config (`clients.widget_*` columns) — cosmetic only, does not affect agent behavior
- Session TTL (`clients.widget_session_ttl_days`) — determines when widget conversation history resets

**Agent persona, knowledge base, tools, and policies are channel-agnostic.**

#### Unified Conversation History Across Channels (Phase 2+)

**Problem:** A customer starts a conversation in the chat widget (session_id = `abc123`), then later contacts the business via WhatsApp (phone_number = `+6591234567`). Without identity linking, the agent treats these as two separate customers with zero shared context.

**Solution (Phase 2):** Identity linking via `customers` table.

1. **Widget conversation:** Customer provides email/phone in widget (agent asks "What's your contact number for appointment confirmation?"). Agent calls new tool `capture_customer_identity(session_id, phone_number)`.
2. **Backend links:** `customers` table INSERT or UPDATE with `phone_number` + `session_ids` array append. Now `customers.session_ids` contains `[abc123]`.
3. **WhatsApp conversation:** Customer messages via WhatsApp (+6591234567). Backend queries `customers` by `phone_number`, finds existing row with `session_ids=[abc123]`.
4. **Unified history fetch:** `context_builder.py` queries `interactions_log` WHERE `phone_number = '+6591234567' OR session_id = ANY('{abc123}')` — returns messages from both widget and WhatsApp, sorted by timestamp.
5. **Agent context:** "I see we spoke earlier on your website. You were asking about chemical wash pricing..."

**Phase 1 (MVP) skips identity linking.** Each channel's conversation history is isolated. Acceptable for pilot — most customers will use only one channel per interaction.

#### Cross-Channel Escalation (Phase 3)

**Use case:** Customer starts booking via widget, encounters a complex issue (e.g., "I need service for 8 units in a commercial building, can you send a quote?"). Agent calls `escalate_to_human` tool. Human agent needs to reply, but customer is on the website (not WhatsApp).

**Phase 3 flow (widget → WhatsApp handoff):**

1. Customer sends message in widget that triggers escalation (agent calls `escalate_to_human` tool).
2. Backend sends alert to human agent's WhatsApp: "Escalation from website chat: [customer inquiry]. Reply here to respond. Session ID: abc123."
3. Human agent replies in WhatsApp thread.
4. Backend detects reply-to-message context (via `context_message_id`), extracts `session_id=abc123` from alert text.
5. Backend **bridges** reply to widget: sends human agent's WhatsApp message as a widget message (via WebSocket or next poll).
6. Customer sees human reply in widget, continues conversation.
7. Subsequent customer messages in widget are routed to human agent's WhatsApp as inbound alerts.
8. **Loop continues** until human agent sends keyword ("resolved") to close escalation. Widget conversation resumes with AI agent.

**Why this architecture:**

- **No new communication channel for human agents.** Human agents already monitor WhatsApp — no training or new app needed.
- **Async bridge.** Human agent replies when available (not real-time). Widget shows "A team member will respond shortly" holding message.
- **Preserved context.** Full conversation history (widget + WhatsApp) is logged in `interactions_log` — human agent has full context from alert.

**Phase 1 escalation (simpler):** Widget escalation stops widget conversation, sends alert to human agent via WhatsApp, and tells customer "A team member will contact you via WhatsApp or email." No bridging — customer must switch channels.

#### Identity Linking Strategy

**Phase 1: No linking.** `session_id` and `phone_number` are separate identifiers. Two separate `customers` table rows if same person uses both channels.

**Phase 2: Explicit linking via agent tool.**

New tool: `capture_customer_identity`
- **Input schema:** `{"session_id": "...", "phone_number": "...", "email": "..."}` (phone or email, at least one required)
- **When agent calls it:** Customer provides contact info in widget conversation (agent asks for confirmation number or follow-up)
- **Backend action:** INSERT or UPDATE `customers` table:
  - If `phone_number` exists → UPDATE `session_ids` array (append current `session_id`)
  - If new → INSERT with `phone_number`, `session_ids=[session_id]`, `channel='chat_widget'`
- **Effect:** Next message from this phone number (via WhatsApp) fetches unified history (widget + WhatsApp messages)

**Phase 3: Heuristic linking (optional, privacy-sensitive).**

If customer's email/phone appears in widget conversation (agent extracts via NER or form input), backend automatically queries `customers` table by email/phone. If match found, link session without explicit tool call. Requires privacy policy disclosure ("We may link your website session with previous conversations").

**Recommended:** Phase 2 only (explicit tool call). Heuristic linking deferred until privacy compliance (GDPR, PDPA) is vetted.

---

### 4. Where Flow AI Uses It First

**Flow AI website currently has:** "Contact Us" WhatsApp button (links to `wa.me/{flow-ai-whatsapp-number}`).

**Chat widget replaces OR supplements this.**

#### Recommended approach: Dual-channel CTA

- **Primary CTA:** Chat widget (floating button, bottom-right corner, always visible)
- **Secondary CTA:** "Prefer WhatsApp?" link in widget welcome message or website footer → opens WhatsApp

**Why widget as primary:**

1. **Lower friction.** Visitor clicks widget, types immediately — no app switch, no WhatsApp install required.
2. **Better lead capture.** Widget conversation happens on flowai.app domain — visitor never leaves site. WhatsApp requires app switch (higher drop-off).
3. **Data ownership.** Widget messages stored in Flow AI's Supabase — full control, no Meta dependency.
4. **Demo-friendly.** Prospects evaluating Flow AI can interact with the agent directly on the website — no need to save Flow AI's WhatsApp number.

#### Flow AI as `client_id='flow-ai'` for chat widget

**Status:** `clients/flow-ai/` artifacts already exist (confirmed via `file_search` — 8 files found: `context.md`, `PRD.md`, `persona.md`, `knowledge/` files, `architecture.md`).

**What this means:**

- Flow AI is already provisioned as a client in the platform (`client_id='flow-ai'`)
- Supabase project `flow-ai-crm` exists (per Track 1 audit from 2026-04-27 status log entry)
- Railway project `flow-ai-agent` exists (per Track 1)
- WhatsApp channel is live (per Track 1)

**Chat widget deployment for Flow AI:**

1. Enable widget in Supabase: `UPDATE clients SET widget_enabled=TRUE, widget_primary_color='#4F46E5', widget_welcome_message='Hi! I''m Flow AI''s assistant. Ask me anything about our platform.' WHERE client_id='flow-ai'`
2. Add `<script src="https://flow-ai-agent.railway.app/widget/flow-ai.js"></script>` to Flow AI website `<body>` tag
3. Widget loads → calls `POST /chat/flow-ai/session` → receives `session_id` + welcome message
4. Visitor types message → widget POSTs to `/chat/flow-ai/message` → backend processes via `handle_widget_message()` → agent responds using same knowledge base as WhatsApp channel

**Zero custom code.** Widget + Flow AI agent integration is config-driven.

#### First production deployment = Flow AI website

**Why this is strategically correct:**

- **Dogfooding.** Flow AI must use its own product before selling it to clients. Builds internal conviction and surfaces UX issues early.
- **Demo artifact.** Every sales call, every prospect email, every LinkedIn post — "Try it yourself at flowai.app" is the strongest proof point.
- **Content marketing.** Widget transcript becomes case study material: "Our own lead qualification bot converts 40% of widget conversations to discovery calls."
- **Iteration velocity.** Flow AI team can test widget changes immediately on own website — no client coordination needed.

**Go-live checklist for Flow AI widget:**

| Task | Owner | Blocker? |
|------|-------|----------|
| Widget JS bundle built (`engine/static/widget.js`) | `@software-engineer` | Yes |
| Chat widget API routes live (`/chat/{client_id}/*`) | `@software-engineer` | Yes |
| `sessions` table migration run on `flow-ai-crm` Supabase | `@sdet-engineer` | Yes |
| `interactions_log.channel` + `interactions_log.session_id` columns added | `@sdet-engineer` | Yes |
| `clients.widget_*` columns added to shared Supabase | `@sdet-engineer` | Yes |
| Flow AI website updated with widget `<script>` tag | founder or `@sdet-engineer` | Yes |
| Widget styling matches Flow AI brand (color, font, tone) | `@ux-ui-designer` | No (can iterate post-launch) |
| Widget transcript appears in Flow AI CRM (`flow-ai-crm` Supabase) | Automatic (backend writes to `interactions_log`) | No (test during QA) |

---

### 5. Impact on Existing Clients (HeyAircon)

**HeyAircon does NOT need the widget in Phase 1.**

HeyAircon's customer acquisition channel is **WhatsApp-first** (customers find them via Google search, Facebook ads, referrals — all direct to WhatsApp). HeyAircon's website (static HTML, `clients/hey-aircon/website/`) is a **landing page only** — no booking form, no contact form. CTA is WhatsApp button.

**Chat widget adds zero value to HeyAircon in Phase 1:**
- Their website traffic is low (<500 visitors/month, per pilot client profile)
- Their customers are mobile-first (HDB/condo residents) — prefer WhatsApp over web chat
- Booking flow requires calendar integration (already working on WhatsApp)

**HeyAircon opts in to widget when:**

1. They expand marketing to Google Ads or SEO (drive web traffic instead of direct WhatsApp referrals), OR
2. They launch a self-service booking portal (Phase 2+ CRM interface), OR
3. They request it explicitly

**Isolation guarantees required (even though HeyAircon doesn't use widget):**

The widget endpoint (`POST /chat/{client_id}/message`) shares the same FastAPI process as the WhatsApp endpoint (`POST /webhook/whatsapp/{client_id}`). If widget code has a bug that crashes the process, HeyAircon's WhatsApp flow is affected.

**Required safeguards:**

| Risk | Mitigation | Owner |
|------|------------|-------|
| Widget API bug crashes FastAPI process → HeyAircon WhatsApp down | Per-client error boundary in `message_handler.py` (already planned in Track 2 deployment isolation hardening, 2026-04-27 status log entry) | `@software-architect` → `@sdet-engineer` |
| Widget database migration breaks HeyAircon queries | All widget schema changes are additive (new columns with defaults, new table). Existing `interactions_log` queries unaffected (no WHERE clause on `channel` or `session_id` unless explicitly filtering). Regression tests must verify WhatsApp flow before widget merge. | `@sdet-engineer` |
| Widget increases Railway memory/CPU usage → WhatsApp webhook response time > 5s → Meta disables HeyAircon webhook | Load testing required before widget GA. If widget traffic is high, split into separate Railway service (`flow-engine-widget`). Monitor Railway metrics after Flow AI widget launch. | `@sdet-engineer` (load test), founder (Railway scaling decision) |

**Verdict:** Widget architecture does not break HeyAircon IF:
1. Track 2 deployment isolation hardening (per-client error boundaries) is completed before widget merge
2. Widget schema migrations are tested against HeyAircon's Supabase before production deploy
3. Railway resource usage is monitored post-widget launch

**Widget is a separate feature, not a migration.** HeyAircon's WhatsApp flow remains unchanged. Widget adds new routes + new table + new code paths — HeyAircon's code paths are untouched.

---

### 6. Product Roadmap — Phase Definition

| Phase | Name | Scope | Status |
|-------|------|-------|--------|
| **Phase 1 (MVP)** | Chat Widget Core — Flow AI Website Only | Basic widget on Flow AI website only; same agent engine; no WhatsApp integration. Validates widget UX, agent reusability, session management. **Deliverables:** Widget JS bundle (`engine/static/widget.js`), chat API routes (`/chat/{client_id}/*`), `sessions` table, `interactions_log.channel` + `session_id` columns, Flow AI website `<script>` tag, widget config UI (`clients.widget_*` columns). **Constraints:** Anonymous sessions only (no identity linking). No rich media (text + buttons only). Escalation stops widget conversation (no cross-channel bridging). Widget served from Railway (not CDN). **Gate:** Flow AI team uses widget for 2 weeks, collects 20+ widget conversations, confirms agent responses are equivalent to WhatsApp quality. | Not Started |
| **Phase 2** | Multi-Client Widget + Identity Linking | Widget available to all clients (embed script per `client_id`). Identity linking: widget session → customer record when email/phone captured. Unified conversation history across channels (widget + WhatsApp). **Deliverables:** Per-client widget customization UI (CRM interface or Supabase Studio form), `capture_customer_identity` tool, `customers.session_ids` array, `context_builder` unified history query, client onboarding docs (how to embed widget). **Gate:** 2 clients (Flow AI + 1 pilot) use widget for 30 days, confirm identity linking works (customer messages via widget, then WhatsApp → agent recognizes them). | Not Started |
| **Phase 3** | Cross-Channel Escalation (Widget → WhatsApp Handoff) | Chat widget escalation bridges to WhatsApp. Human agent replies in WhatsApp thread → customer sees reply in widget. Async bidirectional bridge until escalation resolved. **Deliverables:** Escalation bridge logic (`reset_handler` extended to widget), WebSocket or long-polling for widget real-time updates, human agent training docs (how to reply to widget escalations via WhatsApp). **Gate:** 1 client uses cross-channel escalation for 2 weeks, confirms human agents can respond to widget customers via WhatsApp without switching apps. | Not Started |
| **Phase 4 (Future)** | Widget Enhancements | Rich media (image uploads, file attachments), browser push notifications, proactive messages (time-on-page trigger), multi-language UI, CDN deployment for global latency, mobile SDK (native iOS/Android widget). | Not Started |

### Complexity Assessment

| Phase | Estimated Effort | Complexity Drivers | Risks |
|-------|------------------|-------------------|--------|
| Phase 1 | **4–6 weeks** (1 developer + 1 QA) | Widget JS UI (vanilla JS, 400–500 LOC), session management (new `sessions` table + TTL logic), `handle_widget_message()` refactor (extract channel-agnostic core from `message_handler.py`), database migration (5 new columns + 1 new table), load testing (ensure widget doesn't degrade WhatsApp latency) | **Medium:** Widget UI is greenfield (no existing reference). Session expiration logic has edge cases (concurrent messages during TTL boundary). Railway resource contention between widget + WhatsApp needs monitoring. |
| Phase 2 | **3–4 weeks** | Identity linking tool (`capture_customer_identity`), unified history query (OR clause on `phone_number` + `session_id`), per-client widget config UI (Supabase Studio form or basic CRM interface page), client onboarding docs (embed instructions + troubleshooting) | **Low:** Identity linking is a single tool + 1 table column. Unified history is a query change. Config UI can be Supabase Studio (zero custom UI build) in Phase 2. |
| Phase 3 | **6–8 weeks** | Escalation bridge (bidirectional message relay), WebSocket server (real-time widget updates), `reset_handler` extension (detect widget escalations, route replies to correct session), conversation state machine (escalated widget session must buffer customer messages while human replies), human agent training (new workflow: reply to widget via WhatsApp) | **High:** Real-time messaging layer (WebSocket) is new infrastructure. State machine for buffering customer messages during escalation adds complexity. Human agent UX is new workflow (reply-to-message becomes cross-channel bridge). |

---

### 7. Action Plan — Phase 1 MVP

**Objective:** Chat widget live on Flow AI website within 6 weeks. Widget can handle same conversations as WhatsApp channel (booking, FAQs, escalation). Flow AI team validates widget UX and agent quality before offering to clients.

#### Gate Conditions (Must Pass Before Any Code)

| Gate | Condition | Owner |
|------|-----------|-------|
| **G1: Track 2 Deployment Isolation Complete** | Per-client error boundaries merged to `release` + deployed to HeyAircon Railway. Integration test `test_concurrent_clients.py` passing. (Per 2026-04-27 status log, Track 2 tasks A1–A6) | `@software-architect` → `@sdet-engineer` |
| **G2: Flow AI Website Live** | Public Flow AI website deployed and accessible. "Contact Us" section exists (even if current CTA is WhatsApp button). | Founder (external dependency) |
| **G3: Direction Frame Approved** | Founder confirms direction frame for chat widget: Subject = Website visitors who need immediate answers / Desired Outcome = Visitor can interact with AI agent without leaving website or installing WhatsApp / Threat = Friction of switching to WhatsApp app loses 40–60% of visitors (bounce rate). | Founder → chief-of-staff |

#### Ordered Task List (Phase 1)

| Task | Dependencies | Owner | Estimated Effort | Parallelizable? |
|------|--------------|-------|------------------|-----------------|
| **T1: Requirements** | G3 approved | `@product-manager` | 3 days | No |
| Create `docs/requirements/chat_widget.md` — 50+ requirements covering: widget UI behavior, session lifecycle, message API contracts, conversation history, escalation in widget, client config schema, non-functional requirements (latency <2s, session TTL, idle timeout) | | | | |
| **T2: UX/UI Spec** | T1 complete | `@ux-ui-designer` | 3 days | Yes (parallel with T3) |
| Create `docs/ux-ui-spec/chat_widget.md` — widget visual design (mockups for button, chat window, message bubbles, typing indicator), color scheme (customizable per client), responsive breakpoints, accessibility (WCAG 2.1 AA), copywriting (welcome message, escalation holding text, error messages) | | | | |
| **T3: Architecture** | T1 complete | `@software-architect` | 4 days | Yes (parallel with T2) |
| Create `docs/architecture/chat_widget.md` — 10 sections: API contracts (3 new routes), session management (TTL, fingerprinting, expiration), database schema (DDL for `sessions`, migrations for `interactions_log` + `clients`), `message_handler` refactor (extract `_handle_message_core()`), widget JS architecture (module structure, state management, API client), CDN strategy (Railway static serve for Phase 1), load considerations (separate Railway service if widget traffic > 1000 req/min), identity linking placeholder (Phase 2 interface), escalation bridge placeholder (Phase 3 interface), monitoring (new metrics: widget sessions, message latency) | | | | |
| **T4: Test Plan** | T3 complete | `@sdet-engineer` | 3 days | No |
| Create `docs/test-plan/features/chat_widget.md` — unit tests (40+): session creation, TTL expiration, fingerprint fallback, message routing, channel isolation, config loading; integration tests (15+): end-to-end widget message flow, concurrent widget + WhatsApp, escalation in widget, conversation history fetch; load tests (3): 100 concurrent widget sessions, 500 messages/min sustained, memory leak check (24h session) | | | | |
| **T5: Database Migrations** | T4 complete | `@sdet-engineer` → `@software-engineer` | 2 days | No |
| Write + test migrations: `supabase/migrations/005_sessions_table.sql` (CREATE TABLE sessions), `006_interactions_channel.sql` (ALTER TABLE interactions_log ADD COLUMN channel, ADD COLUMN session_id), `007_clients_widget_config.sql` (ALTER TABLE clients ADD 4 widget_* columns). Test against HeyAircon Supabase (verify no breaking changes to existing queries). | | | | |
| **T6: Worktree Setup** | T5 complete | `@sdet-engineer` | 1 day | No |
| Create feature branch `feat/chat-widget-mvp`, set up worktree, scaffold 8 new files: `engine/api/chat_routes.py` (3 new routes), `engine/integrations/chat_widget.py` (send/log functions), `engine/static/widget.js` (widget UI), `engine/core/message_handler.py` (refactor + new `handle_widget_message()` entry point), `engine/tests/unit/test_chat_widget.py`, `engine/tests/integration/test_widget_flow.py`. Write stub implementations (raise NotImplementedError). | | | | |
| **T7: Implementation (Backend)** | T6 complete | `@sdet-engineer` → `@software-engineer` | 8 days | No (sequential slices) |
| **Slice 1 (2 days):** Session management — `sessions` table CRUD, TTL logic, fingerprint generation, `/chat/{client_id}/session` route. 15 unit tests. | | | | |
| **Slice 2 (3 days):** Message API — `handle_widget_message()`, channel-agnostic refactor of `message_handler.py` (extract `_handle_message_core()`), `/chat/{client_id}/message` route, `chat_widget.send_widget_message()`, `interactions_log` writes with `channel='chat_widget'`. 20 unit tests + 5 integration tests. | | | | |
| **Slice 3 (2 days):** History API — `/chat/{client_id}/history` route, query `interactions_log` by `session_id`, format response. 8 unit tests. | | | | |
| **Slice 4 (1 day):** Widget config loading — add `widget_*` columns to `ClientConfig`, fetch on widget load, return via `/chat/{client_id}/config` route. 5 unit tests. | | | | |
| **T8: Implementation (Frontend — Widget JS)** | T7 Slice 1 complete (can start after session API exists) | `@sdet-engineer` → `@software-engineer` | 5 days | Yes (parallel with T7 Slices 2–4) |
| Build `engine/static/widget.js` (vanilla JS, zero dependencies): button UI (floating, customizable position), chat window (open/close), message bubbles (user + agent), text input + send button, typing indicator, session init (call `/session` on first load), message send (POST to `/message`), history load (GET `/history` on window open), error handling (API failures, network timeout), localStorage (persist `session_id`). 12 unit tests (jsdom). | | | | |
| **T9: Static File Serving** | T8 complete | `@sdet-engineer` → `@software-engineer` | 1 day | No |
| Add `StaticFiles` mount to `engine/api/webhook.py`: `app.mount("/widget", StaticFiles(directory="engine/static"), name="widget")`. Verify widget loads at `https://{railway-url}/widget/{client_id}.js`. Add `/widget/{client_id}.js` route that serves `widget.js` with `client_id` injected as inline JS variable. | | | | |
| **T10: Integration Testing** | T9 complete | `@sdet-engineer` | 3 days | No |
| Run full test suite (55+ tests). End-to-end test: open widget in browser, send 3 messages, verify agent replies, check `interactions_log` (3 inbound + 3 outbound with `channel='chat_widget'`), verify session TTL (send message after 30 min idle → new session created). Concurrent test: widget + WhatsApp message at same time → verify no cross-talk. | | | | |
| **T11: Load Testing** | T10 complete | `@sdet-engineer` | 2 days | No |
| Locust or Artillery script: 100 concurrent widget sessions, 500 messages/min sustained for 10 min. Monitor Railway metrics (CPU, memory, response time). Confirm WhatsApp webhook latency unaffected (<500ms p95). If widget causes WhatsApp degradation, recommend separate Railway service (`flow-engine-widget`). | | | | |
| **T12: Flow AI Website Integration** | T11 complete | founder or `@sdet-engineer` | 1 day | No |
| Add `<script src="https://flow-ai-agent.railway.app/widget/flow-ai.js"></script>` to Flow AI website `<body>` tag. Update `clients` table: `UPDATE clients SET widget_enabled=TRUE, widget_primary_color='#4F46E5', widget_welcome_message='Hi! I''m the Flow AI assistant. Ask me about our platform or book a demo.' WHERE client_id='flow-ai'`. Test: visit flowai.app, click widget, send message, verify agent responds. | | | | |
| **T13: PR + Merge** | T12 complete | `@sdet-engineer` | 1 day | No |
| Open PR from `feat/chat-widget-mvp` → `main`. All tests passing (75+ total). Founder reviews widget UI on Flow AI staging site. Merge to `main`, promote to `release`, deploy to `flow-ai-agent` Railway. Widget live in production. | | | | |
| **T14: 2-Week Validation** | T13 complete | Founder + team | 2 weeks | N/A |
| Flow AI team uses widget for 2 weeks. Collect 20+ widget conversations. Compare agent response quality vs WhatsApp (same questions asked in both channels → responses should be equivalent). Identify UX friction (loading time, button placement, mobile responsiveness). Log bugs/improvements in `.flow/tasks/active.md`. **Gate passed** → offer widget to next pilot client (Phase 2 begins). | | | | |

#### Total Phase 1 Timeline: 6 weeks (wall time)

- **Weeks 1–2:** Requirements (T1), UX spec (T2), Architecture (T3), Test Plan (T4), Migrations (T5), Worktree (T6)
- **Weeks 3–4:** Backend implementation (T7: 4 slices), Frontend implementation (T8: parallel with T7 Slices 2–4)
- **Week 5:** Static serving (T9), Integration testing (T10), Load testing (T11)
- **Week 6:** Website integration (T12), PR/merge (T13), validation begins (T14: 2 weeks, overlaps with next work)

#### Critical Path

T1 → T3 → T4 → T5 → T6 → T7 (Slice 1) → T7 (Slice 2) → T10 → T11 → T12 → T13

Parallelizable: T2 ∥ T3, T8 ∥ T7 (after Slice 1)

#### Resource Requirements

- **1 full-time developer** (`@software-engineer` via `@sdet-engineer` dispatches) — 6 weeks
- **1 QA/SDET** (`@sdet-engineer`) — 6 weeks (test planning, integration testing, load testing, worktree management)
- **1 architect** (`@software-architect`) — 1 week (T3 only)
- **1 UX designer** (`@ux-ui-designer`) — 1 week (T2 only)
- **1 product manager** (`@product-manager`) — 1 week (T1 only)
- **Founder** — 1 day (T12 website integration + T14 validation)

---

## Appendix: Key Design Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|-------------------------|
| Widget served from Railway (not CDN) in Phase 1 | Simplifies deployment (widget + backend version-locked). Railway serves static files natively. CDN adds complexity (CI/CD, cache invalidation). Acceptable latency for <100 clients. | CDN (Cloudflare, AWS): deferred to Phase 2 when widget traffic justifies it (>100GB/month or global latency concerns). |
| Anonymous sessions (no login) in Phase 1 | Reduces friction (visitor can chat immediately, no signup form). Aligns with WhatsApp model (phone number is identifier, not email/password). Identity linking deferred to Phase 2. | Require email before first message: rejected (too much friction, contradicts "instant answers" value prop). |
| Session TTL = 30 days default | Balances conversation continuity (customer returns 1 week later, history is preserved) vs database bloat (30 days = ~1M sessions for 1K daily visitors). Configurable per client. | 7 days (too short, breaks multi-week sales cycles), 90 days (too long, database bloat), infinite (rejected for GDPR/PDPA compliance — chat logs must have expiration). |
| `interactions_log.channel` instead of separate `widget_messages` table | Unified conversation history (same query returns WhatsApp + widget). Simplifies context_builder (no JOIN needed). Same schema for both channels (direction, message_text, timestamp). | Separate table: rejected (duplicates schema, complicates unified history, breaks DRY). |
| `message_handler` refactor (extract `_handle_message_core()`) instead of duplicating logic | DRY — escalation gate, context builder, agent runner are channel-agnostic. Only send/log functions differ by channel. Refactor cost: 1 day. Duplication cost: maintenance drift + bugs. | Duplicate `message_handler` for widget: rejected (high maintenance burden, guaranteed drift, violates DRY). |
| Escalation in Phase 1 stops widget conversation (no bridging) | Simplifies MVP — no WebSocket, no state machine for buffering customer messages. Human agent replies via WhatsApp or email (customer switches channels). Acceptable for pilot. | Cross-channel bridge in Phase 1: rejected (too complex for MVP, delays launch by 4+ weeks). Phase 3 adds bridging after widget UX is validated. |

---

**Status:** Strategic plan complete. Awaiting founder direction frame approval (G3) before dispatching `@product-manager` to T1 (requirements).

**Next Action:** Founder confirms or revises direction frame:
- **Subject:** Website visitors who need immediate answers
- **Desired Outcome:** Visitor can interact with AI agent without leaving website or installing WhatsApp
- **Threat/Problem:** Friction of switching to WhatsApp app loses 40–60% of visitors (bounce rate)

If approved → dispatch `@product-manager` to create `docs/requirements/chat_widget.md`. If revised → update direction frame, re-evaluate Phase 1 scope, return for confirmation.
