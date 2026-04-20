# Test Plan: Service Variations — Agent Clarification Flow

**Feature:** Service Variations — Agent Clarification Flow
**Status:** Ready for Implementation
**SDET Owner:** @sdet-engineer
**Spec source:** `docs/architecture/service_variations_spec.md`
**Requirements source:** `docs/requirements/service_variations.md`
**File under test:** `engine/core/context_builder.py` (PRICING section only)
**Test file:** `engine/tests/unit/test_context_builder.py`
**Date:** 2026-04-19

---

## 1. Scope

This test plan covers unit-level verification of the PRICING section assembly logic in `build_system_message`. The Supabase SQL changes (spec section 7) are executed manually by the founder — they are not part of this test plan.

All tests are pure unit tests: no real database, no real API calls. The mock DB helper `_make_db` from the existing test file is extended per test case.

---

## 2. Out of Scope

The following are explicitly excluded from this test plan:

- Agent conversation-level behaviour (AC-03, AC-04, AC-05, AC-05a, AC-06) — these require eval tests against a live model; they are deferred to the eval pipeline.
- `write_booking` tool call inspection.
- `fetch_conversation_history` — no changes to that function.
- SERVICES, APPOINTMENT WINDOWS, POLICIES section assembly — no changes to those sections.
- SQL migration correctness — executed manually in Supabase Studio.

---

## 3. Test Cases

### TC-01 — Variation group detected and rendered as structured block (AC-01, AC-07, AC-09)

**Setup:**
- Config rows include:
  - `pricing_general_servicing__standard` → `"General Servicing (standard, ≤15,000 BTU): $80"`
  - `pricing_general_servicing__18_24k` → `"General Servicing (large unit, 18,000–24,000 BTU): $100"`
  - `variation_hint_general_servicing` → `"Is your aircon unit 18,000–24,000 BTU (large unit)?"`

**Expected output (within the assembled system message PRICING section):**

```
- General Servicing: pricing varies by unit size.
  Variations:
    • General Servicing (standard, ≤15,000 BTU): $80
    • General Servicing (large unit, 18,000–24,000 BTU): $100
  Clarification required: before quoting or booking, ask: "Is your aircon unit 18,000–24,000 BTU (large unit)?"
```

**Assertions:**
1. `"General Servicing: pricing varies by unit size."` is present in `msg`.
2. `"• General Servicing (standard, ≤15,000 BTU): $80"` is present in `msg`.
3. `"• General Servicing (large unit, 18,000–24,000 BTU): $100"` is present in `msg`.
4. `'Clarification required: before quoting or booking, ask: "Is your aircon unit 18,000–24,000 BTU (large unit)?"'` is present in `msg`.
5. `"- General Servicing (standard, ≤15,000 BTU): $80"` (flat bullet form) is NOT present in `msg` — the value appears only inside the variation block, not as a standalone flat line.
6. The variation block appears exactly once (no duplicate block for the `__18_24k` key).

**AC cross-ref:** AC-01 (clarification line present), AC-07 (hint text from config verbatim), AC-09 (slug-agnostic logic — proven by using `general_servicing` slug with `__` keys)

---

### TC-02 — Hint text appears verbatim from config (AC-07)

**Setup:**
- Config rows include:
  - `pricing_deep_clean__studio` → `"Deep Clean (studio): $150"`
  - `pricing_deep_clean__3br` → `"Deep Clean (3-bedroom): $220"`
  - `variation_hint_deep_clean` → `"How many bedrooms does your unit have?"`

