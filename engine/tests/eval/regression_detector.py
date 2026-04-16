"""
RegressionDetector: Compares current run to baseline/rolling average.

Triggers alerts when:
- Any dimension drops >5% vs N-day rolling average
- Reference test fails
- Safety test fails (always)
- Critical test fails
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from .models import RunResult, AlertPayload, ThresholdConfig


logger = logging.getLogger(__name__)


class RegressionDetector:
    """
    Detects regressions by comparing run results to historical data.
    
    Comparison modes:
    - Rolling average (default: 7-day)
    - Locked baseline
    - Previous run
    """
    
    def __init__(
        self,
        eval_supabase_client,  # AsyncClient
        threshold_config: ThresholdConfig,
        notifier: Optional[object] = None,  # BaseNotifier | None
    ):
        """Initialize with database client and threshold config."""
        self.eval_supabase_client = eval_supabase_client
        self.threshold_config = threshold_config
        self.notifier = notifier
    
    async def detect_and_alert(
        self,
        run_result: RunResult,
        environment: str = "ci",
    ) -> list[AlertPayload]:
        """
        Compare run_result to 7-day rolling average and trigger alerts.
        
        Returns:
            List of AlertPayload objects that were triggered.
        """
        alerts = []
        
        try:
            # Check each dimension for regressions
            for dimension, current_score in run_result.scores_by_dimension.items():
                # Get 7-day average
                avg_score = await self._get_7day_average(dimension, None)
                
                # Safety dimension: always alert if score < 1.0
                if dimension == "safety" and current_score < 1.0:
                    alert = AlertPayload(
                        run_id=run_result.run_id,
                        environment=environment,
                        client_id=None,
                        alert_type="safety_failure",
                        dimension=dimension,
                        score_before=avg_score,
                        score_after=current_score,
                        failing_tests=[tc.test_case.test_name for tc in run_result.failed_tests if any(sr.scorer_name == "safety" and not sr.passed for sr in tc.scorer_results)],
                        message=f"Safety failure detected: score={current_score:.2f}"
                    )
                    alerts.append(alert)
                    await self._write_alert(alert, False)
                    if self.notifier:
                        sent = await self.notifier.send_alert(alert)
                        await self._write_alert(alert, sent)
                    continue
                
                # Regression check: compare to 7-day average
                if avg_score is not None:
                    delta = avg_score - current_score
                    if delta > self.threshold_config.regression_alert_delta:
                        alert = AlertPayload(
                            run_id=run_result.run_id,
                            environment=environment,
                            client_id=None,
                            alert_type="regression",
                            dimension=dimension,
                            score_before=avg_score,
                            score_after=current_score,
                            failing_tests=[tc.test_case.test_name for tc in run_result.failed_tests],
                            message=f"Regression detected in {dimension}: {avg_score:.2f} → {current_score:.2f} (-{delta*100:.1f}%)"
                        )
                        alerts.append(alert)
                        telegram_sent = False
                        if self.notifier:
                            telegram_sent = await self.notifier.send_alert(alert)
                        await self._write_alert(alert, telegram_sent)
            
            return alerts
        
        except Exception as e:
            logger.error(f"RegressionDetector.detect_and_alert() failed: {e}")
            return alerts
    
    async def _get_7day_average(self, dimension: str, client_id: Optional[str] = None) -> Optional[float]:
        """
        Query eval_results table for 7-day rolling average score for a dimension.
        Returns None if insufficient data (< 5 results).
        """
        try:
            # TODO: Implement actual Supabase query
            # For now, return None (no historical data)
            # This will be implemented when Supabase schema is ready
            
            # Placeholder implementation
            return None
        
        except Exception as e:
            logger.error(f"_get_7day_average() failed: {e}")
            return None
    
    async def _write_alert(self, alert: AlertPayload, telegram_sent: bool) -> None:
        """Write alert to Supabase eval_alerts table."""
        try:
            # TODO: Implement actual Supabase write
            # For now, just log
            logger.info(f"Alert written: {alert.alert_type} - {alert.dimension} - telegram_sent={telegram_sent}")
        
        except Exception as e:
            logger.error(f"_write_alert() failed: {e}")
