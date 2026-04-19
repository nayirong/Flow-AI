# Flow AI — Project Status Log

> Owned by: chief-of-staff
> Last Updated: 2026-04-19

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
| Google Calendar integration | Blocked | `write_booking` fails with 404 — service account not yet granted access to `agent.heyaircon@gmail.com` calendar. Fix identified; awaiting user action. |
| hey-aircon website | Built | Static HTML site at clients/hey-aircon/website/ |
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
| D: Booking tools (calendar + write_booking) | Live (partial) | `check_calendar` and `create_event` operational; `write_booking` blocked on Google Calendar 404 (service account access not granted) |
| E: Escalate-to-human tool | Not Started | Awaiting Google Calendar fix and 48h production verification |
| Supabase (shared platform) | Complete | Tables provisioned; HeyAircon row live |
| Meta dev account | Complete | Webhook verified, real traffic flowing as of 2026-04-19 |
| Google Calendar fix | Pending User Action | Share calendar `agent.heyaircon@gmail.com` with service account `client_email` from `HEY_AIRCON_GOOGLE_CALENDAR_CREDS` |
| Per-client LLM keys | Complete | `ClientConfig` carries `anthropic_api_key` and `openai_api_key` from Railway env vars. Shared platform `ANTHROPIC_API_KEY` removed. |
| Go-live / 48h verification | In Progress | Engine live as of 2026-04-19; monitoring for 48h before n8n decommission decision |

### Platform — Multi-client Engine Migration

| Item | Status | Notes |
|------|--------|-------|
| n8n → Python orchestration engine | Live in Production | Real WhatsApp traffic processed 2026-04-19 |
| docs/ folder structure | Complete | Established earlier in project lifecycle |
| .claude/CLAUDE.md | Current | Blockers and migration status updated 2026-04-19 |
| Architecture doc (`00_platform_architecture.md`) | Stale — Update In Progress | Delegated to `@software-architect` 2026-04-19 — model names, `ClientConfig` fields, Railway env vars table, deployment phase, migration checklist all need updating |
| n8n decommission | Pending | Awaiting 48h production verification + Google Calendar fix confirmation |

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

| Date | Event |
|------|-------|
| 2026-04-19 | Code map created: `docs/architecture/code_map.md` — living quick-reference mapping every `engine/` file to its role in the end-to-end message flow, Supabase data flow, and "where to look" developer routing table. Delegated to `@software-architect`. `AGENTS.md` and `.claude/CLAUDE.md` updated with routing entry and hard rule to keep code map current. |
| 2026-04-19 | Python engine confirmed live in production. Meta webhook verified and receiving real WhatsApp traffic for HeyAircon. Per-client LLM keys (`{CLIENT_ID_UPPER}_ANTHROPIC_API_KEY`, `{CLIENT_ID_UPPER}_OPENAI_API_KEY`) implemented in `ClientConfig`; shared `ANTHROPIC_API_KEY` removed from `Settings`. Shared Supabase (`flowai-platform`) fully provisioned with `api_incidents`, `api_usage`, `clients` tables; HeyAircon row live. Google Calendar 404 bug identified — service account not granted calendar access; fix pending user action. `status_log.md` and `.claude/CLAUDE.md` updated. Architecture doc (`docs/architecture/00_platform_architecture.md`) update delegated to `@software-architect`. |
| 2026-04-18 | HeyAircon billing details recorded: `AGENTS.md` Finance Agent section updated with HeyAircon bill-to fields (contact +65 8841 9968, address TBD, payment terms). Both existing invoices (INV-HA-20260401, INV-HA-20260402) regenerated with updated client contact via `finance/invoice_generator.py` — output to `clients/hey-aircon/invoices/`. |
| 2026-04-18 | Finance agent initiative: `AGENTS.md` updated with `finance-agent` entry. `finance/invoice_generator.py`, `generate-invoice` skill, and `.claude/CLAUDE.md` updates pending — routed to `@sdet-engineer`. PDF proposal unreadable in this environment (poppler not installed) — billing field extraction blocked until PDF is accessible or fields are provided manually. |
| 2026-04-16 | Evaluation pipeline initiative approved. Plan saved to `docs/planning/eval_pipeline_plan.md`. `@product-manager` dispatched to produce `docs/requirements/eval_pipeline.md`. |
| 2026-04-15 | Bootstrap session: full project audit completed. Agent doc gaps identified. Migration plan produced. Project structure proposal made. CLAUDE.md content drafted. |
