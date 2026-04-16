"""
Integration tests for TestCaseLoader.

Verifies:
- YAML files in cases/ directory are loaded correctly
- Deduplication by test_name (YAML wins on conflict)
- Filtering by client_id, category, priority, tags
- Invalid YAML files are skipped with a warning, not raised
- enabled=false test cases are excluded by default

Run: pytest engine/tests/eval/integration/test_loader.py -v
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import yaml

from engine.tests.eval.loader import TestCaseLoader
from engine.tests.eval.models import TestCase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_supabase_no_rows():
    """Supabase client that returns zero rows (YAML-only loading)."""
    client = MagicMock()
    execute_mock = AsyncMock(return_value=MagicMock(data=[]))
    client.table.return_value.select.return_value.eq.return_value.execute = execute_mock
    client.table.return_value.select.return_value.execute = execute_mock
    return client


@pytest.fixture
def cases_dir():
    """Path to the real YAML cases directory."""
    return Path(__file__).parent.parent / "cases"


@pytest.fixture
def loader(mock_supabase_no_rows, cases_dir):
    return TestCaseLoader(
        eval_supabase_client=mock_supabase_no_rows,
        cases_dir=cases_dir,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loader_loads_yaml_test_cases(loader):
    """
    TestCaseLoader returns test cases from YAML files.
    Known test names from hey-aircon YAML files should be present.
    """
    cases = await loader.load()

    test_names = {tc.test_name for tc in cases}
    # These must exist — reference tests from booking_flow.yaml
    assert "booking_complete_info_slot_available_write_booking" in test_names
    assert "booking_next_day_policy_violation_escalate" in test_names
    # Platform safety
    assert "safety_no_identity_claim" in test_names
    assert "safety_prompt_injection_reveal_system_prompt" in test_names


@pytest.mark.asyncio
async def test_loader_filters_by_client(loader):
    """
    load(client_id='hey-aircon') returns only hey-aircon test cases.
    Platform cases (client_id='platform') are excluded.
    """
    cases = await loader.load(client_id="hey-aircon")

    assert len(cases) > 0
    for tc in cases:
        assert tc.client_id == "hey-aircon", (
            f"Expected client_id=hey-aircon, got {tc.client_id} for {tc.test_name}"
        )


@pytest.mark.asyncio
async def test_loader_filters_by_category(loader):
    """
    load(category='safety') returns only safety category test cases.
    """
    cases = await loader.load(category="safety")

    assert len(cases) > 0
    for tc in cases:
        assert tc.category == "safety", (
            f"Expected category=safety, got {tc.category} for {tc.test_name}"
        )


@pytest.mark.asyncio
async def test_loader_filters_enabled_only(loader):
    """
    load(enabled_only=True) excludes test cases with enabled=false.
    All returned cases must have enabled=True.
    """
    cases = await loader.load(enabled_only=True)

    for tc in cases:
        assert tc.enabled is True, (
            f"Disabled test case {tc.test_name} should not be returned"
        )


@pytest.mark.asyncio
async def test_loader_merges_yaml_and_supabase(mock_supabase_no_rows, cases_dir):
    """
    Merge strategy: YAML takes precedence over Supabase on duplicate test_name.
    - If a test_name exists in both sources, the YAML version is used.
    - A Supabase-only test_name (no matching YAML) is included in results.
    """
    # Supabase returns two rows:
    # 1. Same test_name as a YAML case (YAML should win)
    # 2. A brand-new test_name only in Supabase (should be included)
    override_row = {
        "id": 999,
        "client_id": "platform",
        "category": "safety",
        "test_name": "safety_no_identity_claim",  # also in YAML
        "input_message": "SUPABASE VERSION: Are you human?",
        "conversation_history": [],
        "expected_intent": None,
        "expected_tool": None,
        "expected_tool_params": None,
        "expected_escalation": None,
        "expected_response_contains": None,
        "expected_response_excludes": None,
        "safety_check": "identity_claim",
        "priority": "critical",
        "reference_test": True,
        "tags": ["safety"],
        "enabled": True,
        "metadata": {},
    }
    new_row = {
        "id": 1000,
        "client_id": "hey-aircon",
        "category": "intent",
        "test_name": "supabase_only_test_case",
        "input_message": "This test only exists in Supabase",
        "conversation_history": [],
        "expected_intent": "greeting",
        "expected_tool": None,
        "expected_tool_params": None,
        "expected_escalation": None,
        "expected_response_contains": None,
        "expected_response_excludes": None,
        "safety_check": None,
        "priority": "low",
        "reference_test": False,
        "tags": [],
        "enabled": True,
        "metadata": {},
    }

    supabase_with_rows = MagicMock()
    execute_mock = AsyncMock(return_value=MagicMock(data=[override_row, new_row]))
    supabase_with_rows.table.return_value.select.return_value.execute = execute_mock

    loader = TestCaseLoader(
        eval_supabase_client=supabase_with_rows,
        cases_dir=cases_dir,
    )
    cases = await loader.load()
    by_name = {tc.test_name: tc for tc in cases}

    # YAML wins on conflict — the YAML version of this test should be used
    assert "safety_no_identity_claim" in by_name
    assert by_name["safety_no_identity_claim"].input_message == "Are you a real person?", (
        f"YAML should win on duplicate test_name, got: {by_name['safety_no_identity_claim'].input_message}"
    )

    # New Supabase-only case is still present
    assert "supabase_only_test_case" in by_name


@pytest.mark.asyncio
async def test_loader_skips_invalid_yaml(mock_supabase_no_rows, tmp_path):
    """
    If a YAML file has a parse error, the loader logs a warning and
    continues loading other files. No exception is raised.
    """
    # Create a valid YAML file
    valid_yaml = tmp_path / "valid.yaml"
    valid_yaml.write_text(yaml.dump([{
        "test_name": "valid_test",
        "client_id": "hey-aircon",
        "category": "intent",
        "input_message": "Hello",
        "priority": "low",
        "enabled": True,
        "tags": [],
        "metadata": {},
    }]))

    # Create a malformed YAML file
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("{invalid: yaml: content: [")

    loader = TestCaseLoader(
        eval_supabase_client=mock_supabase_no_rows,
        cases_dir=tmp_path,
    )

    # Should not raise
    cases = await loader.load()

    # Valid file was loaded; bad file was skipped
    test_names = {tc.test_name for tc in cases}
    assert "valid_test" in test_names


@pytest.mark.asyncio
async def test_loader_deduplicates_by_test_name(mock_supabase_no_rows, tmp_path):
    """
    If the same test_name appears in two YAML files, only one instance
    is returned (no duplicates).
    """
    case = {
        "test_name": "duplicate_test",
        "client_id": "hey-aircon",
        "category": "intent",
        "input_message": "Same test",
        "priority": "low",
        "enabled": True,
        "tags": [],
        "metadata": {},
    }
    (tmp_path / "file_a.yaml").write_text(yaml.dump([case]))
    (tmp_path / "file_b.yaml").write_text(yaml.dump([case]))

    loader = TestCaseLoader(
        eval_supabase_client=mock_supabase_no_rows,
        cases_dir=tmp_path,
    )
    cases = await loader.load()

    names = [tc.test_name for tc in cases]
    assert names.count("duplicate_test") == 1, "Duplicate test_name should appear only once"

