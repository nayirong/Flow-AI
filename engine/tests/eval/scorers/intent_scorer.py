"""
IntentScorer: Compares expected_intent to classified_intent.

Logic:
- If expected_intent is None: skip (return passed=True, score=1.0)
- If classified_intent matches expected_intent (case-insensitive): passed=True, score=1.0
- Else: passed=False, score=0.0, failure_reason includes expected vs actual
"""

from .base import BaseScorer
from ..models import ScorerResult, TestCase, AgentOutput


class IntentScorer(BaseScorer):
    """
    Validates intent classification accuracy.
    
    Compares test_case.expected_intent to agent_output.classified_intent.
    """
    
    async def score(
        self,
        test_case: TestCase,
        agent_output: AgentOutput,
    ) -> ScorerResult:
        """
        Score intent classification.
        
        Returns:
            ScorerResult with passed=True if intent matches or no expectation.
        """
        try:
            # If no expected intent, skip
            if test_case.expected_intent is None:
                return ScorerResult(
                    scorer_name="intent",
                    passed=True,
                    score=1.0,
                    failure_reason=None,
                    metadata={"skipped": "no_expected_intent"}
                )
            
            # Compare case-insensitive
            expected = test_case.expected_intent.lower()
            actual = (agent_output.classified_intent or "").lower()
            
            if expected == actual:
                return ScorerResult(
                    scorer_name="intent",
                    passed=True,
                    score=1.0,
                    failure_reason=None,
                    metadata={"expected": test_case.expected_intent, "actual": agent_output.classified_intent}
                )
            else:
                return ScorerResult(
                    scorer_name="intent",
                    passed=False,
                    score=0.0,
                    failure_reason=f"Expected intent '{test_case.expected_intent}', got '{agent_output.classified_intent}'",
                    metadata={"expected": test_case.expected_intent, "actual": agent_output.classified_intent}
                )
        
        except Exception as e:
            return ScorerResult(
                scorer_name="intent",
                passed=False,
                score=0.0,
                failure_reason=f"scorer_error: {str(e)}",
                metadata={"exception": str(e)}
            )

