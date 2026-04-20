# Architecture Decision Record — Address Fields: customers → bookings

**Status:** Approved — pending implementation
**Date:** 2026-04-20
**Author:** @software-architect
**Production release target:** End of April 2026

---

## Problem Statement

`address TEXT` and `postal_code TEXT` are currently stored on the `customers` table. The `write_booking()` tool (Step 3, `customer_update` dict) performs an UPDATE against the `customers` row after every confirmed booking, overwriting these two fields with whatever address was collected during the most recent booking conversation. For an aircon servicing company, address equals job location — a customer who books at their home one month and their office the next will have their home address silently and permanently destroyed in the CRM. There is no per-booking address history, no audit trail, and no way to recover the overwritten value. This is an operational data loss problem that worsens with each repeat customer.

---

## Approved Solution

Move `address` and `postal_code` from the `customers` table to the `bookings` table. Each booking row carries its own job address, recorded at the time of booking and never overwritten. The `customers` table retains the customer identity record (name, phone, escalation state, visit counts) but no longer stores address. Address becomes per-booking data, which matches the real-world semantics: an address is where the job happens, not a permanent attribute of the person.

---

## Migration Phases

### Phase 1 — Additive DDL (safe, no code change, no production risk)

Add the two columns to the `bookings` table. This is a non-breaking, additive schema change. Existing rows are unaffected (new columns default to NULL). No engine code changes. No production risk.

```sql
ALTER TABLE bookings
  ADD COLUMN address     TEXT,
  ADD COLUMN postal_code TEXT;
```

Execute this statement against the HeyAircon Supabase project (`heyaircon`) via the Supabase SQL Editor or psql. Verify column presence in Supabase Studio before proceeding to Phase 2.

**Rollback (Phase 1):** Drop the newly added columns. No data loss — they will have been empty.

```sql
ALTER TABLE bookings
  DROP COLUMN address,
  DROP COLUMN postal_code;
```

---

### Phase 2 — Code Change: write_booking() rewrite

**File:** `engine/core/tools/booking_tools.py`
**Function:** `write_booking()`

Two specific changes are required. Both are in the same function body.

#### Change A — Add address fields to `booking_row` dict (Step 2)

`booking_row` is the dict passed to `db.table("bookings").insert(booking_row).execute()`. Currently it does not include `address` or `postal_code`. After Phase 2, these fields shall be added unconditionally (they are always required inputs to `write_booking()`):

```
booking_row["address"]     = address
booking_row["postal_code"] = postal_code
```

These two assignments belong alongside the existing unconditional fields (`booking_id`, `phone_number`, `service_type`, `unit_count`, `slot_date`, `slot_window`, `booking_status`) in the `booking_row` dict initialisation block, not in the conditional blocks below it.

#### Change B — Remove address fields from `customer_update` dict (Step 3)

`customer_update` is the dict passed to `db.table("customers").update(customer_update).eq("phone_number", phone_number).execute()`. Currently it contains:

```
customer_update = {
    "customer_name": customer_name,
    "address":       address,
    "postal_code":   postal_code,
}
```

After Phase 2, `address` and `postal_code` shall be removed from `customer_update`. The dict becomes:

```
customer_update = {
    "customer_name": customer_name,
}
```

The `customer_update` block and the `db.table("customers").update(...)` call remain in place — only the two address fields are removed from the dict.

**No other files require changes in Phase 2.** The `write_booking()` function signature retains `address` and `postal_code` as parameters (they are still required inputs from the agent). The `_alert_booking_failure()` function also retains them for the human-readable failure alert — no change there.

**Deploy path:** Phase 2 code change goes through worktree → `@sdet-engineer` gate → PR → Railway release branch deploy. Do not deploy until Phase 1 DDL is confirmed live in Supabase.

**Rollback (Phase 2):** Revert the `booking_tools.py` change. The `bookings` address columns (from Phase 1) will retain whatever values were written during the Phase 2 window; the `customers` address columns will simply stop being updated going forward. No data is lost. If needed, a one-time backfill can copy address values from recent `bookings` rows back to `customers` before reverting.

---

### Phase 2.5 — Backfill (runs after Phase 2 is deployed and verified, before Phase 3 DDL)

**Decision (2026-04-20):** A one-time SQL backfill shall run before Phase 3 drops the columns. The backfill copies historical address data from the `customers` table into any existing `bookings` rows for that customer where `bookings.address IS NULL`. This preserves the historical address record against each booking row before the source columns are destroyed.

