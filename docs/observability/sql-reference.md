# SQL Reference — Observability & Analytics

> **Purpose**: Operational SQL queries for monitoring, analytics, and troubleshooting Flow AI platform observability data.
>
> **Tables**: `api_usage`, `api_incidents`, `interactions_log`
>
> **Last Updated**: 2026-04-21

---

## Table of Contents

1. [Table Schemas (DDL)](#table-schemas-ddl)
2. [API Usage Queries](#api-usage-queries)
3. [Incident & Guardrail Queries](#incident--guardrail-queries)
4. [Maintenance Queries](#maintenance-queries)

---

## Table Schemas (DDL)

### `api_incidents`

Tracks API failures, guardrail events, and fallback activations.

```sql
CREATE TABLE api_incidents (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT NOW(),
    provider      TEXT NOT NULL,
    error_type    TEXT NOT NULL,
    error_message TEXT,
    client_id     TEXT,
    fallback_used BOOLEAN DEFAULT FALSE,
    both_failed   BOOLEAN DEFAULT FALSE
);

CREATE INDEX ON api_incidents (ts DESC);
CREATE INDEX ON api_incidents (provider, ts DESC);
```

### `api_usage`

Tracks LLM API calls, token usage, and model distribution.

```sql
CREATE TABLE api_usage (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ DEFAULT NOW(),
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    client_id       TEXT,
    input_tokens    INT,
    output_tokens   INT,
    total_tokens    INT
);

CREATE INDEX ON api_usage (provider, ts DESC);
CREATE INDEX ON api_usage (client_id, ts DESC);
```

---

## API Usage Queries

### Model Usage Breakdown (Daily)

Daily breakdown of LLM calls and token usage by model for a specific client.

```sql
SELECT 
    model,
    COUNT(*) AS calls,
    SUM(input_tokens)  AS total_input_tokens,
    SUM(output_tokens) AS total_output_tokens,
    DATE_TRUNC('day', ts) AS day
FROM api_usage
WHERE client_id = 'hey-aircon'
GROUP BY model, day
ORDER BY day DESC, calls DESC;
```

**Use case**: Monitor which models are being used, track token consumption trends, identify cost drivers.

---

### Weekly Haiku Usage Check

Count Haiku calls in the last 7 days to evaluate if Sonnet upgrade is warranted.

```sql
SELECT COUNT(*) FROM api_usage 
WHERE client_id = 'hey-aircon' 
  AND model = 'claude-haiku-4-5-20251001'
  AND ts > NOW() - INTERVAL '7 days';
```

**Use case**: Decision signal for model upgrade. If Haiku usage is high and eval scores are borderline, upgrade to Sonnet.

---

## Incident & Guardrail Queries

### Guardrail Event Summary

Count of each guardrail event type, with the most recent occurrence.

```sql
SELECT 
    error_type, 
    COUNT(*) AS event_count, 
    MAX(ts) AS last_seen
FROM api_incidents
WHERE provider = 'agent_guardrail'
  AND client_id = 'hey-aircon'
GROUP BY error_type
ORDER BY last_seen DESC;
```

**Use case**: Quick health check on safety guardrails. High `guardrail_fired` counts may indicate prompt injection attempts or policy violations.

---

### Guardrail Fires vs Recoveries (Daily)

Compare guardrail activation rate against successful re-prompt recoveries.

**Guardrail fires:**
```sql
SELECT 
    DATE_TRUNC('day', ts) AS day, 
    COUNT(*) AS guardrail_fires
FROM api_incidents
WHERE client_id = 'hey-aircon'
  AND error_type = 'guardrail_fired'
GROUP BY day 
ORDER BY day DESC;
```

**Re-prompt recoveries:**
```sql
SELECT 
    DATE_TRUNC('day', ts) AS day, 
    COUNT(*) AS reprompt_recoveries
FROM api_incidents
WHERE client_id = 'hey-aircon'
  AND error_type = 'guardrail_reprompt_success'
GROUP BY day 
ORDER BY day DESC;
```

**Use case**: Measure guardrail effectiveness. High recovery rate means the re-prompt strategy is working. Low recovery rate may require prompt engineering adjustments.

---

## Maintenance Queries

### Clear Stale Conversation History

Remove all interactions for a specific phone number (use for testing or privacy requests).

```sql
DELETE FROM interactions_log 
WHERE phone_number = '6582829071';
```

**Use case**: Reset conversation state for a test phone number, or comply with a customer deletion request.

⚠️ **Warning**: This is destructive. Verify the phone number before executing.

---

## Notes

- All timestamps are stored in UTC (`TIMESTAMPTZ`).
- `client_id` is nullable in observability tables to support platform-level events.
- Indexes are optimized for time-series queries (most recent first).
- For production dashboards, consider materialized views for daily aggregates.

---

## Related Files

- **Table creation**: `supabase/migrations/001_eval_pipeline.sql`
- **Observability implementation**: `engine/integrations/observability.py`
- **Supabase README**: `supabase/README.md`
