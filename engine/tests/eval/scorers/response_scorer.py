"""
ResponseScorer: Validates response content.

Logic:
- Check all phrases in expected_response_contains are present (case-insensitive substring)
- Check no phrases in expected_response_excludes are present
- Partial scoring: 1.0 / N for each required phrase present
- If any excluded phrase present: score=0.0 (overrides partial credit)
- passed=True only if all required present AND no excluded present
"""

from .base import BaseScorer
from ..models import ScorerResult, TestCase, AgentOutput


class ResponseScorer(BaseScorer):
    """
    Validates response content (required phrases, excluded phrases).
    
    Awards partial credit for required phrases.
    Excluded phrases override partial credit (score becomes 0.0).
    """
    
    async def score(
        self,
        test_case: TestCase,
        agent_output: AgentOutput,
    ) -> ScorerResult:
        """
        Score response content.
        
        Returns:
            ScorerResult with partial credit for required phrases,
            0.0 if any excluded phrase present.
        """
        try:
            response_text_lower = agent_output.response_text.lower()
            
            # Check if we have any expectations
            has_contains = test_case.expected_response_contains is not None and len(test_case.expected_response_contains) > 0
            has_excludes = test_case.expected_response_excludes is not None and len(test_case.expected_response_excludes) > 0
            
            if not has_contains and not has_excludes:
                # No expectations, skip
                return ScorerResult(
                    scorer_name="response",
                    passed=True,
                    score=1.0,
                    failure_reason=None,
                    metadata={"skipped": "no_expected_response_conditions"}
                )
            
            score = 1.0
            missing_phrases = []
            excluded_found = []
            
            # Check required phrases
            if has_contains:
                present_count = 0
                total_required = len(test_case.expected_response_contains)
                
                for phrase in test_case.expected_response_contains:
                    if phrase.lower() in response_text_lower:
                        present_count += 1
                    else:
                        missing_phrases.append(phrase)
                
                score = present_count / total_required if total_required > 0 else 1.0
            
            # Check excluded phrases
            if has_excludes:
                for phrase in test_case.expected_response_excludes:
                    if phrase.lower() in response_text_lower:
                        excluded_found.append(phrase)
                
                # Any excluded phrase found: override score to 0.0
                if excluded_found:
                    score = 0.0
            
            # Determine pass/fail
            passed = (score == 1.0) and (len(excluded_found) == 0)
            
            # Build failure reason
            failure_parts = []
            if missing_phrases:
                failure_parts.append(f"Missing required phrases: {missing_phrases}")
            if excluded_found:
                failure_parts.append(f"Found excluded phrases: {excluded_found}")
            
            failure_reason = "; ".join(failure_parts) if failure_parts else None
            
            return ScorerResult(
                scorer_name="response",
                passed=passed,
                score=score,
                failure_reason=failure_reason,
                metadata={
                    "missing_phrases": missing_phrases,
                    "excluded_found": excluded_found
                }
            )
        
        except Exception as e:
            return ScorerResult(
                scorer_name="response",
                passed=False,
                score=0.0,
                failure_reason=f"scorer_error: {str(e)}",
                metadata={"exception": str(e)}
            )

