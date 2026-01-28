# Phase Contracts

## Phase 4 - Entity Resolution and Canonicalization

### Test Summary
- Hard constraints and evidence model align with Phase 1 requirements.
- Blocking and scoring reproducibility with stable candidate sets and scores.
- Threshold band enforcement for auto-merge, review, and auto-separate, including boundary checks.
- Canonical merge policy tests for trust, recency, and confidence ordering.
- Conflicting facts retained with provenance; facts remain append-only.
- ListingChange audit log correctness and idempotency.
- Determinism for fixed inputs across end-to-end runs.
- Detailed plan: `_dev_docs/agent_reports/phase_tests_phase4.md`.
