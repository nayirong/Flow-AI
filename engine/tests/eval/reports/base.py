"""Base reporter class (stub)."""


class BaseReporter:
    """Base class for all reporters."""
    
    async def report(self, run_result):
        """Generate report from run result."""
        raise NotImplementedError()
