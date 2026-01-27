Language choice: Python. Rationale: the system is data- and geo-heavy (ETL, geospatial joins, ranking features, ML/LLM pipelines, PDF/HTML parsing), and Python has the strongest ecosystem for this stack (pandas/geopandas/shapely, libpostal bindings, PostGIS drivers, scheduling, ML tooling). Python also integrates cleanly with OpenAI and Firecrawl SDKs and is ideal for a local-first orchestration layer. A minimal JS frontend can still be served by the Python app, but the core system will be implemented in Python.

# Apartment Finder Architecture Kickoff Document

This document synthesizes all materials in `_dev_docs` and `_dev_docs/research` into a development-ready architecture plan. It is intentionally verbose and explicit to support kickoff and execution.

Hard constraints honored:
- Local-first system; Docker allowed.
- No cloud dependency except Firecrawl and OpenAI.
- Only paid services allowed: Firecrawl and OpenAI.
- Strict provenance and compliance rules.

---

## Table of contents

1. Goals and non-goals
2. Compliance posture and source policy rules
3. Data acquisition strategy
4. End-to-end pipeline (capture -> extract -> normalize -> dedupe -> rank -> alert)
5. Canonical data model and provenance requirements
6. Geo/commute subsystem (open data only)
7. Ranking pipeline and diversity system
8. Freshness/change detection/recrawl scheduler
9. Evaluation and QA plan
10. UI/UX feature summary (system level)
11. Local deployment architecture (Docker ok)
12. Security and privacy considerations
13. Implementation phases (MVP -> month-1 -> month-3)
14. Open questions / decisions
15. High-level component spec reference

---

## 1) System goals and non-goals

### 1.1 Goals
1. **Maximum compliant coverage** of San Francisco rental inventory, especially long-tail PM and building sites that are often missed by major portals.
2. **High freshness**: discover new listings quickly and detect changes (price, availability, status) with minimal lag.
3. **Provenance-first accuracy**: every extracted field is traceable to evidence (text span or image region), with explicit confidence.
4. **Decision-grade ranking**: explainable scores, near-miss tradeoffs, and diversity controls to avoid “same-y” results.
5. **Local-first privacy**: user data and listing corpus are stored locally, never in a third-party cloud (except Firecrawl/OpenAI transient processing).
6. **Open-data geo/commute**: geocoding and routing run locally using open data (OSM, GTFS, DataSF).
7. **Evaluation built-in**: golden sets, regression tests, and audit workflows are first-class from day one.

### 1.2 Non-goals (explicitly out of scope)
1. Automated scraping of restricted marketplaces (Craigslist, Zillow, Realtor.com, Apartments.com, PadMapper, Zumper, HotPads, Trulia, Facebook Marketplace) unless licensed.
2. Use of any paid API/service beyond Firecrawl and OpenAI (Mapbox, Google, TravelTime, Twilio, CoStar, Yardi, RealPage, etc.).
3. Multi-tenant SaaS or cloud-hosted product.
4. Guaranteed full coverage of all listings regardless of legal restrictions.

### 1.3 Constraints and assumptions
- Focused on San Francisco.
- Local machine can run Docker services.
- User provides Firecrawl and OpenAI API keys only.
- No login automation, CAPTCHA bypass, or proxy rotation for evasion.

### 1.4 Success criteria (operational)
- Median time-to-discovery under 6 hours for crawl-allowed sources.
- <5% stale listings in active results.
- Dedup pairwise precision >= 0.95 with conservative thresholds.
- Extraction critical-field pass rate >= 90% on golden set.
- Top-10 results show at least 3 neighborhoods by default (diversity constraint).

---

## 2) Compliance posture and source policy rules

Compliance is enforced at acquisition time and codified in a Source Policy Registry. This is a non-negotiable requirement.

### 2.1 Source policy classification
Each domain is assigned one of:
- `crawl_allowed`: robots/ToS allow automation.
- `partner_required`: licensing required; excluded unless user approves.
- `manual_only`: restricted portals; only user-provided URLs/files.
- `unknown`: blocked until reviewed.

### 2.2 Domain onboarding workflow
1. Fetch and store robots.txt (timestamped).
2. Record ToS URL and a short compliance summary.
3. Classify policy and permitted operations (search/map/crawl/scrape/manual).
4. Store policy record (versioned) in the local DB.

