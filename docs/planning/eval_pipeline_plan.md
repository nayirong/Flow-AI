# Evaluation Pipeline Plan — Flow AI

> Owned by: chief-of-staff
> Created: 2026-04-16
> Status: Approved — dispatching Phase 1

---

## Direction Frame

**Subject:** Automated quality evaluation pipeline for the Flow AI WhatsApp agent across all client deployments (pilot: HeyAircon; scaling to multi-client platform).

**Desired Outcome:** Continuous, pre-production confidence that agent behaviors (intent classification, tool calls, escalation gate, safety guardrails, persona consistency) are correct on every code or config change. Systematic regression detection and a structured feedback loop to iteratively improve quality over time.

**Threat:** Without automated evaluation:
- Prompt refinements or LLM version updates silently degrade quality with no visibility until customers complain.
- Tool call errors (wrong calendar slots, incorrect booking data) reach production undetected.
- Safety violations (impersonation, data leaks, out-of-scope advice) slip through.
- Context engineering changes break client-specific behaviors.
- Multi-client rollouts amplify single-point failures — one bad prompt affects all clients simultaneously.
- New client onboarding has no quality gate — agents go live without baseline validation.

---

## Core Architecture Decision: 1 Shared Pipeline Serving All Clients

**Rationale:**

1. **Client isolation is config, not code.** The Python engine is client-agnostic. All client-specific behavior loads at runtime via `client_id`. Test cases carry a `client_id` field to load the right context.
2. **Platform behaviors are shared.** Intent classification, tool selection, safety guardrails, and escalation gate logic are platform-level. Testing them once validates all clients.
3. **Client-specific test cases are data, not infrastructure.** HeyAircon scenarios are rows in `eval_test_cases` with `client_id = 'hey-aircon'`, not a separate pipeline.
4. **Operational simplicity.** One pipeline = one dashboard, one feedback loop, one place to debug.
5. **Scales cleanly.** Adding a new client = adding rows to `eval_test_cases` + client config. No infrastructure duplication.

---

## Pipeline Architecture

```
TRIGGER
  • GitHub Actions — on PR to engine/, Product/docs/, or clients/*/product/
  • Scheduled — daily production monitoring (2 AM SGT)
  • Manual CLI — debugging, client onboarding baseline
        ↓
LOAD TEST CASES
  • Supabase eval_test_cases table (client-contributed, prod-mined edge cases)
  • YAML files in Git: engine/tests/eval/cases/ (platform core behaviors)
  • Filter by: client_id, category, tags, enabled
        ↓
EXECUTE AGENT (per test case)
  1. Load ClientConfig for test_case.client_id
  2. Build context (config + policies from client Supabase)
  3. Run agent with test_case.input_message
  4. Capture: response text, tool calls, tool params, escalation flag, trace metadata
  5. Log trace to Langfuse (when integrated)
        ↓
SCORE OUTPUT (multi-dimensional)
  • IntentScorer     — expected_intent == classified_intent?
  • ToolScorer       — expected_tool + params match? (partial credit for correct tool, wrong params)
  • EscalationScorer — escalation fired correctly?
  • SafetyScorer     — regex + rule checks for violations
  • ResponseScorer   — expected phrases present/absent?
  • PersonaScorer    — LLM-as-judge for tone (Langfuse, Phase 2)
  Each scorer returns: passed (bool), score (0.0–1.0), failure_reason (str)
        ↓
LOG RESULTS
  • Write to Supabase eval_results table
  • Link to Langfuse trace_id (when integrated)
  • Tag with: run_id, git_commit, branch, LLM model + version
        ↓
AGGREGATE & REPORT
  • Overall pass rate, per-dimension scores, per-client breakdown
  • Trend comparison vs previous run and vs main branch
  • HTML report (GitHub Actions artifact)
  • PR comment summary with key metrics and trend delta
        ↓
GATE & ALERT
  • CI: Block PR merge if thresholds violated (see below)
  • Scheduled: Telegram bot alert if scores drop >5% or safety fails
  • User can override with justification (logged in merge commit metadata)
```

---

## Pass/Fail Thresholds

| Dimension | Threshold | Rationale |
|-----------|-----------|-----------|
| Safety | 100% | Zero tolerance |
| Critical tests (booking flow, escalation) | 95% | Core user journey |
| Overall pass rate | 85% | Matches PRD-02 intent accuracy target |
| Tool correctness (critical) | 95% | Wrong bookings are production incidents |
| Escalation correctness | 90% | High-stakes human handoff |
| Intent classification | 85% | Matches PRD AC-A-03 |

---

## Alerting: Telegram Bot

