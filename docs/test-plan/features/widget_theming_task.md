# Widget Theming — Task Document

**Target Agent:** `@software-engineer`  
**Worktree:** `.worktree/widget-05-theming`  
**Status:** Ready for Implementation  
**Date:** 2026-05-02  

---

## Goal

Enable per-client widget visual customization (primary color + button icon) via Supabase configuration, replacing hardcoded indigo with Flow AI green as default.

---

## Prerequisite

**Baseline:** `main` (no prerequisites — branches directly from current master HEAD)

---

## Success Check

**Founder-visible success condition:** Client can set custom `widget_primary_color` and `widget_button_icon` in Supabase; widget served at `/widget/{client_id}.js` applies those values immediately with zero deployments. Invalid values fall back gracefully to Flow AI brand defaults.

**Proof metric:** 
1. Served widget JS contains `window.FLOWAI_CONFIG` object with correct color + icon for client
2. Widget HTML/CSS no longer contains hardcoded `#4F46E5` (old indigo)
3. All widget theming unit tests pass

**Proxy metrics:** 
- Supabase migrations 009 + 010 applied successfully
- `ClientConfig` dataclass loads `widget_button_icon` field
- `serve_widget_js()` injects `window.FLOWAI_CONFIG` object
- 7 hardcoded color references + 1 hardcoded icon in `widget.js` replaced with config vars

---

## Test Plan

### Unit Tests — Config Loading

**File:** `engine/tests/test_client_config.py`

#### Test 1: `test_client_config_widget_button_icon`
**What:** ClientConfig loads `widget_button_icon` field from Supabase row correctly  
**Given:** Supabase `clients` table row with `widget_button_icon = '🛠️'`  
**When:** `load_client_config()` called for that client  
**Then:** `ClientConfig.widget_button_icon == '🛠️'`  
**Validation:** Assert field value matches database value; assert default is `'💬'` when field is NULL

---

### Unit Tests — Widget Serve & Injection

**File:** `engine/tests/test_widget.py`

#### Test 2: `test_serve_widget_js_injects_config_object`
**What:** Served widget JS contains `window.FLOWAI_CONFIG` object with correct shape and values  
**Given:** Client has `widget_primary_color = '#1B5E3F'` and `widget_button_icon = '💬'`  
**When:** `serve_widget_js()` called for that client  
**Then:** Response body contains:
```javascript
window.FLOWAI_CONFIG = {"clientId": "<client_id>", "primaryColor": "#1B5E3F", "buttonIcon": "💬"};
```
**Validation:** JSON parse the config object; assert all 3 fields present; assert hex format is correct

#### Test 3: `test_serve_widget_js_invalid_hex_fallback`
**What:** Invalid hex color in database falls back to Flow AI green default  
**Given:** Client has `widget_primary_color = 'blue'` (invalid hex)  
**When:** `serve_widget_js()` called  
**Then:** Served JS contains `"primaryColor": "#1B5E3F"` (fallback)  
**And:** Warning logged: "Invalid widget_primary_color for client {client_id}: 'blue'. Falling back to #1B5E3F"  
**Validation:** Assert served color is `#1B5E3F`; assert log contains warning

#### Test 4: `test_serve_widget_js_icon_truncated`
**What:** Icon longer than 4 characters is truncated to 4 chars  
**Given:** Client has `widget_button_icon = 'CONTACT'` (7 chars)  
**When:** `serve_widget_js()` called  
**Then:** Served JS contains `"buttonIcon": "CONT"` (first 4 chars only)  
**And:** Warning logged: "widget_button_icon for client {client_id} exceeds 4 chars. Truncated to 'CONT'"  
**Validation:** Assert served icon length is 4; assert truncation is prefix-only; assert log contains warning

#### Test 5: `test_serve_widget_js_default_green`
**What:** Client with default config (no custom color) serves Flow AI green, not old indigo  
**Given:** Client has `widget_primary_color = '#1B5E3F'` (new default)  
**When:** `serve_widget_js()` called  
**Then:** Served JS contains `"primaryColor": "#1B5E3F"`  
**Validation:** Assert served color is green; assert it is NOT `#4F46E5`

---

### Integration Tests — End-to-End Widget Endpoint

**File:** `engine/tests/test_widget_integration.py`

#### Test 6: `test_widget_js_endpoint_contains_no_hardcoded_indigo`
**What:** Served widget JS no longer contains hardcoded indigo references  
**Given:** Any test client (e.g., `test-client`)  
**When:** `GET /widget/test-client.js`  
**Then:** Response body does NOT contain string `'#4F46E5'` anywhere  
**Validation:** `assert '#4F46E5' not in response.text`; regex search for hex pattern to confirm all replaced

#### Test 7: `test_widget_js_endpoint_custom_color`
**What:** Client with custom color serves that color in FLOWAI_CONFIG  
**Given:** Test client set to `widget_primary_color = '#FF6B35'` (custom orange)  
**When:** `GET /widget/test-client.js`  
**Then:** Response body contains `"primaryColor": "#FF6B35"` in FLOWAI_CONFIG  
**Validation:** Parse config object from response; assert `primaryColor` field matches expected custom value

