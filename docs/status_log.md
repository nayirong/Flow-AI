# Flow AI — Project Status Log

> Owned by: chief-of-staff
> Last Updated: 2026-04-15

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
| Supabase migration | To-Do | Decided and spec'd in mvp_scope.md; must complete before Component E |
| Meta credentials | Blocked | META_PHONE_NUMBER_ID and META_WHATSAPP_TOKEN pending Meta dev account setup |
| hey-aircon website | Built | Static HTML site at clients/hey-aircon/website/ |
| docs/ folder | Missing | No docs/ directory exists — agent ownership model not yet mapped |
| AGENTS.md | Created | This session |
| .claude/CLAUDE.md | Empty | Needs content — see assessment output |

---

## Feature Tracking

### HeyAircon Phase 1 — WhatsApp Agent MVP

| Component | Status | Notes |
|-----------|--------|-------|
| A: Webhook + Meta integration | Complete | Railway running, curl tests pass, pending real Meta credentials |
| B: Escalation gate | Complete | Binary gate with holding reply on TRUE branch |
| C: AI Agent (GPT-4o-mini + Postgres Chat Memory) | Complete | Context engineering working; Config + Policies via Supabase |
| D: Booking tools (calendar + write_booking) | In Progress | Build pending Meta dev account to test end-to-end |
| E: Escalate-to-human tool | Not Started | Blocked — build only after Supabase migration complete |
| Supabase migration | To-Do | Spec complete in mvp_scope.md; pre-requisite for Component E |
| Meta dev account | Blocked | Client action required |
| Go-live checklist | Incomplete | See architecture_reference.md §10 |

### Platform — Multi-client Engine Migration

| Item | Status | Notes |
|------|--------|-------|
| n8n → Python orchestration engine | Planning | Architecture not yet designed; migration plan produced this session |
| docs/ folder structure | Planning | Proposed this session; awaiting implementation |
| .claude/CLAUDE.md | Draft | Content proposed this session; awaiting write |

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
| 2026-04-16 | Evaluation pipeline initiative approved. Plan saved to `docs/planning/eval_pipeline_plan.md`. `@product-manager` dispatched to produce `docs/requirements/eval_pipeline.md`. |
| 2026-04-15 | Bootstrap session: full project audit completed. Agent doc gaps identified. Migration plan produced. Project structure proposal made. CLAUDE.md content drafted. |
