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
async def test_system_message_forbids_second_confirmation_before_write_booking():
    """Booking flow must tell the model not to ask for a second pre-write confirmation."""
    db = _make_db()
    msg = await build_system_message(db)
    assert "Do NOT ask for a second confirmation before write_booking" in msg
    assert "The ONLY confirmation you ask for is after the booking summary in Step 5" in msg


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


# ── Service Variations TC-01 through TC-11 ────────────────────────────────────


@pytest.mark.asyncio
async def test_tc01_variation_group_renders_structured_block():
    """TC-01: variation group detected and rendered as structured block."""
    config_rows = [
        {"key": "pricing_general_servicing__standard",
         "value": "General Servicing (standard, ≤15,000 BTU): $80"},
        {"key": "pricing_general_servicing__18_24k",
         "value": "General Servicing (large unit, 18,000–24,000 BTU): $100"},
        {"key": "variation_hint_general_servicing",
         "value": "Is your aircon unit 18,000–24,000 BTU (large unit)?"},
    ]
    db = _make_db(config_rows=config_rows)
    msg = await build_system_message(db)

    # Assertion 1: block header present
    assert "General Servicing: pricing varies by unit size." in msg
    # Assertion 2: standard bullet present
    assert "• General Servicing (standard, ≤15,000 BTU): $80" in msg
    # Assertion 3: large unit bullet present
    assert "• General Servicing (large unit, 18,000–24,000 BTU): $100" in msg
    # Assertion 4: clarification line present verbatim
    assert (
        'Clarification required: before quoting or booking, ask: '
        '"Is your aircon unit 18,000–24,000 BTU (large unit)?"'
    ) in msg
    # Assertion 5: flat bullet form NOT present
    assert "- General Servicing (standard, ≤15,000 BTU): $80" not in msg
    # Assertion 6: variation block appears exactly once
    assert msg.count("General Servicing: pricing varies by unit size.") == 1


@pytest.mark.asyncio
async def test_tc02_hint_text_appears_verbatim_from_config():
    """TC-02: hint text from config appears verbatim; different slug triggers same path."""
    config_rows = [
        {"key": "pricing_deep_clean__studio",
         "value": "Deep Clean (studio): $150"},
        {"key": "pricing_deep_clean__3br",
         "value": "Deep Clean (3-bedroom): $220"},
        {"key": "variation_hint_deep_clean",
         "value": "How many bedrooms does your unit have?"},
    ]
    db = _make_db(config_rows=config_rows)
    msg = await build_system_message(db)

    # Assertion 1: hint text verbatim
    assert (
        'Clarification required: before quoting or booking, ask: '
        '"How many bedrooms does your unit have?"'
    ) in msg
    # Assertion 2: block header for deep_clean
    assert "Deep Clean: pricing varies by unit size." in msg
    # Assertion 3: no general_servicing block (no such rows in this config)
    assert "General Servicing: pricing varies by unit size." not in msg


@pytest.mark.asyncio
async def test_tc03_second_variation_key_not_duplicated():
    """TC-03: second variation key in same group does not produce a duplicate block."""
    config_rows = [
        {"key": "pricing_general_servicing__standard",
         "value": "General Servicing (standard, ≤15,000 BTU): $80"},
        {"key": "pricing_general_servicing__18_24k",
         "value": "General Servicing (large unit, 18,000–24,000 BTU): $100"},
        {"key": "variation_hint_general_servicing",
         "value": "Is your aircon unit 18,000–24,000 BTU (large unit)?"},
    ]
    db = _make_db(config_rows=config_rows)
    msg = await build_system_message(db)

    # Block header appears exactly once
    assert msg.count("General Servicing: pricing varies by unit size.") == 1
    # Clarification question appears exactly once
    assert msg.count(
        'Clarification required: before quoting or booking, ask: '
        '"Is your aircon unit 18,000–24,000 BTU (large unit)?"'
    ) == 1


