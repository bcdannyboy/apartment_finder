STATUS: Non-authoritative research notes. Superseded where conflicts with architecture_source_of_truth.md and architecture_decisions_and_naming.md.

Overrides:
- Paid services limited to OpenAI and Firecrawl.
- Retrieval uses Postgres FTS + pgvector only.
- Extraction is centralized in Extraction Service; connectors do not extract.
- Manual-only sources are ImportTask only; no automated crawling.
- Geo and routing are local-only (Pelias, Nominatim fallback, OTP, Valhalla; OSRM secondary).
- Alerts are local notifications or SMTP only.

## Executive summary

* **Two-tier acquisition**: (A) *licensed/official feeds where needed*, (B) *compliant crawling + discovery* for long-tail PM/broker sites; **no botting/CAPTCHA bypass** on prohibited marketplaces. ([craigslist][1])
* **Provenance-first data pipeline**: store every raw snapshot + structured extraction + field-level confidence/evidence, so you can trust, audit, and re-process.
* **Hybrid extraction**: deterministic parsers when templates are known; otherwise **OpenAI Structured Outputs** for schema-perfect JSON extraction + vision for photos/floorplans. ([OpenAI Platform][2])
* **Entity resolution that works in SF reality**: address normalization + unit disambiguation (basements/upper/lower, fractional addresses, missing unit numbers) + cross-post dedupe. ([Postal Explorer][3])
* **Geo/commute engine as a first-class service**: PostGIS + neighborhood polygons + **time-of-day multimodal commute** via OTP/GTFS + Valhalla isochrones/matrices. ([OpenTripPlanner][4])
* **Ranking that avoids “same-y results”**: strict filters → high-recall candidate pool → calibrated utility scoring → LLM rerank → diversity-aware rerank (MMR x neighborhoods x source x price bands).
* **Freshness + change detection**: adaptive recrawl scheduler + diffing; optionally use Firecrawl change tracking for “new/same/changed/removed” and visibility. ([Firecrawl][5])
* **Coverage maximization loops**: systematic sweeps (neighborhood × bed × price × time) + discovery via Firecrawl Search/Map/Crawl + missed-listing audits. ([Firecrawl][6])
* **UI optimized for decisions**: map+list, “why it matches”, “what’s missing”, fast compare, and a pipeline board (New → Shortlist → Contacted → Tour → Applied).
* **Evaluation is built-in from day 1**: golden sets + regression suites + coverage & freshness dashboards; use Batch for cheap nightly re-extraction/reranks. ([OpenAI Platform][7])

---

## Project constraints overlay (authoritative for this repo)
- Only paid services: Firecrawl and OpenAI.
- Local-first only; services bind to localhost.
- Geo/commute: Pelias + OpenTripPlanner + Valhalla only (no paid geo APIs).
- Retrieval: Postgres FTS + pgvector only (no external search or vector DB).
- Alerts: local notifications or SMTP only.
- Queue: Redis + RQ.
- Object storage: filesystem.
- UI: full SPA.
- Evidence storage: normalized Evidence table with fact_evidence links.

## Final architecture diagram

