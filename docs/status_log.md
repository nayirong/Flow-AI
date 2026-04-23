# Flow AI — Project Status Log

> Owned by: chief-of-staff
> Last Updated: 2026-04-23

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
| Pending Confirmation booking status + auto-follow-up | Awaiting PM Requirements | New booking status value (`Pending Confirmation`) when agent has gathered all info but not yet received final confirmation. Requires: new `booking_status` value, agent tool/flow change, conversation state tracking, scheduled follow-up mechanism (new infra), message template. Dependency: Postgres trigger for `total_bookings` (migration 002) should only fire on `Confirmed` status inserts. Blocked on `@product-manager` requirements. 2026-04-20. |

---

## Session Log

| Date | Event |
|------|-------|
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
