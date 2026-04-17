"""
Unit tests for engine/integrations/supabase_client.py

Tests the Supabase client factory functions.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_get_shared_db_returns_async_client(mock_env_vars):
    """Test that get_shared_db returns a Supabase AsyncClient."""
    from engine.integrations.supabase_client import get_shared_db

    mock_client = MagicMock()
    mock_client.table = MagicMock()

    with patch("engine.integrations.supabase_client.create_async_client", new_callable=AsyncMock, return_value=mock_client):
        client = await get_shared_db()

    assert client is not None
    assert hasattr(client, "table")


@pytest.mark.asyncio
async def test_get_client_db_returns_async_client(mock_env_vars, mock_supabase_client):
    """Test that get_client_db returns a Supabase AsyncClient for client's project."""
    from engine.integrations.supabase_client import get_client_db

    mock_client = MagicMock()
    mock_client.table = MagicMock()
    mock_config = MagicMock()
    mock_config.supabase_url = "https://heyaircon.supabase.co"
    mock_config.supabase_service_key = "hey_service_key_mock"

    with patch("engine.config.client_config.load_client_config", new_callable=AsyncMock, return_value=mock_config):
        with patch("engine.integrations.supabase_client.create_async_client", new_callable=AsyncMock, return_value=mock_client):
            client = await get_client_db("hey-aircon")

    assert client is not None
    assert hasattr(client, "table")


@pytest.mark.asyncio
async def test_get_shared_db_uses_correct_env_vars(mock_env_vars):
    """Test that get_shared_db uses SHARED_SUPABASE_* env vars."""
    from engine.integrations.supabase_client import get_shared_db

    mock_client = MagicMock()
    captured = {}

    async def fake_create(supabase_url, supabase_key):
        captured["url"] = supabase_url
        captured["key"] = supabase_key
        return mock_client

    with patch("engine.integrations.supabase_client.create_async_client", side_effect=fake_create):
        client = await get_shared_db()

    assert captured["url"] == "https://shared.supabase.co"
    assert captured["key"] == "shared_service_key_mock"
    assert client is not None


@pytest.mark.asyncio
async def test_get_client_db_uses_client_specific_env_vars(mock_env_vars, mock_supabase_client):
    """Test that get_client_db uses client-specific env vars from ClientConfig."""
    from engine.integrations.supabase_client import get_client_db

    mock_client = MagicMock()
    captured = {}
    mock_config = MagicMock()
    mock_config.supabase_url = "https://heyaircon.supabase.co"
    mock_config.supabase_service_key = "hey_service_key_mock"

    async def fake_create(supabase_url, supabase_key):
        captured["url"] = supabase_url
        captured["key"] = supabase_key
        return mock_client

    with patch("engine.config.client_config.load_client_config", new_callable=AsyncMock, return_value=mock_config) as mock_load:
        with patch("engine.integrations.supabase_client.create_async_client", side_effect=fake_create):
            client = await get_client_db("hey-aircon")

    mock_load.assert_called_once_with("hey-aircon")
    assert captured["url"] == "https://heyaircon.supabase.co"
    assert captured["key"] == "hey_service_key_mock"
    assert client is not None
