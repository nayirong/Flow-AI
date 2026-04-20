# Feature: Service Variations — Agent Clarification Flow

**Owner:** @product-manager
**Status:** Approved — Ready for Handoff to Software Architect
**Created:** 2026-04-19
**Scope:** Python engine (context_builder.py) + Supabase config/policies tables

---

## Direction Check

- **Subject:** Customers asking about services that have multiple pricing tiers based on a unit specification they may not know
- **Problem:** The agent quotes a single price or fails to qualify the customer before quoting, leading to incorrect price expectations and bookings made on wrong assumptions
- **Confirmation:** This spec addresses the customer-facing clarification flow (correct subject) and prevents mis-quoted pricing before booking is confirmed (correct threat)

---

## 1. The Pattern — Service Variations in Supabase `config`

### Current state (HeyAircon)

| key | value |
|-----|-------|
| `pricing_general_servicing_standard` | General Servicing (standard, ≤15,000 BTU): $X |
| `pricing_general_servicing_18_24k` | General Servicing (large unit, 18,000–24,000 BTU): $Y |

These two rows are currently opaque to the agent — it sees two unrelated pricing facts.

### Proposed naming convention

A **variation group** is identified by a shared `__{parent}__` prefix segment in the config key. Keys follow this pattern:

```
pricing_{service_slug}__{variation_slug}
```

Two underscores (`__`) delimit the parent service slug from the variation slug. A config key containing `__` signals to the context builder that it belongs to a variation group.

| key | value |
|-----|-------|
| `pricing_general_servicing__standard` | General Servicing (standard, ≤15,000 BTU): $X |
| `pricing_general_servicing__18_24k` | General Servicing (large unit, 18,000–24,000 BTU): $Y |

A companion `variation_hint_` row provides the qualifier question the agent should ask:

| key | value |
|-----|-------|
| `variation_hint_general_servicing` | Is your aircon unit 18,000–24,000 BTU (large unit)? If you're unsure, we can assess on-site. |

### Why no new table

The existing `config` key-value pattern is sufficient. The double-underscore convention makes the relationship machine-readable without schema changes. The `context_builder.py` can detect variation groups at assembly time and inject structured instructions into the system prompt. A new table would require a migration and adds operational complexity for a pattern that only needs naming discipline.

### Generic pattern rules

1. Any `pricing_{X}__{Y}` key is a variation of parent service `X`.
2. Any `pricing_{X}__{Y}` key must have a corresponding `variation_hint_{X}` key. If missing, the context builder logs a warning and falls back to treating the rows as independent pricing facts (safe degradation).
3. A `service_{X}` row should exist for any service that has variation pricing. The service description row does not need the double-underscore — it describes the parent.
4. Variation rows must share the same `sort_order` block so they appear together in the assembled prompt.

---

## 2. Agent Behaviour Spec

### Trigger condition

The agent enters the **variation clarification flow** when a customer asks about a service's price or requests a booking for a service that has two or more `pricing_{X}__*` rows in config.

### Flow

```
Customer asks about General Servicing price or booking
        │
        ▼
Agent asks clarifying question (from variation_hint_{X})
"Is your aircon unit 18,000–24,000 BTU (large unit)?"
        │
    ┌───┴────────────────────────────────────┐
    │                                        │
Customer says YES              Customer says NO or "standard"
    │                                        │
Quote 18k–24k price            Quote standard price
Proceed to booking             Proceed to booking
    │
Customer says UNSURE / doesn't know
    │
Agent: "No problem — our technician will assess on-site.
The price will be between $[standard] and $[18k–24k].
Are you okay to proceed with the booking on that basis?"
    │
    ├── Customer says YES → proceed to booking
    │     write_booking note: "price pending BTU confirmation"
    └── Customer says NO  → do not book, offer to check with the team (escalate)
```

### Acceptance Criteria