### 2.3 Compliance guardrails
- Only crawl domains marked `crawl_allowed`.
- Never bypass login, paywalls, or CAPTCHAs.
- Manual-only sources require user-provided artifacts (URL/file/email).
- Every acquisition task is stamped with `policy_id` and audit metadata.

### 2.4 Firecrawl compliance practices
- Always scope crawls with `limit`, `includePaths`, `excludePaths` to prevent runaway crawls.
- Use changeTracking only when markdown output is included (Firecrawl compares markdown).
- Prefer `maxAge` caching to reduce cost and load.
- Avoid stealth proxy mode unless explicitly approved.

### 2.5 Licensing and data usage rules
- Open data layers remain local; no redistribution.
- OSM data is ODbL; derived datasets must remain local unless share-alike obligations are honored.
- 511 GTFS data is non-commercial and prohibits redistribution.

### 2.6 Restricted portals (manual-only list)
The following sources are explicitly treated as `manual_only` unless the user later obtains licensing:
- Craigslist
- Zillow / HotPads / Trulia (Zillow Rental Network)
- Realtor.com
- Apartments.com (CoStar)
- PadMapper
- Zumper
- Facebook Marketplace

Manual-only handling means:
- Accept a user-pasted URL or uploaded export.
- Store the artifact as a DocumentSnapshot.
- Extract only that artifact; do not crawl or enumerate additional pages.

### 2.7 Source policy registry fields (minimum)
- `source_id`, `name`, `base_domains`
- `policy_status` (crawl_allowed | partner_required | manual_only | unknown)
- `robots_url`, `robots_snapshot_ref`
- `tos_url`, `tos_summary`
- `allowed_operations` (search, map, crawl, scrape, manual)
- `rate_limits` (qps, concurrency)
- `reviewed_by`, `reviewed_at`

### 2.8 Compliance logging
Every fetch records:
- source_id + policy_status
- fetch timestamp, status, and response headers
- applied rate limit / concurrency
- Firecrawl request parameters (formats, changeTracking, maxAge)

---

## 3) Data acquisition strategy

### 3.1 Tiered acquisition model

**Tier A: Licensed/official feeds (excluded by default)**
- MLS/IDX/RESO
- PMS/ILS feeds (Yardi, RealPage, Entrata)

These are paid/licensed. Because only Firecrawl and OpenAI are allowed paid services, these feeds are excluded by default. They can be added later behind `partner_required` if the user explicitly approves licensing.

**Tier B: Crawl-allowed long-tail sites (primary automated acquisition)**
- Property manager websites
- Building availability pages
- Broker sites where ToS allows automation

**Tier C: Manual-only sources**
- Restricted portals: Craigslist, Zillow, Realtor.com, Apartments.com, PadMapper, Zumper, HotPads, Trulia, Facebook Marketplace
- User-provided URL/file import only

### 3.2 Discovery strategy
- Firecrawl Search to discover new PM/building domains.
- Firecrawl Map to enumerate URLs.
- Sweep grid: neighborhood x price x beds x freshness.
- Query expansion: synonyms, neighborhood aliases, and “availability” keywords.

### 3.3 Task types and metadata
Task types:
- `SearchTask`: discover domains/URLs
- `MapTask`: enumerate URLs on approved domain
- `CrawlTask`: scoped crawl of listing pages
- `ScrapeTask`: refresh a single listing
- `ImportTask`: user-provided URL/file

Each task includes:
- source_id and policy_id
- scope constraints
- rate limits
- priority score
- discovery context (query, sweep cell)

### 3.4 Manual-only ingestion flow
- User pastes a URL or uploads a file.
- System captures and extracts that listing only.
- No automated polling beyond the user-provided URL.

### 3.5 Connector architecture (local-first)
Each source is represented by a connector with a consistent interface:
- `enumerate(seeds)`: return listing URLs or IDs.
- `fetch(item)`: capture raw page content (via Firecrawl or manual artifact).
- `extract(snapshot)`: produce structured fields with evidence.
- `check_status(item)`: lightweight staleness check where allowed.

This keeps acquisition pluggable without hardcoding site logic into core pipeline code.

### 3.6 Firecrawl configuration standards
Standard scrape profile for listings:
- `formats`: markdown + html + links + optional screenshot
- `changeTracking`: enabled with `git-diff` for text changes; JSON diff for price/status when stable schema is known
- `maxAge`: use cache for unchanged pages (reduce cost)
- `onlyMainContent`: false when listings hide details outside main content

