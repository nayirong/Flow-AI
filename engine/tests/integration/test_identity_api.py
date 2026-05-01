"""Integration tests for identity linking in POST /chat/{client_id}/session."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient


@pytest.fixture
def app():
    """Create FastAPI app with widget router."""
    from fastapi import FastAPI
    from engine.api.widget import widget_router
    
    app = FastAPI()
    app.include_router(widget_router)
    return app


def test_session_with_phone_creates_visitor_with_customer_id(app, mock_env_vars, clear_client_config_cache):
    """Integration test: session creation with phone links to customer."""
    
    mock_config = MagicMock()
    mock_config.widget_enabled = True
    mock_config.widget_welcome_message = "Welcome to our service!"
    
    # Mock Supabase responses
    mock_sessions_insert = AsyncMock()
    mock_sessions_insert.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-session"}]))
    
    mock_customers_select = AsyncMock()
    mock_customers_result = MagicMock()
    mock_customers_result.data = [{"id": "cust-456"}]
    mock_customers_select.execute = AsyncMock(return_value=mock_customers_result)
    
    mock_visitors_chain = MagicMock()
    mock_visitors_chain.insert.return_value = mock_visitors_chain
    mock_visitors_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_db = MagicMock()
    
    def table_mock(table_name):
        chain = MagicMock()
        if table_name == "sessions":
            chain.insert.return_value = mock_sessions_insert
        elif table_name == "customers":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = mock_customers_select
        elif table_name == "visitors":
            return mock_visitors_chain
        return chain
    
    mock_db.table = table_mock
    
    with patch('engine.api.widget.load_client_config', return_value=mock_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        client = TestClient(app)
        response = client.post(
            "/chat/test-client/session",
            json={"name": "Jane Doe", "email": "jane@example.com", "phone": "+6581234567"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["welcome_message"] == "Welcome to our service!"
        
        # Verify visitors insert was called with customer_id
        mock_visitors_chain.insert.assert_called_once()
        call_args = mock_visitors_chain.insert.call_args[0][0]
        assert call_args["customer_id"] == "cust-456"
        assert call_args["phone"] == "6581234567"  # Normalized
        assert call_args["name"] == "Jane Doe"
        assert call_args["email"] == "jane@example.com"


def test_session_with_phone_no_match_creates_visitor_with_null_customer_id(app, mock_env_vars, clear_client_config_cache):
    """Integration test: session creation with unmatched phone creates visitor without link."""
    
    mock_config = MagicMock()
    mock_config.widget_enabled = True
    mock_config.widget_welcome_message = "Hello!"
    
    mock_sessions_insert = AsyncMock()
    mock_sessions_insert.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-session"}]))
    
    # Customers query returns empty (no match)
    mock_customers_select = AsyncMock()
    mock_customers_result = MagicMock()
    mock_customers_result.data = []
    mock_customers_select.execute = AsyncMock(return_value=mock_customers_result)
    
    mock_visitors_chain = MagicMock()
    mock_visitors_chain.insert.return_value = mock_visitors_chain
    mock_visitors_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_db = MagicMock()
    
    def table_mock(table_name):
        chain = MagicMock()
        if table_name == "sessions":
            chain.insert.return_value = mock_sessions_insert
        elif table_name == "customers":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = mock_customers_select
        elif table_name == "visitors":
            return mock_visitors_chain
        return chain
    
    mock_db.table = table_mock
    
    with patch('engine.api.widget.load_client_config', return_value=mock_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        client = TestClient(app)
        response = client.post(
            "/chat/test-client/session",
            json={"phone": "99998888"}  # New number
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        
        # Verify visitors insert was called with customer_id=None
        call_args = mock_visitors_chain.insert.call_args[0][0]
        assert call_args["customer_id"] is None
        assert call_args["phone"] == "6599998888"  # Normalized


def test_session_without_phone_creates_visitor(app, mock_env_vars, clear_client_config_cache):
    """Integration test: session creation without phone creates visitor without link."""
    
    mock_config = MagicMock()
    mock_config.widget_enabled = True
    mock_config.widget_welcome_message = "Welcome!"
    
    mock_sessions_insert = AsyncMock()
    mock_sessions_insert.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-session"}]))
    
    mock_visitors_chain = MagicMock()
    mock_visitors_chain.insert.return_value = mock_visitors_chain
    mock_visitors_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_db = MagicMock()
    
    def table_mock(table_name):
        chain = MagicMock()
        if table_name == "sessions":
            chain.insert.return_value = mock_sessions_insert
        elif table_name == "visitors":
            return mock_visitors_chain
        return chain
    
    mock_db.table = table_mock
    
    with patch('engine.api.widget.load_client_config', return_value=mock_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        client = TestClient(app)
        response = client.post(
            "/chat/test-client/session",
            json={"name": "Anonymous User"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        
        # Verify visitors insert was called
        mock_visitors_chain.insert.assert_called_once()
        call_args = mock_visitors_chain.insert.call_args[0][0]
        assert call_args["customer_id"] is None
        assert call_args["phone"] is None
        assert call_args["name"] == "Anonymous User"


def test_session_identity_lookup_failure_is_nonfatal(app, mock_env_vars, clear_client_config_cache):
    """Integration test: identity lookup failure doesn't block session creation."""
    
    mock_config = MagicMock()
    mock_config.widget_enabled = True
    mock_config.widget_welcome_message = "Welcome!"
    
    mock_sessions_insert = AsyncMock()
    mock_sessions_insert.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-session"}]))
    
    # Customers query raises exception
    mock_customers_select = AsyncMock()
    mock_customers_select.execute = AsyncMock(side_effect=Exception("Database connection failed"))
    
    mock_visitors_chain = MagicMock()
    mock_visitors_chain.insert.return_value = mock_visitors_chain
    mock_visitors_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_db = MagicMock()
    
    def table_mock(table_name):
        chain = MagicMock()
        if table_name == "sessions":
            chain.insert.return_value = mock_sessions_insert
        elif table_name == "customers":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = mock_customers_select
        elif table_name == "visitors":
            return mock_visitors_chain
        return chain
    
    mock_db.table = table_mock
    
    with patch('engine.api.widget.load_client_config', return_value=mock_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        client = TestClient(app)
        response = client.post(
            "/chat/test-client/session",
            json={"phone": "91234567"}
        )
        
        # Should still return 200 even though customer lookup failed
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["welcome_message"] == "Welcome!"
        
        # Verify visitors insert was still called (with customer_id=None due to failure)
        mock_visitors_chain.insert.assert_called_once()


def test_session_empty_body_backward_compatible(app, mock_env_vars, clear_client_config_cache):
    """Integration test: empty body request is backward compatible."""
    
    mock_config = MagicMock()
    mock_config.widget_enabled = True
    mock_config.widget_welcome_message = "Hi there!"
    
    mock_sessions_insert = AsyncMock()
    mock_sessions_insert.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-session"}]))
    
    mock_visitors_chain = MagicMock()
    mock_visitors_chain.insert.return_value = mock_visitors_chain
    mock_visitors_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_db = MagicMock()
    
    def table_mock(table_name):
        chain = MagicMock()
        if table_name == "sessions":
            chain.insert.return_value = mock_sessions_insert
        elif table_name == "visitors":
            return mock_visitors_chain
        return chain
    
    mock_db.table = table_mock
    
    with patch('engine.api.widget.load_client_config', return_value=mock_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db):
        
        client = TestClient(app)
        # Send empty JSON body
        response = client.post(
            "/chat/test-client/session",
            json={}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["welcome_message"] == "Hi there!"
        
        # Verify visitors insert was called with all None values
        call_args = mock_visitors_chain.insert.call_args[0][0]
        assert call_args["name"] is None
        assert call_args["email"] is None
        assert call_args["phone"] is None
        assert call_args["customer_id"] is None
