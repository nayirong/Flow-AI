"""
Phase 2 address schema migration — unit tests.

Verifies:
- address + postal_code land in booking_row (bookings INSERT)
- address + postal_code are absent from customer_update (customers UPDATE)
- guard raises ValueError on empty/None address before any DB call
- regression: existing fields are unchanged
- definitions.py still declares address + postal_code as required
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_client_config(
    has_calendar: bool = True,
    human_agent_number: str = "6590000001",
) -> MagicMock:
    cfg = MagicMock()
    cfg.client_id = "hey-aircon"
    cfg.human_agent_number = human_agent_number
    cfg.meta_phone_number_id = "123456789"
    cfg.meta_whatsapp_token = "test_token"
    if has_calendar:
        cfg.google_calendar_creds = {"type": "service_account", "project_id": "test"}
        cfg.google_calendar_id = "primary@group.calendar.google.com"
    else:
        cfg.google_calendar_creds = None
        cfg.google_calendar_id = None
    return cfg


def _make_split_db():
    """
    Returns (db, bookings_chain, customers_chain).

    db.table routes by table name so the caller can independently inspect
    what was passed to bookings INSERT vs customers UPDATE.
    """
    bookings_chain = MagicMock()
    bookings_chain.insert.return_value = bookings_chain
    bookings_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    customers_chain = MagicMock()
    customers_chain.update.return_value = customers_chain
    customers_chain.eq.return_value = customers_chain
    customers_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    db = MagicMock()
    db.table.side_effect = (
        lambda name: bookings_chain if name == "bookings" else customers_chain
    )

    return db, bookings_chain, customers_chain


def _base_booking_kwargs(**overrides):
    """Return a complete set of keyword arguments for write_booking."""
    kwargs = dict(
        phone_number="6591234567",
        customer_name="Alice Tan",
        service_type="General Servicing",
        unit_count="2",
        address="10 Jurong East Street 21",
        postal_code="609607",
        slot_date="2026-05-01",
        slot_window="AM",
    )
    kwargs.update(overrides)
    return kwargs


# ── TC-01: booking_row contains address and postal_code ───────────────────────


@pytest.mark.asyncio
@patch(
    "engine.integrations.google_calendar.create_booking_event",
    new_callable=AsyncMock,
)
async def test_tc01_booking_row_contains_address_and_postal_code(mock_create_event):
    """TC-01: booking_row passed to bookings INSERT contains address and postal_code."""
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.return_value = "cal_evt_001"
    db, bookings_chain, _ = _make_split_db()
    cfg = _make_client_config()

    await write_booking(db=db, client_config=cfg, **_base_booking_kwargs())

    inserted_row = bookings_chain.insert.call_args[0][0]
    assert inserted_row["address"] == "10 Jurong East Street 21"
    assert inserted_row["postal_code"] == "609607"


# ── TC-02: customer_update does NOT contain address or postal_code ─────────────


@pytest.mark.asyncio
@patch(
    "engine.integrations.google_calendar.create_booking_event",
    new_callable=AsyncMock,
)
async def test_tc02_customer_update_excludes_address_and_postal_code(mock_create_event):
    """TC-02: customer_update passed to customers UPDATE does not contain address or postal_code."""
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.return_value = "cal_evt_002"
    db, _, customers_chain = _make_split_db()
    cfg = _make_client_config()

    await write_booking(db=db, client_config=cfg, **_base_booking_kwargs())

    updated_payload = customers_chain.update.call_args[0][0]
    assert "address" not in updated_payload
    assert "postal_code" not in updated_payload


# ── TC-03: Guard — address=None raises ValueError before any DB call ───────────


@pytest.mark.asyncio
async def test_tc03_guard_address_none_raises_value_error():
    """TC-03: write_booking(address=None) raises ValueError; db.table never called."""
    from engine.core.tools.booking_tools import write_booking

    db, _, _ = _make_split_db()
    cfg = _make_client_config()

    with pytest.raises(ValueError, match="requires a non-empty address"):
        await write_booking(
            db=db,
            client_config=cfg,
            **_base_booking_kwargs(address=None),
        )

    db.table.assert_not_called()


# ── TC-04: Guard — address="" raises ValueError before any DB call ─────────────


@pytest.mark.asyncio
async def test_tc04_guard_address_empty_string_raises_value_error():
    """TC-04: write_booking(address='') raises ValueError; db.table never called."""
    from engine.core.tools.booking_tools import write_booking

    db, _, _ = _make_split_db()
    cfg = _make_client_config()

    with pytest.raises(ValueError, match="requires a non-empty address"):
        await write_booking(
            db=db,
            client_config=cfg,
            **_base_booking_kwargs(address=""),
        )

    db.table.assert_not_called()


# ── TC-05: Regression — booking_row still contains core fields ─────────────────


@pytest.mark.asyncio
@patch(
    "engine.integrations.google_calendar.create_booking_event",
    new_callable=AsyncMock,
)
async def test_tc05_regression_booking_row_core_fields_present(mock_create_event):
    """TC-05: booking_row still contains booking_id, phone_number, service_type, unit_count,
    slot_date, slot_window, booking_status."""
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.return_value = "cal_evt_005"
    db, bookings_chain, _ = _make_split_db()
    cfg = _make_client_config()

    await write_booking(db=db, client_config=cfg, **_base_booking_kwargs())

    inserted_row = bookings_chain.insert.call_args[0][0]
    assert "booking_id" in inserted_row
    assert inserted_row["phone_number"] == "6591234567"
    assert inserted_row["service_type"] == "General Servicing"
    assert inserted_row["unit_count"] == "2"
    assert inserted_row["slot_date"] == "2026-05-01"
    assert inserted_row["slot_window"] == "AM"
    assert inserted_row["booking_status"] == "Confirmed"


# ── TC-06: Regression — customer_update still contains customer_name ───────────


@pytest.mark.asyncio
@patch(
    "engine.integrations.google_calendar.create_booking_event",
    new_callable=AsyncMock,
)
async def test_tc06_regression_customer_update_contains_name(mock_create_event):
    """TC-06: customer_update still contains customer_name."""
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.return_value = "cal_evt_006"
    db, _, customers_chain = _make_split_db()
    cfg = _make_client_config()

    await write_booking(db=db, client_config=cfg, **_base_booking_kwargs())

    updated_payload = customers_chain.update.call_args[0][0]
    assert updated_payload["customer_name"] == "Alice Tan"


# ── TC-07: Repeat customer — each booking INSERT gets its own address ──────────


@pytest.mark.asyncio
@patch(
    "engine.integrations.google_calendar.create_booking_event",
    new_callable=AsyncMock,
)
async def test_tc07_repeat_customer_each_booking_gets_own_address(mock_create_event):
    """TC-07: Two bookings with different addresses — each INSERT row carries the
    correct address for that call."""
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.side_effect = ["cal_evt_007a", "cal_evt_007b"]

    # First booking
    db1, bookings_chain1, _ = _make_split_db()
    cfg = _make_client_config()
    await write_booking(
        db=db1,
        client_config=cfg,
        **_base_booking_kwargs(
            address="10 Jurong East Street 21", postal_code="609607"
        ),
    )

    # Second booking (different address)
    db2, bookings_chain2, _ = _make_split_db()
    await write_booking(
        db=db2,
        client_config=cfg,
        **_base_booking_kwargs(
            address="5 Tampines Ave 1",
            postal_code="529656",
            slot_date="2026-05-10",
        ),
    )

    row1 = bookings_chain1.insert.call_args[0][0]
    row2 = bookings_chain2.insert.call_args[0][0]

    assert row1["address"] == "10 Jurong East Street 21"
    assert row1["postal_code"] == "609607"
    assert row2["address"] == "5 Tampines Ave 1"
    assert row2["postal_code"] == "529656"


# ── TC-08: Alert path — calendar exception still calls _alert_booking_failure ──


@pytest.mark.asyncio
@patch(
    "engine.integrations.google_calendar.create_booking_event",
    new_callable=AsyncMock,
    side_effect=RuntimeError("Google Calendar 404"),
)
@patch(
    "engine.core.tools.booking_tools._alert_booking_failure",
    new_callable=AsyncMock,
)
async def test_tc08_calendar_exception_triggers_alert(mock_alert, mock_create_event):
    """TC-08: When calendar raises, _alert_booking_failure is still called."""
    from engine.core.tools.booking_tools import write_booking

    db, _, _ = _make_split_db()
    cfg = _make_client_config()

    with pytest.raises(RuntimeError):
        await write_booking(db=db, client_config=cfg, **_base_booking_kwargs())

    mock_alert.assert_awaited_once()


# ── TC-09: Schema contract — definitions.py required array includes address ────


def test_tc09_definitions_required_includes_address_and_postal_code():
    """TC-09 (sync): definitions.py write_booking required array includes address
    and postal_code."""
    from engine.core.tools.definitions import TOOL_DEFINITIONS

    write_booking_def = next(
        t for t in TOOL_DEFINITIONS if t["name"] == "write_booking"
    )
    required = write_booking_def["input_schema"]["required"]
    assert "address" in required
    assert "postal_code" in required


# ── TC-10: NULL safety — get_customer_bookings returns rows with None address ──


@pytest.mark.asyncio
async def test_tc10_get_customer_bookings_tolerates_none_address():
    """TC-10: get_customer_bookings returns rows where address is None without raising."""
    from engine.core.tools.booking_tools import get_customer_bookings

    mock_rows = [
        {
            "booking_id": "HA-20260501-A1B2",
            "service_type": "General Servicing",
            "slot_date": "2026-05-01",
            "slot_window": "AM",
            "booking_status": "Confirmed",
            "address": None,
        }
    ]

    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(return_value=MagicMock(data=mock_rows))

    db = MagicMock()
    db.table.return_value = chain

    result = await get_customer_bookings(db=db, phone_number="6591234567")

    assert result["count"] == 1
    assert result["bookings"][0]["address"] is None


# ── TC-11: Alert path regression — early exit still passes address to alert ────


@pytest.mark.asyncio
@patch(
    "engine.core.tools.booking_tools._alert_booking_failure",
    new_callable=AsyncMock,
)
async def test_tc11_alert_receives_address_on_no_calendar_early_exit(mock_alert):
    """TC-11: When calendar is not configured (early exit), _alert_booking_failure
    is called with the correct address value."""
    from engine.core.tools.booking_tools import write_booking

    db, _, _ = _make_split_db()
    cfg = _make_client_config(has_calendar=False)

    with pytest.raises(RuntimeError):
        await write_booking(
            db=db,
            client_config=cfg,
            **_base_booking_kwargs(
                address="10 Jurong East Street 21",
                postal_code="609607",
            ),
        )

    mock_alert.assert_awaited_once()
    call_kwargs = mock_alert.call_args.kwargs
    assert call_kwargs["address"] == "10 Jurong East Street 21"
    assert call_kwargs["postal_code"] == "609607"


# ── TC-12: Non-fatal customer UPDATE failure ───────────────────────────────────


@pytest.mark.asyncio
@patch(
    "engine.integrations.google_calendar.create_booking_event",
    new_callable=AsyncMock,
)
async def test_tc12_customer_update_failure_is_non_fatal(mock_create_event):
    """TC-12: If customers UPDATE raises, the function still returns a confirmed
    booking result (Step 3 failure is non-fatal)."""
    from engine.core.tools.booking_tools import write_booking

    mock_create_event.return_value = "cal_evt_012"

    bookings_chain = MagicMock()
    bookings_chain.insert.return_value = bookings_chain
    bookings_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    customers_chain = MagicMock()
    customers_chain.update.return_value = customers_chain
    customers_chain.eq.return_value = customers_chain
    customers_chain.execute = AsyncMock(side_effect=Exception("DB write failed"))

    db = MagicMock()
    db.table.side_effect = (
        lambda name: bookings_chain if name == "bookings" else customers_chain
    )

    cfg = _make_client_config()

    result = await write_booking(db=db, client_config=cfg, **_base_booking_kwargs())

    assert result["status"] == "Confirmed"
    assert "booking_id" in result
