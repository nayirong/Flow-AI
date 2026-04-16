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
import logging

from .models import AgentOutput, TestCase


logger = logging.getLogger(__name__)


# Try to import agent_runner — may not exist yet
try:
    from engine.core import agent_runner
    AGENT_RUNNER_AVAILABLE = True
except ImportError:
    logger.warning("agent_runner not available — Python engine not built yet")
    AGENT_RUNNER_AVAILABLE = False


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
        llm_provider_adapter,  # LLMProviderAdapter
        timeout_seconds: int = 30,
    ):
        """Initialize executor with clients."""
        self.eval_supabase_client = eval_supabase_client
        self.llm_provider_adapter = llm_provider_adapter
        self.timeout_seconds = timeout_seconds
    
    async def execute(
        self,
        test_case: TestCase,
    ) -> AgentOutput:
        """
        Execute agent for a single test case.
        
        Returns:
            AgentOutput with response, tools, intent, timing.
            On error: returns AgentOutput with error field set.
        """
        if not AGENT_RUNNER_AVAILABLE:
            return AgentOutput(
                response_text="",
                error="agent_runner not available — Python engine not built yet"
            )
        
        start_time = time.time()
        
        try:
            # Build messages
            messages = []
            for msg in test_case.conversation_history:
                messages.append(msg)
            messages.append({"role": "user", "content": test_case.input_message})
            
            # Call LLM via provider adapter
            result = await asyncio.wait_for(
                self.llm_provider_adapter.complete(
                    messages=messages,
                    tools=None,  # TODO: load tools from agent_runner
                    system="You are a helpful AI assistant."  # TODO: build from context_builder
                ),
                timeout=self.timeout_seconds
            )
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Check if LLM call returned an error
            if result.get("error"):
                return AgentOutput(
                    response_text="",
                    error=result["error"],
                    execution_time_ms=execution_time_ms
                )
            
            return AgentOutput(
                response_text=result.get("response_text", ""),
                tool_called=result.get("tool_called"),
                tool_params=result.get("tool_params"),
                escalation_triggered=False,  # TODO: detect escalation
                classified_intent=result.get("classified_intent"),
                execution_time_ms=execution_time_ms,
                raw_response=result.get("raw_response", {})
            )
        
        except asyncio.TimeoutError:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return AgentOutput(
                response_text="",
                error="timeout",
                execution_time_ms=execution_time_ms
            )
        
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"AgentExecutor.execute() failed: {e}")
            return AgentOutput(
                response_text="",
                error=f"execution_failed: {str(e)}",
                execution_time_ms=execution_time_ms
            )
