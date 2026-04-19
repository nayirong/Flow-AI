"""
Unit tests for engine/config/client_config.py

Tests ClientConfig model and load_client_config() function with TTL caching.
"""
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_load_client_config_success(mock_env_vars, mock_supabase_client, clear_client_config_cache):
    """Test that load_client_config returns ClientConfig with all fields populated."""
    from engine.config.client_config import load_client_config
    
    # Mock get_shared_db to return our mock client
    with patch("engine.config.client_config.get_shared_db", return_value=mock_supabase_client):
        config = await load_client_config("hey-aircon")
    
    assert config.client_id == "hey-aircon"
    assert config.display_name == "HeyAircon"
    assert config.meta_phone_number_id == "123456789"
    assert config.meta_verify_token == "heyaircon_webhook_2026"
    assert config.human_agent_number == "+6591234567"
    assert config.google_calendar_id == "test@group.calendar.google.com"
    assert config.is_active is True
    
    # Verify secrets loaded from env vars
    assert config.meta_whatsapp_token == "hey_meta_token_mock"
    assert config.supabase_url == "https://heyaircon.supabase.co"
    assert config.supabase_service_key == "hey_service_key_mock"
    assert config.anthropic_api_key == "sk-ant-test-key"
    assert config.openai_api_key == "sk-openai-test-key"
    assert isinstance(config.google_calendar_creds, dict)


@pytest.mark.asyncio
async def test_load_client_config_not_found(mock_env_vars, clear_client_config_cache):
    """Test that load_client_config raises ClientNotFoundError for unknown client."""
    from engine.config.client_config import load_client_config, ClientNotFoundError

    mock_response = MagicMock()
    mock_response.data = []
    mock_execute = AsyncMock(return_value=mock_response)
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute = mock_execute
    mock_client = MagicMock()
    mock_client.table.return_value = chain

    with patch("engine.config.client_config.get_shared_db", new_callable=AsyncMock, return_value=mock_client):
        with pytest.raises(ClientNotFoundError) as exc_info:
            await load_client_config("unknown-client")

        assert "unknown-client" in str(exc_info.value)


@pytest.mark.asyncio
async def test_load_client_config_caching(mock_env_vars, mock_supabase_client, clear_client_config_cache):
    """Test that second call within TTL returns cached value without DB query."""
    from engine.config.client_config import load_client_config
    
    call_count = 0
    
    async def tracked_get_shared_db():
        nonlocal call_count
        call_count += 1
        return mock_supabase_client
    
    with patch("engine.config.client_config.get_shared_db", side_effect=tracked_get_shared_db):
        # First call — should hit DB
        config1 = await load_client_config("hey-aircon")
        assert call_count == 1

        # Second call within TTL — should use cache
        config2 = await load_client_config("hey-aircon")
        assert call_count == 1  # No additional DB call

        assert config1.client_id == config2.client_id


@pytest.mark.asyncio
async def test_load_client_config_ttl_expiry(mock_env_vars, mock_supabase_client, clear_client_config_cache):
    """Test that call after TTL expires re-queries Supabase."""
    from engine.config.client_config import load_client_config
    
    call_count = 0
    
    async def tracked_get_shared_db():
        nonlocal call_count
        call_count += 1
        return mock_supabase_client
    
    # Patch TTL to 1 second for faster testing
    with patch("engine.config.client_config.get_shared_db", side_effect=tracked_get_shared_db):
        with patch("engine.config.client_config.CACHE_TTL_SECONDS", 1):
            # First call
            await load_client_config("hey-aircon")
            assert call_count == 1
            
            # Wait for TTL to expire
            time.sleep(1.1)
            
            # Second call after TTL — should hit DB again
            await load_client_config("hey-aircon")
            assert call_count == 2


@pytest.mark.asyncio
async def test_load_client_config_inactive_client(mock_env_vars, clear_client_config_cache):
    """Test that inactive client (is_active=False) raises ClientNotFoundError."""
    from engine.config.client_config import load_client_config, ClientNotFoundError

    # The query filters by is_active=TRUE so returns no rows for inactive client
    mock_response = MagicMock()
    mock_response.data = []
    mock_execute = AsyncMock(return_value=mock_response)
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute = mock_execute
    mock_client = MagicMock()
    mock_client.table.return_value = chain

    with patch("engine.config.client_config.get_shared_db", new_callable=AsyncMock, return_value=mock_client):
        with pytest.raises(ClientNotFoundError):
            await load_client_config("inactive-client")
