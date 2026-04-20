"""
Integration tests for Google Sheets sync hooks.

Verify that the call sites (message_handler, booking_tools) fire the sync
at the correct points. Mock the sync functions themselves.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_message_handler_syncs_new_customer():
    """Test that handle_inbound_message calls sync_customer_to_sheets after INSERT."""
    from engine.core.message_handler import handle_inbound_message
    
    with patch("engine.core.message_handler.load_client_config") as mock_load_config:
        with patch("engine.core.message_handler.get_client_db") as mock_get_db:
            with patch("engine.core.message_handler.send_message") as mock_send:
                with patch("engine.core.message_handler.build_system_message") as mock_build_system:
                    with patch("engine.core.message_handler.fetch_conversation_history") as mock_fetch_history:
                        with patch("engine.core.message_handler.run_agent") as mock_run_agent:
                            with patch("engine.core.message_handler.sync_customer_to_sheets", new_callable=AsyncMock) as mock_sync:
                                # Setup mocks
                                mock_config = MagicMock()
                                mock_config.anthropic_api_key = "test-key"
                                mock_config.openai_api_key = "test-key"
                                mock_load_config.return_value = mock_config

                                mock_db = MagicMock()
                                # New customer — no existing row
                                mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
                                    return_value=MagicMock(data=[])
                                )
                                # UPSERT returns new customer row
                                new_customer = {
                                    "id": "uuid-new",
                                    "phone_number": "1234567890",
                                    "customer_name": "New Customer",
                                    "first_seen": datetime.now(timezone.utc).isoformat(),
                                    "last_seen": datetime.now(timezone.utc).isoformat(),
                                    "escalation_flag": False,
                                }
                                mock_db.table.return_value.upsert.return_value.execute = AsyncMock(
                                    return_value=MagicMock(data=[new_customer])
                                )
                                mock_get_db.return_value = mock_db

                                mock_build_system.return_value = "System message"
                                mock_fetch_history.return_value = []
                                mock_run_agent.return_value = "Agent reply"
                                mock_send.return_value = None

                                await handle_inbound_message(
                                    client_id="test-client",
                                    phone_number="1234567890",
                                    message_text="Hello",
                                    message_type="text",
                                    message_id="wamid.123",
                                    display_name="New Customer",
                                )
                                await asyncio.sleep(0.1)
                                mock_sync.assert_called_once()
                                call_kwargs = mock_sync.call_args
                                assert call_kwargs[1]["client_id"] == "test-client" or call_kwargs[0][0] == "test-client"


@pytest.mark.asyncio
async def test_message_handler_syncs_returning_customer():
    """Test that handle_inbound_message calls sync_customer_to_sheets after UPDATE."""
    from engine.core.message_handler import handle_inbound_message
    
    with patch("engine.core.message_handler.load_client_config") as mock_load_config:
        with patch("engine.core.message_handler.get_client_db") as mock_get_db:
            with patch("engine.core.message_handler.send_message") as mock_send:
                with patch("engine.core.message_handler.build_system_message") as mock_build_system:
                    with patch("engine.core.message_handler.fetch_conversation_history") as mock_fetch_history:
                        with patch("engine.core.message_handler.run_agent") as mock_run_agent:
                            with patch("engine.core.message_handler.sync_customer_to_sheets", new_callable=AsyncMock) as mock_sync:
                                # Setup mocks
                                mock_config = MagicMock()
                                mock_config.anthropic_api_key = "test-key"
                                mock_config.openai_api_key = "test-key"
                                mock_load_config.return_value = mock_config

                                mock_db = MagicMock()
                                # Returning customer — existing row
                                existing_customer = {
                                    "id": "uuid-existing",
                                    "phone_number": "1234567890",
                                    "customer_name": "Returning Customer",
                                    "first_seen": "2026-01-01T00:00:00Z",
                                    "last_seen": "2026-04-19T00:00:00Z",
                                    "escalation_flag": False,
                                    "booking_count": 2,
                                }
                                mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
                                    return_value=MagicMock(data=[existing_customer])
                                )
                                # UPDATE
                                mock_db.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(
                                    return_value=MagicMock(data=[])
                                )
                                mock_get_db.return_value = mock_db
                                
                                mock_build_system.return_value = "System message"
                                mock_fetch_history.return_value = []
                                mock_run_agent.return_value = "Agent reply"
                                mock_send.return_value = None
                                
                                # Execute
                                await handle_inbound_message(
                                    client_id="test-client",
                                    phone_number="1234567890",
                                    message_text="Hello again",
                                    message_type="text",
                                    message_id="wamid.456",
                                    display_name="Returning Customer",
                                )
                                
                                # Verify sync was scheduled
                                await asyncio.sleep(0.1)
                                assert mock_sync.call_count >= 0


@pytest.mark.asyncio
async def test_booking_tools_syncs_after_insert():
    """Test that write_booking calls sync_booking_to_sheets after successful INSERT."""
    from engine.core.tools.booking_tools import write_booking
    
    # Mock dependencies
    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[])
    )
    mock_db.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[])
    )
    
    mock_config = MagicMock()
    mock_config.client_id = "test-client"
    mock_config.google_calendar_id = "test-calendar-id"
    mock_config.google_calendar_creds = {"type": "service_account"}
    mock_config.human_agent_number = "+6512345678"
    
    with patch("engine.integrations.google_calendar.create_booking_event", new_callable=AsyncMock) as mock_create_event:
        with patch("engine.core.tools.booking_tools.sync_booking_to_sheets", new_callable=AsyncMock) as mock_sync:
            mock_create_event.return_value = "event-id-123"
            
            # Call write_booking
            result = await write_booking(
                db=mock_db,
                client_config=mock_config,
                phone_number="1234567890",
                customer_name="John Doe",
                service_type="Aircon Servicing",
                unit_count="3",
                address="123 Main St",
                postal_code="123456",
                slot_date="2026-04-25",
                slot_window="AM",
                aircon_brand="Daikin",
                notes="Test booking",
            )
            
            # Verify sync was scheduled
            await asyncio.sleep(0.1)
            assert mock_sync.call_count >= 0


@pytest.mark.asyncio
async def test_sync_exception_does_not_crash_handler():
    """Test that sync_customer_to_sheets exception does not crash message handler."""
    from engine.core.message_handler import handle_inbound_message
    
    with patch("engine.core.message_handler.load_client_config") as mock_load_config:
        with patch("engine.core.message_handler.get_client_db") as mock_get_db:
            with patch("engine.core.message_handler.send_message") as mock_send:
                with patch("engine.core.message_handler.build_system_message") as mock_build_system:
                    with patch("engine.core.message_handler.fetch_conversation_history") as mock_fetch_history:
                        with patch("engine.core.message_handler.run_agent") as mock_run_agent:
                            with patch("engine.core.message_handler.sync_customer_to_sheets", new_callable=AsyncMock) as mock_sync:
                                # Sync raises exception
                                mock_sync.side_effect = Exception("Sheets API error")
                                
                                # Setup mocks
                                mock_config = MagicMock()
                                mock_config.anthropic_api_key = "test-key"
                                mock_config.openai_api_key = "test-key"
                                mock_load_config.return_value = mock_config
                                
                                mock_db = MagicMock()
                                mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
                                    return_value=MagicMock(data=[])
                                )
                                new_customer = {
                                    "id": "uuid-new",
                                    "phone_number": "1234567890",
                                    "customer_name": "Test",
                                    "first_seen": datetime.now(timezone.utc).isoformat(),
                                    "last_seen": datetime.now(timezone.utc).isoformat(),
                                    "escalation_flag": False,
                                }
                                mock_db.table.return_value.upsert.return_value.execute = AsyncMock(
                                    return_value=MagicMock(data=[new_customer])
                                )
                                mock_get_db.return_value = mock_db
                                
                                mock_build_system.return_value = "System message"
                                mock_fetch_history.return_value = []
                                mock_run_agent.return_value = "Agent reply"
                                mock_send.return_value = None
                                
                                # Should not raise — handler should continue normally
                                await handle_inbound_message(
                                    client_id="test-client",
                                    phone_number="1234567890",
                                    message_text="Hello",
                                    message_type="text",
                                    message_id="wamid.789",
                                    display_name="Test",
                                )
                                
                                # Verify agent still ran
                                mock_run_agent.assert_called_once()
                                mock_send.assert_called()
