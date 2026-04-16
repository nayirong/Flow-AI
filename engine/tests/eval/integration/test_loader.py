"""Integration tests for TestCaseLoader."""

import pytest


@pytest.mark.asyncio
async def test_loader_merges_yaml_and_supabase():
    """Load from both YAML and Supabase, deduplicate by test_name."""
    # TODO: implement integration test
    # See test plan Section 4.2 for full test specification
    pass


@pytest.mark.asyncio
async def test_loader_filters_by_client():
    """Filter test cases by client_id."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_loader_filters_by_category():
    """Filter test cases by category."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_loader_skips_invalid_yaml():
    """Skip YAML files with parse errors."""
    # TODO: implement test
    pass
