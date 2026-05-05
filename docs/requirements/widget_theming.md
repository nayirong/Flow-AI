# Feature Requirements: Widget Theming

> **Requirements Specification**  
> Author: @product-manager  
> Date: 2 May 2026  
> Status: Draft — Pending Founder Approval

---

## 1. Feature Overview

### What
Per-client customization of the Flow AI chat widget's visual brand identity. Clients can configure their widget's primary color and button icon via the `clients` table in Supabase. Changes take effect immediately on widget serve with zero code deployments.

### Who
**Primary users:** Flow AI clients (service business owners or marketing managers) who need the chat widget to match their brand identity when embedded on their website.

**Affected users:** End customers visiting client websites — they see a widget that visually aligns with the client's brand instead of a generic default.

### Why
**Current pain:** 
- All widgets hardcode indigo `#4F46E5` — clients cannot match their brand colors without code changes
- All widgets display a generic 💬 emoji — no brand differentiation between client widgets
- The `widget_primary_color` column exists in the database but is ignored at runtime

**Value delivered:**
- **Brand consistency** — clients can make the widget feel native to their site with 30 seconds of configuration
- **Self-service** — marketing teams control widget appearance via Supabase Studio, no developer required
- **Multi-tenancy differentiation** — each client's widget is visually distinct while running on shared infrastructure

### Channel
Widget served from Railway at `https://{engine-domain}/widget.js?client_id={client_id}`. Configuration read from Supabase `clients` table.

---

## Direction Check

- **Subject**: Flow AI clients (service business owners) who need their embedded widget to match their brand identity
- **Problem**: Widget appearance is hardcoded and generic — clients cannot customize colors or iconography without requesting code changes from Flow AI
- **Confirmation**: This solution gives the subject (clients) self-service control over widget appearance via database configuration — it does NOT address the inverse (e.g., giving end customers control over widget appearance, or making the widget blend with Flow AI's brand instead of the client's brand)

---

## 2. Default Brand Alignment

### FR-01: Default Widget Color

**Requirement:** The widget default primary color must be Flow AI green `#1B5E3F` (not indigo `#4F46E5`).

**Rationale:** Flow AI is standardizing on green as the official brand color (confirmed via `docs/ux-ui-spec/brand-palette.md`). All new clients should inherit this default unless they explicitly customize.

**User Story:**
> As a new Flow AI client onboarded after 2 May 2026, I want my widget to display in Flow AI green by default, so that my widget visually signals "powered by Flow AI" and aligns with the platform's brand identity.

**Acceptance Criteria:**
- [ ] **Given** the `clients` table has a new row with `widget_primary_color = '#1B5E3F'` (default value)  
      **When** a customer visits the client's website and loads the widget  
      **Then** the widget button background is `#1B5E3F`
- [ ] **Given** the `clients` table has a new row with `widget_primary_color = '#1B5E3F'`  
      **When** the widget opens  
      **Then** the widget header background is `#1B5E3F`
- [ ] **Given** no client has explicitly set a custom color  
      **When** the Supabase migration runs  
      **Then** all new rows default to `#1B5E3F`

---

## 3. Per-Client Customization

### FR-02: Per-Client Color Customization

**Requirement:** Each client can set a custom `widget_primary_color` in the `clients` table. The widget JS served for that client must dynamically apply that color to all brand-controlled surfaces.

**User Story:**
> As a Flow AI client with an established brand identity, I want to set my widget's primary color to match my website's color scheme, so that the widget looks native to my site instead of a third-party plugin.

**Surfaces Affected:**
- Widget button background (floating launcher)
- Widget header background
- Send button (message input)
- User message bubble background (messages sent by the customer)
- "Start Chat" button (before first message sent)
- Hover states (all interactive elements — darken primary by ~10%)

**Acceptance Criteria:**
- [ ] **Given** HeyAircon sets `widget_primary_color = '#FF6B35'` (custom orange) in the `clients` table  
      **When** a customer visits HeyAircon's website and loads the widget  
      **Then** the widget button background is `#FF6B35`
- [ ] **Given** HeyAircon sets `widget_primary_color = '#FF6B35'`  
      **When** the widget opens and the customer sends a message  
      **Then** the customer's message bubble background is `#FF6B35`
- [ ] **Given** HeyAircon sets `widget_primary_color = '#FF6B35'`  
      **When** a customer hovers over the send button  
      **Then** the send button background darkens to approximately `#E65F2F` (10% darker)
- [ ] **Given** a client updates `widget_primary_color` from `#FF6B35` to `#00AA66` in Supabase  
      **When** a customer refreshes the widget page within 5 minutes  
      **Then** the widget reflects the new color `#00AA66` without requiring a Railway deployment
