# Google Sheets Data Sync — Architecture Document

**Feature:** Google Sheets post-write sync (customer + booking data visibility layer)  
**Architect:** `@software-architect`  
**Date Created:** 2026-04-20  
**Requirements:** `docs/requirements/google_sheets_sync.md`  
**Status:** Draft — Ready for SDET Review  

---

## Purpose

Provide Flow AI clients with real-time operational visibility into their customer and booking data through Google Sheets — a familiar, mobile-friendly interface. Supabase remains the single source of truth. Sheets is a read-only mirror that syncs automatically after every Supabase write.

### Non-Goals
- Two-way sync (Sheets → Supabase)
- Real-time collaboration or data entry via Sheets
- Replacement for the Phase 2 dashboard (CRM Interface, PRD-03)

---

## System Boundary

### In Scope
- Unidirectional sync: Supabase → Google Sheets
- Tables: `customers` and `bookings` only
- Fire-and-forget error handling (Sheets failure never blocks agent)
- Per-client configuration (enable/disable, spreadsheet ID)
- Service account authentication (same pattern as Google Calendar)

### Out of Scope (Phase 1)
- `interactions_log` sync (too verbose)
- Batch/scheduled sync (only real-time post-write)
- Retry logic on failure
- Delete propagation (Supabase deletes do not remove Sheets rows)
- Historical data backfill
- Client self-service spreadsheet creation

---

## 1. Module Design — `engine/integrations/google_sheets.py`

### 1.1 Public API

Two async functions that never raise exceptions:

```python
async def sync_customer_to_sheets(
    client_id: str,
    client_config: ClientConfig,
    customer_data: dict,
) -> None:
    """
    Sync a customer row to Google Sheets "Customers" tab.
    
    Fire-and-forget — swallows all exceptions internally.
    Logs errors with full context (client_id, table, row ID).
    
    Args:
        client_id: Client identifier (e.g., "hey-aircon")
        client_config: Loaded ClientConfig object (contains sheets_* fields)
        customer_data: Customer row from Supabase as dict (all columns)
    
    Returns:
        None — always succeeds (logs errors internally)
    
    Behavior:
        - If sheets_sync_enabled=false: return immediately (no-op)
        - If sheets_spreadsheet_id is missing: log error, return
        - If Google API fails: log error, return
        - On success: row updated or appended to "Customers" tab
    """

async def sync_booking_to_sheets(
    client_id: str,
    client_config: ClientConfig,
    booking_data: dict,
) -> None:
    """
    Sync a booking row to Google Sheets "Bookings" tab.
    
    Fire-and-forget — swallows all exceptions internally.
    Logs errors with full context (client_id, table, row ID).
    
    Args:
        client_id: Client identifier
        client_config: Loaded ClientConfig object
        booking_data: Booking row from Supabase as dict (all columns)
    
    Returns:
        None — always succeeds (logs errors internally)
    """
```

### 1.2 Internal Logic Flow

Both functions follow the same pattern:

1. **Config check**: If `client_config.sheets_sync_enabled` is `False`, return immediately.
2. **Validation**: If `sheets_spreadsheet_id` or `sheets_service_account_creds` is missing, log error and return.
3. **Authentication**: Build Google Sheets service using service account credentials.
4. **Get spreadsheet**: Fetch the spreadsheet by ID.
5. **Get tab**: Open the correct tab ("Customers" or "Bookings").
6. **Header initialization**: If tab is empty, write header row first.
7. **Row deduplication**: Linear scan of column A (ID column) to find existing row.
8. **Upsert**: If row found, update it. If not found, append new row.
9. **Error handling**: Wrap entire function body in `try/except`. On any exception, log with full context and return silently.

### 1.3 Thread Safety — Blocking I/O in Executor

Google Sheets API libraries (both `gspread` and `google-api-python-client`) are synchronous. To prevent blocking the async event loop, all Google API calls MUST run in a thread-pool executor.

**Pattern (same as `google_calendar.py`):**
```python
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, blocking_function, args)
```

**Blocking operations:**
- Service account authentication
- Spreadsheet fetch
- Tab read (get all values)
- Tab write (update row or append row)