Standard crawl profile for discovery:
- `limit`: hard cap per crawl job
- `includePaths`/`excludePaths`: narrow to availability/listing pages
- `maxDiscoveryDepth`: keep small to avoid marketing pages

### 3.7 Source cadence and rate limiting
Per-source budgets are stored in the registry:
- `qps` and `concurrency` per domain
- exponential backoff on 429/503
- jittered schedules to avoid spikes
- per-domain queues to enforce politeness

### 3.8 Discovery sweeps (coverage maximization)
Scheduled sweeps prevent the system from collapsing into one neighborhood or price band:
- Neighborhood sweeps (Mission, Sunset, Richmond, etc.)
- Price-band sweeps (e.g., 0-2500, 2400-3200, 3100-4000, 3900-5200, 5000+)
- Unit-type sweeps (studio/1BR/2BR/3BR+, ADU/in-law, rooms)
- Freshness sweeps (last 24h/72h/7d)

---

## 4) End-to-end pipeline (capture -> extract -> normalize -> dedupe -> rank -> alert)

### 4.1 Capture
- Firecrawl Scrape/Crawl returns raw HTML, markdown, optional screenshots, links, and changeTracking metadata.
- Manual imports store the artifact as a DocumentSnapshot.
- Snapshots are immutable, with content hashes and fetch metadata.
 - changeTracking metadata includes `changeStatus` (new/same/changed/removed) and `visibility` (visible/hidden).

### 4.2 Extraction
1. Deterministic parse (regex + JSON-LD): price, beds/baths, sqft, phone/email, dates.
2. Structured Outputs: OpenAI Responses API extracts into a strict JSON schema with evidence and confidence.
3. Vision extraction (optional): infer features like laundry, flooring, light, and noise hints.

Extraction requirements:
- Every non-null field includes evidence (text span or photo index).
- Ambiguous fields (address/unit) return multiple candidates rather than guessing.
- Extraction includes `confidence` per field and `extractor_version`.

Extraction guardrails:
- Validate schema on every response; retry with repair prompt on failure.
- Reject outputs that lack evidence for critical fields (price, beds, address).

### 4.3 Normalization
- Address parsing via libpostal.
- USPS secondary unit designators (BSMT, LOWR, REAR, etc.).
- Normalize currency, dates, lease terms, fees, amenity vocab.

Normalization rules (examples):
- “#3” -> “APT 3” when safe; preserve fractional addresses like “123 1/2”.
- Normalize bed/bath half steps (0.5 increments).
- Normalize rent ranges into low/high values.

### 4.4 Dedupe / entity resolution
- Stage 1: blocking (address tokens, geohash, phone/email, image hashes).
- Stage 2: scoring (address similarity, geo distance, unit details, text similarity, photo pHash).
- Conservative thresholds to avoid false merges.

Dedupe thresholds (initial defaults):
- Auto-merge if match probability >= 0.92
- Review band 0.75-0.92 (re-check evidence)
- Auto-separate below 0.75

Merge policy:
- Field selection uses source trust + recency + confidence.
- Keep top-K alternatives for every field.

### 4.5 Ranking
- Hard filters -> fast scoring -> LLM rerank -> diversity rerank.
- Explainability required for each listing.

### 4.6 Alerting and notifications
- Alerts are triggered by change events and matched against SearchSpecs.
- Delivery via local notifications or user-configured SMTP (no paid SMS).
- Digests summarize by neighborhood and match quality.


---

## 5) Canonical data model and provenance requirements

### 5.1 Entities
- Source
- DocumentSnapshot
- SourceObservation
- Building
- Unit
- Listing/Offer
- Fact (value + confidence + evidence)

### 5.2 Provenance requirements
- Every non-null field has evidence (text span or image index).
- Conflicting values are retained with provenance.
- Raw snapshots stored for reprocessing.

### 5.3 Schema sketch (condensed)
```
Source: id, name, policy, domains
DocumentSnapshot: id, source_id, url, fetched_at, http_status, content_hash, raw_refs, change_tracking
SourceObservation: id, snapshot_id, extracted_json, extractor_version
Building: id, address, geo, neighborhood, amenities
Unit: id, building_id, beds, baths, sqft, unit_label
Listing: id, source_id, url, status, price, availability, fees, contact, photos
Fact: field_path, value_json, confidence, evidence, source_obs_id
```

