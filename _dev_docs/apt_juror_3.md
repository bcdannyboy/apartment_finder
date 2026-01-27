## Schema

Below is a **canonical, unit-centric** model with **explicit provenance + evidence**, and a clean separation between:

* **What we observed** (per-source, per-crawl “observations”)
* **What we believe** (the merged canonical record)
* **How we believe it** (field-level provenance + evidence + confidence)

It is designed to minimize false merges (don’t miss good listings) while still aggressively clustering obvious duplicates.

### 1) Canonical entities and relationships

* **Building** (physical structure): address, geocode, building-wide amenities/policies
* **Unit** (a rentable unit within a building or on a parcel): unit number / unit descriptor (LOWR/REAR/etc.), beds/baths/sqft, unit-level amenities
* **Offer** (a marketed listing for a unit): price, lease, availability, fees, status, marketing text
* **SourceObservation** (per crawl per URL): raw HTML/markdown + extracted fields + evidence
* **DuplicateCluster** (entity-resolution result): groups observations (and/or canonical offers) that refer to the same unit/offer

Why the explicit **Building vs Unit** split matters in SF:

* A lot of listings are “**in-law / ADU**”-style units; SF Planning notes ADUs are often called “in-law units… basement or garage apartments,” which often behave like “unit = rear/lower/basement” rather than a numbered apartment. ([projects.sfplanning.org][1])
* **SRO/residential hotel** listings can look like “studios” but functionally behave differently (shared bathrooms/showers); SF Planning describes typical SRO rooms and differentiates them from tourist hotels. ([projects.sfplanning.org][2])

### 2) Canonical listing record (JSON-schema-ish)

This is the “thing you rank/filter.” It’s an **Offer + Unit + Building** bundle with tight provenance.