---

### JS Unit Tests (Optional — if time permits)

**File:** `engine/static/tests/widget.test.js` (create if doesn't exist)

#### Test 8: `test_widget_js_reads_config_object`
**What:** Widget JavaScript correctly reads `window.FLOWAI_CONFIG` instead of hardcoded values  
**Given:** `window.FLOWAI_CONFIG = {primaryColor: '#00AA66', buttonIcon: '🏠'}`  
**When:** Widget initializes  
**Then:** Widget CSS applies `#00AA66` to button background; button HTML contains `🏠`  
**Validation:** Mock `window.FLOWAI_CONFIG`; spy on DOM injection; assert CSS + HTML use config values

---

## Files to Create

### 1. `supabase/migrations/009_widget_button_icon.sql`

**Purpose:** Add `widget_button_icon` column to `clients` table

**DDL:**
```sql
-- ========================================================================
-- Migration 009: Widget Button Icon
-- Purpose: Add per-client widget button icon customization
-- Date: 2026-05-02
-- ========================================================================

-- Add widget_button_icon column with default emoji
ALTER TABLE clients
  ADD COLUMN widget_button_icon TEXT NOT NULL DEFAULT '💬';

-- Add check constraint: max 4 characters
ALTER TABLE clients
  ADD CONSTRAINT widget_button_icon_length CHECK (char_length(widget_button_icon) <= 4);

-- Backfill existing rows (no-op — default applies automatically)
UPDATE clients
  SET widget_button_icon = '💬'
  WHERE widget_button_icon IS NULL;

COMMENT ON COLUMN clients.widget_button_icon IS 'Emoji or short text displayed on floating widget button (max 4 chars, default 💬)';
```

**Expected Outcome:** All clients have `widget_button_icon = '💬'` after migration; constraint prevents storage of strings > 4 chars

---

### 2. `supabase/migrations/010_widget_default_green.sql`

**Purpose:** Change `widget_primary_color` default from indigo to Flow AI green; backfill legacy default

**DDL:**
```sql
-- ========================================================================
-- Migration 010: Widget Default Color (Flow AI Green)
-- Purpose: Change default widget color from indigo to Flow AI green
-- Date: 2026-05-02
-- ========================================================================

-- Update default for new rows
ALTER TABLE clients
  ALTER COLUMN widget_primary_color SET DEFAULT '#1B5E3F';

-- Backfill legacy default to new default (assumes old default was never intentionally chosen)
UPDATE clients
  SET widget_primary_color = '#1B5E3F'
  WHERE widget_primary_color = '#4F46E5';

COMMENT ON COLUMN clients.widget_primary_color IS 'Primary brand color for widget (hex format, default Flow AI green #1B5E3F)';
```

**Expected Outcome:** All clients with old indigo default now have green; new clients default to green; custom colors preserved

---

## Files to Modify

### 3. `engine/config/client_config.py`

**Changes Required:**

#### Add field to ClientConfig dataclass:
```python
@dataclass
class ClientConfig:
    # ... existing fields ...
    widget_button_icon: str = '💬'  # Add this line
```

#### Update `load_client_config()` to read new field:
```python
def load_client_config(client_id: str, row: dict) -> ClientConfig:
    return ClientConfig(
        client_id=client_id,
        # ... existing field mappings ...
        widget_button_icon=row.get("widget_button_icon", "💬"),  # Add this line
    )
```

**Expected Outcome:** `ClientConfig` can load and expose `widget_button_icon` from Supabase

---

### 4. `engine/api/widget.py`

**Changes Required:**

#### Replace simple client_id prepend with full config object injection:

**Current (before):**
```python
widget_js_content = f"window.FLOWAI_CLIENT_ID = '{client_id}';\n" + widget_js_content
```

**Target (after):**
```python
# Validate and prepare config values
primary_color = client_config.widget_primary_color or "#1B5E3F"
if not re.match(r'^#[0-9A-Fa-f]{6}$', primary_color):
    logger.warning(f"Invalid widget_primary_color for client {client_id}: '{primary_color}'. Falling back to #1B5E3F")
    primary_color = "#1B5E3F"

button_icon = client_config.widget_button_icon or "💬"
if len(button_icon) > 4:
    logger.warning(f"widget_button_icon for client {client_id} exceeds 4 chars. Truncated to '{button_icon[:4]}'")
    button_icon = button_icon[:4]

# Inject config object
config_js = f"""window.FLOWAI_CONFIG = {{"clientId": "{client_id}", "primaryColor": "{primary_color}", "buttonIcon": "{button_icon}"}};"""
widget_js_content = config_js + "\n" + widget_js_content
```

**Expected Outcome:** Served JS starts with `window.FLOWAI_CONFIG = {...};` containing validated theme values

---

### 5. `engine/static/widget.js`

**Changes Required:**

#### Extract config at top of IIFE:
```javascript
(function() {
  'use strict';

  // Extract config from injected window object
  const config = window.FLOWAI_CONFIG || {};
  const CLIENT_ID = config.clientId || 'unknown';
  const PRIMARY_COLOR = config.primaryColor || '#1B5E3F';
  const BUTTON_ICON = config.buttonIcon || '💬';
  
  // Compute hover color (darken primary by 10%)
  function _darkenColor(hex, percent) {
    const num = parseInt(hex.slice(1), 16);
    const r = Math.max(0, Math.floor((num >> 16) * (1 - percent / 100)));
    const g = Math.max(0, Math.floor(((num >> 8) & 0x00FF) * (1 - percent / 100)));
    const b = Math.max(0, Math.floor((num & 0x0000FF) * (1 - percent / 100)));
    return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, '0')}`;
  }
  const HOVER_COLOR = _darkenColor(PRIMARY_COLOR, 10);

  // ... rest of widget code ...
})();
```

#### Replace all hardcoded `#4F46E5` with `${PRIMARY_COLOR}`:
**Current (before):**
```css
background: #4F46E5;
```