### 5.4 Fact and Evidence schema (required)
```
Fact<T> = {
  value: T | null,
  confidence: { p: number, extractor: string, at: ISODate },
  evidence: [
    { snapshot_id: UUID, kind: "text_span" | "image_region", locator: string, excerpt?: string }
  ],
  source_priority?: number
}
```

### 5.5 Canonical listing (partial example)
```
Listing {
  listing_id,
  source_id,
  url,
  status,
  price_monthly: Fact<number>,
  available_on: Fact<ISODate>,
  description: Fact<string>,
  photos: Fact<{ url, sha256?, phash? }[]>,
  contact: Fact<{ phone?, email?, name? }>,
  building_id,
  unit_id?
}
```

---

## 6) Geo and commute subsystem (open data only)

### 6.1 Geocoding
- Self-hosted Pelias or Nominatim (OSM-based).
- Local snapping with DataSF building footprints and parcels.
- Store geocode precision and confidence.

### 6.2 Routing
- OpenTripPlanner for transit (GTFS + GTFS-RT).
- Valhalla or OSRM for walk/bike/drive.
- Precompute isochrones for anchors/time buckets.

### 6.3 QoL layers
- 311 cases (noise proxy)
- Parks, street trees, bike network, crash injury data
- DBI complaints, building permits
- Elevation contours and slope layers
- Rent Board Housing Inventory (daily)
- HUD FMR and ACS data

### 6.4 Geocoding pipeline (local-only)
1. Normalize address with libpostal.
2. Generate candidate variants (include unit designators and fractional addresses).
3. Geocode via Pelias/Nominatim.
4. Snap to nearest building footprint or parcel centroid when confidence is low.
5. Store `precision` (rooftop/interpolated/zip_centroid) and `location_redaction` (exact/cross_streets/neighborhood/zip).

### 6.5 GTFS sources and update cadence (local-only)
- SFMTA GTFS: published at least quarterly; use DataSF file download.
- BART GTFS: updated when schedules change; monitor permalink.
- Caltrain GTFS: updated on schedule changes; download from Caltrain developer portal.
- 511 regional GTFS: daily build; license restricts redistribution and non-commercial only.

### 6.6 Commute caching and time buckets
- Precompute commute times for each anchor and time bucket (weekday AM/PM, weekend).
- Cache keys: `(origin_h3, anchor_id, mode, time_bucket)`.
- TTL: walking/biking months, transit days, GTFS-RT hours.

---

## 7) Ranking pipeline and diversity system

### 7.1 Stages
1. Hard filter (probabilistic on uncertain fields).
2. Fast utility scoring (price, commute, amenities, neighborhood, confidence).
3. LLM rerank (structured evidence).
4. Diversity rerank (MMR/xQuAD + caps).
5. Exploration slots.

### 7.2 Near-miss handling
- Identify which constraint failed and by how much.
- Present near-misses with explicit tradeoff explanation.

### 7.3 Scoring formula (initial default)
Utility score is a weighted sum of normalized features with confidence penalties:
```
S = sum_i w_i * (c_i * s_i + (1-c_i) * prior_i) - beta_risk * risk - beta_unc * uncertainty
```
Where:
- `s_i` is a feature satisfaction (price, commute, amenities, etc.)
- `c_i` is field confidence
- `prior_i` is a conservative default when uncertain

Price utility (example):
```
if p <= budget: 1
if budget < p <= stretch: exp(-(p-budget)/tau)
else: 0
```

Commute utility (example):
```
if t <= target: 1
if target < t <= max: exp(-(t-target)/tau_c)
else: 0
```

### 7.4 Diversity rerank
- MMR (relevance vs novelty) as baseline.
- Caps: max per building, max per neighborhood, max per source.
- Optional xQuAD for explicit aspect coverage (neighborhood, building type, price band).

### 7.5 Candidate retrieval
- Structured filters (price, beds, neighborhood) in Postgres.
- Full-text search on descriptions and amenities.
- Semantic retrieval using OpenAI embeddings stored in pgvector.
- Retrieve top-N candidates before LLM rerank.

### 7.6 SearchSpec structure (input to ranking)
SearchSpec is derived from NL input and includes:
- Hard constraints (max rent, min beds, commute max, pet policy).
- Soft preferences with weights (sunlight, quiet, modern style).
- Tradeoffs (e.g., $ vs commute minutes).
- Commute anchors with time windows and modes.