```jsonc
// CanonicalListing (unit-centric offer record)
{
  "canonical_listing_id": "uuid",

  // --- identity links ---
  "building_id": "uuid",
  "unit_id": "uuid",
  "cluster_id": "uuid",                         // duplicate cluster identifier (may include multiple offers)
  "canonical_url": "string|null",               // best representative URL (not necessarily original)

  // --- offer (marketed) ---
  "offer": {
    "title": "string|null",
    "description": "string|null",
    "property_type": "enum",                    // apartment|condo|house|townhouse|adu_in_law|sro_residential_hotel|room_shared|other
    "rent": {
      "amount": "number|null",
      "currency": "string",                     // "USD"
      "period": "enum"                          // month|week|day|unknown
    },
    "deposit": { "amount": "number|null", "note": "string|null" },
    "fees": [
      { "fee_type": "enum", "amount": "number|null", "note": "string|null" } // application|move_in|pet|parking|other
    ],
    "lease_term": {
      "min_months": "number|null",
      "max_months": "number|null",
      "lease_type": "enum"                      // fixed|month_to_month|sublet|unknown
    },
    "availability": {
      "availability_date": "date|null",         // parsed best date
      "availability_text": "string|null",       // raw phrase e.g. "Available now" / "Feb 1"
      "is_available_now": "boolean|null"
    },
    "utilities": {
      "included": ["enum"],                     // water|garbage|gas|electric|internet|other
      "excluded": ["enum"],
      "notes": "string|null"
    },
    "status": "enum",                           // active|removed|suspected_stale|unknown
    "posted_at": "datetime|null",               // if available
    "source_post_id": "string|null"             // Craigslist post id, Zillow id, etc (per canonical if stable)
  },

  // --- unit (physical rentable space) ---
  "unit": {
    "beds": "number|null",                      // allow 0 for studio
    "baths": "number|null",                     // allow 0.5 increments
    "sqft": "number|null",
    "unit_number": "string|null",               // "12B", "#3", etc (normalized)
    "unit_designator": "enum|null",             // APT|STE|UNIT|RM|FL|BLDG|... + BSMT/LOWR/UPPR/REAR/FRNT etc
    "unit_position_hint": "enum|null",          // lower|upper|rear|front|basement|unknown
    "floorplan_name": "string|null",
    "is_furnished": "boolean|null",
    "smoking_policy": "enum|null"               // allowed|not_allowed|unknown
  },

  // --- building (shared facts across units) ---
  "building": {
    "building_name": "string|null",
    "building_type": "enum|null",               // multifamily|single_family|mixed_use|sro_hotel|unknown
    "year_built": "number|null",
    "total_units": "number|null"
  },

  // --- location / address ---
  "address": {
    "raw_address_text": "string|null",          // verbatim from page (may be partial)
    "normalized_address": "string|null",        // standardized string
    "components": {
      "street_number": "string|null",
      "street_name": "string|null",
      "street_suffix": "string|null",
      "unit": "string|null",
      "city": "string|null",                    // "San Francisco"
      "state": "string|null",                   // "CA"
      "postal_code": "string|null"
    },
    "geocode": {
      "lat": "number|null",
      "lon": "number|null",
      "provider": "string|null",                // google|mapbox|pelias|nominatim|...
      "provider_accuracy": "string|null",       // e.g., Google "ROOFTOP" / "RANGE_INTERPOLATED"; Mapbox "rooftop/parcel/interpolated/..."
      "precision": "enum",                      // rooftop|parcel|interpolated|intersection|neighborhood|zip_centroid|unknown
      "confidence": "number"                    // 0..1 internal score
    },
    "location_redaction": "enum",               // exact|cross_streets|neighborhood_only|zip_only|unknown
    "geofence": {
      "neighborhood": "string|null",
      "supervisor_district": "string|null"
    }
  },

  // --- amenities & policies (normalized) ---
  "amenities": {
    "laundry": "enum|null",                     // in_unit|in_building|none|unknown
    "parking": {
      "type": ["enum"],                         // garage|carport|street|assigned|ev_charging|none|unknown
      "monthly_fee": "number|null",
      "notes": "string|null"
    },
    "pets": {
      "cats": "enum|null",                      // allowed|not_allowed|unknown
      "dogs": "enum|null",
      "notes": "string|null",
      "pet_fee": "number|null",
      "pet_rent": "number|null"
    },
    "hvac": { "ac": "boolean|null", "heat": "enum|null" },
    "outdoor_space": "enum|null",               // balcony|patio|yard|none|unknown
    "accessibility": { "elevator": "boolean|null", "accessible_unit": "boolean|null" }
  },

  // --- media (for UX + dedupe) ---
  "media": {
    "photos": [
      {
        "url": "string",
        "captured_at": "datetime|null",
        "sha256": "string|null",                // exact content hash (downloaded bytes)
        "phash": "string|null",                 // perceptual hash for similarity
        "alt_text": "string|null",
        "width": "number|null",
        "height": "number|null",
        "vision_tags": [
          { "tag": "string", "confidence": "number", "model": "string", "derived_at": "datetime" }
        ]
      }
    ],
    "video_urls": ["string"],
    "floorplan_urls": ["string"]
  },

  // --- contacts (dedupe + risk) ---
  "contacts": {
    "contact_name": "string|null",
    "company": "string|null",
    "phone_e164": "string|null",
    "email": "string|null",
    "license": "string|null",
    "preferred_contact_method": "enum|null"     // phone|email|form|unknown
  },

  // --- explainability & provenance ---
  "provenance": {
    "source_observation_ids": ["uuid"],         // all contributing observations (cluster members)
    "field_observations": [
      {
        "field_path": "/offer/rent/amount",     // JSON Pointer style
        "value_json": "any",
        "source": {
          "source_name": "string",              // craigslist|zillow|pm_site|...
          "url": "string",
          "observed_at": "datetime",
          "source_listing_id": "string|null"
        },
        "extraction": {
          "method": "enum",                     // rules|llm|hybrid|human
          "extractor_version": "string",
          "confidence": "number"                // 0..1
        },
        "evidence": [
          {
            "snippet": "string",                // short quoted text
            "doc_ref": "uuid",                  // raw doc id
            "start_char": "number|null",
            "end_char": "number|null"
          }
        ]
      }
    ]
  },

  // --- lifecycle & audit ---
  "lifecycle": {
    "first_seen_at": "datetime",
    "last_seen_at": "datetime",
    "last_changed_at": "datetime",
    "status_reason": "string|null",
    "is_active": "boolean"
  },

  // --- quality scores (computed) ---
  "quality": {
    "completeness": "number",                   // 0..1
    "consistency": "number",                    // 0..1
    "recency": "number",                        // 0..1
    "extraction_risk": "number"                 // 0..1 (higher = riskier)
  }
}
```

