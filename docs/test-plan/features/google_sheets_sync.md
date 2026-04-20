# Test Plan: Google Sheets Data Sync

**Feature:** Google Sheets post-write sync (customer + booking data visibility layer)  
**Status:** Ready for Implementation  
**SDET Owner:** @sdet-engineer  
**Architecture source:** `docs/architecture/google_sheets_sync.md`  
**Requirements source:** `docs/requirements/google_sheets_sync.md`  
**Files under test:**
- `engine/integrations/google_sheets.py` (new file)
- `engine/core/message_handler.py` (call site hook)
- `engine/core/tools/booking_tools.py` (call site hook)
- `engine/config/client_config.py` (config loading)

**Test files:**
- `engine/tests/unit/test_google_sheets.py`
- `engine/tests/integration/test_sheets_sync_hooks.py`

**Date:** 2026-04-20

---

## 1. Scope

This test plan covers end-to-end verification of the Google Sheets sync feature:

### In Scope:
- Unit tests for `integrations/google_sheets.py` (sync functions, deduplication, error handling)
- Integration tests for call site hooks (message_handler, booking_tools)
- Config loading tests (new ClientConfig fields)
- Acceptance criteria verification (all 10 ACs from requirements)
- Fire-and-forget error handling (Sheets failure never blocks agent)
- Thread safety (blocking I/O in executor)
- Header initialization (empty sheet handling)
- Row deduplication (linear scan, UUID matching)

### Out of Scope:
- Manual spreadsheet creation (Flow AI team task during onboarding)
- Supabase DDL execution (manual Supabase Studio task)
- Real Google Sheets API calls in unit tests (mocked only)
- Phase 2 migration/decommission logic

---

## 2. Test Strategy

### 2.1 Unit Tests (`test_google_sheets.py`)

**Mocking approach:**
- Mock `gspread` library calls (authenticate, get spreadsheet, get worksheet, read/write operations)
- Mock `asyncio.get_event_loop().run_in_executor()` to execute blocking functions synchronously in tests
- Use `pytest-asyncio` for async test support
- Use `pytest` fixtures for common test setup (client_config, mock credentials, sample data)

**Test isolation:**
- Each test case creates its own mock objects
- No shared state between tests
- No real API calls

### 2.2 Integration Tests (`test_sheets_sync_hooks.py`)

**Scope:**
- Verify call sites in `message_handler.py` and `booking_tools.py` correctly invoke sync functions
- Verify `asyncio.create_task()` is used (background task, non-blocking)
- Verify sync function is called with correct parameters
- Use mocks to verify function calls without executing real sync logic

### 2.3 Acceptance Criteria Tests

Each AC from the requirements doc maps to one or more test cases below.

---

## 3. Unit Test Cases — `engine/tests/unit/test_google_sheets.py`

### TC-U01 — Config guard: sync disabled, no API calls (AC-8, NFR-2)

**Setup:**
- `ClientConfig` with `sheets_sync_enabled=False`
- Mock all gspread calls

**Test `sync_customer_to_sheets()`:**
1. Call with `sheets_sync_enabled=False`
2. Assert function returns immediately (no gspread calls made)
3. Assert no logs emitted (silent no-op)

**Test `sync_booking_to_sheets()`:**
1. Same test as above for bookings

**AC cross-ref:** AC-8, NFR-2 (disabled sync does not affect agent)

---

### TC-U02 — Config validation: missing spreadsheet ID, error logged (AC-9)

**Setup:**
- `ClientConfig` with `sheets_sync_enabled=True`, `sheets_spreadsheet_id=None`
- Capture logs using `caplog`

**Test:**
1. Call `sync_customer_to_sheets()`
2. Assert ERROR log contains "Sheets sync enabled but spreadsheet ID missing"
3. Assert function returns without raising exception
4. Assert no gspread calls made

**AC cross-ref:** AC-9

---

### TC-U03 — Config validation: missing service account creds, error logged

