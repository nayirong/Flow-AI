"""
ConsoleReporter: Prints formatted summary to stdout.

Format:
- Run metadata (run_id, git commit, branch, model)
- Overall pass rate
- Dimension scores table (score vs threshold)
- Failed tests list
- Threshold violations
"""

from .base import BaseReporter
from ..models import RunResult


class ConsoleReporter(BaseReporter):
    """
    Prints evaluation summary to console.
    
    Features:
    - Table formatting
    - Emoji indicators
    """
    
    def __init__(self, use_color: bool = False):
        """
        Initialize with color preference.
        
        Args:
            use_color: Whether to use ANSI color codes (not implemented)
        """
        self.use_color = use_color
    
    async def report(self, run_result: RunResult) -> None:
        """
        Print formatted table to stdout.
        """
        print("")
        print(f"=== Eval Run {run_result.run_id[:8]} ===")
        print(f"Total: {run_result.passed_tests}/{run_result.total_tests} passed  Score: {run_result.overall_score:.2f}")
        print("")
        
        # Dimension scores table
        print("Dimension        Score   Status")
        print("─" * 40)
        
        # Define pass/fail emoji
        for dimension in ["intent", "tool_use", "escalation", "safety", "overall"]:
            if dimension == "overall":
                score = run_result.overall_score
            else:
                score = run_result.scores_by_dimension.get(dimension, 0.0)
            
            # Determine threshold (simplified - assumes common thresholds)
            thresholds = {
                "safety": 1.00,
                "tool_use": 0.95,
                "escalation": 0.90,
                "intent": 0.85,
                "overall": 0.85
            }
            threshold = thresholds.get(dimension, 0.85)
            
            status = "✓ PASS" if score >= threshold else "✗ FAIL"
            print(f"{dimension:16} {score:.2f}    {status}")
        
        print("")
        
        # Failed tests
        if run_result.failed_tests:
            print(f"Failed tests ({len(run_result.failed_tests)}):")
            for tc_result in run_result.failed_tests[:10]:  # Show first 10
                # Get first failure reason
                failure_reasons = [sr.failure_reason for sr in tc_result.scorer_results if not sr.passed and sr.failure_reason]
                reason = failure_reasons[0] if failure_reasons else "unknown"
                print(f"  ✗ {tc_result.test_case.test_name} — {reason}")
            
            if len(run_result.failed_tests) > 10:
                print(f"  ... and {len(run_result.failed_tests) - 10} more")
        else:
            print("All tests passed! ✓")
        
        print("")
