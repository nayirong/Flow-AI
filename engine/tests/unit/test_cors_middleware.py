"""
Unit tests for CORS middleware — widget endpoint origin validation.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from engine.api.cors_middleware import widget_cors_middleware


@pytest.fixture
def app_with_cors():
    """Create a test FastAPI app with CORS middleware."""
    app = FastAPI()
    app.middleware("http")(widget_cors_middleware)
    
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    @app.post("/chat/{client_id}/session")
    async def create_session(client_id: str):
        return {"session_id": "test-123"}
    
    @app.get("/widget/{client_id}.js")
    async def serve_widget(client_id: str):
        return Response(content="console.log('test');", media_type="application/javascript")
    
    return app


def test_non_widget_path_passes_through(app_with_cors, mock_env_vars, clear_client_config_cache):
    """Test that non-widget paths pass through without CORS headers."""
    client = TestClient(app_with_cors)
    
    response = client.get("/health")
    
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_valid_origin_gets_cors_headers(app_with_cors, mock_env_vars, clear_client_config_cache):
    """Test that valid origin gets CORS headers."""
    # Mock ClientConfig with allowed origin
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    mock_client_config.widget_allowed_origins = "https://example.com"
    
    with patch('engine.api.cors_middleware.load_client_config', return_value=mock_client_config):
        client = TestClient(app_with_cors)
        
        response = client.post(
            "/chat/test-client/session",
            headers={"Origin": "https://example.com"}
        )
        
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"
        assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_invalid_origin_returns_403(app_with_cors, mock_env_vars, clear_client_config_cache):
    """Test that invalid origin returns 403."""
    # Mock ClientConfig with allowed origin
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    mock_client_config.widget_allowed_origins = "https://example.com"
    
    with patch('engine.api.cors_middleware.load_client_config', return_value=mock_client_config):
        client = TestClient(app_with_cors)
        
        response = client.post(
            "/chat/test-client/session",
            headers={"Origin": "https://evil.com"}
        )
        
        assert response.status_code == 403


def test_options_preflight_valid(app_with_cors, mock_env_vars, clear_client_config_cache):
    """Test OPTIONS preflight with valid origin."""
    # Mock ClientConfig with allowed origin
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    mock_client_config.widget_allowed_origins = "https://example.com"
    
    with patch('engine.api.cors_middleware.load_client_config', return_value=mock_client_config):
        client = TestClient(app_with_cors)
        
        response = client.options(
            "/chat/test-client/session",
            headers={"Origin": "https://example.com"}
        )
        
        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"
        assert response.headers["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"
        assert response.headers["Access-Control-Max-Age"] == "86400"


def test_options_preflight_invalid(app_with_cors, mock_env_vars, clear_client_config_cache):
    """Test OPTIONS preflight with invalid origin."""
    # Mock ClientConfig with allowed origin
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    mock_client_config.widget_allowed_origins = "https://example.com"
    
    with patch('engine.api.cors_middleware.load_client_config', return_value=mock_client_config):
        client = TestClient(app_with_cors)
        
        response = client.options(
            "/chat/test-client/session",
            headers={"Origin": "https://evil.com"}
        )
        
        assert response.status_code == 403


def test_development_env_allows_localhost(app_with_cors, mock_env_vars, clear_client_config_cache, monkeypatch):
    """Test that development environment allows localhost origins."""
    # Set ENVIRONMENT to development
    monkeypatch.setenv("ENVIRONMENT", "development")
    
    # Mock ClientConfig with empty allowed origins
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    mock_client_config.widget_allowed_origins = ""
    
    with patch('engine.api.cors_middleware.load_client_config', return_value=mock_client_config):
        client = TestClient(app_with_cors)
        
        response = client.post(
            "/chat/test-client/session",
            headers={"Origin": "http://localhost:3000"}
        )
        
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_widget_js_route_cors(app_with_cors, mock_env_vars, clear_client_config_cache):
    """Test CORS on widget JS route."""
    # Mock ClientConfig with allowed origin
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    mock_client_config.widget_allowed_origins = "https://example.com"
    
    with patch('engine.api.cors_middleware.load_client_config', return_value=mock_client_config):
        client = TestClient(app_with_cors)
        
        response = client.get(
            "/widget/test-client.js",
            headers={"Origin": "https://example.com"}
        )
        
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"


def test_no_origin_header_passes_through(app_with_cors, mock_env_vars, clear_client_config_cache):
    """Test that requests without Origin header are allowed (curl, Postman, same-origin)."""
    # Mock ClientConfig
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    mock_client_config.widget_allowed_origins = "https://example.com"
    
    with patch('engine.api.cors_middleware.load_client_config', return_value=mock_client_config):
        client = TestClient(app_with_cors)
        
        # Request without Origin header
        response = client.post("/chat/test-client/session")
        
        assert response.status_code == 200
