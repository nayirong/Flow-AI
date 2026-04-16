"""
BaseScorer: Abstract base class for all scorers.

All scorers must implement the score() method and return a ScorerResult.
"""

from abc import ABC, abstractmethod
from ..models import ScorerResult, TestCase, AgentOutput


class BaseScorer(ABC):
    """
    Abstract base class for all scorers.
    
    All scorers must implement the score() method.
    Scorers must never raise exceptions — catch all errors and return error result.
    """
    
    @abstractmethod
    async def score(
        self,
        test_case,  # TestCase
        agent_output,  # AgentOutput
    ) -> ScorerResult:
        """
        Evaluate agent output against expected behavior.
        
        Args:
            test_case: TestCase object with expected behavior
            agent_output: AgentOutput from agent execution
        
        Returns:
            ScorerResult with passed, score, failure_reason.
        
        Must never raise — catch all exceptions, return error result.
        """
        pass