### 3) SF-specific normalization hooks you should encode

**Unit designators & positional units**
SF listings frequently use “lower/upper/rear/basement” instead of “Apt 3.” USPS explicitly recognizes many of these as secondary unit designators (e.g., **BSMT, LOWR, UPPR, REAR, FRNT**) and standard abbreviations. Use this list to normalize unit descriptors and improve matching. ([Postal Explorer][3])

**Fractional addresses**
USPS also documents fractional addresses like “123 1/2 MAIN ST”; these appear in real-world addressing and should be preserved and normalized rather than dropped. ([Postal Explorer][4])

**Craigslist location precision**
Craigslist posts can be mapped at different precisions: ZIP “area circle,” an address/cross-streets pin, and pins can be manually adjusted. You should explicitly model this as `location_redaction` + `geocode.precision`. ([craigslist][5])

**ADU / in-law**
In SF, “in-law unit” is often synonymous with ADU/secondary unit; SF Planning explicitly notes ADUs are often called in-law units and can be basement/garage apartments. This should drive classification and unit-position features. ([projects.sfplanning.org][1])

**SRO**
SRO listings can behave like “studios” but often include shared facilities; SF Planning describes typical SRO rooms and context. Add `property_type = sro_residential_hotel` detection and risk flags. ([projects.sfplanning.org][2])

---

## Pipeline

This is a **high-recall, evidence-first** extraction pipeline: store everything, extract conservatively, validate aggressively, and never “lose” candidate values.

### Step 0 — Source registry & crawl policy

Maintain a `SourceRegistry` (domain, crawl rules, expected update cadence, trust weight). This drives merge weighting later.

* `source_trust_weight`: PM/owner sites > brokerages > major aggregators > Craigslist (but keep CL for recall).
* `expected_refresh_hours`: e.g., PM sites 12–24h, Craigslist 6–12h (configurable; learn from observed change rates).

### Step 1 — Firecrawl fetch → immutable SourceDocument

For each URL:

* Use Firecrawl to render/crawl and return:

  * raw HTML (or rendered DOM)
  * cleaned markdown/text
  * (optional) screenshot / HAR if you choose
* Store as an **immutable** `SourceDocument`:

  * `doc_id`, `url`, `source_name`, `fetched_at`
  * `http_status`, `final_url`, `content_hash_sha256(html|markdown)`
  * raw blob pointers (S3/GCS)

This enables:

* deterministic reprocessing if your extractor improves
* explaining any field back to the user (“here’s the snippet”)

### Step 2 — Deterministic pre-extraction (rules-first)

Before any LLM:

1. Extract **structured data** if present:

   * JSON-LD (`application/ld+json`) for address, geo, price, etc.
2. Extract obvious patterns with robust regex:

   * price: `\$[\d,]+` + “/mo” etc
   * beds/baths/sqft patterns
   * phone/email normalization
   * “available now / available <date>” phrases
3. Capture candidate **address strings**:

   * visible address blocks
   * “cross streets”
   * map widget text

Store these as `FieldObservation`s with:

* `method = rules`
* `evidence` pointing into the doc

### Step 3 — Address parsing & normalization layer (pre-LLM and post-LLM)

