"""
Integration tests for widget API routes.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from engine.api.webhook import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_create_session_success(client, mock_env_vars, clear_client_config_cache):
    """Test successful session creation."""
    # Mock ClientConfig
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    mock_client_config.widget_welcome_message = "Welcome to our chat!"
    
    # Mock get_client_db
    mock_db = MagicMock()
    mock_insert_chain = MagicMock()
    mock_insert_chain.insert.return_value = mock_insert_chain
    mock_insert_chain.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-123"}]))
    mock_db.table.return_value = mock_insert_chain
    
    with patch('engine.api.widget.load_client_config', return_value=mock_client_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        response = client.post("/chat/test-client/session")
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["welcome_message"] == "Welcome to our chat!"


def test_create_session_widget_disabled(client, mock_env_vars, clear_client_config_cache):
    """Test session creation when widget is disabled."""
    # Mock ClientConfig with widget disabled
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = False
    
    with patch('engine.api.widget.load_client_config', return_value=mock_client_config):
        response = client.post("/chat/test-client/session")
        
        assert response.status_code == 403


def test_create_session_client_not_found(client, mock_env_vars, clear_client_config_cache):
    """Test session creation when client not found."""
    from engine.config.client_config import ClientNotFoundError
    
    with patch('engine.api.widget.load_client_config', side_effect=ClientNotFoundError("Not found")):
        response = client.post("/chat/test-client/session")
        
        assert response.status_code == 404


def test_send_message_success(client, mock_env_vars, clear_client_config_cache):
    """Test successful message send."""
    # Mock ClientConfig
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    # Mock get_client_db
    mock_db = MagicMock()
    
    # Single chain that handles both select and update operations on sessions table.
    # All chained methods return self so any call sequence works.
    mock_session_chain = MagicMock()
    mock_session_chain.select.return_value = mock_session_chain
    mock_session_chain.update.return_value = mock_session_chain
    mock_session_chain.eq.return_value = mock_session_chain
    mock_session_chain.limit.return_value = mock_session_chain
    mock_session_chain.execute = AsyncMock(return_value=MagicMock(data=[
        {"session_id": "test-session-123", "expired_at": None}
    ]))

    mock_db.table.return_value = mock_session_chain
    
    # Mock handle_widget_message
    mock_reply = "Hello! How can I help?"
    
    with patch('engine.api.widget.load_client_config', return_value=mock_client_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db), \
         patch('engine.api.widget.handle_widget_message', return_value=(mock_reply, False)):
        
        response = client.post(
            "/chat/test-client/message",
            json={"session_id": "test-session-123", "message": "Hello"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == mock_reply
        assert data["escalated"] is False


def test_send_message_session_not_found(client, mock_env_vars, clear_client_config_cache):
    """Test message send with invalid session."""
    # Mock ClientConfig
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    # Mock get_client_db with empty session result
    mock_db = MagicMock()
    mock_session_chain = MagicMock()
    mock_session_chain.select.return_value = mock_session_chain
    mock_session_chain.eq.return_value = mock_session_chain
    mock_session_chain.limit.return_value = mock_session_chain
    mock_session_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    mock_db.table.return_value = mock_session_chain
    
    with patch('engine.api.widget.load_client_config', return_value=mock_client_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        response = client.post(
            "/chat/test-client/message",
            json={"session_id": "invalid-session", "message": "Hello"}
        )
        
        assert response.status_code == 404


def test_send_message_expired_session(client, mock_env_vars, clear_client_config_cache):
    """Test message send with expired session."""
    # Mock ClientConfig
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    # Mock get_client_db with expired session
    mock_db = MagicMock()
    mock_session_chain = MagicMock()
    mock_session_chain.select.return_value = mock_session_chain
    mock_session_chain.eq.return_value = mock_session_chain
    mock_session_chain.limit.return_value = mock_session_chain
    mock_session_chain.execute = AsyncMock(return_value=MagicMock(data=[
        {"session_id": "test-session-123", "expired_at": "2026-05-01T10:00:00Z"}
    ]))
    mock_db.table.return_value = mock_session_chain
    
    with patch('engine.api.widget.load_client_config', return_value=mock_client_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        response = client.post(
            "/chat/test-client/message",
            json={"session_id": "test-session-123", "message": "Hello"}
        )
        
        assert response.status_code == 410


def test_send_message_empty_message(client, mock_env_vars, clear_client_config_cache):
    """Test message send with empty message."""
    response = client.post(
        "/chat/test-client/message",
        json={"session_id": "test-session-123", "message": ""}
    )
    
    # FastAPI validation should reject empty message
    assert response.status_code == 422


def test_get_history_success(client, mock_env_vars, clear_client_config_cache):
    """Test successful history retrieval."""
    # Mock ClientConfig
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    # Mock get_client_db
    mock_db = MagicMock()
    
    # Mock session validation
    mock_session_chain = MagicMock()
    mock_session_chain.select.return_value = mock_session_chain
    mock_session_chain.eq.return_value = mock_session_chain
    mock_session_chain.limit.return_value = mock_session_chain
    mock_session_chain.execute = AsyncMock(return_value=MagicMock(data=[
        {"session_id": "test-session-123", "expired_at": None}
    ]))
    
    # Mock interactions_log history
    mock_history_chain = MagicMock()
    mock_history_chain.select.return_value = mock_history_chain
    mock_history_chain.eq.return_value = mock_history_chain
    mock_history_chain.order.return_value = mock_history_chain
    mock_history_chain.limit.return_value = mock_history_chain
    mock_history_chain.execute = AsyncMock(return_value=MagicMock(data=[
        {"message_text": "Hello", "direction": "inbound", "created_at": "2026-05-01T10:00:00Z"},
        {"message_text": "Hi there!", "direction": "outbound", "created_at": "2026-05-01T10:00:01Z"},
    ]))
    
    # Mock visitors query (no escalation)
    mock_visitor_chain = MagicMock()
    mock_visitor_chain.select.return_value = mock_visitor_chain
    mock_visitor_chain.eq.return_value = mock_visitor_chain
    mock_visitor_chain.limit.return_value = mock_visitor_chain
    mock_visitor_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    call_count = [0]
    def mock_table(table_name):
        call_count[0] += 1
        if table_name == "sessions":
            return mock_session_chain
        elif table_name == "interactions_log":
            return mock_history_chain
        elif table_name == "visitors":
            return mock_visitor_chain
        return MagicMock()
    
    mock_db.table = mock_table
    
    with patch('engine.api.widget.load_client_config', return_value=mock_client_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        response = client.get("/chat/test-client/history?session_id=test-session-123")
        
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"
        assert data["escalated"] is False


def test_widget_js_success(client, mock_env_vars, clear_client_config_cache):
    """Test widget JS serving."""
    # Mock ClientConfig
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    with patch('engine.api.widget.load_client_config', return_value=mock_client_config):
        response = client.get("/widget/test-client.js")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/javascript"
        assert "FLOWAI_CLIENT_ID" in response.text
        assert "'test-client'" in response.text


def test_widget_js_client_not_found(client, mock_env_vars, clear_client_config_cache):
    """Test widget JS serving when client not found."""
    from engine.config.client_config import ClientNotFoundError
    
    with patch('engine.api.widget.load_client_config', side_effect=ClientNotFoundError("Not found")):
        response = client.get("/widget/invalid-client.js")
        
        assert response.status_code == 404
        assert "Widget not enabled" in response.text


def test_widget_js_widget_disabled(client, mock_env_vars, clear_client_config_cache):
    """Test widget JS serving when widget is disabled."""
    # Mock ClientConfig with widget disabled
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = False
    
    with patch('engine.api.widget.load_client_config', return_value=mock_client_config):
        response = client.get("/widget/test-client.js")
        
        assert response.status_code == 404
        assert "Widget not enabled" in response.text
