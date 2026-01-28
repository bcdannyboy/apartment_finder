# Phase 4 Test Plan - Entity Resolution and Canonicalization

## References
- architecture_schema.md
- architecture_evidence.md


## Scope
- Entity resolution: blocking, pair scoring, clustering, and threshold band routing.
- Canonicalization: canonical field selection, fact retention, and audit logging.
- Interfaces touched: listings, buildings, units, facts, listing_changes.
- Hard constraints and evidence model follow the Phase 1 format.

## Hard constraints
- Determinism for fixed inputs: identical inputs and config yield identical outputs.
- Facts are append-only; no deletion or overwrite in place.
- Conflicting facts are retained with provenance and evidence.
- Canonical fields must reference a Fact with confidence and evidence.
- Threshold bands must be enforced without overlap or gaps.
- ListingChange is an audit log; it must be correct and idempotent.

## Evidence model
- Inputs: versioned fixture set IDs, normalization outputs, and config hash.
- Blocking evidence: sorted blocking keys and candidate pair lists with counts.
- Scoring evidence: feature vectors, model version, and stable score outputs.
- Merge evidence: winning fact id plus the policy reason (trust, recency, confidence).
- Output evidence: cluster membership, canonical field map, and listing_changes rows.
- Determinism evidence: stable hashes of sorted outputs across repeated runs.

## Fixtures and baselines
- Duplicate fixture: same unit across sources with small formatting variance.
- Near-duplicate fixture: similar address but different unit or building.
- Conflict fixture: same field with different values across sources.
- Policy fixture: sources with different trust and observation order.
- Threshold fixture: pairs covering values at and around band boundaries.

## Tests
### T4.01 Blocking reproducibility
- Goal: blocking keys and candidate pairs are identical across repeated runs.
- Setup: run blocking twice on the same fixture set and config.
- Checks: same keys, same candidate pair list, same counts.
- Evidence: saved key list, pair list, and hashes.

### T4.02 Blocking recall for known duplicates
- Goal: known duplicate pairs appear in candidate sets.
- Setup: fixture with labeled duplicates and near duplicates.
- Checks: all labeled duplicates are present in candidate pairs; near duplicates are not required.
- Evidence: candidate pair list with labels.

### T4.03 Pair scoring reproducibility
- Goal: scoring outputs are identical for fixed inputs.
- Setup: run scoring twice on the same candidate pairs and features.
- Checks: same score for each pair; no nondeterministic drift.
- Evidence: score table and hash.

### T4.04 Threshold band enforcement
- Goal: auto-merge, review, and auto-separate bands are applied correctly.
- Setup: scores at boundaries and interior points for each band.
- Checks: boundary values map to the specified band; no overlap or gaps.
- Evidence: score classification table.

### T4.05 Review band non-destructive behavior
- Goal: review band pairs do not alter canonical state without approval.
- Setup: fixture with review-band pairs only.
- Checks: no merge, no split, review queue entries created.
- Evidence: cluster membership diff and review queue output.

### T4.06 Canonical merge policy - trust priority
- Goal: higher trust source wins over lower trust even when less recent.
- Setup: conflicting facts with different trust levels and different recency.
- Checks: canonical field selects the higher trust fact.
- Evidence: canonical field map with winning fact id and policy reason.

### T4.07 Canonical merge policy - recency and confidence tie-breaks
- Goal: recency wins when trust is equal; confidence wins when recency is equal.
- Setup: fixtures with equal trust and differing recency; then equal recency and differing confidence.
- Checks: canonical field selection follows the tie-break order.
- Evidence: canonical field map with policy reasons.

### T4.08 Conflicting facts retained with provenance
- Goal: conflicting facts remain stored with full provenance and evidence.
- Setup: conflicting facts for the same field across sources.
- Checks: facts table retains all values; canonical field points to one fact; others remain.
- Evidence: facts rows and canonical field references.

### T4.09 ListingChange audit log correctness
- Goal: listing_changes reflect real canonical changes and are idempotent.
- Setup: apply a new observation that changes a canonical field, then rerun.
- Checks: one change record with old and new values; no extra records on rerun.
- Evidence: listing_changes rows and canonical field diff.

### T4.10 No deletion of Facts
- Goal: facts are append-only.
- Setup: merge clusters and rerun dedupe.
- Checks: no fact row removed; any superseded facts remain accessible.
- Evidence: fact row count and ids before and after.

### T4.11 End-to-end determinism for fixed inputs
- Goal: full dedupe and canonicalization outputs are identical across runs.
- Setup: run the full Phase 4 pipeline twice on the same inputs.
- Checks: cluster assignments, canonical fields, and listing_changes are identical.
- Evidence: output hashes and diff report.

## Acceptance signals
- All tests pass with identical hashes across repeated runs.
- No missing candidates for labeled duplicates.
- No deletion of facts and no loss of provenance.
- ListingChange is correct, minimal, and idempotent.