- [ ] **Given** a client sets an invalid hex color (e.g., `'blue'`, `'#ZZZ'`, or `NULL`)  
      **When** the widget serves  
      **Then** the widget falls back to the default `#1B5E3F` and logs a warning

### FR-03: Per-Client Button Icon Customization

**Requirement:** Add a `widget_button_icon` column to the `clients` table (TEXT, default '💬', max 4 characters). Each client can set any emoji or short text as the floating button icon.

**User Story:**
> As a Flow AI client, I want to customize the widget button icon to match my service category (e.g., 🛠️ for repairs, 🏠 for home services, 📅 for booking-focused services), so that the widget visually signals its purpose before customers open it.

**Acceptance Criteria:**
- [ ] **Given** the `widget_button_icon` column exists in the `clients` table with default value '💬'  
      **When** a new client is onboarded  
      **Then** their widget button displays '💬' unless explicitly customized
- [ ] **Given** HeyAircon sets `widget_button_icon = '🛠️'` in the `clients` table  
      **When** a customer visits HeyAircon's website  
      **Then** the floating widget button displays '🛠️' instead of '💬'
- [ ] **Given** a client sets `widget_button_icon = 'HELP'` (4 characters)  
      **When** the widget serves  
      **Then** the button displays 'HELP'
- [ ] **Given** a client sets `widget_button_icon = 'CONTACT'` (7 characters, exceeds max)  
      **When** the widget serves  
      **Then** the button truncates to 'CONT' (first 4 characters) and logs a warning
- [ ] **Given** a client sets `widget_button_icon = NULL` or `''` (empty string)  
      **When** the widget serves  
      **Then** the button falls back to '💬'

---

## 4. Technical Implementation Pattern

### FR-04: Injection at Serve Time

**Requirement:** The Railway engine injects `window.FLOWAI_PRIMARY_COLOR` and `window.FLOWAI_BUTTON_ICON` at the top of the served widget JS file. The widget reads these global variables instead of hardcoded CSS or HTML values.

**Rationale:** This pattern is already proven with `window.FLOWAI_CLIENT_ID`. Keeps the widget JS stateless and cacheable while allowing per-client configuration.

**Implementation Details:**
- The `/widget.js?client_id={client_id}` endpoint reads the `clients` table row for `{client_id}`
- Injects the following at the top of `widget.js` before serving:
  ```javascript
  window.FLOWAI_CLIENT_ID = 'hey-aircon';
  window.FLOWAI_PRIMARY_COLOR = '#1B5E3F';
  window.FLOWAI_BUTTON_ICON = '💬';
  ```
- The widget's CSS engine reads `window.FLOWAI_PRIMARY_COLOR` and applies it to all brand surfaces
- The widget's HTML builder reads `window.FLOWAI_BUTTON_ICON` and injects it into the button element

**Acceptance Criteria:**
- [ ] **Given** the widget serves for `client_id=hey-aircon` with `widget_primary_color='#00AA66'` and `widget_button_icon='🏠'`  
      **When** the browser executes the widget JS  
      **Then** `window.FLOWAI_PRIMARY_COLOR === '#00AA66'` and `window.FLOWAI_BUTTON_ICON === '🏠'`
- [ ] **Given** the widget serves without a `client_id` query parameter (invalid request)  
      **When** the Railway endpoint processes the request  
      **Then** the response is HTTP 400 with error message: "client_id is required"
- [ ] **Given** the widget serves for a `client_id` that does not exist in the `clients` table  
      **When** the Railway endpoint processes the request  
      **Then** the response is HTTP 404 with error message: "Client not found"

---

## 5. Data Migration & Backward Compatibility

### FR-05: Backward Compatibility

**Requirement:** Existing clients (e.g., HeyAircon) who have not explicitly set custom values must experience zero breaking changes. The widget falls back to safe defaults if columns are `NULL` or missing.

**User Story:**
> As HeyAircon (an existing client from before this feature), I want my widget to continue working without interruption when this feature deploys, even though I haven't configured the new fields yet.

**Acceptance Criteria:**
- [ ] **Given** HeyAircon's row has `widget_button_icon = NULL` (column exists but not populated)  
      **When** the widget serves  
      **Then** the button displays '💬' (default fallback)
- [ ] **Given** HeyAircon's row has `widget_primary_color = NULL`  
      **When** the widget serves  
      **Then** all brand surfaces use `#1B5E3F` (default fallback)
- [ ] **Given** HeyAircon's row still has the legacy value `widget_primary_color = '#4F46E5'` (old indigo default)  
      **When** the Supabase migration runs  
      **Then** the value is automatically updated to `#1B5E3F` (migrated to new default)
- [ ] **Given** any existing client has explicitly customized `widget_primary_color` to a non-default value (e.g., `'#FF0000'`)  
      **When** the Supabase migration runs  
      **Then** the custom value is preserved unchanged