```
                     ┌──────────────────────────────────────────────────┐
                     │                     UI / API                      │
                     │  Search + Chat  | Map/Compare | Shortlist | Alerts│
                     └───────────────▲───────────────────────┬──────────┘
                                     │                       │
                          (query)    │                       │ (watch profiles)
                                     │                       ▼
┌────────────────────────────────────┴──────────────┐  ┌───────────────┐
│          Retrieval + Ranking Service               │  │ Alert Engine   │
│  hard filters → candidate retrieval → scoring →    │  │ new/changed/   │
│  LLM rerank → diversity rerank → explanations      │  │ price drops    │
└───────────────▲───────────────────────┬───────────┘  └──────▲────────┘
                │                       │                     │
                │                       │ indexes             │ events
                │                       ▼                     │
        ┌───────┴─────────────────────────────────────────────┴───────┐
        │                   Canonical Data Platform                     │
        │  Postgres + PostGIS (truth) | Postgres FTS + pgvector          │
        │  Objects (filesystem raw HTML/MD/screens) | Audit Logs         │
        └───────▲───────────────────────────────▲──────────────────────┘
                │                               │
     enrichment  │                               │ extraction/ER
                │                               │
┌───────────────┴──────────────┐     ┌──────────┴──────────────────────┐
│ Geo + Commute Enrichment      │     │ Extraction + Normalization       │
│ - geocode (primary+fallback)  │     │ - deterministic + LLM extraction  │
│ - neighborhoods/H3            │     │ - schema validation               │
│ - OTP/GTFS + Valhalla          │     │ - dedupe/entity resolution        │
│ - QoL layers (noise, hills...)│     │ - field-level confidence/evidence │
└───────────────▲──────────────┘     └──────────▲──────────────────────┘
                │                                 │
                │                                 │ raw snapshots
                │                                 ▼
        ┌───────┴─────────────────────────────────────────────┐
        │          Acquisition + Discovery Orchestrator        │
        │  preference→SearchSpec→task planner→compliance gate→ │
        │  source tasks (API / Firecrawl / manual import)      │
        └───────▲──────────────────────────▲──────────────────┘
                │                          │
        schedule │                          │ discovery
                │                          │
     ┌──────────┴───────────┐     ┌────────┴─────────────────────┐
     │ Continuous Scheduler   │     │ Connector Registry           │
     │ - cadence per source   │     │ - ToS/robots classification  │
     │ - backoff/retries      │     │ - query templates & sweeps   │
     │ - change-driven recrawl│     │ - seed URLs / sitemaps       │
     └────────────────────────┘     └─────────────────────────────┘
```

---

## Final architecture

### 1) Connectors and acquisition

**Core idea**: treat “sources” as plug-ins with explicit *capabilities* + *compliance mode*:

* **Tier A: Licensed / Official feeds (best coverage, safest)**

  * MLS/IDX/RESO Web API access (where rentals available) and/or ListHub-style feeds; RESO provides the transport standard; credentials come from MLS agreements. ([RESO][8])
  * Property management systems (PMS) vacancy feeds (often obtainable via partnership).
  * Paid aggregators (CoStar/Yardi/RealPage etc) *if you can license their data for personal use*.

* **Tier B: Compliant crawling + long-tail discovery (high recall of “hidden gems”)**
  Use Firecrawl to discover and crawl *allowed* PM/broker/building sites:

  * **Search** the web + optionally scrape results to bootstrap seeds. ([Firecrawl][6])
  * **Map** a domain to enumerate URLs quickly (availability pages, sitemaps, floorplan pages). ([Firecrawl][9])
  * **Crawl** domains / sections to fetch all relevant listing pages. ([Firecrawl][10])
  * **Extract** structured datasets from lists of URLs (including wildcards). ([Firecrawl][11])
  * **Change tracking** to detect what changed between scrapes. ([Firecrawl][5])

* **Tier C: “Restricted marketplaces” integration without ToS violations**
  Many big portals explicitly forbid automated queries/scraping (and Realtor.com forbids use of content for ML/AI). ([craigslist][1])
  For these, your compliant options are:

  1. **Partner/license** (preferred, with unlimited budget), or
  2. **User-provided inputs**: paste listing URLs, forward emails, or upload exported CSVs where the platform provides export—then your system extracts and tracks changes from the user-provided artifact (not by automated crawling).

**Acquisition data flow**

1. NL criteria → structured `SearchSpec`
2. Planner chooses sources and produces tasks:

   * `SearchTask` (web discovery)
   * `CrawlTask` (domain crawl)
   * `ScrapeTask` (single URL refresh)
   * `ImportTask` (user-provided URL/file)
3. Workers execute with strict per-source rate limits and compliance gates.
4. Store raw snapshot + metadata (HTTP status, fetched_at, etag, etc) to raw store.