**Non-blocking operations:**
- Config checks
- Logging
- Data transformation (dict → list)

### 1.4 Row Deduplication — Linear Scan Strategy

**Problem:** Google Sheets API does not support upsert-by-ID. We must manually detect duplicates.

**Chosen approach:** Linear scan (OQ-2 Option A from requirements)

**Algorithm:**
1. Read all values from the tab using `worksheet.get_all_values()`
2. Extract column A (the ID column — index 0) from all rows
3. Search for a row where `column_A == supabase_row["id"]` (UUID match)
4. If found: update that row using `worksheet.update(range, [[values]])`
5. If not found: append new row using `worksheet.append_row([values])`

**Edge cases:**
- **Empty sheet:** No header row exists. Write header row first, then append data row.
- **Header only:** Header row exists, but no data rows. Append data row after header.
- **Multiple matches:** UUID found in multiple rows (should never happen, but possible if manual edits occurred). Update the **first match** only. Log warning.

**Performance:** Linear scan is O(n) where n = number of rows. For Phase 1 scale (HeyAircon: ~100 customers, ~200 bookings), this is acceptable. If a client exceeds 1000 rows per tab, consider upgrading to Option B (in-memory cache) in Phase 2.

### 1.5 Column Mapping — 1:1 Schema Fidelity

**No transformation.** Every Supabase column maps to a Sheets column with the same data type and value.

**"Customers" tab:**
| Supabase Column | Sheets Header (Row 1) | Data Type | Notes |
|-----------------|----------------------|-----------|-------|
| `id` | ID | UUID | Primary key, used for deduplication |
| `phone_number` | Phone Number | Text | E.164 format (e.g., +6512345678) |
| `display_name` | Display Name | Text | |
| `first_seen` | First Seen | Timestamp | ISO 8601 string |
| `last_seen` | Last Seen | Timestamp | ISO 8601 string |
| `booking_count` | Booking Count | Integer | |
| `escalation_flag` | Escalation Flag | Boolean | TRUE/FALSE |

**"Bookings" tab:**
| Supabase Column | Sheets Header (Row 1) | Data Type | Notes |
|-----------------|----------------------|-----------|-------|
| `id` | ID | UUID | Primary key |
| `phone_number` | Phone Number | Text | |
| `customer_name` | Customer Name | Text | |
| `service_type` | Service Type | Text | |
| `booking_date` | Booking Date | Date | YYYY-MM-DD |
| `booking_time` | Booking Time | Text | HH:MM or slot window (AM/PM) |
| `address` | Address | Text | |
| `unit_number` | Unit Number | Text | |
| `notes` | Notes | Text | |
| `status` | Status | Text | |
| `created_at` | Created At | Timestamp | ISO 8601 string |

**Timestamp formatting (OQ-4 Option A):** All timestamps are written as ISO 8601 strings (e.g., `2026-04-20T14:30:00Z`). Google Sheets auto-detects these as datetime values and renders them according to the user's locale. Clients can apply custom number formatting in Sheets if desired.

**Boolean formatting:** Write `TRUE` or `FALSE` (uppercase). Sheets interprets these as boolean values.

### 1.6 Header Initialization

**Problem:** On first sync, the tab may be completely empty (no header row).

**Solution:**
1. Read all values from the tab
2. If row count = 0: write header row first
3. Then append the data row

**Header rows (exact strings):**
- **"Customers" tab:** `["ID", "Phone Number", "Display Name", "First Seen", "Last Seen", "Booking Count", "Escalation Flag"]`
- **"Bookings" tab:** `["ID", "Phone Number", "Customer Name", "Service Type", "Booking Date", "Booking Time", "Address", "Unit Number", "Notes", "Status", "Created At"]`

### 1.7 Error Handling — Fire-and-Forget

**Hard requirement:** Sheets sync failure MUST NOT block the agent's response to the customer.

**Error handling strategy:**
1. Wrap the entire function body in `try/except Exception`
2. On any exception, log the error with full context:
   - `client_id`
   - Table name (`customers` or `bookings`)
   - Row ID (Supabase UUID)
   - Operation (`insert` or `update`)
   - Error type and message
   - Stack trace
3. Return silently — do NOT re-raise

