# AGENTS.md — Flow AI Master Agent Index

> Owned by: chief-of-staff
> Last Updated: 2026-04-18

---

## Project: Flow AI

Vertical AI agent platform for SEA service SMEs. WhatsApp + website automation. Pilot client: HeyAircon.

---

## Active Documentation Artifacts

| Agent | Owns | Key Files |
|-------|------|-----------|
| chief-of-staff | `docs/status_log.md`, `AGENTS.md` | This file; `/Users/nayirong/Desktop/Personal/Professional Service/Flow AI/docs/status_log.md` |
| product-manager | `docs/requirements/` | Not yet created — see gap audit |
| ux-ui-designer | `docs/ux-ui-spec/` | Not yet created |
| software-architect | `docs/architecture/` | Not yet created — current architecture lives at `clients/hey-aircon/plans/build/00_architecture_reference.md` |
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

---

## Migration Gating Rules

n8n docs in `clients/hey-aircon/plans/build/` are **preserved and untouched** until:
1. Python engine is verified in production (real WhatsApp, real Meta webhook)
2. Meta webhook cutover is confirmed
3. Explicit approval given to archive n8n docs

Do not archive, rename, or modify `clients/hey-aircon/plans/build/` until all three gates are passed.