@pytest.mark.asyncio
async def test_tc04_sentinel_none_silently_renders_flat_bullet(caplog):
    """TC-04: sentinel 'none' hint suppresses variation block; flat bullet rendered; no warning."""
    config_rows = [
        {"key": "pricing_chemical_wash", "value": "Chemical Wash: $120"},
        {"key": "variation_hint_chemical_wash", "value": "none"},
    ]
    db = _make_db(config_rows=config_rows)

    import logging
    with caplog.at_level(logging.WARNING):
        msg = await build_system_message(db)

    # Assertion 1: flat bullet rendered
    assert "- Chemical Wash: $120" in msg
    # Assertion 2: 'none' value not present in output
    assert "none" not in msg
    # Assertion 3: no clarification text
    assert "Clarification required" not in msg
    # Assertion 4: no "varies by unit size" for chemical_wash
    assert "Chemical Wash: pricing varies by unit size." not in msg
    # No WARNING log for sentinel case
    for record in caplog.records:
        assert "chemical_wash" not in record.message.lower() or record.levelno < logging.WARNING


@pytest.mark.asyncio
async def test_tc05_flat_key_no_hint_renders_flat_bullet_no_warning(caplog):
    """TC-05: flat pricing key with no hint row → flat bullet, no warning."""
    config_rows = [
        {"key": "pricing_gas_top_up", "value": "Gas Top-Up: $60"},
    ]
    db = _make_db(config_rows=config_rows)

    import logging
    with caplog.at_level(logging.WARNING):
        msg = await build_system_message(db)

    # Assertion 1: flat bullet present
    assert "- Gas Top-Up: $60" in msg
    # Assertion 2: no WARNING containing gas_top_up
    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert not any("gas_top_up" in m for m in warning_messages)
    # Assertion 3: no clarification text for gas_top_up
    assert "Clarification required" not in msg


@pytest.mark.asyncio
async def test_tc06_missing_hint_for_variation_group_warning_and_flat_bullets(caplog):
    """TC-06: missing hint row for variation group → WARNING + flat bullets + no crash."""
    config_rows = [
        {"key": "pricing_deep_clean__studio", "value": "Deep Clean (studio): $150"},
        {"key": "pricing_deep_clean__3br", "value": "Deep Clean (3-bedroom): $220"},
        # no variation_hint_deep_clean row
    ]
    db = _make_db(config_rows=config_rows)

    import logging
    with caplog.at_level(logging.WARNING):
        msg = await build_system_message(db)

    # Assertion 1: WARNING containing 'variation_hint_deep_clean missing from config'
    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("variation_hint_deep_clean missing from config" in m for m in warning_messages)
    # Assertion 2: flat bullet for studio
    assert "- Deep Clean (studio): $150" in msg
    # Assertion 3: flat bullet for 3br
    assert "- Deep Clean (3-bedroom): $220" in msg
    # Assertion 4: no clarification text
    assert "Clarification required" not in msg
    # Assertion 5: no exception (function completed successfully — implied by reaching here)


@pytest.mark.asyncio
async def test_tc07_non_variation_pricing_rows_unaffected(caplog):
    """TC-07: only flat keys → flat bullets; no variation text; no warnings."""
    config_rows = [
        {"key": "pricing_general", "value": "General Servicing: $50"},
        {"key": "pricing_chemical", "value": "Chemical Wash: $80"},
    ]
    db = _make_db(config_rows=config_rows)

    import logging
    with caplog.at_level(logging.WARNING):
        msg = await build_system_message(db)

    assert "- General Servicing: $50" in msg
    assert "- Chemical Wash: $80" in msg
    assert "varies by unit size" not in msg
    assert "Clarification required" not in msg
    # No warnings
    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warning_messages) == 0