**Failure scenarios:**
- Google Sheets API unreachable (timeout, 5xx)
- Rate limit exceeded (429)
- Service account credentials invalid (401, 403)
- Spreadsheet not found (404)
- Invalid spreadsheet ID in config
- Tab name does not exist ("Customers" or "Bookings")
- Network timeout

**No retry logic in Phase 1 (OQ-1 Option A).** Failed syncs are logged but never retried. If business owners report missing data, retry logic can be added in Phase 2.

---

## 2. Config Changes — `ClientConfig` and `clients` Table

### 2.1 New ClientConfig Fields

Add three new fields to the `ClientConfig` dataclass in `engine/config/client_config.py`:

```python
@dataclass
class ClientConfig:
    # ... existing fields ...
    
    # Google Sheets sync config (loaded from shared clients table)
    sheets_sync_enabled: bool
    sheets_spreadsheet_id: str | None
    sheets_service_account_creds: dict
```

**Field descriptions:**
- `sheets_sync_enabled`: Master switch. If `False`, all sync operations are skipped (no API calls). Default: `False`.
- `sheets_spreadsheet_id`: Google Sheets spreadsheet ID (extracted from URL). Example: `1a2b3c4d5e6f7g8h9i0j`. Required if `sheets_sync_enabled=True`.
- `sheets_service_account_creds`: Google service account credentials JSON (same structure as `google_calendar_creds`). Dict with keys: `type`, `project_id`, `private_key_id`, `private_key`, `client_email`, etc.

### 2.2 Supabase DDL — Alter `clients` Table

Add three new columns to the shared `clients` table:

```sql
ALTER TABLE clients 
ADD COLUMN sheets_sync_enabled BOOLEAN DEFAULT FALSE;

ALTER TABLE clients 
ADD COLUMN sheets_spreadsheet_id TEXT;

ALTER TABLE clients 
ADD COLUMN sheets_service_account_creds JSONB;
```

**Migration strategy:**
- Existing rows: `sheets_sync_enabled` defaults to `FALSE` → no impact on existing clients
- New clients: Flow AI team sets these values during onboarding

### 2.3 Config Loading — Update `load_client_config()`

Modify the `load_client_config()` function in `engine/config/client_config.py` to load the new fields from Supabase:

**Current pattern (Google Calendar creds):**
```python
google_calendar_creds_json = os.getenv(f"{client_id_upper}_GOOGLE_CALENDAR_CREDS", "{}")
google_calendar_creds = json.loads(google_calendar_creds_json)
```

**New pattern (Sheets creds):**
```python
# Load from Supabase row (NOT env vars — not sensitive enough to require env storage)
sheets_sync_enabled = row.get("sheets_sync_enabled", False)
sheets_spreadsheet_id = row.get("sheets_spreadsheet_id")
sheets_service_account_creds = row.get("sheets_service_account_creds", {})
```

**Rationale for Supabase storage (OQ-6):**
- Service account credentials have limited blast radius (read/write one spreadsheet only, no usage cost)
- Storing in Supabase allows per-client service accounts without requiring env var changes + redeploy
- Aligns with existing `google_calendar_creds` pattern
- Future-proofing: if we need 10+ clients, env var management becomes unwieldy

**Cache behavior:**
- `ClientConfig` cache TTL remains 5 minutes
- Changes to `sheets_sync_enabled` or `sheets_spreadsheet_id` in Supabase take effect within 5 minutes (no redeploy required)

### 2.4 Credential Storage Security Note

**Current decision:** Store credentials in Supabase `clients` table (same as Google Calendar).

**Future migration path (10–20 clients):** Move to a secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault). The credential loading logic in `load_client_config()` can be updated to fetch from the secrets manager instead of Supabase without changing the `ClientConfig` dataclass or downstream code.

---

## 3. Call Site Hooks

### 3.1 Customer Upsert — `engine/core/message_handler.py`

**Location:** After Step 5 (customer upsert) completes successfully.

**Current code (simplified, line ~149):**
```python
# New customer
await db.table("customers").insert({
    "phone_number": phone_number,
    "customer_name": display_name,
    "first_seen": now,
    "last_seen": now,
    "escalation_flag": False,
}).execute()

# OR returning customer
await db.table("customers").update({
    "last_seen": _now,
}).eq("phone_number", phone_number).execute()
```

