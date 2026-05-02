"""Tests for widget JS serving endpoint."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from starlette.testclient import TestClient
from fastapi import FastAPI
from engine.api.widget import widget_router
from engine.config.client_config import ClientNotFoundError


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(widget_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_client_config():
    """Mock client config with widget enabled."""
    config = MagicMock()
    config.widget_enabled = True
    config.widget_welcome_message = "Welcome!"
    config.widget_primary_color = '#1B5E3F'
    config.widget_button_icon = '💬'
    return config


def test_widget_js_injects_client_id(client, mock_client_config):
    """Test that GET /widget/{client_id}.js injects the client ID via FLOWAI_CONFIG."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert "application/javascript" in response.headers["content-type"]
        assert 'window.FLOWAI_CONFIG' in response.text
        assert '"clientId": "hey-aircon"' in response.text


def test_widget_js_cache_control_header(client, mock_client_config):
    """Test that response includes proper Cache-Control header."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=3600"


def test_widget_js_widget_disabled_returns_404(client):
    """Test that widget disabled returns 404."""
    mock_config = MagicMock()
    mock_config.widget_enabled = False
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 404
        assert "not enabled" in response.text


def test_widget_js_client_not_found_returns_404(client):
    """Test that non-existent client returns 404."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.side_effect = ClientNotFoundError("Client not found")
        
        response = client.get("/widget/nonexistent.js")
        
        assert response.status_code == 404


def test_widget_js_body_starts_with_client_id_injection(client, mock_client_config):
    """Test that the client ID injection is at the TOP of the file."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        # Verify the injection is at the start
        assert response.text.startswith("window.FLOWAI_CONFIG")


def test_widget_js_contains_static_file_content(client, mock_client_config):
    """Test that response includes content from engine/static/widget.js."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        # Verify it contains actual widget code (IIFE pattern)
        assert "(function()" in response.text or "(function ()" in response.text
        # Verify it contains widget-specific code
        assert "flowai-widget-btn" in response.text
        assert "flowai-widget-window" in response.text


def test_serve_widget_js_injects_flowai_config(client, mock_client_config):
    """Served JS contains window.FLOWAI_CONFIG object not window.FLOWAI_CLIENT_ID."""
    mock_client_config.widget_primary_color = '#1B5E3F'
    mock_client_config.widget_button_icon = '💬'
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert 'window.FLOWAI_CONFIG' in response.text
        assert '"clientId": "hey-aircon"' in response.text
        assert '"primaryColor": "#1B5E3F"' in response.text
        assert '"buttonIcon": "💬"' in response.text
        assert 'window.FLOWAI_CLIENT_ID' not in response.text  # old pattern removed


def test_serve_widget_js_no_hardcoded_indigo(client, mock_client_config):
    """Served JS does not contain hardcoded #4F46E5."""
    mock_client_config.widget_primary_color = '#1B5E3F'
    mock_client_config.widget_button_icon = '💬'
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert '#4F46E5' not in response.text


def test_serve_widget_js_invalid_hex_fallback(client, mock_client_config):
    """Invalid hex color falls back to #1B5E3F."""
    mock_client_config.widget_primary_color = 'not-a-color'
    mock_client_config.widget_button_icon = '💬'
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert '"primaryColor": "#1B5E3F"' in response.text


def test_serve_widget_js_icon_truncated(client, mock_client_config):
    """Icon longer than 4 chars is truncated."""
    mock_client_config.widget_primary_color = '#1B5E3F'
    mock_client_config.widget_button_icon = 'toolong'
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert '"buttonIcon": "tool"' in response.text

