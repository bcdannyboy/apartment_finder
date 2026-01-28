# Phase Contracts

## Phase 6
### Test Summary
- Comprehensive Phase 6 test plan lives at _dev_docs/agent_reports/phase_tests_phase6.md.
- Covers SearchSpec validation and schema versioning, including strict field validation and version mismatch errors.
- Confirms retrieval is limited to Postgres FTS and pgvector only.
- Validates hard filters with confidence-aware logic and deterministic tie-breaks.
- Enforces LLM rerank inputs to structured fields and evidence only, with strict payload constraints.
- Ensures diversity caps by building, neighborhood, and source, API schema stability, and deterministic outputs.
