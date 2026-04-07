# Flow AI — Client Onboarding Guide

> Reference for onboarding new clients into the Flow AI agent orchestration system.

---

## Prerequisites

Before starting, ensure you have:
- Access to the Flow AI workspace root
- The client ID (lowercase, hyphenated — e.g. `acme-corp`)
- The client display name (e.g. `Acme Corp`)
- A contact at the client who can confirm knowledge base content (pricing, hours, services)

---

## Step 1 — Scaffold the Client Directory

Run the onboarding script from the Flow AI workspace root:

```bash
bash .flow/scripts/new-client.sh <client-id> "<Client Display Name>"
```

**Example:**
```bash
bash .flow/scripts/new-client.sh acme-corp "Acme Corp"
```

This will create:
```
clients/acme-corp/
├── context.md
├── .agents/
│   ├── orchestrator.md
│   ├── pm-agent.md
│   ├── engineering-agent.md
│   ├── qa-agent.md
│   ├── prompt-persona-agent.md
│   └── knowledge-agent.md
└── product/
    ├── PRD.md
    ├── changelog.md
    ├── persona.md
    └── knowledge/
        ├── pricing.md
        ├── hours.md
        ├── faqs/
        ├── services/
        └── policies/
```

---

## Step 2 — Fill in Client Context

Open `clients/<client-id>/context.md` and complete all `[TO FILL]` sections:

- **Business** — industry, primary users, internal users
- **AI Agent Purpose** — what the AI agent is expected to do
- **Key Constraints** — business rules the agent must respect
- **Integration Points** — CRM, booking system, WhatsApp, other tools

This file is the single source of truth for all client agents. Do not leave it incomplete before activating any agent.

---

## Step 3 — Configure Agent-Specific Rules

Each agent has client-specific rules that need to be tailored. Open each file and replace the `[TO FILL]` placeholders:

| File | What to Fill |
|------|-------------|
| `.agents/pm-agent.md` | Client-specific constraints (compliance, escalation rules) |
| `.agents/prompt-persona-agent.md` | Brand voice, off-limits topics, escalation triggers |
| `.agents/knowledge-agent.md` | Knowledge sources, approval process, expiry rules |

---

## Step 4 — Register the Client in Config

Open `.flow/config.yaml` and add the new client under `clients:`:

```yaml
clients:
  <client-id>:
    path: clients/<client-id>
    agents: clients/<client-id>/.agents
    context: clients/<client-id>/context.md
    product: clients/<client-id>/product
    knowledge_base: clients/<client-id>/product/knowledge
    prompt_library: clients/<client-id>/product/prompts
    persona: clients/<client-id>/product/persona.md
```

---

## Step 5 — Populate the Knowledge Base

Work with the client contact to fill in the knowledge base. All entries require a confirmed source before going live.

### Priority order:
1. `product/knowledge/hours.md` — operating hours (needed before any booking flow)
2. `product/knowledge/pricing.md` — pricing (needed before any quote flow)
3. `product/knowledge/services/` — service catalogue entries (one file per service)
4. `product/knowledge/faqs/` — FAQ entries (one file per category)
5. `product/knowledge/policies/` — cancellation, refund, and other policies

Use the schemas in [Product/docs/knowledge-schema.md](../../Product/docs/knowledge-schema.md) for all entry formats.
Use the writing standards in [Product/docs/knowledge-standards.md](../../Product/docs/knowledge-standards.md).

---

## Step 6 — Define the Agent Persona

Open `product/persona.md` and complete the persona definition with the client:

- **Agent Name** — what the AI agent calls itself to customers
- **Tone** — e.g. friendly, professional, concise
- **Personality Traits** — 3–5 defining characteristics
- **Must Always / Must Never** — client-specific behavioural rules (on top of platform guardrails)
- **Escalation Triggers** — when the agent hands off to a human coordinator

All personas must comply with [Product/docs/persona-framework.md](../../Product/docs/persona-framework.md) and [Product/docs/safety-guardrails.md](../../Product/docs/safety-guardrails.md).

---

## Step 7 — Initialise the PRD

Open `product/PRD.md` and work with the Hey Aircon PM Agent (or human PM) to document:

- Project overview and goals
- In-scope and out-of-scope features
- Functional and non-functional requirements

The PRD must be in place before the Engineering Agent is assigned any tasks.

---

## Step 8 — Verify the Setup

Run through this checklist before the client goes live:

- [ ] `context.md` — all `[TO FILL]` sections completed
- [ ] `.agents/pm-agent.md` — client-specific rules added
- [ ] `.agents/prompt-persona-agent.md` — brand voice and escalation rules added
- [ ] `.agents/knowledge-agent.md` — knowledge sources and approval process defined
- [ ] `product/knowledge/hours.md` — operating hours confirmed and sourced
- [ ] `product/knowledge/pricing.md` — pricing confirmed and sourced
- [ ] `product/persona.md` — persona definition completed
- [ ] `product/PRD.md` — initial requirements documented
- [ ] `.flow/config.yaml` — client registered under `clients:`

---

## Reference

| Resource | Path |
|----------|------|
| Shared skill definitions | `.flow/skills/` |
| Core agent definitions | `.flow/agents/` |
| Handoff protocol | `.flow/protocols/handoff-protocol.md` |
| Escalation protocol | `.flow/protocols/escalation-protocol.md` |
| Change request protocol | `.flow/protocols/change-request-protocol.md` |
| Knowledge schema | `Product/docs/knowledge-schema.md` |
| Knowledge standards | `Product/docs/knowledge-standards.md` |
| Persona framework | `Product/docs/persona-framework.md` |
| Safety guardrails | `Product/docs/safety-guardrails.md` |
| New client script | `.flow/scripts/new-client.sh` |
