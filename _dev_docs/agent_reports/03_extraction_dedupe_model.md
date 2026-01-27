# Extraction, Dedupe, and Canonical Schema

This document consolidates the canonical data model plus extraction, normalization, and dedupe plans for the apartment finder pipeline. It is written to be implementable with strict provenance and evidence requirements.

## Canonical Entities + Relationships

Relationship overview (one-to-many unless noted):
- Source -> DocumentSnapshot -> SourceObservation -> FieldObservation(s)
- Building -> Unit -> Listing (Listing also links to Source and SourceObservation)
- DedupeCluster groups SourceObservations and/or Listings that refer to the same real-world unit/offer
- ListingChange records canonical changes

Entities (minimum required fields):

1) Source
- source_id (uuid)
- name
- base_domains[]
- policy_status (crawl_allowed | partner_required | manual_only | unknown)
- source_trust_weight (0..1)
- allowed_operations[]

2) DocumentSnapshot (immutable)
- snapshot_id (uuid)
- source_id
- url, final_url
- fetched_at, http_status
- content_hash (sha256 of html + markdown)
- formats: { html, markdown, screenshot, change_tracking }
- storage_refs: { html_path, markdown_path, screenshot_path, pdf_path }
- change_tracking: { status: new|same|changed|removed, visibility: visible|hidden, previous_snapshot_id? }
- fetch_metadata: { headers, etag, cache_hit?, firecrawl_request? }

3) SourceObservation (per snapshot extraction run)
- observation_id (uuid)
- snapshot_id
- extracted_at
- extractor_version (rules version + model + prompt hash)
- extracted_json (raw structured outputs)
- validation_report (schema_ok, errors[])

4) Building (canonical)
- building_id (uuid)
- address (Fact<Address>)
- geo (Fact<GeoPoint>)
- neighborhood (Fact<string>)
- property_type (Fact<enum>)
- amenities (Fact<string[]>)
- manager_contact (Fact<Contact>)

5) Unit (canonical)
- unit_id (uuid)
- building_id
- unit_label (Fact<string>)
- beds (Fact<number>)
- baths (Fact<number>)
- sqft (Fact<number>)
- unit_amenities (Fact<string[]>)

6) Listing (canonical offer)
- listing_id (uuid)
- source_id
- url
- source_listing_key (stable id if provided)
- status (active|pending|off_market|unknown)
- first_seen_at, last_seen_at
- building_id
- unit_id (nullable)
- price_monthly (Fact<number>)
- deposit (Fact<number>)
- fees (Fact<Fee[]>)
- lease_terms (Fact<Lease>)
- available_on (Fact<date>)
- description (Fact<string>)
- photos (Fact<Photo[]>)
- contact (Fact<Contact>)
- policies (Fact<Policy>)
- observations[] (observation_id list)

7) DedupeCluster
- cluster_id (uuid)
- member_observation_ids[]
- match_edges[] (pair_id, probability, features_hash)

8) ListingChange (audit)
- listing_id
- changed_at
- change_type (price|status|availability|content|address)
- old_value_json, new_value_json
- observation_id

Notes:
- Building and Unit are canonical physical entities; Listing is a marketed offer tied to a source and time.
- A listing can exist without a unit_id if only building-level information exists.

## Fact/Evidence Schema (required fields)

Fact and evidence are required for all non-null fields. Use JSON Pointer for field_path to keep mapping stable.

Definitions (JSON-ish):

Fact<T>:
- value: T | null
- confidence: { p: number, extractor: string, at: ISODateTime, method: rules|llm|vision|hybrid|human }
- evidence: EvidenceRef[] (required when value != null)
- source_priority: number (optional, derived from source trust)

EvidenceRef:
- snapshot_id: uuid (required)
- kind: text_span | dom_path | image_region | json_ld
- locator: string (required; css/xpath or image index + box)
- excerpt: string (optional; <= 200 chars, no PII redaction needed for listing content)
- start_char, end_char (optional; for text spans)

FieldObservation (candidate value prior to canonical merge):
- field_path: string (JSON Pointer)
- value_json: any
- confidence: Confidence
- evidence: EvidenceRef[]
- observation_id: uuid
- validator_flags[]: string

Hard requirements:
- Every non-null field must have at least one EvidenceRef.
- For ambiguous fields (address, unit, price range), store multiple FieldObservations instead of guessing.
- Critical fields must include evidence: address or neighborhood, price, beds, baths, status.

## Extraction Pipeline (deterministic + LLM + vision)

0) Policy gate
- Only process snapshots from sources marked crawl_allowed or manual_only.

1) Capture and snapshot
- Store raw html, markdown, screenshots, pdfs, and change_tracking metadata.
- Compute content_hash; link to source and policy.

2) Deterministic pre-extraction (rules-first)
- JSON-LD parse for address, geo, price, beds, baths, sqft, availability.
- Regex extraction for rent, beds/baths, sqft, phone/email, dates.
- Build candidate lists (price range, address strings, unit labels).

3) Address parsing and candidate generation
- Run libpostal on each candidate address string.
- Generate normalized variants and components.
- Preserve fractional addresses (e.g., "123 1/2").
- Normalize secondary unit designators (BSMT, LOWR, UPPR, REAR, FRNT).

4) LLM structured extraction (text)
- Use OpenAI Responses API with Structured Outputs (JSON schema enforced).
- Inputs: markdown, JSON-LD blocks, deterministic candidates.
- Output: FieldObservations with confidence and evidence for every non-null field.
- Failure handling: on schema errors, retry with repair prompt; if still invalid, mark observation error and fall back to deterministic outputs only.

