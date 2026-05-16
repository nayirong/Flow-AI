-- Migration 012: AI Schedule & Business Hours
-- Adds configurable time windows for AI operational hours and business hours context.

-- Add columns (all nullable except timezone)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS ai_active_start_time TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS ai_active_end_time   TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_start_time TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS business_end_time   TIME DEFAULT NULL;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';

-- Add comments for Supabase Studio
COMMENT ON COLUMN clients.ai_active_start_time IS 'Start of AI active window in 24hr format (e.g., 18:00:00 for 6pm). Leave NULL for 24/7 active. Times interpreted in timezone column.';
COMMENT ON COLUMN clients.ai_active_end_time IS 'End of AI active window in 24hr format (e.g., 09:00:00 for 9am). Leave NULL for 24/7 active. If end < start, window spans midnight (overnight).';
COMMENT ON COLUMN clients.business_start_time IS 'Start of business hours in 24hr format (e.g., 09:00:00). Used for escalation message context only. Leave NULL if not needed.';
COMMENT ON COLUMN clients.business_end_time IS 'End of business hours in 24hr format (e.g., 18:00:00). Used for escalation message context only. Leave NULL if not needed.';
COMMENT ON COLUMN clients.timezone IS 'IANA timezone string (e.g., Asia/Singapore) — applies to all schedule times for this client. Defaults to UTC if not set.';

-- Constraints: both-or-neither for each pair
ALTER TABLE clients ADD CONSTRAINT ai_hours_both_or_neither
    CHECK (
        (ai_active_start_time IS NULL AND ai_active_end_time IS NULL)
        OR
        (ai_active_start_time IS NOT NULL AND ai_active_end_time IS NOT NULL)
    );

ALTER TABLE clients ADD CONSTRAINT business_hours_both_or_neither
    CHECK (
        (business_start_time IS NULL AND business_end_time IS NULL)
        OR
        (business_start_time IS NOT NULL AND business_end_time IS NOT NULL)
    );

-- Set HeyAircon defaults
UPDATE clients
SET
    ai_active_start_time = '18:00:00',
    ai_active_end_time   = '09:00:00',
    business_start_time  = '09:00:00',
    business_end_time    = '18:00:00',
    timezone             = 'Asia/Singapore'
WHERE client_id = 'hey-aircon';

-- Rollback (if needed):
-- ALTER TABLE clients DROP CONSTRAINT IF EXISTS business_hours_both_or_neither;
-- ALTER TABLE clients DROP CONSTRAINT IF EXISTS ai_hours_both_or_neither;
-- ALTER TABLE clients DROP COLUMN IF EXISTS timezone;
-- ALTER TABLE clients DROP COLUMN IF EXISTS business_end_time;
-- ALTER TABLE clients DROP COLUMN IF EXISTS business_start_time;
-- ALTER TABLE clients DROP COLUMN IF EXISTS ai_active_end_time;
-- ALTER TABLE clients DROP COLUMN IF EXISTS ai_active_start_time;
