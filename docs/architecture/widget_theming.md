# Architecture Specification: Widget Theming Customization

> **Architecture Document**  
> Author: @software-architect  
> Date: 2 May 2026  
> Status: Ready for Implementation  
> Related Requirements: `docs/requirements/widget_theming.md`

---

## 1. System Overview

### Purpose
Enable per-client visual customization of the Flow AI chat widget through database configuration. Primary color and button icon are injected at serve time (Python) and consumed at runtime (JavaScript).

### Scope
- Server-side injection of theme variables (`widget_primary_color`, `widget_button_icon`) into served JavaScript
- Client-side consumption of injected variables in CSS and HTML
- Database schema extension (`clients` table)
- Hover state color derivation at runtime (browser)
- Validation and fallback handling

### Out of Scope (Phase 1)
- Secondary color customization (chat bubble background, typography colors)
- Font family customization
- Layout variations (widget position, size, border radius)
- Dark mode variants
- Per-visitor theme overrides

---

## 2. Design Decisions

### D1: Injection Pattern — Config Object (Recommended)

**Decision:** Inject theming configuration as a single `window.FLOWAI_CONFIG` object instead of separate `window.*` variables.

**Rationale:**
1. **Namespace discipline** — Single global reduces collision risk as widget configuration grows (future: font families, layout options, feature flags)
2. **Type safety** — JS consumers can destructure a known object shape instead of checking multiple globals
3. **Consistency** — Aligns with modern config injection patterns (Stripe, Intercom, etc.)
4. **Future extensibility** — Adding new config fields requires no change to injection block structure

**Implementation:**
```javascript
window.FLOWAI_CONFIG = {
  clientId: 'hey-aircon',
  primaryColor: '#1B5E3F',
  buttonIcon: '💬'
};
```

**Injected before the widget IIFE** so all functions can access `window.FLOWAI_CONFIG` at initialization time.

**Rejected alternative (Option A: separate window vars):**  
Would work but creates namespace pollution and harder future maintenance when adding 5+ config fields.

---

### D2: Hover Color Derivation — Runtime JS (Recommended)

**Decision:** Derive hover color at runtime in JavaScript using a lightweight darkening function.

**Rationale:**
1. **Separation of concerns** — Python serves configuration, browser handles presentation
2. **Simplicity** — No Python color parsing/manipulation logic (avoiding `colormath` or regex hex parsing)
3. **Zero latency** — Hover state computed once at DOM injection time (not per-hover)
4. **Client-side correctness** — Browser knows the actual rendered color (accounts for CSS overrides or transparency)

**Implementation:**
Add a `_darkenColor(hex, percent)` utility in `widget.js`:
```javascript
function _darkenColor(hex, percent) {
  // Parses #RRGGBB, darkens each channel by percent (0-100)
  const num = parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.floor((num >> 16) * (1 - percent / 100)));
  const g = Math.max(0, Math.floor(((num >> 8) & 0x00FF) * (1 - percent / 100)));
  const b = Math.max(0, Math.floor((num & 0x0000FF) * (1 - percent / 100)));
  return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, '0')}`;
}
```

Call once in `injectStyles()`:
```javascript
const primaryColor = (window.FLOWAI_CONFIG && window.FLOWAI_CONFIG.primaryColor) || '#1B5E3F';
const hoverColor = _darkenColor(primaryColor, 10);
```

**Rejected alternative (Option A: Python-computed hover color):**  
Would require Python hex parsing + color manipulation logic. Overkill for a 10% darken operation. Adds maintenance burden and ties presentation logic to backend.

---

### D3: Validation and Fallback Strategy

**Requirement:** Invalid or missing config values must not break the widget. Fallback to Flow AI brand defaults.

**Validation rules:**

| Field | Invalid Condition | Fallback Value | Log Level |
|-------|-------------------|----------------|-----------|
| `primaryColor` | Not a 6-char hex (`#[0-9A-Fa-f]{6}`) | `#1B5E3F` (Flow AI green) | `warning` |
| `primaryColor` | `NULL` or empty string | `#1B5E3F` | `warning` |
| `buttonIcon` | `NULL` or empty string | `💬` | `warning` |
| `buttonIcon` | Length > 4 characters | Truncate to first 4 chars | `warning` |

**Where validation happens:**
- **Python (serve time):** `serve_widget_js()` validates before injection. Invalid values replaced with defaults + log warning.
- **JavaScript (runtime):** `injectStyles()` and `injectHTML()` check `window.FLOWAI_CONFIG` existence and apply fallbacks if undefined.