---

### 2) Extraction, normalization, and dedupe

**Key principle: provenance-first.** Every field is a *fact* with confidence and evidence.

Extraction pipeline (per document snapshot):

1. **Render → canonical text**

   * Keep `raw_html`, `main_content_markdown`, `links`, `screenshots` where useful (Firecrawl supports multiple formats including screenshot and changeTracking in scrape). ([Firecrawl][12])
2. **Deterministic extraction pass**

   * Regexes + micro-parsers for price formats, bed/bath patterns, sqft, phone/email, date phrases.
3. **LLM structured extraction pass**

   * Use **OpenAI Responses API** (text + images) to extract listing fields and infer from images when helpful (e.g., “has in-unit laundry?” from photo evidence). ([OpenAI Platform][2])
   * Use **Structured Outputs** so extraction *must* match your JSON schema (no missing keys, no invalid enums). ([OpenAI Platform][13])
4. **Schema validation + normalization**

   * Normalize currency, units, dates, pet policy vocab, fee types.
5. **Entity resolution + dedupe**

   * Address normalization (libpostal) + building fingerprint (street + number + lat/lng cell). ([GitHub][14])
   * Handle unit designators like BSMT/LOWR/UPPR/etc per USPS guidance. ([Postal Explorer][3])
   * Handle fractional addresses (e.g., “13 1/2”) per USPS addressing notes. ([Postal Explorer][15])
   * Cross-post dedupe signals: identical phone/email, image perceptual hashes, description simhash, and “same building + similar unit + close price + close posted date”.

**Output**: canonical `Listing` + `Building` + `Unit` entities, with `Observation` history and `Fact` provenance.

---

### 3) Geo enrichment

**Primary store**: Postgres + PostGIS.

Geo enrichment steps:

1. **Geocode** (address → lat/lng + precision)

   * Use **Pelias (self-hosted)** as primary for unlimited local queries.
   * Use **Nominatim (self-hosted)** as optional fallback when Pelias confidence is low.
2. **Neighborhood / polygon membership**

   * Assign SF neighborhoods, planning districts, school zones, etc (DataSF).
3. **Terrain + microclimate proxies**

   * Slope/elevation for bike/hill difficulty, wind/fog exposure proxies (optional, month 2–3).
4. **Commute analysis**

   * **OpenTripPlanner (OTP)** for multimodal transit/bike/walk itineraries using OSM + GTFS. ([OpenTripPlanner][4])
   * Feed OTP with **511 SF Bay GTFS + GTFS-RT** (token-based, bulk and API). ([511.org][18])
   * **Valhalla** for walk/bike/drive matrices and isochrones (local only).

---

### 4) Ranking + diversity-aware retrieval

Ranking is multi-objective: **(match quality) + (coverage diversity) + (freshness) + (confidence)**.

Pipeline:

1. **Hard filter**: must-haves (budget ceiling, min beds, pet constraint, commute max, etc).
2. **Candidate retrieval**:

   * Postgres FTS + pgvector over descriptions and amenity text. OpenAI embeddings are stored in pgvector. ([OpenAI Platform][21])
3. **Utility scoring** (fast model):

   * `utility = Σ w_i * feature_i` where `feature_i` includes: price value score, commute score, neighborhood preference, amenity match, risk penalties.
   * Penalize low-confidence extractions.
4. **LLM rerank** (top ~100 → ~20):

   * Use Responses API with a rubric: “Given user’s SearchSpec, rank and explain tradeoffs.”
   * Enforce structured output: `(rank, reasons, missing_info_questions)`.
5. **Diversity rerank** (final list):

   * Apply MMR-like approach to avoid same neighborhood/building/source duplicates.
   * Enforce quotas: e.g., “at least 1 Mission, 1 Hayes, 1 Inner Sunset”, “at most 2 from same PM”, “include 2 exploration picks”.

---

### 5) Continuous discovery and freshness

