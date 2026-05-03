-- Migration 011: Fix widget schema column gaps
-- Adds columns required by widget_handler.py and context_builder.py that were
-- missing from the base schema created in migration 008.
--
-- Run on: shared Flow AI Supabase (nayhqstuupdsqpltseof)
-- Safe to re-run (all ADD COLUMN IF NOT EXISTS)

-- ── interactions_log: add widget-specific columns ─────────────────────────────
-- message_text replaces the WhatsApp-era 'content' column for widget messages.
-- direction distinguishes inbound (user) from outbound (agent) messages.
ALTER TABLE interactions_log ADD COLUMN IF NOT EXISTS message_text TEXT;
ALTER TABLE interactions_log ADD COLUMN IF NOT EXISTS direction    TEXT;

-- ── config: add sort_order for deterministic prompt section ordering ───────────
ALTER TABLE config ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
