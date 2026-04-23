# AGENTS.md — Flow AI Master Agent Index

> Owned by: chief-of-staff
> Last Updated: 2026-04-23

---

## Project: Flow AI

Vertical AI agent platform for SEA service SMEs. WhatsApp + website automation. Pilot client: HeyAircon.

---

## Active Documentation Artifacts

| Agent | Owns | Key Files |
|-------|------|-----------|
| chief-of-staff | `docs/status_log.md`, `AGENTS.md`, `docs/observability/observation-log.md` | This file; `/Users/nayirong/Desktop/Personal/Professional Service/Flow AI/docs/status_log.md`; observation log: `docs/observability/observation-log.md` |
| product-manager | `docs/requirements/` | Not yet created — see gap audit |
| ux-ui-designer | `docs/ux-ui-spec/` | Not yet created |
| software-architect | `docs/architecture/`, `docs/observability/` | `docs/architecture/00_platform_architecture.md` (platform engine architecture, live); `docs/architecture/code_map.md` (cold-start file index, all 15 engine files, Supabase data flow, where-to-look table); `docs/observability/sql-reference.md` (operational SQL queries for monitoring, 2026-04-21) |
| sdet-engineer | `docs/test-plan/`, worktrees | Not yet created |
| business-strategist | `docs/business-plan.md`, `docs/pitch-deck.md` | `Product/docs/business-plan.md` exists (partial) |
| growth-marketer | `docs/messaging-playbook.md`, etc. | Not yet created |
| planner | `docs/planning/` | Not yet created |
| finance-agent | `finance/`, `clients/{client_id}/invoices/` | `finance/invoice_generator.py`; skill: `~/.claude/skills/generate-invoice/SKILL.md` |

---

## Platform-Level Docs (Product/)

| File | Purpose |
|------|---------|
| `Product/docs/00_Master_Project_Document.md` | Platform vision, module map, 4-product architecture, phased delivery |
| `Product/docs/PRD-02_AI_WhatsApp_Agent.md` | Full PRD for AI WhatsApp agent — context engineering, tools, flows, requirements |
| `Product/docs/PRD-01_Client_Website.md` | PRD for client website |
| `Product/docs/PRD-03_CRM_Interface.md` | PRD for CRM interface |
| `Product/docs/PRD-04_Sales_Reporting.md` | PRD for sales reporting |
| `Product/docs/knowledge-schema.md` | Schema for all client knowledge base entries |
| `Product/docs/knowledge-standards.md` | Writing standards for knowledge base |
| `Product/docs/persona-framework.md` | Base persona framework all clients inherit |
| `Product/docs/safety-guardrails.md` | Platform-level hard safety rules |
| `Product/docs/business-plan.md` | Business plan (partial) |

---

## Client: HeyAircon

| File | Purpose |
|------|---------|
| `clients/hey-aircon/context.md` | Client context — business, purpose, constraints, integration points |
| `clients/hey-aircon/product/PRD.md` | Client PRD (stub — needs population) |
| `clients/hey-aircon/product/persona.md` | Agent persona definition (draft) |
| `clients/hey-aircon/product/knowledge/pricing.md` | Pricing knowledge |
| `clients/hey-aircon/product/knowledge/hours.md` | Operating hours |
| `clients/hey-aircon/plans/proj_plan.md` | Full customer + client journey, module definitions, roadmap |
| `clients/hey-aircon/plans/mvp_scope.md` | Phase 1 scope, Supabase schemas, migration plan, design decisions |
| `clients/hey-aircon/plans/build/00_architecture_reference.md` | Living architecture doc — infrastructure, workflows, known issues, go-live checklist |
| `clients/hey-aircon/plans/build/02_component_b_c_setup.md` | Build guide for Components B + C |
| `clients/hey-aircon/website/` | Static HTML website (built) |
| `engine/core/reset_handler.py` | Escalation reset handler — reply-to-message detection, keyword matching, clears `escalation_flag` + `escalation_notified` |
| `supabase/migrations/003_escalation_tracking.sql` | Escalation tracking table + 3 indexes |
| `supabase/migrations/004_escalation_notified.sql` | `escalation_notified` column on customers table |