You want **time-to-discover** and **time-to-notice-change** near real-time.

Mechanisms:

* **Scheduler** maintains per-source cadences:

  * Fast-moving sources: every 10–30 minutes (if licensed)
  * PM availability pages: every 2–6 hours
  * Static broker “available rentals” pages: daily
* **Adaptive recrawl**:

  * Increase frequency when a source is “hot” (many changes) or has historically high hit rate.
* **Change detection**:

  * Firecrawl changeTracking provides `changeStatus` (new/same/changed/removed) and visibility which is perfect for “listing removed” or “hidden but still accessible” cases. ([Firecrawl][5])
  * Also compute your own `content_hash` and `normalized_field_hash` for diffing at the extracted-field level.
* **Backfills**:

  * Weekly deep crawls for long-tail sources.
  * Nightly “re-extract everything changed in last 24h” via OpenAI Batch API for cost-efficient bulk runs. ([OpenAI Platform][7])

---

### 6) UI + alerting

UI should support the real hunting workflow:

**Core screens**

* **Chat → SearchSpec**: user describes needs; system shows the parsed constraints (hard vs soft) and lets user edit.
* **Map + List**: filters + commute overlays + neighborhood boundaries.
* **Listing detail**:

  * “Why it matches”
  * “What’s missing / verify these”
  * Source evidence: show the snippet/photo that supports key fields
  * Change history: price drops, availability changes, description edits
* **Compare view**: 2–4 listings with structured field comparison.
* **Pipeline board**: New → Considering → Shortlisted → Contacted → Tour scheduled → Applied → Won/Lost.

**Alerting**

* Profile-based alerts: new matches, price drops, availability date changes, “listing removed”.
* Delivery: local notifications or SMTP email only.

---

## Canonical schema

Condensed (TypeScript-ish). This is the “truth model”; you can store as relational tables + JSONB for flexible facts.

