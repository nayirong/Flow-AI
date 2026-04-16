"""Unit tests for SafetyScorer."""

import pytest


@pytest.mark.asyncio
async def test_safety_identity_claim_detected():
    """Fail when identity claim pattern detected."""
    # TODO: implement test
    # See test plan Section 3.4 for full test specification
    pass


@pytest.mark.asyncio
async def test_safety_identity_claim_not_present():
    """Pass when no identity claim."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_safety_data_leak_credit_card():
    """Fail when credit card number in response."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_safety_data_leak_nric():
    """Fail when NRIC/FIN in response."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_safety_out_of_scope_legal_advice():
    """Fail when legal advice given."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_safety_prompt_injection_detected():
    """Fail when prompt injection evidence in response."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_safety_clean_response():
    """Pass when all safety checks pass."""
    # TODO: implement test
    pass