- [ ] **AC-01:** When a customer asks for General Servicing price or booking and the config contains `pricing_general_servicing__standard` and `pricing_general_servicing__18_24k`, the agent MUST ask the BTU clarification question before quoting a price or proceeding to booking.
- [ ] **AC-02:** Agent must not skip the clarification question even if the customer says "I want to book" without specifying a variation.
- [ ] **AC-03:** If the customer confirms large unit (18k–24k), the agent quotes only the 18k–24k price and proceeds with that price in the booking.
- [ ] **AC-04:** If the customer confirms standard unit, the agent quotes only the standard price and proceeds with that price in the booking.
- [ ] **AC-05:** If the customer is unsure, the agent states the price range (standard to 18k–24k) and explicitly asks for confirmation before proceeding. The agent must not assume the customer is okay with the range without a yes.
- [ ] **AC-05a:** When an unsure customer accepts the range and the agent creates the booking via `write_booking`, the booking notes field must contain the string "price pending BTU confirmation". The upper price (18k–24k) must NOT be written as the confirmed price. No price value is committed in the record until the technician confirms on-site.
- [ ] **AC-06:** If the unsure customer declines the range, the agent does NOT create a booking. It offers to connect the customer with the team (escalate_to_human).
- [ ] **AC-07:** The clarification question text is read from `variation_hint_general_servicing` in config — it is not hardcoded in the agent prompt or code.
- [ ] **AC-08:** If `variation_hint_{X}` is missing for a variation group, the context builder logs a warning and the pricing rows are rendered as independent facts (no clarification flow is triggered). The agent does not crash.
- [ ] **AC-09:** The pattern works for any service slug, not only `general_servicing`. A new client with `pricing_deep_clean__studio` and `pricing_deep_clean__3br` triggers the same flow.

---

## 3. Config Schema Changes

### New fields required in `config` table (no schema change — same key/value/sort_order columns)

| key | value | sort_order | notes |
|-----|-------|-----------|-------|
| `variation_hint_{service_slug}` | The question text the agent asks to determine which variation applies | Adjacent to the variation pricing rows | New row type — not `service_` or `pricing_` prefix |

### context_builder.py changes required

The PRICING section assembly must be extended to:

1. Detect variation groups by scanning for `__` in `pricing_*` keys.
2. For each variation group, look up `variation_hint_{parent}` in config_dict.
3. Render variation groups as a structured block in the PRICING section:

```
PRICING:
...
- General Servicing: pricing varies by unit size.
  Variations:
    • Standard (≤15,000 BTU): $X
    • Large unit (18,000–24,000 BTU): $Y
  Clarification required: before quoting or booking, ask: "Is your aircon unit 18,000–24,000 BTU (large unit)? If you're unsure, we can assess on-site."
...
```

4. Non-variation `pricing_*` keys (no `__`) render as before: a flat bullet line.
5. If a variation group has no `variation_hint_` key, render the rows as flat bullets and emit a `logger.warning`.

The policies section is unchanged — behavioural rules for handling uncertainty continue to live in the `policies` table.

---

## 4. Immediate HeyAircon Action Items

These are the Supabase changes that must be made before the Python engine build for this feature begins.

### 4a. Rename existing pricing keys

| Current key | New key | Action |
|-------------|---------|--------|
| `pricing_general_servicing_9_12k` | `pricing_general_servicing__standard` | UPDATE (the `9_12k` label was informal; "standard" is the correct qualifier for the agent to communicate) |
| `pricing_general_servicing_18_24k` | `pricing_general_servicing__18_24k` | UPDATE (add double-underscore) |

**SQL:**
```sql
UPDATE config SET key = 'pricing_general_servicing__standard'
WHERE key = 'pricing_general_servicing_9_12k';

UPDATE config SET key = 'pricing_general_servicing__18_24k'
WHERE key = 'pricing_general_servicing_18_24k';
```

### 4b. Add variation hint row

```sql
INSERT INTO config (key, value, sort_order)
VALUES (
  'variation_hint_general_servicing',
  'Is your aircon unit 18,000–24,000 BTU (large unit)? Standard units are ≤15,000 BTU. If you''re not sure, no problem — our technician can assess on-site.',
  -- set sort_order to sit between the two pricing rows
  (SELECT sort_order FROM config WHERE key = 'pricing_general_servicing__standard') + 1
);
```

Adjust sort_order as needed so the hint row sits adjacent to the variation pricing rows in the assembled prompt.

### 4c. Add or update policies row — BTU variation behaviour

Add a new row to the `policies` table with the following text. This is the authoritative instruction the agent receives for handling the uncertainty path.

**Policy text (exact):**

```
SERVICE VARIATION — BTU ASSESSMENT POLICY:

When a customer is unsure which General Servicing tier applies to their unit, do NOT quote a single price. Instead:
1. Tell the customer the price range: "The price will be between $[standard price] and $[18k–24k price], depending on your unit — our technician will confirm on-site."
2. Ask: "Are you okay to proceed on that basis?"
3. Only proceed to booking if the customer explicitly says yes.
   When creating the booking via write_booking, set the notes field to "price pending BTU confirmation". Do NOT write either price as the confirmed booking price.
4. If the customer says no or wants a firm price first, use the escalate_to_human tool so the team can follow up directly.
Do not guess which tier applies. Do not commit to either price until the customer has confirmed the unit size or explicitly accepted the range.
```

