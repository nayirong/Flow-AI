# Package Awareness for the WhatsApp Agent — Requirements Document

**Feature Owner:** `@product-manager`
**Date Created:** 2026-04-20
**Status:** PARKED — not in current scope. Revisit after initial Phase 1 delivery is complete.
**Priority:** Post-MVP (billable add-on)
**Phase:** Phase 1 add-on (parked)

---

> **PARKED NOTICE**
> This feature is fully scoped and decision-complete. No open questions remain. It is parked — not blocked — pending completion of Flow AI's initial Phase 1 delivery. When the team returns to this feature, no further discovery or clarification sessions are needed. Proceed directly to `@software-architect`.

---

## Direction Check

- **Subject:** Customers who have purchased service packages from an SME client (e.g., HeyAircon aircon servicing packages)
- **Problem:** The WhatsApp agent has zero awareness of package state — purchased services, remaining credits, or balance owed — and risks giving wrong or fabricated answers to package queries
- **Confirmation:** Solution gives the agent accurate, client-maintained package data to answer customer queries faithfully. It does not give the agent write access to client records, and it does not attempt to become the authoritative source of package truth

---

## Problem Statement

Clients sell service packages to customers — for example, a 3-session aircon servicing bundle. Customers ask the WhatsApp agent questions such as: "How many sessions do I have left?" or "How much do I still owe?" The agent currently has no data to answer these questions and will either guess (dangerous) or refuse.

The naive fix — maintaining a Supabase `packages` table as the primary record — fails because clients record package usage offline (pen, paper, spreadsheet, point-of-sale). Any Flow AI-owned record would be stale by default.

The correct fix is to sync client-maintained package data into the agent's read layer on a regular cadence, give the agent a tool to query it, and be honest with the customer about data freshness.

---

## Goals