---

## Agent Orchestration System (.flow/)

| File | Purpose |
|------|---------|
| `.flow/onboarding.md` | Client onboarding guide — 8-step process |
| `.flow/config.yaml` | Client registry |
| `.flow/templates/` | Client-specific agent template files |
| `.flow/tasks/active.md` | Active task queue |
| `.flow/tasks/blocked.md` | Blocked tasks |
| `.flow/tasks/done.md` | Completed tasks archive |

---

## Key Decisions on Record

| Decision | Location |
|----------|----------|
| Meta Cloud API direct (no BSP) | `00_architecture_reference.md` §8 |
| Supabase as CRM (migrated from Google Sheets) | `mvp_scope.md` §Stack Migration |
| Context engineering — business data in DB, not hardcoded | `00_architecture_reference.md` §8, `mvp_scope.md` |
| Binary escalation gate (Phase 1) | `mvp_scope.md` §DR-001 |
| LLM starting model: Claude Haiku 4.5 | Decided 2026-04-17 — lower cost, sufficient for booking flows; upgrade to Sonnet if eval scores fall short |
| LLM fallback: GPT-4o-mini (OpenAI) | Decided 2026-04-17 — activated per-request when Anthropic API unreachable; retries Anthropic on next message |
| n8n → Python orchestration engine (planned) | Decided 2026-04-15 — finish n8n D/E first, then build Python in parallel |
| Client config isolation: hybrid approach | Decided 2026-04-15 — non-sensitive fields in Supabase `clients` table; 5 secrets in Railway env vars (namespaced): `meta_whatsapp_token`, `supabase_url`, `supabase_service_key`, `anthropic_api_key`, `openai_api_key`. LLM keys per-client (each client billed on their own accounts). Migrate to secrets manager at 10–20 clients. |
| Monorepo | Decided 2026-04-15 — single repo; split before client 3 |
| Railway deployment model | Decided 2026-04-18 — Option A: one Railway project per client, all connected to same repo. Each project tracks `release` branch (not `main`) so deploys are explicit and per-client. Adding a client = new Railway project + 3 env vars + 1 Supabase row. |
| Google Sheets sync — Core, not bespoke | Decided 2026-04-20 — Post-write sync to external visibility layer is a portable platform pattern. Lives in `integrations/google_sheets.py`. Config flags (`sheets_sync_enabled`, `sheets_spreadsheet_id`) in `clients` table. Sheets failure is fire-and-forget — never rolls back Supabase write. Phase 2 will replace Sheets with dashboard; sync layer must not block that migration. Tables synced: `customers` + `bookings` only (`interactions_log` excluded). |
| Escalation reset mechanism | Decided 2026-04-22 — Reply-to-message + keyword matching ("done"/"resolved"/"ok" etc.) implemented in `reset_handler.py`. WhatsApp label-based reset rejected — Meta does not send webhook events for label removal. Human agent replies to escalation alert → agent detects `context_message_id` → matches keywords → clears `escalation_flag` + marks `resolved_at` in `escalation_tracking`. |
| Escalation holding reply — once only | Decided 2026-04-22 — `escalation_notified` column controls holding reply state. First inbound from escalated customer → send holding reply once + flip `escalation_notified=True`. Subsequent inbound → silently dropped (no reply, no agent call). On reset → `escalation_notified` reset to `False` for re-escalation. Prevents message spam to escalated customers. |
| Sheets sync on escalation reset | Decided 2026-04-22 — `reset_handler.py` calls `sync_customer_to_sheets()` immediately after clearing `escalation_flag` so CRM reflects updated state without waiting for customer's next message. Previously Sheets only updated when customer sent next message — now immediate. |

---

## Finance Agent

**Agent name:** `finance-agent`

**Role:** Invoice and billing automation for Flow AI clients. Lightweight — owns invoicing only, not financial modeling or pricing strategy.

**Owns:** `finance/` directory at project root.

**When to invoke:**
- Generating a new invoice for a client
- Regenerating or amending an existing invoice
- Onboarding a new client and producing their first invoice from a proposal
- Any task that requires converting proposal parameters into a PDF invoice

