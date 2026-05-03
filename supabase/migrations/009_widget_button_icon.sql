-- Migration 009: Widget Button Icon
-- Adds per-client widget button icon customization
-- Run on: shared Flow AI Supabase

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS widget_button_icon TEXT NOT NULL DEFAULT '💬';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'widget_button_icon_length'
          AND conrelid = 'clients'::regclass
    ) THEN
        ALTER TABLE clients
            ADD CONSTRAINT widget_button_icon_length CHECK (char_length(widget_button_icon) <= 4);
    END IF;
END $$;

COMMENT ON COLUMN clients.widget_button_icon IS 'Emoji or short text for floating widget button (max 4 chars, default 💬)';