**Target (after):**
```css
background: ${PRIMARY_COLOR};
```

**Count of replacements needed:** 7 occurrences in `injectStyles()` function

#### Replace all hardcoded `#4338CA` hover values with `${HOVER_COLOR}`:
**Current (before):**
```css
background: #4338CA;
```

**Target (after):**
```css
background: ${HOVER_COLOR};
```

**Count of replacements needed:** ~3-4 occurrences in hover state CSS

#### Replace hardcoded `💬` in button HTML:
**Current (before):**
```html
<button id="flowai-widget-button">💬</button>
```

**Target (after):**
```html
<button id="flowai-widget-button">${BUTTON_ICON}</button>
```

**Expected Outcome:** Widget JavaScript reads config from `window.FLOWAI_CONFIG` and applies dynamic theme; no hardcoded colors or icons remain

---

## Validation Commands

After implementation, run these commands **inside the worktree** before reporting done:

### 1. Run widget-specific tests:
```bash
python3 -m pytest engine/tests/ -x -q --tb=short -k "widget" 2>&1 | tail -20
```
**Expected:** All new tests pass; no regressions in existing widget tests

### 2. Run full test suite (sanity check):
```bash
python3 -m pytest engine/tests/ -x -q --tb=short 2>&1 | tail -30
```
**Expected:** 52+ passing (pre-existing asyncio.coroutine failure in test_concurrent_clients.py is acceptable)

### 3. Visual inspection of served widget:
```bash
curl -s "http://localhost:8000/widget/test-client.js" | head -5
```
**Expected Output:**
```javascript
window.FLOWAI_CONFIG = {"clientId": "test-client", "primaryColor": "#1B5E3F", "buttonIcon": "💬"};
(function() {
  'use strict';
  ...
```

### 4. Verify no hardcoded indigo remains:
```bash
grep -n "#4F46E5" engine/static/widget.js
```
**Expected:** No matches (empty output)

---

## Commit Requirement

**BEFORE reporting done:**
1. Run `git add` on all modified/created files
2. Run `git commit -m "feat(widget): add per-client theming (color + icon)"`
3. Run `git log --oneline -5` to confirm commit exists

Do NOT exit worktree or report completion without a committed git log entry.

---

## Constraints

### Boundary Verification
**Integration type:** Internal refactor — no new external API surface  
**Changes:**
- Supabase: ADD columns only (no new tables, no dropped columns)
- Meta API: None
- Google Calendar: None
- Widget endpoint: Response format changes (adds config object injection), but path + query params unchanged

**No new integration boundaries introduced.** This is an internal theming refactor of existing widget serve logic.

### Format Command
**Project standard:** None specified (Python project with no explicit formatter configured)  
**Action:** Run `python3 -m black engine/` if Black is installed; otherwise proceed without format step

---

## Architecture Contract References

**Primary source:** `docs/architecture/widget_theming.md`

**Key sections:**
- §D1: Config Object Injection Pattern — `window.FLOWAI_CONFIG` shape and injection order
- §D2: Hover Color Derivation — `_darkenColor()` utility implementation
- §D3: Validation & Fallback Strategy — hex validation regex, truncation rules, log levels
- §M1: Clients Table Schema Changes — DDL for migrations 009 + 010

**Contract verification:**
- Config object must be injected BEFORE widget IIFE (order matters for initialization)
- Hex validation must use regex `^#[0-9A-Fa-f]{6}$` (exactly 6 hex digits after #)
- Icon truncation must be prefix-only (first 4 chars)
- Fallback values: `#1B5E3F` for color, `💬` for icon
- Hover color: darken primary by 10% using bit-shift darkening algorithm (see §D2 for exact implementation)

---

## Notes

- **Migration order:** 009 must run before 010 (010 references `widget_primary_color` which already exists; 009 adds new column)
- **Backward compatibility:** All existing clients safe — defaults applied automatically via migration + DB constraints
- **Zero downtime:** Config changes take effect on next widget load (no Railway restart required)
- **Test data:** Use `test-client` as the test client_id for integration tests (matches existing test fixtures)

---

## Sign-off

**SDET Engineer:** Ready for implementation  
**Software Engineer:** [Pending dispatch]  
**Verification Status:** [Pending test execution]  
**Merge Status:** [Pending approval]