**Setup:**
- `ClientConfig` with `sheets_sync_enabled=True`, `sheets_spreadsheet_id="valid-id"`, `sheets_service_account_creds=None`

**Test:**
1. Call `sync_customer_to_sheets()`
2. Assert ERROR log contains "service account credentials missing"
3. Assert function returns without raising exception

---

### TC-U04 — Header initialization: empty sheet, write header + data row

**Setup:**
- Mock `worksheet.get_all_values()` returns `[]` (empty sheet)
- Mock `worksheet.append_row()` to track calls

**Test `sync_customer_to_sheets()`:**
1. Call with valid customer data
2. Assert `append_row` called twice:
   - First call: header row `["ID", "Phone Number", "Display Name", "First Seen", "Last Seen", "Booking Count", "Escalation Flag"]`
   - Second call: data row with customer values
3. Assert both calls succeeded

**AC cross-ref:** Architecture section 1.6

---

### TC-U05 — Row insert: new customer, append to sheet (AC-4)

**Setup:**
- Mock `worksheet.get_all_values()` returns header + 2 existing rows (neither matches test UUID)
- Mock `worksheet.append_row()` to track calls

**Test:**
1. Call `sync_customer_to_sheets()` with customer data `{"id": "new-uuid-123", ...}`
2. Assert linear scan searched all rows (ID column extracted)
3. Assert no match found
4. Assert `append_row` called once with correct data row
5. Assert `worksheet.update()` NOT called

**AC cross-ref:** AC-4

---

### TC-U06 — Row update: existing customer, update in place (AC-5)

**Setup:**
- Mock `worksheet.get_all_values()` returns:
  - Row 1: header
  - Row 2: `["existing-uuid-456", "+6512345678", "John Doe", ...]`
  - Row 3: other customer
- Mock `worksheet.update()` to track calls

**Test:**
1. Call `sync_customer_to_sheets()` with customer data `{"id": "existing-uuid-456", "last_seen": "2026-04-20T14:30:00Z", ...}`
2. Assert linear scan found match at row 2
3. Assert `worksheet.update()` called with range `"A2:G2"` (7 columns for Customers tab)
4. Assert updated row contains new `last_seen` value
5. Assert `append_row` NOT called

**AC cross-ref:** AC-5

---

### TC-U07 — Row deduplication: duplicate UUID in sheet, update first match only

**Setup:**
- Mock `worksheet.get_all_values()` returns:
  - Row 1: header
  - Row 2: `["duplicate-uuid-789", ...]`
  - Row 3: `["duplicate-uuid-789", ...]` (manual duplicate)
- Capture logs

**Test:**
1. Call `sync_customer_to_sheets()` with `{"id": "duplicate-uuid-789", ...}`
2. Assert WARNING log contains "Duplicate ID found in Sheets"
3. Assert `worksheet.update()` called ONCE for row 2 only
4. Assert row 3 remains unchanged

**AC cross-ref:** Architecture section 4.3 (edge cases)

---

### TC-U08 — Column mapping: 1:1 fidelity (AC-3)

**Setup:**
- Mock `worksheet.append_row()` to capture arguments

**Test `sync_customer_to_sheets()`:**
1. Call with complete customer data dict (all 7 fields populated)
2. Assert `append_row` called with list of 7 values in exact column order:
   `[id, phone_number, display_name, first_seen, last_seen, booking_count, escalation_flag]`
3. Assert boolean `escalation_flag=True` rendered as `"TRUE"` (uppercase string)
4. Assert timestamps are ISO 8601 strings (no transformation)

**Test `sync_booking_to_sheets()`:**
1. Call with complete booking data dict (all 11 fields)
2. Assert `append_row` called with list of 11 values in exact column order per architecture doc
3. Assert no data transformation or truncation

**AC cross-ref:** AC-3, Architecture section 1.5

---

### TC-U09 — Timestamp formatting: ISO 8601 strings, no locale conversion

