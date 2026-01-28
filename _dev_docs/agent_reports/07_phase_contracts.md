# Phase Contracts

## Phase 1

### Test Summary
- Coverage: Policy Gate decision matrix, ImportTask enforcement for manual_only, Snapshot Store immutability, Evidence linking, Postgres PostGIS pgvector migrations, determinism, and local-only binding.
- Compliance: blocked automation paths for login, CAPTCHA bypass, and paywall circumvention.
- Reference: _dev_docs/agent_reports/phase_tests_phase1.md

## Phase 2 - Acquisition Pipeline

### Test Summary
- Test plan: _dev_docs/agent_reports/phase_tests_phase2.md
- Coverage: task schema and queue payload validation, Policy Gate enforcement, per-domain rate limits and politeness, Firecrawl adapter format rules with changeTracking and content_hash fallback, manual-only enforcement, audit logging completeness, error handling with policy-aware retries, deterministic scheduling inputs.
- Hard constraints and evidence model: same as Phase 1, with required evidence artifacts for every test case.
