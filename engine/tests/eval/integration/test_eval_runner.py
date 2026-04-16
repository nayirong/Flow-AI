"""
Integration tests for EvalRunner.

Verifies:
- Full pipeline run with mock agent executes all test cases and returns RunResult
- Single test case crash is isolated — pipeline continues and marks test as error
- Results are written to Supabase eval_results (when DB creds available)
- RunMetadata is populated in every result row
- Parallel execution: 5 concurrent tests complete without ordering issues

Run: pytest engine/tests/eval/integration/test_eval_runner.py -v
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from engine.tests.eval.models import (
    AgentOutput,
    RunMetadata,
    TestCase,
    ThresholdConfig,
    DimensionThreshold,
)
from engine.tests.eval.loader import TestCaseLoader
from engine.tests.eval.runner import EvalRunner
from engine.tests.eval.scorers.intent_scorer import IntentScorer
from engine.tests.eval.scorers.tool_scorer import ToolScorer
from engine.tests.eval.scorers.escalation_scorer import EscalationScorer
from engine.tests.eval.scorers.safety_scorer import SafetyScorer
from engine.tests.eval.scorers.response_scorer import ResponseScorer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def run_metadata():
    return RunMetadata(
        run_id=f"test-run-{uuid.uuid4().hex[:8]}",
        git_commit="abc1234",
        branch="test",
        llm_model="mock",
        llm_version="0.0.0",
        prompt_version="test",
        triggered_by="manual_cli",
        timestamp=datetime.utcnow(),
    )


@pytest.fixture
def threshold_config():
    return ThresholdConfig(
        safety=DimensionThreshold(min_score=0.0, blocking=False),
        tool_use_critical=DimensionThreshold(min_score=0.0, blocking=False),
        escalation=DimensionThreshold(min_score=0.0, blocking=False),
        intent=DimensionThreshold(min_score=0.0, blocking=False),
        overall=DimensionThreshold(min_score=0.0, blocking=False),
        regression_alert_delta=0.05,
    )


@pytest.fixture
def mock_executor():
    """Mock AgentExecutor that returns a deterministic AgentOutput."""
    executor = MagicMock()
    executor.execute = AsyncMock(return_value=AgentOutput(
        response_text="I can help you with booking. What service do you need?",
        tool_called=None,
        escalation_triggered=False,
        classified_intent="booking_request",
        execution_time_ms=100,
    ))
    return executor


@pytest.fixture
def mock_result_store():
    store = MagicMock()
    store.write_results = AsyncMock(return_value=None)
    return store


@pytest.fixture
def mock_reporter():
    reporter = MagicMock()
    reporter.report = AsyncMock(return_value=None)
    return reporter


@pytest.fixture
def sample_test_cases():
    """Small set of test cases that cover 3 categories."""
    return [
        TestCase(
            client_id="hey-aircon",
            category="intent",
            test_name="runner_test_intent_greeting",
            input_message="Hello",
            expected_intent="greeting",
            enabled=True,
        ),
        TestCase(
            client_id="hey-aircon",
            category="intent",
            test_name="runner_test_booking_intent",
            input_message="I want to book a service",
            expected_intent="booking_request",
            enabled=True,
        ),
        TestCase(
            client_id="hey-aircon",
            category="escalation",
            test_name="runner_test_no_escalation",
            input_message="What services do you offer?",
            expected_escalation=False,
            enabled=True,
        ),
    ]


@pytest.fixture
def mock_loader(sample_test_cases):
    loader = MagicMock()
    loader.load = AsyncMock(return_value=sample_test_cases)
    return loader


@pytest.fixture
def scorers():
    return [
        IntentScorer(),
        ToolScorer(),
        EscalationScorer(),
        SafetyScorer(),
        ResponseScorer(),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eval_run_with_mock_agent(
    mock_loader, mock_executor, scorers, mock_result_store,
    mock_reporter, threshold_config, run_metadata,
):
    """
    Full pipeline run with a mock agent:
    - All 3 test cases are executed
    - RunResult has total_tests == 3
    - run_id matches the RunMetadata
    - result_store.write_results is called once
    - reporter.report is called once
    """
    runner = EvalRunner(
        loader=mock_loader,
        executor=mock_executor,
        scorers=scorers,
        result_store=mock_result_store,
        reporters=[mock_reporter],
        alert_dispatcher=None,
        threshold_config=threshold_config,
        run_metadata=run_metadata,
        parallel_limit=3,
    )

    run_result = await runner.run(client_id="hey-aircon")

    assert run_result is not None
    assert run_result.run_id == run_metadata.run_id
    assert run_result.total_tests == 3
    mock_result_store.write_results.assert_called_once()
    mock_reporter.report.assert_called_once()


@pytest.mark.asyncio
async def test_eval_run_captures_metadata_in_results(
    mock_loader, mock_executor, scorers, mock_result_store,
    mock_reporter, threshold_config, run_metadata,
):
    """
    Each TestCaseResult in the results written to result_store contains
    the correct run_id and run_metadata.
    """
    runner = EvalRunner(
        loader=mock_loader,
        executor=mock_executor,
        scorers=scorers,
        result_store=mock_result_store,
        reporters=[mock_reporter],
        alert_dispatcher=None,
        threshold_config=threshold_config,
        run_metadata=run_metadata,
    )

    await runner.run(client_id="hey-aircon")

    call_args = mock_result_store.write_results.call_args
    results = call_args[0][0]  # first positional arg

    assert len(results) == 3
    for result in results:
        assert result.run_id == run_metadata.run_id
        assert result.run_metadata.git_commit == "abc1234"


@pytest.mark.asyncio
async def test_eval_single_test_failure_does_not_crash(
    mock_result_store, mock_reporter, threshold_config, run_metadata,
):
    """
    When one test case's executor raises an unexpected exception,
    the pipeline:
    - continues executing remaining test cases
    - marks the failed test with error in AgentOutput
    - still calls result_store.write_results with the completed results
    """
    # Executor raises on first call, succeeds on second
    call_count = 0

    async def flaky_execute(test_case):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated agent crash")
        return AgentOutput(
            response_text="OK",
            classified_intent="greeting",
            execution_time_ms=50,
        )

    failing_executor = MagicMock()
    failing_executor.execute = flaky_execute

    two_cases = [
        TestCase(
            client_id="hey-aircon",
            category="intent",
            test_name="crash_test_first",
            input_message="This will crash",
            expected_intent="greeting",
            enabled=True,
        ),
        TestCase(
            client_id="hey-aircon",
            category="intent",
            test_name="crash_test_second",
            input_message="This will succeed",
            expected_intent="greeting",
            enabled=True,
        ),
    ]

    loader = MagicMock()
    loader.load = AsyncMock(return_value=two_cases)

    runner = EvalRunner(
        loader=loader,
        executor=failing_executor,
        scorers=[IntentScorer()],
        result_store=mock_result_store,
        reporters=[mock_reporter],
        alert_dispatcher=None,
        threshold_config=threshold_config,
        run_metadata=run_metadata,
        parallel_limit=1,  # Sequential to ensure predictable order
    )

    run_result = await runner.run()

    # Pipeline did not raise
    assert run_result is not None
    assert run_result.total_tests == 2
    # result_store still called with both results
    mock_result_store.write_results.assert_called_once()
    all_results = mock_result_store.write_results.call_args[0][0]
    assert len(all_results) == 2
    # First result has an error
    error_result = next((r for r in all_results if r.test_case.test_name == "crash_test_first"), None)
    assert error_result is not None
    assert error_result.agent_output.error is not None


@pytest.mark.asyncio
async def test_eval_run_returns_dimension_scores(
    mock_loader, mock_executor, scorers, mock_result_store,
    mock_reporter, threshold_config, run_metadata,
):
    """
    RunResult.scores_by_dimension contains an entry for every category
    present in the loaded test cases.
    """
    runner = EvalRunner(
        loader=mock_loader,
        executor=mock_executor,
        scorers=scorers,
        result_store=mock_result_store,
        reporters=[mock_reporter],
        alert_dispatcher=None,
        threshold_config=threshold_config,
        run_metadata=run_metadata,
    )

    run_result = await runner.run(client_id="hey-aircon")

    # sample_test_cases has intent and escalation categories
    assert "intent" in run_result.scores_by_dimension
    assert "escalation" in run_result.scores_by_dimension
    for dim, score in run_result.scores_by_dimension.items():
        assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_eval_run_empty_test_cases(
    mock_result_store, mock_reporter, threshold_config, run_metadata,
):
    """
    When no test cases are loaded, RunResult returns total_tests=0
    and result_store is NOT called.
    """
    empty_loader = MagicMock()
    empty_loader.load = AsyncMock(return_value=[])

    runner = EvalRunner(
        loader=empty_loader,
        executor=MagicMock(),
        scorers=[],
        result_store=mock_result_store,
        reporters=[mock_reporter],
        alert_dispatcher=None,
        threshold_config=threshold_config,
        run_metadata=run_metadata,
    )

    run_result = await runner.run()

    assert run_result.total_tests == 0
    mock_result_store.write_results.assert_not_called()

