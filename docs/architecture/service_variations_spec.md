# Architecture Spec: Service Variations — Agent Clarification Flow

**Status:** Ready for SDET
**Requirements source:** `docs/requirements/service_variations.md`
**Scope:** `engine/core/context_builder.py` (PRICING section only) + Supabase `config` and `policies` tables
**Date:** 2026-04-19

---

## 1. Summary of Change

The PRICING section of the assembled system prompt currently renders every `pricing_*` config row as an independent flat bullet. This spec introduces a **variation group** rendering path: when two or more `pricing_*` keys share a parent service slug (identified by a double-underscore `__` delimiter), the context builder groups them and injects a structured block including a clarification question. All other rendering is unchanged.

No new tables. No new environment variables. No changes to any function signature.

---

## 2. Naming Convention (Data Layer)

### 2.1 Variation key pattern

A config key is a **variation key** if and only if it matches:

```
pricing_{service_slug}__{variation_slug}
```

The double-underscore (`__`) is the machine-readable delimiter. Everything before `__` (after the `pricing_` prefix) is the **parent service slug**. Everything after `__` is the **variation slug**.

Single-underscore keys (e.g. `pricing_chemical_wash`) are **flat pricing keys** and are not variation keys.

### 2.2 Variation hint key pattern

Each parent service slug that has at least one variation key must have a corresponding:

```
variation_hint_{service_slug}
```

row in the `config` table. The value is either:

- A non-empty string that is not `"none"` → the clarification question the agent must ask (active hint)
- The literal string `"none"` → sentinel; the service has no current variations (skip variation logic)

### 2.3 Canonical key names for HeyAircon (post-migration)

| Canonical config key | Value description |
|---|---|
| `pricing_general_servicing__standard` | Standard pricing line (renamed from `pricing_general_servicing_9_12k`) |
| `pricing_general_servicing__18_24k` | Large-unit pricing line (renamed from `pricing_general_servicing_18_24k`) |
| `variation_hint_general_servicing` | Active BTU clarification question |
| `variation_hint_chemical_wash` | Sentinel: `"none"` |
| `variation_hint_gas_top_up` | Sentinel: `"none"` |
| `variation_hint_chemical_overhaul` | Sentinel: `"none"` |
| `variation_hint_inspection` | Sentinel: `"none"` |

---

## 3. Function Signature

`build_system_message` signature is **unchanged**:

```
async def build_system_message(db: Any) -> str
```

No new parameters. No new return type. The change is entirely within the PRICING section assembly block (lines 103–109 of current `context_builder.py`).

---

## 4. PRICING Section Assembly Logic

This section replaces the current Section 3 assembly (lines 103–109 of `context_builder.py`). All other sections are unchanged.

### 4.1 Inputs available at assembly time

- `config_rows`: ordered list of `{key, value}` dicts (fetched once, already in scope)
- `config_dict`: key → value dict (already in scope)

### 4.2 Step-by-step logic (pseudocode, language-agnostic)

