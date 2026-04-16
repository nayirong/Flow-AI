"""Unit tests for IntentScorer."""

import pytest


@pytest.mark.asyncio
async def test_intent_exact_match(sample_test_case, sample_agent_output):
    """Pass when expected_intent matches classified_intent."""
    # TODO: implement test
    # See test plan Section 3.1 for full test specification
    pass


@pytest.mark.asyncio
async def test_intent_mismatch():
    """Fail when expected_intent does not match classified_intent."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_intent_no_expected():
    """Skip when expected_intent is None."""
    # TODO: implement test
    pass
