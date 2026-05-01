"""Unit tests for Slice 3: cross-channel identity linking."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from engine.api.widget import _normalize_phone


@pytest.mark.asyncio
async def test_create_session_with_phone_matches_customer(mock_env_vars, clear_client_config_cache):
    """Test session creation with phone that matches existing customer."""
    from engine.api.widget import create_session, CreateSessionRequest
    
    # Mock client config
    mock_config = MagicMock()
    mock_config.widget_enabled = True
    mock_config.widget_welcome_message = "Welcome!"
    
    # Mock Supabase responses
    mock_sessions_insert = AsyncMock()
    mock_sessions_insert.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-session"}]))
    
    mock_customers_select = AsyncMock()
    mock_customers_result = MagicMock()
    mock_customers_result.data = [{"id": "cust-123"}]
    mock_customers_select.execute = AsyncMock(return_value=mock_customers_result)
    
    # Self-referential chain: .insert(data) returns self, .execute() is the AsyncMock
    mock_visitors_chain = MagicMock()
    mock_visitors_chain.insert.return_value = mock_visitors_chain
    mock_visitors_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock the table chain
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
         patch('engine.api.widget.get_client_db', return_value=mock_db), \
         patch('engine.api.widget.uuid.uuid4', return_value=MagicMock(hex="test-session-id")):
        
        request = CreateSessionRequest(name="John", phone="91234567")
        response = await create_session(client_id="test-client", request=request)
        
        # Assert session created
        assert response.session_id
        assert response.welcome_message == "Welcome!"
        
        # Assert visitors insert was called with customer_id
        mock_visitors_chain.insert.assert_called_once()
        call_args = mock_visitors_chain.insert.call_args[0][0]
        assert call_args["customer_id"] == "cust-123"
        assert call_args["phone"] == "6591234567"  # Normalized


@pytest.mark.asyncio
async def test_create_session_with_phone_no_match(mock_env_vars, clear_client_config_cache):
    """Test session creation with phone that doesn't match any customer."""
    from engine.api.widget import create_session, CreateSessionRequest
    
    mock_config = MagicMock()
    mock_config.widget_enabled = True
    mock_config.widget_welcome_message = "Welcome!"
    
    mock_sessions_insert = AsyncMock()
    mock_sessions_insert.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-session"}]))
    
    # Customers query returns empty
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
         patch('engine.api.widget.get_client_db', return_value=mock_db), \
         patch('engine.api.widget.uuid.uuid4', return_value=MagicMock(hex="test-session-id")):
        
        request = CreateSessionRequest(name="John", phone="91234567")
        response = await create_session(client_id="test-client", request=request)
        
        assert response.session_id
        
        # Assert visitors insert was called with customer_id=None
        call_args = mock_visitors_chain.insert.call_args[0][0]
        assert call_args["customer_id"] is None
        assert call_args["phone"] == "6591234567"


@pytest.mark.asyncio
async def test_create_session_no_phone_skips_customer_lookup(mock_env_vars, clear_client_config_cache):
    """Test session creation without phone skips customer lookup."""
    from engine.api.widget import create_session, CreateSessionRequest
    
    mock_config = MagicMock()
    mock_config.widget_enabled = True
    mock_config.widget_welcome_message = "Welcome!"
    
    mock_sessions_insert = AsyncMock()
    mock_sessions_insert.execute = AsyncMock(return_value=MagicMock(data=[{"session_id": "test-session"}]))
    
    mock_visitors_chain = MagicMock()
    mock_visitors_chain.insert.return_value = mock_visitors_chain
    mock_visitors_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_db = MagicMock()
    customers_table_called = False
    
    def table_mock(table_name):
        nonlocal customers_table_called
        chain = MagicMock()
        if table_name == "sessions":
            chain.insert.return_value = mock_sessions_insert
        elif table_name == "customers":
            customers_table_called = True
        elif table_name == "visitors":
            return mock_visitors_chain
        return chain
    
    mock_db.table = table_mock
    
    with patch('engine.api.widget.load_client_config', return_value=mock_config), \
         patch('engine.api.widget.get_client_db', return_value=mock_db), \
         patch('engine.api.widget.uuid.uuid4', return_value=MagicMock(hex="test-session-id")):
        
        request = CreateSessionRequest(name="John")  # No phone
        response = await create_session(client_id="test-client", request=request)
        
        assert response.session_id
        
        # Assert customers table was NOT queried
        assert not customers_table_called
        
        # Assert visitors insert was called with customer_id=None
        call_args = mock_visitors_chain.insert.call_args[0][0]
        assert call_args["customer_id"] is None
        assert call_args["phone"] is None


