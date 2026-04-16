"""
Pytest configuration and fixtures for evaluation pipeline tests.

Fixtures:
- mock_supabase_client: Mock Supabase client
- sample_test_case: Sample TestCase object
- sample_agent_output: Sample AgentOutput object
- mock_telegram_notifier: Mock TelegramNotifier
"""

import os
import pytest
import asyncio


# Event loop configuration for async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def llm_provider_adapter():
    """
    Fixture that provides a mock LLMProviderAdapter for unit/integration tests.

    In unit tests (default): returns a mock that returns canned AgentOutput.
    In integration tests (LLM_PROVIDER set): returns real adapter using:
      - LLM_PROVIDER=github_models + GITHUB_TOKEN (uses Copilot subscription)
      - LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY (uses Anthropic billing)

    Set LLM_PROVIDER env var in .env.test to control which provider is used
    for integration tests. See docs/test-plan/eval_pipeline.md §9.3 for setup.
    """
    provider = os.getenv("LLM_PROVIDER", "mock")

    if provider == "mock":
        # Default for unit tests — no real API calls
        class MockLLMProviderAdapter:
            async def complete(self, messages, tools=None):
                return {
                    "response_text": "Mocked LLM response",
                    "tool_called": None,
                    "tool_params": None,
                    "classified_intent": "booking_request",
                    "raw_response": {},
                }
        return MockLLMProviderAdapter()

    # For integration tests — build real adapter
    # TODO: import and return LLMProviderAdapter(provider=provider) once implemented
    raise NotImplementedError(
        f"Real LLMProviderAdapter for '{provider}' not yet implemented. "
        "See engine/tests/eval/llm_provider.py stub."
    )


@pytest.fixture
def mock_supabase_client():
    """
    Mock Supabase client for testing.
    
    Provides:
    - Mock query methods
    - Mock insert/update methods
    - Configurable return values
    """
    # TODO: implement mock Supabase client
    # - Create mock object with .table(), .select(), .insert(), .update() methods
    # - Return mock
    
    class MockSupabaseClient:
        """Mock Supabase client."""
        
        def __init__(self):
            self.mock_rolling_average = None
            self.mock_test_cases = []
        
        def table(self, table_name: str):
            """Mock table selector."""
            return self
        
        def select(self, *args):
            """Mock select."""
            return self
        
        async def execute(self):
            """Mock execute."""
            return {"data": self.mock_test_cases, "error": None}
    
    return MockSupabaseClient()


@pytest.fixture
def sample_test_case():
    """
    Sample TestCase object for testing.
    
    Returns a TestCase with all common fields populated.
    """
    # TODO: implement
    # - Import TestCase model
    # - Return populated instance
    
    class TestCase:
        """Mock TestCase for now."""
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    return TestCase(
        id=1,
        client_id="hey-aircon",
        category="intent",
        test_name="test_sample",
        input_message="Hello",
        expected_intent="greeting",
        priority="medium",
        enabled=True,
    )


@pytest.fixture
def sample_agent_output():
    """
    Sample AgentOutput object for testing.
    
    Returns an AgentOutput with typical agent response.
    """
    # TODO: implement
    # - Import AgentOutput model
    # - Return populated instance
    
    class AgentOutput:
        """Mock AgentOutput for now."""
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    return AgentOutput(
        response_text="Hi! How can I help you?",
        tool_called=None,
        tool_params=None,
        escalation_triggered=False,
        classified_intent="greeting",
        execution_time_ms=500,
        raw_response={},
        error=None,
    )


@pytest.fixture
def mock_telegram_notifier(monkeypatch):
    """
    Mock TelegramNotifier for testing.
    
    Uses pytest-httpx to mock HTTP calls to api.telegram.org.
    """
    # TODO: implement
    # - Use pytest-httpx to mock Telegram API
    # - Return mock notifier instance
    
    from engine.tests.eval.alerts.telegram_notifier import TelegramNotifier
    
    notifier = TelegramNotifier(
        bot_token="test_token",
        chat_id="test_chat",
    )
    
    # Mock HTTP client
    async def mock_send_alert(alert):
        """Mock send_alert that always succeeds."""
        return True
    
    monkeypatch.setattr(notifier, "send_alert", mock_send_alert)
    
    return notifier


@pytest.fixture
def threshold_config():
    """
    Sample ThresholdConfig for testing.
    
    Loads from thresholds.yaml or returns hardcoded values.
    """
    # TODO: implement
    # - Import ThresholdConfig
    # - Load from YAML or return mock
    
    class ThresholdConfig:
        """Mock ThresholdConfig for now."""
        def __init__(self):
            self.regression_alert_delta = 0.05
    
    return ThresholdConfig()
