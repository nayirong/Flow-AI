"""
LLMProviderAdapter: Normalises LLM API calls across providers.

Supported providers (controlled by LLM_PROVIDER env var):

  anthropic (default for CI and production)
    - Uses: anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    - Requires: ANTHROPIC_API_KEY environment variable

  github_models (recommended for local development)
    - Uses: openai.AsyncOpenAI(api_key=GITHUB_TOKEN, base_url="https://models.inference.ai.azure.com/v1")
    - Requires: GITHUB_TOKEN environment variable
    - Works with an active GitHub Copilot subscription — no separate Anthropic billing needed
    - Model name may differ from Anthropic; override with LLM_MODEL_OVERRIDE env var
    - Rate limits apply on Copilot tier; use EVAL_PARALLELISM=3 locally

Optional env vars:
  LLM_MODEL_OVERRIDE  — override the model name (e.g. claude-claude-sonnet-4-6-20250219 for GitHub Models)
  LLM_PROVIDER        — 'anthropic' | 'github_models' (default: 'anthropic')
"""

import os
import logging

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class LLMProviderAdapter:
    """
    Adapter that wraps Anthropic or GitHub Models API behind a single interface.
    """

    def __init__(self):
        """
        Initialise the adapter from environment variables.
        """
        self.provider = os.getenv("LLM_PROVIDER", "anthropic")
        self.model = os.getenv("LLM_MODEL_OVERRIDE", DEFAULT_MODEL)
        self._client = None

        logger.info(f"LLMProviderAdapter: provider={self.provider}, model={self.model}")

        if self.provider == "anthropic":
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
                self._client = anthropic.AsyncAnthropic(api_key=api_key)
            except ImportError:
                logger.error("anthropic package not installed. Install with: pip install anthropic")
                raise

        elif self.provider == "github_models":
            try:
                import openai
                token = os.getenv("GITHUB_TOKEN")
                if not token:
                    raise ValueError("GITHUB_TOKEN is required when LLM_PROVIDER=github_models")
                self._client = openai.AsyncOpenAI(
                    api_key=token,
                    base_url="https://models.inference.ai.azure.com/v1",
                )
            except ImportError:
                logger.error("openai package not installed. Install with: pip install openai")
                raise

        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {self.provider!r}. Use 'anthropic' or 'github_models'.")

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
    ) -> dict:
        """
        Send a completion request and return a normalised response dict.

        Never raises — returns {"error": str} on failure.
        """
        try:
            if self.provider == "anthropic":
                return await self._complete_anthropic(messages, tools, system)
            elif self.provider == "github_models":
                return await self._complete_github_models(messages, tools, system)
        except Exception as e:
            logger.error(f"LLMProviderAdapter.complete() failed: {e}")
            return {
                "response_text": "",
                "tool_called": None,
                "tool_params": None,
                "classified_intent": None,
                "raw_response": {},
                "error": str(e)
            }

    async def _complete_anthropic(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        system: str | None,
    ) -> dict:
        """Call Anthropic API and normalise response."""
        try:
            kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": messages
            }
            
            if system:
                kwargs["system"] = system
            
            if tools:
                kwargs["tools"] = tools
            
            response = await self._client.messages.create(**kwargs)
            return self._normalise_anthropic_response(response.model_dump())
        
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            return {
                "response_text": "",
                "tool_called": None,
                "tool_params": None,
                "classified_intent": None,
                "raw_response": {},
                "error": str(e)
            }

    async def _complete_github_models(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        system: str | None,
    ) -> dict:
        """
        Call GitHub Models API (OpenAI-compatible) and normalise response.
        """
        try:
            # Prepend system message if provided
            if system:
                messages = [{"role": "system", "content": system}] + messages
            
            kwargs = {
                "model": self.model,
                "messages": messages
            }
            
            # Convert Anthropic tools format to OpenAI tools format if provided
            if tools:
                openai_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema", {})
                        }
                    }
                    for tool in tools
                ]
                kwargs["tools"] = openai_tools
            
            response = await self._client.chat.completions.create(**kwargs)
            return self._normalise_openai_response(response.model_dump())
        
        except Exception as e:
            logger.error(f"GitHub Models API call failed: {e}")
            return {
                "response_text": "",
                "tool_called": None,
                "tool_params": None,
                "classified_intent": None,
                "raw_response": {},
                "error": str(e)
            }

    def _normalise_anthropic_response(self, raw: dict) -> dict:
        """Extract response_text, tool_called, tool_params from Anthropic response."""
        response_text = ""
        tool_called = None
        tool_params = None
        
        # Extract from content blocks
        for block in raw.get("content", []):
            if block.get("type") == "text":
                response_text += block.get("text", "")
            elif block.get("type") == "tool_use":
                # Get first tool call only (eval tests one tool at a time)
                if tool_called is None:
                    tool_called = block.get("name")
                    tool_params = block.get("input", {})
        
        return {
            "response_text": response_text,
            "tool_called": tool_called,
            "tool_params": tool_params,
            "classified_intent": None,  # TODO: extract from metadata if present
            "raw_response": raw
        }

    def _normalise_openai_response(self, raw: dict) -> dict:
        """Extract response_text, tool_called, tool_params from OpenAI-format response."""
        message = raw.get("choices", [{}])[0].get("message", {})
        response_text = message.get("content", "") or ""
        
        tool_called = None
        tool_params = None
        
        # Extract tool calls
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            # Get first tool call only
            first_call = tool_calls[0]
            function = first_call.get("function", {})
            tool_called = function.get("name")
            
            # Parse JSON params
            import json
            params_str = function.get("arguments", "{}")
            try:
                tool_params = json.loads(params_str)
            except json.JSONDecodeError:
                tool_params = {}
        
        return {
            "response_text": response_text,
            "tool_called": tool_called,
            "tool_params": tool_params,
            "classified_intent": None,
            "raw_response": raw
        }