**Setup:**
- Mock `worksheet.append_row()`

**Test:**
1. Call `sync_customer_to_sheets()` with `first_seen="2026-04-20T09:30:00Z"`
2. Assert `append_row` called with ISO string unchanged: `"2026-04-20T09:30:00Z"`
3. Assert no timezone conversion or locale formatting applied

**AC cross-ref:** Architecture section 1.5, Requirements OQ-4

---

### TC-U10 — Error handling: Google API 503, logged and swallowed (AC-6, NFR-2)

**Setup:**
- Mock `_build_service()` to raise `Exception("503 Service Unavailable")`
- Capture logs

**Test:**
1. Call `sync_customer_to_sheets()`
2. Assert ERROR log contains:
   - `client_id`
   - Table name "customers"
   - Row ID (UUID)
   - Error message "503 Service Unavailable"
3. Assert function returns without raising exception
4. Assert no re-raise

**AC cross-ref:** AC-6, NFR-2

---

### TC-U11 — Error handling: invalid credentials (401), logged and swallowed

**Setup:**
- Mock `_build_service()` to raise `gspread.exceptions.APIError` with 401 status

**Test:**
1. Call `sync_customer_to_sheets()`
2. Assert ERROR log contains "authentication failed" or "401"
3. Assert function returns without raising exception

**AC cross-ref:** Architecture section 1.7

---

### TC-U12 — Error handling: spreadsheet not found (404), logged and swallowed (AC-7)

**Setup:**
- Mock `service.open_by_key()` to raise `gspread.exceptions.SpreadsheetNotFound`

**Test:**
1. Call `sync_customer_to_sheets()`
2. Assert ERROR log contains "Spreadsheet not found" and spreadsheet ID
3. Assert function returns without raising exception

**AC cross-ref:** AC-7

---

### TC-U13 — Error handling: tab name does not exist, logged and swallowed

**Setup:**
- Mock `spreadsheet.worksheet("Customers")` to raise `gspread.exceptions.WorksheetNotFound`

**Test:**
1. Call `sync_customer_to_sheets()`
2. Assert ERROR log contains "Worksheet 'Customers' not found"
3. Assert function returns without raising exception

---

### TC-U14 — Thread safety: blocking I/O runs in executor

**Setup:**
- Mock `asyncio.get_event_loop().run_in_executor()` to capture calls

**Test:**
1. Call `sync_customer_to_sheets()`
2. Assert `run_in_executor()` called for ALL gspread blocking operations:
   - Service account authentication
   - Spreadsheet fetch
   - Worksheet.get_all_values()
   - Worksheet.update() or append_row()
3. Assert executor is `None` (default thread pool)

**AC cross-ref:** Architecture section 1.3

---

### TC-U15 — NULL fields: empty string in Sheets (edge case)

**Setup:**
- Mock `worksheet.append_row()`

**Test:**
1. Call `sync_customer_to_sheets()` with `display_name=None`
2. Assert `append_row` called with `""` (empty string) in the display_name position
3. Assert no exception raised

**AC cross-ref:** Architecture section 4.3

---

### TC-U16 — Booking sync: all 11 columns mapped correctly

**Setup:**
- Mock `worksheet.append_row()`

**Test `sync_booking_to_sheets()`:**
1. Call with complete booking data dict (all 11 fields from architecture doc)
2. Assert `append_row` called with list of 11 values in exact order:
   `[id, phone_number, customer_name, service_type, booking_date, booking_time, address, unit_number, notes, status, created_at]`
3. Assert column order matches architecture section 1.5 table

---

## 4. Integration Test Cases — `engine/tests/integration/test_sheets_sync_hooks.py`

### TC-I01 — message_handler: customer insert triggers sync (AC-1)

**Setup:**
- Mock `sync_customer_to_sheets()` from `integrations.google_sheets`
- Mock Supabase insert to return customer row with generated UUID
- Mock all other dependencies (Meta API, Claude API, etc.)

