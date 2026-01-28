# Phase Integration Tests

## References
- architecture_compliance_enforcement.md
- architecture_api_contracts.md
- architecture_searchspec.md
- architecture_retrieval.md
- architecture_geo_commute.md


## Scope
- Validate cross-phase integration from acquisition and import through UI delivery.
- Enforce policy and compliance gates at every entry point.
- Prove deterministic, reproducible outputs on frozen inputs.
- Prove local-only networking rules with a strict outbound allowlist.
- Verify contract compatibility across key service boundaries.

## Pipeline under test
ImportTask -> Snapshot -> Extraction -> Normalization -> Dedupe -> Geo -> Ranking -> Alerts -> UI

## Test environment and fixtures
- Local services only; outbound network is blocked except for Firecrawl and OpenAI.
- Allowlist includes production OpenAI and Firecrawl standard endpoints only.
- Fixed dataset with sources labeled crawl_allowed, manual_only, and blocked.
- Frozen snapshot fixtures with known content hashes and stable identifiers.
- Deterministic configuration for ranking and extraction (fixed seeds and stable tie breaks).
- Local geocode and routing fixtures or local engines with fixed responses.

## Phase boundary checks
- Acquisition or manual import produces a Snapshot and a single immutable snapshot record.
- Extraction reads only snapshot content and emits SourceObservation with evidence links.
- Normalization modifies extracted fields without losing provenance.
- Dedupe merges into canonical entities while preserving source traceability.
- Geo enriches entities with local geocode and routing outputs.
- Ranking consumes canonical entities and emits stable, explainable scores.
- Alerts process listing changes and produce Alert records for matching SearchSpecs.
- UI reads API responses with evidence and alert status surfaced to users.

## Test cases

### IT-001 End-to-end pipeline
Purpose: Validate the full pipeline from ImportTask to UI.
Setup:
- Create a manual ImportTask and a crawl task for a crawl_allowed source.
- Seed SearchSpec that matches the expected listing.
Steps:
1) Run acquisition or manual import to create Snapshot records.
2) Run Extraction, Normalization, Dedupe, and Geo in sequence.
3) Run Ranking for the SearchSpec.
4) Run Alerts for the SearchSpec.
5) Load the UI listing and search results.
Assertions:
- Each phase writes expected records and references the prior phase IDs.
- Evidence links from extraction appear in the API payload and UI.
- Search results include the listing with stable scoring fields.
- Alerts are created and visible in UI alert views.

### IT-002 Policy Gate enforcement
Purpose: Enforce policy in acquisition and manual import paths.
Setup:
- Sources tagged as crawl_allowed, manual_only, and blocked.
Steps:
1) Submit acquisition tasks for each source.
2) Submit manual imports for each source.
Assertions:
- crawl_allowed permits automated acquisition.
- manual_only blocks automation and permits manual imports.
- blocked rejects both automated and manual paths.
- Policy Gate responses are audited and stored with task metadata.

### IT-003 Snapshot immutability
Purpose: Ensure Snapshot records are immutable across reprocess.
Setup:
- Create a Snapshot with known content hash.
Steps:
1) Run Extraction and Normalization.
2) Re-run Extraction and Normalization without changing the Snapshot.
Assertions:
- Snapshot content hash and immutable fields do not change.
- Reprocessing creates new derived artifacts only when needed.
- Derived artifacts reference the same Snapshot ID.

### IT-004 Evidence propagation to UI
Purpose: Verify evidence linkage from extraction to UI.
Setup:
- Snapshot contains fields with evidence ranges.
Steps:
1) Run Extraction, Normalization, Dedupe.
2) Query listing detail API.
3) Load UI detail view.
Assertions:
- API includes evidence links for each non-null field.
- UI renders evidence references and opens the Snapshot view.

### IT-005 Determinism on frozen inputs
Purpose: Prove stable outputs on fixed inputs.
Setup:
- Freeze snapshot fixtures and config.
Steps:
1) Run the pipeline twice from Snapshot through Alerts.
2) Compare outputs for normalization, dedupe, geo, ranking, and alert matches.
Assertions:
- Output records are identical or match a defined deterministic fingerprint.
- Ranking order and scores are stable for equal inputs.

### IT-006 Local-only network checks
Purpose: Enforce network egress restrictions.
Setup:
- Network policy allows only Firecrawl and OpenAI endpoints.
Steps:
1) Run the pipeline with network monitoring enabled.
Assertions:
- No outbound connections occur except to allowed endpoints.
- Any blocked attempt fails the test and is logged.

### IT-007 Contract tests: Policy Gate
Purpose: Ensure consistent request and response schemas.
Assertions:
- Policy Gate accepts task metadata and returns policy decision and reason.
- Error codes and retry guidance match the contract schema.

### IT-008 Contract tests: Snapshot Store
Purpose: Ensure snapshot immutability and retrieval behaviors.
Assertions:
- Create returns snapshot ID and content hash.
- Read returns exact content by ID and rejects mutation calls.

### IT-009 Contract tests: Ranking API
Purpose: Validate ranking inputs, outputs, and explanations.
Assertions:
- Accepts canonical entity IDs and SearchSpec.
- Returns stable scores, ranks, and explanation fields.
- Rejects missing evidence fields with a clear error response.

### IT-010 Contract tests: Alert API
Purpose: Validate alert generation and delivery records.
Assertions:
- Accepts listing change events and SearchSpec links.
- Returns alert records with matching criteria and status.
- Idempotent behavior for repeated change events.

## Reporting and artifacts
- Store per-test run artifacts: input fixtures, output snapshots, and diff reports.
- Publish a per-phase summary with pass or fail and primary failure cause.
