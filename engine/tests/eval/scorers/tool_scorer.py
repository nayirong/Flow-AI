"""
ToolScorer: Evaluates tool selection and parameter correctness.

Scoring logic:
- Tool name match: 0.5 points
- Tool params match (JSON equality): 0.5 points
- passed=True only if both match (score=1.0)
- score=0.5 for correct tool + wrong params (partial credit)
- score=0.0 for wrong tool
"""

from .base import BaseScorer
from ..models import ScorerResult, TestCase, AgentOutput


class ToolScorer(BaseScorer):
    """
    Validates tool selection and parameter correctness.
    
    Awards partial credit for correct tool with wrong parameters.
    """
    
    async def score(
        self,
        test_case: TestCase,
        agent_output: AgentOutput,
    ) -> ScorerResult:
        """
        Score tool use.
        
        Returns:
            ScorerResult with score 0.0/0.5/1.0 based on tool + params match.
        """
        try:
            # If no expected tool, skip
            if test_case.expected_tool is None:
                return ScorerResult(
                    scorer_name="tool",
                    passed=True,
                    score=1.0,
                    failure_reason=None,
                    metadata={"skipped": "no_expected_tool"}
                )
            
            score = 0.0
            tool_match = False
            params_match = False
            failure_parts = []
            
            # Check tool name match
            if agent_output.tool_called == test_case.expected_tool:
                score += 0.5
                tool_match = True
            else:
                failure_parts.append(f"Expected tool '{test_case.expected_tool}', got '{agent_output.tool_called}'")
            
            # Check params match if expected params are provided
            if test_case.expected_tool_params is not None and tool_match:
                # Skip dynamic param values (start with "{{ ")
                expected_params = {
                    k: v for k, v in test_case.expected_tool_params.items()
                    if not (isinstance(v, str) and v.startswith("{{ "))
                }
                
                actual_params = agent_output.tool_params or {}
                
                # Compare only non-dynamic keys
                if expected_params:
                    params_match = all(
                        actual_params.get(k) == v 
                        for k, v in expected_params.items()
                    )
                    
                    if params_match:
                        score += 0.5
                    else:
                        mismatch_keys = [
                            k for k, v in expected_params.items()
                            if actual_params.get(k) != v
                        ]
                        failure_parts.append(f"Params mismatch on keys: {mismatch_keys}")
                else:
                    # All params were dynamic, award full credit for params
                    score += 0.5
                    params_match = True
            elif test_case.expected_tool_params is None and tool_match:
                # No expected params specified, award param credit if tool matches
                score += 0.5
                params_match = True
            
            passed = tool_match and params_match
            failure_reason = "; ".join(failure_parts) if failure_parts else None
            
            return ScorerResult(
                scorer_name="tool",
                passed=passed,
                score=score,
                failure_reason=failure_reason,
                metadata={
                    "expected_tool": test_case.expected_tool,
                    "actual_tool": agent_output.tool_called,
                    "tool_match": tool_match,
                    "params_match": params_match
                }
            )
        
        except Exception as e:
            return ScorerResult(
                scorer_name="tool",
                passed=False,
                score=0.0,
                failure_reason=f"scorer_error: {str(e)}",
                metadata={"exception": str(e)}
            )

