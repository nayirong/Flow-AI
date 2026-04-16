"""
BaseScorer: Abstract base class for all scorers.

All scorers must implement the score() method and return a ScorerResult.
"""

from abc import ABC, abstractmethod
from typing import Optional


class ScorerResult:
    """
    Result from a single scorer.
    
    Attributes:
        scorer_name: Name of the scorer
        passed: Whether the test passed this scorer's criteria
        score: Numeric score between 0.0 and 1.0
        failure_reason: Human-readable explanation if failed
        metadata: Additional debugging info
    """
    
    def __init__(
        self,
        scorer_name: str,
        passed: bool,
        score: float,
        failure_reason: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Initialize scorer result."""
        self.scorer_name = scorer_name
        self.passed = passed
        self.score = score
        self.failure_reason = failure_reason
        self.metadata = metadata or {}
        
        # Validate score range
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Score must be between 0.0 and 1.0, got {score}")


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