Use **libpostal** to parse/normalize messy address strings and generate variants (expansions) that help matching and geocoding. libpostal is specifically built for parsing/normalizing street addresses using statistical NLP. ([GitHub][6])

Normalization rules (critical for dedupe):

* Apply USPS unit designator normalization (BSMT/LOWR/UPPR/REAR/FRNT etc). ([Postal Explorer][3])
* Preserve fractional address tokens like “1/2”. ([Postal Explorer][4])
* Normalize “#3” → “APT 3” when safe; USPS warns `#` shouldn’t replace a known designator when the correct designation is known. ([Postal Explorer][7])

Output:

* `normalized_address`
* structured components (street number, name, unit, zip…)

### Step 4 — LLM extraction (schema-constrained, evidence-required)

Feed the LLM:

* cleaned markdown
* extracted JSON-LD block(s)
* deterministic candidates (price/beds/address candidates)
* instruction: **produce JSON in your canonical schema AND include evidence snippets for every non-null field**

Key prompt requirements:

* For each extracted field: include

  * `confidence` (0–1)
  * `evidence.snippet` (short quote)
  * `start_char/end_char` (or paragraph index)
* For ambiguous fields (esp. address/unit): output multiple candidates, not one guess.

Output:

* `ExtractionResult` JSON with `FieldObservation`s (method=llm) + evidence

### Step 5 — Geocoding with explicit confidence & precision

Geocode only after normalization and with multiple strategies:

**Strategy A: exact address geocode**

* Use Google/Mapbox (paid, high quality) + optionally Pelias/Nominatim as secondary signals.
* Google returns `location_type` (e.g., **ROOFTOP** vs **RANGE_INTERPOLATED**); interpolated results generally occur when rooftop is unavailable. Use this to compute `geocode.precision` + confidence. ([Google for Developers][8])
* Mapbox provides an explicit accuracy metric for address features (e.g., `rooftop`, `parcel`, `interpolated`, `intersection`, `street`). Map this to your `precision`. ([Mapbox][9])

**Strategy B: cross streets / intersection geocode**
Craigslist can allow pins from cross streets. If you only have cross streets, set:

* `location_redaction = cross_streets`
* `precision = intersection`

Craigslist docs confirm pins can be made by entering an address **or cross streets**, and posts can be a ZIP-area circle or a pin. ([craigslist][5])

**Strategy C: neighborhood-only / zip-only**
If Craigslist (or another source) provides only ZIP: store the zip centroid / polygon and mark precision as `zip_centroid` (low confidence).

### Step 6 — Validators (hard checks + soft checks)

Run validators after LLM extraction; do not “delete” fields—downgrade confidence and add risk flags.

**Hard checks (fail → null out or mark conflict)**

* `rent.amount` must be positive and within configured bounds
* `beds` in [0, 10], `baths` in [0, 10] with 0.5 increments
* SF bounding box check when city=San Francisco (else mismatch flag)

**Soft checks (don’t delete, but reduce confidence)**

* `sqft` < 100 or > 5000 → suspicious
* price-per-sqft outliers vs your own observed distribution
* “available now” but posted months ago → stale risk

### Step 7 — Evidence store (explainability)

Persist:

* `FieldObservation.evidence` snippets
* pointers to SourceDocument offsets
* a compact “explain view” per canonical listing:

  * show top 1–3 evidence snippets per field
  * list conflicting observations and why one won

### Step 8 — Create/Update canonical + history

For each new observation:

1. Run dedupe (next section) to get `cluster_id` and maybe `canonical_listing_id`
2. Merge into canonical record (field-by-field)
3. Write change events:

   * price change, availability change, status change
4. Update lifecycle:

   * `first_seen_at`, `last_seen_at`, `last_changed_at`, `status`

---

## Dedupe + merge

### C) Dedupe / entity resolution proposal

Use a **probabilistic record linkage** approach (pairwise match probability + clustering). The classical framework is Fellegi–Sunter (“A theory for record linkage”). ([Taylor & Francis Online][10])