**How it works:**
1. Reads the client's proposal file (e.g., `clients/{client_id}/plans/*.pdf` or `.md`) to extract billing parameters
2. Calls `finance/invoice_generator.py` with extracted parameters (CLI or as a module)
3. Saves the output PDF to `clients/{client_id}/invoices/`

**Skill:** `generate-invoice` (at `~/.claude/skills/generate-invoice/SKILL.md`)

**Key file:** `finance/invoice_generator.py` — reusable CLI + importable module. No client-specific logic hardcoded. All parameters passed at call time.

**Hard constraints:**
- No HeyAircon-specific or any client-specific hardcoding in `finance/invoice_generator.py`
- Invoice output always goes to `clients/{client_id}/invoices/`
- Finance agent does not own pricing decisions — those come from the proposal/product-manager artifacts

### HeyAircon Billing Details

These are the bill-to fields for HeyAircon invoices. Pass these at call time when generating or regenerating any HeyAircon invoice.

| Field | Value |
|-------|-------|
| Client name | HeyAircon |
| Contact | +65 8841 9968 |
| Address | *(blank — to be filled when available)* |
| Invoice output directory | `clients/hey-aircon/invoices/` |
| Payment terms | Bank transfer to DBS Savings 030-64719-0 |

---

## Agent-to-File Routing

| Task | Read first |
|------|-----------|
| Understanding which code file handles what | `docs/architecture/code_map.md` |
| Monitoring API usage, incidents, guardrails, or writing SQL analytics queries | `docs/observability/sql-reference.md` |
| Reviewing founder testing observations, picking up `#needs-review` entries, dispatching to agents | `docs/observability/observation-log.md` |

---

## Hard Rules — Git Worktree Discipline

These rules exist because two separate worktrees (`feat/telegram-alerts`, `feat/llm-observability`) were lost on 2026-04-22 when `git worktree remove --force` removed branches whose commits existed only in the worktree working tree — never as committed git objects. Approximately 3 hours of implementation work was lost twice.

### sdet-engineer — Merge Gate (Hard Rule)

Before running `git merge feat/*` on main, always run:

```
git log main..feat/<branch-name> --oneline
```

Confirm there is at least one commit in the output (i.e., the feature branch has commits that main does not). If the output is empty, do NOT merge. Return to the software-engineer and require them to `git add` and `git commit` inside the worktree first. A passing test suite does NOT imply committed code. Tests run against working-tree files; `git merge` only operates on committed objects.

### software-engineer — Commit Before Done (Hard Rule)

After writing code and before reporting work complete:

1. Run `git add -p` (or `git add <files>`) inside the worktree.
2. Run `git commit -m "..."` with a descriptive message.
3. Run `git log --oneline -5` to confirm the commit appears.
4. Only then report "done" to the sdet-engineer.

Do NOT exit the worktree or report "done" without a committed `git log` entry showing the work. Passing tests are not a substitute for a commit. If the worktree is removed before committing, all work is permanently lost.

---

## Deployment & Integration Hard Rules

These rules were added after the 2026-04-24 session post-mortem, which identified 4 rework clusters totaling 20 commits. Each rule addresses a specific avoidable failure mode.

### Platform Feature Check Gate (Hard Rule)

Before implementing code-level workarounds for deployment or infrastructure constraints (Railway root changes, environment variable hacks, sys.path manipulation, custom routing layers), always check the platform's native feature set first:
- Railway: Watch Paths, project-level env vars, custom start commands, build settings
- Supabase: RLS policies, database functions, triggers, extensions
- Meta API: webhook validation, message templates, interactive components
- Google Calendar API: service account sharing, event visibility settings

**Why this exists:** The 2026-04-24 Railway isolation issue was solved with Watch Paths (a native Railway feature) after 4 commits of code changes (root to `/engine`, sys.path hack, GitHub Actions workflow) were attempted and fully reverted. All 4 commits were avoidable.

**When to apply:** Any time a task involves deployment configuration, cloud platform constraints, or third-party API limitations.

### Backend Bypass Preference Rule (Hard Rule)