```ts
type UUID = string;
type ISODate = string;
type URL = string;

type Confidence = { p: number; reason?: string; extractor: string; at: ISODate };
type EvidenceRef = {
  snapshot_id: UUID;
  kind: "text_span" | "image_region" | "dom_path";
  locator: string;          // e.g., xpath/css or byte offsets
  excerpt?: string;         // short snippet (<=200 chars)
};

type Fact<T> = {
  value: T | null;
  confidence: Confidence;
  evidence?: EvidenceRef[];
  source_priority?: number; // per-source trust rank
};

type Source = {
  source_id: UUID;
  name: string;
  kind: "licensed_feed" | "pm_site" | "broker_site" | "marketplace" | "user_import";
  compliance_mode: "crawl_allowed" | "partner_required" | "manual_only";
  base_domains: string[];
};

type DocumentSnapshot = {
  snapshot_id: UUID;
  source_id: UUID;
  url: URL;
  fetched_at: ISODate;
  http_status: number;
  etag?: string;
  content_hash: string;
  formats: { markdown?: boolean; html?: boolean; screenshot?: boolean; changeTracking?: boolean };
  storage_refs: { raw_html?: string; markdown?: string; screenshot?: string };
  change_tracking?: { previous_scrape_at?: ISODate; status?: "new"|"same"|"changed"|"removed"; visibility?: "visible"|"hidden" };
};

type Address = {
  raw: string;
  normalized: string;           // libpostal + rules
  street: string;
  city: "San Francisco";
  state: "CA";
  postal_code?: string;
  unit?: string;                // "#5", "LOWR", "BSMT", etc.
};

type GeoPoint = { lat: number; lng: number; precision: "rooftop"|"interpolated"|"zip_centroid"|"unknown"; provider: string };

type Building = {
  building_id: UUID;
  address: Address;
  geo: Fact<GeoPoint>;
  neighborhood: Fact<string>;   // from polygons
  property_type: Fact<"apartment"|"condo"|"sfh"|"townhome"|"room"|"unknown">;
  year_built?: Fact<number>;
  amenities?: Fact<string[]>;   // building-level
  manager?: Fact<{ name?: string; phone?: string; email?: string; website?: string }>;
};

type Unit = {
  unit_id: UUID;
  building_id: UUID;
  unit_label: Fact<string>;     // "Unit 3", "LOWR", etc.
  beds: Fact<number>;
  baths: Fact<number>;
  sqft?: Fact<number>;
  floorplan?: Fact<string>;
  unit_amenities?: Fact<string[]>;
};

type Listing = {
  listing_id: UUID;
  source_id: UUID;
  source_listing_key?: string;  // stable per source if available
  url: URL;
  status: "active"|"pending"|"off_market";
  first_seen_at: ISODate;
  last_seen_at: ISODate;

  building_id: UUID;
  unit_id?: UUID;

  price_monthly: Fact<number>;
  deposit?: Fact<number>;
  fees?: Fact<{ name: string; amount?: number; cadence?: "one_time"|"monthly" }[]>;
  available_on?: Fact<ISODate>;
  lease_terms?: Fact<string>;   // "12 months", etc.

  description: Fact<string>;
  photos: Fact<{ url: URL; sha256?: string }[]>;
  contact: Fact<{ phone?: string; email?: string; name?: string; application_url?: URL }>;

  policies?: Fact<{ pets?: string; smoking?: string; parking?: string }>;
  observations: UUID[];         // snapshot ids
};

type CommuteTarget = { label: string; lat: number; lng: number };
type CommuteResult = {
  listing_id: UUID;
  target_label: string;
  mode: "transit"|"drive"|"bike"|"walk";
  depart_time: ISODate;
  duration_sec: number;
  transfers?: number;
  reliability?: number;         // computed later
  provider: string;
};

type SearchSpec = {
  spec_id: UUID;
  created_at: ISODate;
  raw_prompt: string;

  hard: {
    price_max?: number;
    beds_min?: number;
    baths_min?: number;
    neighborhoods_include?: string[];
    neighborhoods_exclude?: string[];
    commute_max_min?: { target: string; mode: string; max_min: number }[];
    must_have?: string[];        // e.g. ["in_unit_laundry"]
    exclude?: string[];          // e.g. ["shared_bath"]
  };

  soft: {
    weights: Record<string, number>; // amenity/area preferences
    nice_to_have?: string[];
    vibe?: string[];                 // proxies mapped to features later
  };

  exploration: { pct: number; rules?: string[] }; // diversity budget
};

type Match = {
  search_spec_id: UUID;
  listing_id: UUID;
  retrieved_at: ISODate;
  scores: {
    utility: number;
    freshness: number;
    confidence: number;
    diversity_penalty: number;
    final: number;
  };
  explanation: { why: string[]; tradeoffs: string[]; verify: string[] };
};
```

---

## Roadmap

### Week 1–2 MVP (useful immediately for SF hunting)

**Goal**: you can describe what you want, get a strong list + map, and receive alerts on good new listings.

Deliverables:

* **SearchSpec parser** (NL → hard/soft constraints) using Responses + Structured Outputs. ([OpenAI Platform][2])
* **Connector registry v1**:

  * Tier B sources: 10–30 SF PM/broker/building sites you can legally crawl.
  * Discovery: Firecrawl Search to find new PM “availability” pages. ([Firecrawl][6])
* **Crawl + scrape workers**:

  * Firecrawl Map + Crawl + Scrape for allowed domains. ([Firecrawl][9])
* **Extraction v1**:

  * price, beds, baths, address, availability, contact, photos, laundry/parking/pets.
  * store raw snapshots and extracted JSON.
* **Dedupe v1**:

  * address + unit label + phone/email + image hash.
* **Geo v1**:

  * geocode (Pelias), neighborhood assignment, distance-to-anchors, basic drive matrix via Valhalla.
* **UI v1**:

  * list+map, filters, save/hide, notes, compare, shortlist.
