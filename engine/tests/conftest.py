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
    return env_vars


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
    """Mock Supabase AsyncClient with table() method chain."""
    mock_response = MagicMock()
    mock_response.data = [mock_supabase_clients_row]
    
    mock_execute = AsyncMock(return_value=mock_response)
    
    mock_limit = MagicMock()
    mock_limit.execute = mock_execute
    
    mock_eq = MagicMock(return_value=mock_limit)
    
    mock_select = MagicMock()
    mock_select.eq = mock_eq
    
    mock_table = MagicMock(return_value=mock_select)
    
    client = MagicMock()
    client.table = mock_table
    
    return client


@pytest.fixture
def clear_client_config_cache():
    """Clear the client config cache between tests."""
    # This will be imported and used by test_client_config.py
    # The actual cache clearing logic will be implemented by @software-engineer
    yield
    # Cache clearing happens here after test runs
