# Flow AI — Option C Migration Plan: Engine-as-Package

**Owner:** chief-of-staff  
**Date:** 2026-05-12  
**Status:** Approved — Founder approved Option C on 2026-05-12  
**Source decision:** `docs/architecture/multi_client_repo_and_positioning_eval.md`

---

## 1. Current State vs. Target State

| Dimension | Current State | Target State |
|-----------|--------------|-------------|
| **Repos** | 1 monorepo (`flow-ai`) containing engine + both clients | 3 repos: `flow-ai-engine`, `client-hey-aircon`, `client-flow-ai` |
| **Engine packaging** | `engine/` directory embedded in monorepo, not installable | `flow-ai-engine` published as a private Python package (GitHub Packages). Client repos `pip install` it. |
| **Client content** | `clients/hey-aircon/` and `clients/flow-ai/` in monorepo | Each client's content lives exclusively in its own repo |
| **Railway deployment** | Each Railway project tracks a `deploy/{client-id}` branch on the monorepo | Each Railway project tracks the `main` branch of its corresponding client repo (`client-hey-aircon`, `client-flow-ai`) |
| **CLAUDE.md / agent context** | Single `CLAUDE.md` at monorepo root carries context for both clients + engine | `flow-ai-engine` has an engine-scoped `CLAUDE.md`; each client repo has a client-scoped `CLAUDE.md` |
| **AGENTS.md / .flow/** | Monorepo root — covers all clients and engine | `flow-ai-engine` gets its own `AGENTS.md` + `.flow/`. Client repos get lightweight `AGENTS.md` pointing at engine docs for reference. |
| **Eval pipeline** | `engine/tests/eval/` — monolithic, no client/engine separation | Engine evals stay in `flow-ai-engine`. Client-specific evals (persona, knowledge base coverage) move to each client repo. |
| **CI/CD** | No CI confirmed in current monorepo | `flow-ai-engine`: publish package on git tag (GitHub Actions). Client repos: install engine, run client evals, deploy to Railway on push to `main`. |
| **Confidentiality** | No repo-level isolation — both clients visible from one checkout | Contractor for hey-aircon has access to only `client-hey-aircon`. Engine code is in a separate private repo. |
| **Versioning** | No versioning — `master` HEAD is shared state | Engine versioned as `v0.1.0`, `v0.2.0`, etc. Clients pin specific releases. |

---

## 2. Gap Analysis

### 2.1 Repository Restructuring

**What moves to `flow-ai-engine`:**
- `engine/core/` (all files: `agent_runner.py`, `context_builder.py`, `message_handler.py`, `reset_handler.py`, `tools/`)
- `engine/integrations/` (all files: `meta_whatsapp.py`, `supabase_client.py`, `google_calendar.py`, `google_sheets.py`)
- `engine/api/webhook.py`
- `engine/config/settings.py`
- `engine/tests/` (all engine-level tests and eval scaffolding, **except** client-specific YAML test cases)
- `supabase/migrations/` (shared schema migrations belong to the platform, not per-client)

**What stays in the current monorepo (becomes `flow-ai-engine` or is archived):**
- `docs/` — the architecture, requirements, test-plan docs are platform-level and follow the engine. They move to `flow-ai-engine/docs/`.
- `finance/invoice_generator.py` — platform tool, moves to `flow-ai-engine`.
- `Product/docs/` — platform PRDs and standards, moves to `flow-ai-engine/Product/docs/` or stays in a dedicated `platform-docs` directory inside the engine repo.
- `.flow/` — the agent orchestration system. Engine-level `.flow/` (platform task queue, onboarding guide for new engine clients) moves to `flow-ai-engine`. Client-specific task queues move to their respective client repos.

**What moves to `client-hey-aircon`:**
- `clients/hey-aircon/` — entire directory: `plans/`, `product/`, `website/`, `invoices/`, `reports/`, `context.md`
- `engine/tests/eval/test_cases/hey_aircon/` (if it exists) — client-specific YAML eval cases
- `CLAUDE.md` content scoped to hey-aircon only (see §2.4)
- A `requirements.txt` pinning `flow-ai-engine==0.1.0`
- A thin `Dockerfile` or `railway.toml` deployment config
- `supabase/` seed files specific to hey-aircon (if any — currently migrations are shared, but any hey-aircon-specific seed data)

**What moves to `client-flow-ai`:**
- `clients/flow-ai/` (if the directory exists in the monorepo — currently implied but verify)
- Same pattern as hey-aircon: `requirements.txt`, deployment config, client-scoped `CLAUDE.md`
- Any flow-ai-specific eval YAML test cases

**Unresolved/Decision Required:**
- `finance/invoice_generator.py` — belongs in `flow-ai-engine` (platform tool). Client invoice output directories (`clients/{id}/invoices/`) belong in client repos. The generator reads client parameters at runtime — no change needed to the code, only to where it lives.
- The current `AGENTS.md` at the monorepo root is owned by chief-of-staff. After migration, chief-of-staff maintains one `AGENTS.md` per repo (engine + each client).

---

### 2.2 Engine Packaging

**Gap:** `engine/` is currently a plain Python directory, not an installable package. There is no `pyproject.toml`, no `setup.py`, no version metadata.

**What needs to be created in `flow-ai-engine`:**

```
flow-ai-engine/
  pyproject.toml          ← package metadata, dependencies, version
  engine/
    __init__.py           ← marks engine as a package; exports version
    core/
    integrations/
    api/
    config/
  tests/
  docs/
  .github/
    workflows/
      publish.yml         ← GitHub Actions: publish to GitHub Packages on git tag
```

**`pyproject.toml` minimum requirements:**
- `[project]` section: `name = "flow-ai-engine"`, `version = "0.1.0"`, `requires-python = ">=3.11"`
- `[project.dependencies]`: pin all current `requirements.txt` dependencies (anthropic, fastapi, supabase, google-api-python-client, openai, pydantic-settings, etc.)
- `[build-system]`: use `hatchling` or `setuptools` as the build backend
- Optional: `[project.scripts]` entry point if there is a CLI

**GitHub Packages vs. PyPI private:**
- **Recommended for now: GitHub Packages.** Same GitHub org, no additional account, authentication via `GITHUB_TOKEN` or a PAT. Client repos install via `pip install flow-ai-engine --index-url https://pip.pkg.github.com/OWNER/`.
- **Alternative for local dev:** `pip install -e ../flow-ai-engine` — editable install from local path. This is the standard local dev workflow and requires no package registry during development.
- **Decision gate (§4.1):** Founder must decide: GitHub Packages now, or defer to a private PyPI (Gemfury, AWS CodeArtifact) at scale? GitHub Packages is the lowest-friction path for a 1–2 person team.

**Versioning strategy:**
- Start at `v0.1.0` (not `v1.0.0` — the engine is pre-1.0 until it reaches a stable public API).
- Semantic versioning: `MAJOR.MINOR.PATCH`
  - `PATCH` bump: bug fixes, no interface changes
  - `MINOR` bump: new tools, new integrations, backward-compatible additions
  - `MAJOR` bump: breaking changes to how client repos consume the engine (tool signatures, config schema changes)
- Git tag triggers publish: `git tag v0.1.0 && git push origin v0.1.0` → GitHub Actions publishes to GitHub Packages.

**Client repo consumption:**

In each client repo's `requirements.txt`:
```
flow-ai-engine==0.1.0
```

For local dev (when engine and client repo are checked out side by side):
```
# requirements-dev.txt
-e ../flow-ai-engine
```

---

### 2.3 Railway Deployment Changes

**Current model:**
- One Railway account
- `hey-aircon` Railway project → tracks `deploy/hey-aircon` branch on monorepo
- `flow-ai` Railway project → tracks `deploy/flow-ai` branch on monorepo
- 5 env vars per client, namespaced by client ID

**Target model:**
- One Railway account (same)
- `hey-aircon` Railway project → tracks `main` branch of `client-hey-aircon` GitHub repo
- `flow-ai` Railway project → tracks `main` branch of `client-flow-ai` GitHub repo
- `flow-ai-engine` does NOT have its own Railway project — it is a library, not a deployed service

**Railway config changes per client:**
1. In the Railway project settings, disconnect from the current GitHub repo (`flow-ai`).
2. Connect to the new client repo (`client-hey-aircon` or `client-flow-ai`).
3. Set the branch to `main`.
4. Verify the root directory is `/` (the client repo root, which will contain the `engine/` after `pip install`). The `railway.toml` or start command in the client repo must point to the FastAPI app entry point.
5. Env vars: **no changes needed.** The 5 env vars per client (`{CLIENT_ID_UPPER}_META_WHATSAPP_TOKEN`, etc.) stay in the same Railway project. They were always client-scoped — they just move with the client repo.

**Deploy branch deprecation:**
- `deploy/hey-aircon` and `deploy/flow-ai` branches on the monorepo become obsolete once each Railway project is re-pointed at its client repo.
- Do NOT delete these branches until Railway has successfully deployed from the client repo and the service is confirmed live. They are the rollback path during migration.
- After Railway cutover is confirmed: `git push origin --delete deploy/hey-aircon` and `git push origin --delete deploy/flow-ai`.

**New deployment workflow (post-migration):**
```
# For a client-specific change (e.g., hey-aircon knowledge base update):
cd client-hey-aircon/
git add . && git commit -m "update knowledge base"
git push origin main          # Railway auto-deploys hey-aircon project

# For an engine change affecting all clients:
cd flow-ai-engine/
git tag v0.1.1
git push origin v0.1.1        # GitHub Actions publishes new package version

# In each client repo, upgrade and deploy:
cd client-hey-aircon/
# Update requirements.txt: flow-ai-engine==0.1.1
git add requirements.txt && git commit -m "upgrade engine to v0.1.1"
git push origin main          # Railway deploys

cd client-flow-ai/
# Same steps
```

---

### 2.4 Agent Context and CLAUDE.md Changes

**Current problem:** The monorepo `CLAUDE.md` at `~/.claude/projects/.../CLAUDE.md` carries context about both clients, the engine architecture, and all hard rules. Every dev session for either client loads this entire context. At 5+ clients this will degrade agent decision quality.

**Target state:**

**`flow-ai-engine` repo — new `CLAUDE.md` (engine-scoped):**
- Tech stack section (FastAPI, Claude Haiku, Supabase, Railway — but no client-specific details)
- Python conventions section (all current conventions)
- Folder structure (engine-only structure)
- Hard rules relevant to engine development (no direct `@software-engineer` dispatch, no client logic in `engine/core/`, etc.)
- Eval pipeline section (engine-level evals only)
- Agent-to-file routing for engine files
- Bespoke vs. Core Framework section
- LLM strategy section
- All deployment rules that apply to the engine package

**`client-hey-aircon` repo — new `CLAUDE.md` (hey-aircon scoped):**
- What this client is (business context, pilot client status)
- Tech stack: "Engine: `flow-ai-engine` package (see engine repo for internals)"
- Folder structure of the client repo
- Client-specific hard rules (n8n preservation rule, Google Calendar write rules for this client)
- Current blockers specific to hey-aircon
- Agent-to-file routing for hey-aircon files
- HeyAircon billing details (for finance agent)
- n8n migration status (until decommission is confirmed)

**`client-flow-ai` repo — new `CLAUDE.md` (flow-ai client scoped):**
- Same pattern, content scoped to the flow-ai client

**What sections move where:**

| Current CLAUDE.md Section | Destination |
|--------------------------|------------|
| What this project is | `flow-ai-engine` CLAUDE.md |
| Tech Stack table | `flow-ai-engine` CLAUDE.md |
| LLM Strategy | `flow-ai-engine` CLAUDE.md |
| Key Design Principles (context engineering, multi-client isolation, escalation gate, calendar write rules) | `flow-ai-engine` CLAUDE.md (platform principles); each client CLAUDE.md references engine CLAUDE.md |
| Folder Structure | Split: engine structure → engine CLAUDE.md; client structure → client CLAUDE.md |
| Agent-to-File Routing | Split by file ownership |
| Python Conventions | `flow-ai-engine` CLAUDE.md |
| Bespoke vs. Core Feature Framework | `flow-ai-engine` CLAUDE.md |
| Hard Rules | Split: engine-level rules → engine CLAUDE.md; client-specific rules → client CLAUDE.md |
| Railway Deployment Model | `flow-ai-engine` CLAUDE.md (model description); each client CLAUDE.md (their specific project/branch) |
| Current Blockers | Each client CLAUDE.md only |
| n8n migration status | `client-hey-aircon` CLAUDE.md only |

**AGENTS.md and `.flow/` split:**

| Artifact | Current Location | Destination |
|---------|-----------------|------------|
| `AGENTS.md` | Monorepo root | Replicated in each repo: engine-scoped in `flow-ai-engine`, client-scoped in each client repo |
| `.flow/onboarding.md` | Monorepo root | `flow-ai-engine/.flow/onboarding.md` (platform onboarding template) |
| `.flow/config.yaml` | Monorepo root | Split: engine-level config → engine repo; per-client config → each client repo |
| `.flow/templates/` | Monorepo root | `flow-ai-engine/.flow/templates/` (generic templates); client-specific extensions in client repos |
| `.flow/tasks/active.md` | Monorepo root | Each repo maintains its own `.flow/tasks/` — engine tasks in engine repo, client tasks in client repo |

---

### 2.5 Eval Pipeline Changes

**Current state:** `engine/tests/eval/` exists with some scaffolding. The eval pipeline is designed to test both engine behavior and client-specific behaviors in one runner.

**Target state:**

**Engine evals (stay in `flow-ai-engine/tests/eval/`):**
- Intent classification accuracy (engine-level behavior)
- Tool use accuracy (does the agent call the right tool with the right parameters)
- LLM fallback logic (does Anthropic → OpenAI fallback trigger correctly)
- Escalation gate behavior (hard programmatic check — engine responsibility)
- Safety guardrail enforcement (engine-level)
- `thresholds.yaml`: retains engine-level thresholds only (intent accuracy, tool use accuracy, fallback success rate)

**Client evals (move to each client repo's `tests/eval/`):**
- Persona accuracy (does the agent respond in hey-aircon's brand voice?)
- Knowledge base coverage (are services, pricing, operating hours answered correctly?)
- Booking flow accuracy for this client's specific service catalog
- Client-specific YAML test case files (currently in `engine/tests/eval/test_cases/` subdirectory)
- Client-specific `thresholds.yaml` (persona score threshold, KB coverage threshold)

**Eval runner change:**
- The `EvalRunner` class stays in the engine package (it is the platform tool).
- Client repos import `EvalRunner` from the engine package and pass their own test case directory and thresholds file.
- This means `EvalRunner` must accept `test_cases_dir` and `thresholds_file` as constructor parameters, not hardcoded paths. **This is a minor engine change required before migration.** Flag as a pre-migration task.

---

### 2.6 CI/CD and GitHub Actions

**Current state:** No CI confirmed in the monorepo.

**`flow-ai-engine` CI (to be created):**

`.github/workflows/publish.yml`:
- Trigger: `on: push: tags: ['v*']`
- Steps: checkout, set up Python 3.11, `pip install build`, `python -m build`, publish to GitHub Packages via `GITHUB_TOKEN`
- On every push to `main` (non-tag): run test suite (`pytest engine/tests/` excluding eval tests that need live API keys)

`.github/workflows/test.yml`:
- Trigger: `on: push: branches: ['main', 'feature/**']` and `on: pull_request`
- Steps: checkout, install dependencies, run `pytest engine/tests/unit/` (unit tests only — no live credentials needed in CI)

**Per-client repo CI (to be created in each client repo):**

`.github/workflows/deploy.yml`:
- Trigger: `on: push: branches: ['main']`
- Steps: checkout, install dependencies (`pip install -r requirements.txt` — pulls engine from GitHub Packages), run client evals (`pytest tests/eval/` with client Supabase test credentials), Railway deploy (Railway CLI or Railway's built-in GitHub integration)
- Note: if Railway's GitHub integration is used (connect Railway project to GitHub repo), Railway auto-deploys on push and CI can be limited to testing only.

**Decision gate (§4.2):** Does the founder want CI to gate Railway deploys, or is Railway's native GitHub integration sufficient? For 2 clients, Railway's built-in integration (push to `main` → auto-deploy) is probably enough. CI testing gates are more important for the engine package.

---

## 3. Ordered Migration Steps

### Phase 0: Pre-migration prerequisites (no downtime, monorepo stays live)

| Step | Action | Owner | Notes |
|------|--------|-------|-------|
| 0.1 | Confirm `clients/flow-ai/` directory exists in monorepo and identify what it contains. If it does not exist, document what the flow-ai client's content is. | Founder | Verify before creating `client-flow-ai` repo |
| 0.2 | Modify `EvalRunner` in `engine/tests/eval/` to accept `test_cases_dir` and `thresholds_file` as constructor parameters instead of hardcoded paths. This is a backwards-compatible change. | `@sdet-engineer` (dispatches `@software-engineer`) | Required for client repos to use the eval runner |
| 0.3 | Audit `engine/tests/eval/test_cases/` — identify which YAML files are engine-level (intent, escalation, safety) vs. client-specific (booking flows, persona, KB). Document the split. | `@sdet-engineer` | Needed to know what moves where in Phase 1 |
| 0.4 | Confirm Google Calendar blocker status. The calendar integration is listed as "working" in the status log but was previously blocked. Confirm it is fully operational before migrating hey-aircon — a migration during an active blocker adds unnecessary risk. | Founder | If blocker is re-open, note it but do not let it block migration |
| 0.5 | Confirm n8n decommission status. n8n docs must stay accessible in `clients/hey-aircon/plans/build/` until all 5 migration gates are passed. Client repo structure must preserve this directory. | Founder | Copy `plans/build/` into `client-hey-aircon` repo — do not archive it |

---

### Phase 1: Create `flow-ai-engine` repo and package (no client downtime)

| Step | Action | Owner | Notes |
|------|--------|-------|-------|
| 1.1 | Create new private GitHub repo: `flow-ai-engine` under the same GitHub account/org | Founder | Must be private. Do not make it public. |
| 1.2 | Copy all `engine/` contents from monorepo into `flow-ai-engine/engine/`. Add `engine/__init__.py` with `__version__ = "0.1.0"`. | `@sdet-engineer` (dispatches `@software-engineer`) | Use copy, not move — monorepo stays intact until Phase 3 |
| 1.3 | Create `pyproject.toml` in `flow-ai-engine/` root. Define package name, version `0.1.0`, Python version requirement, and all current dependencies extracted from `engine/requirements.txt` (or the monorepo root `requirements.txt`). | `@software-architect` → `@sdet-engineer` | `@software-architect` defines the manifest; `@sdet-engineer` implements |
| 1.4 | Copy `engine/tests/` into `flow-ai-engine/tests/`. Remove client-specific YAML test cases (identified in Step 0.3) — those will go to client repos. Verify all engine-level tests pass inside `flow-ai-engine/` with `pip install -e .` and `pytest tests/`. | `@sdet-engineer` | Milestone: engine installs and tests pass in isolation |
| 1.5 | Copy `docs/` directory into `flow-ai-engine/docs/`. Copy `Product/docs/` into `flow-ai-engine/Product/docs/`. Copy `.flow/` (platform-level portions) into `flow-ai-engine/.flow/`. Copy `finance/invoice_generator.py` to `flow-ai-engine/finance/`. | `@sdet-engineer` | Docs are the agent handoff medium — they travel with the engine |
| 1.6 | Create engine-scoped `CLAUDE.md` in `flow-ai-engine/` root. Extract the engine-relevant sections from the current monorepo `CLAUDE.md` (per §2.4). | `@sdet-engineer` owns file creation; chief-of-staff provides the section split spec | Do NOT copy-paste the entire CLAUDE.md — scope it to engine only |
| 1.7 | Create engine-scoped `AGENTS.md` in `flow-ai-engine/` root. | chief-of-staff | Own file — edit directly |
| 1.8 | Create `.github/workflows/publish.yml` in `flow-ai-engine/` — publishes package to GitHub Packages on `v*` tag. Create `.github/workflows/test.yml` — runs unit tests on push. | `@sdet-engineer` | Milestone: `git tag v0.1.0 && git push origin v0.1.0` publishes the package |
| 1.9 | Tag `v0.1.0` and push. Confirm GitHub Packages shows `flow-ai-engine` version `0.1.0` available for install. | Founder (tags the release) + `@sdet-engineer` (verifies) | Milestone: package is installable |
| 1.10 | Update `flow-ai-engine/docs/architecture/code_map.md` to reflect that the engine is now a standalone package. | `@software-architect` | Hard rule: code_map.md must be updated after any structural change |

---

### Phase 2: Create `client-flow-ai` repo and migrate (lower-risk client first)

Flow-ai is identified as lower risk than hey-aircon. Migrate it first to validate the process.

| Step | Action | Owner | Notes |
|------|--------|-------|-------|
| 2.1 | Create new private GitHub repo: `client-flow-ai` | Founder | Private repo |
| 2.2 | Copy `clients/flow-ai/` (or equivalent content) into `client-flow-ai/`. Structure the repo as: `clients/flow-ai/` (content), `requirements.txt` (pinning `flow-ai-engine==0.1.0`), `requirements-dev.txt` (with `-e ../flow-ai-engine`), `railway.toml` or `Dockerfile`. | `@sdet-engineer` | This is the complete client repo — thin by design |
| 2.3 | Add `pyproject.toml`-based GitHub Packages authentication config so `pip install` can resolve `flow-ai-engine` from GitHub Packages. This typically means a `.pip.conf` or `pip.ini` in the repo root, or a `requirements.txt` index URL. | `@sdet-engineer` | Decision gate: if using `pip install -e` for now instead of GitHub Packages, this step is simpler |
| 2.4 | Move flow-ai client-specific YAML eval test cases (identified in Step 0.3) into `client-flow-ai/tests/eval/`. Create a client `thresholds.yaml`. | `@sdet-engineer` | |
| 2.5 | Create client-scoped `CLAUDE.md` in `client-flow-ai/` root (per §2.4). | `@sdet-engineer` owns file; chief-of-staff provides section split spec | |
| 2.6 | Create client-scoped `AGENTS.md` in `client-flow-ai/` root. | chief-of-staff | Own file — edit directly |
| 2.7 | In Railway: disconnect the `flow-ai` project from `deploy/flow-ai` branch on the monorepo. Connect it to `client-flow-ai` GitHub repo, `main` branch. | Founder (Railway console action) | **This is the cutover step — brief deploy interruption possible. Schedule during low-traffic window.** |
| 2.8 | Confirm Railway deploys `client-flow-ai` successfully. Verify the FastAPI webhook is live and responding. Test with a real or synthetic WhatsApp message. | Founder + `@sdet-engineer` | Milestone: flow-ai client is live from its own repo |
| 2.9 | After confirmed live: deprecate `deploy/flow-ai` branch on the monorepo. Do NOT delete yet — keep for 48 hours as rollback. | `@sdet-engineer` | Delete after 48h if no rollback needed: `git push origin --delete deploy/flow-ai` |

---

### Phase 3: Create `client-hey-aircon` repo and migrate (production client — more caution)

| Step | Action | Owner | Notes |
|------|--------|-------|-------|
| 3.1 | Create new private GitHub repo: `client-hey-aircon` | Founder | Private repo |
| 3.2 | Copy full `clients/hey-aircon/` directory into `client-hey-aircon/`. This includes `plans/build/` (n8n docs — preserved per migration gating rule). Create `requirements.txt`, `requirements-dev.txt`, `railway.toml`. | `@sdet-engineer` | n8n docs must be present — do not skip `plans/build/` |
| 3.3 | Copy hey-aircon client-specific eval YAML test cases into `client-hey-aircon/tests/eval/`. Create client `thresholds.yaml`. | `@sdet-engineer` | |
| 3.4 | Create client-scoped `CLAUDE.md` in `client-hey-aircon/` root. Include n8n migration status section, n8n preservation rule, Google Calendar write rules, and HeyAircon billing details. | `@sdet-engineer` owns file; chief-of-staff provides section split spec | |
| 3.5 | Create client-scoped `AGENTS.md` in `client-hey-aircon/` root. | chief-of-staff | Own file — edit directly |
| 3.6 | Run full eval suite inside `client-hey-aircon/` (`pytest tests/eval/` against a staging Supabase or test credentials). Confirm passing before Railway cutover. | `@sdet-engineer` | Do not cut over Railway until evals pass |
| 3.7 | In Railway: disconnect the `hey-aircon` project from `deploy/hey-aircon` branch on the monorepo. Connect it to `client-hey-aircon` GitHub repo, `main` branch. | Founder (Railway console action) | **Production traffic — schedule during lowest-traffic window. Coordinate with HeyAircon if needed.** |
| 3.8 | Confirm Railway deploys `client-hey-aircon` successfully. Verify Meta webhook is live. Send a test WhatsApp message and confirm end-to-end flow: inbound → escalation gate → Claude Haiku → reply. | Founder + `@sdet-engineer` | Milestone: hey-aircon is live from its own repo |
| 3.9 | After 48h confirmed live: deprecate and delete `deploy/hey-aircon` branch on the monorepo. | `@sdet-engineer` | `git push origin --delete deploy/hey-aircon` |

---

### Phase 4: Monorepo cleanup and archival

| Step | Action | Owner | Notes |
|------|--------|-------|-------|
| 4.1 | Add `engine/` to `.gitignore` in the monorepo root (or remove the `engine/` directory entirely after confirming both client repos and the engine repo are live). | `@sdet-engineer` | The monorepo can be archived or repurposed as a holding repo for shared platform planning docs |
| 4.2 | Update monorepo `CLAUDE.md` to document the new architecture: "This monorepo is now archived. Active development happens in `flow-ai-engine`, `client-hey-aircon`, and `client-flow-ai`." | Founder or chief-of-staff (only CLAUDE.md at root is in scope) | |
| 4.3 | Update project `AGENTS.md` in the monorepo to reflect the archive state and point to the three active repos. | chief-of-staff | Own file — edit directly |
| 4.4 | Update `docs/status_log.md` with migration completion. | chief-of-staff | Own file — edit directly |

---

## 4. Decision Gates

### Gate 1 (Before Phase 1 begins): Package registry choice

**Question:** Where does `flow-ai-engine` get published as a private package?

| Option | Pros | Cons | When to choose |
|--------|------|------|---------------|
| **GitHub Packages** (recommended now) | Same GitHub account, `GITHUB_TOKEN` auth, no extra accounts | Requires PAT or Actions token for install in CI; slightly less ergonomic than public PyPI | Choose this now — lowest friction for 2-person team |
| **`pip install -e`** (local dev only, defer registry) | Zero setup, works immediately | Only works when repos are co-located on same machine; breaks Railway CI unless you copy engine code | Viable for local dev but NOT for Railway deployment |
| **Private PyPI** (Gemfury, AWS CodeArtifact) | More standard, better tooling | Extra account, extra cost, more setup | Revisit at 10+ clients |

**Founder must decide:** GitHub Packages or defer? If deferring, Phase 1 must include a step that copies the engine package into client repos at deploy time (e.g., a `Makefile` target or a CI step that copies `engine/` before installing). This is messier but works.

**Recommendation:** Use GitHub Packages. It is the lowest-friction option and avoids the copy-at-deploy antipattern.

---

### Gate 2 (Before Phase 2 begins): CI/CD depth for client repos

**Question:** Do client repos need full CI gates (test → deploy) or is Railway's built-in GitHub integration (push → auto-deploy) sufficient for now?

- At 2 clients with a solo founder, Railway's native integration is probably sufficient.
- Full CI gates (run evals before deploy) add safety but also add setup time and credential management in GitHub Actions secrets.

**Recommendation:** Start with Railway's native GitHub integration. Add CI gates when the eval suite is mature enough to be meaningful (i.e., when YAML test cases are fully populated).

---

### Gate 3 (Before Phase 3 begins): hey-aircon notification

**Question:** Does HeyAircon need to be notified of the Railway cutover in Phase 3?

- The cutover is brief (Railway redeploys typically take 1–3 minutes).
- The Meta webhook URL does not change — it is a Railway URL tied to the project, not the branch.
- **Recommendation:** No client notification needed. Schedule the cutover during off-hours (e.g., 2–4 AM Singapore time) when WhatsApp traffic is minimal. Monitor for 15 minutes post-deploy.

---

### Gate 4 (After Phase 4): Monorepo fate

**Question:** Should the monorepo (`flow-ai`) be archived, deleted, or repurposed?

- **Archive** (recommended): Mark as archived in GitHub (Settings → Archive). It remains accessible for reference but no new commits can be pushed. The `clients/hey-aircon/plans/build/` n8n docs are preserved here as a secondary copy.
- **Keep live as platform planning repo**: If platform-level planning docs (`Product/docs/`, `docs/planning/`) need a home that is not tied to the engine package, keep the monorepo alive but remove `engine/` and `clients/`. Rename to `flow-ai-platform-docs` or similar.
- **Delete**: Only after confirming all content is preserved in the three new repos. Not recommended — historical commits may be valuable.

---

## 5. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **Railway cutover gap** — brief downtime during Phase 2/3 Railway re-pointing | Medium | Medium (WhatsApp messages missed during deploy) | Schedule during off-hours. Keep old `deploy/{client-id}` branch live as rollback for 48h post-cutover. |
| **Engine package auth breaks Railway CI** — GitHub Packages auth not configured correctly in client repo, Railway build fails | Medium | High (client goes down) | Test the `pip install` from GitHub Packages in a clean environment BEFORE cutting over Railway. Use a test deploy on a throwaway Railway service. |
| **Missing env vars in client repo Railway project** — env vars are present but their names or structure differ from what the engine `settings.py` expects after restructuring | Low | High | Audit `engine/config/settings.py` before Phase 1. Document every env var the engine reads. Confirm all 5 per-client vars are present in the Railway project before cutover. |
| **hey-aircon n8n docs lost** — `clients/hey-aircon/plans/build/` not copied into `client-hey-aircon` repo | Low | High (migration gating rule violated) | Explicit checklist item in Step 3.2. SDET verifies directory presence before committing. |
| **Eval test cases mis-classified** — engine-level test cases accidentally moved to client repos, or vice versa | Medium | Low-Medium (evals pass but don't test what they should) | Step 0.3 audit is the mitigation. Do not skip it. |
| **`EvalRunner` hardcoded paths break client repos** — if Step 0.2 is skipped and `EvalRunner` has hardcoded paths to `engine/tests/eval/`, client eval imports will fail | Medium | Medium (evals don't run in client repos) | Step 0.2 is a blocking prerequisite for Phases 2 and 3. |
| **Context drift between repos** — engine CLAUDE.md and client CLAUDE.md become out of sync; agents make decisions based on stale context | Medium (will happen over time) | Medium | Each repo's CLAUDE.md is maintained by its owning sessions. Cross-repo changes (e.g., engine API change) require a corresponding CLAUDE.md update in affected client repos. Flag as an ongoing maintenance pattern, not a one-time fix. |
| **Google Calendar blocker re-opens during migration** | Low | Low-Medium (operational disruption, not migration-blocking) | Migration is independent of the Calendar blocker. Proceed with migration. If Calendar breaks during migration window, the blocker is a separate incident. |
| **n8n decommission not yet approved during migration** | Certain (it hasn't been approved yet) | Low (n8n docs are preserved — this is just a documentation concern) | n8n docs travel with `client-hey-aircon` repo. Migration does not require n8n decommission to be approved. These are independent tracks. |

---

## 6. Rollback Plan

**If Phase 2 (flow-ai client cutover) fails:**
1. In Railway: disconnect `client-flow-ai` repo, reconnect to monorepo `deploy/flow-ai` branch.
2. Push `master` to `deploy/flow-ai` to restore the latest code: `git push origin master:deploy/flow-ai`.
3. Confirm Railway deploys from the restored branch.
4. Diagnose failure in `client-flow-ai` without production pressure.

**If Phase 3 (hey-aircon cutover) fails:**
1. Same pattern: reconnect Railway hey-aircon project to `deploy/hey-aircon` branch on monorepo.
2. `git push origin master:deploy/hey-aircon`.
3. Confirm HeyAircon traffic is flowing again.
4. Diagnose. Do not re-attempt cutover until root cause is identified and fixed.

**Rollback window:** Keep `deploy/hey-aircon` and `deploy/flow-ai` branches live on the monorepo until each client has been confirmed stable on their new repo for 48 hours minimum. Do not delete the deploy branches early.

---

## 7. Migration Sequencing — Active Blockers

The following active blockers from CLAUDE.md are open during this migration planning. Their relationship to migration:

| Blocker | Relationship to Migration | Action |
|---------|--------------------------|--------|
| Google Calendar service account 404 | Independent — calendar is an engine integration, not a migration blocker. Calendar fix applies to `engine/google_calendar.py`, which moves to `flow-ai-engine` unchanged. | Proceed with migration independently. Calendar fix ships as a patch to the engine package. |
| n8n Component E (escalate-to-human) not yet built | Independent — n8n Component E is tracked separately. Migration copies n8n docs into `client-hey-aircon` repo and preserves all 5 decommission gates. | Proceed with migration. n8n decommission is a separate track. |
| n8n 48h verification + decommission pending | Independent — decommission approval is not required for the repo migration. | Proceed with migration. n8n decommission completes separately on its own track. |

**Conclusion:** None of the current active blockers block this migration. Migration can begin immediately after Gate 1 is decided.

---

## 8. Eval Case Audit (Step 0.3)

**Audited:** `engine/tests/eval/cases/` — 7 YAML files across 2 subdirectories.

### `platform/` — 4 files (engine-level behaviors)

| File | Cases | Classification | Notes |
|------|-------|---------------|-------|
| `intent.yaml` | 9 | Correct | All `client_id: "platform"`. Covers greeting, booking_request, pricing_inquiry, service_inquiry, reschedule_request, cancellation_request, complaint, out_of_scope, ambiguous booking. Generic message inputs with no HeyAircon-specific content. |
| `escalation_gate.yaml` | 8 | Correct | All `client_id: "platform"`. Covers: complaint keyword, refund request, human handoff request, anger/distress, danger signal, unconfirmable commitment, repeat out-of-scope. Negative case (normal reschedule) is also present. |
| `safety.yaml` | 10 | Correct | All `client_id: "platform"`. Covers: identity disclosure, impersonation, PAN data leak, cross-customer data, physical harm advice, legal advice, prompt injection, jailbreak. No client-specific content. |
| `tools.yaml` | 7 | Correct | All `client_id: "platform"`. Covers: calendar check, FAQ no-tool, booking ordering rule (calendar before write), no booking without required fields, escalate params, get_bookings before reschedule, no calendar for pricing. |

**Verdict:** All 4 platform files are correctly classified. Every case uses `client_id: "platform"` and tests engine behaviors that must hold across all clients regardless of industry or service catalog.

---

### `hey-aircon/` — 3 files (client-specific behaviors)

| File | Cases | Classification | Notes |
|------|-------|---------------|-------|
| `booking_flow.yaml` | 11 | Correct | All `client_id: "hey-aircon"`. Tests HeyAircon-specific service names ("General Servicing", "Chemical Wash", "Chemical Overhaul", "Gas Top Up"), booking ID format (`HA-`), minimum booking notice policy (`MIN_BOOKING_NOTICE_DAYS=2`), Singapore address formats, and unit count validation. Cannot be generalized to other clients. |
| `faq.yaml` | 11 | Correct | All `client_id: "hey-aircon"`. Tests HeyAircon-specific service catalog (5 named services), operating hours (Mon–Sat), service area (Singapore coverage), and knowledge base content (gas top-up symptoms, chemical wash explanation). Response content assertions are HeyAircon-config-dependent. |
| `rescheduling.yaml` | 9 | Correct | All `client_id: "hey-aircon"`. Tests booking lookup by phone, booking ID (`HA-` format), multi-booking disambiguation, same-day cancellation urgency, reschedule fee policy (read from Supabase policies table). Escalation to human pattern is platform-level but test cases use HeyAircon booking IDs and service names as fixtures. |

**Verdict:** All 3 hey-aircon files are correctly classified. They depend on HeyAircon's service catalog, booking ID format, pricing policy, and knowledge base content — none of which would apply unchanged to another client.

---

### Flags and Observations

**One boundary case worth noting:** `rescheduling.yaml` contains a mix of concerns. The escalation-on-reschedule rule itself ("Phase 1: agent cannot modify bookings — always escalate") is a platform-level policy (`engine/core/` enforces it for all clients). However, the test cases in this file use HeyAircon-specific booking IDs (`HA-`), service names, and address fixtures — so the file correctly belongs in `hey-aircon/`. When other client repos are created, they should author their own `rescheduling.yaml` using their own booking ID format and service names. The platform-level escalation rule is already validated generically in `platform/escalation_gate.yaml` (test: `reschedule_cancellation_request_escalate` equivalent) and `platform/tools.yaml` (test: `tool_get_bookings_before_reschedule`).

**One potential gap:** Neither `platform/` nor `hey-aircon/` contains a test case for the **LLM fallback logic** (Anthropic → OpenAI-mini). The migration plan (§2.5) lists "LLM fallback logic" as an engine eval. This should be added to `platform/` as a new `fallback.yaml` file before Phase 1 is complete. Not a mis-classification — a gap.

**No mis-classifications found.** No files need to move. The split is ready to support Phase 1 migration as-is.
