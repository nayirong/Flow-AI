"""Unit tests for RegressionDetector."""

import pytest


@pytest.mark.asyncio
async def test_regression_detected_on_5pct_drop(mock_supabase_client, threshold_config):
    """Trigger alert when score drops >5%."""
    # TODO: implement test
    # See test plan Section 3.6 for full test specification
    pass


@pytest.mark.asyncio
async def test_regression_not_detected_below_threshold():
    """No alert when drop <5%."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_regression_no_previous_data():
    """No alert on first run (no historical data)."""
    # TODO: implement test
    pass


@pytest.mark.asyncio
async def test_regression_safety_failure_always_alerts():
    """Safety failure always triggers alert, even without historical comparison."""
    # TODO: implement test
    pass
