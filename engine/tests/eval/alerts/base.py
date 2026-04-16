"""
BaseNotifier: Abstract base class for alert notifiers.

All notifiers must implement send_alert() and never raise exceptions.
"""

from abc import ABC, abstractmethod
from ..models import AlertPayload


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
