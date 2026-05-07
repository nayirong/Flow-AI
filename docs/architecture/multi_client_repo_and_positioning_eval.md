# Flow AI — Multi-Client Repo Strategy & Positioning Evaluation

**Owner:** chief-of-staff  
**Date:** 2026-05-07  
**Status:** Decision-Pending — Founder Review Required  
**Trigger:** Monorepo complexity surfacing at 2 clients; opportunity to migrate one client before it worsens  

---

## Framing

This document evaluates two interlocked questions:

1. **Repo strategy:** How should Flow AI manage code and configuration as client count grows?
2. **Positioning:** Should Flow AI operate as a SaaS product or as an enterprise/managed service (Agent-as-a-Service)?

These questions are not independent. The correct answer to one constrains the answer to the other. They are evaluated together at the end.

---

## Part 1 — Multi-Client Repo Strategy

### What's Breaking Right Now

The monorepo is showing three concrete failure modes at just 2 clients:

**1. Branch promotion is manual and fragile.**
`deploy/hey-aircon` and `deploy/flow-ai` require explicit per-client pushes. The old `release` branch was deprecated after a single incident where both clients were deployed simultaneously. This workaround solves the symptom but not the root problem: the engine and the client context live in the same change surface.

**2. Agent context is bloating.**
CLAUDE.md, AGENTS.md, and the `.flow/` task queue all carry multi-client knowledge. Every AI-assisted dev session requires loading context for both clients even when working on one. This will degrade agent decision quality and increase per-session cost as clients 3, 4, and 5 are added.

**3. Confidentiality boundaries are informal.**
Client isolation is enforced at runtime (per-request Supabase connections) but not at the repository level. A contractor hired to work on hey-aircon has theoretical access to flow-ai's context, knowledge base, and deployment config. This is acceptable at 2 clients but becomes a liability at 10.

---

### Option A: Stay Monorepo (Status Quo)

**What it looks like:**
- Single repo, single engine, N `clients/{client_id}/` directories
- Per-client deploy branches in Railway
- Engine changes land in `master`, promoted selectively

**Honest pros:**
- Engine updates are atomic — fix a bug once, all clients benefit
- Single test suite — eval pipeline covers all clients simultaneously
- Low ops overhead now — one CI/CD pipeline, one Railway account

**Critical cons:**

| Problem | Current severity | At 10 clients |
|---------|-----------------|--------------|
| Per-client branch management | Manageable | Unmanageable — 10 branches to manually promote changes across |
| Agent context window | Acceptable | Degraded — CLAUDE.md grows proportionally; agent makes more cross-client errors |
| Confidentiality leakage | Low risk (founder only) | Real risk if contractors involved |
| Merge conflict surface | Low | High — client A knowledge base changes merge against client B schema migrations |
| Railway env var namespace | 5 vars × 2 clients = 10 vars | 5 vars × 10 clients = 50 vars in one Railway service |

**Verdict:** This model has a real ceiling. The current architecture was correctly designed for 2 clients on a tight timeline. It was never designed for 10+. Each additional client adds friction that compounds non-linearly.

---

### Option B: One Client, One Repo

**What it looks like:**
- `flow-ai-engine` monorepo (engine code only — no client config)
- `client-hey-aircon` repo (imports engine, contains all client-specific content)
- `client-flow-ai` repo (same pattern)
- Engine changes propagate via Git submodule, Python package, or copy-push

**Honest pros:**
- Full isolation — contractor for hey-aircon sees only hey-aircon's repo
- Cleaner CI/CD — each client's Railway project tracks its own repo, not a branch
- Agent context is scoped — working on hey-aircon loads only hey-aircon's docs
- No accidental cross-client deployments

**Critical cons:**

| Problem | Severity |
|---------|---------|
| Engine update propagation | **High.** Every bug fix must be applied to N client repos. Without a package model, drift is inevitable within 3 months. |
| No obvious propagation mechanism | Submodules are notoriously messy. Copy-push is manual and error-prone. PyPI package adds versioning overhead. |
| Testing surface fragments | Eval pipeline must run separately per client. Cross-client regression tests become harder. |
| More repos = more cognitive overhead | 10 clients = 11 repos to context-switch between. |

**Verdict:** Solves the confidentiality and context problems but creates an engine propagation problem that will become the next operational bottleneck. Not the right answer in isolation.

