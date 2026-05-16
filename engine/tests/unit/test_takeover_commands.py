"""
Unit tests for takeover commands in reset_handler.py.

Tests:
- Takeover command ("take") sets takeover_flag
- Takeover command logs to takeover_tracking
- Takeover command sends confirmation
- Release command ("done") clears takeover_flag
- Release command clears both takeover and escalation flags
- Release command syncs to Sheets
- Status command lists active takeovers
- Status command shows no takeovers when none active
- Invalid command sends help message
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from engine.core.reset_handler import (
    handle_human_agent_message,
    _handle_takeover_command,
    _handle_release_command,
    _handle_status_command,
)


def _make_db(query_results=None):
    """
    Build a mock Supabase client that returns different results based on table name.
    
    Args:
        query_results: Dict mapping table names to mock response data
    """
    if query_results is None:
        query_results = {}
    
    def table_factory(table_name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.insert.return_value = chain
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.is_.return_value = chain
        chain.limit.return_value = chain
        chain.order.return_value = chain
        
        mock_response = MagicMock()
        mock_response.data = query_results.get(table_name, [])
        chain.execute = AsyncMock(return_value=mock_response)
        
        return chain
    
    db = MagicMock()
    db.table.side_effect = table_factory
    
    return db


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_takeover_command_sets_flag(mock_client_config_obj):
    """'take' command sets takeover_flag=True for matching customer."""
    db = _make_db({
        "customers": [{
            "phone_number": "6591234567",
            "customer_name": "John Tan",
            "takeover_flag": False,
        }]
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock) as mock_send:
        await _handle_takeover_command(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="+6598765432",
            context_message_id="wamid.alert123",
        )
    
    # Verify update was called with takeover flags
    update_calls = [call for call in db.table.call_args_list if call[0][0] == "customers"]
    assert len(update_calls) > 0
    
    # Verify confirmation sent
    mock_send.assert_called()
    assert "Taking over" in mock_send.call_args[0][2]


@pytest.mark.asyncio
async def test_takeover_command_logs_to_tracking(mock_client_config_obj):
    """'take' command inserts into takeover_tracking table."""
    db = _make_db({
        "customers": [{
            "phone_number": "6591234567",
            "customer_name": "John Tan",
            "takeover_flag": False,
        }]
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock):
        await _handle_takeover_command(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="+6598765432",
            context_message_id="wamid.alert123",
        )
    
    # Verify insert was called on takeover_tracking
    insert_calls = [call for call in db.table.call_args_list if call[0][0] == "takeover_tracking"]
    assert len(insert_calls) > 0


@pytest.mark.asyncio
async def test_takeover_command_sends_confirmation(mock_client_config_obj):
    """'take' command sends confirmation message with customer name."""
    db = _make_db({
        "customers": [{
            "phone_number": "6591234567",
            "customer_name": "John Tan",
            "takeover_flag": False,
        }]
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock) as mock_send:
        await _handle_takeover_command(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="+6598765432",
            context_message_id="wamid.alert123",
        )
    
    mock_send.assert_called()
    confirmation_text = mock_send.call_args[0][2]
    assert "Taking over" in confirmation_text
    assert "John Tan" in confirmation_text


@pytest.mark.asyncio
async def test_release_command_clears_takeover_flag(mock_client_config_obj):
    """'done' command clears takeover_flag."""
    db = _make_db({
        "customers": [{
            "phone_number": "6591234567",
            "customer_name": "John Tan",
            "takeover_flag": True,
            "escalation_flag": False,
        }]
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock):
        with patch("engine.core.reset_handler.sync_customer_to_sheets", new_callable=AsyncMock):
            await _handle_release_command(
                db=db,
                client_config=mock_client_config_obj,
                phone_number="+6598765432",
                context_message_id="wamid.alert123",
            )
    
    # Verify update was called with takeover_flag=False
    update_calls = [call for call in db.table.call_args_list if call[0][0] == "customers"]
    assert len(update_calls) > 0


@pytest.mark.asyncio
async def test_release_command_clears_both_flags(mock_client_config_obj):
    """'done' command clears BOTH takeover_flag AND escalation_flag."""
    db = _make_db({
        "customers": [{
            "phone_number": "6591234567",
            "customer_name": "John Tan",
            "takeover_flag": True,
            "escalation_flag": True,
        }]
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock) as mock_send:
        with patch("engine.core.reset_handler.sync_customer_to_sheets", new_callable=AsyncMock):
            await _handle_release_command(
                db=db,
                client_config=mock_client_config_obj,
                phone_number="+6598765432",
                context_message_id="wamid.alert123",
            )
    
    # Verify confirmation mentions both flags cleared
    confirmation_text = mock_send.call_args[0][2]
    assert "takeover" in confirmation_text.lower()
    assert "escalation" in confirmation_text.lower()


@pytest.mark.asyncio
async def test_release_command_syncs_to_sheets(mock_client_config_obj):
    """'done' command triggers Sheets sync."""
    db = _make_db({
        "customers": [{
            "phone_number": "6591234567",
            "customer_name": "John Tan",
            "takeover_flag": True,
            "escalation_flag": False,
        }]
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock):
        with patch("engine.core.reset_handler.sync_customer_to_sheets", new_callable=AsyncMock) as mock_sync:
            with patch("asyncio.create_task") as mock_create_task:
                await _handle_release_command(
                    db=db,
                    client_config=mock_client_config_obj,
                    phone_number="+6598765432",
                    context_message_id="wamid.alert123",
                )
    
    # Verify create_task was called (fire-and-forget Sheets sync)
    assert mock_create_task.called


@pytest.mark.asyncio
async def test_status_command_lists_active_takeovers(mock_client_config_obj):
    """'//status' command lists all customers with takeover_flag=True."""
    now = datetime.now(timezone.utc)
    db = _make_db({
        "customers": [
            {
                "phone_number": "6591234567",
                "customer_name": "John Tan",
                "takeover_at": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "phone_number": "6598765432",
                "customer_name": "Mary Lim",
                "takeover_at": (now - timedelta(minutes=45)).isoformat(),
            },
        ]
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock) as mock_send:
        await _handle_status_command(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="+6598888888",
        )
    
    mock_send.assert_called_once()
    status_text = mock_send.call_args[0][2]
    assert "Active takeovers (2)" in status_text
    assert "John Tan" in status_text
    assert "Mary Lim" in status_text


@pytest.mark.asyncio
async def test_status_command_no_active_takeovers(mock_client_config_obj):
    """'//status' command reports when no active takeovers."""
    db = _make_db({
        "customers": []  # No active takeovers
    })
    
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock) as mock_send:
        await _handle_status_command(
            db=db,
            client_config=mock_client_config_obj,
            phone_number="+6598888888",
        )
    
    mock_send.assert_called_once()
    status_text = mock_send.call_args[0][2]
    assert "No active takeovers" in status_text


@pytest.mark.asyncio
async def test_invalid_command_sends_help(mock_client_config_obj):
    """Unrecognized keyword sends help message."""
    with patch("engine.core.reset_handler.send_message", new_callable=AsyncMock) as mock_send:
        await handle_human_agent_message(
            db=MagicMock(),
            client_config=mock_client_config_obj,
            phone_number="+6598888888",
            message_text="invalid",
            context_message_id="wamid.alert123",
        )
    
    mock_send.assert_called_once()
    help_text = mock_send.call_args[0][2]
    assert "Valid commands" in help_text
    assert "take" in help_text
    assert "done" in help_text
    assert "//status" in help_text


# Import timedelta for test_status_command_lists_active_takeovers
from datetime import timedelta
