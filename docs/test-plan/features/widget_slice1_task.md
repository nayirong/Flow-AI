# Chat Widget — Slice 1 Task Document

**Target Agent:** `@software-engineer`  
**Worktree:** `.worktree/widget-01-schema`  
**Status:** Ready for Implementation  
**Date:** 2026-04-30  

---

## Goal

Add widget Supabase schema migration and widget configuration fields to `ClientConfig`.

---

## Prerequisite

**Baseline:** `main` (no prerequisites — Slice 1 branches directly from main)

---

## Success Check

**Founder-visible success condition:** Schema migration applied to Flow AI's Supabase; `ClientConfig` can load widget fields from `clients` table.

**Proof metric:** Migration SQL executes without error; `test_client_config_loads_widget_fields_from_supabase()` passes.

**Proxy metrics:** ClientConfig dataclass has 6 new widget fields; Supabase `clients` table has 6 new columns.

---

## Files to Create

### 1. `supabase/migrations/007_widget_schema.sql`

**Full SQL migration** — ALL schema changes from architecture document §2:

```sql
-- ========================================================================
-- Migration 007: Widget Schema
-- Purpose: Add widget channel support (sessions, visitors, schema changes)
-- Date: 2026-04-30
-- ========================================================================

-- ────────────────────────────────────────────────────────────────────────
-- Table: sessions
-- Purpose: Store all widget sessions (anonymous and identified)
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expired_at TIMESTAMPTZ,
    user_agent TEXT
);

-- Note: client_id FK constraint references shared Supabase clients table.
-- For per-client Supabase (current architecture), client_id is validated
-- at application layer (not enforced by FK in migration).

CREATE INDEX IF NOT EXISTS idx_sessions_client_id ON sessions(client_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(last_active_at) WHERE expired_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_expired ON sessions(expired_at) WHERE expired_at IS NOT NULL;

-- ────────────────────────────────────────────────────────────────────────
-- Table: visitors
-- Purpose: Store identity data for visitors who submit pre-chat form
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS visitors (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    client_id TEXT NOT NULL,
    name TEXT,
    email TEXT,
    phone TEXT,
    customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,
    escalation_flag BOOLEAN NOT NULL DEFAULT FALSE,
    escalation_reason TEXT,
    escalated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_visitors_session_id ON visitors(session_id);
CREATE INDEX IF NOT EXISTS idx_visitors_email ON visitors(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_visitors_customer_id ON visitors(customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_visitors_escalation ON visitors(session_id, escalation_flag);

-- ────────────────────────────────────────────────────────────────────────
-- Schema Changes: interactions_log
-- Purpose: Add widget channel support (channel, session_id columns)
-- ────────────────────────────────────────────────────────────────────────

-- Add channel column (default 'whatsapp' for backward compatibility)
ALTER TABLE interactions_log 
ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'whatsapp';

-- Add session_id column (NULL for WhatsApp messages, populated for widget)
ALTER TABLE interactions_log 
ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL;

-- Make phone_number nullable (widget messages have no phone if visitor is anonymous)
ALTER TABLE interactions_log 
ALTER COLUMN phone_number DROP NOT NULL;

-- Indexes for widget queries
CREATE INDEX IF NOT EXISTS idx_interactions_log_session_id ON interactions_log(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_log_customer_channel ON interactions_log(phone_number, channel, created_at DESC) 
WHERE phone_number IS NOT NULL;

-- ────────────────────────────────────────────────────────────────────────
-- Schema Changes: bookings
-- Purpose: Track which channel the booking came from
-- ────────────────────────────────────────────────────────────────────────

-- Add channel column (default 'whatsapp')
ALTER TABLE bookings 
ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'whatsapp';

-- Add session_id column (NULL for WhatsApp bookings, populated for widget)
ALTER TABLE bookings 
ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL;

-- Index for widget booking queries
CREATE INDEX IF NOT EXISTS idx_bookings_session_id ON bookings(session_id) WHERE session_id IS NOT NULL;

-- ────────────────────────────────────────────────────────────────────────
-- Schema Changes: clients (Shared Supabase)
-- Purpose: Add widget configuration columns
-- NOTE: This must be applied to the SHARED Supabase clients table manually.
-- Do NOT apply this section to per-client Supabase databases.
-- ────────────────────────────────────────────────────────────────────────

-- Widget feature flag
ALTER TABLE clients 
ADD COLUMN IF NOT EXISTS widget_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- Widget branding
ALTER TABLE clients 
ADD COLUMN IF NOT EXISTS widget_primary_color TEXT DEFAULT '#4F46E5';

ALTER TABLE clients 
ADD COLUMN IF NOT EXISTS widget_agent_name TEXT DEFAULT 'Assistant';

ALTER TABLE clients 
ADD COLUMN IF NOT EXISTS widget_welcome_message TEXT DEFAULT 'Hi! How can I help you today?';

-- CORS origin whitelist (comma-separated domains)
ALTER TABLE clients 
ADD COLUMN IF NOT EXISTS widget_allowed_origins TEXT;

-- Session TTL (minutes of inactivity before expiry)
ALTER TABLE clients 
ADD COLUMN IF NOT EXISTS widget_session_ttl_minutes INTEGER NOT NULL DEFAULT 30;

-- ========================================================================
-- End of Migration 007
-- ========================================================================
```

