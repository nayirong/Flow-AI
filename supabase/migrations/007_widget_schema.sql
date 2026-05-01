-- Migration 007: Widget channel schema
-- Adds sessions, visitors tables + schema changes to interactions_log, bookings, clients

-- ── sessions table (per-client Supabase) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expired_at TIMESTAMPTZ,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_client_id ON sessions(client_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(last_active_at) WHERE expired_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_expired ON sessions(expired_at) WHERE expired_at IS NOT NULL;

-- ── visitors table (per-client Supabase) ─────────────────────────────────────
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

-- ── interactions_log schema changes ──────────────────────────────────────────
ALTER TABLE interactions_log ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'whatsapp';
ALTER TABLE interactions_log ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL;
ALTER TABLE interactions_log ALTER COLUMN phone_number DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_interactions_log_session_id ON interactions_log(session_id, created_at DESC);

-- ── bookings schema changes ───────────────────────────────────────────────────
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'whatsapp';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_bookings_session_id ON bookings(session_id);

-- ── clients table widget config (shared Supabase) ────────────────────────────
ALTER TABLE clients ADD COLUMN IF NOT EXISTS widget_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS widget_primary_color TEXT DEFAULT '#4F46E5';
ALTER TABLE clients ADD COLUMN IF NOT EXISTS widget_agent_name TEXT DEFAULT 'Assistant';
ALTER TABLE clients ADD COLUMN IF NOT EXISTS widget_welcome_message TEXT DEFAULT 'Hi! How can I help you today?';
ALTER TABLE clients ADD COLUMN IF NOT EXISTS widget_allowed_origins TEXT DEFAULT '';
ALTER TABLE clients ADD COLUMN IF NOT EXISTS widget_session_ttl_minutes INTEGER NOT NULL DEFAULT 30;