#### 1) Two-stage architecture: blocking → scoring

**Stage 1: Candidate generation (blocking)**
You want very high recall here.

Create candidate pairs if they share *any* of:

* **Exact contact match**: normalized phone/email
* **Geo proximity**: same geohash (e.g., precision 8–9) OR within X meters (X depends on geocode precision)
* **Address token block**: same (street_number + normalized street_name) when available
* **Image block**: same sha256 OR same pHash “bucket”
* **Building name trigram block**: same building_name 3-gram signature in same neighborhood/zip

**Stage 2: Pair scoring model**
Features (grouped) with recommended weighting ideas:

**(A) Location/address**

* Exact normalized address match (strong)
* Component matches: street_number, street_name, zip
* Unit match:

  * exact unit_number match (very strong)
  * unit_designator + unit_position_hint match (LOWR/REAR/BSMT/etc.) (strong in SF) ([Postal Explorer][3])
  * fractional address consistent (e.g., 123 vs 123 1/2) treat carefully ([Postal Explorer][4])
* Geo distance:

  * < 10m if rooftop/parcel
  * < 50m if interpolated
  * < 250m if neighborhood/zip (weak)

**(B) Offer/unit attributes**

* beds/baths exact or near match
* sqft similarity (relative error)
* price similarity (relative error; but allow difference for price drops)

**(C) Text similarity**

* embedding cosine similarity on title+description
* character n-gram similarity on unique phrases (esp. Craigslist ↔ PM site)

**(D) Media similarity**

* exact photo match: sha256 equality (very strong)
* perceptual match: pHash Hamming distance threshold (strong)

  * Perceptual hashes are designed so similar media have “close” hashes. ([phash.org][11])

**(E) Source behavior priors**

* Same source, same ID → near-certain duplicate
* PM site vs aggregator: more likely same unit
* Craigslist: more likely to be partial location; require additional evidence

**Implementation options**

* You can use the `dedupe` library as a strong baseline for learning weights + blocking rules with human-labeled training data. The docs describe it as ML-based dedupe/entity resolution driven by human training labels. ([docs.dedupe.io][12])
* With unlimited budget, you can also train a custom model (logistic regression / GBDT) and use active learning on uncertain pairs.

#### 2) Match thresholds and policies (conservative to avoid bad merges)

I recommend **three bands**:

* **Auto-merge:** `P(match) >= 0.92`
* **Needs review / second-pass:** `0.75 <= P(match) < 0.92`
* **Auto-separate:** `P(match) < 0.75`

Second-pass actions for the middle band:

* re-geocode with alternate provider
* compute image similarity if missing
* ask an LLM “pair-judge” with strict evidence comparison (still store as evidence)

#### 3) Craigslist-specific strategies (address-hidden reality)

Craigslist postings can be:

* ZIP-area circle (no exact address)
* a pin created from address OR cross streets and draggable by poster ([craigslist][5])

So for Craigslist, treat location features as **lower reliability** unless precision is “pin/rooftop/intersection” *and* matches other sources.

Strong Craigslist duplicate signals:

* phone/email match
* pHash/sha256 match on images
* unique phrase overlap (rare adjectives, copy-pasted text)
* same cross streets + same beds/baths + price within tolerance

Hard “do not merge” constraints (unless unit_number missing on one side):

* beds mismatch by ≥ 2
* unit numbers both present and differ (e.g., APT 3 vs APT 7)
* geodistance > 300m with at least one rooftop geocode

#### 4) Clustering duplicates

Build a graph:

* nodes = SourceObservations (or SourceListings)
* edges = pair matches with probability

Cluster using:

* connected components on edges >= auto-merge threshold
* then run a “cluster sanity pass” to split clusters that contain conflicting unit numbers/beds patterns (very important for large buildings with many similar listings)

### D) Merge policy (conflict resolution)

Merge is **field-by-field** with explainability.

#### 1) Source precedence (default; override by evidence/confidence)