---

### Option C: Engine-as-Package, Client Repos (Recommended)

**What it looks like:**
- `flow-ai-engine` repo: the Python orchestration engine, published as a private package (PyPI or GitHub Packages). Contains all of `engine/core/`, `engine/integrations/`, `engine/api/`, `engine/config/`. No client-specific logic.
- Per-client repos (`client-hey-aircon`, `client-flow-ai`, etc.): `requirements.txt` pins the engine version. Client repo contains only: `clients/{client_id}/` knowledge base, persona, Supabase seed files, and a thin deployment config.
- Versioned releases: `engine v1.2.0` — clients can pin stable releases and upgrade on their own schedule.

**Honest pros:**
- Engine improvements are a versioned release, not a manual cherry-pick
- Client repos are small, clean, contractor-safe
- Each client can be on a different engine version if needed (stability vs. new features)
- Railway CI/CD is clean — client repo push → deploy that client's Railway service
- Agent context is appropriately scoped per session

**Critical cons:**

| Problem | Severity | Mitigation |
|---------|---------|-----------|
| Package publishing overhead | Medium | GitHub Packages (private) is low-friction for a private repo. One `pip install` from `requirements.txt`. |
| Version pinning discipline | Medium | Must commit to semantic versioning from day 1. Client upgrades are now a manual decision — which is actually safer. |
| Local dev complexity | Low | `pip install -e ../flow-ai-engine` for dev mode. Standard Python practice. |
| Migration effort from current monorepo | Medium | 1–2 days of repo restructuring. Not a crisis. |

**Verdict:** This is the architecture that scales. The engine is the platform. Client repos are deployments. This mirrors how mature SaaS companies separate their core product from client-specific configuration.

---

### Repo Strategy Recommendation

**Move to Option C.** Do it now while you only have 2 clients. The migration cost is low now; it will be high at 10.

**Migration path:**
1. Extract `engine/` into a new `flow-ai-engine` repo. Tag `v0.1.0`.
2. Add `engine/` to `.gitignore` in the current monorepo. Replace with `pip install flow-ai-engine==0.1.0`.
3. Create `client-hey-aircon` and `client-flow-ai` repos. Move their respective `clients/{client_id}/` directories there.
4. Point each Railway project at its corresponding client repo (not a branch — a repo).
5. Archive the monorepo or keep it as the engine development repo.

**Exception:** If the client triggering this conversation (client with issues) is already in a state where migration is feasible, do it now. Don't wait for the engine to be perfectly packaged — a working `pip install -e` local dev setup is good enough to start.

---

## Part 2 — Positioning: SaaS vs. Agent-as-a-Service

### The Central Honest Observation

Read the following and sit with it for a moment:

> Flow AI currently operates as a **managed service disguised as a SaaS product.**

The evidence:
- Onboarding is an 8-step manual process owned by the founder
- Each client has a custom knowledge base, custom persona, custom Supabase schema seeds
- Each client has a custom Railway deploy branch / project with manually configured env vars
- There is no self-serve portal, no client-facing dashboard, no automated onboarding
- The AI agent loop, context builder, and tool definitions require engineering changes per client vertical

This is not a criticism. It is the correct approach for a 2-client, pre-PMF company. The problem is that the **pricing does not reflect this reality**.

At SGD 79–699/month, Flow AI is priced as a SaaS product. But the delivery model is a software house. This mismatch has consequences:

| Metric | SaaS at $699/mo | Managed Service at $699/mo |
|--------|-----------------|---------------------------|
| Revenue to cover founder's time | $699 | $699 |
| Realistic founder hours per client/month | 2–3 hours (if truly self-serve) | 15–30 hours (current reality) |
| Implied hourly rate | $233–$350/hr | $23–$47/hr |
| Break-even clients to replace $10k/month income | 15 clients | 15 clients |
| Founder capacity at 15 clients (30 hrs/client) | 0 hours for anything else | Physically impossible |

**The math is broken at current pricing if the delivery model stays manual.**

---

### SaaS Model — Critical Evaluation

**What SaaS actually requires:**
1. A product that any client can configure without founder involvement
2. A self-serve onboarding flow (signup → connect WhatsApp → configure knowledge base → go live)
3. Standardized pricing tiers that clients self-select into
4. Support infrastructure (docs, ticketing, automated monitoring)
5. A dashboard for clients to manage their own agent