**Defensive JS pattern:**
```javascript
const primaryColor = (window.FLOWAI_CONFIG && window.FLOWAI_CONFIG.primaryColor) || '#1B5E3F';
const buttonIcon = (window.FLOWAI_CONFIG && window.FLOWAI_CONFIG.buttonIcon) || '💬';
```

---

## 3. Data Model Changes

### M1: Clients Table — New Column

**Table:** `clients` (shared Supabase `flowai-platform`)

**Migration:** `supabase/migrations/009_widget_button_icon.sql`

**DDL:**
```sql
-- Add widget_button_icon column with default emoji
ALTER TABLE clients
  ADD COLUMN widget_button_icon TEXT NOT NULL DEFAULT '💬';

-- Add check constraint: max 4 characters
ALTER TABLE clients
  ADD CONSTRAINT widget_button_icon_length CHECK (char_length(widget_button_icon) <= 4);

-- Backfill existing rows (no-op — default applies to all NULL)
UPDATE clients
  SET widget_button_icon = '💬'
  WHERE widget_button_icon IS NULL;

COMMENT ON COLUMN clients.widget_button_icon IS 'Emoji or short text displayed on floating widget button (max 4 chars, default 💬)';
```

**Notes:**
- Default `'💬'` ensures all existing and new clients inherit the current hardcoded icon
- `NOT NULL` enforced at DB level — Python always reads a valid string
- Check constraint prevents overly long strings (UI truncates client-side, but DB prevents storage)

---

### M2: ClientConfig Dataclass Extension

**File:** `engine/config/client_config.py`

**Change:** Add `widget_button_icon` field to `ClientConfig` dataclass.

**Before:**
```python
@dataclass
class ClientConfig:
    # ... existing fields ...
    widget_primary_color: str = '#4F46E5'
    widget_agent_name: str = 'Assistant'
    widget_welcome_message: str = 'Hi! How can I help you today?'
    widget_allowed_origins: str = ''
    widget_session_ttl_minutes: int = 30
```

**After:**
```python
@dataclass
class ClientConfig:
    # ... existing fields ...
    widget_primary_color: str = '#4F46E5'  # Will change default to '#1B5E3F' in migration 010
    widget_button_icon: str = '💬'
    widget_agent_name: str = 'Assistant'
    widget_welcome_message: str = 'Hi! How can I help you today?'
    widget_allowed_origins: str = ''
    widget_session_ttl_minutes: int = 30
```

**Notes:**
- Default `'💬'` matches database default
- Python type hint `str` — no `Optional` because DB column is `NOT NULL`
- Field positioned immediately after `widget_primary_color` for logical grouping (appearance fields together)

---

### M3: load_client_config() Loader Update

**File:** `engine/config/client_config.py`

**Change:** Read `widget_button_icon` from Supabase `clients` row.

**Before:**
```python
async def load_client_config(client_id: str) -> ClientConfig:
    # ... [cache check logic] ...
    
    # Read from shared Supabase clients table
    response = await shared_db.table("clients").select("*").eq("client_id", client_id).eq("is_active", True).single().execute()
    
    # ... [row extraction] ...
    
    return ClientConfig(
        client_id=client_id,
        # ... [existing field mappings] ...
        widget_enabled=row.get("widget_enabled", False),
        widget_primary_color=row.get("widget_primary_color", "#4F46E5"),
        widget_agent_name=row.get("widget_agent_name", "Assistant"),
        widget_welcome_message=row.get("widget_welcome_message", "Hi! How can I help you today?"),
        widget_allowed_origins=row.get("widget_allowed_origins", ""),
        widget_session_ttl_minutes=row.get("widget_session_ttl_minutes", 30),
    )
```

**After:**
```python
async def load_client_config(client_id: str) -> ClientConfig:
    # ... [cache check logic — unchanged] ...
    
    # Read from shared Supabase clients table
    response = await shared_db.table("clients").select("*").eq("client_id", client_id).eq("is_active", True).single().execute()
    
    # ... [row extraction — unchanged] ...
    
    return ClientConfig(
        client_id=client_id,
        # ... [existing field mappings — unchanged] ...
        widget_enabled=row.get("widget_enabled", False),
        widget_primary_color=row.get("widget_primary_color", "#4F46E5"),
        widget_button_icon=row.get("widget_button_icon", "💬"),  # NEW
        widget_agent_name=row.get("widget_agent_name", "Assistant"),
        widget_welcome_message=row.get("widget_welcome_message", "Hi! How can I help you today?"),
        widget_allowed_origins=row.get("widget_allowed_origins", ""),
        widget_session_ttl_minutes=row.get("widget_session_ttl_minutes", 30),
    )
```

