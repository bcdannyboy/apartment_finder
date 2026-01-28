# Evidence Model (Authoritative)

## Purpose
Defines the Evidence model, locator schema, and validation rules.

## Evidence kinds
- text_span
- image_region

## Evidence locator schema

### text_span
- snapshot_id (uuid)
- start_char (int)
- end_char (int)
- text_hash (optional, text) // hash of extracted span for validation
- source_format (optional, text) // html | markdown | text

### image_region
- snapshot_id (uuid)
- image_ref (text) // reference to stored image artifact
- x (int)
- y (int)
- width (int)
- height (int)

## Evidence requirements
- Every non-null Fact must link to one or more Evidence rows via fact_evidence.
- Evidence must reference an immutable DocumentSnapshot.
- Locator offsets must resolve within the referenced snapshot content or image bounds.
- excerpt is optional and, if present, must match the referenced locator span.

## Validation rules
- text_span: start_char < end_char, both non-negative, within content length.
- image_region: width > 0, height > 0, coordinates within image bounds.
- snapshot_id must match the snapshot that produced the observation.

## UI requirements
- Evidence for each displayed Fact is available and linkable.
- Missing evidence must be explicitly marked as missing evidence.