**Test:**
1. Send inbound webhook message (new customer)
2. Assert `message_handler` completes successfully
3. Assert `sync_customer_to_sheets()` called with:
   - `client_id` = correct value
   - `client_config` = loaded ClientConfig object
   - `customer_data` dict contains all 7 fields including generated `id`
4. Assert sync was called via `asyncio.create_task()` (verify task was scheduled)

**AC cross-ref:** AC-1

---

### TC-I02 — message_handler: customer update triggers sync (AC-1)

**Setup:**
- Mock `sync_customer_to_sheets()`
- Mock Supabase update for returning customer (update `last_seen`)
- Existing `customer_row` already loaded in message_handler

**Test:**
1. Send inbound webhook message (returning customer)
2. Assert `message_handler` completes successfully
3. Assert `sync_customer_to_sheets()` called with:
   - `customer_data` dict contains updated `last_seen` timestamp
   - `customer_data["id"]` matches existing customer UUID from Step 4 of message_handler

**AC cross-ref:** AC-1

---

### TC-I03 — booking_tools: booking insert triggers sync (AC-2)

**Setup:**
- Mock `sync_booking_to_sheets()` from `integrations.google_sheets`
- Mock Supabase insert for `bookings` table
- Mock Google Calendar API

**Test:**
1. Call `write_booking()` tool function
2. Assert booking inserted to Supabase
3. Assert `sync_booking_to_sheets()` called with:
   - `client_id` = correct value
   - `client_config` = loaded ClientConfig object
   - `booking_data` dict contains all booking fields
4. Assert sync was called via `asyncio.create_task()`

**AC cross-ref:** AC-2

---

### TC-I04 — Non-blocking: sync does not block webhook response (NFR-1)

**Setup:**
- Mock `sync_customer_to_sheets()` to sleep for 2 seconds (simulate slow Sheets API)
- Mock all other dependencies

**Test:**
1. Send inbound webhook message
2. Measure time from webhook receipt to `200 OK` response
3. Assert response time < 500ms (does not wait for 2-second sync to complete)
4. Assert sync task was scheduled but not awaited

**AC cross-ref:** NFR-1

---

### TC-I05 — Sheets failure does not break agent: Supabase write succeeds (AC-6, NFR-2)

**Setup:**
- Mock `sync_customer_to_sheets()` to raise `Exception("Sheets API timeout")`
- Mock Supabase insert to succeed
- Mock Meta WhatsApp API to succeed

**Test:**
1. Send inbound webhook message
2. Assert message_handler completes successfully
3. Assert customer inserted to Supabase
4. Assert WhatsApp reply sent to customer
5. Assert webhook returns `200 OK`
6. Assert ERROR log contains "Sheets API timeout"

**AC cross-ref:** AC-6, NFR-2

---

## 5. Config Tests — `test_client_config.py` (add to existing file)

### TC-C01 — ClientConfig: new fields loaded from Supabase

**Setup:**
- Mock Supabase `clients` table row with:
  - `sheets_sync_enabled=true`
  - `sheets_spreadsheet_id="1a2b3c4d5e6f"`
  - `sheets_service_account_creds={"type": "service_account", ...}`

**Test:**
1. Call `load_client_config("test-client")`
2. Assert returned `ClientConfig` object has:
   - `sheets_sync_enabled == True`
   - `sheets_spreadsheet_id == "1a2b3c4d5e6f"`
   - `sheets_service_account_creds` is dict with expected keys

---

### TC-C02 — ClientConfig: sheets fields default to safe values

**Setup:**
- Mock Supabase `clients` table row with NO sheets_* columns (missing or NULL)

**Test:**
1. Call `load_client_config("test-client")`
2. Assert `sheets_sync_enabled == False` (default)
3. Assert `sheets_spreadsheet_id == None`
4. Assert `sheets_service_account_creds == {}` (empty dict)

---

