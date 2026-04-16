"""
EscalationScorer: Validates escalation gate triggered correctly.

Logic:
- If expected_escalation is None: skip (return passed=True, score=1.0)
- If expected_escalation == agent_output.escalation_triggered: passed=True, score=1.0
- Else: passed=False, score=0.0, failure_reason includes expected vs actual
"""

from .base import BaseScorer, ScorerResult


class EscalationScorer(BaseScorer):
    """
    Validates escalation gate correctness.
    
    Compares test_case.expected_escalation (bool) to agent_output.escalation_triggered (bool).
    """
    
    async def score(
        self,
        test_case,  # TestCase
        agent_output,  # AgentOutput
    ) -> ScorerResult:
        """
        Score escalation gate behavior.
        
        Returns:
            ScorerResult with passed=True if boolean match or no expectation.
        """
        # TODO: implement
        # - Check if expected_escalation is None (skip if so)
        # - Compare expected_escalation to escalation_triggered (boolean equality)
        # - Return ScorerResult
        
        raise NotImplementedError("EscalationScorer.score() not yet implemented")
