"""
AgentExecutor: Wraps existing agent runner to execute test cases.

Integrates with production agent code:
- engine.core.agent_runner.run_agent()
- engine.core.context_builder.build_system_message()
- engine.config.client_config.load_client_config()
- engine.core.tools (tool definitions and dispatch)
"""

import asyncio
import time


class AgentExecutor:
    """
    Executes agent for a single test case and captures output.
    
    Design:
    - Invokes agent_runner.run_agent() directly (not via HTTP)
    - Captures: response_text, tool_called, tool_params, escalation_triggered,
      classified_intent, execution_time_ms
    - Never raises — returns AgentOutput with error field on failure
    """
    
    def __init__(
        self,
        eval_supabase_client,  # AsyncClient
        anthropic_client,  # Anthropic
        timeout_seconds: int = 30,
    ):
        """Initialize executor with clients."""
        self.eval_supabase_client = eval_supabase_client
        self.anthropic_client = anthropic_client
        self.timeout_seconds = timeout_seconds
    
    async def execute(
        self,
        test_case,  # TestCase
    ):  # -> AgentOutput
        """
        Execute agent for a single test case.
        
        Args:
            test_case: TestCase object with input_message and metadata.
        
        Returns:
            AgentOutput with response, tools, intent, timing.
            On error: returns AgentOutput with error field set.
        """
        # TODO: implement
        # - Load client config via _load_client_config()
        # - Build context via _build_context()
        # - Invoke agent via _invoke_agent() with timeout
        # - Extract tool calls and intent
        # - Return AgentOutput
        # - Catch all exceptions, return AgentOutput(error=...)
        
        raise NotImplementedError("AgentExecutor.execute() not yet implemented")
    
    async def _load_client_config(
        self,
        client_id: str,
    ):  # -> ClientConfig
        """Load client config (reuses engine/config/client_config.py)."""
        # TODO: implement
        # - Import and call load_client_config(client_id)
        # - Return ClientConfig
        raise NotImplementedError()
    
    async def _build_context(
        self,
        client_config,  # ClientConfig
        conversation_history: list,
    ) -> str:
        """Call engine/core/context_builder.build_system_message()."""
        # TODO: implement
        # - Import and call context_builder.build_system_message()
        # - Return system_message string
        raise NotImplementedError()
    
    async def _invoke_agent(
        self,
        system_message: str,
        conversation_history: list,
        current_message: str,
        tools: list,
    ) -> dict:
        """
        Call engine/core/agent_runner.run_agent().
        
        Wraps with timeout (asyncio.wait_for).
        Captures tool calls from agent response.
        """
        # TODO: implement
        # - Import agent_runner.run_agent()
        # - Wrap with asyncio.wait_for(timeout=self.timeout_seconds)
        # - Return agent response dict
        # - On timeout: raise asyncio.TimeoutError
        raise NotImplementedError()
    
    def _extract_intent(self, agent_response: dict) -> str | None:
        """
        Extract classified intent from agent response metadata.
        (Depends on whether agent_runner exposes intent classification.)
        """
        # TODO: implement
        # - Check if agent_response contains classified_intent field
        # - Return it or None
        raise NotImplementedError()
