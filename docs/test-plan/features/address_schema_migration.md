# Test Plan — Address Schema Migration (Phase 2)
## Feature: Move `address` / `postal_code` from `customers` → `bookings`

**Status:** Ready for Implementation
**Date:** 2026-04-20
**Owned by:** @sdet-engineer
**ADR source:** `docs/architecture/address_schema_migration.md`
**Scope:** Phase 2 code change only — `engine/core/tools/booking_tools.py`

---

## Success Condition

**Proof metric:** After a booking is written, the `bookings` INSERT payload contains `address` and `postal_code`; the `customers` UPDATE payload does NOT.

**Proxy metrics:** All other fields on `booking_row` and `customer_update` are unchanged. The `_alert_booking_failure()` path is unaffected. Tool schema in `definitions.py` continues to list `address` and `postal_code` in the `required` array.

---

## Prerequisite Gate

Phase 1 DDL must be confirmed live in Supabase before Phase 2 code is deployed to production. The code change itself can be developed and tested against mocks without Phase 1 DDL being applied, but deployment is blocked on DDL confirmation. This test suite runs against mocks only — it does not require Phase 1 DDL to be applied.

---

## Test Cases

### TC-01 — Happy path: valid address written to `bookings`, not to `customers`

**What it tests:** The core migration behaviour — address is in the `bookings` INSERT and absent from the `customers` UPDATE.

**Setup:**
- Mock `create_booking_event` to return `"cal_event_xyz"`.
- Mock Supabase db with a chainable mock that records all `insert()` and `update()` call arguments.
- Call `write_booking()` with all required fields including a valid `address` and `postal_code`.

**Inputs:**
```python
phone_number   = "6591234567"
customer_name  = "Alice Tan"
service_type   = "General Servicing"
unit_count     = "2"
address        = "10 Jurong East Street 21"
postal_code    = "609607"
slot_date      = "2026-05-10"
slot_window    = "AM"
```

**Assertions:**
1. Return dict has `status == "Confirmed"`.
2. `booking_row` dict passed to `db.table("bookings").insert(...)` contains `address == "10 Jurong East Street 21"` and `postal_code == "609607"`.
3. `customer_update` dict passed to `db.table("customers").update(...)` does NOT contain key `"address"`.
4. `customer_update` dict does NOT contain key `"postal_code"`.
5. `customer_update` dict DOES contain `"customer_name"`.

**Implementation note:** Capture the `insert()` and `update()` call args from the mock chain to inspect the dict contents.

---

### TC-02 — `customers` UPDATE contains only `customer_name` after migration

**What it tests:** Confirms Step 3 of `write_booking()` is narrowed to name-only — no other fields added or removed accidentally.

**Setup:** Same as TC-01.

**Assertions:**
1. `customer_update` dict has exactly one key: `"customer_name"`.
2. `customer_update["customer_name"] == "Alice Tan"`.

---

### TC-03 — Tool-level guard: `address=None` raises validation error, no DB write

**What it tests:** The defensive backstop added at function entry per ADR E1 decision.

**Setup:**
- Call `write_booking()` with `address=None`, `postal_code="609607"`.
- No mock for calendar (it should never be reached).

**Assertions:**
1. A `ValueError` (or equivalent explicit exception) is raised.
2. Error message contains a clear human-readable description (e.g. "address" is referenced).
3. `db.table` is never called — no Supabase write attempted.
4. `create_booking_event` is never called — no calendar write attempted.

---

### TC-04 — Tool-level guard: `address=""` (empty string) raises validation error, no DB write

**What it tests:** Empty string variant of the guard — both `None` and `""` must be rejected.

**Setup:** Same as TC-03 but `address=""`.

**Assertions:**
1. Same exception class as TC-03.
2. `db.table` never called.
3. `create_booking_event` never called.

---

### TC-05 — Existing `booking_row` fields unaffected by the migration

**What it tests:** Regression — the unconditional fields that were in `booking_row` before the migration are still present after it.

**Setup:** Same as TC-01 (happy path).

**Assertions:** The `booking_row` dict passed to `db.table("bookings").insert(...)` contains ALL of the following keys with correct values:
- `"booking_id"` — starts with `"HA-20260510-"`, length 16
- `"phone_number"` — `"6591234567"`
- `"service_type"` — `"General Servicing"`
- `"unit_count"` — `"2"`
- `"slot_date"` — `"2026-05-10"`
- `"slot_window"` — `"AM"`
- `"booking_status"` — `"Confirmed"`
- `"address"` — `"10 Jurong East Street 21"` (new)
- `"postal_code"` — `"609607"` (new)
- `"calendar_event_id"` — `"cal_event_xyz"` (set because calendar returned an ID)

---

### TC-06 — Optional fields still written conditionally to `booking_row`

**What it tests:** `aircon_brand` and `notes` optional fields are not broken by the migration.

**Setup:** Call `write_booking()` with `aircon_brand="Daikin"` and `notes="Please check unit 2 thoroughly"`.

**Assertions:**
1. `booking_row` contains `"aircon_brand": "Daikin"`.
2. `booking_row` contains `"notes": "Please check unit 2 thoroughly"`.

**Sub-case (no optional fields):** Call `write_booking()` without `aircon_brand` or `notes`.
1. `booking_row` does NOT contain key `"aircon_brand"`.
2. `booking_row` does NOT contain key `"notes"`.

