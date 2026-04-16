"""
IntentScorer: Compares expected_intent to classified_intent.

Logic:
- If expected_intent is None: skip (return passed=True, score=1.0)
- If classified_intent matches expected_intent (case-insensitive): passed=True, score=1.0
- Else: passed=False, score=0.0, failure_reason includes expected vs actual
"""

from .base import BaseScorer, ScorerResult


class IntentScorer(BaseScorer):
    """
    Validates intent classification accuracy.
    
    Compares test_case.expected_intent to agent_output.classified_intent.
    """
    
    async def score(
        self,
        test_case,  # TestCase
        agent_output,  # AgentOutput
    ) -> ScorerResult:
        """
        Score intent classification.
        
        Returns:
            ScorerResult with passed=True if intent matches or no expectation.
        """
        # TODO: implement
        # - Check if expected_intent is None (skip if so)
        # - Compare expected_intent to classified_intent (case-insensitive)
        # - Return ScorerResult
        
        raise NotImplementedError("IntentScorer.score() not yet implemented")
