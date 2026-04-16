# Supabase

This folder contains SQL migration files for all Supabase projects used by Flow AI.

## Projects

| Project name | Purpose | Connection env var |
|---|---|---|
| `flow-ai-eval` | Eval pipeline — test cases, results, alerts | `EVAL_SUPABASE_URL` |
| `flow-ai-{client}` | Per-client production DB — conversations, bookings, customers | `{CLIENT_ID_UPPER}_SUPABASE_URL` |

These are **separate Supabase projects**. The eval pipeline reads client config from the client production DB (read-only) and writes all eval data to `flow-ai-eval`.

## How to run migrations

1. Open [Supabase Studio](https://supabase.com/dashboard) → select the target project
2. Go to **SQL Editor** → **New query**
3. Paste the migration file content → **Run**
4. Verify tables appear under **Table Editor**

No Supabase CLI is required. Migrations are applied manually once per project.

## Migrations

| File | Target project | What it creates |
|---|---|---|
| `001_eval_pipeline.sql` | `flow-ai-eval` | `eval_test_cases`, `eval_results`, `eval_alerts`, `client_baselines`, 2 views, indexes |

## When to add a new migration file

- New table or column → new numbered file (`002_*.sql`)
- ALTER TABLE or data backfill → new numbered file
- Never modify existing migration files (they may already be applied)
