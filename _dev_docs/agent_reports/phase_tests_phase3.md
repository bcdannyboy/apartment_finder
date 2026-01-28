# Phase 3 Tests: Extraction and Normalization

## Scope
- Extraction Service deterministic pre-extraction (JSON-LD and regex).
- Structured Outputs extraction with schema validation.
- Normalization Service output and provenance preservation.
- Evidence requirements, ambiguity handling, validation_report behavior, locator validity.
- Determinism and replay on frozen snapshots.

## Inherited constraints and evidence model (Phase 1 alignment)
- Local-first system; only paid services are Firecrawl and OpenAI.
- Compliance gating remains enforced; extraction uses stored snapshots only.
- Snapshots are immutable and versioned for replay.
- Provenance-first: every non-null field has confidence and evidence.
- Evidence is tied to a snapshot and is resolvable (text_span or image_region).
- Conflicting values are retained with provenance; no destructive overwrite.

Evidence model (minimum):
- FieldObservation / Fact
  - value: typed value or null
  - confidence: numeric with extractor metadata
  - evidence: one or more EvidenceRef entries
- EvidenceRef
  - snapshot_id
  - kind: text_span or image_region
  - locator: snapshot-specific pointer
  - excerpt: optional, must match snapshot content when present

## Test data and fixtures (frozen snapshots)
- FIX-P3-001 jsonld_full: JSON-LD with price, beds, baths, address, availability; visible text matches fields.
- FIX-P3-002 regex_only: no JSON-LD; fields only in visible text.
- FIX-P3-003 ambiguous_address: multiple address candidates in the same snapshot.
- FIX-P3-004 multi_unit: multiple unit options with different prices and beds.
- FIX-P3-005 conflicting_values: JSON-LD value conflicts with visible text.
- FIX-P3-006 image_only: key fields only visible in images or floorplans.
- FIX-P3-007 schema_fail: mocked model output with type errors and missing required keys.
- FIX-P3-008 locator_edge: short text with repeated substrings and tight offsets.
- FIX-P3-009 replay_set: pinned snapshot set used for deterministic replay checks.

All fixtures are immutable and stored as snapshots with stable content hashes.

## Test suites

### Deterministic pre-extraction (JSON-LD, regex)

#### P3-EX-001 JSON-LD extraction is deterministic
- Setup: FIX-P3-001.
- Steps: run deterministic parser twice on the same snapshot.
- Expected:
  - Identical fields, values, and evidence locators across runs.
  - Evidence kind is text_span with locators that resolve to JSON-LD or visible text.
  - extractor_version is recorded and unchanged between runs.

#### P3-EX-002 Regex extraction is deterministic
- Setup: FIX-P3-002.
- Steps: run deterministic regex parser twice.
- Expected:
  - Identical fields, values, and evidence locators across runs.
  - Evidence locators resolve to the matched text spans.

#### P3-EX-003 Deterministic parser does not guess on ambiguity
- Setup: FIX-P3-003.
- Steps: run deterministic parser.
- Expected:
  - Ambiguous fields are either null or emitted as multiple candidates.
  - No single candidate is selected without evidence for disambiguation.

#### P3-EX-004 Deterministic parser handles conflicts without overwrite
- Setup: FIX-P3-005.
- Steps: run deterministic parser.
- Expected:
  - Conflicting values are emitted as separate FieldObservations with evidence.
  - No conflict is silently resolved or overwritten.

### Structured Outputs schema validation behavior

#### P3-SO-001 Valid Structured Outputs pass schema validation
- Setup: FIX-P3-001 with a valid Structured Outputs response.
- Steps: validate response against schema and emit observations.
- Expected:
  - validation_report status is success.
  - Extracted fields are emitted with evidence and confidence.

#### P3-SO-002 Type mismatch triggers schema failure
- Setup: FIX-P3-007 with wrong types.
- Steps: validate response.
- Expected:
  - validation_report status is failure.
  - Error list includes schema path and expected type.
  - No FieldObservations are emitted from the invalid response.

#### P3-SO-003 Missing required keys triggers schema failure
- Setup: FIX-P3-007 with missing required keys.
- Steps: validate response.
- Expected:
  - validation_report lists missing keys with schema paths.
  - Extracted JSON is not accepted.

#### P3-SO-004 Bounded repair retry is recorded
- Setup: FIX-P3-007.
- Steps: run validation with repair enabled.
- Expected:
  - At least one repair attempt is recorded when enabled.
  - validation_report includes retry_count and final status.
  - Final output is only accepted if it passes schema validation.

### Evidence requirement for all non-null fields

#### P3-EV-001 Missing evidence invalidates non-null fields
- Setup: Any fixture with a model response missing evidence.
- Steps: validate evidence presence for all non-null fields.
- Expected:
  - Any non-null field without evidence is rejected or set to null.
  - validation_report records evidence_missing with field path.

#### P3-EV-002 Evidence required for deterministic extraction too
- Setup: FIX-P3-002.
- Steps: emit deterministic fields without evidence to simulate a failure.
- Expected:
  - Extraction is rejected until evidence is attached for each non-null field.