**Hard constraints:**
- Use `IF NOT EXISTS` / `IF EXISTS` for idempotency (migration can be run multiple times without error)
- All new columns in `clients` table MUST have DEFAULT values — existing client rows must not break
- `interactions_log.phone_number` change: `ALTER COLUMN phone_number DROP NOT NULL` — do NOT DROP the column or change its type
- `sessions.client_id` references the `clients` table but FK constraint NOT enforced in migration (per-client Supabase does not have direct access to shared `clients` table — FK validated at application layer)

---

### 2. `engine/config/client_config.py`

**Add 6 widget fields to `ClientConfig` dataclass:**

```python
@dataclass
class ClientConfig:
    """
    Configuration for a single client, loaded from Supabase + env vars.
    
    Attributes:
        client_id: Unique client identifier (e.g., "hey-aircon")
        display_name: Human-readable client name
        meta_phone_number_id: Meta WhatsApp phone number ID
        meta_verify_token: Meta webhook verification token
        meta_whatsapp_token: Meta WhatsApp API token (from env)
        human_agent_number: Phone number for escalation
        google_calendar_id: Google Calendar ID for bookings
        google_calendar_creds: Google Calendar service account credentials (from env)
        supabase_url: Client's Supabase project URL (from env)
        supabase_service_key: Client's Supabase service key (from env)
        timezone: Client's timezone
        is_active: Whether client is active
        sheets_sync_enabled: Whether Google Sheets sync is enabled
        sheets_spreadsheet_id: Google Sheets spreadsheet ID
        sheets_service_account_creds: Google Sheets service account credentials
        widget_enabled: Widget feature flag (NEW)
        widget_primary_color: Widget button background color (NEW)
        widget_agent_name: Agent name displayed in widget (NEW)
        widget_welcome_message: First message displayed in chat window (NEW)
        widget_allowed_origins: Comma-separated CORS origin whitelist (NEW)
        widget_session_ttl_minutes: Session TTL in minutes (NEW)
    """
    client_id: str
    display_name: str
    meta_phone_number_id: str
    meta_verify_token: str
    meta_whatsapp_token: str
    human_agent_number: str
    google_calendar_id: str | None
    google_calendar_creds: dict
    supabase_url: str
    supabase_service_key: str
    anthropic_api_key: str
    openai_api_key: str
    timezone: str
    is_active: bool
    sheets_sync_enabled: bool = False
    sheets_spreadsheet_id: str | None = None
    sheets_service_account_creds: dict | None = None
    # Widget configuration (NEW — Phase 1)
    widget_enabled: bool = False
    widget_primary_color: str = '#4F46E5'
    widget_agent_name: str = 'Assistant'
    widget_welcome_message: str = 'Hi! How can I help you today?'
    widget_allowed_origins: str = ''
    widget_session_ttl_minutes: int = 30
```

**Update `load_client_config()` function** to read widget fields from Supabase `clients` table row:

Find this section in `load_client_config()`:

```python
    # 4. Construct ClientConfig
    config = ClientConfig(
        client_id=row["client_id"],
        display_name=row.get("display_name", ""),
        meta_phone_number_id=row["meta_phone_number_id"],
        meta_verify_token=row["meta_verify_token"],
        meta_whatsapp_token=meta_whatsapp_token,
        human_agent_number=row["human_agent_number"],
        google_calendar_id=row.get("google_calendar_id"),
        google_calendar_creds=google_calendar_creds,
        supabase_url=supabase_url,
        supabase_service_key=supabase_service_key,
        anthropic_api_key=anthropic_api_key,
        openai_api_key=openai_api_key,
        timezone=row.get("timezone", "Asia/Singapore"),
        is_active=row["is_active"],
        sheets_sync_enabled=row.get("sheets_sync_enabled", False),
```

**Add these 6 lines after `sheets_sync_enabled`:**

```python
        sheets_sync_enabled=row.get("sheets_sync_enabled", False),
        sheets_spreadsheet_id=row.get("sheets_spreadsheet_id"),
        sheets_service_account_creds=sheets_service_account_creds,
        # Widget configuration (NEW — Phase 1)
        widget_enabled=row.get("widget_enabled", False),
        widget_primary_color=row.get("widget_primary_color", "#4F46E5"),
        widget_agent_name=row.get("widget_agent_name", "Assistant"),
        widget_welcome_message=row.get("widget_welcome_message", "Hi! How can I help you today?"),
        widget_allowed_origins=row.get("widget_allowed_origins", ""),
        widget_session_ttl_minutes=row.get("widget_session_ttl_minutes", 30),
```

**Hard constraints:**
- Do NOT change any existing ClientConfig field names or types — append only
- All 6 widget fields MUST have default values in the dataclass (for clients where widget is not enabled yet)
- `widget_allowed_origins` stored as plain TEXT (comma-separated) in Supabase — no JSON, no array type

---

### 3. `engine/tests/unit/test_widget_schema.py`

**NEW test file** — 3 test functions:

```python
"""
Unit tests for widget schema and ClientConfig widget fields.
"""
import pytest
from engine.config.client_config import ClientConfig, load_client_config


def test_client_config_has_widget_fields():
    """Verify ClientConfig dataclass has all 6 widget fields with correct types and defaults."""
    # Assert fields exist
    assert hasattr(ClientConfig, "widget_enabled")
    assert hasattr(ClientConfig, "widget_primary_color")
    assert hasattr(ClientConfig, "widget_agent_name")
    assert hasattr(ClientConfig, "widget_welcome_message")
    assert hasattr(ClientConfig, "widget_allowed_origins")
    assert hasattr(ClientConfig, "widget_session_ttl_minutes")
    
    # Assert default values
    from dataclasses import fields
    field_defaults = {f.name: f.default for f in fields(ClientConfig) if f.default is not f.default_factory}
    
    assert field_defaults["widget_enabled"] is False
    assert field_defaults["widget_primary_color"] == "#4F46E5"
    assert field_defaults["widget_agent_name"] == "Assistant"
    assert field_defaults["widget_welcome_message"] == "Hi! How can I help you today?"
    assert field_defaults["widget_allowed_origins"] == ""
    assert field_defaults["widget_session_ttl_minutes"] == 30


def test_widget_enabled_default_false():
    """Verify widget_enabled defaults to False."""
    from dataclasses import fields
    widget_enabled_field = next(f for f in fields(ClientConfig) if f.name == "widget_enabled")
    assert widget_enabled_field.default is False


@pytest.mark.asyncio
async def test_client_config_loads_widget_fields_from_supabase(
    mock_env_vars,
    mock_supabase_client,
    clear_client_config_cache
):
    """Verify load_client_config() reads all 6 widget fields from Supabase clients table."""
    # Arrange — mock Supabase response with widget fields
    mock_supabase_clients_row = {
        "client_id": "hey-aircon",
        "display_name": "HeyAircon",
        "meta_phone_number_id": "123456789",
        "meta_verify_token": "heyaircon_webhook_2026",
        "human_agent_number": "+6591234567",
        "google_calendar_id": "test@group.calendar.google.com",
        "timezone": "Asia/Singapore",
        "is_active": True,
        # Widget fields (NEW)
        "widget_enabled": True,
        "widget_primary_color": "#FF5733",
        "widget_agent_name": "Kai",
        "widget_welcome_message": "Hi! I'm Kai, your AI assistant.",
        "widget_allowed_origins": "https://getflowai.co,https://www.getflowai.co",
        "widget_session_ttl_minutes": 45,
    }
    
    mock_response = MagicMock()
    mock_response.data = [mock_supabase_clients_row]
    mock_supabase_client.table().select().eq().eq().limit().execute.return_value = mock_response
    
    # Mock get_shared_db to return our mock client
    from unittest.mock import patch, AsyncMock
    with patch("engine.config.client_config.get_shared_db", new_callable=AsyncMock) as mock_get_shared_db:
        mock_get_shared_db.return_value = mock_supabase_client
        
        # Act
        config = await load_client_config("hey-aircon")
    
    # Assert — all 6 widget fields loaded correctly
    assert config.widget_enabled is True
    assert config.widget_primary_color == "#FF5733"
    assert config.widget_agent_name == "Kai"
    assert config.widget_welcome_message == "Hi! I'm Kai, your AI assistant."
    assert config.widget_allowed_origins == "https://getflowai.co,https://www.getflowai.co"
    assert config.widget_session_ttl_minutes == 45
```