@pytest.mark.asyncio
async def test_tc08_pricing_section_structure_unchanged_no_variation_keys():
    """TC-08: PRICING section structure intact when no variation keys present."""
    db = _make_db()  # uses default _make_config_rows() — no __ keys
    msg = await build_system_message(db)

    assert "PRICING:" in msg
    # All existing pricing values appear as flat bullets
    assert "- General Servicing: 1 unit $50" in msg
    assert "- Chemical Wash: 1 unit $80" in msg
    # Sections in order
    idx_services = msg.index("SERVICES:")
    idx_pricing = msg.index("PRICING:")
    idx_appointment = msg.index("APPOINTMENT WINDOWS:")
    idx_policies = msg.index("POLICIES:")
    assert idx_services < idx_pricing < idx_appointment < idx_policies


@pytest.mark.asyncio
async def test_tc09_display_name_derived_from_parent_slug():
    """TC-09: parent_slug converts to title-case display name in block header."""
    config_rows = [
        {"key": "pricing_general_servicing__standard",
         "value": "General Servicing standard: $80"},
        {"key": "variation_hint_general_servicing",
         "value": "What BTU?"},
        {"key": "pricing_deep_clean__studio",
         "value": "Deep Clean studio: $150"},
        {"key": "variation_hint_deep_clean",
         "value": "How many rooms?"},
    ]
    db = _make_db(config_rows=config_rows)
    msg = await build_system_message(db)

    # general_servicing → "General Servicing"
    assert "- General Servicing: pricing varies by unit size." in msg
    # deep_clean → "Deep Clean"
    assert "- Deep Clean: pricing varies by unit size." in msg


@pytest.mark.asyncio
async def test_tc10_mixed_config_variation_and_flat_coexist(caplog):
    """TC-10: variation group + flat keys + sentinel coexist correctly."""
    config_rows = [
        {"key": "pricing_general_servicing__standard",
         "value": "General Servicing (standard): $80"},
        {"key": "pricing_general_servicing__18_24k",
         "value": "General Servicing (large): $100"},
        {"key": "variation_hint_general_servicing",
         "value": "What BTU is your unit?"},
        {"key": "pricing_chemical_wash", "value": "Chemical Wash: $120"},
        {"key": "variation_hint_chemical_wash", "value": "none"},
        {"key": "pricing_gas_top_up", "value": "Gas Top-Up: $60"},
    ]
    db = _make_db(config_rows=config_rows)

    import logging
    with caplog.at_level(logging.WARNING):
        msg = await build_system_message(db)

    # Assertion 1: structured block for general_servicing
    assert "General Servicing: pricing varies by unit size." in msg
    assert (
        'Clarification required: before quoting or booking, ask: "What BTU is your unit?"'
    ) in msg
    # Assertion 2: flat bullet for chemical_wash
    assert "- Chemical Wash: $120" in msg
    # Assertion 3: flat bullet for gas_top_up
    assert "- Gas Top-Up: $60" in msg
    # Assertion 4: sentinel 'none' not in output
    assert "none" not in msg
    # Assertion 5: no duplicate variation block
    assert msg.count("General Servicing: pricing varies by unit size.") == 1
    # Assertion 6: no warnings (all groups have valid hints or sentinels)
    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warning_messages) == 0


@pytest.mark.asyncio
async def test_tc11_anomalous_flat_key_with_active_hint_warns_and_renders_flat(caplog):
    """TC-11: flat key with active (non-'none') hint → WARNING emitted + flat bullet."""
    config_rows = [
        {"key": "pricing_inspection", "value": "Inspection: $45"},
        {"key": "variation_hint_inspection", "value": "What floor is the unit on?"},
    ]
    db = _make_db(config_rows=config_rows)

    import logging
    with caplog.at_level(logging.WARNING):
        msg = await build_system_message(db)

    # Assertion 1: WARNING containing variation_hint_inspection
    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("variation_hint_inspection" in m for m in warning_messages)
    # Assertion 2: flat bullet rendered
    assert "- Inspection: $45" in msg
    # Assertion 3: no clarification text injected
    assert "Clarification required" not in msg