```
STEP 1 — Partition pricing rows

For each row in config_rows where row.key starts with "pricing_":
    If row.key contains "__":
        Extract parent_slug = substring between "pricing_" and "__"
        Extract variation_slug = substring after "__"
        Append (parent_slug, variation_slug, row.value) to variation_rows list
    Else:
        Append row to flat_rows list

STEP 2 — Group variation rows by parent_slug

Build variation_groups dict: parent_slug → list of (variation_slug, value) tuples
(Preserve insertion order — sort_order from the DB query determines order within each group)

STEP 3 — Build PRICING output lines

pricing_lines = []

For each row in config_rows where row.key starts with "pricing_":

    If row.key contains "__":
        parent_slug = extract parent slug from row.key

        If parent_slug has already been rendered (track a seen_parents set):
            SKIP — already emitted this group's block
            CONTINUE

        Mark parent_slug as seen

        hint_key = "variation_hint_" + parent_slug
        hint_value = config_dict.get(hint_key)

        If hint_value is None:
            # Missing hint row — degrade gracefully
            EMIT logger.warning:
                "variation_hint_{parent_slug} missing from config; rendering variation rows as flat bullets"
            For each (variation_slug, value) in variation_groups[parent_slug]:
                Append "- {value}" to pricing_lines
            CONTINUE

        If hint_value == "none":
            # Sentinel — treat as flat (should not normally occur for a key with __)
            # This is a safety fallback; sentinel is only expected on flat keys
            For each (variation_slug, value) in variation_groups[parent_slug]:
                Append "- {value}" to pricing_lines
            CONTINUE

        # Active hint — render structured variation block
        group_values = variation_groups[parent_slug]
        variation_bullets = "\n".join(
            f"    • {value}" for (_, value) in group_values
        )
        block = (
            f"- {parent_slug_display_name(parent_slug)}: pricing varies by unit size.\n"
            f"  Variations:\n"
            f"{variation_bullets}\n"
            f"  Clarification required: before quoting or booking, ask: \"{hint_value}\""
        )
        Append block to pricing_lines

    Else:
        # Flat pricing key — check sentinel
        service_slug = extract slug from row.key (strip "pricing_" prefix)
        hint_key = "variation_hint_" + service_slug
        hint_value = config_dict.get(hint_key)

        If hint_value is None or hint_value == "none":
            Append "- {row.value}" to pricing_lines
            CONTINUE

        # hint_value is non-"none" and non-None for a flat key
        # This is anomalous (single flat key with active hint — not a valid variation group)
        # Degrade: render as flat bullet, emit warning
        EMIT logger.warning:
            "variation_hint_{service_slug} has active value but pricing_{service_slug} has no variation keys (no __); rendering as flat bullet"
        Append "- {row.value}" to pricing_lines

STEP 4 — Assemble section

pricing_section = "\nPRICING:\n" + "\n".join(pricing_lines) + "\n"
```

### 4.3 `parent_slug_display_name` helper

This is a pure string transformation — no lookup required:

```
Replace each "_" in parent_slug with a space, then title-case each word.

Examples:
  "general_servicing"  → "General Servicing"
  "deep_clean"         → "Deep Clean"
  "gas_top_up"         → "Gas Top Up"
```

This helper is used only within the variation block header line. It does not affect flat bullet rendering.

### 4.4 seen_parents tracking

A local set `seen_parents` is initialised empty before the pricing loop and tracks which `parent_slug` values have already emitted a block. This prevents duplicate blocks when multiple variation keys share the same parent (which is the normal case — one block per parent, not one block per key).

---

## 5. Rendered Output Shapes

### 5.1 Variation service — `general_servicing` (active hint present)

Given config rows (in sort_order):
- `pricing_general_servicing__standard` → `"General Servicing (standard, ≤15,000 BTU): $X"`
- `pricing_general_servicing__18_24k` → `"General Servicing (large unit, 18,000–24,000 BTU): $Y"`
- `variation_hint_general_servicing` → `"Is your aircon unit 18,000–24,000 BTU (large unit)? Standard units are ≤15,000 BTU. If you're not sure, no problem — our technician can assess on-site."`

Expected rendered block within PRICING section:

```
- General Servicing: pricing varies by unit size.
  Variations:
    • General Servicing (standard, ≤15,000 BTU): $X
    • General Servicing (large unit, 18,000–24,000 BTU): $Y
  Clarification required: before quoting or booking, ask: "Is your aircon unit 18,000–24,000 BTU (large unit)? Standard units are ≤15,000 BTU. If you're not sure, no problem — our technician can assess on-site."
```

The second variation key (`pricing_general_servicing__18_24k`) is encountered later in the loop but `general_servicing` is already in `seen_parents` — it is skipped and does not produce a second block.

### 5.2 Non-variation service — `chemical_wash` (sentinel `"none"`)

Given config rows:
- `pricing_chemical_wash` → `"Chemical Wash: $Z"`
- `variation_hint_chemical_wash` → `"none"`

Expected rendered line:

```
- Chemical Wash: $Z
```

The sentinel is consumed silently. The agent prompt contains only the flat bullet. No clarification instruction is emitted.

### 5.3 Non-variation service — `gas_top_up` (no hint row at all)

Given config rows:
- `pricing_gas_top_up` → `"Gas Top-Up: $W"`
- (no `variation_hint_gas_top_up` row)

Expected rendered line:

```
- Gas Top-Up: $W
```

No warning is emitted for flat keys with no hint row. (Warning is only emitted for variation keys — those containing `__` — when their `variation_hint_` row is absent.)

### 5.4 Degraded output — missing hint for a variation group

Given config rows:
- `pricing_deep_clean__studio` → `"Deep Clean (studio): $A"`
- `pricing_deep_clean__3br` → `"Deep Clean (3-bedroom): $B"`
- (no `variation_hint_deep_clean` row)

