# Google Sheets Data Sync — Requirements Document

**Feature Owner:** `@product-manager`  
**Date Created:** 2026-04-20  
**Status:** Draft — Pending Founder Approval  
**Priority:** High (Phase 1 operational visibility)  
**Phase:** Phase 1 MVP  

---

## Direction Check

- **Subject:** HeyAircon business owner (and future SME clients) who need operational visibility into customer and booking data
- **Problem/Threat:** Cannot access their data because Supabase Studio is too technical; need a familiar, accessible tool for day-to-day operations
- **Confirmation:** Solution provides the subject (non-technical business owners) with real-time data visibility through Google Sheets — not an engineering debug tool, not a replacement for Supabase as source of truth, not a two-way sync that could corrupt data

---

## Feature Overview

### What It Is
A **unidirectional, post-write data sync** from Supabase to Google Sheets that gives Flow AI clients (starting with HeyAircon) real-time operational visibility into their customer and booking data without requiring technical database access.

### Who It's For
- **Primary:** HeyAircon business owner and future SME client business owners
- **Secondary:** Flow AI operations team (for client support and troubleshooting visibility)

### Why It Exists
Supabase Studio requires technical knowledge and direct database access. Business owners need to:
- See who messaged today
- Check upcoming bookings
- Monitor customer engagement patterns
- Access data from mobile devices

Google Sheets provides a familiar, mobile-friendly interface that non-technical users already know.

### Phase 2 Migration Path
A full dashboard (CRM Interface, PRD-03) will replace Google Sheets in Phase 2. This sync layer must be designed so that:
1. Disabling the Sheets sync (via config flag) does not break any core platform functionality
2. The sync logic is isolated in a single module (`integrations/google_sheets.py`)
3. No business logic depends on Sheets — it is a **read-only visibility layer only**

---

## Functional Requirements

### FR-1: Sync Trigger
**Requirement:** The sync operation MUST be triggered immediately after every successful Supabase write to `customers` or `bookings` tables.

**Rationale:** Real-time visibility is critical for operational use cases (e.g., confirming a booking was recorded, checking if a customer escalation flag was set).

**Write Points:**
- `core/message_handler.py` — customer upsert on every inbound WhatsApp message
- `core/tools/booking_tools.py` — booking insert after Google Calendar event creation

**Mechanism:** Async background task that runs after the Supabase write completes. Must not block the agent's response to the customer.

---

### FR-2: Sync Direction
**Requirement:** Data flows **Supabase → Google Sheets only**. The agent NEVER reads from Sheets. Clients NEVER write to Sheets.

**Rationale:** Supabase is the single source of truth. Two-way sync introduces data corruption risk and race conditions. Sheets is a read-only mirror for human visibility.

**Enforcement:**
- Google Sheets permissions must be set to "View Only" for all users except the service account
- No code path in the engine reads from Sheets
- Documentation must explicitly state that manual Sheets edits will be overwritten on the next sync

---

### FR-3: Tables to Sync
**Requirement:** Sync ONLY the following tables:
- `customers`
- `bookings`

**Explicitly excluded:** `interactions_log` (too verbose, not operationally relevant)

**Rationale:** Business owners need customer contact info and booking status — not conversation transcripts.

---

### FR-4: Column Mapping
**Requirement:** Column mapping MUST be 1:1 with Supabase schema. No transformation, no computed fields, no aggregations.

**`customers` → "Customers" tab:**
| Supabase Column | Sheets Column | Type | Notes |
|-----------------|---------------|------|-------|
| `id` | ID | UUID | |
| `phone_number` | Phone Number | Text | |
| `display_name` | Display Name | Text | |
| `first_seen` | First Seen | Timestamp | |
| `last_seen` | Last Seen | Timestamp | |
| `booking_count` | Booking Count | Integer | |
| `escalation_flag` | Escalation Flag | Boolean | TRUE/FALSE |

**`bookings` → "Bookings" tab:**
| Supabase Column | Sheets Column | Type | Notes |
|-----------------|---------------|------|-------|
| `id` | ID | UUID | |
| `phone_number` | Phone Number | Text | |
| `customer_name` | Customer Name | Text | |
| `service_type` | Service Type | Text | |
| `booking_date` | Booking Date | Date | |
| `booking_time` | Booking Time | Text | |
| `address` | Address | Text | |
| `unit_number` | Unit Number | Text | |
| `notes` | Notes | Text | |
| `status` | Status | Text | |
| `created_at` | Created At | Timestamp | |