**Suggested sort_order:** append after existing policies (high sort_order value).

### 4d. Verify service row exists

Confirm a `service_general_servicing` row exists in `config` describing the parent service. If it describes the service without reference to BTU tiers, leave it as-is — the variation rows and hint row carry the tier detail. If the value text references a single price, update it to remove the price (price detail lives in variation rows only).

### 4e. Add `variation_hint_` sentinel rows for all other services

No other HeyAircon services currently have variations. However, every service must have a `variation_hint_` row set to `"none"` so the context_builder can use a single consistent check: if the value is `"none"`, skip variation logic entirely. This keeps the pattern extensible — a future service with real variations simply replaces `"none"` with the hint question; no code changes required.

Insert one row per service that does NOT already have a `variation_hint_` row:

```sql
-- Chemical Wash
INSERT INTO config (key, value, sort_order)
VALUES ('variation_hint_chemical_wash', 'none',
        (SELECT sort_order FROM config WHERE key = 'pricing_chemical_wash') + 1);

-- Gas Top-Up
INSERT INTO config (key, value, sort_order)
VALUES ('variation_hint_gas_top_up', 'none',
        (SELECT sort_order FROM config WHERE key = 'pricing_gas_top_up') + 1);

-- Chemical Overhaul
INSERT INTO config (key, value, sort_order)
VALUES ('variation_hint_chemical_overhaul', 'none',
        (SELECT sort_order FROM config WHERE key = 'pricing_chemical_overhaul') + 1);

-- Inspection / Diagnostic
INSERT INTO config (key, value, sort_order)
VALUES ('variation_hint_inspection', 'none',
        (SELECT sort_order FROM config WHERE key = 'pricing_inspection') + 1);
```

**Note:** Replace the `WHERE key = 'pricing_{slug}'` references with the actual pricing keys present in the `config` table. The slugs above are illustrative — match them to whatever keys exist. If a service has no `pricing_` row yet, set `sort_order` manually to an appropriate value in the same sort block as that service's `service_` row.

**context_builder.py behaviour with sentinel:** When the context builder encounters `variation_hint_{X} = "none"`, it treats the service as having no variations and renders any `pricing_{X}` rows as flat bullet lines (same as today). The sentinel is invisible to the agent prompt — it is consumed and discarded during assembly.

---

## 5. User Stories

**US-01 — Standard unit customer**
As a customer with a standard aircon unit, I want the agent to quote me the correct standard price after I confirm my unit is standard, so that I am not given an incorrect price.

**US-02 — Large unit customer**
As a customer with a large unit (18k–24k BTU), I want the agent to recognise my unit type and quote the correct large-unit price, so that I am not surprised by a higher charge on the day.

**US-03 — Customer unsure of unit size**
As a customer who doesn't know their BTU rating, I want the agent to acknowledge the uncertainty, give me the price range, and only book if I agree to the range, so that I am never booked on a price I did not accept.

**US-04 — Future client with different variation type**
As a Flow AI operator onboarding a new client with service variations (e.g. cleaning by room count), I want to add `pricing_{X}__{Y}` rows and a `variation_hint_{X}` row in Supabase without any code changes, so that the variation clarification flow activates automatically for that client.

---

## 6. Out of Scope (this feature)

- Multi-level variations (a variation that itself has sub-variations) — not required for HeyAircon Phase 1
- Customer-facing UI for selecting variations — agent handles this conversationally
- Changing the `bookings` table schema to store the resolved variation — the booking price field already captures the agreed price; no schema change needed
- Automatic BTU lookup from any external source — customer self-reports or team assesses on-site

---

## Open Questions

| # | Question | Owner | Status | Resolution |
|---|----------|-------|--------|------------|
| OQ-01 | What are the exact dollar values for standard and 18k–24k pricing? | Founder / HeyAircon | **Resolved** | Dollar values already in Supabase are correct. No change to price values — only the key rename in section 4a applies. |
| OQ-02 | Should the booking record flag that the price is pending BTU confirmation, or is the price range sufficient? | Founder | **Resolved** | When the customer is unsure and accepts the price range, write_booking must set notes to `"price pending BTU confirmation"`. The upper price is NOT written as the confirmed price. See AC-05a and section 4c. |
| OQ-03 | Are there other HeyAircon services with variations? If yes, they follow the same pattern and need their own `variation_hint_` rows. | Founder | **Resolved** | No other services currently have variations. All remaining services receive a `variation_hint_` row set to `"none"` (sentinel) so the context_builder can skip variation logic consistently. See section 4e for INSERT statements. |