### TC-C03 — ClientConfig cache: sheets config updates within 5 minutes

**Setup:**
- Mock Supabase to return `sheets_sync_enabled=False` initially
- Mock time.time() to control cache expiry

**Test:**
1. Call `load_client_config()` → returns cached value with `sheets_sync_enabled=False`
2. Update mock Supabase row to `sheets_sync_enabled=True`
3. Advance mock time by 6 minutes (past TTL)
4. Call `load_client_config()` again
5. Assert new value `sheets_sync_enabled=True` is loaded

---

## 6. Acceptance Criteria Verification

### AC-1: Sync Trigger — Immediate Post-Write (Customer)
**Test Coverage:** TC-I01, TC-I02

**Verification Steps:**
1. New customer sends WhatsApp message
2. Verify `message_handler` upserts customer to Supabase
3. Verify `sync_customer_to_sheets()` called immediately after Supabase write
4. Verify "Customers" tab updated within 10 seconds (manual verification in real environment)

---

### AC-2: Sync Trigger — Booking Creation
**Test Coverage:** TC-I03

**Verification Steps:**
1. Agent creates booking via `write_booking` tool
2. Verify booking inserted to Supabase
3. Verify `sync_booking_to_sheets()` called immediately after
4. Verify "Bookings" tab updated within 10 seconds

---

### AC-3: Column Mapping — 1:1 Accuracy
**Test Coverage:** TC-U08, TC-U16

**Verification Steps:**
1. Create booking with all fields populated (address, unit_number, notes, etc.)
2. Verify every Sheets column matches corresponding Supabase column exactly
3. Verify no data transformation or truncation

---

### AC-4: Row Insert — New Record
**Test Coverage:** TC-U05

**Verification Steps:**
1. New customer with unique UUID
2. Verify new row appended to "Customers" tab
3. Verify row contains correct data in all columns

---

### AC-5: Row Update — Existing Record
**Test Coverage:** TC-U06

**Verification Steps:**
1. Existing customer's `last_seen` or `booking_count` changes
2. Verify existing row (matched by UUID) is updated
3. Verify no duplicate row created

---

### AC-6: Failure — Sheets Outage Does Not Block Agent
**Test Coverage:** TC-U10, TC-I05

**Verification Steps:**
1. Simulate Google Sheets API 503 error
2. Verify message handled normally (Supabase write succeeds, WhatsApp reply sent)
3. Verify Sheets sync failure logged
4. Verify no exception raised to webhook handler

---

### AC-7: Failure — Invalid Spreadsheet ID
**Test Coverage:** TC-U12

**Verification Steps:**
1. Set invalid `sheets_spreadsheet_id` in config
2. Trigger sync
3. Verify error logged ("Spreadsheet not found")
4. Verify Supabase write not rolled back
5. Verify agent continues normally

---

### AC-8: Config — Sync Disabled
**Test Coverage:** TC-U01

**Verification Steps:**
1. Set `sheets_sync_enabled=false`
2. Trigger any Supabase write
3. Verify no Sheets API calls made
4. Verify no Sheets-related logs
5. Verify agent functions normally

---

### AC-9: Config — Spreadsheet ID Missing
**Test Coverage:** TC-U02

**Verification Steps:**
1. Set `sheets_sync_enabled=true`, `sheets_spreadsheet_id=NULL`
2. Trigger sync
3. Verify error logged ("spreadsheet ID missing")
4. Verify sync skipped
5. Verify agent continues normally

---

### AC-10: Permissions — Read-Only for Client
**Test Coverage:** Manual verification (not automated)

**Verification Steps:**
1. Share HeyAircon spreadsheet with business owner as "Viewer"
2. Business owner attempts to edit a cell
3. Verify edit rejected by Google Sheets
4. Verify message: "You need permission to edit this spreadsheet"

---

## 7. Edge Cases & Failure Scenarios

### Edge Case Matrix