@pytest.mark.asyncio
async def test_create_session_empty_body(mock_env_vars, clear_client_config_cache):
    """Test session creation with empty body (backward compatibility)."""
    from engine.api.widget import create_session, CreateSessionRequest
    
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
         patch('engine.api.widget.get_client_db', return_value=mock_db), \
         patch('engine.api.widget.uuid.uuid4', return_value=MagicMock(hex="test-session-id")):
        
        request = CreateSessionRequest()  # Empty
        response = await create_session(client_id="test-client", request=request)
        
        assert response.session_id
        assert response.welcome_message == "Welcome!"
        
        # Assert visitors insert was called with all None
        call_args = mock_visitors_chain.insert.call_args[0][0]
        assert call_args["name"] is None
        assert call_args["email"] is None
        assert call_args["phone"] is None
        assert call_args["customer_id"] is None


def test_normalize_phone_local_8_digit():
    """Test normalization of local 8-digit SG number."""
    assert _normalize_phone("91234567") == "6591234567"
    assert _normalize_phone("81234567") == "6581234567"
    assert _normalize_phone("61234567") == "6561234567"


def test_normalize_phone_with_plus():
    """Test normalization of number with + prefix."""
    assert _normalize_phone("+6591234567") == "6591234567"
    assert _normalize_phone("+65 9123 4567") == "6591234567"


def test_normalize_phone_already_normalized():
    """Test normalization of already normalized number."""
    assert _normalize_phone("6591234567") == "6591234567"


def test_normalize_phone_with_formatting():
    """Test normalization strips spaces, dashes, dots."""
    assert _normalize_phone("9123-4567") == "6591234567"
    assert _normalize_phone("9123.4567") == "6591234567"
    assert _normalize_phone("9123 4567") == "6591234567"


@pytest.mark.asyncio
async def test_widget_handler_with_linked_customer_fetches_wa_history(mock_env_vars, clear_client_config_cache):
    """Test widget handler fetches WhatsApp history when customer is linked."""
    from engine.core.widget_handler import handle_widget_message
    
    mock_config = MagicMock()
    mock_config.widget_welcome_message = "Welcome!"
    
    # Mock DB responses
    # 1. interactions_log insert (inbound)
    mock_insert_inbound = AsyncMock()
    mock_insert_inbound.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # 2. visitors escalation gate - no escalation
    mock_visitors_escalation = AsyncMock()
    mock_visitors_result = MagicMock()
    mock_visitors_result.data = [{"visitor_id": "vis-1", "escalation_flag": False}]
    mock_visitors_escalation.execute = AsyncMock(return_value=mock_visitors_result)
    
    # 3. widget history - 2 messages
    mock_widget_history = AsyncMock()
    mock_widget_history_result = MagicMock()
    # DESC order (newest first) — mirrors actual Supabase ORDER BY created_at DESC
    mock_widget_history_result.data = [
        {"message_text": "Hello!", "direction": "outbound", "created_at": "2026-01-01T00:01:00Z"},
        {"message_text": "Hi", "direction": "inbound", "created_at": "2026-01-01T00:00:00Z"},
    ]
    mock_widget_history.execute = AsyncMock(return_value=mock_widget_history_result)
    
    # 4. visitors customer_id lookup - linked
    mock_visitors_customer = AsyncMock()
    mock_visitors_customer_result = MagicMock()
    mock_visitors_customer_result.data = [{"customer_id": "cust-123"}]
    mock_visitors_customer.execute = AsyncMock(return_value=mock_visitors_customer_result)
    
    # 5. customers phone lookup
    mock_customers = AsyncMock()
    mock_customers_result = MagicMock()
    mock_customers_result.data = [{"phone_number": "6591234567"}]
    mock_customers.execute = AsyncMock(return_value=mock_customers_result)
    
    # 6. WhatsApp history - 2 messages
    mock_wa_history = AsyncMock()
    mock_wa_history_result = MagicMock()
    # DESC order (newest first) — mirrors actual Supabase ORDER BY created_at DESC
    mock_wa_history_result.data = [
        {"message_text": "Sure, let me help", "direction": "outbound", "created_at": "2025-12-01T00:01:00Z"},
        {"message_text": "Need aircon service", "direction": "inbound", "created_at": "2025-12-01T00:00:00Z"},
    ]
    mock_wa_history.execute = AsyncMock(return_value=mock_wa_history_result)
    
    # 7. interactions_log insert (outbound)
    mock_insert_outbound = AsyncMock()
    mock_insert_outbound.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    # Mock the table chain
    mock_db = MagicMock()
    call_count = {"interactions_log": 0, "visitors": 0}
    
    def table_mock(table_name):
        chain = MagicMock()
        
        if table_name == "interactions_log":
            call_count["interactions_log"] += 1
            if call_count["interactions_log"] == 1:
                # First call: inbound insert
                chain.insert.return_value = mock_insert_inbound
            elif call_count["interactions_log"] == 2:
                # Second call: widget history fetch
                chain.select.return_value = chain
                chain.eq = MagicMock(side_effect=lambda k, v: chain)
                chain.order.return_value = chain
                chain.limit.return_value = mock_widget_history
            elif call_count["interactions_log"] == 3:
                # Third call: WhatsApp history fetch
                chain.select.return_value = chain
                chain.eq = MagicMock(side_effect=lambda k, v: chain)
                chain.order.return_value = chain
                chain.limit.return_value = mock_wa_history
            elif call_count["interactions_log"] == 4:
                # Fourth call: outbound insert
                chain.insert.return_value = mock_insert_outbound
                
        elif table_name == "visitors":
            call_count["visitors"] += 1
            if call_count["visitors"] == 1:
                # First call: escalation gate
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.limit.return_value = mock_visitors_escalation
            elif call_count["visitors"] == 2:
                # Second call: customer_id lookup
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.limit.return_value = mock_visitors_customer
                
        elif table_name == "customers":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = mock_customers
            
        return chain
    
    mock_db.table = table_mock
    
    # Mock context builder and agent
    mock_system_message = "You are a helpful assistant."
    
    with patch('engine.core.widget_handler.get_client_db', return_value=mock_db), \
         patch('engine.core.widget_handler.load_client_config', return_value=mock_config), \
         patch('engine.core.widget_handler.build_system_message', return_value=mock_system_message), \
         patch('engine.core.widget_handler.run_agent', return_value="How can I help?") as mock_agent, \
         patch('engine.core.widget_handler.build_tool_definitions', return_value=[]), \
         patch('engine.core.widget_handler.build_tool_dispatch', return_value={}):
        
        reply, escalated = await handle_widget_message(
            client_id="test-client",
            session_id="test-session",
            message="I need help",
        )
        
        assert reply == "How can I help?"
        assert escalated is False
        
        # Assert run_agent was called with messages including WhatsApp history
        mock_agent.assert_called_once()
        call_args = mock_agent.call_args
        messages = call_args[1]["messages"]
        
        # Should have 2 WA messages + 2 widget messages = 4 total
        assert len(messages) == 4
        
        # First 2 should be WhatsApp with prefix
        assert "[Prior WhatsApp]" in messages[0]["content"]
        assert "[Prior WhatsApp]" in messages[1]["content"]
        
        # Last 2 should be widget history
        assert messages[2]["content"] == "Hi"
        assert messages[3]["content"] == "Hello!"