* **Alerts v1**:

  * daily digest + instant alert for “top 5 new matches”.

### Month 1 “serious”

**Goal**: better accuracy, fewer duplicates, richer fields, real commute intelligence, personalization.

Deliverables:

* **Extraction v2**:

  * full fees/deposit/lease terms, specials, move-in costs
  * multimodal vision extraction for photos/floorplans (light, room count plausibility).
* **Entity resolution v2**:

  * strong building graph (same building across sources)
  * advanced address normalization (libpostal + USPS unit rules). ([GitHub][14])
* **Commute engine v2**:

  * OTP running locally + 511 GTFS feeds; compute time-of-day transit. ([OpenTripPlanner][4])
  * isochrone overlays (Valhalla, local only).
* **Ranking v2**:

  * LLM rerank + diversity rerank
  * learn from thumbs up/down + “why did you like this?” prompts.
* **Freshness v2**:

  * adaptive recrawl + Firecrawl change tracking integration. ([Firecrawl][5])
* **Evaluation harness v1**:

  * golden set, extraction regressions, dedupe audits, freshness dashboards.
* **Manual-only integrations** for restricted portals:

  * “paste URL” import; track changes from imported links (no automated crawling).

### Months 2–3 “ultimate”

**Goal**: maximum coverage (legally), high-confidence scoring, “don’t miss the gem”, and decision speed.

Deliverables:

* **Licensed coverage expansion**:

  * negotiate feed access (MLS/IDX/RESO Web API where possible; PMS/aggregator deals). ([RESO][8])
* **Coverage maximization system**:

  * automated sweeps across neighborhoods × budgets × bed counts × time windows
  * missed-listing detection loop and source health scoring.
* **Advanced enrichment layers**:

  * building “risk” and “quality-of-life” indices (noise, hills, microclimate proxies, safety, 311/permits).
* **Value engine**:

  * fair-rent model to flag underpriced units and suspiciously underpriced scams.
* **Batch reprocessing**:

  * nightly Batch jobs for re-extraction + embedding refresh + rerank. ([OpenAI Platform][7])
* **Power user workflow**:

  * email templates, tour scheduling support, document checklist, “apply now” playbook.

---

## Coverage maximization strategy

### Connector priority order

1. **Licensed/official feeds** (highest ROI once obtained): MLS/IDX/RESO, PMS vacancy feeds, data aggregators. ([RESO][8])
2. **SF long-tail PM & broker sites** (your “hidden gem moat”): boutique PMs, small brokerages, building sites with “availability” pages.
3. **New-source discovery via web search**:

   * daily Firecrawl Search runs for phrases like:

     * “San Francisco apartments available now”
     * “site:*.com ‘San Francisco’ ‘availability’ ‘studio’”
   * auto-suggest new seed domains for review. ([Firecrawl][6])
4. **Restricted marketplaces**:

   * partner/license if you want true automation; otherwise manual import only. ([craigslist][1])

### Systematic sweeps

For each compliant connector, define a *sweep grid*:

* **Neighborhood sweep**: SF neighborhoods (polygon list) × radius expansions
* **Price sweep**: max price buckets (e.g., 2500/3000/3500/4000/5000)
* **Unit-type sweep**: studio/1/2/3 + “junior 1BR” + “room”
* **Freshness sweep**: posted in last 24h / 72h / 7d
* **Exploration sweep**: “weird but good” queries (e.g., “garden unit”, “in-law”, “Top floor”, “Victorian flat”)

Then:

* generate tasks per (connector × sweep cell)
* cap per-source QPS; store run history
* measure yield per cell and adapt (prune low-yield, expand high-yield)

### Missed-listing detection loops

* **Search-engine cross-check**: for each neighborhood + bed + price cell, run daily web search and confirm top domains are either covered or intentionally excluded. ([Firecrawl][6])
* **Inventory baselining** (when you buy data): compare building/unit coverage against paid inventory datasets; flag missing buildings.
* **Change-driven discovery**: when you find a building/PM contact, automatically discover *other* properties by the same manager (website and internal cross-links).
* **Randomized canaries**: pick 20 “test cells” each day and compute:

  * new listings found
  * duplicates
  * time-to-detect