**Header row:** First row of each tab contains the Sheets column names (human-readable, Title Case).

---

### FR-5: Sheet Structure
**Requirement:** One spreadsheet per client, with 2 tabs:
1. **"Customers"** — syncs `customers` table
2. **"Bookings"** — syncs `bookings` table

**Spreadsheet ownership:** Created manually by Flow AI team during client onboarding. Service account granted "Editor" access. Business owner granted "Viewer" access.

**Row operation logic:**
- **Insert:** If the Supabase row's `id` does not exist in the Sheets tab, append a new row
- **Update:** If the Supabase row's `id` exists in the Sheets tab, update that row's columns
- **Delete:** Not supported in Phase 1. Deletes in Supabase do not propagate to Sheets. (Row remains in Sheets with stale data.)

---

### FR-6: Authentication
**Requirement:** Use Google service account credentials (reuse existing Google Calendar service account pattern).

**Service account permissions:**
- "Editor" access to the client's spreadsheet
- Access granted via the spreadsheet's Share settings (share to service account email)

**Config storage:** Service account JSON credentials stored in per-client Supabase database (same pattern as `google_calendar_creds` column in `clients` table).

---

### FR-7: Configuration
**Requirement:** Sheets sync MUST be configurable per client via the shared `clients` table.

**New columns to add to `clients` table:**
| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `sheets_sync_enabled` | Boolean | `false` | Master switch. If `false`, all sync operations are skipped. |
| `sheets_spreadsheet_id` | Text | `NULL` | Google Sheets spreadsheet ID (extracted from the spreadsheet URL). Required if `sheets_sync_enabled=true`. |

**Validation:** If `sheets_sync_enabled=true` but `sheets_spreadsheet_id` is NULL or empty, log an error and skip sync (do not crash).

---

### FR-8: Failure Handling
**Requirement:** Sheets sync failure MUST be **fire-and-forget**. A failed Sheets write NEVER rolls back the Supabase write.

**Rationale:** The customer's booking or message is the source of truth. The agent's job is to serve the customer, not to maintain a Sheets mirror. Sheets outages cannot degrade booking flows.

**Failure scenarios:**
- Google Sheets API unreachable (timeout, 5xx)
- Rate limit exceeded
- Service account credentials invalid
- Spreadsheet not found or access denied
- Invalid spreadsheet ID in config

**Failure response:**
1. Log the error with full context (client_id, table, row ID, error message)
2. Alert via logging/monitoring (future: send to alerting channel)
3. Continue execution — do NOT raise exception to caller
4. Do NOT retry automatically (retry logic is an open question for architect)

---

## Non-Functional Requirements

### NFR-1: Performance — No Agent Latency Impact
**Requirement:** Sheets sync MUST NOT add latency to the agent's response to the customer.

**Implementation approach:** Run the sync as an async background task (e.g., `asyncio.create_task()`) after the Supabase write completes and the agent response is sent to the customer.

**Acceptance:** Agent response time (measured from webhook receipt to WhatsApp API send) must not increase by more than 50ms when Sheets sync is enabled vs. disabled.

---

### NFR-2: Reliability — Graceful Degradation
**Requirement:** If Google Sheets API is unavailable, the agent MUST continue to function normally. Bookings, customer upserts, and message handling are unaffected.

**Acceptance:** 
- 100% Sheets API failure rate for 1 hour → zero agent failures, zero booking failures
- Customer experiences no difference whether Sheets sync is working or not

---

### NFR-3: Observability — Failure Visibility
**Requirement:** Every Sheets sync failure MUST be logged with sufficient context to debug and remediate.

**Log fields:**
- Timestamp
- Client ID
- Table name (`customers` or `bookings`)
- Row ID (Supabase UUID)
- Operation (`insert` or `update`)
- Error type (timeout, 5xx, auth failure, etc.)
- Error message

**Acceptance:** On sync failure, Flow AI team can identify which client, which row, and what error occurred without needing to reproduce the failure.

---

### NFR-4: Data Freshness
**Requirement:** Sheets data SHOULD reflect Supabase data within 10 seconds of a write under normal conditions.

**Rationale:** Business owner checks Sheets immediately after a customer books. 10-second lag is acceptable; 5-minute lag is not.

**Caveat:** This is a target, not a hard requirement. If Google Sheets API is slow (rare but possible), the sync may take longer. The critical requirement is that the sync eventually completes or fails gracefully.

---

## User Stories

