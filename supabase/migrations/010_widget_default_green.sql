-- Migration 010: Widget Default Color — Flow AI Green
-- Changes widget_primary_color default from indigo to Flow AI brand green
-- Run on: shared Flow AI Supabase

ALTER TABLE clients
    ALTER COLUMN widget_primary_color SET DEFAULT '#1B5E3F';

-- Backfill existing rows that still have the old indigo default
UPDATE clients
    SET widget_primary_color = '#1B5E3F'
    WHERE widget_primary_color = '#4F46E5';

COMMENT ON COLUMN clients.widget_primary_color IS 'Primary brand color for widget (hex, default Flow AI green #1B5E3F)';
