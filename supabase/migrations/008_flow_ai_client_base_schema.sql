-- Migration 008: Base per-client schema for flow-ai client on shared Supabase
-- Run this on the shared Flow AI Supabase BEFORE running 007_widget_schema.sql
--
-- Context: Supabase free tier = 2 projects max. The shared Flow AI Supabase
-- (which holds the `clients` platform table) doubles as the per-client DB for
-- the `flow-ai` pilot client. This migration creates the per-client tables that
-- would normally exist in a dedicated per-client project.
--
-- Run order: 008 → then re-run 007 (all 007 statements are idempotent)

-- ── customers ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id                   BIGSERIAL PRIMARY KEY,
    phone_number         TEXT UNIQUE NOT NULL,
    name                 TEXT,
    total_bookings       INTEGER NOT NULL DEFAULT 0,
    last_interaction_at  TIMESTAMPTZ,
    escalation_flag      BOOLEAN NOT NULL DEFAULT FALSE,
    escalation_notified  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone_number);

-- ── config (services / pricing) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS config (
    id         BIGSERIAL PRIMARY KEY,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_config_key ON config(key);

-- ── policies ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS policies (
    id         BIGSERIAL PRIMARY KEY,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_policies_key ON policies(key);

-- ── interactions_log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS interactions_log (
    id           BIGSERIAL PRIMARY KEY,
    phone_number TEXT,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interactions_log_phone ON interactions_log(phone_number, created_at DESC);

-- ── bookings ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    id           BIGSERIAL PRIMARY KEY,
    booking_id   TEXT UNIQUE NOT NULL,
    phone_number TEXT NOT NULL,
    service      TEXT,
    address      TEXT,
    scheduled_at TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bookings_phone   ON bookings(phone_number);
CREATE INDEX IF NOT EXISTS idx_bookings_status  ON bookings(status);
CREATE INDEX IF NOT EXISTS idx_bookings_booking_id ON bookings(booking_id);

-- ── escalation_tracking (from migration 003) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS escalation_tracking (
    id                SERIAL PRIMARY KEY,
    phone_number      TEXT NOT NULL,
    alert_msg_id      TEXT,
    escalated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    escalation_reason TEXT,
    resolved_at       TIMESTAMPTZ,
    resolved_by       TEXT
);

CREATE INDEX IF NOT EXISTS idx_escalation_tracking_alert_msg
    ON escalation_tracking(alert_msg_id)
    WHERE alert_msg_id IS NOT NULL AND resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_escalation_tracking_pending
    ON escalation_tracking(resolved_at)
    WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_escalation_tracking_phone
    ON escalation_tracking(phone_number);

-- ── scheduler_runs (from migration 005) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS scheduler_runs (
    id                    BIGSERIAL PRIMARY KEY,
    client_id             TEXT NOT NULL,
    run_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bookings_t2h          INT NOT NULL DEFAULT 0,
    bookings_t24h         INT NOT NULL DEFAULT 0,
    bookings_abandoned    INT NOT NULL DEFAULT 0,
    messages_sent_failed  INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_client_id ON scheduler_runs(client_id);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_run_at    ON scheduler_runs(run_at DESC);