* **Property manager / owner site** (highest)
* **Brokerage / MLS syndications**
* **Major aggregators** (Zillow/Realtor/Apartments.com)
* **Craigslist** (lowest *for address*, but not necessarily for “exists”)

Rationale: Craigslist explicitly allows ZIP-only or user-adjusted pins, so its location can be less precise than other sources. ([craigslist][5])

#### 2) Value selection rule (per field)

For each canonical field:

* compute `score = w_source_trust * w_recency * extraction_confidence * validator_score`
* pick top-scoring value as canonical
* store top-K alternatives as `FieldObservation`s (never discard)

#### 3) Special-case rules

* **Price (`offer.rent.amount`)**: choose *most recent high-confidence* value; always append to price history
* **Availability date**: choose most recent; if conflicting, keep both + set `status_reason="availability_conflict"`
* **Address**:

  * prefer exact address with high geocode precision (`ROOFTOP` or Mapbox `rooftop/parcel`) ([Google for Developers][8])
  * if only cross-streets/zip: keep redacted; never “invent” a street address
* **Unit descriptor normalization**:

  * map “lower” → `LOWR`, “rear” → `REAR`, “basement” → `BSMT` using USPS designators to standardize comparisons ([Postal Explorer][3])
* **SRO detection**:

  * if evidence indicates shared toilets/showers, classify as SRO/hotel-style; SF Planning describes typical SRO room characteristics ([projects.sfplanning.org][2])
* **ADU / in-law**:

  * detect “in-law / granny flat / garage apartment” and set `property_type=adu_in_law` when supported by evidence; SF Planning notes these terms are common for ADUs ([projects.sfplanning.org][1])

---

## Quality scoring rubric

Compute four independent scores in [0,1]. Keep them interpretable; show subcomponents.

### 1) Completeness score

Weighted coverage of key fields:

* **Tier 1 (must-have)**: rent, beds/baths, location (at least neighborhood/zip), status
* **Tier 2**: sqft, availability, lease term, pet policy, laundry, parking
* **Tier 3**: deposit/fees/utilities, building name, media hashes, contact info

Example weighting:

* Tier1 = 0.55, Tier2 = 0.35, Tier3 = 0.10
* Each tier: average of present fields (present if canonical value non-null and confidence >= 0.6)

### 2) Consistency score

Start at 1.0 and subtract penalties:

* internal contradictions:

  * beds/baths conflict between structured fields and description
  * “studio” mentioned but beds=2
* validator penalties:

  * sqft out of range
  * rent outlier vs your own distribution
* cross-source disagreement:

  * high disagreement on a high-importance field (price, beds, address)

### 3) Recency score

Focus on **freshness of observation** and **source cadence**:

* `days_since_last_seen` mapped to [0,1] via exponential decay
* boosted if multiple sources confirmed recently
* penalized if source is known to stale (learned empirically)

### 4) Extraction risk score (higher = riskier)

This is for “flag suspicious listings,” not for ranking desirability.

Additive risk signals:

* **Location risk**: only zip-only or neighborhood-only + low corroboration (Craigslist often allows this) ([craigslist][5])
* **Identity risk**: missing contact + no images + no address
* **Extraction risk**: LLM confidence low or evidence missing for key fields
* **Fraud heuristics** (text rules): “wire transfer,” “gift cards,” “application fee before viewing,” etc.
* **SRO/ADU ambiguity**: keywords indicate nonstandard housing type but missing details (shared bath, etc.); SF has SRO and ADU/in-law patterns worth flagging ([projects.sfplanning.org][2])

Output:

* `extraction_risk` plus a list of `risk_reasons[]` for explainability.

---

## Storage/index recommendation

### System of record: PostgreSQL + PostGIS

Use Postgres as the authoritative store:

* **PostGIS** for geospatial filtering (radius searches, neighborhood containment)
* **JSONB** for flexible storage of extracted observations + provenance blobs
* Strong transactional semantics matter for dedupe merges + history

### Recommended tables (core)

