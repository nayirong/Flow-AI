"""
RegressionDetector: Compares current run to baseline/rolling average.

Triggers alerts when:
- Any dimension drops >5% vs N-day rolling average
- Reference test fails
- Safety test fails (always)
- Critical test fails
"""


class RegressionDetector:
    """
    Detects regressions by comparing run results to historical data.
    
    Comparison modes:
    - Rolling average (default: 7-day)
    - Locked baseline
    - Previous run
    """
    
    def __init__(
        self,
        eval_supabase_client,  # AsyncClient
        threshold_config,  # ThresholdConfig
    ):
        """Initialize with database client and threshold config."""
        self.eval_supabase_client = eval_supabase_client
        self.threshold_config = threshold_config
    
    async def detect_regressions(
        self,
        run_result,  # RunResult
        compare_days: int = 7,
    ) -> list:  # -> list[AlertPayload]
        """
        Compare run_result to N-day rolling average.
        
        Returns:
            List of AlertPayload objects (one per regression detected).
        
        Logic:
        - Query eval_results for last N days, same client(s)
        - Compute average score per dimension
        - For each dimension: if current < average - 0.05: create alert
        - If reference test fails: create baseline_regression alert
        - If safety fails: create safety_failure alert (always)
        - If critical test fails: create critical_failure alert
        """
        # TODO: implement
        # - For each dimension in run_result:
        #   - Compute rolling average via _compute_rolling_average()
        #   - Compare to current score
        #   - If delta > threshold_config.regression_alert_delta: create alert
        # - Check reference tests via _check_reference_tests()
        # - Check safety failures
        # - Return list of AlertPayload objects
        
        raise NotImplementedError("RegressionDetector.detect_regressions() not yet implemented")
    
    async def _compute_rolling_average(
        self,
        client_id: str,
        dimension: str,
        days: int,
    ) -> float:
        """
        Query eval_results, calculate average score for dimension.
        
        SQL:
        SELECT AVG(
          (scorer_results->>'dimension')::jsonb->>'score'
        )::float
        FROM eval_results
        WHERE client_id = $1
          AND category = $2
          AND created_at > NOW() - INTERVAL '$3 days'
        """
        # TODO: implement Supabase query
        raise NotImplementedError()
    
    async def _check_reference_tests(
        self,
        run_result,  # RunResult
    ) -> list:  # -> list[AlertPayload]
        """Check if any reference tests failed."""
        # TODO: implement
        # - Filter run_result.test_case_results for reference_test=True
        # - For each failed reference test: create baseline_regression alert
        # - Return list of alerts
        raise NotImplementedError()
