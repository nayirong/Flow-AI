"""
CLI entry point for the evaluation pipeline.

Usage:
    python -m engine.tests.eval.run_eval [options]

Examples:
    # Run all tests
    python -m engine.tests.eval.run_eval

    # Run for specific client
    python -m engine.tests.eval.run_eval --client hey-aircon

    # Dry-run (load test cases without executing)
    python -m engine.tests.eval.run_eval --dry-run

    # Save as baseline
    python -m engine.tests.eval.run_eval --baseline --save-baseline

    # Compare to baseline
    python -m engine.tests.eval.run_eval --compare-baseline
"""

import argparse
import asyncio
import sys
from pathlib import Path


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Flow AI Evaluation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Filters
    parser.add_argument(
        "--client",
        type=str,
        help="Filter test cases by client ID (default: all)",
    )
    parser.add_argument(
        "--category",
        type=str,
        choices=["intent", "tool_use", "escalation", "safety", "persona", "multi_turn", "context_engineering"],
        help="Filter by category",
    )
    parser.add_argument(
        "--priority",
        type=str,
        choices=["critical", "high", "medium", "low"],
        help="Filter by priority",
    )
    parser.add_argument(
        "--tags",
        type=str,
        help="Filter by tags (comma-separated)",
    )
    parser.add_argument(
        "--test-name",
        type=str,
        help="Run a single test case by name",
    )
    
    # Execution modes
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and validate test cases without executing",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Mark this run as a baseline candidate",
    )
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Lock this run as the official baseline",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare results to locked baseline",
    )
    parser.add_argument(
        "--compare-days",
        type=int,
        default=7,
        help="Compare to N-day rolling average (default: 7)",
    )
    
    # Reporting
    parser.add_argument(
        "--report-format",
        type=str,
        choices=["console", "html", "json", "all"],
        default="console",
        help="Report format (default: console)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./eval_reports",
        help="Output directory for reports (default: ./eval_reports)",
    )
    
    # Execution settings
    parser.add_argument(
        "--parallel",
        type=int,
        default=5,
        help="Concurrent agent executions (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-test-case timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose logging",
    )
    
    return parser.parse_args()


def main() -> int:
    """
    Main entry point.
    
    Returns:
        0 on success, 1 on threshold violation, 2 on fatal error.
    """
    args = parse_args()
    
    # TODO: implement
    # - Load threshold config
    # - Initialize EvalRunner with all dependencies
    # - Run evaluation
    # - Generate reports
    # - Check thresholds
    # - Return appropriate exit code
    
    print("Evaluation pipeline CLI - TODO: implement")
    print(f"Args: {args}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
