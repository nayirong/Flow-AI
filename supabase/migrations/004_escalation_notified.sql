-- Migration 004: Add escalation_notified to customers table
--
-- Controls whether the holding reply has already been sent for the current
-- escalation. When True, subsequent messages from an escalated customer are
-- silently dropped (no reply). Resets to False when escalation is cleared.
--
-- Behaviour:
--   escalation_flag=True,  escalation_notified=False → send holding reply, flip to True
--   escalation_flag=True,  escalation_notified=True  → silent drop
--   escalation_flag=False, escalation_notified=False → normal agent flow

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS escalation_notified BOOLEAN NOT NULL DEFAULT FALSE;

-- Rollback:
-- ALTER TABLE customers DROP COLUMN IF EXISTS escalation_notified;