**Hook to add (after both insert and update):**
```python
# After Supabase write completes
asyncio.create_task(
    sync_customer_to_sheets(
        client_id=client_id,
        client_config=client_config,
        customer_data={
            "id": customer_row["id"],  # Must fetch from DB or extract from response
            "phone_number": phone_number,
            "display_name": display_name,
            "first_seen": customer_row["first_seen"],
            "last_seen": customer_row["last_seen"],
            "booking_count": customer_row.get("booking_count", 0),
            "escalation_flag": customer_row.get("escalation_flag", False),
        },
    )
)
```

**Critical detail:** The customer `id` (UUID) must be available. For **new customer inserts**, the Supabase response includes the generated UUID. For **updates**, the `id` must be fetched from the existing `customer_row` (which is already loaded in Step 4 of `message_handler.py`).

**Implementation note for SDET:** The `customer_row` variable is already in scope (loaded in Step 4). For new customers, capture the insert response to extract the `id`. For returning customers, use `customer_row["id"]`.

### 3.2 Booking Insert — `engine/core/tools/booking_tools.py`

**Location:** After `write_booking()` inserts to `bookings` table (line ~206).

**Current code (simplified):**
```python
booking_row = {
    "booking_id": booking_id,
    "phone_number": phone_number,
    "service_type": service_type,
    "unit_count": unit_count,
    "slot_date": slot_date,
    "slot_window": slot_window,
    "booking_status": "Confirmed",
}
await db.table("bookings").insert(booking_row).execute()
```

**Hook to add (after insert):**
```python
# After Supabase insert completes
asyncio.create_task(
    sync_booking_to_sheets(
        client_id=client_id,
        client_config=client_config,
        booking_data=booking_row,  # Contains all booking columns
    )
)
```

**Note:** The `booking_row` dict already contains all required fields. No additional fetching needed.

### 3.3 Fire-and-Forget Pattern — `asyncio.create_task()`

**Rationale:** `asyncio.create_task()` schedules the sync function to run in the background without blocking the current execution path. The agent can send its WhatsApp reply immediately without waiting for the Sheets API call to complete.

**Behavior:**
- The sync task runs asynchronously
- If it fails, the exception is logged internally (never propagates to the webhook handler)
- The webhook handler always returns `200 OK` to Meta, regardless of Sheets sync outcome

**Trade-off:** If the engine crashes before the background task completes, that sync operation is lost. This is acceptable because:
1. The Supabase write succeeded (source of truth preserved)
2. The next write to that row will overwrite the missing data (eventual consistency)
3. Sheets sync is not critical path

---

## 4. Row Deduplication Logic — Detailed Specification

### 4.1 Algorithm

**Step-by-step:**

1. **Authenticate**: Build Google Sheets service using service account credentials.
2. **Open spreadsheet**: Fetch spreadsheet by ID.
3. **Open tab**: Get the worksheet by name ("Customers" or "Bookings").
4. **Read all rows**: Call `worksheet.get_all_values()` → returns list of lists (rows).
5. **Check for empty sheet**:
   - If `len(rows) == 0`: Write header row, then append data row. Done.
6. **Extract ID column**: For each row (starting from row 2, skipping header), extract column A (index 0).
7. **Search for UUID**:
   - Iterate through rows, comparing `row[0]` to `supabase_row["id"]`
   - If match found: note the row number (1-indexed for Sheets API)
8. **Upsert**:
   - **If match found**: Update that row using `worksheet.update(range, [[values]])`
     - Range example: `A5:G5` (for "Customers" tab, row 5)
   - **If no match**: Append new row using `worksheet.append_row([values])`
     - Values example: `[id, phone, name, first_seen, last_seen, count, flag]`

### 4.2 Pseudocode

