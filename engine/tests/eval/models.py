"""
Pydantic models for the evaluation pipeline.

All models use Pydantic v2.
"""

from pydantic import BaseModel, field_validator
from typing import Literal, Optional
from datetime import datetime


class TestCase(BaseModel):
    """Test case specification for agent evaluation."""
    
    id: Optional[int] = None
    client_id: str
    category: Literal["intent", "tool_use", "escalation", "safety", "persona", "multi_turn", "context_engineering"]
    test_name: str
    input_message: str
    conversation_history: list[dict] = []
    expected_intent: Optional[str] = None
    expected_tool: Optional[str] = None
    expected_tool_params: Optional[dict] = None
    expected_escalation: Optional[bool] = None
    expected_response_contains: Optional[list[str]] = None
    expected_response_excludes: Optional[list[str]] = None
    safety_check: Optional[str] = None
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    reference_test: bool = False
    tags: list[str] = []
    enabled: bool = True
    metadata: dict = {}


class AgentOutput(BaseModel):
    """Output captured from agent execution."""
    
    response_text: str
    tool_called: Optional[str] = None
    tool_params: Optional[dict] = None
    escalation_triggered: bool = False
    classified_intent: Optional[str] = None
    execution_time_ms: int = 0
    raw_response: dict = {}
    error: Optional[str] = None  # set if execution failed


class ScorerResult(BaseModel):
    """Result from a single scorer."""
    
    scorer_name: str
    passed: bool
    score: float
    failure_reason: Optional[str] = None
    metadata: dict = {}

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"score must be 0.0–1.0, got {v}")
        return v


class RunMetadata(BaseModel):
    """Metadata about an evaluation run."""
    
    run_id: str
    git_commit: str
    branch: str
    llm_model: str
    llm_version: str
    prompt_version: str
    triggered_by: Literal["ci_pr", "ci_scheduled", "manual_cli"]
    timestamp: datetime


class TestCaseResult(BaseModel):
    """Result from evaluating a single test case."""
    
    run_id: str
    test_case: TestCase
    agent_output: AgentOutput
    scorer_results: list[ScorerResult]
    overall_passed: bool
    overall_score: float
    langfuse_trace_id: Optional[str] = None
    run_metadata: RunMetadata


class DimensionThreshold(BaseModel):
    """Threshold configuration for a dimension."""
    
    min_score: float
    blocking: bool


class ThresholdConfig(BaseModel):
    """Complete threshold configuration."""
    
    safety: DimensionThreshold
    tool_use_critical: DimensionThreshold
    escalation: DimensionThreshold
    intent: DimensionThreshold
    overall: DimensionThreshold
    regression_alert_delta: float  # e.g. 0.05 for 5%


class AlertPayload(BaseModel):
    """Alert notification payload."""
    
    run_id: str
    environment: str
    client_id: Optional[str]
    alert_type: Literal["regression", "safety_failure", "critical_failure", "baseline_regression"]
    dimension: Optional[str] = None
    score_before: Optional[float] = None
    score_after: Optional[float] = None
    failing_tests: list[str] = []
    message: str
    report_url: Optional[str] = None
    trace_url: Optional[str] = None


class RunResult(BaseModel):
    """Aggregate result from a full evaluation run."""
    
    run_id: str
    run_metadata: RunMetadata
    total_tests: int
    passed_tests: int
    overall_score: float
    scores_by_dimension: dict[str, float]
    scores_by_client: dict[str, float]
    failed_tests: list[TestCaseResult]
    threshold_violations: list[str]  # dimension names that violated thresholds
    duration_seconds: float
