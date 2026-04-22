# docs/architecture/
## Owned by: @software-architect

This directory contains architecture documents for the Flow AI platform and client builds.

### Architecture Documents
- `00_platform_architecture.md` — Python engine architecture (FastAPI, Supabase hybrid config, tool structure)
- `eval_pipeline.md` — Evaluation pipeline architecture (automated testing, CI/CD integration, regression detection)
- `service_variations_spec.md` — Service variations clarification flow: config naming convention, context_builder PRICING section logic, Supabase SQL, acceptance criteria cross-reference
- `google_sheets_sync.md` — Google Sheets data sync architecture: post-write sync for customers + bookings, fire-and-forget error handling, linear scan deduplication, gspread integration, Phase 2 decommission path
- `address_schema_migration.md` — ADR: move `address` + `postal_code` from `customers` to `bookings`; three-phase migration plan with DDL, write_booking() change spec, rollback notes, and edge cases
- `escalation_reset.md` — ADR + implementation spec for escalation reset via WhatsApp reply-to-message: `escalation_tracking` table, `send_message()` return type change, `reset_handler` module, human agent routing, keyword validation, audit trail

### Source documents (read before producing architecture)
- `clients/hey-aircon/plans/build/00_architecture_reference.md` — current n8n architecture (living reference)
- `clients/hey-aircon/plans/mvp_scope.md` — Supabase schemas and component scope
- `Product/docs/PRD-02_AI_WhatsApp_Agent.md` — agent tool specs and context engineering requirements
- `.claude/CLAUDE.md` — locked tech stack decisions and design principles

### Note on n8n docs
`clients/hey-aircon/plans/build/` contains the n8n architecture reference and all component build guides. These are preserved as-is until the Python engine migration is confirmed live in production. Do not modify or archive them.