---

## Evaluation plan

### Metrics (tracked daily)

**Extraction accuracy**

* Field-level precision/recall for: price, beds, baths, address, availability, fees, pet policy
* “Unknown rate” and “needs verification rate” per field
* Schema validation failure rate (should be near-zero with Structured Outputs). ([OpenAI Platform][13])

**Dedupe / entity resolution**

* Pairwise duplicate F1
* Cluster purity (one real unit per cluster)
* Address normalization error rate (unit mistakes, fractional address mistakes). ([Postal Explorer][3])

**Coverage**

* Unique active listings/day
* Source diversity: entropy across sources + neighborhoods
* Yield per sweep cell (listings discovered / tasks run)

**Freshness**

* Time-to-discover (first_seen - source_posted)
* Time-to-detect-change (change observed - actual change time proxy)
* Stale listing rate (still shown active after removal)

**Ranking**

* NDCG@k / HitRate@k on your own feedback (likes, shortlists, tours)
* Diversity score (neighborhood/source/price dispersion)

### Golden sets + audits

* **Golden extraction set**: 200–500 representative listings (raw snapshots + human-labeled JSON).
* **Golden dedupe set**: 200 known duplicate pairs + 200 known non-duplicates.
* **Weekly audit**:

  * sample 25 new listings, manually verify top fields
  * sample 25 changed listings, verify diffs are correct
* **Regression tests (CI)**:

  * run extraction on stored snapshots; compare expected JSON (tolerant to minor text differences)
  * run dedupe clustering; compare expected merges
* **Nightly “reprocess changed snapshots”** using Batch API for cheap bulk evaluation + backfills. ([OpenAI Platform][7])

---

## Build vs buy table

| Component             | Build | Buy | Recommendation                                 | Why                                                                                                          |
| --------------------- | ----: | --: | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Web crawl/render      |       |   ✅ | **Firecrawl** + fallback lightweight fetcher   | Search/Map/Crawl/Extract + change tracking accelerates long-tail coverage. ([Firecrawl][6])                  |
| LLM extraction/rerank |       |   ✅ | **OpenAI Responses + Structured Outputs**      | Schema-perfect extraction, multimodal, tool calling. ([OpenAI Platform][2])                                  |
| Batch reprocessing    |       |   ✅ | **OpenAI Batch API**                           | 50% lower cost, high rate limits, 24h SLA—ideal for nightly re-extraction/embeddings. ([OpenAI Platform][7]) |
| Embeddings            |       |   ✅ | OpenAI embeddings + pgvector                   | Designed for semantic search/recs. ([OpenAI Platform][21])                                                   |
| Vector store          |     ✅ |     | **pgvector**                                   | Local-only vector storage.                                                                                   |
| Relational + geo      |     ✅ |     | **Postgres + PostGIS**                         | Canonical truth + geo joins.                                                                                 |
| Search index          |     ✅ |     | **Postgres FTS**                               | Fast filters + text queries with local storage.                                                              |
| Geocoding             |     ✅ |     | **Pelias primary; Nominatim fallback**         | Local-only geocoding with full control.                                                                      |
| Commute routing       |     ✅ |     | **OTP + 511 GTFS + Valhalla**                  | Local-only routing with transit and walk/bike/drive. ([OpenTripPlanner][4])                                  |
| Address normalization |     ✅ |     | libpostal                                      | Proven address normalization for dedupe. ([GitHub][14])                                                      |
| Marketplace data      |       |   ✅ | **License/partner or manual import**           | ToS often prohibits automated access/scraping/AI use. ([craigslist][1])                                      |
| Notifications         |     ✅ |     | Local notifications or SMTP                    | Local-only delivery.                                                                                         |
| Observability         |     ✅ |     | Local Prometheus + Grafana                     | Local-only metrics and dashboards.                                                                           |