| Scenario | Expected Behavior | Test Coverage |
|----------|------------------|---------------|
| Empty sheet (no header) | Write header first, then append data | TC-U04 |
| Header only (no data rows) | Append data row after header | TC-U05 |
| UUID in multiple rows (duplicate) | Update first match, log warning | TC-U07 |
| NULL fields in Supabase row | Write empty string to Sheets | TC-U15 |
| Concurrent writes to same row | Last write wins (no locking) | Not tested (acceptable for Phase 1) |
| Google API timeout | Log error, return silently | TC-U10 |
| Invalid credentials (401) | Log error, return silently | TC-U11 |
| Spreadsheet not found (404) | Log error, return silently | TC-U12 |
| Tab name does not exist | Log error, return silently | TC-U13 |
| Rate limit (429) | Log error, return silently | TC-U10 (same handler) |

---

## 8. Performance & Reliability Tests

### NFR-1: No Agent Latency Impact
**Test Coverage:** TC-I04

**Target:** Agent response time increase < 50ms when sync enabled vs disabled

**Verification:**
1. Measure baseline: sync disabled, 100 messages → median response time
2. Measure with sync: sync enabled, 100 messages → median response time
3. Assert difference < 50ms

---

### NFR-2: Graceful Degradation
**Test Coverage:** TC-U10, TC-U11, TC-U12, TC-I05

**Target:** 100% Sheets API failure rate → zero agent failures

**Verification:**
1. Mock all Sheets API calls to fail (100% failure rate)
2. Send 50 test messages
3. Assert all 50 messages handled successfully
4. Assert all 50 Supabase writes succeeded
5. Assert all 50 WhatsApp replies sent

---

### NFR-3: Observability — Failure Visibility
**Test Coverage:** All TC-U10–TC-U13

**Target:** Every failure logged with context

**Verification:**
1. Trigger each failure scenario
2. Verify log contains:
   - Timestamp
   - Client ID
   - Table name
   - Row ID (UUID)
   - Operation (insert/update)
   - Error type and message

---

### NFR-4: Data Freshness
**Test Coverage:** Manual verification (AC-1, AC-2)

**Target:** Sheets data reflects Supabase within 10 seconds

**Verification:**
1. Send WhatsApp message (new customer)
2. Check Supabase `customers` table (record inserted)
3. Check Google Sheets "Customers" tab (row appears)
4. Measure time delta
5. Assert delta < 10 seconds

---

## 9. Test Execution Checklist

### Unit Tests
- [ ] TC-U01 through TC-U16 pass (16 tests)
- [ ] All tests use mocks (no real Sheets API calls)
- [ ] Code coverage >80% for `integrations/google_sheets.py`

### Integration Tests
- [ ] TC-I01 through TC-I05 pass (5 tests)
- [ ] Call site hooks verified (message_handler, booking_tools)

### Config Tests
- [ ] TC-C01 through TC-C03 pass (3 tests)
- [ ] ClientConfig fields loaded correctly

### Acceptance Criteria
- [ ] AC-1 through AC-9 automated and passing
- [ ] AC-10 verified manually (permissions check)

### Performance & Reliability
- [ ] NFR-1: Agent latency < 50ms increase
- [ ] NFR-2: 100% Sheets failure → zero agent failures
- [ ] NFR-3: All failures logged with context
- [ ] NFR-4: Data freshness < 10 seconds (manual spot-check)

### Manual Verification (Real Environment)
- [ ] HeyAircon spreadsheet created with "Customers" and "Bookings" tabs
- [ ] Service account granted "Editor" access
- [ ] Business owner granted "Viewer" access
- [ ] Send real WhatsApp message → verify row appears in Sheets
- [ ] Create booking → verify row appears in Sheets
- [ ] Attempt manual edit as Viewer → verify rejected

---

## 10. Test Data Fixtures