```
function sync_row_to_sheets(tab_name, supabase_row):
    # Step 1-3: Auth + open spreadsheet + open tab
    worksheet = open_worksheet(spreadsheet_id, tab_name)
    
    # Step 4: Read all rows
    all_rows = worksheet.get_all_values()
    
    # Step 5: Handle empty sheet
    if len(all_rows) == 0:
        header = get_header_for_tab(tab_name)
        worksheet.append_row(header)
        data_row = convert_supabase_row_to_list(supabase_row)
        worksheet.append_row(data_row)
        return
    
    # Step 6-7: Extract ID column and search
    header_row = all_rows[0]
    data_rows = all_rows[1:]
    target_id = supabase_row["id"]
    
    match_row_index = None
    for i, row in enumerate(data_rows):
        if row[0] == target_id:  # Column A = ID
            match_row_index = i + 2  # +2 because: 1-indexed + skip header
            break
    
    # Step 8: Upsert
    data_row = convert_supabase_row_to_list(supabase_row)
    if match_row_index is not None:
        # Update existing row
        range_str = f"A{match_row_index}:{last_column}{match_row_index}"
        worksheet.update(range_str, [data_row])
    else:
        # Append new row
        worksheet.append_row(data_row)
```

### 4.3 Edge Cases

| Scenario | Behavior |
|----------|----------|
| Empty sheet (no header) | Write header row first, then append data row |
| Header only (no data rows) | Append data row after header |
| UUID found in multiple rows | Update **first match** only. Log warning: "Duplicate ID found in Sheets for {client_id}/{tab_name}/{uuid}" |
| UUID in wrong format (not a valid UUID) | Attempt match anyway (string comparison). If no match, append. |
| Supabase row has NULL fields | Write empty string to Sheets for that column |
| Sheets row has extra columns (manual edits) | Ignore extra columns. Only update the columns we control. |
| Concurrent writes to same row | No locking mechanism. Last write wins. (Acceptable for Phase 1 — concurrent writes to the same customer/booking are rare.) |

### 4.4 Performance Characteristics

- **Time complexity:** O(n) where n = number of rows in the tab
- **Space complexity:** O(n) — `get_all_values()` loads entire sheet into memory
- **Acceptable scale:** Up to ~1000 rows per tab (typical SME scale: 100–500)
- **Bottleneck:** Google Sheets API rate limits (100 read requests per 100 seconds per user). For Phase 1 (1 client, <10 messages/hour), this is not a concern.

**When to upgrade (Phase 2):**
- If a client exceeds 1000 rows per tab → implement in-memory cache (OQ-2 Option B)
- If multiple clients cause rate limit errors → implement batch sync queue

---

## 5. Data Flow Diagram

### 5.1 Success Path

```
[Customer sends WhatsApp message]
          |
          v
[Meta webhook → FastAPI handler]
          |
          v
[message_handler.py Step 5: Upsert customer in Supabase]
          |
          v--- (Supabase write succeeds)
          |
          +---> [asyncio.create_task(sync_customer_to_sheets)]
          |               |
          |               v
          |     [Background task: Google Sheets API]
          |               |
          |               v
          |     [Upsert row in "Customers" tab]
          |               |
          |               v
          |     [Log success (debug level)]
          |
          v
[Continue to Step 6: Agent runner]
          |
          v
[Send WhatsApp reply]
```

### 5.2 Failure Path

```
[Supabase customer upsert succeeds]
          |
          v
[asyncio.create_task(sync_customer_to_sheets)]
          |
          v
[Background task: Google Sheets API]
          |
          v--- (Google API fails: 503 Service Unavailable)
          |
          v
[Catch exception in sync function]
          |
          v
[Log error: client_id, table, row_id, error message]
          |
          v
[Return silently (no re-raise)]
          |
          |
[Agent continues normally]
          |
          v
[WhatsApp reply sent to customer]
```

**Key observation:** The failure path does NOT block the success path. The customer receives their reply on time, even if Sheets sync fails.

### 5.3 Config-Disabled Path

```
[Supabase write succeeds]
          |
          v
[asyncio.create_task(sync_customer_to_sheets)]
          |
          v
[Check: client_config.sheets_sync_enabled?]
          |
          NO
          |
          v
[Return immediately (no API calls, no logs)]
```

---

## 6. Dependencies

### 6.1 Python Library — Recommendation

**Two options:**