1. `source_documents`

   * `doc_id (pk)`, `url`, `source_name`, `fetched_at`, `http_status`, `final_url`
   * `html_blob_ref`, `markdown_blob_ref`, `content_hash`
2. `source_observations`

   * `observation_id (pk)`, `doc_id (fk)`, `extracted_at`, `extractor_version`
   * `extracted_json (jsonb)` (your FieldObservations)
3. `canonical_listings`

   * `canonical_listing_id (pk)`, `building_id`, `unit_id`, `cluster_id`
   * canonical fields (columns for fast filtering) + `canonical_json (jsonb)`
4. `listing_cluster_members`

   * `cluster_id`, `observation_id`, `match_probability`, `linked_at`
5. `field_observations`

   * (optional normalized table if you don’t want JSONB-only)
   * `canonical_listing_id`, `field_path`, `value_json`, `observation_id`, `confidence`, `evidence[]`
6. `listing_changes`

   * `canonical_listing_id`, `changed_at`, `change_type`, `old_value`, `new_value`, `observation_id`

### Search index: OpenSearch/Elasticsearch

Use it for:

* fast faceted search (beds/baths/price range)
* full-text search (“Victorian,” “in-law,” “rent controlled”)
* geo filters (bounding boxes / polygons)

You still keep Postgres as truth; OpenSearch is a derived index.

### Vector store: pgvector (inside Postgres) or dedicated

For:

* semantic similarity of descriptions (dedupe + search)
* “find similar units to this one”

Given unlimited budget you can use a dedicated vector DB, but **pgvector** is often sufficient and simplifies consistency.

### Media store: object storage + hash indexes

* Put images in S3/GCS
* In Postgres:

  * `sha256` (exact matches)
  * `phash` (similarity)
* For fast pHash similarity:

  * store pHash as 64-bit int
  * use a BK-tree / Hamming distance index (or compute candidate sets via bucketing on prefixes)

Perceptual hashes are explicitly designed to be “close” when media content is similar, making them valuable for dedupe. ([phash.org][11])

---

If you want, I can also provide:

* a **concrete blocking key spec** (exact geohash precisions + which combinations to use per geocode precision),
* and a **pairwise feature dictionary** you can feed directly into an XGBoost model (including monotonic constraints like “closer geo distance should not reduce match probability”).

[1]: https://projects.sfplanning.org/community-stabilization/accessory-dwelling-units.htm "San Francisco's Community Stabilization | Accessory Dwelling Units"
[2]: https://projects.sfplanning.org/community-stabilization/sro-hotel-protections.htm "San Francisco's Community Stabilization | Single Room Occupancy Hotel Protections"
[3]: https://pe.usps.com/text/pub28/28apc_003.htm "C2 Secondary Unit Designators | Postal Explorer"
[4]: https://pe.usps.com/text/pub28/28apd_005.htm "D4 Fractional Addresses | Postal Explorer"
[5]: https://www.craigslist.org/about/help/posting/features/map "craigslist | about | help | posting | features | map"
[6]: https://github.com/openvenues/libpostal "GitHub - openvenues/libpostal: A C library for parsing/normalizing street addresses around the world. Powered by statistical NLP and open geo data."
[7]: https://pe.usps.com/text/pub28/28c2_003.htm "213 Secondary Address Unit Designators | Postal Explorer"
[8]: https://developers.google.com/maps/documentation/geocoding/requests-geocoding?utm_source=chatgpt.com "Geocoding request and response"
[9]: https://docs.mapbox.com/api/search/geocoding-v5/?utm_source=chatgpt.com "Geocoding v5 API"
[10]: https://www.tandfonline.com/doi/abs/10.1080/01621459.1969.10501049?utm_source=chatgpt.com "A Theory for Record Linkage"
[11]: https://www.phash.org/ "pHash.org: Home of pHash, the open source perceptual hash library"
[12]: https://docs.dedupe.io/ "Dedupe 3.0.2 — dedupe 3.0.2 documentation"