---

### TC-07 — Repeat customer, different addresses: each booking row is independent

**What it tests:** ADR E4 — two bookings for the same phone number with different addresses must each carry their own correct address. No cross-contamination.

**Setup:**
- Call `write_booking()` twice for `phone_number="6591234567"` with different addresses.
  - Booking A: `address="10 Jurong East Street 21"`, `postal_code="609607"`, `slot_date="2026-05-10"`.
  - Booking B: `address="80 Airport Boulevard"`, `postal_code="819642"`, `slot_date="2026-05-17"`.
- Both calls use the same mocked calendar (returns unique event IDs each time).

**Assertions:**
1. First `bookings` INSERT contains `address="10 Jurong East Street 21"` and `postal_code="609607"`.
2. Second `bookings` INSERT contains `address="80 Airport Boulevard"` and `postal_code="819642"`.
3. Neither `customers` UPDATE payload contains any address keys.

---

### TC-08 — `_alert_booking_failure()` still receives address parameters (regression)

**What it tests:** The alert function signature and template still use `address` and `postal_code` — the migration must not silently strip them from the failure path.

**Setup:**
- Use a client config with `google_calendar_creds=None` to trigger the early-exit alert path.
- Patch `_alert_booking_failure` as an `AsyncMock`.

**Assertions:**
1. `_alert_booking_failure` is called once.
2. It is called with `address="10 Jurong East Street 21"` and `postal_code="609607"` as keyword arguments.
3. A `RuntimeError` is raised (calendar not configured).
4. `db.table` is never called.

---

### TC-09 — `definitions.py` schema: `address` and `postal_code` are in `required` array

**What it tests:** The Anthropic tool definition contract — the agent must always provide `address` and `postal_code`. This is a static verification, not an async test.

**Setup:** Import `TOOL_DEFINITIONS` from `engine.core.tools.definitions`.

**Assertions:**
1. The `write_booking` tool definition exists in `TOOL_DEFINITIONS`.
2. `input_schema["required"]` includes `"address"`.
3. `input_schema["required"]` includes `"postal_code"`.
4. Both `"address"` and `"postal_code"` exist as property keys in `input_schema["properties"]`.

---

### TC-10 — Null-safety: pre-Phase-2 bookings with NULL address do not break `get_customer_bookings()`

**What it tests:** ADR E2 — existing booking rows that have `address=NULL` and `postal_code=NULL` (written before Phase 2) do not cause errors when read back.

**Setup:**
- Mock `db.table("bookings").select(...)...execute()` to return a row where `address` key is absent (as Supabase would return for NULL columns not selected) or present with value `None`.
- Call `get_customer_bookings()`.

**Assertions:**
1. No exception raised.
2. Return dict has `count >= 1`.
3. `bookings` list items are returned without error even if `address` key is missing or `None`.

---

### TC-11 — Calendar write failure still triggers alert with address in message (regression)

**What it tests:** When `create_booking_event` raises, the `_alert_booking_failure` call still includes the address information — the alert text sent to the human agent remains complete.

**Setup:**
- Mock `create_booking_event` to raise `Exception("Google API 404")`.
- Patch `_alert_booking_failure` as `AsyncMock`.
- Patch `send_message` to avoid real network call.

**Assertions:**
1. `_alert_booking_failure` is called once.
2. Called with `address="10 Jurong East Street 21"` and `postal_code="609607"`.
3. The original exception is re-raised.
4. `db.table` is never called (calendar failure blocks DB write).

---

### TC-12 — Customer `UPDATE` failure after successful booking is non-fatal

**What it tests:** Step 3 failure handling is unaffected by the migration — a `customers` UPDATE failure must still log a warning and not re-raise.

**Setup:**
- Mock calendar to succeed.
- Mock first `db.table("bookings").insert(...)` to succeed.
- Mock second `db.table("customers").update(...)` to raise `Exception("DB down")`.

**Assertions:**
1. `write_booking()` returns a result dict with `status == "Confirmed"` (non-fatal).
2. No exception propagates to the caller.

---

## Test File Location

`engine/tests/unit/test_address_schema_migration.py`

Tests use the same `_make_db()` and `_make_client_config()` helpers established in `engine/tests/unit/test_tools.py`. The new test file imports those helpers directly or duplicates them — do NOT modify `test_tools.py`.

---

## Validation Commands

Run from the repository root (not inside the worktree):

```bash
# Run migration-specific tests only
pytest engine/tests/unit/test_address_schema_migration.py -v

# Run full unit test suite to confirm no regressions
pytest engine/tests/unit/ -v

# Full test suite
pytest engine/tests/ -v
```

---

## Out of Scope for This Test Plan

- Phase 1 DDL verification (Supabase Studio action — founder confirms manually)
- Phase 2.5 backfill SQL (one-time Supabase SQL Editor action)
- Phase 3 DROP DDL (explicit founder approval required — separate future test plan entry)
- Google Sheets sync behaviour (blocked on Phase 3 — tracked in `features/google_sheets_sync.md`)
- Agent-level prompt guard (agent must prompt user before calling tool — tested in agent integration tests, not here)
- `get_customer_bookings()` SELECT extension to include `address` (ADR E6 — future enhancement, not Phase 2)