**Assertions:**
1. `'Clarification required: before quoting or booking, ask: "How many bedrooms does your unit have?"'` appears verbatim in `msg`.
2. `"Deep Clean: pricing varies by unit size."` appears in `msg`.
3. No variation block appears for `general_servicing` (no such rows in this test's config).

**AC cross-ref:** AC-07 (hint is read from config, not hardcoded), AC-09 (different slug `deep_clean` triggers the same structured rendering path)

---

### TC-03 — Second variation key in same group is skipped (no duplicate block)

**Setup:** Same as TC-01 (two `pricing_general_servicing__*` keys).

**Assertions:**
1. The string `"General Servicing: pricing varies by unit size."` appears exactly once in `msg` (use `msg.count(...)` assertion).
2. The clarification question appears exactly once.

**AC cross-ref:** Spec section 4.4 (seen_parents deduplication)

---

### TC-04 — Sentinel `"none"` hint silently suppressed; flat bullet rendered (spec section 5.2)

**Setup:**
- Config rows include:
  - `pricing_chemical_wash` → `"Chemical Wash: $120"`
  - `variation_hint_chemical_wash` → `"none"`

**Assertions:**
1. `"- Chemical Wash: $120"` appears in `msg`.
2. `"none"` does NOT appear anywhere in `msg`.
3. No `"Clarification required"` text is present in `msg` (no hint injected for this service).
4. No `"varies by unit size"` text for chemical_wash.

**AC cross-ref:** Spec section 5.2, requirements section 4e (sentinel rows invisible to agent prompt)

---

### TC-05 — Flat pricing key with no hint row renders as flat bullet, no warning (spec section 5.3)

**Setup:**
- Config rows include:
  - `pricing_gas_top_up` → `"Gas Top-Up: $60"`
  - (no `variation_hint_gas_top_up` row)

**Assertions:**
1. `"- Gas Top-Up: $60"` appears in `msg`.
2. No warning is emitted for flat keys with a missing hint row (use `caplog` to verify no WARNING-level log contains `gas_top_up`).
3. No `"Clarification required"` text for gas_top_up.

**AC cross-ref:** Spec section 5.3 (no warning for flat key with missing hint)

---

### TC-06 — Missing hint row for a variation group: warning emitted + flat bullets rendered, no crash (AC-08, spec section 5.4)

**Setup:**
- Config rows include:
  - `pricing_deep_clean__studio` → `"Deep Clean (studio): $150"`
  - `pricing_deep_clean__3br` → `"Deep Clean (3-bedroom): $220"`
  - (no `variation_hint_deep_clean` row)

**Assertions:**
1. A WARNING-level log message containing `"variation_hint_deep_clean missing from config"` is emitted (use `caplog`).
2. `"- Deep Clean (studio): $150"` appears in `msg` as a flat bullet.
3. `"- Deep Clean (3-bedroom): $220"` appears in `msg` as a flat bullet.
4. No `"Clarification required"` text is injected.
5. No exception is raised — `build_system_message` completes successfully.

**AC cross-ref:** AC-08 (missing hint → warning + flat bullets, no crash)

---

### TC-07 — Non-variation pricing rows unaffected (existing flat-key behaviour preserved)

**Setup:**
- Config rows include only flat pricing keys (no `__` in any key):
  - `pricing_general` → `"General Servicing: $50"`
  - `pricing_chemical` → `"Chemical Wash: $80"`

**Assertions:**
1. `"- General Servicing: $50"` appears in `msg`.
2. `"- Chemical Wash: $80"` appears in `msg`.
3. No `"varies by unit size"` text anywhere in `msg`.
4. No `"Clarification required"` text anywhere in `msg`.
5. No WARNING log emitted (use `caplog`).

**AC cross-ref:** Spec section 4.2 (flat key path unchanged), existing test `test_system_message_pricing_from_config` must continue to pass.

---

### TC-08 — PRICING section structure unchanged when no variation keys present

**Setup:** Default `_make_config_rows()` from the existing test file (no `__` keys).

**Assertions:**
1. `"PRICING:"` section is present.
2. All existing pricing values appear as flat bullets.
3. Sections appear in order: SERVICES < PRICING < APPOINTMENT WINDOWS < POLICIES (existing `test_system_message_sections_in_order` must pass unchanged).

**AC cross-ref:** Spec constraint: all other sections are unchanged. Regression guard.

---

### TC-09 — `parent_slug_display_name` helper converts slug to title-case display name

**Setup:** Test the helper directly if exposed, or verify indirectly via TC-01.

**Assertions:**
- `"general_servicing"` → renders as `"General Servicing"` in block header.
- `"deep_clean"` → renders as `"Deep Clean"` in block header.
- `"gas_top_up"` → renders as `"Gas Top Up"` in block header (verified if a test uses that slug as a variation parent).

**AC cross-ref:** Spec section 4.3 (display name derivation)

---

### TC-10 — Mixed config: variation group + flat keys coexist correctly

**Setup:**
- Config rows include:
  - `pricing_general_servicing__standard` → `"General Servicing (standard): $80"`
  - `pricing_general_servicing__18_24k` → `"General Servicing (large): $100"`
  - `variation_hint_general_servicing` → `"What BTU is your unit?"`
  - `pricing_chemical_wash` → `"Chemical Wash: $120"`
  - `variation_hint_chemical_wash` → `"none"`
  - `pricing_gas_top_up` → `"Gas Top-Up: $60"`

**Assertions:**
1. Structured variation block present for `general_servicing`.
2. `"- Chemical Wash: $120"` present as flat bullet.
3. `"- Gas Top-Up: $60"` present as flat bullet.
4. `"none"` not present in `msg`.
5. No duplicate variation block for `general_servicing`.
6. No WARNING log emitted (all variation groups have valid hints or sentinels).

**AC cross-ref:** Integration of all paths in a single realistic config — most representative of the HeyAircon production config post-migration.

---

### TC-11 — Anomalous flat key with active hint: warning emitted, flat bullet rendered (spec section 4.2 flat key path)

**Setup:**
- Config rows include:
  - `pricing_inspection` → `"Inspection: $45"` (no `__` — flat key)
  - `variation_hint_inspection` → `"What floor is the unit on?"` (non-"none" active hint for a flat key — anomalous)

**Assertions:**
1. A WARNING-level log message is emitted containing `"variation_hint_inspection"` and indicating the anomalous condition (active hint with no variation keys).
2. `"- Inspection: $45"` appears as a flat bullet in `msg`.
3. No `"Clarification required"` text is injected for inspection.

**AC cross-ref:** Spec section 4.2 flat key anomaly path (degrade safely, warn)

---

## 4. Regression Guard

All existing `test_context_builder.py` tests must continue to pass without modification. In particular:

- `test_system_message_contains_identity_block`
- `test_system_message_sections_in_order`
- `test_system_message_services_from_config`
- `test_system_message_pricing_from_config` — note: this test uses flat keys (`pricing_general`, `pricing_chemical`) with no `__`. It must still pass because flat key behaviour is unchanged.
- `test_system_message_appointment_windows_from_config`
- `test_system_message_appointment_windows_defaults`
- `test_system_message_policies_from_db`
- `test_system_message_empty_config_still_assembles`

---

## 5. AC Cross-Reference Table

| AC | Description | Test Cases | Test Surface |
|----|-------------|------------|--------------|
| AC-01 | Agent asked BTU question before quoting when variation keys exist | TC-01, TC-10 | Unit: "Clarification required" line in rendered block |
| AC-02 | Agent must not skip clarification even on direct booking request | (eval only) | Policy row content — out of scope for unit tests |
| AC-03 | Large unit confirmed → 18k–24k price only | (eval only) | Conversation-level |
| AC-04 | Standard unit confirmed → standard price only | (eval only) | Conversation-level |
| AC-05 | Unsure customer → price range + explicit yes required | (eval only) | Conversation-level |
| AC-05a | write_booking notes = "price pending BTU confirmation" | (eval only) | Tool call inspection |
| AC-06 | Unsure customer declines → no booking, escalate | (eval only) | Conversation-level |
| AC-07 | Hint text is from config, not hardcoded | TC-01, TC-02 | Unit: custom hint value appears verbatim in rendered block |
| AC-08 | Missing variation_hint → warning + flat bullets, no crash | TC-06 | Unit: caplog assert + flat bullet assert + no exception |
| AC-09 | Pattern works for any service slug | TC-02, TC-10 | Unit: `deep_clean` slug triggers identical structured rendering |

---

## 6. Validation Commands

Run from the repository root:

```bash
# Run all context_builder tests
cd ".worktree/service-variations-slice1" && python -m pytest engine/tests/unit/test_context_builder.py -v

# Run full unit test suite (regression guard)
python -m pytest engine/tests/unit/ -v

# Run full test suite
python -m pytest engine/tests/ -v
```

All tests must be green before the worktree is approved for merge.

---

## 7. Definition of Done

- [ ] TC-01 through TC-11 pass.
- [ ] All pre-existing `test_context_builder.py` tests still pass (regression clean).
- [ ] Full unit suite (`engine/tests/unit/`) green.
- [ ] No WARNING logs emitted in test cases where none are expected.
- [ ] `caplog` used for log assertions — no `print` or ad-hoc log inspection.
- [ ] Implementation touches only `engine/core/context_builder.py` and `engine/tests/unit/test_context_builder.py`.
- [ ] No SQL, no other files modified.