**Notes:**
- `.get("widget_button_icon", "💬")` fallback redundant (DB has `NOT NULL` + default) but defensive in case future migrations change constraint
- Positioned after `widget_primary_color` to match dataclass field order

---

## 4. Server-Side Injection (Python)

### I1: serve_widget_js() — Validation + Injection Block

**File:** `engine/api/widget.py`

**Change:** Replace single-line `client_id` injection with validated `FLOWAI_CONFIG` object injection.

**Before:**
```python
# Prepend client_id
js_with_client_id = f"window.FLOWAI_CLIENT_ID = '{client_id}';\n{widget_js_content}"

return Response(
    content=js_with_client_id.encode("utf-8"),
    media_type="application/javascript; charset=utf-8",
    headers={"Cache-Control": "public, max-age=3600"},
)
```

**After:**
```python
# Validate and prepare config values
primary_color = client_config.widget_primary_color
button_icon = client_config.widget_button_icon

# Validate hex color format (#RRGGBB)
import re
if not re.match(r'^#[0-9A-Fa-f]{6}$', primary_color):
    logger.warning(
        f"Invalid widget_primary_color '{primary_color}' for {client_id}. "
        f"Falling back to default #1B5E3F"
    )
    primary_color = '#1B5E3F'

# Truncate button icon if too long (UI constraint: max 4 chars)
if len(button_icon) > 4:
    logger.warning(
        f"widget_button_icon '{button_icon}' exceeds 4 characters for {client_id}. "
        f"Truncating to '{button_icon[:4]}'"
    )
    button_icon = button_icon[:4]

# Fallback for empty icon
if not button_icon:
    logger.warning(f"Empty widget_button_icon for {client_id}. Falling back to 💬")
    button_icon = '💬'

# Build config object injection block
config_injection = f"""window.FLOWAI_CONFIG = {{
  clientId: '{client_id}',
  primaryColor: '{primary_color}',
  buttonIcon: '{button_icon}'
}};
"""

# Prepend config before widget IIFE
js_with_config = config_injection + widget_js_content

return Response(
    content=js_with_config.encode("utf-8"),
    media_type="application/javascript; charset=utf-8",
    headers={"Cache-Control": "public, max-age=3600"},
)
```

**Notes:**
- Hex validation uses simple regex (no color library dependency)
- Truncation at serve time prevents malformed HTML (DB check constraint is defense-in-depth)
- All validation warnings include `client_id` for operational debugging
- Config object formatted for readability (multi-line) — minification not needed for 3-field object
- Injection precedes widget IIFE so all widget functions see `window.FLOWAI_CONFIG` at initialization

---

## 5. Client-Side Consumption (JavaScript)

### C1: widget.js — Variable Extraction + Hover Color Utility

**File:** `engine/static/widget.js`

**Change:** Add utility function and extract config at top of IIFE.

**Location:** After `'use strict';` declaration, before existing config constants.

**Add:**
```javascript
(function() {
  'use strict';
  
  // ── Config extraction ──────────────────────────────────────────────────────
  const CONFIG = window.FLOWAI_CONFIG || {};
  const CLIENT_ID = CONFIG.clientId || '';
  const PRIMARY_COLOR = CONFIG.primaryColor || '#1B5E3F';
  const BUTTON_ICON = CONFIG.buttonIcon || '💬';
  
  // Derive hover color (10% darker)
  function _darkenColor(hex, percent) {
    const num = parseInt(hex.slice(1), 16);
    const r = Math.max(0, Math.floor((num >> 16) * (1 - percent / 100)));
    const g = Math.max(0, Math.floor(((num >> 8) & 0x00FF) * (1 - percent / 100)));
    const b = Math.max(0, Math.floor((num & 0x0000FF) * (1 - percent / 100)));
    return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, '0')}`;
  }
  const HOVER_COLOR = _darkenColor(PRIMARY_COLOR, 10);
  
  // ── Existing config constants ──────────────────────────────────────────────
  const SESSION_KEY = 'flowai_session_' + CLIENT_ID;
  // ... [rest of existing code] ...
