# Canonical Schema (Authoritative)

## Purpose
Defines the canonical data model and minimum required fields. This schema is aligned to the provenance-first requirements and the evidence model.

## Global requirements
- DocumentSnapshot is immutable.
- Facts are append-only.
- Every non-null field requires Evidence and confidence.
- Evidence is normalized and linked via fact_evidence.

## Core tables

### sources
- source_id (uuid, pk)
- name (text)
- kind (text) // pm_site, broker_site, marketplace, licensed_feed, user_import
- base_domains (text[])
- created_at (timestamp)

### source_policies
- policy_id (uuid, pk)
- source_id (uuid, fk -> sources)
- policy_status (enum PolicyStatus)
- allowed_operations (text[])
- robots_snapshot_id (uuid, fk -> document_snapshots)
- tos_url (text)
- compliance_summary (text)
- reviewer (text)
- reviewed_at (timestamp)
- version (int)

### document_snapshots
- snapshot_id (uuid, pk)
- source_id (uuid, fk -> sources)
- url (text)
- fetched_at (timestamp)
- http_status (int)
- content_hash (text)
- formats (jsonb) // { html, markdown, screenshot, change_tracking }
- storage_refs (jsonb) // filesystem paths
- change_tracking (jsonb) // if present
- raw_metadata (jsonb)
- immutable (bool, always true)

### source_observations
- observation_id (uuid, pk)
- snapshot_id (uuid, fk -> document_snapshots)
- source_id (uuid, fk -> sources)
- extracted_json (jsonb)
- extractor_version (text)
- validation_report (jsonb)
- created_at (timestamp)

### facts
- fact_id (uuid, pk)
- observation_id (uuid, fk -> source_observations)
- entity_type (text) // building | unit | listing
- entity_id (uuid)
- field_path (text) // JSON pointer path
- value_json (jsonb)
- confidence (numeric)
- extractor (text)
- extracted_at (timestamp)
- is_canonical (bool, default false)

### evidence
- evidence_id (uuid, pk)
- snapshot_id (uuid, fk -> document_snapshots)
- kind (enum EvidenceKind)
- locator (jsonb)
- excerpt (text)
- created_at (timestamp)

### fact_evidence
- fact_id (uuid, fk -> facts)
- evidence_id (uuid, fk -> evidence)
- rank (int)
- primary key (fact_id, evidence_id)

### buildings
- building_id (uuid, pk)
- address_json (jsonb)
- geo_json (jsonb)
- created_at (timestamp)

### units
- unit_id (uuid, pk)
- building_id (uuid, fk -> buildings)
- unit_label_json (jsonb)
- beds_json (jsonb)
- baths_json (jsonb)
- sqft_json (jsonb)
- created_at (timestamp)

### listings
- listing_id (uuid, pk)
- source_id (uuid, fk -> sources)
- building_id (uuid, fk -> buildings)
- unit_id (uuid, fk -> units, nullable)
- url (text)
- status (enum ListingStatus)
- first_seen_at (timestamp)
- last_seen_at (timestamp)
- created_at (timestamp)

### listing_changes
- change_id (uuid, pk)
- listing_id (uuid, fk -> listings)
- field_path (text)
- old_value_json (jsonb)
- new_value_json (jsonb)
- changed_at (timestamp)

### search_specs
- search_spec_id (uuid, pk)
- schema_version (text)
- raw_prompt (text)
- spec_json (jsonb)
- created_at (timestamp)

### matches
- match_id (uuid, pk)
- search_spec_id (uuid, fk -> search_specs)
- listing_id (uuid, fk -> listings)
- retrieved_at (timestamp)
- scores_json (jsonb)
- explanation_json (jsonb)

### alerts
- alert_id (uuid, pk)
- search_spec_id (uuid, fk -> search_specs)
- listing_id (uuid, fk -> listings)
- channel (enum AlertChannel)
- status (text)
- created_at (timestamp)

### tasks
- task_id (uuid, pk)
- task_type (enum TaskType)
- source_id (uuid, fk -> sources)
- policy_id (uuid, fk -> source_policies)
- domain (text)
- payload (jsonb)
- status (text)
- attempt (int)
- max_attempts (int)
- scheduled_at (timestamp)
- created_at (timestamp)

### audit_logs
- audit_id (uuid, pk)
- task_id (uuid, fk -> tasks)
- policy_id (uuid, fk -> source_policies)
- outcome (text)
- params (jsonb)
- error_class (text)
- created_at (timestamp)

## Required indexes (minimum)
- document_snapshots(url, content_hash)
- source_observations(snapshot_id, source_id)
- facts(field_path)
- fact_evidence(fact_id, evidence_id)
- listings(status, last_seen_at)
- listings(geom) // PostGIS geometry index if used
- search_specs(schema_version)
- matches(search_spec_id, retrieved_at)
- alerts(search_spec_id, created_at)

## Immutability rules
- document_snapshots and evidence are immutable after creation.
- facts are append-only; no in-place edits.
- listing_changes are append-only.