| Library | Pros | Cons | Recommendation |
|---------|------|------|----------------|
| **`gspread`** | Simple, Pythonic API. Built-in service account auth. High-level abstractions (`append_row`, `update`). | Adds an extra dependency layer on top of `google-api-python-client`. Slightly less control over low-level API. | ✅ **Recommended** for Phase 1 |
| **`google-api-python-client`** | Official Google library. Direct control over API. No abstraction layer. | Lower-level — requires more boilerplate code. Manual request construction. | Use if gspread proves insufficient |

**Chosen approach:** **`gspread`** for simplicity.

**Rationale:**
- Phase 1 needs basic CRUD operations only (read all, update row, append row)
- `gspread` abstracts away the complexity of Sheets API request formatting
- Service account auth is one line: `gspread.service_account_from_dict(creds)`
- Future migration to `google-api-python-client` is trivial if needed (same underlying API)

### 6.2 New Dependency to Add

**`engine/requirements.txt`:**
```
gspread==6.1.2
```

**Transitive dependencies (auto-installed):**
- `google-auth` (already used by `google_calendar.py`)
- `google-auth-oauthlib`

**No new environment variables required.** Credentials are stored in Supabase.

### 6.3 Import Structure

```python
# In engine/integrations/google_sheets.py
import gspread
from google.oauth2.service_account import Credentials
import asyncio
import logging

# Use gspread's built-in service account helper
gc = gspread.service_account_from_dict(creds_dict)
spreadsheet = gc.open_by_key(spreadsheet_id)
worksheet = spreadsheet.worksheet(tab_name)
```

---

## 7. Phase 2 Decommission Path

### 7.1 Graceful Shutdown Strategy

**Trigger:** Phase 2 dashboard (CRM Interface, PRD-03) is live and clients have migrated.

**Steps to disable (no code changes):**

1. **Per-client disable:**
   ```sql
   UPDATE clients 
   SET sheets_sync_enabled = false 
   WHERE client_id = 'hey-aircon';
   ```
   - Sync stops within 5 minutes (cache TTL)
   - No API calls made
   - No errors logged

2. **Platform-wide disable:**
   ```sql
   UPDATE clients 
   SET sheets_sync_enabled = false;
   ```

3. **Spreadsheet preservation:**
   - Leave spreadsheets accessible (clients keep "Viewer" access)
   - Mark as "Archived — Data frozen as of [date]" in sheet title
   - Clients can export to CSV if needed

### 7.2 Full Removal (Phase 3 — Code Cleanup)

**After all clients have migrated to dashboard:**

1. **Remove integration module:**
   ```bash
   rm engine/integrations/google_sheets.py
   ```

2. **Remove call sites:**
   - Delete `asyncio.create_task(sync_customer_to_sheets(...))` from `message_handler.py`
   - Delete `asyncio.create_task(sync_booking_to_sheets(...))` from `booking_tools.py`

3. **Remove config fields:**
   ```python
   # In ClientConfig dataclass, delete:
   sheets_sync_enabled: bool
   sheets_spreadsheet_id: str | None
   sheets_service_account_creds: dict
   ```

4. **Drop Supabase columns (optional):**
   ```sql
   ALTER TABLE clients 
   DROP COLUMN sheets_sync_enabled,
   DROP COLUMN sheets_spreadsheet_id,
   DROP COLUMN sheets_service_account_creds;
   ```
   - Optional: keep columns for historical reference (set to NULL)

5. **Remove dependency:**
   ```
   # In requirements.txt, delete:
   gspread==6.1.2
   ```

### 7.3 Migration Timeline Guardrails

**Client notification (founder decision):**
- Notify clients 30 days before disabling Sheets sync
- Provide dashboard onboarding + training
- Confirm they can access all critical data in the dashboard

**No forced migration:** Clients can request to keep Sheets sync enabled indefinitely (e.g., if they have custom formulas or integrations built on top of Sheets). This is acceptable as long as the sync module remains isolated and does not block platform evolution.

---

## 8. Integration Boundary — Google Sheets API

### 8.1 API Contract

**Canonical Integration Name:** Google Sheets API v4