#### P3-EV-003 Evidence required for nested and array fields
- Setup: FIX-P3-004 with multiple units and amenities.
- Steps: validate evidence for each element.
- Expected:
  - Every nested non-null value has at least one EvidenceRef.

### Ambiguity handling returns multiple candidates

#### P3-AMB-001 Ambiguous address yields multiple candidates
- Setup: FIX-P3-003.
- Steps: run Structured Outputs extraction.
- Expected:
  - Address field returns multiple candidates, each with evidence.
  - No single candidate is selected without disambiguation evidence.

#### P3-AMB-002 Multiple rent values preserved as candidates
- Setup: FIX-P3-004.
- Steps: run extraction and normalization.
- Expected:
  - Candidate rent values remain distinct with their evidence.
  - Normalization does not collapse candidates into a single value.

#### P3-AMB-003 Ambiguous unit identifiers preserved
- Setup: FIX-P3-004.
- Steps: run extraction and normalization.
- Expected:
  - Unit labels remain as multiple candidates when ambiguous.
  - Each candidate has evidence and confidence.

### Validation_report behavior on schema failures

#### P3-VAL-001 validation_report is always populated on failure
- Setup: FIX-P3-007.
- Steps: force schema failure.
- Expected:
  - validation_report exists on SourceObservation even when extracted_json is null.

#### P3-VAL-002 validation_report includes load-bearing failure details
- Setup: FIX-P3-007.
- Steps: validate response.
- Expected:
  - validation_report includes schema_version, error paths, and severity.
  - Raw model output is referenced via a stable ref or snapshot link.

#### P3-VAL-003 Failed validation does not emit FieldObservations
- Setup: FIX-P3-007.
- Steps: validate response.
- Expected:
  - No FieldObservations are emitted when schema validation fails.
  - Failure is marked for review or retry.

### Normalization preserves raw values and evidence

#### P3-NORM-001 Raw and normalized values both persist
- Setup: FIX-P3-001 with price "$1,950/mo".
- Steps: normalize currency and rent range.
- Expected:
  - Raw value is preserved alongside normalized value.
  - Evidence remains tied to the raw text span.
  - Normalized value references the raw observation.

#### P3-NORM-002 Fractional addresses are preserved
- Setup: FIX-P3-001 with "123 1/2".
- Steps: normalize address.
- Expected:
  - Normalized address retains fractional component.
  - Evidence locators remain unchanged.

#### P3-NORM-003 Bed and bath normalization preserves evidence
- Setup: FIX-P3-001 with "1.5 bath".
- Steps: normalize to half-step increments.
- Expected:
  - Normalized value is correct and evidence still points to the raw text.

#### P3-NORM-004 No destructive overwrite of conflicting values
- Setup: FIX-P3-005 with conflicting price values.
- Steps: normalize.
- Expected:
  - Conflicting values remain as separate observations.
  - Each retains its original evidence.

### Evidence locator validity tests

#### P3-LOC-001 text_span locator resolves to snapshot content
- Setup: FIX-P3-001.
- Steps: resolve each text_span locator to the snapshot.
- Expected:
  - Locator resolves to a valid span within the snapshot content.
  - excerpt, if present, matches the resolved span exactly.

#### P3-LOC-002 text_span locator handles repeated substrings
- Setup: FIX-P3-008.
- Steps: resolve locator offsets for repeated text.
- Expected:
  - Locator points to the correct occurrence, not a different match.

#### P3-LOC-003 image_region locator is within bounds
- Setup: FIX-P3-006.
- Steps: validate image_region coordinates.
- Expected:
  - Coordinates are within image bounds and reference an existing image.

#### P3-LOC-004 locator snapshot_id matches evidence source
- Setup: Any fixture with mixed snapshot references.
- Steps: validate snapshot_id on evidence locators.
- Expected:
  - snapshot_id matches the snapshot that produced the field value.

### Determinism and replay on frozen snapshots

#### P3-DET-001 Deterministic parsers are stable across replays
- Setup: FIX-P3-009.
- Steps: run deterministic pre-extraction multiple times.
- Expected:
  - Outputs match exactly, including evidence locators.

#### P3-DET-002 Structured Outputs replay is stable
- Setup: FIX-P3-009 with stored model output or deterministic settings.
- Steps: replay extraction.
- Expected:
  - Outputs match the stored reference or approved golden output.
  - Any drift is flagged and requires review.

#### P3-DET-003 Normalization is stable across replays
- Setup: FIX-P3-009.
- Steps: run normalization multiple times on the same inputs.
- Expected:
  - Normalized outputs are identical and ordered deterministically.

#### P3-DET-004 Version changes do not overwrite prior results
- Setup: FIX-P3-009 with a new extractor_version.
- Steps: run extraction with updated version.
- Expected:
  - New results are stored separately with new extractor_version.
  - Prior results remain intact for audit and comparison.

## Phase 3 exit criteria
- All test cases in this document pass.
- Any schema validation failure or evidence gap blocks acceptance.
- Replay tests pass with zero drift on frozen snapshots.
