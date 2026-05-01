"""
Unit tests for widget_handler.py — widget message processing pipeline.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from engine.core.widget_handler import handle_widget_message, HOLDING_REPLY


@pytest.mark.asyncio
async def test_handle_widget_message_normal_flow(mock_env_vars, clear_client_config_cache):
    """Test normal message flow without escalation."""
    # Mock load_client_config
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    # Mock get_client_db
    mock_db = MagicMock()
    
    # Mock interactions_log insert (inbound + outbound)
    mock_insert_chain = MagicMock()
    mock_insert_chain.insert.return_value = mock_insert_chain
    mock_insert_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock visitors query (no escalation)
    mock_visitor_chain = MagicMock()
    mock_visitor_chain.select.return_value = mock_visitor_chain
    mock_visitor_chain.eq.return_value = mock_visitor_chain
    mock_visitor_chain.limit.return_value = mock_visitor_chain
    mock_visitor_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock interactions_log history query
    mock_history_chain = MagicMock()
    mock_history_chain.select.return_value = mock_history_chain
    mock_history_chain.eq.return_value = mock_history_chain
    mock_history_chain.order.return_value = mock_history_chain
    mock_history_chain.limit.return_value = mock_history_chain
    mock_history_chain.execute = AsyncMock(return_value=MagicMock(data=[
        {"message_text": "Hi", "direction": "inbound", "created_at": "2026-05-01T10:00:00Z"},
        {"message_text": "Hello!", "direction": "outbound", "created_at": "2026-05-01T10:00:01Z"},
    ]))
    
    def mock_table(table_name):
        if table_name == "interactions_log":
            # First call = inbound log, second = history, third = outbound log
            return mock_insert_chain
        elif table_name == "visitors":
            return mock_visitor_chain
        return MagicMock()
    
    mock_db.table = mock_table
    
    # Mock build_system_message
    mock_system_message = "You are a helpful assistant."
    
    # Mock run_agent
    mock_agent_reply = "Hello! How can I help you?"
    
    with patch('engine.core.widget_handler.load_client_config', return_value=mock_client_config), \
         patch('engine.core.widget_handler.get_client_db', return_value=mock_db), \
         patch('engine.core.widget_handler.build_system_message', return_value=mock_system_message), \
         patch('engine.core.widget_handler.build_tool_definitions', return_value=[]), \
         patch('engine.core.widget_handler.build_tool_dispatch', return_value={}), \
         patch('engine.core.widget_handler.run_agent', return_value=mock_agent_reply):
        
        reply, escalated = await handle_widget_message(
            client_id="test-client",
            session_id="test-session-123",
            message="Hi there",
        )
        
        assert reply == mock_agent_reply
        assert escalated is False
        
        # Verify interactions_log was called for inbound and outbound
        assert mock_insert_chain.insert.call_count >= 2


@pytest.mark.asyncio
async def test_handle_widget_message_escalated(mock_env_vars, clear_client_config_cache):
    """Test message handling when visitor is escalated."""
    # Mock load_client_config
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    # Mock get_client_db
    mock_db = MagicMock()
    
    # Mock interactions_log insert
    mock_insert_chain = MagicMock()
    mock_insert_chain.insert.return_value = mock_insert_chain
    mock_insert_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock visitors query (escalation_flag=True)
    mock_visitor_chain = MagicMock()
    mock_visitor_chain.select.return_value = mock_visitor_chain
    mock_visitor_chain.eq.return_value = mock_visitor_chain
    mock_visitor_chain.limit.return_value = mock_visitor_chain
    mock_visitor_chain.execute = AsyncMock(return_value=MagicMock(data=[
        {"visitor_id": "visitor-123", "escalation_flag": True}
    ]))
    
    def mock_table(table_name):
        if table_name == "interactions_log":
            return mock_insert_chain
        elif table_name == "visitors":
            return mock_visitor_chain
        return MagicMock()
    
    mock_db.table = mock_table
    
    with patch('engine.core.widget_handler.load_client_config', return_value=mock_client_config), \
         patch('engine.core.widget_handler.get_client_db', return_value=mock_db), \
         patch('engine.core.widget_handler.run_agent') as mock_run_agent:
        
        reply, escalated = await handle_widget_message(
            client_id="test-client",
            session_id="test-session-123",
            message="I need help",
        )
        
        assert reply == HOLDING_REPLY
        assert escalated is True
        
        # Verify agent was NOT called
        mock_run_agent.assert_not_called()
        
        # Verify holding reply was logged
        assert mock_insert_chain.insert.call_count >= 2


@pytest.mark.asyncio
async def test_handle_widget_message_no_visitor_row(mock_env_vars, clear_client_config_cache):
    """Test message handling when no visitor row exists (not escalated)."""
    # Mock load_client_config
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    # Mock get_client_db
    mock_db = MagicMock()
    
    # Mock interactions_log insert
    mock_insert_chain = MagicMock()
    mock_insert_chain.insert.return_value = mock_insert_chain
    mock_insert_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock visitors query (empty result = no visitor row)
    mock_visitor_chain = MagicMock()
    mock_visitor_chain.select.return_value = mock_visitor_chain
    mock_visitor_chain.eq.return_value = mock_visitor_chain
    mock_visitor_chain.limit.return_value = mock_visitor_chain
    mock_visitor_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock history query
    mock_history_chain = MagicMock()
    mock_history_chain.select.return_value = mock_history_chain
    mock_history_chain.eq.return_value = mock_history_chain
    mock_history_chain.order.return_value = mock_history_chain
    mock_history_chain.limit.return_value = mock_history_chain
    mock_history_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    def mock_table(table_name):
        if table_name == "interactions_log":
            return mock_insert_chain
        elif table_name == "visitors":
            return mock_visitor_chain
        return MagicMock()
    
    mock_db.table = mock_table
    
    # Mock build_system_message
    mock_system_message = "You are a helpful assistant."
    
    # Mock run_agent
    mock_agent_reply = "Hello!"
    
    with patch('engine.core.widget_handler.load_client_config', return_value=mock_client_config), \
         patch('engine.core.widget_handler.get_client_db', return_value=mock_db), \
         patch('engine.core.widget_handler.build_system_message', return_value=mock_system_message), \
         patch('engine.core.widget_handler.build_tool_definitions', return_value=[]), \
         patch('engine.core.widget_handler.build_tool_dispatch', return_value={}), \
         patch('engine.core.widget_handler.run_agent', return_value=mock_agent_reply) as mock_run_agent:
        
        reply, escalated = await handle_widget_message(
            client_id="test-client",
            session_id="test-session-123",
            message="Hello",
        )
        
        assert reply == mock_agent_reply
        assert escalated is False
        
        # Verify agent WAS called (no escalation row = not escalated)
        mock_run_agent.assert_called_once()


@pytest.mark.asyncio
async def test_handle_widget_message_agent_exception(mock_env_vars, clear_client_config_cache):
    """Test message handling when agent throws exception."""
    # Mock load_client_config
    mock_client_config = MagicMock()
    mock_client_config.widget_enabled = True
    
    # Mock get_client_db
    mock_db = MagicMock()
    
    # Mock interactions_log insert
    mock_insert_chain = MagicMock()
    mock_insert_chain.insert.return_value = mock_insert_chain
    mock_insert_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock visitors query (no escalation)
    mock_visitor_chain = MagicMock()
    mock_visitor_chain.select.return_value = mock_visitor_chain
    mock_visitor_chain.eq.return_value = mock_visitor_chain
    mock_visitor_chain.limit.return_value = mock_visitor_chain
    mock_visitor_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock history query
    mock_history_chain = MagicMock()
    mock_history_chain.select.return_value = mock_history_chain
    mock_history_chain.eq.return_value = mock_history_chain
    mock_history_chain.order.return_value = mock_history_chain
    mock_history_chain.limit.return_value = mock_history_chain
    mock_history_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    def mock_table(table_name):
        if table_name == "interactions_log":
            return mock_insert_chain
        elif table_name == "visitors":
            return mock_visitor_chain
        return MagicMock()
    
    mock_db.table = mock_table
    
    # Mock build_system_message
    mock_system_message = "You are a helpful assistant."
    
    with patch('engine.core.widget_handler.load_client_config', return_value=mock_client_config), \
         patch('engine.core.widget_handler.get_client_db', return_value=mock_db), \
         patch('engine.core.widget_handler.build_system_message', return_value=mock_system_message), \
         patch('engine.core.widget_handler.build_tool_definitions', return_value=[]), \
         patch('engine.core.widget_handler.build_tool_dispatch', return_value={}), \
         patch('engine.core.widget_handler.run_agent', side_effect=Exception("Agent failed")):
        
        reply, escalated = await handle_widget_message(
            client_id="test-client",
            session_id="test-session-123",
            message="Hello",
        )
        
        # Should return safe error message (from agent exception handler in widget_handler.py)
        assert "try again" in reply.lower()
        assert escalated is False