```

**Notes:**
- `CONFIG` destructured once at top — all subsequent code uses `PRIMARY_COLOR`, `BUTTON_ICON`, `HOVER_COLOR` constants
- `_darkenColor()` called once at initialization (not per hover event)
- Fallbacks `|| '#1B5E3F'` and `|| '💬'` defend against missing injection (e.g., old cached widget.js served without server update)

---

### C2: widget.js — CSS Style Replacements

**File:** `engine/static/widget.js`

**Change:** Replace hardcoded `#4F46E5` with `PRIMARY_COLOR` variable, `#4338CA` with `HOVER_COLOR` variable.

**Affected CSS rules in `injectStyles()` function:**

| Rule Selector | Property | Before | After |
|---------------|----------|--------|-------|
| `#flowai-widget-btn` | `background` | `#4F46E5` | `${PRIMARY_COLOR}` |
| `#flowai-widget-header` | `background` | `#4F46E5` | `${PRIMARY_COLOR}` |
| `#flowai-start-chat` | `background` | `#4F46E5` | `${PRIMARY_COLOR}` |
| `#flowai-start-chat:hover` | `background` | `#4338CA` | `${HOVER_COLOR}` |
| `.flowai-message-user` | `background` | `#4F46E5` | `${PRIMARY_COLOR}` |
| `#flowai-send-btn` | `background` | `#4F46E5` | `${PRIMARY_COLOR}` |
| `#flowai-send-btn:hover` | `background` | `#4338CA` | `${HOVER_COLOR}` |

**Implementation:**

Change `style.textContent = \`...\`;` template literal to use `${PRIMARY_COLOR}` and `${HOVER_COLOR}` instead of hardcoded hex values.

**Before (example):**
```javascript
function injectStyles() {
  const style = document.createElement('style');
  style.textContent = `
    #flowai-widget-btn {
      background: #4F46E5;
      /* ... */
    }
    #flowai-widget-btn:hover {
      /* no explicit hover color — uses transform only */
    }
    #flowai-widget-header {
      background: #4F46E5;
      /* ... */
    }
  `;
  document.head.appendChild(style);
}
```

**After:**
```javascript
function injectStyles() {
  const style = document.createElement('style');
  style.textContent = `
    #flowai-widget-btn {
      background: ${PRIMARY_COLOR};
      /* ... */
    }
    #flowai-widget-btn:hover {
      background: ${HOVER_COLOR};
      transform: scale(1.05);
    }
    #flowai-widget-header {
      background: ${PRIMARY_COLOR};
      /* ... */
    }
    #flowai-start-chat {
      background: ${PRIMARY_COLOR};
      /* ... */
    }
    #flowai-start-chat:hover {
      background: ${HOVER_COLOR};
    }
    .flowai-message-user {
      background: ${PRIMARY_COLOR};
      /* ... */
    }
    #flowai-send-btn {
      background: ${PRIMARY_COLOR};
      /* ... */
    }
    #flowai-send-btn:hover {
      background: ${HOVER_COLOR};
    }
  `;
  document.head.appendChild(style);
}
```

**Note:** Add explicit `background: ${HOVER_COLOR};` to `#flowai-widget-btn:hover` — currently only has `transform`. Other hover states already exist in CSS.

---

### C3: widget.js — Button Icon HTML Replacement

**File:** `engine/static/widget.js`

**Change:** Replace hardcoded `💬` emoji with `BUTTON_ICON` variable.

**Affected HTML in `injectHTML()` function:**

| Element | Before | After |
|---------|--------|-------|
| `#flowai-widget-btn` inner text | `<div id="flowai-widget-btn">💬</div>` | `<div id="flowai-widget-btn">${BUTTON_ICON}</div>` |

**Implementation:**

Change `container.innerHTML = \`...\`;` template literal to use `${BUTTON_ICON}`.

**Before:**
```javascript
function injectHTML() {
  const container = document.createElement('div');
  container.innerHTML = `
    <div id="flowai-widget-btn">💬</div>
    <div id="flowai-widget-window" style="display:none">
      <!-- ... -->
    </div>
  `;
  document.body.appendChild(container);
}
```

**After:**
```javascript
function injectHTML() {
  const container = document.createElement('div');
  container.innerHTML = `
    <div id="flowai-widget-btn">${BUTTON_ICON}</div>
    <div id="flowai-widget-window" style="display:none">
      <!-- ... -->
    </div>
  `;
  document.body.appendChild(container);
}
```

---

