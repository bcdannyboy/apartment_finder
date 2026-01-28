# Phase 6 Test Plan (Retrieval, Ranking, SearchSpec Parser, API)

## References
- architecture_searchspec.md
- architecture_retrieval.md
- architecture_api_contracts.md


## Purpose and scope
- Validate Phase 6 search correctness, safety, and API stability for retrieval, ranking, SearchSpec parsing, and search responses.
- Ensure deterministic behavior for fixed inputs and seed sets.

## Hard constraints
- Candidate retrieval uses Postgres FTS and pgvector only.
- LLM rerank uses structured fields and evidence only (no raw text beyond evidence).

## Test data and fixtures
- Curated listings with controlled evidence, structured fields, and known edge cases.
- Fixtures include:
  - Multiple listings per building and neighborhood.
  - Mixed source origins per listing.
  - Varying evidence confidence levels per field.
  - Conflicting field values with different evidence confidence.
  - Missing fields with evidence present for other fields.
- Seed sets defined per test suite for deterministic ordering.

## SearchSpec parser and validation
### Schema versioning
- Accept the current schema version and reject unknown versions.
- Enforce backward compatibility only when explicitly supported; otherwise return a version error.
- Version mismatch returns a structured error with a machine-readable code and human-readable message.

### Validation rules
- Required fields are present and typed correctly.
- Optional fields validate when provided and reject unknown fields.
- Enumerations and ranges are enforced (price bounds, bedroom counts, geo bounds, etc.).
- Invalid combinations are rejected with field-level errors (for example, both "only_available_now" and "move_in_after" when mutually exclusive).
- Normalization rules are applied consistently (whitespace, casing, trimming, canonical enum values).

## Retrieval (Postgres FTS + pgvector only)
### Query path integrity
- Retrieval executes only Postgres FTS and pgvector queries.
- No external search engines, vector stores, or cache layers are used.
- Test via query instrumentation and database query auditing.

### FTS behavior
- Validate tokenization and matching for keywords, phrases, and common punctuation.
- Verify ranking and weights by field (title vs body vs structured text).
- Confirm no results when keywords are absent and no fallback leaks in.

### Vector behavior
- Verify embedding dimension and similarity metric are consistent with index settings.
- Ensure vector search is used only when a vector query is provided.
- Validate ANN index usage with query plan inspection.

### Combined retrieval
- Validate merge logic for FTS and vector candidates (union, dedupe, stable ordering).
- Ensure candidate limits are enforced before rerank.
- Confirm deterministic ordering for equal scores via stable tie-breakers.

## Hard filters with confidence-aware logic
- High-confidence mismatches on hard filters exclude candidates.
- Low-confidence mismatches do not hard-exclude but are flagged for rerank.
- Missing evidence for a hard filter produces a deterministic default behavior.
- Conflicting evidence is resolved using the highest-confidence evidence only.
- Test both pass-through and rejection for each hard filter dimension.

## LLM rerank input constraints
- Rerank input is strictly structured fields plus evidence; no raw text beyond evidence.
- Each field includes evidence references and confidence values.
- Enforce a max field list and evidence list per candidate.
- Reject or strip unexpected fields and raw text payloads.
- Verify serialization is stable and ordering is deterministic.

## Diversity caps by building, neighborhood, and source
- Enforce per-building caps to avoid duplicate building dominance.
- Enforce per-neighborhood caps to avoid local over-concentration.
- Enforce per-source caps to avoid single-source bias.
- Validate deterministic tie-breaking when caps exclude candidates.
- Validate caps are applied after candidate retrieval but before final ranking output.

## API schema stability
- Response schema matches published contract and rejects unknown fields.
- SearchSpec request schema is versioned and validated.
- Backward compatible fields are preserved without behavioral change.
- Error payloads are stable with consistent codes and field-level details.

## Determinism for fixed inputs and seed sets
- For fixed inputs, results are identical across runs.
- Deterministic ordering under ties is enforced via stable keys.
- Rerank with fixed seed yields stable ordering and scores.
- End-to-end search output is stable for a fixed SearchSpec and seed set.

## Reporting and acceptance
- Each test case records expected inputs, outputs, and rationale.
- Failures must identify the layer (parser, retrieval, filters, rerank, API).
- All hard constraints are validated by explicit negative tests.