### FR-06: Supabase Migration

**Requirement:** A new migration (009) must execute three atomic operations:
1. Add `widget_button_icon` column (TEXT, default '💬', nullable)
2. Update the default value for `widget_primary_color` from `'#4F46E5'` to `'#1B5E3F'`
3. Backfill all existing rows where `widget_primary_color = '#4F46E5'` to `'#1B5E3F'` (assumes the legacy default was never intentionally chosen)

**Migration SQL Pseudo-code:**
```sql
-- Add button icon column
ALTER TABLE clients ADD COLUMN widget_button_icon TEXT DEFAULT '💬';

-- Update the default for new rows
ALTER TABLE clients ALTER COLUMN widget_primary_color SET DEFAULT '#1B5E3F';

-- Backfill legacy default to new default
UPDATE clients SET widget_primary_color = '#1B5E3F' WHERE widget_primary_color = '#4F46E5';
```

**Acceptance Criteria:**
- [ ] **Given** the migration runs against a production database with 3 clients  
      **When** the migration completes successfully  
      **Then** all 3 rows have a `widget_button_icon` column with value '💬'
- [ ] **Given** the migration runs against a database where HeyAircon has `widget_primary_color = '#4F46E5'`  
      **When** the migration completes  
      **Then** HeyAircon's row has `widget_primary_color = '#1B5E3F'`
- [ ] **Given** the migration runs against a database where Client B has `widget_primary_color = '#FF0000'` (custom)  
      **When** the migration completes  
      **Then** Client B's row still has `widget_primary_color = '#FF0000'` (unchanged)
- [ ] **Given** a new client is created after the migration  
      **When** the INSERT statement does not specify `widget_primary_color` or `widget_button_icon`  
      **Then** the row defaults to `widget_primary_color = '#1B5E3F'` and `widget_button_icon = '💬'`

---

## 6. Out of Scope (Phase 2 or Later)

The following are explicitly excluded from this requirements document:

| Item | Reason |
|------|--------|
| Full theme builder UI in CRM | Phase 2 dashboard feature — requires visual color picker and live preview |
| Font family customization | Not a brand differentiation priority; adds complexity to serve-time injection |
| Widget position customization (bottom-left vs. bottom-right) | Separate feature — affects embed script, not theming |
| Dark mode / light mode switching | Requires redesigning the entire widget CSS architecture |
| Secondary color palette (accent colors beyond primary) | Adds complexity without clear client demand; wait for Phase 2 |
| Custom button shape (circle vs. rounded square vs. square) | Low priority — all clients accept the current button shape |

---

## 7. Dependencies & Integration Points

| System | Integration Point | Impact |
|--------|------------------|--------|
| Supabase `clients` table | Reads `widget_primary_color` and `widget_button_icon` at widget serve time | Must query on every widget serve (or implement 5-min cache) |
| Railway widget serve endpoint | `/widget.js?client_id={id}` reads `clients` row and injects globals | Adds 1 database query per widget serve request |
| Client website embed script | No changes — existing `<script>` tags continue working | Zero client-side action required |
| Widget JS (`widget.js`) | Refactor to read `window.FLOWAI_PRIMARY_COLOR` and `window.FLOWAI_BUTTON_ICON` instead of hardcoded values | Replace all CSS hex values and button innerHTML with dynamic reads |

---

## 8. Success Metrics (Post-Launch)

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **Adoption rate** | 50% of clients customize color or icon within 30 days of feature launch | Count rows where `widget_primary_color != '#1B5E3F'` OR `widget_button_icon != '💬'` |
| **Zero breaking changes** | No client reports widget rendering issues after deploy | Support tickets tagged "widget-theming" with severity "broken" = 0 |
| **Performance impact** | Widget serve latency increases by < 50ms (p95) | Compare pre-deploy vs. post-deploy Railway metrics for `/widget.js` endpoint |

---

## 9. Open Questions for Founder

1. **Color validation:** Should the engine reject invalid hex colors at write time (Supabase trigger) or at serve time (widget endpoint)? Current spec assumes serve-time validation with fallback.
2. **Button icon character limit:** Is 4 characters sufficient, or should we allow up to 10 for short text labels like "CONTACT" or "BOOK NOW"?
3. **Cache strategy:** Should the widget endpoint cache `clients` table lookups (5-min TTL) to reduce Supabase query load, or is per-request querying acceptable at current scale?

---

**End of Requirements Document**

---

**Next Steps:**
1. Founder reviews and approves this requirements document
2. Upon approval, hand off to `@ux-ui-designer` (if mockups needed) or directly to `@software-architect` to design the implementation
3. `@software-architect` produces architecture design in `docs/architecture/widget_theming.md`
4. `@sdet-engineer` creates worktree, writes test plan, dispatches implementation to `@software-engineer`
