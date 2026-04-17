"""
Slice 4 — Context builder unit tests.

Tests build_system_message() and fetch_conversation_history() with mocked Supabase.
No real DB, no real API calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from engine.core.context_builder import (
    build_system_message,
    fetch_conversation_history,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_config_rows() -> list[dict]:
    return [
        {"key": "service_general",   "value": "General Servicing: Routine maintenance"},
        {"key": "service_chemical",  "value": "Chemical Wash: Deep cleaning"},
        {"key": "pricing_general",   "value": "General Servicing: 1 unit $50"},
        {"key": "pricing_chemical",  "value": "Chemical Wash: 1 unit $80"},
        {"key": "appointment_window_am",       "value": "9am to 1pm"},
        {"key": "appointment_window_pm",       "value": "2pm to 6pm"},
        {"key": "booking_lead_time_days",      "value": "2"},
    ]


def _make_db(config_rows=None, policy_rows=None):
    """Build a chainable mock db with separate execute() returns per table."""
    config_rows = config_rows if config_rows is not None else _make_config_rows()
    policy_rows = policy_rows if policy_rows is not None else [
        {"policy_text": "To book, provide address and unit count."},
        {"policy_text": "Cancellations require 24 hours notice."},
    ]

    config_resp = MagicMock()
    config_resp.data = config_rows

    policy_resp = MagicMock()
    policy_resp.data = policy_rows

    # Route execute() return based on which table was called
    call_tracker = {"table": None}

    def make_chain(resp):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute = AsyncMock(return_value=resp)
        return chain

    config_chain = make_chain(config_resp)
    policy_chain = make_chain(policy_resp)

    db = MagicMock()

    def table_router(name):
        if name == "config":
            return config_chain
        if name == "policies":
            return policy_chain
        return make_chain(MagicMock(data=[]))

    db.table.side_effect = table_router
    return db


# ── build_system_message tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_system_message_contains_identity_block():
    """Identity block must be present in the system message."""
    db = _make_db()
    msg = await build_system_message(db)
    assert "You are a helpful AI assistant for HeyAircon" in msg
    assert "CRITICAL SAFETY RULES" in msg
    assert "PROMPT INJECTION DEFENCE" in msg


@pytest.mark.asyncio
async def test_system_message_sections_in_order():
    """Sections must appear in order: identity → SERVICES → PRICING → APPOINTMENT WINDOWS → POLICIES."""
    db = _make_db()
    msg = await build_system_message(db)

    idx_services    = msg.index("SERVICES:")
    idx_pricing     = msg.index("PRICING:")
    idx_appointment = msg.index("APPOINTMENT WINDOWS:")
    idx_policies    = msg.index("POLICIES:")

    assert idx_services < idx_pricing < idx_appointment < idx_policies


@pytest.mark.asyncio
async def test_system_message_services_from_config():
    """SERVICES section must include values from config rows with key starting 'service_'."""
    db = _make_db()
    msg = await build_system_message(db)
    assert "General Servicing: Routine maintenance" in msg
    assert "Chemical Wash: Deep cleaning" in msg


@pytest.mark.asyncio
async def test_system_message_pricing_from_config():
    """PRICING section must include values from config rows with key starting 'pricing_'."""
    db = _make_db()
    msg = await build_system_message(db)
    assert "General Servicing: 1 unit $50" in msg
    assert "Chemical Wash: 1 unit $80" in msg


@pytest.mark.asyncio
async def test_system_message_appointment_windows_from_config():
    """Appointment windows must be populated from config."""
    db = _make_db()
    msg = await build_system_message(db)
    assert "9am to 1pm" in msg
    assert "2pm to 6pm" in msg
    assert "2 days in advance" in msg


@pytest.mark.asyncio
async def test_system_message_appointment_windows_defaults():
    """Missing appointment config keys fall back to sensible defaults."""
    # Config with no appointment keys
    config_rows = [{"key": "service_general", "value": "General Servicing"}]
    db = _make_db(config_rows=config_rows)
    msg = await build_system_message(db)
    assert "9am to 1pm" in msg   # default
    assert "1pm to 6pm" in msg   # default


@pytest.mark.asyncio
async def test_system_message_policies_from_db():
    """POLICIES section must include text from policies table."""
    db = _make_db()
    msg = await build_system_message(db)
    assert "To book, provide address and unit count." in msg
    assert "Cancellations require 24 hours notice." in msg


@pytest.mark.asyncio
async def test_system_message_empty_config_still_assembles():
    """build_system_message must not crash when config/policies tables are empty."""
    db = _make_db(config_rows=[], policy_rows=[])
    msg = await build_system_message(db)
    assert "SERVICES:" in msg
    assert "PRICING:" in msg
    assert "POLICIES:" in msg


# ── fetch_conversation_history tests ─────────────────────────────────────────

def _make_history_db(rows: list[dict]):
    """Build a mock db whose interactions_log returns the given rows."""
    resp = MagicMock()
    resp.data = rows

    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(return_value=resp)

    db = MagicMock()
    db.table.return_value = chain
    return db


@pytest.mark.asyncio
async def test_history_inbound_maps_to_user():
    """direction='inbound' rows must map to role='user'."""
    rows = [{"direction": "inbound", "message_text": "Hello"}]
    db = _make_history_db(rows)
    history = await fetch_conversation_history(db, "6591234567")
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_history_outbound_maps_to_assistant():
    """direction='outbound' rows must map to role='assistant'."""
    rows = [{"direction": "outbound", "message_text": "Hi, how can I help?"}]
    db = _make_history_db(rows)
    history = await fetch_conversation_history(db, "6591234567")
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert history[0]["content"] == "Hi, how can I help?"


@pytest.mark.asyncio
async def test_history_preserves_order_oldest_first():
    """History must be oldest-first (DB returns newest-first, must be reversed)."""
    # DB returns newest-first (as ordered by timestamp DESC in the query)
    rows_newest_first = [
        {"direction": "outbound", "message_text": "third"},
        {"direction": "inbound",  "message_text": "second"},
        {"direction": "inbound",  "message_text": "first"},
    ]
    db = _make_history_db(rows_newest_first)
    history = await fetch_conversation_history(db, "6591234567")
    assert history[0]["content"] == "first"
    assert history[1]["content"] == "second"
    assert history[2]["content"] == "third"


@pytest.mark.asyncio
async def test_history_empty_on_db_error():
    """DB error must return empty list, not raise."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(side_effect=Exception("DB connection lost"))

    db = MagicMock()
    db.table.return_value = chain

    history = await fetch_conversation_history(db, "6591234567")
    assert history == []