**Where Flow AI is today:**
- None of these exist
- Product 3 (CRM Interface) and a client-facing configuration dashboard are not built
- WhatsApp Business API access requires Meta account setup — non-trivial for non-technical SME owners
- Knowledge base management requires editing Supabase tables directly

**Time-to-SaaS estimate (honest):** 6–12 months of product development to reach genuine self-serve. This assumes the CRM dashboard, onboarding flow, and knowledge base editor are all built.

**Revenue at SaaS pricing before self-serve exists:** Marginal. At $79/month, 50 clients = SGD 3,950/month — a founder salary that comes with 50 clients' worth of support burden.

**Verdict on SaaS:** Not the right positioning for the next 12 months. The product is not there yet. Positioning as SaaS at current pricing will create a treadmill: acquire clients at low prices, burn founder time on manual delivery, revenue never exceeds operational overhead.

---

### Enterprise / Software House / AaaS Model — Critical Evaluation

**What AaaS (Agent-as-a-Service) actually means:**
- You are selling an outcome, not a software subscription
- Clients pay for "an AI agent that handles our WhatsApp bookings" not "access to a platform"
- Pricing reflects implementation + management + results, not seat count or message volume
- Engagement model: discovery → proposal → implementation → ongoing managed service

**What this looks like for Flow AI:**
- Setup fee: SGD 3,000–8,000 (implementation, knowledge base, testing, go-live)
- Monthly retainer: SGD 1,500–4,000 (ongoing management, updates, monitoring, escalation handling)
- Included: founder manages everything — Supabase config, agent prompt tuning, new service additions, monitoring
- Excluded: client doesn't touch anything; they just receive leads and bookings in their Sheets/CRM

**Revenue math:**
| Clients | Monthly Retainer (avg $2,500) | Annual Revenue |
|---------|------------------------------|----------------|
| 5 | $12,500/month | $150,000/year |
| 10 | $25,000/month | $300,000/year |
| 15 | $37,500/month | $450,000/year |

At 10 clients paying $2,500/month retainer, that's $25,000 MRR. This is achievable with a 1-person operation managing standardized-but-configured implementations.

**Honest cons of AaaS:**

| Risk | Reality |
|------|---------|
| Scales with headcount, not code | You hit a wall at 8–12 clients as a solo founder. Growth requires hiring. |
| Hard to productize later | Clients used to full-service managed relationships resist self-serve migration |
| Perceived as a vendor, not a platform | Harder to raise funding; investors want ARR with low COGS, not service revenue |
| Client dependency risk | Lose 2 big clients and revenue drops significantly vs. distributed SaaS base |

---

### The Real Trade-off Is Not SaaS vs. AaaS — It's Timing

Neither model is categorically right. The question is what posture makes sense at **this stage** vs. what you build toward.

Here is a brutally honest read of the strategic landscape:

**The market window is real but not infinite.** Respond.io is well-funded, SEA-native, and adding AI capabilities. If they ship a credible LLM reasoning layer on top of their WhatsApp infrastructure in 2026, your whitespace compresses meaningfully. Speed to market matters.

**The product is not ready for self-serve.** You can price and market as SaaS today but the delivery is manual. This is not sustainable at scale and creates client experience risk — a client who signs up for a "SaaS product" and receives a manual onboarding call and Supabase table edits will feel confused about what they bought.

**Managed service pricing funds the product.** The margin from 5 clients at $2,500/month = $12,500 MRR funds the 6–12 months of product development required to build self-serve SaaS. This is the "productize the service" pattern: sell a managed outcome, use the revenue and learnings to build the standardized product.

**High-touch early clients create the vertical dataset.** Every manual implementation produces signal: which knowledge base patterns work, which tool definitions fail, which escalation flows clients actually want. This signal cannot be bought. It is the foundation of your vertical moat.

---

### Positioning Recommendation: Managed AI Implementation → Platform

**Phase 1 (Now — 12 months): Managed AI Implementation Service**

External positioning: "We implement and manage an AI agent for your WhatsApp business — no technical work required on your side."

Pricing:
- Setup fee: SGD 3,000–6,000 (implementation, knowledge base config, testing, go-live)
- Monthly retainer: SGD 1,500–3,000 (ongoing management, monitoring, updates)
- Target: 5–10 clients