@pytest.mark.asyncio
async def test_widget_handler_without_linked_customer_no_wa_history(mock_env_vars, clear_client_config_cache):
    """Test widget handler without linked customer doesn't fetch WhatsApp history."""
    from engine.core.widget_handler import handle_widget_message
    
    mock_config = MagicMock()
    mock_config.widget_welcome_message = "Welcome!"
    
    # Mock DB responses
    mock_insert_inbound = AsyncMock()
    mock_insert_inbound.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_visitors_escalation = AsyncMock()
    mock_visitors_result = MagicMock()
    mock_visitors_result.data = [{"visitor_id": "vis-1", "escalation_flag": False}]
    mock_visitors_escalation.execute = AsyncMock(return_value=mock_visitors_result)
    
    mock_widget_history = AsyncMock()
    mock_widget_history_result = MagicMock()
    mock_widget_history_result.data = [
        {"message_text": "Hi", "direction": "inbound", "created_at": "2026-01-01T00:00:00Z"},
    ]
    mock_widget_history.execute = AsyncMock(return_value=mock_widget_history_result)
    
    # visitors customer_id lookup - NOT linked
    mock_visitors_customer = AsyncMock()
    mock_visitors_customer_result = MagicMock()
    mock_visitors_customer_result.data = [{"customer_id": None}]
    mock_visitors_customer.execute = AsyncMock(return_value=mock_visitors_customer_result)
    
    mock_insert_outbound = AsyncMock()
    mock_insert_outbound.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_db = MagicMock()
    call_count = {"interactions_log": 0, "visitors": 0}
    
    def table_mock(table_name):
        chain = MagicMock()
        
        if table_name == "interactions_log":
            call_count["interactions_log"] += 1
            if call_count["interactions_log"] == 1:
                chain.insert.return_value = mock_insert_inbound
            elif call_count["interactions_log"] == 2:
                chain.select.return_value = chain
                chain.eq = MagicMock(side_effect=lambda k, v: chain)
                chain.order.return_value = chain
                chain.limit.return_value = mock_widget_history
            elif call_count["interactions_log"] == 3:
                chain.insert.return_value = mock_insert_outbound
                
        elif table_name == "visitors":
            call_count["visitors"] += 1
            if call_count["visitors"] == 1:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.limit.return_value = mock_visitors_escalation
            elif call_count["visitors"] == 2:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.limit.return_value = mock_visitors_customer
                
        return chain
    
    mock_db.table = table_mock
    
    mock_system_message = "You are a helpful assistant."
    
    with patch('engine.core.widget_handler.get_client_db', return_value=mock_db), \
         patch('engine.core.widget_handler.load_client_config', return_value=mock_config), \
         patch('engine.core.widget_handler.build_system_message', return_value=mock_system_message), \
         patch('engine.core.widget_handler.run_agent', return_value="How can I help?") as mock_agent, \
         patch('engine.core.widget_handler.build_tool_definitions', return_value=[]), \
         patch('engine.core.widget_handler.build_tool_dispatch', return_value={}):
        
        reply, escalated = await handle_widget_message(
            client_id="test-client",
            session_id="test-session",
            message="I need help",
        )
        
        assert reply == "How can I help?"
        assert escalated is False
        
        # Assert run_agent was called with only widget history (no WhatsApp)
        mock_agent.assert_called_once()
        call_args = mock_agent.call_args
        messages = call_args[1]["messages"]
        
        # Should have only 1 widget message
        assert len(messages) == 1
        assert messages[0]["content"] == "Hi"
        
        # Should NOT have any WhatsApp prefix
        for msg in messages:
            assert "[Prior WhatsApp]" not in msg["content"]


