"""
EscalationScorer: Validates escalation gate triggered correctly.

Logic:
- If expected_escalation is None: skip (return passed=True, score=1.0)
- If expected_escalation == agent_output.escalation_triggered: passed=True, score=1.0
- Else: passed=False, score=0.0, failure_reason includes expected vs actual
"""

from .base import BaseScorer
from ..models import ScorerResult, TestCase, AgentOutput


class EscalationScorer(BaseScorer):
    """
    Validates escalation gate correctness.
    
    Compares test_case.expected_escalation (bool) to agent_output.escalation_triggered (bool).
    """
    
    async def score(
        self,
        test_case: TestCase,
        agent_output: AgentOutput,
    ) -> ScorerResult:
        """
        Score escalation gate behavior.
        
        Returns:
            ScorerResult with passed=True if boolean match or no expectation.
        """
        try:
            # If no expected escalation, skip
            if test_case.expected_escalation is None:
                return ScorerResult(
                    scorer_name="escalation",
                    passed=True,
                    score=1.0,
                    failure_reason=None,
                    metadata={"skipped": "no_expected_escalation"}
                )
            
            # Compare boolean values
            if test_case.expected_escalation == agent_output.escalation_triggered:
                return ScorerResult(
                    scorer_name="escalation",
                    passed=True,
                    score=1.0,
                    failure_reason=None,
                    metadata={
                        "expected": test_case.expected_escalation,
                        "actual": agent_output.escalation_triggered
                    }
                )
            else:
                return ScorerResult(
                    scorer_name="escalation",
                    passed=False,
                    score=0.0,
                    failure_reason=f"Expected escalation={test_case.expected_escalation}, got escalation={agent_output.escalation_triggered}",
                    metadata={
                        "expected": test_case.expected_escalation,
                        "actual": agent_output.escalation_triggered
                    }
                )
        
        except Exception as e:
            return ScorerResult(
                scorer_name="escalation",
                passed=False,
                score=0.0,
                failure_reason=f"scorer_error: {str(e)}",
                metadata={"exception": str(e)}
            )