This is what you are already doing. Name it correctly and price it correctly. Stop underselling.

Internal reality: Every implementation is built on the same engine (`flow-ai-engine`). Knowledge base schemas, tool definitions, context builder patterns — all standardized. What varies is the content (services, pricing, persona). This is not a software house building bespoke systems; it is a platform delivery team deploying a standardized engine with configured content.

**Phase 2 (12–18 months): Platform + Managed Tier**

Once you have 8–10 implementations:
- Extract repeating patterns into a client-facing configuration layer (dashboard or structured onboarding form)
- Launch a self-serve tier for simple implementations (single location, standard services, no custom tooling)
- Retain managed tier for complex clients (multi-location, custom integrations, sensitive escalation flows)
- Begin transitioning from "we manage everything" to "we provide the platform + optional managed service addon"

Pricing splits:
- Self-serve tier: SGD 399–699/month (client configures knowledge base via dashboard)
- Managed tier: SGD 1,500–3,000/month (you configure + manage everything)
- Setup fee remains for managed tier; eliminated for self-serve

**Phase 3 (18–36 months): SaaS Platform**

- Self-serve onboarding is the primary acquisition channel
- Managed tier is the upsell / enterprise tier
- You are now a SaaS company with a managed service offering on top

---

## Part 3 — Integrated Recommendation

The two questions are now answerable together:

### Q1: How should you manage multi-client repos?

**Move to engine-as-package model.** This is the correct architecture regardless of whether you position as SaaS or AaaS, because:
- It enforces the separation between platform (engine) and deployment (client config) at the code level
- It makes the eventual self-serve product easier to build — the engine is already a standalone artifact
- It prevents client context from bleeding into agent decision-making as you scale

Do this now. The migration is one day of work and it future-proofs the architecture.

### Q2: SaaS or enterprise/software house?

**Managed AI Implementation Service for the next 12 months.** Not because SaaS is the wrong destination — it isn't — but because:
1. The product is not self-serve yet
2. The pricing math breaks below $1,500/month at current manual delivery costs
3. High-touch implementations generate the vertical data and learnings needed to build a real SaaS product
4. The revenue from 5–10 managed clients funds the self-serve product development

**The dangerous failure mode to avoid:** Selling at $79/month SaaS pricing while delivering $3,000 worth of implementation work per client. This is the current trajectory and it will exhaust you.

---

## Decision Gates

| Gate | Question | Action Required |
|------|----------|-----------------|
| 1 | Is the client with current issues migrating away? | If yes — use the migration as the catalyst to restructure repos. Do not re-onboard them onto the monorepo. |
| 2 | Is the founder willing to reprice existing clients? | Existing clients (hey-aircon, flow-ai) should be re-evaluated against managed service pricing. If they are underpriced, either renegotiate or accept them as reference clients and reprice from the next client forward. |
| 3 | Is there a target number of managed clients before building self-serve? | Recommend: 8 clients minimum. Enough to see repeating patterns, enough revenue to fund 3–6 months of platform development. |
| 4 | When does the next client join? | Next client should be onboarded at managed service pricing ($3,000–6,000 setup + $1,500–3,000/month). No exceptions. |

---

## What This Document Does Not Decide

- **Client contracts / repricing:** Founder decision. This document flags the pricing mismatch; it does not prescribe how to handle existing client relationships.
- **Whether to take VC funding:** AaaS revenue is "services revenue" and is discounted by investors. If fundraising is in the 18-month plan, the roadmap to self-serve SaaS becomes a prerequisite for a credible pitch.
- **Which vertical to focus on:** Service SMEs is a large category. Concentration in one vertical (aircon/home services, clinics, tutoring) accelerates the template library and vertical moat. This is a product-manager / business-strategist question.
- **Hiring:** The managed service model hits a wall at ~8–12 clients solo. Hiring or contracting becomes necessary at that point.

---

## Appendix: Current State Snapshot (2026-05-07)

| Dimension | Current Reality |
|-----------|----------------|
| Clients live | 2 (hey-aircon, flow-ai) |
| Repo model | Monorepo, per-client deploy branches |
| Pricing | SGD 79–699/month (SaaS framing) |
| Delivery model | Manual implementation and management |
| Self-serve capability | None |
| Engine package status | Embedded in monorepo, not extracted |
| Next logical step | Reprice, restructure repos, close next client at managed service rates |
