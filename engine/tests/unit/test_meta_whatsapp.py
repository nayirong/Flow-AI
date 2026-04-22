"""
Meta WhatsApp integration unit tests — send_message() return type.

Tests for the return type change from bool to Optional[str]:
- Returns wamid on successful send
- Returns None on HTTP error
- Returns None on JSON parse error
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_client_config():
    """Mock ClientConfig."""
    cfg = MagicMock()
    cfg.client_id = "hey-aircon"
    cfg.meta_phone_number_id = "123456789"
    cfg.meta_whatsapp_token = "test_token"
    return cfg


@pytest.mark.asyncio
async def test_send_message_returns_wamid_on_success():
    """
    send_message() returns wamid string on successful 200 response.
    """
    from engine.integrations.meta_whatsapp import send_message
    
    cfg = _make_client_config()
    
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "messaging_product": "whatsapp",
        "contacts": [{"input": "6591234567", "wa_id": "6591234567"}],
        "messages": [{"id": "wamid.HBgLNjU5MTIzNDU2Nw"}]
    }
    
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        
        result = await send_message(
            client_config=cfg,
            to_phone_number="6591234567",
            text="Test message",
        )
    
    # Assert returns wamid string
    assert result == "wamid.HBgLNjU5MTIzNDU2Nw"
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_send_message_returns_none_on_http_error():
    """
    send_message() returns None on non-200 HTTP response.
    """
    from engine.integrations.meta_whatsapp import send_message
    
    cfg = _make_client_config()
    
    # Mock httpx response with 400 error
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        
        result = await send_message(
            client_config=cfg,
            to_phone_number="6591234567",
            text="Test message",
        )
    
    # Assert returns None
    assert result is None


@pytest.mark.asyncio
async def test_send_message_returns_none_on_json_parse_error():
    """
    send_message() returns None if response is 200 but JSON parsing fails.
    """
    from engine.integrations.meta_whatsapp import send_message
    
    cfg = _make_client_config()
    
    # Mock httpx response with invalid JSON
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.text = "Not JSON"
    
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        
        result = await send_message(
            client_config=cfg,
            to_phone_number="6591234567",
            text="Test message",
        )
    
    # Assert returns None (treats as failure)
    assert result is None


@pytest.mark.asyncio
async def test_send_message_returns_none_on_missing_wamid():
    """
    send_message() returns None if response is 200 but wamid is missing.
    """
    from engine.integrations.meta_whatsapp import send_message
    
    cfg = _make_client_config()
    
    # Mock httpx response with valid JSON but missing wamid
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "messaging_product": "whatsapp",
        # messages array is missing
    }
    mock_response.text = '{"messaging_product": "whatsapp"}'
    
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        
        result = await send_message(
            client_config=cfg,
            to_phone_number="6591234567",
            text="Test message",
        )
    
    # Assert returns None (treats as failure)
    assert result is None


@pytest.mark.asyncio
async def test_send_message_returns_none_on_exception():
    """
    send_message() returns None if httpx raises an exception.
    """
    from engine.integrations.meta_whatsapp import send_message
    
    cfg = _make_client_config()
    
    # Mock httpx to raise exception
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(side_effect=Exception("Network error"))
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_http_client
        
        result = await send_message(
            client_config=cfg,
            to_phone_number="6591234567",
            text="Test message",
        )
    
    # Assert returns None (never raises)
    assert result is None
