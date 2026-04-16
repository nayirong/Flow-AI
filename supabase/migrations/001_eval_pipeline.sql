-- ============================================================================
-- Flow AI — Eval Supabase Migration 001
-- Project: flow-ai-eval  (separate from client production DBs)
-- Run: Paste this entire file into Supabase Studio SQL Editor → Run
-- ============================================================================

-- ============================================================================
-- Eval Test Cases
-- Stores test case definitions from YAML sync and direct Supabase inserts.
-- One row per test case. YAML files take precedence on test_name conflict.
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_test_cases (
  id SERIAL PRIMARY KEY,
  client_id TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN (
    'intent', 'tool_use', 'escalation', 'safety', 'persona', 'multi_turn', 'context_engineering'
  )),
  test_name TEXT UNIQUE NOT NULL,
  input_message TEXT NOT NULL,
  conversation_history JSONB DEFAULT '[]'::jsonb,
  expected_intent TEXT,
  expected_tool TEXT,
  expected_tool_params JSONB,
  expected_escalation BOOLEAN,
  expected_response_contains TEXT[],
  expected_response_excludes TEXT[],
  safety_check TEXT,
  priority TEXT DEFAULT 'medium' CHECK (priority IN ('critical', 'high', 'medium', 'low')),
  reference_test BOOLEAN DEFAULT FALSE,
  tags TEXT[] DEFAULT '{}',
  enabled BOOLEAN DEFAULT TRUE,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_test_cases_client_id ON eval_test_cases(client_id);
CREATE INDEX IF NOT EXISTS idx_eval_test_cases_category ON eval_test_cases(category);
CREATE INDEX IF NOT EXISTS idx_eval_test_cases_priority ON eval_test_cases(priority);
CREATE INDEX IF NOT EXISTS idx_eval_test_cases_enabled ON eval_test_cases(enabled);
CREATE INDEX IF NOT EXISTS idx_eval_test_cases_tags ON eval_test_cases USING GIN(tags);

-- ============================================================================
-- Eval Results
-- Stores one row per test case per eval run.
-- scorer_results JSONB shape: { "intent": { "passed": true, "score": 1.0 }, ... }
-- run_metadata JSONB shape: { "git_commit", "branch", "llm_model", "triggered_by", ... }
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_results (
  id SERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  test_case_id INT REFERENCES eval_test_cases(id) ON DELETE SET NULL,
  client_id TEXT NOT NULL,
  category TEXT NOT NULL,
  test_name TEXT NOT NULL,
  passed BOOLEAN NOT NULL,
  score FLOAT CHECK (score >= 0.0 AND score <= 1.0),
  agent_response TEXT,
  tool_called TEXT,
  tool_params JSONB,
  escalation_triggered BOOLEAN,
  scorer_results JSONB NOT NULL,
  failure_reason TEXT,
  langfuse_trace_id TEXT,  -- Phase 2
  execution_time_ms INT,
  run_metadata JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_results_run_id ON eval_results(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_client_id ON eval_results(client_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_category ON eval_results(category);
CREATE INDEX IF NOT EXISTS idx_eval_results_created_at ON eval_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_results_test_name ON eval_results(test_name);
-- Composite index for 7-day rolling average queries in regression_detector.py
CREATE INDEX IF NOT EXISTS idx_eval_results_client_category_created
  ON eval_results(client_id, category, created_at DESC);

-- ============================================================================
-- Eval Alerts
-- One row per Telegram alert fired (regression, safety failure, etc.).
-- telegram_sent=FALSE rows can be retried by the alerting system.
-- ============================================================================
CREATE TABLE IF NOT EXISTS eval_alerts (
  id SERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  alert_type TEXT NOT NULL CHECK (alert_type IN (
    'regression', 'safety_failure', 'critical_failure', 'baseline_regression'
  )),
  client_id TEXT,
  dimension TEXT,
  score_before FLOAT,
  score_after FLOAT,
  message TEXT NOT NULL,
  telegram_sent BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_alerts_run_id ON eval_alerts(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_alerts_created_at ON eval_alerts(created_at DESC);
-- Partial index: quickly find unsent alerts for retry
CREATE INDEX IF NOT EXISTS idx_eval_alerts_unsent
  ON eval_alerts(telegram_sent) WHERE telegram_sent = FALSE;

-- ============================================================================
-- Client Baselines
-- One row per client. Locked by `--save-baseline` CLI flag.
-- Used by regression_detector.py for baseline comparison mode.
-- ============================================================================
CREATE TABLE IF NOT EXISTS client_baselines (
  client_id TEXT PRIMARY KEY,
  baseline_run_id TEXT NOT NULL,
  locked_at TIMESTAMPTZ DEFAULT NOW(),
  locked_by TEXT,  -- GitHub username or "manual_cli"
  notes TEXT
);

-- ============================================================================
-- updated_at trigger (eval_test_cases only)
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_eval_test_cases_updated_at
BEFORE UPDATE ON eval_test_cases
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Views
-- ============================================================================

-- Summary per eval run (used by HTML + console reporters)
CREATE OR REPLACE VIEW eval_run_summary AS
SELECT
  run_id,
  COUNT(*) AS total_tests,
  SUM(CASE WHEN passed THEN 1 ELSE 0 END) AS passed_tests,
  ROUND(AVG(score)::numeric, 3) AS avg_score,
  ROUND(
    (SUM(CASE WHEN passed THEN 1 ELSE 0 END)::float / COUNT(*)::float)::numeric, 3
  ) AS pass_rate,
  MIN(created_at) AS run_start,
  MAX(created_at) AS run_end,
  (run_metadata->>'git_commit')::text AS git_commit,
  (run_metadata->>'branch')::text AS branch,
  (run_metadata->>'llm_model')::text AS llm_model,
  (run_metadata->>'triggered_by')::text AS triggered_by
FROM eval_results
GROUP BY run_id, run_metadata;

-- Per-dimension scores per run (used by regression_detector.py)
CREATE OR REPLACE VIEW eval_dimension_scores AS
SELECT
  run_id,
  client_id,
  category AS dimension,
  ROUND(AVG(score)::numeric, 3) AS avg_score,
  ROUND(
    (SUM(CASE WHEN passed THEN 1 ELSE 0 END)::float / COUNT(*)::float)::numeric, 3
  ) AS pass_rate,
  COUNT(*) AS test_count
FROM eval_results
GROUP BY run_id, client_id, category;