**Backfill logic:** For each customer row, copy `customers.address` and `customers.postal_code` to all `bookings` rows for that `phone_number` where `bookings.address IS NULL`.

```sql
-- Phase 2.5 Backfill — run after Phase 2 is confirmed working, before Phase 3 DDL.
-- This is a one-time operation. Safe to run multiple times (WHERE clause prevents overwrite of post-Phase-2 values).
UPDATE bookings b
SET
  address     = c.address,
  postal_code = c.postal_code
FROM customers c
WHERE b.phone_number = c.phone_number
  AND b.address IS NULL
  AND c.address IS NOT NULL;
```

**Pre-conditions for Phase 2.5:**
1. Phase 2 has been deployed and confirmed working in production.
2. At least one real post-Phase-2 booking has been inspected to confirm `bookings.address` is populated correctly by the new code.
3. Run the backfill in the Supabase SQL Editor. Verify row counts before and after — the number of updated rows should equal the number of pre-Phase-2 booking rows for customers who had an address on file.

**Rollback (Phase 2.5):** The backfill only writes to rows where `bookings.address IS NULL`. Rows written by Phase 2 code (which already have `address` populated) are untouched. If the backfill is run erroneously, affected rows can be set back to NULL — but this is rarely necessary since the source data (`customers.address`) still exists until Phase 3.

---

### Phase 3 — Cleanup DDL (explicit approval required — separate deployment)

**Do not execute Phase 3 without explicit approval from the founder after Phase 2 has been confirmed working in production.**

Phase 3 drops the now-unused address columns from `customers`. This is a destructive, irreversible operation. All address data on the `customers` table at the time of execution will be permanently deleted.

```sql
-- WARNING: DESTRUCTIVE AND IRREVERSIBLE.
-- Execute only after Phase 2 is confirmed working in production.
-- Back up or verify that all address data has been captured in bookings rows
-- before running this statement.
ALTER TABLE customers
  DROP COLUMN address,
  DROP COLUMN postal_code;
```

**Pre-conditions for Phase 3:**
1. Phase 2 has been deployed and confirmed working in production for at least one full booking cycle.
2. At least one real booking post-Phase-2 has been inspected to confirm `address` and `postal_code` are populated on the `bookings` row.
3. Founder gives explicit approval to proceed with the DROP.

**Rollback (Phase 3):** There is no rollback. Once the columns are dropped, historical address data on `customers` is gone. The `customers` table will still be correct going forward — address is now on `bookings`. But any address data that existed only on `customers` and was not present on a `bookings` row is unrecoverable. This is the reason Phase 3 requires explicit approval and is a separate deployment from Phase 2.

---

## Edge Cases to Test

### E1 — address or postal_code is NULL at booking time (DECIDED)

**Decision (2026-04-20):** The agent must prompt the user for address before calling `write_booking()`. Address collection is an agent-level responsibility, not a tool-level primary guard. If the agent cannot collect a valid address after prompting, it must escalate to human rather than call `write_booking()` with a missing address. `write_booking()` is never called without a valid address in the normal flow.

**Phase 2 implementation implication:** `write_booking()` shall add a hard validation guard as a defensive backstop: if `address` is `None` or empty string, the tool raises a clear error immediately and does not proceed to the calendar write or Supabase INSERT. This guard is not the primary gate — the agent prompt is — but it prevents silent NULL writes if the agent somehow bypasses collection.

**Required SDET tests:**
- (a) Happy path: agent collects address, calls `write_booking()` with valid address — booking succeeds.
- (b) Agent prompts: agent detects address is missing mid-flow and prompts the customer to provide it before proceeding.
- (c) Escalation path: agent cannot collect address after prompting — escalates to human, does NOT call `write_booking()`.
- (d) Tool-level guard: `write_booking()` called with `address=None` or empty string raises a clear validation error; no calendar event is created; no Supabase INSERT is attempted.

### E2 — Booking created before Phase 2 is deployed (transition window)

Between Phase 1 (columns added to `bookings`) and Phase 2 (code deployed), any new booking will have `address=NULL` and `postal_code=NULL` on the `bookings` row — because the code hasn't yet been updated to populate them. The `customers` table will continue to receive the address write as it does today.

**Required test:** Confirm Phase 1 DDL succeeds and the engine continues to function normally with the new nullable columns present. No code reads `bookings.address` in Phase 1 — the new columns are invisible to the running engine.

