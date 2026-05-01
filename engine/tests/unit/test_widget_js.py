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
    return config


def test_widget_js_injects_client_id(client, mock_client_config):
    """Test that GET /widget/{client_id}.js injects the client ID."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert "application/javascript" in response.headers["content-type"]
        assert "window.FLOWAI_CLIENT_ID = 'hey-aircon';" in response.text


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
        assert response.text.startswith("window.FLOWAI_CLIENT_ID")


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