5) Vision extraction (photos/floorplans)
- Fast pass for all listings: infer signals (laundry, flooring, renovation tier, light, noise hints) with Structured Outputs and photo indexes.
- Deep pass only for top candidates or high-uncertainty: add image embeddings and additional analysis.
- Store image hashes (sha256 + phash) and link evidence to photo index or region.
- Failure handling: if vision fails, keep text-only signals and mark missing vision evidence.

6) Validation and normalization
- Hard checks: rent > 0; beds/baths within bounds; baths increments of 0.5; SF bounding box if city=San Francisco.
- Soft checks: sqft outliers, price-per-sqft outliers, stale availability text.
- Do not delete fields; reduce confidence and add validator_flags.

7) Persist observation
- Store SourceObservation and FieldObservations; keep raw LLM output and model metadata.

8) Dedupe and canonical merge
- Run blocking, pair scoring, clustering, and merge (see below).
- Emit ListingChange events and update first/last seen.

9) Reprocessing
- Nightly batch re-extraction for changed snapshots using Batch API.
- Keep extractor_version and prompt hash so results are reproducible.

## Normalization Rules

Address and location:
- Normalize unit designators using USPS abbreviations (APT, UNIT, BSMT, LOWR, UPPR, REAR, FRNT).
- Convert "#3" -> "APT 3" when a unit designator is implied; preserve literal hashtags in building names.
- Preserve fractional street numbers and ranges (e.g., "123 1/2", "100-110").
- If only cross streets or neighborhood are provided, set location_redaction and precision accordingly.

Numeric fields:
- Beds: map "studio" to 0; allow 0.5 for split layouts only if explicit.
- Baths: allow 0.5 increments; "shared bath" => baths unknown and add policy flag.
- Price: parse ranges; store low/high and derived price_monthly if single value.
- Lease terms: parse month counts; map "month-to-month" and "sublet" to enum.

Fees and specials:
- Normalize fee types: application, move_in, pet, parking, amenity, admin, technology, other.
- Capture cadence: one_time vs monthly.
- Detect net effective rent vs base rent; store both if present.

Amenities and policies:
- Laundry: in_unit | in_building | none | unknown.
- Parking: garage | carport | assigned | street | ev_charging | none | unknown.
- Pets: cats/dogs allowed | not_allowed | unknown; capture pet_fee and pet_rent when present.

Contact:
- Normalize phones to E.164; lowercase emails; strip tracking params from URLs.

Media:
- Compute sha256 and phash; store image dimensions and capture time when available.

## Dedupe/Entity Resolution Plan

Goal: high recall in blocking, conservative merges to avoid false positives.

1) Blocking (candidate generation)
Create candidate pairs if any block matches:
- Exact phone or email match.
- Same normalized address tokens (street_number + normalized street_name).
- Geohash match at precision based on geocode precision:
  - rooftop/parcel -> geohash 9
  - interpolated -> geohash 8
  - intersection -> geohash 7
  - neighborhood/zip -> geohash 6 (weak)
- Same image sha256 OR phash bucket.
- Building name trigram overlap in same neighborhood/zip.

2) Pair scoring features
Location/address:
- Exact normalized address match (strong).
- Unit number match; unit designator match (LOWR/REAR/BSMT).
- Geo distance thresholds by precision (10m rooftop, 50m interpolated, 250m neighborhood).

Unit/offer attributes:
- Beds/baths similarity; sqft similarity; price similarity (allow price drops).
- Availability date proximity.

Text and media:
- Description similarity (embeddings + n-gram overlap).
- Photo similarity (sha256 equality, phash Hamming distance).

Source priors:
- Same source and same source_listing_key -> near-certain match.
- Source trust weighting (pm site > broker > aggregator > Craigslist for address).

3) Thresholds and routing
- Auto-merge if match_probability >= 0.92
- Review band if 0.75 <= p < 0.92 (second pass: re-geocode, compute missing image hashes, optional LLM pair-judge)
- Auto-separate if p < 0.75

4) Cluster formation
- Build graph edges for auto-merge pairs; take connected components.
- Cluster sanity pass: split clusters with conflicting unit numbers or large beds/baths disagreement.

5) Merge policy (field-level)
For each field, pick the value with:
score = source_trust * recency * extraction_confidence * validator_score

Special cases:
- Price: pick most recent high-confidence value; always append to price history.
- Address: prefer highest geocode precision; never invent a street address if only cross streets are known.
- Unit descriptor: normalize to USPS designators for comparison.
- ADU/SRO: keep classification only when evidence supports it; otherwise set unknown and add risk flag.

## What must be stored for provenance and reprocessing

Required storage (minimum):
- Raw snapshots (html, markdown, screenshots, pdfs) + content hashes.
- Extraction inputs: which formats were used, deterministic candidates, JSON-LD blocks.
- Extraction metadata: model name, extractor_version, prompt hash, timestamp, structured outputs schema version.
- FieldObservations with evidence refs and validator flags.
- Dedupe features and scores per pair, plus merge decisions.
- Canonical history: ListingChange events with old/new values and observation_id.
- Quality signals: completeness, consistency, recency, extraction_risk.

## Conflicts / Open Questions

1) Geocoding provider
- Kickoff doc requires local-only geocoding, but some juror notes mention Mapbox/Google. Decide on a single primary geocoder (Pelias/Nominatim) and document precision mapping to keep the pipeline local-only.

2) Canonical unit vs listing identity
- For large buildings with multiple identical floorplans, decide if unit_id should represent a specific unit number or a floorplan group.

3) Evidence granularity
- Should evidence store exact byte offsets for html and markdown, or only text snippets + DOM path? Decide for reproducible reprocessing.

4) Storage shape for FieldObservations
- Choose between JSONB-only (simpler) or a normalized field_observations table (faster auditing and queries).

5) Vision signals scope
- Decide which vision signals are required for all listings vs optional for top-ranked candidates to control cost and latency.