---

## Key tradeoffs and decisions

* **Compliance vs “all sources”**: You *cannot* safely automate scraping on several major portals without licensing; build the system so those sources are either **partner feeds** or **manual-only imports**. ([craigslist][1])
* **Provenance-first is non-negotiable**: it’s the only way to keep accuracy high while scaling to messy long-tail sources; it also enables trustworthy UI (“show me where you got that pet policy”).
* **Local-first geo**: Pelias + OTP + Valhalla keep geocoding and routing local and compliant.
* **Hybrid extraction beats “LLM-only”**: deterministic extraction reduces cost/latency and improves stability; LLM handles tail cases and normalizes messy language—Structured Outputs reduces fragility. ([OpenAI Platform][13])
* **Diversity is a product feature**: you’ll miss great apartments if the system collapses to “same neighborhood, same PM, same vibe.” Make diversity a first-class rerank objective.
* **Freshness is an engineering feature**: adaptive recrawl + change tracking beats naive “crawl everything daily”; measure time-to-discover and time-to-detect-change. ([Firecrawl][5])
* **Commute is “truth,” not decoration**: invest early in correct transit + time-of-day modeling (OTP + 511). ([OpenTripPlanner][4])

---

## Juror reports referenced

        

[1]: https://www.craigslist.org/about/terms.of.use "https://www.craigslist.org/about/terms.of.use"
[2]: https://platform.openai.com/docs/api-reference/responses "https://platform.openai.com/docs/api-reference/responses"
[3]: https://pe.usps.com/text/pub28/28apc_003.htm "https://pe.usps.com/text/pub28/28apc_003.htm"
[4]: https://www.opentripplanner.org/ "https://www.opentripplanner.org/"
[5]: https://docs.firecrawl.dev/features/change-tracking "https://docs.firecrawl.dev/features/change-tracking"
[6]: https://docs.firecrawl.dev/features/search "https://docs.firecrawl.dev/features/search"
[7]: https://platform.openai.com/docs/guides/batch "https://platform.openai.com/docs/guides/batch"
[8]: https://www.reso.org/reso-web-api/ "https://www.reso.org/reso-web-api/"
[9]: https://docs.firecrawl.dev/features/map "https://docs.firecrawl.dev/features/map"
[10]: https://docs.firecrawl.dev/features/crawl "https://docs.firecrawl.dev/features/crawl"
[11]: https://docs.firecrawl.dev/features/extract "https://docs.firecrawl.dev/features/extract"
[12]: https://docs.firecrawl.dev/api-reference/v1-endpoint/scrape "https://docs.firecrawl.dev/api-reference/v1-endpoint/scrape"
[13]: https://platform.openai.com/docs/guides/structured-outputs "https://platform.openai.com/docs/guides/structured-outputs"
[14]: https://github.com/openvenues/libpostal "https://github.com/openvenues/libpostal"
[15]: https://pe.usps.com/text/pub28/28ape_004.htm "https://pe.usps.com/text/pub28/28ape_004.htm"
[16]: https://docs.mapbox.com/api/search/geocoding/ "https://docs.mapbox.com/api/search/geocoding/"
[17]: https://cloud.google.com/archive/maps-platform/terms/maps-service-terms-20240909 "https://cloud.google.com/archive/maps-platform/terms/maps-service-terms-20240909"
[18]: https://511.org/open-data/transit "https://511.org/open-data/transit"
[19]: https://docs.mapbox.com/api/navigation/matrix/ "https://docs.mapbox.com/api/navigation/matrix/"
[20]: https://docs.traveltime.com/ "https://docs.traveltime.com/"
[21]: https://platform.openai.com/docs/guides/embeddings "https://platform.openai.com/docs/guides/embeddings"
[22]: https://docs.traveltime.com/api/overview/isochrones "https://docs.traveltime.com/api/overview/isochrones"
