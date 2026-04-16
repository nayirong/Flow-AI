"""
EvalRunner: Orchestrates full evaluation run.

Flow:
    1. Load test cases (via TestCaseLoader)
    2. Execute agent for each test case (via AgentExecutor)
    3. Score output (via scorers)
    4. Store results (via ResultStore)
    5. Generate reports (via reporters)
    6. Detect regressions and send alerts (via RegressionDetector + AlertDispatcher)
"""

import asyncio
import time
import logging
from typing import List

from .models import RunResult, TestCaseResult, ScorerResult, TestCase, AgentOutput


logger = logging.getLogger(__name__)


class EvalRunner:
    """
    Orchestrator for evaluation runs.
    
    Responsibilities:
    - Execute all test cases with parallelism limit
    - Aggregate results from all scorers
    - Coordinate reporting and alerting
    - Enforce error isolation (single test failure does not crash run)
    """
    
    def __init__(
        self,
        loader,  # TestCaseLoader
        executor,  # AgentExecutor
        scorers: List,  # list[BaseScorer]
        result_store,  # ResultStore
        reporters: List,  # list[BaseReporter]
        alert_dispatcher,  # AlertDispatcher | None
        threshold_config,  # ThresholdConfig
        run_metadata,  # RunMetadata
        parallel_limit: int = 5,
    ):
        """Initialize runner with all dependencies."""
        self.loader = loader
        self.executor = executor
        self.scorers = scorers
        self.result_store = result_store
        self.reporters = reporters
        self.alert_dispatcher = alert_dispatcher
        self.threshold_config = threshold_config
        self.run_metadata = run_metadata
        self.parallel_limit = parallel_limit
        self.semaphore = asyncio.Semaphore(parallel_limit)
    
    async def run(
        self,
        client_id: str = None,
        category: str = None,
        priority: str = None,
        tags: List[str] = None,
        test_name: str = None,
    ):  # -> RunResult
        """
        Execute full eval run.
        
        Returns:
            RunResult containing overall pass rate, dimension scores,
            failed tests, threshold violations.
        """
        try:
            start_time = time.time()
            
            # 1. Load test cases
            logger.info("Loading test cases...")
            test_cases = await self.loader.load(
                client_id=client_id,
                category=category,
                priority=priority,
                tags=tags,
                test_name=test_name
            )
            logger.info(f"Loaded {len(test_cases)} test cases")
            
            if not test_cases:
                logger.warning("No test cases loaded")
                return RunResult(
                    run_id=self.run_metadata.run_id,
                    run_metadata=self.run_metadata,
                    total_tests=0,
                    passed_tests=0,
                    overall_score=0.0,
                    scores_by_dimension={},
                    scores_by_client={},
                    failed_tests=[],
                    threshold_violations=[],
                    duration_seconds=0.0
                )
            
            # 2. Execute all test cases in parallel
            logger.info(f"Executing {len(test_cases)} test cases with parallelism={self.parallel_limit}...")
            results = await self._execute_test_cases(test_cases)
            
            # 3. Aggregate results
            passed_tests = sum(1 for r in results if r.overall_passed)
            failed_results = [r for r in results if not r.overall_passed]
            
            # Calculate overall score
            overall_score = sum(r.overall_score for r in results) / len(results) if results else 0.0
            
            # Calculate dimension scores
            scores_by_dimension = self._aggregate_dimension_scores(results)
            
            # Calculate client scores
            scores_by_client = self._aggregate_client_scores(results)
            
            # Check threshold violations
            threshold_violations = self._check_thresholds(scores_by_dimension)
            
            duration = time.time() - start_time
            
            run_result = RunResult(
                run_id=self.run_metadata.run_id,
                run_metadata=self.run_metadata,
                total_tests=len(results),
                passed_tests=passed_tests,
                overall_score=overall_score,
                scores_by_dimension=scores_by_dimension,
                scores_by_client=scores_by_client,
                failed_tests=failed_results,
                threshold_violations=threshold_violations,
                duration_seconds=duration
            )
            
            # 4. Store results
            if self.result_store:
                logger.info("Storing results...")
                await self.result_store.write_results(results)
            
            # 5. Generate reports
            logger.info("Generating reports...")
            for reporter in self.reporters:
                try:
                    await reporter.report(run_result)
                except Exception as e:
                    logger.error(f"Reporter {reporter.__class__.__name__} failed: {e}")
            
            # 6. Detect regressions and alert
            if self.alert_dispatcher:
                logger.info("Detecting regressions...")
                try:
                    await self.alert_dispatcher.detect_and_alert(run_result)
                except Exception as e:
                    logger.error(f"Alert dispatcher failed: {e}")
            
            logger.info(f"Eval run complete: {passed_tests}/{len(results)} passed, score={overall_score:.2f}")
            return run_result
        
        except Exception as e:
            logger.error(f"EvalRunner.run() failed: {e}")
            raise
    
    async def _execute_test_cases(self, test_cases: List[TestCase]) -> List[TestCaseResult]:
        """
        Execute all test cases with parallelism limit.
        Uses asyncio.Semaphore to limit concurrent agent executions.
        """
        tasks = [self._execute_single_test(tc) for tc in test_cases]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results
    
    async def _execute_single_test(self, test_case: TestCase) -> TestCaseResult:
        """
        Execute one test case: agent → scorers → aggregate.
        Error isolation: catches all exceptions, returns error result.
        """
        async with self.semaphore:
            try:
                # Execute agent
                agent_output = await self.executor.execute(test_case)
                
                # Score with all scorers
                scorer_results = []
                for scorer in self.scorers:
                    try:
                        result = await scorer.score(test_case, agent_output)
                        scorer_results.append(result)
                    except Exception as e:
                        logger.error(f"Scorer {scorer.__class__.__name__} crashed: {e}")
                        scorer_results.append(ScorerResult(
                            scorer_name=scorer.__class__.__name__,
                            passed=False,
                            score=0.0,
                            failure_reason=f"scorer_crashed: {str(e)}"
                        ))
                
                # Aggregate
                overall_passed = all(r.passed for r in scorer_results)
                overall_score = sum(r.score for r in scorer_results) / len(scorer_results) if scorer_results else 0.0
                
                return TestCaseResult(
                    run_id=self.run_metadata.run_id,
                    test_case=test_case,
                    agent_output=agent_output,
                    scorer_results=scorer_results,
                    overall_passed=overall_passed,
                    overall_score=overall_score,
                    langfuse_trace_id=None,
                    run_metadata=self.run_metadata
                )
            
            except Exception as e:
                logger.error(f"Test case {test_case.test_name} failed: {e}")
                # Return error result
                return TestCaseResult(
                    run_id=self.run_metadata.run_id,
                    test_case=test_case,
                    agent_output=AgentOutput(
                        response_text="",
                        error=f"execution_failed: {str(e)}"
                    ),
                    scorer_results=[],
                    overall_passed=False,
                    overall_score=0.0,
                    langfuse_trace_id=None,
                    run_metadata=self.run_metadata
                )
    
    def _aggregate_dimension_scores(self, results: List[TestCaseResult]) -> dict[str, float]:
        """Aggregate scores by dimension (category)."""
        dimension_scores = {}
        dimension_results = {}
        
        for result in results:
            category = result.test_case.category
            if category not in dimension_results:
                dimension_results[category] = []
            dimension_results[category].append(result.overall_score)
        
        for dimension, scores in dimension_results.items():
            dimension_scores[dimension] = sum(scores) / len(scores) if scores else 0.0
        
        return dimension_scores
    
    def _aggregate_client_scores(self, results: List[TestCaseResult]) -> dict[str, float]:
        """Aggregate scores by client_id."""
        client_scores = {}
        client_results = {}
        
        for result in results:
            client_id = result.test_case.client_id
            if client_id not in client_results:
                client_results[client_id] = []
            client_results[client_id].append(result.overall_score)
        
        for client_id, scores in client_results.items():
            client_scores[client_id] = sum(scores) / len(scores) if scores else 0.0
        
        return client_scores
    
    def _check_thresholds(self, scores_by_dimension: dict[str, float]) -> List[str]:
        """Check if any dimensions violate thresholds."""
        violations = []
        
        # Map dimension names to threshold config
        threshold_map = {
            "safety": self.threshold_config.safety,
            "tool_use": self.threshold_config.tool_use_critical,
            "escalation": self.threshold_config.escalation,
            "intent": self.threshold_config.intent,
        }
        
        for dimension, threshold in threshold_map.items():
            if dimension in scores_by_dimension:
                score = scores_by_dimension[dimension]
                if score < threshold.min_score and threshold.blocking:
                    violations.append(dimension)
        
        # Check overall threshold
        overall_score = sum(scores_by_dimension.values()) / len(scores_by_dimension) if scores_by_dimension else 0.0
        if overall_score < self.threshold_config.overall.min_score and self.threshold_config.overall.blocking:
            violations.append("overall")
        
        return violations