Expected behaviour:
- `logger.warning` emitted: `"variation_hint_deep_clean missing from config; rendering variation rows as flat bullets"`
- Two flat bullets rendered:

```
- Deep Clean (studio): $A
- Deep Clean (3-bedroom): $B
```

No clarification instruction is injected. Agent receives the rows as independent facts. Agent does not crash.

---

## 6. Debug Log Line

The existing debug log at the end of `build_system_message` counts `pricing_lines`. After this change, `pricing_lines` contains both flat lines and multi-line variation blocks. The count will reflect the number of items in the list (one item per flat key, one item per variation group), not the number of raw config rows. This is acceptable — the log is for debugging only.

No change to the log format is required.

---

## 7. Supabase SQL — All Data Changes

These statements must be executed against the HeyAircon client Supabase instance (not the shared Flow AI Supabase). Execute them in the order listed.

### 7.1 Rename existing pricing keys (section 4a of requirements)

```sql
UPDATE config
SET key = 'pricing_general_servicing__standard'
WHERE key = 'pricing_general_servicing_9_12k';

UPDATE config
SET key = 'pricing_general_servicing__18_24k'
WHERE key = 'pricing_general_servicing_18_24k';
```

Precondition: exactly one row must match each `WHERE` clause. Verify row count = 1 before committing. If either key does not exist, investigate before running.

### 7.2 Insert variation hint row for general_servicing (section 4b of requirements)

```sql
INSERT INTO config (key, value, sort_order)
VALUES (
    'variation_hint_general_servicing',
    'Is your aircon unit 18,000–24,000 BTU (large unit)? Standard units are ≤15,000 BTU. If you''re not sure, no problem — our technician can assess on-site.',
    (SELECT sort_order FROM config WHERE key = 'pricing_general_servicing__standard') + 1
);
```

Note: this sort_order places the hint row immediately after the standard pricing row. The `__18_24k` row must have a sort_order that is already higher than the `__standard` row. Confirm both variation rows are adjacent in sort_order before inserting.

### 7.3 Insert sentinel rows for all non-variation services (section 4e of requirements)

Replace each `pricing_{slug}` reference with the actual key present in the `config` table. These keys are illustrative — verify against live data before running.

```sql
-- Chemical Wash
INSERT INTO config (key, value, sort_order)
VALUES (
    'variation_hint_chemical_wash',
    'none',
    (SELECT sort_order FROM config WHERE key = 'pricing_chemical_wash') + 1
);

-- Gas Top-Up
INSERT INTO config (key, value, sort_order)
VALUES (
    'variation_hint_gas_top_up',
    'none',
    (SELECT sort_order FROM config WHERE key = 'pricing_gas_top_up') + 1
);

-- Chemical Overhaul
INSERT INTO config (key, value, sort_order)
VALUES (
    'variation_hint_chemical_overhaul',
    'none',
    (SELECT sort_order FROM config WHERE key = 'pricing_chemical_overhaul') + 1
);

-- Inspection / Diagnostic
INSERT INTO config (key, value, sort_order)
VALUES (
    'variation_hint_inspection',
    'none',
    (SELECT sort_order FROM config WHERE key = 'pricing_inspection') + 1
);
```

If a `pricing_{slug}` key does not exist yet for a given service, set `sort_order` to an appropriate value adjacent to that service's `service_` row rather than deriving from a non-existent key.

### 7.4 Insert BTU variation behaviour policy row (section 4c of requirements)

This is inserted into the `policies` table (not `config`). Set `sort_order` to a value higher than all existing policy rows.

```sql
INSERT INTO policies (policy_text, sort_order)
VALUES (
    'SERVICE VARIATION — BTU ASSESSMENT POLICY:

When a customer is unsure which General Servicing tier applies to their unit, do NOT quote a single price. Instead:
1. Tell the customer the price range: "The price will be between $[standard price] and $[18k–24k price], depending on your unit — our technician will confirm on-site."
2. Ask: "Are you okay to proceed on that basis?"
3. Only proceed to booking if the customer explicitly says yes.
   When creating the booking via write_booking, set the notes field to "price pending BTU confirmation". Do NOT write either price as the confirmed booking price.
4. If the customer says no or wants a firm price first, use the escalate_to_human tool so the team can follow up directly.
Do not guess which tier applies. Do not commit to either price until the customer has confirmed the unit size or explicitly accepted the range.',
    (SELECT COALESCE(MAX(sort_order), 0) + 10 FROM policies)
);
```