### E3 — Booking created after Phase 2 but before Phase 3 (address still on both tables)

Between Phase 2 and Phase 3, `bookings` will have address populated and `customers.address` and `customers.postal_code` will exist but stop receiving updates. Old bookings will have `customers.address` values from pre-Phase-2 writes; new bookings will have `bookings.address` populated.

Any reporting or admin query that reads `customers.address` directly will see stale data for customers who have booked after Phase 2. This is expected and acceptable during the Phase 2→3 window.

**Required test:** Confirm the Google Sheets sync (if active) either stops syncing `customers.address` or is clearly documented as stale for this window.

**Ordering constraint (DECIDED 2026-04-20):** Google Sheets sync deployment is blocked on Phase 3 completion. The Sheets sync must never mirror `customers.address` or `customers.postal_code` because those columns will be absent from the `customers` table by the time sync ships. When the Sheets sync is eventually built, the bookings tab must include `bookings.address` and `bookings.postal_code`; the customers tab must not include any address columns. This is a hard sequencing rule — Phase 3 is a prerequisite for Google Sheets sync.

### E4 — Repeat customer, multiple bookings, different addresses

After Phase 2, each booking carries its own address. The `customers` table has no address column (after Phase 3) or a stale one (between Phase 2 and Phase 3). A customer with bookings at two different addresses will have correct, independent address records on their respective booking rows.

**Required test:** Create two bookings for the same phone number with different addresses. Confirm each `bookings` row contains the correct address for that booking. Confirm no cross-contamination.

### E5 — Agent context: what if address is missing from the conversation?

The agent collects address during the booking flow. If the agent calls `write_booking()` without having collected address (either because the customer refused or because of a prompt failure), the tool will receive an empty string or None.

**Architecture rule:** The tool signature retains `address: str` and `postal_code: str` as required parameters. If the agent passes empty strings, the tool writes empty strings to `bookings`. If it passes None (type violation), the tool should handle gracefully by coercing to None (nullable column). No booking should fail solely because address is empty — the booking is more valuable than the address.

**Required test:** Verify the Anthropic tool definition in `core/tools/definitions.py` lists `address` and `postal_code` in the `required` array (they are required inputs from the agent). Confirm the system prompt booking collection rules still explicitly require both fields before tool invocation. This is a prompt-level guard, not a code-level hard stop.

### E6 — get_customer_bookings() — does it need to return address?

Currently `get_customer_bookings()` selects: `booking_id, service_type, slot_date, slot_window, booking_status`. It does not return address.

After Phase 2, `bookings` has address columns populated. If a future use case requires the agent to confirm a customer's previous service address, the SELECT in `get_customer_bookings()` can be extended to include `address` and `postal_code`. No schema change is needed — the columns will exist on `bookings` after Phase 1.

**This is not a Phase 2 requirement.** No change to `get_customer_bookings()` is required for this migration. Flag it as a future enhancement.

---

## Founder Decisions — Resolved (2026-04-20)

**Q1 — Should an empty address block the booking? DECIDED.**
Address collection is an agent-level responsibility. The agent must prompt the customer for address before calling `write_booking()`. If address cannot be collected, escalate to human — do not call `write_booking()`. As a defensive backstop, `write_booking()` shall validate that `address` is non-None and non-empty and raise a clear error if violated. Full test requirements documented in E1 above.

**Q2 — Google Sheets sync behaviour during Phase 2→3 window. DECIDED.**
Google Sheets sync deployment is blocked on Phase 3 completion. The sync must never mirror `customers.address` or `customers.postal_code`. When sync is built, the bookings tab includes `bookings.address` and `bookings.postal_code`; the customers tab includes no address columns. Full ordering constraint documented in E3 above.

**Q3 — Backfill: should historical bookings get address populated? DECIDED.**
Yes. A one-time SQL backfill (Phase 2.5) runs after Phase 2 is verified and before Phase 3 DDL. Backfill copies `customers.address` and `customers.postal_code` to all `bookings` rows for that `phone_number` where `bookings.address IS NULL`. Full backfill SQL and pre-conditions documented in Phase 2.5 above.

**Q4 — mvp_scope.md DDL update. DECIDED.**
`clients/hey-aircon/plans/mvp_scope.md` Section 6 has been updated to reflect the post-Phase-3 target schema: `bookings` table includes `address TEXT` and `postal_code TEXT`; `customers` table does not. A note in that file marks that `customers` currently still carries these columns pending Phase 3 cleanup.
