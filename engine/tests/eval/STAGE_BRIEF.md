# Stage Brief: Evaluation Pipeline Implementation

> Dispatched by: @sdet-engineer  
> Target: @software-engineer  
> Created: 2026-04-16  
> Architecture: [docs/architecture/eval_pipeline.md](../../../docs/architecture/eval_pipeline.md)  
> Test Plan: [docs/test-plan/eval_pipeline.md](../../../docs/test-plan/eval_pipeline.md)

---

## 1. Goal

Implement the Flow AI evaluation pipeline — an automated quality assurance system that validates WhatsApp agent behaviors before code reaches production and continuously monitors production quality through regression detection.

---

## 2. Scope — What to Implement

### 2.1 Core Pipeline Modules

**Files to implement** (all in `engine/tests/eval/`):

```
run_eval.py              # CLI entry point (stub exists, needs full implementation)
runner.py                # EvalRunner orchestrator (stub exists)
loader.py                # TestCaseLoader (stub exists)
executor.py              # AgentExecutor (stub exists)
regression_detector.py   # RegressionDetector (stub exists)
check_threshold.py       # Threshold checker utility (stub exists)
```

### 2.2 Scorers (6 total)

**Files to implement** (all in `engine/tests/eval/scorers/`):

```
base.py               # BaseScorer abstract class (complete — do not modify)
intent_scorer.py      # IntentScorer (stub exists)
tool_scorer.py        # ToolScorer (stub exists)
escalation_scorer.py  # EscalationScorer (stub exists)
safety_scorer.py      # SafetyScorer (stub exists)
response_scorer.py    # ResponseScorer (stub exists)
persona_scorer.py     # PersonaScorer stub only (Phase 2)
```

### 2.3 Alerts

**Files to implement** (all in `engine/tests/eval/alerts/`):

```
base.py               # BaseNotifier abstract class (complete — do not modify)
telegram_notifier.py  # TelegramNotifier (stub exists)
```

### 2.4 Reporters

**Files to implement** (all in `engine/tests/eval/reports/`):

```
base.py               # BaseReporter abstract class (stub exists)
console_reporter.py   # ConsoleReporter (stub exists)
html_reporter.py      # HtmlReporter (stub exists)
json_reporter.py      # JsonReporter (stub exists)
```

### 2.5 Unit Tests

**Files to implement** (all in `engine/tests/eval/unit/`):

```
test_intent_scorer.py
test_tool_scorer.py
test_escalation_scorer.py
test_safety_scorer.py
test_response_scorer.py
test_regression_detector.py
test_telegram_notifier.py
```

All test stubs exist. Implement according to test plan Section 3.

### 2.6 Integration Tests

**Files to implement** (all in `engine/tests/eval/integration/`):

```
test_eval_runner.py
test_loader.py
test_cli.py
```

All test stubs exist. Implement according to test plan Section 4.

---

## 3. What NOT to Implement

**Do NOT modify:**
- Any files in `engine/core/` (production agent code)
- Any files in `engine/config/` (client config loading)
- Any files in `engine/integrations/` (Supabase, Meta, Google Calendar clients)
- Client Supabase schemas (no new tables in client DBs)
- FastAPI webhook routes

**Do NOT implement:**
- PersonaScorer beyond the stub (Phase 2 only)
- Langfuse integration (Phase 2 only)
- Multi-turn conversation evaluation (Phase 2)
- A/B prompt testing (Phase 2)

**Do NOT create:**
- Real Telegram bot (use mocks in tests via pytest-httpx)
- Real Supabase tables yet (SDET will provision test DB)

---

## 4. Interface Contracts (from Architecture)

All interfaces are fully specified in [docs/architecture/eval_pipeline.md](../../../docs/architecture/eval_pipeline.md) Section 3.

### Key Interfaces

#### BaseScorer

```python
class BaseScorer(ABC):
    @abstractmethod
    async def score(
        self,
        test_case: TestCase,
        agent_output: AgentOutput,
    ) -> ScorerResult:
        """
        Must return ScorerResult with:
        - passed: bool
        - score: float (0.0 to 1.0)
        - failure_reason: str | None
        
        Must never raise — catch all exceptions, return error result.
        """
```

