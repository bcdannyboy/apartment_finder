# Phase Contracts

## Purpose
Define cross-phase service contracts and the minimum guarantees each phase provides to the next.

## Contract surfaces
- Policy Gate API
- Snapshot Store API
- Ranking API
- Alert API

## Contract quality gates
- Schema compatibility and versioning rules
- Error handling and retry guidance
- Idempotency and immutability guarantees
- Evidence and provenance requirements

## Integration Tests
- The integration test plan lives in `_dev_docs/agent_reports/phase_tests_integration.md`.
- Coverage includes the full pipeline and all contract boundaries.
- Contract tests exist for Policy Gate, Snapshot Store, Ranking API, and Alert API.
- Network egress is restricted to Firecrawl and OpenAI endpoints only.
- Determinism and snapshot immutability are enforced in cross-phase runs.

## Notes
This document focuses on interface guarantees; implementation details live in service specs.