For high-frequency deterministic flows where intent is unambiguous (confirmation, cancellation, yes/no branching, single-action shortcuts), prefer backend logic over LLM orchestration. Backend bypass pattern:
1. Detect intent signal (keyword match, button press, reply-to-message context)
2. Verify preconditions (e.g., `pending_confirmation` booking exists)
3. Call tool directly without LLM invocation
4. Return structured response to user

Prompt engineering is the fallback for ambiguous or low-frequency interactions where context complexity justifies LLM cost.

**Why this exists:** The 2026-04-24 Slice 2 booking confirmation loop required 3 commits to fix via prompt tuning, history deduplication, and guardrail expansion. Backend bypass (`message_handler.py` detects affirmative + pending booking → calls `confirm_booking` directly) eliminated the entire class of LLM confusion on first attempt.

**When to apply:** User confirms/cancels an action, replies yes/no to a binary question, or takes a shortcut action (e.g., "book the first slot"). If the intent and preconditions are programmatically detectable, bypass the LLM.

### Integration Fallback Strategy Rule (Hard Rule)

All external integration points (webhooks, reply-to-message, third-party API callbacks, event-driven flows) must include fallback logic for stale, missing, or out-of-order identifiers. Integration design requires:
1. **Primary path:** Expected identifier present and valid (e.g., `alert_msg_id` matches latest escalation)
2. **Recovery path:** Identifier missing/stale — fallback to secondary lookup (e.g., extract phone number from historical message, find latest unresolved escalation for that customer)
3. **Error path:** No valid match found — log incident, send graceful user-facing error, do not crash

Do NOT assume external systems will deliver identifiers in the expected order or state. Reply-to-message can reference old alerts. Webhooks can arrive out of order. Callbacks can contain stale references.

**Why this exists:** The 2026-04-24 escalation reset failure occurred when a human agent replied "done" to an older alert. `reset_handler.py` looked up `escalation_tracking` by exact `alert_msg_id`, but newer unresolved escalations existed with different IDs. Primary lookup failed. Fix required fallback recovery: extract phone from historical alert → find latest unresolved escalation.

**When to apply:** Any integration that depends on message IDs, webhook payloads, event references, or third-party identifiers. If the identifier can become stale or ambiguous, design fallback recovery before the primary integration goes live.

### External Sync Primary Key Stability Rule (Hard Rule)

Sync layers to external systems without native foreign keys (Google Sheets, third-party CRMs, flat file exports) must use a primary key that:
1. **Exists from first write** — key field must be populated when the record is created, not added later
2. **Stable across all states** — key must not change when record transitions between states (pending → confirmed, draft → published, new → updated)
3. **Unique and deterministic** — key must uniquely identify the record and produce the same value on every sync operation

For bookings: use `booking_id` (stable, exists immediately) NOT `id` (nullable, assigned only after confirmation).  
For customers: use `phone_number` or stable `customer_id` NOT row index or mutable fields.

**Why this exists:** The 2026-04-24 Google Sheets duplicate booking rows issue occurred because `_booking_to_row()` used `id or booking_id` as the first column (row key). Pending write used `booking_id` (no numeric `id` yet). Confirmed write used `id` (now present). `_sync_row()` matched by first column — treated them as different rows, appended instead of updating. Fix: consistently prefer `booking_id or id` so pending and confirmed map to same row.

**When to apply:** Any sync integration to external systems (Sheets, third-party APIs, data exports). Define the stable key upfront in the architecture phase. Test with records in all lifecycle states (pending, confirmed, cancelled, expired) to verify key stability.

---

## Migration Gating Rules

n8n docs in `clients/hey-aircon/plans/build/` are **preserved and untouched** until:
1. Python engine is verified in production (real WhatsApp, real Meta webhook) — **PASSED** as of 2026-04-19
2. Meta webhook cutover is confirmed — **PASSED** as of 2026-04-19
3. 48h production verification window cleared — **In Progress** (started 2026-04-19)
4. Google Calendar integration confirmed working (GCP Calendar API enabled + events appearing) — **Blocked**
5. Explicit approval given to archive n8n docs — **Pending**

Do not archive, rename, or modify `clients/hey-aircon/plans/build/` until all five gates are passed.
