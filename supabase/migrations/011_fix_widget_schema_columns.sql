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

-- ── policies: add policy_text and sort_order used by context_builder ──────────
-- The base policies table (migration 008) was created with 'key' and 'value'
-- columns. context_builder.py queries 'policy_text' and 'sort_order'.
ALTER TABLE policies ADD COLUMN IF NOT EXISTS policy_text TEXT;
ALTER TABLE policies ADD COLUMN IF NOT EXISTS sort_order  INTEGER NOT NULL DEFAULT 0;

-- ── interactions_log: drop NOT NULL on 'role' ─────────────────────────────────
-- Widget inserts use message_text + direction and do not set the WhatsApp-era
-- 'role' column. Must be nullable for widget rows to insert cleanly.
ALTER TABLE interactions_log ALTER COLUMN role DROP NOT NULL;