@pytest.mark.asyncio
async def test_widget_handler_cross_channel_failure_is_nonfatal(mock_env_vars, clear_client_config_cache):
    """Test widget handler continues if cross-channel history fetch fails."""
    from engine.core.widget_handler import handle_widget_message
    
    mock_config = MagicMock()
    mock_config.widget_welcome_message = "Welcome!"
    
    # Mock DB responses
    mock_insert_inbound = AsyncMock()
    mock_insert_inbound.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_visitors_escalation = AsyncMock()
    mock_visitors_result = MagicMock()
    mock_visitors_result.data = [{"visitor_id": "vis-1", "escalation_flag": False}]
    mock_visitors_escalation.execute = AsyncMock(return_value=mock_visitors_result)
    
    mock_widget_history = AsyncMock()
    mock_widget_history_result = MagicMock()
    mock_widget_history_result.data = [
        {"message_text": "Hi", "direction": "inbound", "created_at": "2026-01-01T00:00:00Z"},
    ]
    mock_widget_history.execute = AsyncMock(return_value=mock_widget_history_result)
    
    # visitors customer_id lookup - raises exception
    mock_visitors_customer = AsyncMock()
    mock_visitors_customer.execute = AsyncMock(side_effect=Exception("DB error"))
    
    mock_insert_outbound = AsyncMock()
    mock_insert_outbound.execute = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_db = MagicMock()
    call_count = {"interactions_log": 0, "visitors": 0}
    
    def table_mock(table_name):
        chain = MagicMock()
        
        if table_name == "interactions_log":
            call_count["interactions_log"] += 1
            if call_count["interactions_log"] == 1:
                chain.insert.return_value = mock_insert_inbound
            elif call_count["interactions_log"] == 2:
                chain.select.return_value = chain
                chain.eq = MagicMock(side_effect=lambda k, v: chain)
                chain.order.return_value = chain
                chain.limit.return_value = mock_widget_history
            elif call_count["interactions_log"] == 3:
                chain.insert.return_value = mock_insert_outbound
                
        elif table_name == "visitors":
            call_count["visitors"] += 1
            if call_count["visitors"] == 1:
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.limit.return_value = mock_visitors_escalation
            elif call_count["visitors"] == 2:
                # Second call raises exception
                chain.select.return_value = chain
                chain.eq.return_value = chain
                chain.limit.return_value = mock_visitors_customer
                
        return chain
    
    mock_db.table = table_mock
    
    mock_system_message = "You are a helpful assistant."
    
    with patch('engine.core.widget_handler.get_client_db', return_value=mock_db), \
         patch('engine.core.widget_handler.load_client_config', return_value=mock_config), \
         patch('engine.core.widget_handler.build_system_message', return_value=mock_system_message), \
         patch('engine.core.widget_handler.run_agent', return_value="How can I help?") as mock_agent, \
         patch('engine.core.widget_handler.build_tool_definitions', return_value=[]), \
         patch('engine.core.widget_handler.build_tool_dispatch', return_value={}):
        
        # Should NOT raise exception
        reply, escalated = await handle_widget_message(
            client_id="test-client",
            session_id="test-session",
            message="I need help",
        )
        
        assert reply == "How can I help?"
        assert escalated is False
        
        # Assert run_agent was still called (without WhatsApp history)
        mock_agent.assert_called_once()