#### AgentExecutor

```python
class AgentExecutor:
    async def execute(
        self,
        test_case: TestCase,
    ) -> AgentOutput:
        """
        Execute agent for test case.
        
        Returns AgentOutput with:
        - response_text: str
        - tool_called: str | None
        - tool_params: dict | None
        - escalation_triggered: bool
        - classified_intent: str | None
        - execution_time_ms: int
        - raw_response: dict
        - error: str | None (if execution failed)
        
        Must never raise — return AgentOutput(error=...) on failure.
        """
```

#### BaseNotifier

```python
class BaseNotifier(ABC):
    @abstractmethod
    async def send_alert(self, alert: AlertPayload) -> bool:
        """
        Returns True if send succeeded, False otherwise.
        Must never raise — catch all exceptions, return False.
        """
```

---

## 5. Implementation Notes

### 5.1 All Async

Use `async def` and `await` throughout. No synchronous blocking calls.

### 5.2 Error Handling

**Critical invariant:** The eval pipeline must never crash due to a single test case failure.

- Errors in individual test cases → captured in `TestCaseResult`, not propagated
- Scorer exceptions → return `ScorerResult(passed=False, score=0.0, failure_reason="scorer_error: ...")`
- AgentExecutor failures → return `AgentOutput(error="...")`
- TelegramNotifier failures → return `False`

See architecture doc Section 10 for full error handling strategy.

### 5.3 Logging

Use `structlog` or standard `logging` module. No bare `print` statements.

### 5.4 Pydantic Models

Use Pydantic v2 for all data models. Models are specified in architecture doc Section 4.

### 5.5 HTTP Client

Use `httpx.AsyncClient` for all HTTP calls (Telegram). No `requests` library.

### 5.6 Testing

- Use `pytest` with `pytest-asyncio` for async tests
- Use `pytest-httpx` for mocking HTTP calls in Telegram tests
- All tests must be runnable with `pytest engine/tests/eval/ -v`

---

## 6. Integration with Existing Engine

The evaluation pipeline is a **testing harness** that wraps production agent code.

### 6.1 Shared Code

| Component | Location | How Eval Uses It |
|-----------|----------|------------------|
| **ClientConfig** | `engine/config/client_config.py` | `AgentExecutor.load_client_config(client_id)` |
| **Context Builder** | `engine/core/context_builder.py` | `AgentExecutor._build_context()` |
| **Agent Runner** | `engine/core/agent_runner.py` | `AgentExecutor._invoke_agent()` — **DEPENDENCY** |
| **Tool Definitions** | `engine/core/tools/definitions.py` | Import tool definitions list |
| **Tool Dispatch** | `engine/core/tools/__init__.py` | Import tool dispatch map |
| **Supabase Client** | `engine/integrations/supabase_client.py` | `get_client_db(client_id)` |

### 6.2 AgentExecutor Dependency

**BLOCKING DEPENDENCY:** `AgentExecutor` requires `engine/core/agent_runner.py` to expose:

```python
async def run_agent(
    system_message: str,
    conversation_history: list[dict],
    current_message: str,
    tool_definitions: list[dict],
    tool_dispatch: dict[str, Callable],
    client_config: ClientConfig,
    anthropic_client: Anthropic,
    timeout_seconds: int = 30,
) -> dict:
    """
    Returns:
        {
          "response_text": str,
          "tool_calls": [{"tool_name": str, "tool_params": dict, "result": dict}],
          "classified_intent": str | None,
          "raw_response": dict,
        }
    """
```

**If `agent_runner.py` does not exist yet:** Document this as a blocker. Implement all other modules first, mock `run_agent()` in tests, return to `AgentExecutor` when `agent_runner.py` is available.

---

## 7. Data Models (from Architecture Doc Section 4)

All Pydantic models are specified in architecture doc Section 4. Key models:

