"""Unit tests for widget ClientConfig fields (Slice 1)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from engine.config.client_config import ClientConfig


def test_client_config_has_widget_fields():
    """ClientConfig has all 6 widget fields with correct types and defaults."""
    config = ClientConfig(
        client_id="test-client",
        display_name="Test Client",
        meta_phone_number_id="test-phone-id",
        meta_verify_token="test-token",
        meta_whatsapp_token="test-whatsapp-token",
        human_agent_number="6500000000",
        google_calendar_id=None,
        google_calendar_creds={},
        supabase_url="https://test.supabase.co",
        supabase_service_key="test-key",
        anthropic_api_key="test-anthropic",
        openai_api_key="test-openai",
        timezone="Asia/Singapore",
        is_active=True,
    )
    assert hasattr(config, "widget_enabled")
    assert hasattr(config, "widget_primary_color")
    assert hasattr(config, "widget_agent_name")
    assert hasattr(config, "widget_welcome_message")
    assert hasattr(config, "widget_allowed_origins")
    assert hasattr(config, "widget_session_ttl_minutes")

    assert isinstance(config.widget_enabled, bool)
    assert isinstance(config.widget_primary_color, str)
    assert isinstance(config.widget_agent_name, str)
    assert isinstance(config.widget_welcome_message, str)
    assert isinstance(config.widget_allowed_origins, str)
    assert isinstance(config.widget_session_ttl_minutes, int)


def test_widget_enabled_default_false():
    """widget_enabled defaults to False."""
    config = ClientConfig(
        client_id="test-client",
        display_name="Test Client",
        meta_phone_number_id="test-phone-id",
        meta_verify_token="test-token",
        meta_whatsapp_token="test-whatsapp-token",
        human_agent_number="6500000000",
        google_calendar_id=None,
        google_calendar_creds={},
        supabase_url="https://test.supabase.co",
        supabase_service_key="test-key",
        anthropic_api_key="test-anthropic",
        openai_api_key="test-openai",
        timezone="Asia/Singapore",
        is_active=True,
    )
    assert config.widget_enabled is False
    assert config.widget_primary_color == "#4F46E5"
    assert config.widget_agent_name == "Assistant"
    assert config.widget_welcome_message == "Hi! How can I help you today?"
    assert config.widget_allowed_origins == ""
    assert config.widget_session_ttl_minutes == 30


@pytest.mark.asyncio
async def test_client_config_loads_widget_fields_from_supabase():
    """load_client_config() populates all 6 widget fields from Supabase clients row."""
    from engine.config.client_config import load_client_config, _cache

    # Clear cache to force fresh load
    _cache.clear()

    supabase_row = {
        "client_id": "flow-ai",
        "display_name": "Flow AI",
        "meta_phone_number_id": "12345",
        "meta_verify_token": "verify-token",
        "human_agent_number": "6512345678",
        "is_active": True,
        "google_calendar_id": None,
        "timezone": "Asia/Singapore",
        "sheets_sync_enabled": False,
        "sheets_spreadsheet_id": None,
        "sheets_service_account_creds": None,
        "widget_enabled": True,
        "widget_primary_color": "#FF6B35",
        "widget_agent_name": "Kai",
        "widget_welcome_message": "Hi! I'm Kai from Flow AI.",
        "widget_allowed_origins": "https://getflowai.co,https://www.getflowai.co",
        "widget_session_ttl_minutes": 45,
    }

    # Mock the Supabase call chain: db.table("clients").select("*").eq(...).eq(...).limit(1).execute()
    mock_supabase = MagicMock()
    mock_chain = MagicMock()
    mock_chain.select.return_value = mock_chain
    mock_chain.eq.return_value = mock_chain
    mock_chain.limit.return_value = mock_chain
    mock_chain.execute = AsyncMock(return_value=MagicMock(data=[supabase_row]))
    mock_supabase.table.return_value = mock_chain

    # Mock environment variables for secrets
    env_vars = {
        "FLOW_AI_META_WHATSAPP_TOKEN": "test-whatsapp-token",
        "FLOW_AI_SUPABASE_URL": "https://test.supabase.co",
        "FLOW_AI_SUPABASE_SERVICE_KEY": "test-service-key",
        "FLOW_AI_ANTHROPIC_API_KEY": "test-anthropic-key",
        "FLOW_AI_OPENAI_API_KEY": "test-openai-key",
        "FLOW_AI_GOOGLE_CALENDAR_CREDS": "{}",
    }

    with patch("engine.config.client_config.get_shared_db", new=AsyncMock(return_value=mock_supabase)):
        with patch.dict("os.environ", env_vars, clear=False):
            config = await load_client_config("flow-ai")

    assert config.widget_enabled is True
    assert config.widget_primary_color == "#FF6B35"
    assert config.widget_agent_name == "Kai"
    assert config.widget_welcome_message == "Hi! I'm Kai from Flow AI."
    assert config.widget_allowed_origins == "https://getflowai.co,https://www.getflowai.co"
    assert config.widget_session_ttl_minutes == 45
