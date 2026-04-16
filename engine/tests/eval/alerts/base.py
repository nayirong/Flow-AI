"""
BaseNotifier: Abstract base class for alert notifiers.

All notifiers must implement send_alert() and never raise exceptions.
"""

from abc import ABC, abstractmethod
from typing import Optional


class AlertPayload:
    """
    Alert notification payload.
    
    Attributes:
        alert_type: Type of alert (regression | safety_failure | critical_failure | baseline_regression)
        run_id: Eval run identifier
        client_id: Client identifier (None for platform-wide alerts)
        dimension: Scoring dimension that triggered alert
        score_before: Previous score (baseline or rolling average)
        score_after: Current run score
        failed_tests: List of test names that failed
        github_actions_url: Link to GitHub Actions run
        langfuse_url: Link to Langfuse trace (Phase 2)
    """
    
    def __init__(
        self,
        alert_type: str,
        run_id: str,
        client_id: Optional[str] = None,
        dimension: Optional[str] = None,
        score_before: Optional[float] = None,
        score_after: Optional[float] = None,
        failed_tests: Optional[list] = None,
        github_actions_url: Optional[str] = None,
        langfuse_url: Optional[str] = None,
    ):
        """Initialize alert payload."""
        self.alert_type = alert_type
        self.run_id = run_id
        self.client_id = client_id
        self.dimension = dimension
        self.score_before = score_before
        self.score_after = score_after
        self.failed_tests = failed_tests or []
        self.github_actions_url = github_actions_url
        self.langfuse_url = langfuse_url


class BaseNotifier(ABC):
    """
    Abstract base class for all alert notifiers.
    
    All notifiers must implement send_alert() method.
    Must never raise — catch all exceptions, return False.
    """
    
    @abstractmethod
    async def send_alert(self, alert: AlertPayload) -> bool:
        """
        Send alert notification.
        
        Args:
            alert: AlertPayload with alert details
        
        Returns:
            True if send succeeded, False otherwise.
            Must never raise — catch all exceptions, return False.
        """
        pass
