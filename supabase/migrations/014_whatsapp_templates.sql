-- Migration 014: WhatsApp Message Template fields
-- Adds 5 optional template name columns to the shared `clients` table.
-- These columns remain NULL until Meta approves the templates and Phase 3 activation SQL is run.
-- NULL = free-text fallback (existing behavior). Non-NULL = template send (bypasses 24h window).
-- Applies to: shared flowai-platform Supabase DB (clients table)

ALTER TABLE clients
  ADD COLUMN IF NOT EXISTS template_escalation_alert    TEXT,
  ADD COLUMN IF NOT EXISTS template_conversation_alert  TEXT,
  ADD COLUMN IF NOT EXISTS template_takeover_forward    TEXT,
  ADD COLUMN IF NOT EXISTS template_takeover_confirmation TEXT,
  ADD COLUMN IF NOT EXISTS template_auto_resume         TEXT;

-- ─── PHASE 3: Run this AFTER Meta approves all 5 templates ───────────────────
-- Do NOT run this during initial migration — templates must be approved first.
-- Check approval status in Meta Business Manager → WhatsApp Manager → Message Templates.
--
-- UPDATE clients
-- SET
--   template_escalation_alert     = 'escalation_alert',
--   template_conversation_alert   = 'conversation_alert',
--   template_takeover_forward     = 'takeover_new_message',
--   template_takeover_confirmation = 'takeover_confirmation',
--   template_auto_resume          = 'takeover_auto_resume'
-- WHERE client_id = 'hey-aircon';
-- ─────────────────────────────────────────────────────────────────────────────