---

## 8) Freshness, change detection, and recrawl scheduler

### 8.1 Change detection
- Firecrawl changeTracking (new/same/changed/removed).
- Local content hashes and field-level hashes.

### 8.2 Scheduler
- Adaptive cadence per source.
- Two-lane queue: index vs detail.
- Error backoff and politeness.

### 8.3 Scheduler scoring formula (initial)
Priority score for a URL or source:
```
score = w_source * source_velocity
      + w_change * estimated_change_prob
      + w_interest * user_interest
      - w_age * page_age
      - w_fail * error_penalty
```

### 8.4 TTL and staleness rules
- High-churn PM sites: TTL 48-72h unless re-seen.
- Static broker pages: TTL 7-14 days.
- Manual-only sources: TTL only when user refreshes.

---

## 9) Evaluation and QA plan

- Golden extraction set (200-500 listings).
- Dedupe pairs (200 duplicates + 200 non-duplicates).
- Ranking labels (0-3 relevance scale).
- Metrics: extraction accuracy, dedupe F1, freshness, coverage, NDCG@k.
- Regression suite with frozen HTML snapshots.

Additional evaluation mechanics:
- Weekly audits: sample new listings and verify critical fields.
- Missed-listing sweeps: independent searches to detect blind spots.
- Capture-recapture estimates to approximate recall by source.
- Regression gates: block releases if key metrics drop beyond thresholds.
 - Nightly OpenAI Batch jobs for re-extraction and embedding refresh.

---

## 10) UI/UX feature summary

- Onboarding with NL intake + structured SearchSpec preview.
- Split map/list view with commute overlays.
- Listing detail with evidence and change history.
- Compare view.
- Near-miss explorer.
- Pipeline board.
- Alerts center.

UX principles:
- Always show “why this matches” and “what is missing”.
- Near-miss explorer exposes tradeoffs explicitly.
- Diversity dial lets user control explore vs strict ranking.

---

## 11) Local deployment architecture

### 11.1 Services
- API server (FastAPI)
- Scheduler (APScheduler)
- Workers (Celery/RQ or asyncio)
- Postgres + PostGIS
- pgvector
- Redis
- Object store (FS or MinIO)
- OpenTripPlanner
- Valhalla or OSRM

### 11.2 Orchestration
- CLI commands: ingest, extract, normalize, dedupe, rank, alert, geo-sync, eval.

### 11.3 Storage choices
- Postgres + PostGIS is the source of truth.
- pgvector for embeddings (dedupe + semantic search).
- Object store for raw HTML, markdown, screenshots, and images.
- Redis for queues and short-lived caches.

---

## 12) Security and privacy

- All data local.
- Secrets stored in env files.
- API bound to localhost.
- PII minimized and redacted.
- Compliance logs retained.

Additional safeguards:
- Encrypt backups if user opts in.
- Separate API keys from data volumes.
- Provide a “delete all data” command for local reset.

---

## 13) Implementation phases

### MVP (weeks 0-2)
- Source registry + policy gating
- Firecrawl crawl/scrape on 10-30 allowed PM sites
- Extraction v1 + normalization
- Basic dedupe
- Postgres + PostGIS
- Simple UI + daily digest alerts

### Month 1
- OTP routing + GTFS
- Advanced extraction (fees, lease terms, pets)
- Diversity rerank + near-miss
- Golden sets + regression tests
- QoL layers (311, parks, bike network)

### Month 3
- Adaptive scheduler + change detection
- Vision extraction
- Value engine using Rent Board data
- Advanced dedupe with embeddings + pHash
- Expanded discovery (100+ domains)

Acceptance milestones:
- MVP: end-to-end crawl -> extract -> rank -> alert for at least 10 sources.
- Month 1: commute-aware ranking and golden-set evaluation gates in place.
- Month 3: adaptive scheduler and advanced dedupe reduce duplicates by >30%.

---

## 14) Open questions

1. Queue system choice (Redis/RQ vs Celery vs Postgres-based queue).
2. Geocoder choice (Pelias vs Nominatim).
3. Routing engine choice (Valhalla vs OSRM).
4. UI scope (minimal vs full SPA).
5. Use of 511 GTFS feeds given licensing restrictions.
6. Object storage (filesystem vs MinIO).

---

## 15) High-level component spec

A complete component spec is provided in `architecture_components.md`.
