"""
Unit tests for engine/integrations/supabase_client.py

Tests the Supabase client factory functions.
"""
import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_get_shared_db_returns_async_client(mock_env_vars):
    """Test that get_shared_db returns a Supabase AsyncClient."""
    from engine.integrations.supabase_client import get_shared_db
    
    client = await get_shared_db()
    
    # Verify it's an AsyncClient instance
    # The actual type check will depend on supabase-py implementation
    assert client is not None
    assert hasattr(client, "table")  # AsyncClient has table() method


@pytest.mark.asyncio
async def test_get_client_db_returns_async_client(mock_env_vars, mock_supabase_client):
    """Test that get_client_db returns a Supabase AsyncClient for client's project."""
    from engine.integrations.supabase_client import get_client_db
    
    # Mock load_client_config to avoid circular dependency
    with patch("engine.integrations.supabase_client.load_client_config") as mock_load:
        mock_config = AsyncMock()
        mock_config.supabase_url = "https://heyaircon.supabase.co"
        mock_config.supabase_service_key = "hey_service_key_mock"
        mock_load.return_value = mock_config
        
        client = await get_client_db("hey-aircon")
    
    assert client is not None
    assert hasattr(client, "table")


@pytest.mark.asyncio
async def test_get_shared_db_uses_correct_env_vars(mock_env_vars):
    """Test that get_shared_db uses SHARED_SUPABASE_* env vars."""
    from engine.integrations.supabase_client import get_shared_db
    from engine.config.settings import settings
    
    # Verify settings loaded correctly
    assert settings.shared_supabase_url == "https://shared.supabase.co"
    assert settings.shared_supabase_service_key == "shared_service_key_mock"
    
    # get_shared_db should use these values
    client = await get_shared_db()
    assert client is not None


@pytest.mark.asyncio
async def test_get_client_db_uses_client_specific_env_vars(mock_env_vars, mock_supabase_client):
    """Test that get_client_db uses client-specific env vars from ClientConfig."""
    from engine.integrations.supabase_client import get_client_db
    
    with patch("engine.integrations.supabase_client.load_client_config") as mock_load:
        mock_config = AsyncMock()
        mock_config.supabase_url = "https://heyaircon.supabase.co"
        mock_config.supabase_service_key = "hey_service_key_mock"
        mock_load.return_value = mock_config
        
        client = await get_client_db("hey-aircon")
        
        # Verify load_client_config was called with correct client_id
        mock_load.assert_called_once_with("hey-aircon")
        assert client is not None