### 7.5 Verify service row (section 4d of requirements)

No SQL is prescribed here. A human must manually inspect the `service_general_servicing` row in `config`. If its `value` text references a single price, the price text must be removed from that row (price detail lives in variation rows only). If it describes the service without referencing a price, no change is needed.

---

## 8. Constraints and Invariants

1. **Key uniqueness:** The `config` table must not contain both `pricing_general_servicing_9_12k` and `pricing_general_servicing__standard` simultaneously. The rename in section 7.1 must succeed before any engine code for this feature is deployed.

2. **Hint row must not be a `pricing_` key:** `variation_hint_*` rows do not start with `pricing_` and are therefore never included in the PRICING section scan. No filtering is needed to exclude them — the key prefix is the natural filter.

3. **`variation_hint_*` rows are not rendered in the PRICING section:** They are consumed from `config_dict` only. They never appear as bullet lines in the assembled prompt.

4. **Order preservation:** The output order of variation groups within the PRICING section follows the sort_order of their first-encountered variation key in the config_rows list. This is consistent with the existing flat pricing row ordering.

5. **Idempotency of sentinel:** A `variation_hint_{X} = "none"` row for a service that later acquires variation keys is not sufficient to activate the variation block. The variation block activates only when hint_value is a non-empty, non-`"none"` string. Updating the sentinel to a real question string is the only config change needed to activate the flow for a new service — no code change required.

6. **No cross-client contamination:** `build_system_message` receives a per-client `db` handle. All config reads are scoped to the calling client's database. The variation logic is client-agnostic by construction.

---

## 9. Acceptance Criteria Cross-Reference

| Requirements AC | What the spec covers | Test surface |
|---|---|---|
| AC-01: Agent asks BTU question before quoting/booking when both variation keys exist | Section 5.1 shows the "Clarification required" line in the assembled prompt; policy row (section 7.4) enforces the behavioural rule | Prompt assembly test: verify "Clarification required" line present when both `__standard` and `__18_24k` keys exist |
| AC-02: Agent must not skip clarification even on direct booking request | Covered by policy row text (section 7.4) — policy is injected into every system message | Policy injection test: verify BTU policy row appears in assembled system message |
| AC-03: Large unit confirmation → 18k–24k price only | Covered by policy row instruction ("Do not commit to either price until confirmed") + variation block showing both prices | Eval test / conversation-level |
| AC-04: Standard unit confirmation → standard price only | Same as AC-03 | Eval test / conversation-level |
| AC-05: Unsure customer → price range + explicit yes required | Policy row text in section 7.4 prescribes exact agent behaviour | Eval test / conversation-level |
| AC-05a: write_booking notes = "price pending BTU confirmation" when customer unsure and accepts | Policy row text prescribes this exact string | Eval test + write_booking tool call inspection |
| AC-06: Unsure customer declines → no booking, escalate_to_human | Policy row text step 4 in section 7.4 | Eval test |
| AC-07: Clarification question text from config, not hardcoded | Section 4.2 step 3: hint_value is read from config_dict at runtime | Unit test: supply custom hint value, assert it appears verbatim in rendered block |
| AC-08: Missing variation_hint_* → warning + flat bullets, no crash | Section 4.2 step 3, degraded path; section 5.4 shows expected output | Unit test: omit hint row, assert warning emitted and flat bullets rendered |
| AC-09: Pattern works for any service slug, not only general_servicing | Logic in section 4.2 is entirely slug-agnostic | Unit test: use `pricing_deep_clean__studio` / `__3br` with `variation_hint_deep_clean`, assert structured block rendered |

---

## 10. Out of Scope (this spec)

The following are explicitly excluded per requirements section 6:

- Multi-level variations (a variation that itself has sub-variations)
- Changes to the `bookings` table schema
- Changes to `write_booking` tool definition or signature — the existing `notes` field receives the string; no tool change is needed
- Any change to `fetch_conversation_history`
- Any change to `settings.py` or env vars
- Any change to the SERVICES, APPOINTMENT WINDOWS, or POLICIES assembly logic beyond inserting the new policy row into the `policies` table

---

## 11. Open Questions

None. All open questions from the requirements doc are resolved. See `docs/requirements/service_variations.md` section "Open Questions" for resolution notes.
