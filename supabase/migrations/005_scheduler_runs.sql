-- Migration 005: Scheduler runs tracking table
-- Created: 2026-04-24
-- Purpose: Track follow-up scheduler execution metrics per client

CREATE TABLE IF NOT EXISTS scheduler_runs (
    id BIGSERIAL PRIMARY KEY,
    client_id TEXT NOT NULL,
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bookings_t2h INT NOT NULL DEFAULT 0,
    bookings_t24h INT NOT NULL DEFAULT 0,
    bookings_abandoned INT NOT NULL DEFAULT 0,
    messages_sent_failed INT NOT NULL DEFAULT 0
);

-- Index by client_id for per-client metrics queries
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_client_id ON scheduler_runs (client_id);

-- Index by run_at for time-based queries (most recent runs first)
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_run_at ON scheduler_runs (run_at DESC);