Alerts are routed to a Telegram bot for operational visibility without depending on Slack.

**Alert triggers:**
- Scheduled monitoring: any dimension drops >5% vs 7-day average
- Safety test fails in any run
- Baseline regression detected for a client
- Critical test failure in CI (informational — gate is in GitHub)

**Alert payload:**
```
Flow AI Eval Alert

Environment: production
Client: hey-aircon
Run: 2026-04-16T02:00Z
Regression: tool_use dropped from 0.94 → 0.86
Safety: pass
Critical failures:
  - booking_happy_path_am_slot
  - reschedule_policy_same_day

Report: <github actions url>
Trace: <langfuse url>
```

**Implementation:**
- `engine/tests/eval/alerts/base.py` — `BaseNotifier` abstract class
- `engine/tests/eval/alerts/telegram_notifier.py` — Telegram implementation
- Future-proof: `SlackNotifier`, `EmailNotifier` can be added without touching eval core
- Config: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `TELEGRAM_THREAD_ID` (for topic routing)
- All alert events also written to `eval_alerts` log in Supabase for auditability

**Control principle:** Telegram sends alerts only. No auto-remediation. All intervention happens through GitHub, CLI, or Supabase.

---

## Test Case Storage: Hybrid Approach

| Source | Contents | Why |
|--------|----------|-----|
| YAML in Git (`engine/tests/eval/cases/`) | Platform-level core behaviors (safety, escalation gate, tool definitions, intent) | Version-controlled; diffs visible in PRs; immutable reference tests |
| Supabase `eval_test_cases` table | Client-specific scenarios, prod-mined edge cases, regression tests from escalations | Easy to add without Git; client can contribute via Supabase Studio; queryable |

**Directory structure:**
```
engine/tests/eval/cases/
├── platform/
│   ├── safety.yaml
│   ├── escalation_gate.yaml
│   ├── tools.yaml
│   └── intent.yaml
└── hey-aircon/
    ├── booking_flow.yaml
    ├── faq.yaml
    └── rescheduling.yaml
```

---

## Supabase Schema

### eval_test_cases

```sql
CREATE TABLE eval_test_cases (
  id SERIAL PRIMARY KEY,
  client_id TEXT NOT NULL,
  category TEXT NOT NULL,  -- intent | tool_use | escalation | safety | persona | multi_turn | context_engineering
  test_name TEXT UNIQUE NOT NULL,
  input_message TEXT NOT NULL,
  conversation_history JSONB DEFAULT '[]'::jsonb,
  expected_intent TEXT,
  expected_tool TEXT,
  expected_tool_params JSONB,
  expected_escalation BOOLEAN,
  expected_response_contains TEXT[],
  expected_response_excludes TEXT[],
  safety_check TEXT,
  priority TEXT DEFAULT 'medium',  -- critical | high | medium | low
  reference_test BOOLEAN DEFAULT FALSE,
  tags TEXT[],
  enabled BOOLEAN DEFAULT TRUE,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### eval_results

```sql
CREATE TABLE eval_results (
  id SERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  test_case_id INT REFERENCES eval_test_cases(id),
  client_id TEXT NOT NULL,
  category TEXT NOT NULL,
  test_name TEXT NOT NULL,
  passed BOOLEAN NOT NULL,
  score FLOAT CHECK (score >= 0.0 AND score <= 1.0),
  agent_response TEXT,
  tool_called TEXT,
  tool_params JSONB,
  escalation_triggered BOOLEAN,
  scorer_results JSONB,
  failure_reason TEXT,
  langfuse_trace_id TEXT,
  execution_time_ms INT,
  run_metadata JSONB,  -- { git_commit, branch, llm_model, llm_version, prompt_version }
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### eval_alerts

```sql
CREATE TABLE eval_alerts (
  id SERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  alert_type TEXT NOT NULL,  -- regression | safety_failure | critical_failure | baseline_regression
  client_id TEXT,
  dimension TEXT,
  score_before FLOAT,
  score_after FLOAT,
  message TEXT,
  telegram_sent BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Python Framework Structure

```
engine/tests/eval/
├── __init__.py
├── run_eval.py              # CLI entry point
├── runner.py                # EvalRunner class
├── loader.py                # Loads test cases from YAML + Supabase
├── executor.py              # Executes agent for a single test case
├── alerts/
│   ├── __init__.py
│   ├── base.py              # BaseNotifier abstract class
│   └── telegram_notifier.py # Telegram bot implementation
├── scorers/
│   ├── __init__.py
│   ├── base.py              # BaseScorer abstract class
│   ├── intent_scorer.py
│   ├── tool_scorer.py
│   ├── escalation_scorer.py
│   ├── safety_scorer.py
│   ├── response_scorer.py
│   └── persona_scorer.py   # LLM-as-judge (Langfuse, Phase 2)
├── cases/                   # Version-controlled YAML test cases
│   ├── platform/
│   │   ├── safety.yaml
│   │   ├── escalation_gate.yaml
│   │   ├── tools.yaml
│   │   └── intent.yaml
│   └── hey-aircon/
│       ├── booking_flow.yaml
│       ├── faq.yaml
│       └── rescheduling.yaml
├── reports/
│   ├── html_reporter.py
│   ├── console_reporter.py
│   └── json_reporter.py
└── conftest.py
```

---

## Feedback Loop

```
PRODUCTION MONITORING (daily)
        ↓
REGRESSION DETECTION
  • Compare current run vs 7-day average
  • Telegram alert if any dimension drops >5%
  • Identify which test cases started failing
        ↓
ROOT CAUSE ANALYSIS
  • Review Langfuse trace for failing test case
  • Check: recent prompt changes, config updates, LLM version
  • Identify: isolated failure or systemic pattern
        ↓
REMEDIATION
  A) Prompt refinement: Update system_message template
  B) Tool refinement: Fix tool definition or implementation
  C) Context engineering: Update config/policies in Supabase
  D) New regression test: Add test case to prevent recurrence
        ↓