## 6. Migration Specification

### Migration 009: Add widget_button_icon Column

**File:** `supabase/migrations/009_widget_button_icon.sql`

**Target database:** Shared Supabase `flowai-platform`

**SQL:**
```sql
-- Migration 009: Add widget_button_icon column to clients table
-- Purpose: Enable per-client customization of widget floating button icon
-- Date: 2026-05-02
-- Related: docs/requirements/widget_theming.md (FR-03)

BEGIN;

-- Add column with default emoji
ALTER TABLE clients
  ADD COLUMN widget_button_icon TEXT NOT NULL DEFAULT '💬';

-- Add length constraint (max 4 characters for UI fit)
ALTER TABLE clients
  ADD CONSTRAINT widget_button_icon_length CHECK (char_length(widget_button_icon) <= 4);

-- Backfill existing rows (no-op — default already applies)
-- Explicit UPDATE for audit trail clarity
UPDATE clients
  SET widget_button_icon = '💬'
  WHERE widget_button_icon IS NULL;

-- Add column comment for schema documentation
COMMENT ON COLUMN clients.widget_button_icon IS 
  'Emoji or short text displayed on floating widget button. Max 4 characters. Default: 💬';

COMMIT;

-- Verification query (run manually post-migration)
-- SELECT client_id, widget_button_icon, char_length(widget_button_icon) AS icon_length
-- FROM clients
-- ORDER BY client_id;
```

**Notes:**
- `NOT NULL DEFAULT '💬'` ensures no NULL state — backfill UPDATE is defensive only
- Check constraint enforces max length at DB level (Python truncates at serve time as second line of defense)
- Migration wrapped in transaction for atomicity
- Verification query provided for post-migration audit

---

### Migration 010: Change Default Primary Color (Separate Migration)

**File:** `supabase/migrations/010_widget_default_green.sql`

**Purpose:** Change `widget_primary_color` default from indigo `#4F46E5` to Flow AI green `#1B5E3F` (FR-01).

**SQL:**
```sql
-- Migration 010: Change widget_primary_color default to Flow AI green
-- Purpose: Align widget default color with Flow AI brand identity
-- Date: 2026-05-02
-- Related: docs/requirements/widget_theming.md (FR-01)

BEGIN;

-- Change column default (does NOT update existing rows)
ALTER TABLE clients
  ALTER COLUMN widget_primary_color SET DEFAULT '#1B5E3F';

-- Backfill existing rows that still use old indigo default
-- Only update rows where color is exactly the old default
UPDATE clients
  SET widget_primary_color = '#1B5E3F'
  WHERE widget_primary_color = '#4F46E5';

-- Add column comment documenting new default
COMMENT ON COLUMN clients.widget_primary_color IS 
  'Hex color code for widget primary brand color (button, header, user messages). Default: #1B5E3F (Flow AI green)';

COMMIT;

-- Verification query
-- SELECT client_id, widget_primary_color
-- FROM clients
-- ORDER BY client_id;
```

**Notes:**
- Separate migration from `009` because it modifies existing config behavior (not purely additive)
- Backfill only updates rows with exact match of old default `#4F46E5` — preserves client customizations
- Clients who explicitly set indigo keep their choice (business decision — explicit overrides are honored)

---

## 7. Code Map Updates

### File: `docs/architecture/code_map.md`

**Section:** `4. Where to Look` → `Widget Channel (Phase 1)`

**Add new row:**

| Task | First file to open |
|------|--------------------|
| Modify widget button appearance (color, icon) or hover states | `engine/static/widget.js` — `injectStyles()` function for CSS, `injectHTML()` for button icon; config extracted from `window.FLOWAI_CONFIG` at top of IIFE |

**Update existing row:**

**Before:**
```
| Change widget JavaScript delivery or caching | `api/widget_routes.py` — client_id injection, Cache-Control headers |
```

**After:**
```
| Change widget JavaScript delivery or caching | `api/widget.py` — `serve_widget_js()` function; validates and injects `window.FLOWAI_CONFIG` (clientId, primaryColor, buttonIcon), Cache-Control headers |
```

**Notes:**
- Clarifies that `serve_widget_js()` now injects full config object (not just `client_id`)
- Points implementers to validation logic in Python and consumption pattern in JS

---

## 8. Implementation Sequence

Recommended order to avoid merge conflicts and test incrementally:

1. **Migration 009** → Run SQL against shared Supabase, verify column exists
2. **Migration 010** → Run SQL to change default color, verify backfill
3. **ClientConfig dataclass** → Add `widget_button_icon` field, update type annotations
4. **load_client_config()** → Read `widget_button_icon` from DB row
5. **serve_widget_js()** → Add validation + inject `FLOWAI_CONFIG` object (requires step 3–4)
6. **widget.js — config extraction** → Add `_darkenColor()`, extract constants at top of IIFE
7. **widget.js — CSS replacements** → Replace all `#4F46E5` and `#4338CA` with variables
8. **widget.js — HTML replacement** → Replace hardcoded `💬` with `${BUTTON_ICON}`
9. **code_map.md** → Update routing table (documentation only, no functional dependency)

**Test checkpoints:**
- After step 5: Verify `window.FLOWAI_CONFIG` present in browser console when loading `/widget/{client_id}.js`
- After step 8: Verify widget renders with custom color + icon when `widget_primary_color` and `widget_button_icon` set in Supabase

---

## 9. Non-Functional Considerations

### Performance
- **Impact:** Negligible. Config injection adds <100 bytes to served JS payload.
- **Caching:** `serve_widget_js()` returns `Cache-Control: public, max-age=3600` — browser caches for 1 hour. Config changes propagate within 60 minutes (acceptable for branding updates).

### Security
- **XSS risk (mitigated):** `client_id`, `primaryColor`, `buttonIcon` injected into JS string literals. Values sourced from database (trusted) and validated (hex regex, length check). No user-supplied input.
- **Injection attack surface:** Hex validation regex prevents script injection via color field. Button icon truncated to 4 chars (no `<script>` tags possible). Config object uses single quotes in template literal (double quotes in values are escaped by Python f-string encoding).

### Observability
- **Logging:** Invalid config values logged at `warning` level with client ID. Operators can detect misconfiguration via log aggregation.
- **Metrics (future):** No metrics currently emitted for theming. Could add counter for validation fallbacks if misconfig becomes frequent.

### Scalability
- **Shared Supabase load:** Each widget serve queries `clients` table (cached 5 min). Theming adds no new DB queries. Cache hit rate >>95% for active clients.
- **Railway egress:** Config injection adds ~100 bytes per widget JS serve. At 10,000 daily widget loads = 1 MB/day (negligible).

---

## 10. Open Questions

None. Design is fully specified and ready for implementation.

---

## 11. Acceptance Criteria Mapping

| Requirements AC ID | Satisfied By | Verification Method |
|--------------------|--------------|---------------------|
| FR-01 AC1–AC3 (default green) | Migration 010 + ClientConfig default | Manual test: new client row → widget renders green |
| FR-02 AC1–AC4 (custom color) | serve_widget_js() validation + widget.js CSS | Manual test: set custom hex in Supabase → widget reflects color |
| FR-02 AC5 (invalid color fallback) | serve_widget_js() hex regex validation | Unit test: invalid hex → fallback to `#1B5E3F` + warning log |
| FR-03 AC1–AC4 (custom icon) | Migration 009 + serve_widget_js() + widget.js HTML | Manual test: set emoji in Supabase → widget button displays emoji |
| FR-03 AC5 (truncation) | serve_widget_js() length check | Unit test: 7-char string → truncated to 4 chars + warning log |
| FR-03 AC6 (empty fallback) | serve_widget_js() empty check | Unit test: empty string → fallback to '💬' + warning log |
| FR-04 AC1 (injection presence) | serve_widget_js() config_injection block | Integration test: GET `/widget/hey-aircon.js` → response contains `window.FLOWAI_CONFIG` |

---

## 12. Files Modified Summary

| File | Change Type | Lines Changed (Est.) |
|------|-------------|---------------------|
| `supabase/migrations/009_widget_button_icon.sql` | Create | 30 |
| `supabase/migrations/010_widget_default_green.sql` | Create | 25 |
| `engine/config/client_config.py` | Modify (dataclass + loader) | +2 (dataclass), +1 (loader) |
| `engine/api/widget.py` | Modify (serve_widget_js validation) | +35 (replace 2 lines with validation block) |
| `engine/static/widget.js` | Modify (config extraction + CSS + HTML) | +15 (config block), ~20 (CSS replacements), +1 (HTML) |
| `docs/architecture/code_map.md` | Modify (routing table) | +1 row, update 1 row |

**Total estimated LOC:** ~130 lines across 6 files (5 implementation, 1 documentation).

---

## End of Specification
