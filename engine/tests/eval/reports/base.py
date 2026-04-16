"""Base reporter class."""

from abc import ABC, abstractmethod
from ..models import RunResult


class BaseReporter(ABC):
    """Base class for all reporters."""
    
    @abstractmethod
    async def report(self, run_result: RunResult):
        """Generate report from run result."""
        pass