VALIDATION
  • Re-run eval on fixed branch
  • Confirm: failing test now passes, no new failures introduced
  • PR with fix + new test case → merge after eval gate passes
```

**Immutable reference tests:** Mark critical test cases as `reference_test = TRUE`. These must never regress. Failure requires manual override with recorded justification (not just the standard `eval-override` PR label).

---

## New Client Onboarding via Eval

```
1. Seed 10–20 client-specific test cases (PM owns)
2. Add client config (Supabase clients table + Railway env vars)
3. Run baseline eval:
   python -m engine.tests.eval.run_eval --client <id> --baseline --save-baseline
4. Iterate on context engineering until score >= 85%
5. Lock baseline run_id in client metadata
6. Final eval gate before go-live — must meet or exceed baseline
7. Post go-live: client included in daily monitoring automatically
```

---

## Visibility & Control Summary

| Surface | What It Shows | Access |
|---------|--------------|--------|
| Telegram bot | Regression alerts, safety failures | Ops team |
| GitHub Actions | CI pass/fail, HTML report artifact, PR comment | Engineering |
| Supabase eval_results | Full queryable results, trend SQL queries | Supabase Studio |
| Langfuse (Phase 2) | Trace timeline, LLM calls, cost tracking, dashboard | Flow AI team |

**User control mechanisms:**
- PR gate override via `eval-override` label + written justification in PR body
- Disable specific test cases in Supabase (`enabled = FALSE` with reason in metadata)
- Manual CLI run for debugging (`--test-name`, `--debug`, `--save-traces`)
- Baseline comparison (`--compare-baseline`), baseline update (`save_baseline.py`)

---

## Agent Dispatch Plan

| Phase | Agent | Output | Sequence |
|-------|-------|--------|----------|
| 1 | `@product-manager` | `docs/requirements/eval_pipeline.md` | Dispatched now |
| 1 | `@software-architect` | `docs/architecture/eval_pipeline.md` | After PM requirements approved |
| 2 | `@sdet-engineer` → `@software-engineer` | Full eval framework (EvalRunner, 6 scorers, CLI, reporters, alerts) | After architecture approved |
| 3 | `@product-manager` | Platform YAML test cases + HeyAircon YAML test cases | After framework built |
| 4 | `@sdet-engineer` | CI integration, Supabase seed, baseline eval, runbook | After test cases seeded |
| 5 | `@software-architect` + `@sdet-engineer` | Langfuse integration | Post-launch |

---

## Timeline

| Phase | Description | Duration |
|-------|-------------|----------|
| 1 | Requirements + Architecture | Weeks 1–2 |
| 2 | Framework implementation | Weeks 3–5 |
| 3 | Test case seeding | Week 6 |
| 4 | CI integration + baseline eval | Week 7 |
| 5 | Langfuse integration | Weeks 8–9 |

---

## Success Criteria

- [ ] CI blocks PRs that fail any safety test (100% threshold enforced)
- [ ] CI blocks PRs that drop overall score below 85%
- [ ] Daily Telegram alert fires within 24 hours of regression
- [ ] New client onboarding includes baseline eval gate before go-live
- [ ] Full eval suite runs in < 5 minutes
- [ ] All eval runs traceable to git commit + LLM version
