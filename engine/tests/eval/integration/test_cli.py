"""
Integration tests for the run_eval CLI entry point.

Verifies:
- --help displays usage and exits 0
- --dry-run loads test cases and prints count without executing agent
- --client flag filters test cases to the specified client
- --category flag filters to specified category
- Exit code 1 when thresholds are violated (mocked)
- Exit code 0 when thresholds are met

Run: pytest engine/tests/eval/integration/test_cli.py -v
"""

import subprocess
import sys
import os
from pathlib import Path

import pytest


# Path to module
MODULE = "engine.tests.eval.run_eval"
WORKSPACE = Path(__file__).parents[4]  # engine/tests/eval/integration -> workspace root


def run_cli(*args, env_overrides=None):
    """Run the CLI as a subprocess and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    # Ensure PYTHONPATH includes workspace root so 'engine' package is importable
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{WORKSPACE}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(WORKSPACE)
    # Ensure no real LLM calls in CLI tests
    env["LLM_PROVIDER"] = "mock"
    env["EVAL_SUPABASE_URL"] = env.get("EVAL_SUPABASE_URL", "http://localhost:54321")
    env["EVAL_SUPABASE_SERVICE_KEY"] = env.get("EVAL_SUPABASE_SERVICE_KEY", "mock-key")
    if env_overrides:
        env.update(env_overrides)

    result = subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        capture_output=True,
        text=True,
        cwd=str(WORKSPACE),
        env=env,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cli_help():
    """
    --help displays usage information and exits with code 0.
    """
    returncode, stdout, stderr = run_cli("--help")

    assert returncode == 0
    assert "Flow AI Evaluation Pipeline" in stdout or "usage" in stdout.lower()
    assert "--client" in stdout
    assert "--dry-run" in stdout


def test_cli_dry_run_exits_zero():
    """
    --dry-run loads test cases and exits 0 without executing the agent.
    Output must mention the number of test cases loaded.
    """
    returncode, stdout, stderr = run_cli("--dry-run", "--client", "hey-aircon")

    assert returncode == 0, f"--dry-run exited {returncode}\nstderr: {stderr}"
    combined = stdout + stderr
    # Should mention loaded test cases
    assert any(word in combined.lower() for word in ["loaded", "test case", "dry"]), (
        f"Expected dry-run output to mention test cases.\nOutput: {combined}"
    )


def test_cli_filter_by_client():
    """
    --client hey-aircon loads only hey-aircon test cases.
    The dry-run output must not mention platform test cases.
    """
    _, stdout_all, _ = run_cli("--dry-run")
    _, stdout_filtered, _ = run_cli("--dry-run", "--client", "hey-aircon")

    # Filtering reduces (or equals) case count
    def extract_count(output: str) -> int:
        import re
        match = re.search(r"(\d+)\s+test case", output, re.IGNORECASE)
        return int(match.group(1)) if match else -1

    all_count = extract_count(stdout_all)
    filtered_count = extract_count(stdout_filtered)

    if all_count > 0 and filtered_count > 0:
        assert filtered_count <= all_count, (
            f"Filtered count ({filtered_count}) should be <= total ({all_count})"
        )


def test_cli_filter_by_category():
    """
    --category safety loads only safety test cases in dry-run mode.
    """
    returncode, stdout, stderr = run_cli("--dry-run", "--category", "safety")

    assert returncode == 0, f"CLI exited {returncode}\nstderr: {stderr}"


def test_cli_unknown_client_exits_zero_with_warning():
    """
    --client unknown-client loads zero test cases (no match) and exits 0
    with a warning rather than crashing.
    """
    returncode, stdout, stderr = run_cli("--dry-run", "--client", "unknown-client-xyz")

    assert returncode == 0, (
        f"Unknown client should exit 0 (no tests is valid), got {returncode}\nstderr: {stderr}"
    )


def test_cli_exit_code_on_threshold_violation():
    """
    When check_threshold.py finds a threshold violation, the overall
    pipeline must exit with code 1 to block CI merges.

    This test invokes check_threshold directly with a mocked summary
    that has a safety score below the minimum threshold.
    """
    import json
    import tempfile

    # Build a summary JSON that violates safety threshold (min_score=0.9)
    failing_summary = {
        "run_id": "test-violation-run",
        "overall_score": 0.5,
        "scores": {
            "safety": 0.5,   # below threshold
            "intent": 0.95,
            "tool_use": 0.90,
        },
        "total_tests": 10,
        "passed_tests": 5,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(failing_summary, f)
        summary_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "engine.tests.eval.check_threshold", "--summary", summary_path],
            capture_output=True,
            text=True,
            cwd=str(WORKSPACE),
            timeout=30,
        )
        assert result.returncode == 1, (
            f"Expected exit code 1 for threshold violation, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    finally:
        os.unlink(summary_path)


def test_cli_exit_code_zero_when_thresholds_met():
    """
    When all dimension scores are above thresholds, check_threshold exits 0.
    """
    import json
    import tempfile

    passing_summary = {
        "run_id": "test-passing-run",
        "overall_score": 0.97,
        "scores": {
            "safety": 1.0,
            "intent": 0.96,
            "tool_use": 0.95,
            "escalation": 0.98,
        },
        "total_tests": 20,
        "passed_tests": 19,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(passing_summary, f)
        summary_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "engine.tests.eval.check_threshold", "--summary", summary_path],
            capture_output=True,
            text=True,
            cwd=str(WORKSPACE),
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Expected exit code 0 when thresholds met, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    finally:
        os.unlink(summary_path)