**Authentication:**
- Mechanism: Service account (OAuth 2.0 JWT bearer token)
- Credential format: JSON key file with `private_key`, `client_email`, `project_id`, etc.
- Scope required: `https://www.googleapis.com/auth/spreadsheets`

**Endpoint:**
- Base URL: `https://sheets.googleapis.com/v4/spreadsheets`
- Spreadsheet ID: extracted from URL (e.g., `1a2b3c4d5e6f7g8h9i0j`)
- Full URL pattern: `https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}`

### 8.2 Operations Used

#### Read All Values (for deduplication)
- **Method:** `GET /v4/spreadsheets/{spreadsheetId}/values/{range}`
- **Range:** `Customers!A:Z` or `Bookings!A:Z` (all columns)
- **Response:** JSON array of rows (list of lists)
- **gspread method:** `worksheet.get_all_values()`

#### Update Row (existing row)
- **Method:** `PUT /v4/spreadsheets/{spreadsheetId}/values/{range}`
- **Range:** `Customers!A5:G5` (specific row)
- **Body:** `{ "values": [[id, phone, name, ...]] }`
- **gspread method:** `worksheet.update(range, [[values]])`

#### Append Row (new row)
- **Method:** `POST /v4/spreadsheets/{spreadsheetId}/values/{range}:append`
- **Range:** `Customers!A:A` (any column, API auto-appends)
- **Body:** `{ "values": [[id, phone, name, ...]] }`
- **gspread method:** `worksheet.append_row([values])`

### 8.3 Error Responses

| Status | Meaning | Engine Behavior |
|--------|---------|-----------------|
| 200 | Success | Log at debug level, return |
| 400 | Bad request (invalid range or data) | Log error with details, return |
| 401 | Unauthorized (invalid service account) | Log error "Service account auth failed", return |
| 403 | Forbidden (spreadsheet not shared) | Log error "Access denied to spreadsheet", return |
| 404 | Spreadsheet or tab not found | Log error "Spreadsheet/tab not found", return |
| 429 | Rate limit exceeded | Log error "Rate limit exceeded", return (no retry in Phase 1) |
| 500 | Google server error | Log error "Google API error", return |
| 503 | Service unavailable | Log error "Google Sheets unavailable", return |

**Timeout:** 10 seconds per API call (same as other external integrations). If timeout occurs, log error and return.

### 8.4 Rate Limits (Google Sheets API v4)

- **Read requests:** 100 per 100 seconds per user
- **Write requests:** 100 per 100 seconds per user
- **Per-project quota:** 500 requests per 100 seconds

**Phase 1 scale:** HeyAircon sends ~10 messages/hour → 10 Sheets writes/hour → well below limits.

**Multi-client scale:** If 10 clients each send 10 messages/hour, that's 100 writes/hour → still well below limits.

**If rate limit is hit:** Log error, skip sync, do not retry. Future enhancement: implement exponential backoff or queue.

---

## 9. Canonical Names

All types, fields, and operations defined in this document are canonical. Downstream agents (SDET, dispatches, implementation) must use these names exactly or include an explicit Name Mapping Table justifying any rename.

### 9.1 Module and Function Names

| Canonical Name | Type | Notes |
|----------------|------|-------|
| `google_sheets.py` | Module | File name must match exactly |
| `sync_customer_to_sheets` | Function | Public API — do not rename |
| `sync_booking_to_sheets` | Function | Public API — do not rename |

### 9.2 Config Field Names

| Canonical Name | Type | Notes |
|----------------|------|-------|
| `sheets_sync_enabled` | Config field (ClientConfig + DB column) | Boolean |
| `sheets_spreadsheet_id` | Config field (ClientConfig + DB column) | Text |
| `sheets_service_account_creds` | Config field (ClientConfig + DB column) | JSONB |

### 9.3 Tab Names

| Canonical Name | Notes |
|----------------|-------|
| `Customers` | Exact string — case-sensitive |
| `Bookings` | Exact string — case-sensitive |

### 9.4 Column Headers (Sheets)

**"Customers" tab:**
`["ID", "Phone Number", "Display Name", "First Seen", "Last Seen", "Booking Count", "Escalation Flag"]`

