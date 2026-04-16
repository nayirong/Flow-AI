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


class ConsoleReporter(BaseReporter):
    """
    Prints evaluation summary to console.
    
    Features:
    - Color support (optional, via colorama)
    - Table formatting
    - Emoji indicators
    """
    
    def __init__(self, use_color: bool = True):
        """
        Initialize with color preference.
        
        Args:
            use_color: Whether to use ANSI color codes
        """
        self.use_color = use_color
    
    async def report(self, run_result) -> None:  # run_result: RunResult
        """
        Print formatted table to stdout.
        
        Format:
        ╔════════════════════════════════════════╗
        ║   Flow AI Evaluation Summary           ║
        ╚════════════════════════════════════════╝
        
        Run ID: 2026-04-16T14:32:00Z-abc123
        Git Commit: abc123def
        Branch: feature/eval-pipeline
        LLM: claude-sonnet-4-6
        
        Overall Pass Rate: 88.0% (44/50) ✅
        
        Dimension Scores:
        ┌────────────────┬────────┬───────────┐
        │ Dimension      │ Score  │ Threshold │
        ├────────────────┼────────┼───────────┤
        │ Safety         │ 100.0% │  100.0%   │ ✅
        │ Tool Use       │  92.0% │   95.0%   │ ❌
        │ Escalation     │  90.0% │   90.0%   │ ✅
        │ Intent         │  88.0% │   85.0%   │ ✅
        └────────────────┴────────┴───────────┘
        
        Failed Tests (6):
        ❌ booking_happy_path_am_slot (tool_use)
           Expected tool: create_booking, got: check_calendar_availability
        ...
        
        Thresholds: ❌ NOT MET (tool_use below threshold)
        """
        # TODO: implement formatted console output
        raise NotImplementedError("ConsoleReporter.report() not yet implemented")


class BaseReporter:
    """Base class for reporters (stub for now)."""
    
    async def report(self, run_result):
        """Generate report from run result."""
        raise NotImplementedError()
