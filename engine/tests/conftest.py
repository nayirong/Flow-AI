"""
Shared pytest fixtures for Flow AI engine tests.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock all required environment variables for Settings."""
    env_vars = {
        "SHARED_SUPABASE_URL": "https://shared.supabase.co",
        "SHARED_SUPABASE_SERVICE_KEY": "shared_service_key_mock",
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "LOG_LEVEL": "INFO",
        # HeyAircon client secrets
        "HEY_AIRCON_META_WHATSAPP_TOKEN": "hey_meta_token_mock",
        "HEY_AIRCON_SUPABASE_URL": "https://heyaircon.supabase.co",
        "HEY_AIRCON_SUPABASE_SERVICE_KEY": "hey_service_key_mock",
        "HEY_AIRCON_GOOGLE_CALENDAR_CREDS": '{"type": "service_account", "project_id": "test"}',
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    # Reset the lazy singleton so it re-reads the mocked env vars
    import engine.config.settings as _settings_mod
    _settings_mod._settings_instance = None
    yield env_vars
    # Reset again after test so next test starts clean
    _settings_mod._settings_instance = None


@pytest.fixture
def mock_supabase_clients_row():
    """Mock Supabase clients table row for hey-aircon."""
    return {
        "client_id": "hey-aircon",
        "display_name": "HeyAircon",
        "meta_phone_number_id": "123456789",
        "meta_verify_token": "heyaircon_webhook_2026",
        "human_agent_number": "+6591234567",
        "google_calendar_id": "test@group.calendar.google.com",
        "timezone": "Asia/Singapore",
        "is_active": True,
    }


@pytest.fixture
def mock_supabase_client(mock_supabase_clients_row):
    """Mock Supabase AsyncClient with a fully chainable table() method."""
    mock_response = MagicMock()
    mock_response.data = [mock_supabase_clients_row]

    mock_execute = AsyncMock(return_value=mock_response)

    # Chainable mock: every method call returns self, except execute() which is AsyncMock
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.order.return_value = chain
    chain.execute = mock_execute

    client = MagicMock()
    client.table.return_value = chain

    return client


@pytest.fixture
def clear_client_config_cache():
    """Clear the client config cache between tests."""
    from engine.config import client_config
    # Clear cache before test
    client_config._cache.clear()
    yield
    # Clear cache after test
    client_config._cache.clear()


@pytest.fixture
def sample_meta_payload():
    """Valid Meta inbound message webhook payload."""
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "6591234567",
                        "id": "wamid.test123",
                        "type": "text",
                        "text": {"body": "Hello, I need aircon servicing"}
                    }],
                    "contacts": [{
                        "profile": {"name": "John Tan"},
                        "wa_id": "6591234567"
                    }]
                }
            }]
        }]
    }


@pytest.fixture
def sample_meta_status_payload():
    """Meta status update payload (no messages — should be ignored)."""
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{"status": "delivered", "id": "wamid.test123"}]
                }
            }]
        }]
    }


@pytest.fixture
def mock_client_config_obj():
    """Mock ClientConfig for webhook tests."""
    from unittest.mock import MagicMock
    config = MagicMock()
    config.meta_verify_token = "heyaircon_webhook_2026"
    config.meta_phone_number_id = "123456789"
    config.meta_whatsapp_token = "test_token"
    return config