### Sample ClientConfig
```python
@pytest.fixture
def sample_client_config():
    return ClientConfig(
        client_id="hey-aircon",
        display_name="HeyAircon",
        meta_phone_number_id="123456789",
        meta_verify_token="verify_token_123",
        meta_whatsapp_token="whatsapp_token_123",
        human_agent_number="+6512345678",
        google_calendar_id="calendar@example.com",
        google_calendar_creds={},
        supabase_url="https://example.supabase.co",
        supabase_service_key="service_key_123",
        anthropic_api_key="sk-ant-123",
        openai_api_key="sk-123",
        timezone="Asia/Singapore",
        is_active=True,
        sheets_sync_enabled=True,
        sheets_spreadsheet_id="1a2b3c4d5e6f7g8h9i0j",
        sheets_service_account_creds={
            "type": "service_account",
            "project_id": "test-project",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
        },
    )
```

### Sample Customer Data
```python
@pytest.fixture
def sample_customer_data():
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "phone_number": "+6587654321",
        "display_name": "Jane Doe",
        "first_seen": "2026-04-20T09:00:00Z",
        "last_seen": "2026-04-20T14:30:00Z",
        "booking_count": 3,
        "escalation_flag": False,
    }
```

### Sample Booking Data
```python
@pytest.fixture
def sample_booking_data():
    return {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "phone_number": "+6587654321",
        "customer_name": "Jane Doe",
        "service_type": "General Servicing",
        "booking_date": "2026-04-25",
        "booking_time": "AM",
        "address": "123 Orchard Road",
        "unit_number": "#12-34",
        "notes": "Please call before arriving",
        "status": "Confirmed",
        "created_at": "2026-04-20T14:30:00Z",
    }
```

---

## 11. Known Limitations & Future Work

### Phase 1 Limitations:
1. **No retry logic** — Failed syncs are logged but never retried
2. **No delete propagation** — Supabase deletes do not remove Sheets rows
3. **Linear scan performance** — O(n) deduplication, acceptable up to ~1000 rows
4. **No batch backfill** — Existing Supabase data not synced to newly configured spreadsheet
5. **No rate limit handling** — 429 errors treated same as other failures (log and continue)

### Phase 2 Enhancements:
1. **Retry queue** — Persistent failed sync queue with background worker
2. **In-memory cache** — Cache `{uuid: row_number}` mapping for faster deduplication
3. **Dashboard migration** — Deprecate Sheets sync when CRM Interface (PRD-03) launches
4. **Observability** — Send sync errors to Slack/PagerDuty for real-time alerting
5. **Batch backfill tool** — CLI script to sync all existing Supabase data to Sheets

---

## 12. Validation Commands

### Run Unit Tests
```bash
cd .worktree/google-sheets-sync-01-implementation
pytest engine/tests/unit/test_google_sheets.py -v --cov=engine/integrations/google_sheets
```

### Run Integration Tests
```bash
pytest engine/tests/integration/test_sheets_sync_hooks.py -v
```

### Run All Sheets-Related Tests
```bash
pytest engine/tests/ -v -k "sheets"
```

### Check Code Coverage
```bash
pytest engine/tests/unit/test_google_sheets.py --cov=engine/integrations/google_sheets --cov-report=term-missing
```

**Target coverage:** >80% for `google_sheets.py`

---

## 13. Success Criteria Summary

This feature is **APPROVED FOR MERGE** when:

- ✅ All 16 unit tests pass (TC-U01 through TC-U16)
- ✅ All 5 integration tests pass (TC-I01 through TC-I05)
- ✅ All 3 config tests pass (TC-C01 through TC-C03)
- ✅ All 9 automated ACs verified (AC-1 through AC-9)
- ✅ AC-10 verified manually (permissions check)
- ✅ Code coverage >80% for `integrations/google_sheets.py`
- ✅ All NFRs verified (latency, reliability, observability, freshness)
- ✅ No real Sheets API calls in test suite (all mocked)
- ✅ Format check passes (project formatter runs clean)
- ✅ Real-environment smoke test: send test message → verify Sheets row appears