- Allow the agent to answer package status queries (remaining sessions, balance owed) using client-maintained data
- Make the sync mechanism lightweight: client maintains one additional tab in the existing Google Sheets file, Flow AI syncs it to Supabase on a 15-minute cadence
- Log all package-related service usage the agent confirms (append-only, never write back to the client's Packages sheet)
- Be transparent with customers when data may be stale

## Non-Goals

- Flow AI will never be the authoritative source of package data in Phase 1. Client's Packages sheet is always the record of truth.
- The agent will not modify or delete records in the Packages sheet under any circumstance
- No UI for clients to manage packages inside Flow AI (that is Phase 2+)
- No payment processing or invoice generation (out of scope entirely)
- Historical backfill of package data is not supported at launch

---

## Phased Approach

### Phase 0 — Escalation Only (deliver in current Phase 1 scope, no new build)

No new code. Add escalation triggers to the agent's existing behavior:

- Any customer message containing package-related intent — credits, sessions remaining, balance owed, payment due — triggers the escalation tool immediately
- Agent sends a holding reply: "Let me check your package details with the team and get back to you."
- Human agent handles it

This is the correct behavior today because the agent has no package data. It costs zero build time.

**Trigger phrases to detect (non-exhaustive, handled by agent intent classification):**
- "how many sessions do I have left"
- "how much do I owe"
- "what's my package balance"
- "I bought a package"
- "when does my package expire"

---

### Phase 1 — Google Sheets Sync Bridge (this parked feature)

Client maintains a `Packages` tab in the existing per-client Google Sheets file. A sync job runs every 15 minutes: reads the `Packages` tab, writes to a `packages` shadow table in the client's Supabase. The agent gets a `get_package_status` tool that reads from Supabase.

When the agent confirms a package-related service (e.g., booking a session against a package), it appends a row to the `Package Usage Log` tab. The client reconciles manually: they review the Usage Log and update their Packages sheet accordingly.

**Sync cadence:** 15 minutes (scheduled job).
**Staleness caveat:** Agent always appends the last sync timestamp to its package status answer. If `last_synced_at` is older than 1 hour, the agent explicitly flags the data as potentially outdated.

---

### Phase 2 — Supabase as Primary Record (future)

Supabase `packages` table becomes the authoritative record. Client-facing interface (the Phase 2 CRM dashboard) replaces manual Sheets editing. Sync bridge is retired. The `get_package_status` tool requires no changes — it already reads from Supabase.

---

## Sheet Architecture

All tabs live within the single per-client Google Sheets file already established for the Google Sheets Data Sync feature. The `Packages` and `Package Usage Log` tabs are additive — they do not affect existing `Customers` and `Bookings` tabs.

| Tab | Who Writes | Who Reads | Protection |
|-----|-----------|-----------|------------|
| Customers | Flow AI only | Client views | Protected — Flow AI service account only |
| Bookings | Flow AI only | Client views | Protected — Flow AI service account only |
| Packages | Client only | Flow AI syncs to Supabase | Unprotected — client edits freely |
| Package Usage Log | Flow AI only (append-only) | Client views | Protected — Flow AI service account only |

**Key rule:** Flow AI never writes to the `Packages` tab. Client never writes to `Package Usage Log`.

---

## Schema Definitions

### Packages Tab (client-maintained, Flow AI-defined columns)

This is the schema the client must follow. Flow AI defines the column names and order. Client fills the rows.

| Column | Type | Notes |
|--------|------|-------|
| `phone_number` | Text | Customer's WhatsApp number. Primary lookup key. |
| `customer_name` | Text | Display name. |
| `package_name` | Text | e.g., "5-Session Aircon Servicing Bundle" |
| `total_sessions` | Integer | Total sessions purchased. |
| `used_sessions` | Integer | Sessions consumed to date. Client updates this. |
| `amount_paid` | Decimal | SGD paid to date. |
| `amount_owed` | Decimal | SGD balance outstanding. |
| `last_updated` | Date | Date client last updated this row. Informs staleness context. |

**Lookup key:** `phone_number` + `client_id`. A customer may have at most one active package row per client. Multiple packages per customer are not supported in Phase 1.

---

### Packages Shadow Table (Supabase — Flow AI-maintained)

Mirrors the Packages tab. Written by the sync job, read by the `get_package_status` tool. Never written by the agent directly.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Auto-generated primary key. |
| `client_id` | Text | Foreign key to `clients` table. |
| `phone_number` | Text | Lookup key. |
| `customer_name` | Text | |
| `package_name` | Text | |
| `total_sessions` | Integer | |
| `used_sessions` | Integer | |
| `sessions_remaining` | Integer | Computed on sync: `total_sessions - used_sessions`. |
| `amount_paid` | Decimal | |
| `amount_owed` | Decimal | |
| `client_last_updated` | Date | Copied from `last_updated` column in Packages sheet. |
| `last_synced_at` | Timestamp | Set by the sync job on every write. |

---

### Package Usage Log Tab (Flow AI-appended)

The agent appends one row each time it confirms a service booking that consumes a package session. Append-only. Never modified or deleted by the engine.

| Column | Type | Notes |
|--------|------|-------|
| `timestamp` | Timestamp | UTC. When the agent logged the usage. |
| `customer_phone` | Text | Customer's WhatsApp number. |
| `customer_name` | Text | |
| `service_used` | Text | e.g., "Aircon Chemical Wash — 1 unit" |
| `sessions_deducted` | Integer | Always 1 in Phase 1. |
| `booking_id` | UUID | Supabase `bookings.id` for cross-reference. |
| `recorded_by` | Text | Always `"flowai"`. Never changes. |

---

## Agent Behavior Specification

### `get_package_status` Tool

**Location:** `engine/core/tools/` — this is a core tool (universally useful across clients), not a bespoke client tool.

**Reads from:** `packages` shadow table in Supabase (per-client).

**Input:** `phone_number` (string), `client_id` (string — injected by the engine, not inferred from conversation).

**Output (to agent):** Package name, sessions remaining, amount owed, `last_synced_at`, `client_last_updated`.

**Staleness rule:**
- If `last_synced_at` is within the last 1 hour: answer normally, append a brief note: "This is based on data last synced at [time]."
- If `last_synced_at` is older than 1 hour: answer with explicit caveat: "This information was last synced [X hours] ago and may not reflect recent changes. Please confirm with [client name] directly if you need the exact figure."

**No package found:** If no row exists for the customer's phone number, agent responds: "I don't have a package on record for your number. If you've purchased a package, please contact us directly to confirm the details."

**Agent never:**
- Calculates sessions remaining independently (uses the `sessions_remaining` column from Supabase, which is computed at sync time)
- Guesses or estimates a balance
- Tells the customer the data is definitely current — the caveat is always present

---

### Phase 0 Escalation Triggers (no new build)

Before Phase 1 is built, the agent must escalate any package-related query rather than attempt to answer. These triggers must be woven into the agent's existing system prompt or intent classification.

**Escalate when customer intent matches any of:**
- Remaining sessions / credits on a package
- Balance or payment owed for a package
- Whether a package is active or expired
- What services are included in their package

**Escalation behavior:** Use the existing `escalate` tool. The agent sends the holding message and stops processing — it does not attempt a partial answer.

---

### Package Usage Logging (agent-initiated, Phase 1)

When the agent confirms a booking that a customer explicitly states is against their package (e.g., "I want to use one of my package sessions"), the agent calls a `log_package_usage` tool after the booking is confirmed.

**`log_package_usage` tool behavior:**
- Appends one row to the `Package Usage Log` tab in Google Sheets
- Does NOT modify the `Packages` tab
- Does NOT modify the `packages` Supabase table
- If the Google Sheets write fails: log the error, do not fail the booking, do not retry
- Fires as a background task (same fire-and-forget pattern as the Sheets sync)

The client's responsibility is to check the Usage Log periodically and update their Packages sheet to reflect consumed sessions. Flow AI does not force this reconciliation.

---

## Architecture Constraints

| Constraint | Detail |
|-----------|--------|
| Tool location | `get_package_status` and `log_package_usage` live in `engine/core/tools/` — never in `clients/` |
| Client isolation | Tool inputs include `client_id`; reads scoped to that client's rows in the shared `packages` table |
| Default-on | `packages` table exists for all clients by default. Empty table = client does not use packages. No conditional logic in the engine based on "is packages enabled". |
| Sync job | 15-minute scheduled cadence. Reads `Packages` tab → full replace of matching `client_id` rows in `packages` shadow table (not incremental). |
| No engine writes to Packages sheet | Absolute hard rule. Only the client writes to `Packages`. Engine only appends to `Package Usage Log`. |
| Caveat is always present | Every `get_package_status` response includes last sync time, regardless of staleness. Staleness threshold (1 hour) determines language severity, not whether the caveat appears. |
| Phase 2 compatibility | `get_package_status` reads from Supabase only. In Phase 2, when Supabase becomes the primary record, the tool requires no changes. |

---

## Open Questions

None. All decisions have been made. Proceed to `@software-architect` when this feature is un-parked.

---

## Billing Note

Package Awareness is a billable add-on. It is not included in the standard Flow AI Phase 1 scope. Clients must opt in and will be billed separately. Pricing is not defined here — that is a `@business-strategist` concern. The engineering team should not build this as part of any base client contract.

---

## Sign-off

**Product Manager:** Complete — all decisions made, no open questions. Document is ready for architecture phase when un-parked.

**Founder Approval:** [ ] Approved — un-park and route to `@software-architect`

**Next Steps When Un-parked:**
1. Route to `@software-architect`:
   - Design `packages` Supabase table schema (migration)
   - Design 15-minute sync job (scheduler mechanism, TBD — cron, Railway cron, or in-process APScheduler)
   - Design `get_package_status` and `log_package_usage` tool signatures and error handling
   - Confirm how `Package Usage Log` writes interact with the existing `google_sheets.py` integration
2. Route to `@sdet-engineer` to create test plan and dispatch implementation
