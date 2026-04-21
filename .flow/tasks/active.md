# Active Tasks

> Managed by: Flow AI Orchestrator
> All task specs written here by PM Agent. Moved to `done.md` on completion, `blocked.md` on block.
> Format: one H2 block per task, in order of creation.

---

<!-- Paste new task specs below this line. Most recent at the top. -->

## BUG (Critical): Guardrail Re-Prompt Message Leaking to Customer as Outbound WhatsApp Message

**Type:** Bug — Critical
**Status:** Open
**Logged:** 2026-04-21
**Client:** HeyAircon
**Interaction Log Reference:** ID 269

**Observed Behavior:**
The guardrail re-prompt logic in `agent_runner.py` — which fires when `write_booking` has not been called yet — produced a message starting with:
> "I appreciate you pointing that out, but I need to clarify: I haven't yet collected all the required details from the customer to make the booking..."

This message was delivered to the customer's WhatsApp as an outbound reply. It is the agent reasoning to itself about what it still needs to collect. It must never reach the customer.

**Sequence:**
1. Customer said "okay, then 24th April evening is fine."
2. Agent responded with internal reasoning about needing more info (delivered as outbound message — the bug).
3. On next message, customer provided name/address and booking proceeded correctly.

**Root Cause (suspected):**
The guardrail detects that `write_booking` has not been called and injects a re-prompt. That re-prompt is being handled as an outbound reply rather than as an internal correction (a new user turn or system message injected into the agent loop). The re-prompt must never exit the agent runner as a message to be sent.

**Files to Investigate:**
- `engine/core/agent_runner.py` — guardrail detection logic and re-prompt injection point. The re-prompt must be re-injected as a new user-side message into the conversation loop, not returned as an assistant reply.

**Fix Criteria:**
- Re-prompt is injected as an internal loop correction (user turn or system injection), not as the agent's outbound reply.
- Customer-facing message flow is unaffected — customer never sees internal agent reasoning.
- Existing guardrail behavior (blocking confirmation language when `write_booking` has not succeeded) is preserved.

**Next Step:**
Route to `@sdet-engineer` for investigation and implementation dispatch.

---

## BUG (Medium): booking_count Not Incremented on First Booking

**Type:** Bug — Medium
**Status:** Open
**Logged:** 2026-04-21
**Client:** HeyAircon

**Observed Behavior:**
After the first successful booking was written (booking ID: HA-20260424-87RU, 24 April, 7 units General Servicing), the customer's `booking_count` in the `customers` table remained 0. It only incremented to 1 after the second booking (HA-20260426-RF02, 26 April).

**Root Cause (suspected):**
The `write_booking` tool PATCHes the customer record to increment `booking_count`. On the first booking, the customer record was just created earlier in the same message handling cycle (also via PATCH from `message_handler.py` to set `last_seen_at`). The `message_handler` PATCH may be executing after `write_booking` and overwriting the incremented counter — either due to ordering or because the PATCH payload includes `booking_count: 0` implicitly.

**Files to Investigate:**
- `engine/core/tools/write_booking.py` — where `booking_count` increment PATCH is issued. Confirm field is being sent correctly and not overwritten.
- `engine/core/message_handler.py` — where `last_seen_at` PATCH fires. Confirm the PATCH payload does not include `booking_count` or any field that would reset it. Check execution order relative to `write_booking`.

**Fix Criteria:**
- `booking_count` increments to 1 immediately after the first booking is written.
- The `message_handler` PATCH and the `write_booking` PATCH do not interfere with each other.
- Verified on a fresh customer record (0 → 1 on first booking).

**Next Step:**
Route to `@sdet-engineer` for investigation and implementation dispatch.

## Pending Confirmation Booking Status + Auto-Follow-Up

**Type:** New Feature
**Status:** Blocked — Awaiting PM Requirements
**Logged:** 2026-04-20
**Client:** HeyAircon (platform-level capability, client-agnostic)

**Description:**
When the AI agent has gathered all required booking information from a customer but has not yet received final confirmation, the booking should be created with status `Pending Confirmation`. Only when the customer replies to confirm does the status change to `Confirmed`.

Additionally: an auto-follow-up message should be sent to customers whose bookings remain in `Pending Confirmation` status after a configurable time window (e.g., 24 hours).

**Current State:**
- Booking records are only created on explicit customer confirmation (status = `Confirmed`).
- No partial/pending booking state exists.

**Requirements:**
- New `booking_status` value: `Pending Confirmation`
- Full status enum agreed: `Confirmed`, `Pending Confirmation`, `Cancelled`, `Rescheduled`, `Completed`, `No-Show`
- Agent tool or flow change to create pending bookings
- Conversation state tracking (to know we've already gathered all required info)
- Scheduled/cron-style follow-up mechanism (new infrastructure)
- New agent message template for follow-up

**Dependencies:**
- Postgres trigger for `total_bookings` increment (migration 002, deployed) should only fire for `Confirmed` status inserts — not `Pending Confirmation`.

**Next Step:**
`@product-manager` must produce requirements document in `docs/requirements/`.

**Blocked On:**
PM requirements — no architecture, test plan, or implementation can proceed until requirements exist.
