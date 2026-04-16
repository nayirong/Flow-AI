"""
JsonReporter: Exports structured JSON summary.

Schema:
{
  "run_id": "...",
  "timestamp": "2026-04-16T14:32:00Z",
  "git_commit": "abc123",
  "branch": "main",
  "llm_model": "claude-sonnet-4-6",
  "overall_pass_rate": 0.88,
  "dimension_scores": {
    "intent": 0.88,
    "tool_use": 0.92,
    ...
  },
  "client_scores": {
    "hey-aircon": 0.90,
    ...
  },
  "failed_tests": [
    {
      "test_name": "...",
      "category": "...",
      "failure_reason": "..."
    }
  ],
  "thresholds_met": {
    "safety": true,
    "overall": false,
    ...
  },
  "threshold_violations": ["tool_use_critical"]
}
"""

import json
from pathlib import Path

from .base import BaseReporter
from ..models import RunResult


class JsonReporter(BaseReporter):
    """
    Exports JSON summary for programmatic consumption.
    
    Used by:
    - GitHub Actions PR comment script
    - Threshold checker
    - External monitoring tools
    """
    
    def __init__(self, output_dir: str):
        """
        Initialize with output directory path.
        
        Args:
            output_dir: Directory to write JSON file
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def report(self, run_result: RunResult) -> str:
        """
        Write JSON summary file.
        
        Returns:
            Path to generated JSON file (eval_summary.json).
        """
        # Build full summary
        full_summary = {
            "run_id": run_result.run_id,
            "timestamp": run_result.run_metadata.timestamp.isoformat(),
            "git_commit": run_result.run_metadata.git_commit,
            "branch": run_result.run_metadata.branch,
            "llm_model": run_result.run_metadata.llm_model,
            "llm_version": run_result.run_metadata.llm_version,
            "total_tests": run_result.total_tests,
            "passed_tests": run_result.passed_tests,
            "overall_score": run_result.overall_score,
            "scores_by_dimension": run_result.scores_by_dimension,
            "scores_by_client": run_result.scores_by_client,
            "failed_tests": [
                {
                    "test_name": tc.test_case.test_name,
                    "category": tc.test_case.category,
                    "client_id": tc.test_case.client_id,
                    "overall_score": tc.overall_score,
                    "failure_reasons": [
                        {"scorer": sr.scorer_name, "reason": sr.failure_reason}
                        for sr in tc.scorer_results if not sr.passed
                    ]
                }
                for tc in run_result.failed_tests
            ],
            "threshold_violations": run_result.threshold_violations,
            "duration_seconds": run_result.duration_seconds
        }
        
        # Write full report
        full_path = self.output_dir / "latest.json"
        with open(full_path, 'w') as f:
            json.dump(full_summary, f, indent=2)
        
        # Build simplified summary for GitHub Actions
        simple_summary = {
            "overall_score": run_result.overall_score,
            "passed_tests": run_result.passed_tests,
            "total_tests": run_result.total_tests,
            "scores": run_result.scores_by_dimension,
            "diff": {}  # Empty for now, will be populated by comparison logic
        }
        
        # Write summary.json
        summary_path = self.output_dir / "summary.json"
        with open(summary_path, 'w') as f:
            json.dump(simple_summary, f, indent=2)
        
        return str(full_path)
