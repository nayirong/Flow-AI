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


class JsonReporter:
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
    
    async def report(self, run_result) -> str:  # run_result: RunResult
        """
        Write JSON summary file.
        
        Returns:
            Path to generated JSON file (eval_summary.json).
        """
        # TODO: implement
        # - Build summary dict from run_result
        # - Write to output_dir/eval_summary.json
        # - Return file path
        
        raise NotImplementedError("JsonReporter.report() not yet implemented")
