# docs/test-plan/
## Owned by: @sdet-engineer

This directory contains test plans, acceptance criteria, and worktree management for all builds.

### Expected files
- `hey-aircon-phase1-test-plan.md` — test plan for HeyAircon Phase 1 Python engine — **COMPLETE** (April 2026)
- `engine_slice1_task.md` — Slice 1 (Foundation) task brief and verification record
- `engine_slice2_task.md` — Slice 2 (Webhook) task brief and verification record
- `engine_slice3_task.md` — Slice 3 (Message Handler + Escalation Gate) task brief and verification record
- `engine_slice4_task.md` — Slice 4 (Context Builder + Agent Runner) task brief and verification record — **VERIFIED GREEN** (April 2026)
- `eval_pipeline.md` — eval pipeline design for agent response quality testing
- `features/service_variations_test_plan.md` — Service Variations — Agent Clarification Flow (context_builder.py PRICING section) — **IN PROGRESS** (April 2026)
- `features/google_sheets_sync.md` — Google Sheets post-write sync (customer + booking data visibility layer) — **READY FOR IMPLEMENTATION** (April 2026)
- `features/address_schema_migration.md` — Address fields migration: `customers` → `bookings` (Phase 2 code change in `write_booking()`) — **READY FOR IMPLEMENTATION** (April 2026)

### Source documents (read before producing test plan)
- `clients/hey-aircon/plans/mvp_scope.md` — acceptance criteria per component (§What's NOT Built Yet, §Supabase schemas)
- `clients/hey-aircon/plans/test_scenarios.md` — existing test scenarios
- `clients/hey-aircon/plans/build/00_architecture_reference.md` — known issues and workarounds
- `docs/architecture/00_platform_architecture.md` — engine architecture (once created)
