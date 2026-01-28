# Phase 8 Test Plan (UI and Evaluation/QA)

## References
- architecture_evidence.md
- architecture_api_contracts.md


## Purpose
Define rigorous tests for Phase 8 to validate UI behavior and evaluation/QA determinism using frozen snapshots.

## Scope
- UI behavior for evidence rendering, change history, compare, and near-miss views
- Evaluation/QA regression behavior on frozen snapshots
- Validation of evaluation metrics sanity

## Hard Constraints (must hold for all tests)
- UI uses API only; no direct database access
- Evidence is surfaced for all displayed facts
- Evaluation is deterministic on frozen snapshots

## Test Data and Snapshots
- Use frozen snapshots with fixed IDs and contents
- Provide at least one snapshot with:
  - full evidence for every field
  - partial evidence with explicit missing markers
  - multiple change history entries for the same field
  - compare candidates with near-miss differences

## Test Cases

### UI Access Path: API-Only
- UI-API-001: Network audit
  - Setup: Run UI with API endpoint logs enabled
  - Steps: Navigate through all Phase 8 views
  - Expected: All data requests are HTTP API calls; no direct DB connections or drivers in UI bundle
- UI-API-002: DB isolation
  - Setup: Block DB network access and credentials
  - Steps: Load UI views and perform standard actions
  - Expected: UI functions via API; no DB errors surfaced in UI
- UI-API-003: Offline API failure handling
  - Setup: API returns 5xx and 4xx for key endpoints
  - Steps: Load evidence, history, compare, near-miss views
  - Expected: UI shows graceful errors, no DB fallback attempts

### Evidence Rendering
- UI-EV-001: Evidence present for all facts
  - Setup: Snapshot with full evidence
  - Steps: View record details
  - Expected: Each non-null field shows evidence link or inline snippet
- UI-EV-002: Missing evidence markers
  - Setup: Snapshot with missing evidence for some fields
  - Steps: View record details
  - Expected: UI shows explicit missing-evidence state; no silent omission
- UI-EV-003: Evidence provenance integrity
  - Setup: Snapshot with multiple evidence sources
  - Steps: Open evidence detail view
  - Expected: Source identifiers and captured content align to the snapshot

### Change History Display
- UI-HIST-001: Field-level history timeline
  - Setup: Snapshot with multiple updates to a field
  - Steps: Open change history for the field
  - Expected: Entries ordered consistently; previous and current values shown
- UI-HIST-002: Evidence in history entries
  - Setup: History entries with evidence
  - Steps: Inspect history row details
  - Expected: Each entry includes evidence and timestamp label; no empty evidence rows
- UI-HIST-003: History filtering
  - Setup: History across multiple fields
  - Steps: Filter by field and change type
  - Expected: Filters apply correctly and do not remove required evidence

### Compare and Near-Miss Views: Input Validation
- UI-CMP-001: Required inputs
  - Setup: Compare view
  - Steps: Submit with missing required IDs
  - Expected: Validation error shown; no API call sent
- UI-CMP-002: ID format validation
  - Setup: Compare view
  - Steps: Enter malformed IDs, invalid characters, or oversized inputs
  - Expected: Input rejected with clear error
- UI-CMP-003: Near-miss threshold validation
  - Setup: Near-miss view
  - Steps: Submit invalid thresholds (negative, non-numeric, above max)
  - Expected: Validation error shown; defaults not silently applied
- UI-CMP-004: Cross-snapshot validation
  - Setup: Compare across snapshots
  - Steps: Submit mismatched snapshot IDs
  - Expected: UI blocks or warns; API rejects with clear message

### Regression Suite: Determinism on Frozen Snapshots
- EVA-REG-001: Repeated run stability
  - Setup: Frozen snapshot set
  - Steps: Run evaluation twice with identical inputs
  - Expected: Identical metrics and outputs (bitwise match or hash match)
- EVA-REG-002: Order independence
  - Setup: Same snapshots, different processing order
  - Steps: Run evaluation with shuffled input order
  - Expected: Identical outputs and metrics
- EVA-REG-003: Snapshot immutability enforcement
  - Setup: Frozen snapshot
  - Steps: Attempt to mutate snapshot data during evaluation
  - Expected: Mutation blocked or ignored; evaluation still deterministic

### Evaluation Metrics Sanity Tests
- EVA-MET-001: Range checks
  - Setup: Evaluation metrics output
  - Steps: Validate all metrics
  - Expected: Metrics in valid ranges (for example, 0.0 to 1.0 where applicable)
- EVA-MET-002: Baseline sanity
  - Setup: Synthetic dataset with known outcomes
  - Steps: Run evaluation
  - Expected: Metrics match expected values
- EVA-MET-003: Missing-data handling
  - Setup: Dataset with missing evidence or fields
  - Steps: Run evaluation
  - Expected: Metrics exclude or penalize missing data per spec; no NaN values
- EVA-MET-004: Precision-recall consistency
  - Setup: Dataset with known positives/negatives
  - Steps: Compute metrics
  - Expected: Derived metrics consistent (for example, F1 aligns with precision and recall)

## Reporting
- All test runs must log the snapshot IDs, API endpoints used, and evaluation outputs
- Any non-determinism is a failure and must include a minimal reproduction case
