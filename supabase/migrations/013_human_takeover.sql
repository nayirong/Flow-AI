-- Migration 013: Human Takeover Detection
-- Adds takeover state tracking and audit trail for manual human agent takeovers.

-- ── Add takeover state columns to customers table ─────────────────────────────
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_flag BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_by TEXT DEFAULT NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS takeover_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_ai_alert_msg_id TEXT DEFAULT NULL;

-- ── Create takeover_tracking audit table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS takeover_tracking (
    id SERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    alert_msg_id TEXT,
    takeover_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    takeover_by TEXT,
    command_type TEXT NOT NULL,
    released_at TIMESTAMPTZ DEFAULT NULL,
    released_by TEXT DEFAULT NULL,
    release_command_type TEXT DEFAULT NULL
);

-- ── Indexes for takeover_tracking ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_takeover_tracking_alert_msg_id 
    ON takeover_tracking(alert_msg_id) 
    WHERE released_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_takeover_tracking_phone_active 
    ON takeover_tracking(phone_number, takeover_at) 
    WHERE released_at IS NULL;

-- ── Index on customers table for takeover gate ────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_customers_takeover_flag 
    ON customers(phone_number) 
    WHERE takeover_flag = TRUE;

-- ── Add column comments for Supabase Studio ───────────────────────────────────
COMMENT ON COLUMN customers.takeover_flag IS 'TRUE if human agent has manually taken over this conversation. AI is paused until released.';
COMMENT ON COLUMN customers.takeover_by IS 'Phone number of human agent who initiated takeover.';
COMMENT ON COLUMN customers.takeover_at IS 'Timestamp when takeover was initiated.';
COMMENT ON COLUMN customers.last_ai_alert_msg_id IS 'wamid of the most recent conversation alert sent to human_agent_number for this customer. Used for reply-to-message takeover detection.';

COMMENT ON TABLE takeover_tracking IS 'Audit trail for manual human agent takeovers. Tracks when human took over, when they released, and how (manual or timeout).';
COMMENT ON COLUMN takeover_tracking.alert_msg_id IS 'wamid of the conversation alert sent to human_agent_number. Used for reply-to-message takeover detection.';
COMMENT ON COLUMN takeover_tracking.command_type IS 'How takeover was initiated: reply_to_alert or auto_timeout.';
COMMENT ON COLUMN takeover_tracking.release_command_type IS 'How takeover was released: manual_done or auto_resume.';

-- Rollback (if needed):
-- DROP INDEX IF EXISTS idx_customers_takeover_flag;
-- DROP INDEX IF EXISTS idx_takeover_tracking_phone_active;
-- DROP INDEX IF EXISTS idx_takeover_tracking_alert_msg_id;
-- DROP TABLE IF EXISTS takeover_tracking;
-- ALTER TABLE customers DROP COLUMN IF EXISTS last_ai_alert_msg_id;
-- ALTER TABLE customers DROP COLUMN IF EXISTS takeover_at;
-- ALTER TABLE customers DROP COLUMN IF EXISTS takeover_by;
-- ALTER TABLE customers DROP COLUMN IF EXISTS takeover_flag;
