-- Migration 003: escalation_tracking table
-- Audit trail for all escalations — tracks when triggered, when resolved, and by whom.
--
-- Purpose: Enable human agents to reset escalations via WhatsApp reply-to-message.
-- alert_msg_id is the wamid of the escalation alert sent to the human agent.
-- When a human agent replies to that alert with "done", "resolved", etc., the
-- reset handler looks up the row by alert_msg_id and clears the escalation.

CREATE TABLE IF NOT EXISTS escalation_tracking (
    id              SERIAL PRIMARY KEY,
    phone_number    TEXT NOT NULL,
    alert_msg_id    TEXT,
    escalated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    escalation_reason TEXT,
    resolved_at     TIMESTAMPTZ,
    resolved_by     TEXT
);

-- Index for reply-to-message lookup (only unresolved rows)
CREATE INDEX IF NOT EXISTS idx_escalation_tracking_alert_msg 
  ON escalation_tracking(alert_msg_id) 
  WHERE alert_msg_id IS NOT NULL AND resolved_at IS NULL;

-- Index for pending escalations query
CREATE INDEX IF NOT EXISTS idx_escalation_tracking_pending 
  ON escalation_tracking(resolved_at) 
  WHERE resolved_at IS NULL;

-- Index for customer history lookup
CREATE INDEX IF NOT EXISTS idx_escalation_tracking_phone 
  ON escalation_tracking(phone_number);
