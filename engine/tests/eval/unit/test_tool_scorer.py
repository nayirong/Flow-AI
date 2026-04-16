"""Unit tests for ToolScorer."""

import pytest


@pytest.mark.asyncio
async def test_tool_exact_match_with_params():
    """Full credit when tool name and params both match."""
    # TODO: implement test
    # See test plan Section 3.2 for full test specification
    pass


@pytest.mark.asyncio
async def test_tool_correct_name_wrong_params():
    """Partial credit (0.5) when tool correct but params wrong."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_tool_wrong_name():
    """Zero credit when wrong tool called."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_tool_dynamic_params_skip():
    """Dynamic params ({{ tomorrow_iso }}) should not cause failure."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_tool_no_expected():
    """Skip when expected_tool is None."""
    # TODO: implement test
    pass
