"""
ResponseScorer: Validates response content.

Logic:
- Check all phrases in expected_response_contains are present (case-insensitive substring)
- Check no phrases in expected_response_excludes are present
- Partial scoring: 1.0 / N for each required phrase present
- If any excluded phrase present: score=0.0 (overrides partial credit)
- passed=True only if all required present AND no excluded present
"""

from .base import BaseScorer, ScorerResult


class ResponseScorer(BaseScorer):
    """
    Validates response content (required phrases, excluded phrases).
    
    Awards partial credit for required phrases.
    Excluded phrases override partial credit (score becomes 0.0).
    """
    
    async def score(
        self,
        test_case,  # TestCase
        agent_output,  # AgentOutput
    ) -> ScorerResult:
        """
        Score response content.
        
        Returns:
            ScorerResult with partial credit for required phrases,
            0.0 if any excluded phrase present.
        """
        # TODO: implement
        # - Check if expected_response_contains is set
        # - For each required phrase: check if present (case-insensitive)
        # - Calculate partial score: N_present / N_required
        # - Check if expected_response_excludes is set
        # - For each excluded phrase: check if present
        # - If any excluded present: override score to 0.0
        # - Return ScorerResult
        
        raise NotImplementedError("ResponseScorer.score() not yet implemented")
