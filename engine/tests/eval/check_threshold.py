"""
Threshold checker utility.

Reads eval_summary.json, checks if thresholds are met, exits with appropriate code.

Used by GitHub Actions to gate PR merges.
"""

import argparse
import json
import sys
from pathlib import Path


def check_thresholds(summary_path: str) -> int:
    """
    Check if thresholds are met.
    
    Args:
        summary_path: Path to eval_summary.json
    
    Returns:
        0 if thresholds met, 1 if violated
    """
    # TODO: implement
    # - Load JSON summary
    # - Check thresholds_met field
    # - Print violations if any
    # - Return 0 or 1
    
    print(f"Checking thresholds from {summary_path}")
    print("TODO: implement threshold checking")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Check eval thresholds")
    parser.add_argument(
        "--summary",
        type=str,
        required=True,
        help="Path to eval_summary.json",
    )
    
    args = parser.parse_args()
    return check_thresholds(args.summary)


if __name__ == "__main__":
    sys.exit(main())
