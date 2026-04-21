# Flow AI — Project Status Log

> Owned by: chief-of-staff
> Last Updated: 2026-04-21

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
| E: Escalate-to-human tool | Not Started | Next to build. No outstanding blockers. |
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

---

## Backlog — Pending PM Requirements

| Feature | Status | Notes |
|---------|--------|-------|
| Pending Confirmation booking status + auto-follow-up | Awaiting PM Requirements | New booking status value (`Pending Confirmation`) when agent has gathered all info but not yet received final confirmation. Requires: new `booking_status` value, agent tool/flow change, conversation state tracking, scheduled follow-up mechanism (new infra), message template. Dependency: Postgres trigger for `total_bookings` (migration 002) should only fire on `Confirmed` status inserts. Blocked on `@product-manager` requirements. 2026-04-20. |

---

## Session Log

| Date | Event |
|------|-------|
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