**Hard constraints:**
- All 3 test functions MUST pass before Slice 1 is marked ready for review
- Test file MUST import from existing `engine.config.client_config` module — do NOT create new modules
- Use existing test fixtures from `engine/tests/conftest.py` (`mock_env_vars`, `mock_supabase_client`, `clear_client_config_cache`)

---

## Files to Modify

### None

No existing files are modified in Slice 1 (schema and config only).

---

## Hard Constraints

| Constraint | Details |
|------------|---------|
| **No routes, handlers, middleware, or JS in this slice** | Schema and config only — Slice 2 adds API routes |
| **Do NOT change any existing ClientConfig field names or types** | Append only — existing WhatsApp fields must remain unchanged |
| **`widget_allowed_origins` stored as plain TEXT (comma-separated)** | No JSON, no array type — CORS middleware will parse comma-separated string |
| **All new columns in `clients` table must have DEFAULT values** | Existing client rows must not break — `NOT NULL` columns require `DEFAULT` |
| **`sessions` and `visitors` tables go in per-client Supabase** | Same database as `customers`, `bookings`, `interactions_log` |
| **`sessions.client_id` references `clients` table but FK NOT enforced in migration** | Per-client Supabase does not have direct access to shared `clients` table — FK validated at application layer |
| **`interactions_log.phone_number` change: `ALTER COLUMN phone_number DROP NOT NULL`** | Do NOT DROP the column or change its type — only make it nullable |
| **Migration file must be idempotent** | Use `IF NOT EXISTS`, `IF EXISTS`, `ADD COLUMN IF NOT EXISTS` — migration can be run multiple times without error |

---

## Validate (SDET runs these after SE completes)

```bash
# From repository root
python3 -m pytest engine/tests/unit/test_widget_schema.py -v

# Confirm no regressions
python3 -m pytest engine/tests/unit/ -v --tb=short
```

**Expected output:**
```
engine/tests/unit/test_widget_schema.py::test_client_config_has_widget_fields PASSED
engine/tests/unit/test_widget_schema.py::test_widget_enabled_default_false PASSED
engine/tests/unit/test_widget_schema.py::test_client_config_loads_widget_fields_from_supabase PASSED

============ 3 passed in 0.50s ============
```

---

## Commit Requirement

**CRITICAL:** SE must `git add` + `git commit` inside `.worktree/widget-01-schema` before reporting done.

**Commands to run before reporting completion:**
```bash
cd .worktree/widget-01-schema
git add supabase/migrations/007_widget_schema.sql
git add engine/config/client_config.py
git add engine/tests/unit/test_widget_schema.py
git commit -m "Add widget schema migration and ClientConfig widget fields"
git log --oneline -3
```

**The commit MUST appear in `git log` before the work is reported complete.** Passing tests are not a substitute for a commit.

---

## Format Requirement

**Before committing, run the project format command:**

```bash
# Flow AI uses no formatter in Phase 1 — skip this step
# (Future: add `black` or `ruff` when standardized)
```

**For this project, no format command is required.** Proceed directly to `git commit` after tests pass.

---

**End of Slice 1 Task Document**