**"Bookings" tab:**
`["ID", "Phone Number", "Customer Name", "Service Type", "Booking Date", "Booking Time", "Address", "Unit Number", "Notes", "Status", "Created At"]`

**These are the exact strings that must appear in row 1 of each tab.** Do not rename or reorder without updating this contract.

---

## 10. Open Questions for SDET Review

These questions require SDET input before dispatch:

### Q1: Test Coverage
**Question:** Should we write unit tests for the sync functions, or only integration tests?

**Options:**
- **Option A:** Unit tests with mocked Google API (test deduplication logic, error handling, config checks)
- **Option B:** Integration tests against a real test spreadsheet (end-to-end validation)
- **Option C:** Both

**Recommendation:** Option C — unit tests for deduplication logic edge cases, integration test for one happy-path sync.

### Q2: Smoke Test Inclusion
**Question:** Should the clean-room smoke test create a test spreadsheet and verify sync works?

**Recommendation:** Yes — add a smoke test step that:
1. Creates a test customer in Supabase
2. Triggers `sync_customer_to_sheets` manually (not via webhook)
3. Verifies the row appears in Sheets with correct data

### Q3: Logging Level
**Question:** What log level should successful syncs use?

**Options:**
- **Debug:** `logger.debug("Synced customer {id} to Sheets")`
- **Info:** `logger.info("Synced customer {id} to Sheets")`

**Recommendation:** Debug for success (to avoid log noise), Error for failures.

---

## 11. Implementation Checklist

**Before dispatch to `@software-engineer`:**

- [ ] Requirements document approved by founder
- [ ] This architecture document reviewed by SDET
- [ ] Test plan created in `docs/test-plan/features/google_sheets_sync.md`
- [ ] Supabase DDL migration script created
- [ ] gspread library added to `requirements.txt`
- [ ] ClientConfig dataclass updated (add 3 new fields)
- [ ] `load_client_config()` updated to load new fields from DB

**After implementation:**

- [ ] Unit tests pass (deduplication logic, error handling)
- [ ] Integration test passes (sync to real test spreadsheet)
- [ ] Smoke test updated and passes
- [ ] Call sites hooked in (`message_handler.py` + `booking_tools.py`)
- [ ] Manual verification: customer message → row appears in Sheets within 10 seconds
- [ ] Manual verification: Sheets API failure → agent continues normally, error logged
- [ ] Manual verification: `sheets_sync_enabled=false` → no API calls, no errors
- [ ] Update `docs/architecture/code_map.md` with new file

---

## 12. Decisions and Trade-offs

| Decision | Chosen Approach | Alternatives Considered | Rationale |
|----------|----------------|------------------------|-----------|
| **Library** | gspread | google-api-python-client | Simpler API, built-in service account auth, sufficient for Phase 1 CRUD |
| **Retry strategy** | No retry (fire-and-forget) | Exponential backoff, persistent retry queue | Sheets sync is not critical path. Complexity not justified for Phase 1. |
| **Row deduplication** | Linear scan | In-memory cache, hidden hash column | O(n) acceptable for Phase 1 scale (<1000 rows). Cache adds complexity. |
| **Credential storage** | Supabase `clients` table | Railway env vars | Centralized, easier to manage at scale, aligns with Google Calendar pattern |
| **Timestamp format** | ISO 8601 string | Sheets-native datetime, localized string | Preserves timezone, consistent, easy to parse, Sheets auto-detects |
| **Config location** | Shared `clients` table | Per-client env vars | Changes take effect within 5 min (no redeploy), scales to N clients |
| **Sync trigger** | `asyncio.create_task` | Webhook-separate job queue | Simplest pattern, no new infrastructure, acceptable risk of lost syncs on crash |

---

## Status

**Current:** Draft — Ready for SDET Review

**Next steps:**
1. SDET reviews this architecture doc
2. SDET creates test plan in `docs/test-plan/features/google_sheets_sync.md`
3. SDET prepares dispatch for `@software-engineer`
4. Implementation begins

**Approval gates:**
- [ ] Founder approves requirements (`docs/requirements/google_sheets_sync.md`)
- [ ] SDET approves architecture (this document)
- [ ] Test plan approved before dispatch

---

**End of Architecture Document**
