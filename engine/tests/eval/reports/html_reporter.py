"""
HtmlReporter: Generates static HTML report artifact.

Features:
- Responsive, mobile-friendly design
- Summary cards (overall pass rate, dimension scores)
- Bar charts (dimension scores vs thresholds) using Chart.js or inline SVG
- Per-client breakdown table
- Full test results table (sortable, filterable)
- Trend comparison (vs main, vs baseline)
- Links to Langfuse traces (Phase 2)
- No external dependencies (inline CSS/JS)
"""

from pathlib import Path


class HtmlReporter:
    """
    Generates HTML report artifact.
    
    Uses Jinja2 template engine.
    """
    
    def __init__(self, output_dir: str):
        """
        Initialize with output directory path.
        
        Args:
            output_dir: Directory to write HTML file
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def report(self, run_result) -> str:  # run_result: RunResult
        """
        Generate HTML report file.
        
        Returns:
            Path to generated HTML file.
        
        Structure:
        - Metadata section (run_id, commit, branch, model, timestamp)
        - Summary cards (overall pass rate, dimension scores)
        - Bar chart (dimension scores vs thresholds)
        - Per-client breakdown table (if multiple clients)
        - Full test results table (sortable, filterable)
        - Trend comparison section (vs main, vs baseline)
        - Links to Langfuse traces (Phase 2)
        
        Style: Responsive, mobile-friendly, no external dependencies.
        """
        # TODO: implement
        # - Load Jinja2 template from engine/tests/eval/templates/report.html.j2
        # - Render with run_result data
        # - Write to output_dir/eval_report_{run_id}.html
        # - Return file path
        
        raise NotImplementedError("HtmlReporter.report() not yet implemented")