### US-1: Business Owner — View Today's Bookings
**As** HeyAircon's business owner,  
**I want** to open a Google Sheet and see all bookings created today,  
**So that** I can plan technician dispatch and confirm customer appointments without asking the dev team.

**Acceptance Criteria:**
- [ ] Booking appears in the "Bookings" tab within 10 seconds of customer confirmation via WhatsApp
- [ ] All booking fields (date, time, address, service type) are visible and correct
- [ ] I can filter/sort by "Booking Date" column to see today's appointments
- [ ] I can access the sheet from my phone

---

### US-2: Business Owner — Check Customer Escalation Status
**As** HeyAircon's business owner,  
**I want** to see which customers are flagged for escalation,  
**So that** I can prioritize follow-up calls for sensitive or high-value customers.

**Acceptance Criteria:**
- [ ] "Customers" tab has an "Escalation Flag" column showing TRUE/FALSE
- [ ] When a customer is escalated (via the agent's `escalate` tool), the flag updates in Sheets within 10 seconds
- [ ] I can filter the "Escalation Flag" column to show only TRUE rows

---

### US-3: Flow AI Operator — Support Client Without DB Access
**As** a Flow AI support operator,  
**I want** to view a client's customer and booking data in Sheets,  
**So that** I can troubleshoot issues or answer client questions without requiring Supabase Studio access.

**Acceptance Criteria:**
- [ ] I am granted "Viewer" access to all client spreadsheets
- [ ] Data in Sheets matches Supabase (verified via spot-check)
- [ ] I can share the spreadsheet URL with the client for self-service visibility

---

### US-4: Flow AI Engineer — Disable Sync Without Breaking Agent
**As** a Flow AI engineer,  
**I want** to disable Sheets sync for a client (via config flag),  
**So that** I can troubleshoot sync issues or migrate to the Phase 2 dashboard without affecting the agent's core functionality.

**Acceptance Criteria:**
- [ ] Set `clients.sheets_sync_enabled = false` in Supabase
- [ ] Agent continues to handle messages, upsert customers, and create bookings normally
- [ ] No Sheets API calls are made for that client
- [ ] No errors are logged related to Sheets sync

---

## Acceptance Criteria (Feature-Level)

### AC-1: Sync Trigger — Immediate Post-Write
- [ ] Given a new customer message arrives via WhatsApp
- [ ] When `message_handler` upserts the `customers` table
- [ ] Then the Sheets sync triggers immediately after the Supabase write completes
- [ ] And the "Customers" tab updates within 10 seconds

### AC-2: Sync Trigger — Booking Creation
- [ ] Given the agent successfully creates a booking via `write_booking` tool
- [ ] When the `bookings` table insert completes
- [ ] Then the Sheets sync triggers immediately after
- [ ] And the "Bookings" tab updates within 10 seconds

### AC-3: Column Mapping — 1:1 Accuracy
- [ ] Given a booking with all fields populated (address, unit_number, notes, etc.)
- [ ] When synced to Sheets
- [ ] Then every Sheets column matches the corresponding Supabase column exactly
- [ ] And no data transformation or truncation occurs

### AC-4: Row Insert — New Record
- [ ] Given a new customer with a unique `id` (UUID)
- [ ] When synced to Sheets
- [ ] Then a new row is appended to the "Customers" tab
- [ ] And the row contains the correct data in all columns

### AC-5: Row Update — Existing Record
- [ ] Given an existing customer whose `last_seen` timestamp or `booking_count` changes
- [ ] When synced to Sheets
- [ ] Then the existing row (matched by `id`) is updated
- [ ] And no duplicate row is created

### AC-6: Failure — Sheets Outage Does Not Block Agent
- [ ] Given Google Sheets API returns 503 Service Unavailable
- [ ] When the agent processes a customer message
- [ ] Then the message is handled normally (Supabase write succeeds, WhatsApp reply sent)
- [ ] And the Sheets sync failure is logged
- [ ] And no exception is raised to the webhook handler

### AC-7: Failure — Invalid Spreadsheet ID
- [ ] Given `clients.sheets_spreadsheet_id` contains an invalid ID
- [ ] When a sync is triggered
- [ ] Then the error is logged ("Spreadsheet not found")
- [ ] And the Supabase write is not rolled back
- [ ] And the agent continues normally

### AC-8: Config — Sync Disabled
- [ ] Given `clients.sheets_sync_enabled = false`
- [ ] When any Supabase write occurs
- [ ] Then no Sheets API calls are made
- [ ] And no Sheets-related logs are written
- [ ] And the agent functions normally

### AC-9: Config — Spreadsheet ID Missing
- [ ] Given `clients.sheets_sync_enabled = true` but `sheets_spreadsheet_id = NULL`
- [ ] When a sync is triggered
- [ ] Then an error is logged ("Sheets sync enabled but spreadsheet ID missing")
- [ ] And the sync is skipped
- [ ] And the agent continues normally

### AC-10: Permissions — Read-Only for Client
- [ ] Given the HeyAircon business owner has "Viewer" access to the spreadsheet
- [ ] When they attempt to edit a cell
- [ ] Then the edit is rejected by Google Sheets
- [ ] And a message appears: "You need permission to edit this spreadsheet"

---

## Out of Scope (Explicit Exclusions)

### Explicitly NOT Included in Phase 1:
1. **`interactions_log` sync** — Too verbose, not operationally useful
2. **Sheets → Supabase sync** — Sheets is read-only. Manual edits in Sheets are NOT synced back to Supabase.
3. **Delete propagation** — Deletes in Supabase do NOT remove rows from Sheets
4. **Computed columns** — No aggregations, no formulas, no derived fields (e.g., "Total Revenue")
5. **Batch sync** — No scheduled/periodic full-table sync. Only real-time post-write sync.
6. **Retry logic** — Phase 1 does not retry failed syncs. (Open question for architect.)
7. **Data validation in Sheets** — Sheets rows are not validated. If Supabase writes invalid data (e.g., malformed phone number), it syncs as-is.
8. **Multi-spreadsheet support** — One spreadsheet per client only. No splitting customers/bookings across multiple sheets.
9. **Client self-service spreadsheet creation** — Flow AI team creates the spreadsheet during onboarding. Clients cannot create their own.
10. **Historical backfill** — Phase 1 does not backfill existing Supabase data into a newly configured spreadsheet. Only new writes are synced. (Future enhancement.)

---

## Open Questions for Architect

These questions require `@software-architect` input before implementation:

### OQ-1: Retry Strategy
**Question:** Should failed Sheets syncs be retried? If yes, what is the retry policy?

**Options:**
- **Option A:** No retry — fire-and-forget. Failed sync is logged, never retried. (Simplest, aligns with "Sheets is not critical path")
- **Option B:** Retry with exponential backoff (1s, 2s, 4s, max 3 retries). If all retries fail, log and give up.
- **Option C:** Queue failed syncs in a persistent retry queue (e.g., Redis, Postgres table). Background worker retries periodically.

**Recommendation:** Start with **Option A** (no retry). If business owner reports missing data, upgrade to Option B or C in a future iteration.

---

### OQ-2: Row Deduplication Strategy
**Question:** How do we prevent duplicate rows in Sheets when the same Supabase row is written multiple times?

**Challenge:** Google Sheets API does not have a native "upsert by ID" operation. We must:
1. Search the tab for a row where column A (ID) matches the Supabase UUID
2. If found, update that row. If not found, append a new row.

**Implementation approaches:**
- **Option A:** Linear scan — read all rows, search for matching ID, update/append accordingly. (Simple, slow for large sheets >1000 rows)
- **Option B:** Maintain an in-memory cache of `{supabase_id: sheet_row_number}`. Cache is rebuilt on engine restart by reading the sheet once. (Faster, adds complexity)
- **Option C:** Use a hidden column in Sheets to store a hash of the row. Compare hash to detect changes. (Complex, fragile)

**Recommendation:** Start with **Option A** (linear scan). HeyAircon will have <100 customers and <200 bookings in Phase 1. Performance is not a bottleneck yet.

---

### OQ-3: Row Ordering
**Question:** Should new rows be appended to the bottom of the sheet, or inserted at the top (most recent first)?

**User preference:** Most recent bookings/customers at the top is more useful for daily operations.

**Implementation complexity:**
- Append to bottom: trivial (one API call)
- Insert at top: requires shifting existing rows down (more API calls, slower)

**Recommendation:** Append to bottom for Phase 1. Client can manually sort by "Created At" or "Booking Date" descending if they want most recent first.

---

### OQ-4: Timestamp Formatting
**Question:** How should Supabase `timestamp` columns be formatted in Sheets?

**Options:**
- **Option A:** ISO 8601 string (e.g., `2026-04-20T14:30:00Z`) — preserves timezone, easy to parse
- **Option B:** Sheets-native datetime format (detected automatically by Sheets API based on locale)
- **Option C:** Localized string (e.g., `20 Apr 2026, 2:30 PM SGT`) — human-readable, not sortable

**Recommendation:** **Option A** (ISO 8601) for consistency. Sheets will auto-detect and render it as a datetime. Client can apply custom number formatting in Sheets if they prefer a different display format.

---

### OQ-5: Error Alerting Channel
**Question:** Where should Sheets sync errors be sent for human visibility?

**Current state:** Errors are logged to stdout/Railway logs. Flow AI team must manually check logs to detect failures.

**Future enhancement:** Send errors to a Slack channel, email, or PagerDuty. Not required for Phase 1, but architect should design the sync module so that an alerting hook can be added later without refactoring.

**Recommendation:** Design `integrations/google_sheets.py` with a pluggable error callback (e.g., `on_sync_error(client_id, error)`) that defaults to logging but can be swapped for alerting in Phase 2.

---

### OQ-6: Service Account Credential Storage
**Question:** Should Google service account credentials be stored in the shared `clients` table (like `google_calendar_creds`) or in Railway env vars (like LLM keys)?

**Trade-offs:**
- **Shared `clients` table:** Centralized, easier to manage at scale, client-specific credentials possible
- **Railway env vars:** More secure (secrets manager pattern), but requires redeploy to change credentials

**Recommendation:** Use the **shared `clients` table** pattern (same as Google Calendar). Service account credentials are not as sensitive as LLM API keys (no usage cost, limited blast radius), and storing them in Supabase allows client-specific service accounts in the future.

---

### OQ-7: Phase 2 Migration — Decommission Strategy
**Question:** When the Phase 2 dashboard launches, how do we gracefully decommission Sheets sync?

**Requirements:**
- Client must be notified in advance ("Sheets will stop updating on [date]")
- Sync can be disabled via config flag without code changes
- Historical data in Sheets remains accessible (read-only archive)

**Recommendation:** 
1. Set `clients.sheets_sync_enabled = false` when dashboard goes live
2. Leave the spreadsheet accessible but frozen (client keeps "Viewer" access)
3. Remove `integrations/google_sheets.py` and related code in Phase 3 (after all clients migrated to dashboard)

This is a product/UX question as much as a technical one — defer to `@product-manager` and founder for timeline.

---

## Implementation Notes for Architect

### New Integration File
- **Path:** `engine/integrations/google_sheets.py`
- **Does not exist yet** — architect must create it

### Suggested Public API
```python
async def sync_customer_to_sheets(
    client_id: str,
    customer_data: dict,  # Supabase row as dict
) -> None:
    """
    Syncs a customer row to Google Sheets.
    Fire-and-forget — never raises exceptions.
    """

async def sync_booking_to_sheets(
    client_id: str,
    booking_data: dict,  # Supabase row as dict
) -> None:
    """
    Syncs a booking row to Google Sheets.
    Fire-and-forget — never raises exceptions.
    """
```

### Call Sites to Hook In
1. **`core/message_handler.py`** — after customer upsert:
   ```python
   # After Supabase customer upsert
   asyncio.create_task(sync_customer_to_sheets(client_id, customer_data))
   ```

2. **`core/tools/booking_tools.py`** — after booking insert:
   ```python
   # After Supabase booking insert
   asyncio.create_task(sync_booking_to_sheets(client_id, booking_data))
   ```

### Config Fetching
- Read `clients.sheets_sync_enabled` and `clients.sheets_spreadsheet_id` from the in-memory client config cache (same pattern as `google_calendar_creds`)
- If `sheets_sync_enabled = false`, return immediately (no API calls)

### Google Sheets API
- Use `gspread` library (Python) or `google-auth` + `google-api-python-client`
- Service account auth via JSON credentials (same as Google Calendar integration)

---

## Sign-off

**Product Manager:** Draft complete, pending founder approval.

**Founder Approval:** [ ] Approved — proceed to architecture phase

**Next Steps After Approval:**
1. Route to `@software-architect` to:
   - Design `integrations/google_sheets.py` module
   - Answer open questions (retry strategy, row deduplication, etc.)
   - Update `docs/architecture/integration-boundaries/google-sheets.md`
   - Define Supabase schema changes (`clients` table: add `sheets_sync_enabled`, `sheets_spreadsheet_id`)
2. Route to `@sdet-engineer` to create test plan and dispatch implementation to `@software-engineer`
