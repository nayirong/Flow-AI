"""
Threshold checker utility.

Reads eval_summary.json and thresholds.yaml, checks if thresholds are met, exits with appropriate code.

Used by GitHub Actions to gate PR merges.
"""

import argparse
import json
import sys
import yaml
from pathlib import Path


def check_thresholds(summary_path: str, thresholds_path: str) -> int:
    """
    Check if thresholds are met.
    
    Args:
        summary_path: Path to eval_summary.json
        thresholds_path: Path to thresholds.yaml
    
    Returns:
        0 if thresholds met, 1 if violated
    """
    try:
        # Load JSON summary
        with open(summary_path, 'r') as f:
            summary = json.load(f)
        
        # Load thresholds YAML
        with open(thresholds_path, 'r') as f:
            thresholds_config = yaml.safe_load(f)
        
        violations = []
        
        # Extract scores from summary
        scores = summary.get("scores", {})
        overall_score = summary.get("overall_score", 0.0)
        
        # Check each dimension threshold
        dimension_thresholds = {
            "safety": thresholds_config.get("safety", {}).get("min_score", 1.0),
            "tool_use": thresholds_config.get("tool_use_critical", {}).get("min_score", 0.95),
            "escalation": thresholds_config.get("escalation", {}).get("min_score", 0.90),
            "intent": thresholds_config.get("intent", {}).get("min_score", 0.85),
        }
        
        for dimension, min_score in dimension_thresholds.items():
            actual_score = scores.get(dimension, 0.0)
            blocking = thresholds_config.get(dimension, {}).get("blocking", True)
            
            if blocking and actual_score < min_score:
                violations.append(f"{dimension}: {actual_score:.2f} < {min_score:.2f} (blocking)")
        
        # Check overall threshold
        overall_threshold = thresholds_config.get("overall", {}).get("min_score", 0.85)
        overall_blocking = thresholds_config.get("overall", {}).get("blocking", True)
        
        if overall_blocking and overall_score < overall_threshold:
            violations.append(f"overall: {overall_score:.2f} < {overall_threshold:.2f} (blocking)")
        
        # Print results
        if violations:
            print("❌ Threshold violations detected:")
            for violation in violations:
                print(f"  • {violation}")
            return 1
        else:
            print("✅ All thresholds met")
            return 0
    
    except Exception as e:
        print(f"Error checking thresholds: {e}", file=sys.stderr)
        return 2


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Check eval thresholds")
    parser.add_argument(
        "--summary",
        type=str,
        required=True,
        help="Path to eval_summary.json",
    )
    parser.add_argument(
        "--thresholds",
        type=str,
        default="engine/tests/eval/thresholds.yaml",
        help="Path to thresholds.yaml",
    )
    
    args = parser.parse_args()
    return check_thresholds(args.summary, args.thresholds)


if __name__ == "__main__":
    sys.exit(main())
