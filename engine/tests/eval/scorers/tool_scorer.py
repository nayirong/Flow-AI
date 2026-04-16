"""
ToolScorer: Evaluates tool selection and parameter correctness.

Scoring logic:
- Tool name match: 0.5 points
- Tool params match (JSON equality): 0.5 points
- passed=True only if both match (score=1.0)
- score=0.5 for correct tool + wrong params (partial credit)
- score=0.0 for wrong tool
"""

from .base import BaseScorer, ScorerResult


class ToolScorer(BaseScorer):
    """
    Validates tool selection and parameter correctness.
    
    Awards partial credit for correct tool with wrong parameters.
    """
    
    async def score(
        self,
        test_case,  # TestCase
        agent_output,  # AgentOutput
    ) -> ScorerResult:
        """
        Score tool use.
        
        Returns:
            ScorerResult with score 0.0/0.5/1.0 based on tool + params match.
        """
        # TODO: implement
        # - Check if expected_tool is None (skip if so)
        # - Compare tool name: award 0.5 if match
        # - Compare tool params: award additional 0.5 if match (JSON deep equality)
        # - Handle dynamic params ({{ ... }}) gracefully
        # - Return ScorerResult
        
        raise NotImplementedError("ToolScorer.score() not yet implemented")
