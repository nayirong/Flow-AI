"""
PersonaScorer: LLM-as-judge evaluation of tone and persona adherence.

**Phase 2 only** — requires Langfuse integration.

This is a placeholder stub for Phase 1.
"""

from .base import BaseScorer, ScorerResult


class PersonaScorer(BaseScorer):
    """
    LLM-as-judge scorer for tone, helpfulness, persona adherence.
    
    **Phase 2 implementation** — currently returns skip/pass for all cases.
    """
    
    def __init__(self, langfuse_client=None):
        """Initialize with Langfuse client (Phase 2)."""
        self.langfuse_client = langfuse_client
    
    async def score(
        self,
        test_case,  # TestCase
        agent_output,  # AgentOutput
    ) -> ScorerResult:
        """
        Score persona adherence.
        
        Phase 1: Always returns passed=True, score=1.0 (stub).
        Phase 2: Will use LLM-as-judge with persona guidelines.
        
        Returns:
            ScorerResult (stub in Phase 1).
        """
        # TODO: Phase 2 implementation
        # - Load persona guidelines from client config
        # - Construct LLM-as-judge prompt
        # - Call Claude with response evaluation task
        # - Parse score (0.0–1.0) and justification
        # - Link to Langfuse trace
        # - Return ScorerResult with score + justification in metadata
        
        # Phase 1 stub: always pass
        return ScorerResult(
            scorer_name="persona",
            passed=True,
            score=1.0,
            failure_reason=None,
            metadata={"phase": "stub", "note": "PersonaScorer not implemented in Phase 1"},
        )