- `TestCase`
- `AgentOutput`
- `ScorerResult`
- `TestCaseResult`
- `RunMetadata`
- `RunResult`
- `DimensionThreshold`
- `ThresholdConfig`
- `AlertPayload`

**Create these in:** `engine/tests/eval/models.py` (new file)

---

## 8. Validation Commands

Before submitting work, run these commands:

### Format Check

```bash
# Python formatter (black or ruff)
black engine/tests/eval/ --check
# or
ruff format engine/tests/eval/ --check
```

If any file is unformatted, SDET will reject the work.

### Unit Tests

```bash
pytest engine/tests/eval/unit/ -v
```

All tests must pass.

### Integration Tests

```bash
pytest engine/tests/eval/integration/ -v
```

All tests must pass.

### Full Test Suite

```bash
pytest engine/tests/eval/ -v
```

All tests must pass. No test should be skipped without SDET approval.

### Type Checking (if configured)

```bash
mypy engine/tests/eval/
```

---

## 9. Constraints

### 9.1 No Hardcoded Client Data

All client-specific data must load from:
- Environment variables
- Supabase `clients` table
- Supabase `eval_test_cases` table

### 9.2 No Direct Commits to Main

All changes go through PR review. SDET is the gatekeeper.

### 9.3 Parallel Execution

`EvalRunner` must support concurrent test case execution with configurable parallelism limit (default: 5).

### 9.4 5-Minute Runtime SLA

Full eval suite with 40 test cases must complete in <5 minutes.

### 9.5 No External Dependencies

- Telegram: direct HTTP via `httpx`, no Telegram SDK
- HTML reports: inline CSS/JS, no external CDN dependencies

---

## 10. Open Questions (SDET Needs Answers Before Merge)

### Q1: Intent Classification Capture

**Question:** Does `agent_runner.py` currently expose `classified_intent` in its return value?

**If No:** Add `classified_intent: str | None` to return dict. This is a blocker for IntentScorer.

### Q2: Baseline Locking Storage

**Question:** Where should we store the locked baseline `run_id`?

**Options:**
- A. Client Supabase `clients.metadata` JSONB field
- B. Eval Supabase `client_baselines` table

**Recommendation:** Option B (dedicated table).

### Q3: Test Case YAML Authorship

**Question:** Who writes platform-level YAML test cases?

**Answer:** SDET for Phase 1. PM will contribute later.

---

## 11. Success Criteria

Work is ready for SDET review when:

1. ✅ All stubs replaced with full implementations
2. ✅ All unit tests pass (`pytest engine/tests/eval/unit/ -v`)
3. ✅ All integration tests pass (`pytest engine/tests/eval/integration/ -v`)
4. ✅ All files formatted correctly (`black --check` or `ruff format --check`)
5. ✅ No `# TODO: implement` comments remain in non-test code
6. ✅ All interfaces match architecture doc exactly
7. ✅ All error handling follows architecture doc Section 10
8. ✅ All open questions answered and documented in PR description

---

## 12. Dispatch Metadata

**Worktree:** `.worktree/eval-pipeline-implementation`

**Prerequisite:** None (first slice)

**Baseline:** `main`

**Format Command:** `black engine/tests/eval/` or `ruff format engine/tests/eval/`

**Validate:**
```bash
pytest engine/tests/eval/ -v
black engine/tests/eval/ --check
```

**Boundary Verification:**

This slice involves integration with:
- `engine/core/agent_runner.py` — verify interface matches architecture doc Section 6 (AgentExecutor Design)
- Supabase `eval_test_cases` table — verify schema matches architecture doc Section 5 (Supabase DDL)
- Telegram bot API — verify HTTP payload matches architecture doc Section 8 (Telegram Notifier Design)

**Success Check:**

**Proof metric:** Full eval run completes with sample test cases, writes results to Supabase, generates HTML/JSON reports, exits with correct code (0 or 1).

**Proxy metrics:**
- Unit tests pass
- Integration tests pass
- CLI `--help` works
- Dry-run mode works

---

**End of Stage Brief**
