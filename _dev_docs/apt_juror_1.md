STATUS: Non-authoritative research notes. Superseded where conflicts with architecture_source_of_truth.md and architecture_decisions_and_naming.md.

Overrides:
- Paid services limited to OpenAI and Firecrawl.
- Retrieval uses Postgres FTS + pgvector only.
- Extraction is centralized in Extraction Service; connectors do not extract.
- Manual-only sources are ImportTask only; no automated crawling.
- Geo and routing are local-only (Pelias, Nominatim fallback, OTP, Valhalla; OSRM secondary).
- Alerts are local notifications or SMTP only.

## 10-bullet summary (Coverage & Acquisition verdict)

1. **The big portals you listed (Craigslist, Zillow, Realtor.com, Apartments.com, PadMapper, Zumper)** explicitly restrict “robots/spiders/scraping/automated queries” in their Terms—so for a compliant system, you either (a) **license/partner**, (b) use **first‑party feeds/alerts that the site itself provides**, or (c) treat them as **manual-only** and focus your automation elsewhere. ([craigslist][1])
2. **Maximum SF recall comes from “origin capture”:** property management companies + their PMS/ILS syndication feeds + building sites (where permitted), because many listings originate there *before* being copied into portals.
3. **Buy coverage where it’s rational:** license data platforms like **CoStar (multifamily market + inventory data)** and **Yardi Matrix (researched multifamily property data)**; integrate **RealPage APIs** if you’re connecting into their ecosystem. ([CoStar][2])
4. **MLS rentals / broker-listed inventory**: integrate via **RESO Web API** through a broker/MLS/vendor (Bridge, Spark, etc.). This won’t cover every mom‑and‑pop rental, but it’s high-quality structured inventory. ([reso.org][3])
5. **For HotPads specifically:** there’s an official **Rental Listing Bulk Feed Guide** (supply-side syndication). That tells you the “official” direction of data flow (publishers → HotPads/Zillow), not a public consumer listings API. ([Amazon Web Services, Inc.][4])
6. Build acquisition as a **connector portfolio**: direct feeds/APIs first, then permitted Firecrawl crawlers for the long tail, then user-facing “alerts/import links” for restricted sources.
7. Freshness wins come from **adaptive polling** + **delta detection** + **fast stale removal**: per-source cadence, per-URL hashing/ETag, and TTL policies.
8. Diversity is a scheduling problem: implement a **search diversity engine** that runs neighborhood/price/unit-type sweeps and allocates more budget to “high yield” slices without collapsing into one slice.
9. Dedup is not optional: unify listings across sources using address+unit+geo, contact info, description embeddings, and image perceptual hashes (pHash) to reduce spam/duplicates.
10. Measure “coverage” without perfect ground truth via **overlap-based estimation (capture–recapture)** + source contribution curves + time-to-discovery.

---

## A) Prioritized source acquisition matrix (SF-focused, compliance-first)

> **Legend**
>
> * **Access method**: API/partner/paid feed/permitted crawl/manual/alerts
> * **Coverage value**: Very High / High / Medium / Low (for SF apartment hunting)
> * **Freshness strategy**: what to poll + cadence + delta detection
> * **Data quality gotchas**: common missing fields / traps

| Source                                                                                                 | Access method (API/partner/paid feed/permitted crawl)                                                                        |                                Expected coverage value | Freshness strategy (poll cadence + delta detection)                                                        | Data quality reliability / gotchas                                                                                                                      |
| ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- | -----------------------------------------------------: | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Property mgmt + building sites (long tail)** (SF local PMs, single-building sites, small brokerages) | **Permitted Firecrawl crawl** (robots/ToS allow) + sitemap/“availability” endpoints when public                              |        **Very High** (this is where many SF gems live) | Crawl index pages 15–60 min; detail pages only when changed; hash normalized JSON for delta                | Often missing exact unit #, fees, lease terms; “call for pricing”; availability text-only; photos reused across units                                   |
| **Large PM portfolios** (Greystar / Equity / AvalonBay / Essex / Related / etc.)                       | Prefer **direct feed/partner** if available; otherwise **permitted crawl** of their own sites                                |                                               **High** | Hourly on “available units”; daily on “floorplans”; delta on unit availability/price                       | Many have dynamic PMS widgets; sometimes show “starting at” not exact price; availability can lag                                                       |
| **PMS / ILS syndication feeds** (Yardi/RentCafe, RealPage/LeaseStar, Entrata, etc.)                    | **Partner/publisher agreements** to receive XML/JSON vacancy feeds; (don’t scrape the aggregator portals)                    |                                               **High** | Usually nightly feed + intraday “delta feed” if offered; reconcile by unit ID + lastUpdated                | Can be extremely clean (unit IDs) but varies by operator; some omit concessions, fees, or exact move-in dates                                           |
| **CoStar / CoStar ecosystem**                                                                          | **Paid license** (data platform / exports / integrations)                                                                    |            **High** (especially multifamily buildings) | Vendor dataset refresh schedule + your own incremental ingestion; treat as authoritative building registry | Great for building-level coverage; may be weaker for tiny landlords/in-law units ([CoStar][2])                                                          |
| **Yardi Matrix**                                                                                       | **Paid license** (research + property datasets)                                                                              |          **Medium–High** (building/owner intelligence) | Periodic dataset pulls (daily/weekly) + incremental merges                                                 | Great for “what buildings exist + who owns them”; not always “every currently vacant unit” ([yardimatrix.com][5])                                       |
| **RealPage APIs** (ecosystem integrations)                                                             | **Official APIs** via developer portal / contracts                                                                           |      **Medium–High** (depends on what you can license) | Event/webhook where possible; otherwise hourly/daily pulls                                                 | Coverage depends on participating operators + products; integration scope varies ([developer.realpage.com][6])                                          |
| **MLS / broker-listed rentals**                                                                        | **RESO Web API** via MLS/broker/vendor (Bridge, Spark, SimplyRETS-like vendors)                                              | **Medium** (high quality; not the whole rental market) | Near-real-time or hourly pulls via “modified since” + RESO IDs                                             | Structured fields are strong (beds/baths/DOM), but rentals may be incomplete in some markets ([reso.org][3])                                            |
| **Zillow**                                                                                             | **No compliant crawling.** Options: (a) **license/partner**; (b) **use Zillow APIs only if approved + within allowed scope** |             **High**, but hard to ingest automatically | If licensed: use partner delta feed; otherwise treat as “manual/alerts only”                               | ToS forbids automated queries/scraping; fields often normalized but some fees hidden ([Zillow][7])                                                      |
| **HotPads**                                                                                            | Similar posture to Zillow; official docs exist for **bulk listing feeds (publishers → HotPads)**                             |                                             **Medium** | If you become an approved publisher/partner: scheduled feed; else manual                                   | Feed guide is supply-side; not a public consumer listings API ([Amazon Web Services, Inc.][4])                                                          |
| **Trulia**                                                                                             | Treat as **no compliant crawling**; pursue **partner/licensed** routes                                                       |                                             **Medium** | Licensed feed or manual                                                                                    | Similar portal dynamics: duplicates, “starting at,” unclear fees (verify terms before any automation)                                                   |
| **Realtor.com**                                                                                        | **No compliant crawling**; use **license/partner** (if feasible)                                                             |                                             **Medium** | Licensed feed + incremental; otherwise manual                                                              | Terms prohibit scraping/robots/data-mining; rentals can be thinner than sales in some areas ([Realtor][8])                                              |
| **Apartments.com (CoStar)**                                                                            | **No compliant crawling**; licensing/partner only                                                                            |                             **High** (big multifamily) | Licensed feed/dataset; incremental updates                                                                 | Terms prohibit robots/spiders/manual processes to monitor/copy; strong building/unit coverage but often paid placements ([Apartments.com][9])           |
| **PadMapper**                                                                                          | **No compliant crawling**                                                                                                    |                                             **Medium** | Manual/alerts or partnership                                                                               | Explicitly prohibits crawling/scraping/spidering to collect content ([PadMapper][10])                                                                   |
| **Zumper**                                                                                             | **No compliant crawling**                                                                                                    |                                             **Medium** | Manual/alerts or partnership                                                                               | Explicitly prohibits crawling/scraping/spidering/harvesting site content ([Zumper - Apartments for Rent & Houses][11])                                  |
| **Craigslist**                                                                                         | **No compliant crawling** (unless separately licensed)                                                                       |            **High** for in-law units / small landlords | Manual-only; at most store “links you personally saved”                                                    | Terms prohibit using software/services to interact (incl. searching) and prohibit collecting content via automated/manual equivalents ([craigslist][1]) |
| **Facebook Marketplace**                                                                               | **Generally no broad public listings API**; explore official restricted programs; otherwise manual                           |                             **Medium** (sublets/rooms) | Manual-only; optionally ingest user-exported links/messages                                                | Frequent scams; missing address/unit; stale quickly; availability text-only                                                                             |
| **SF affordable housing / lotteries (e.g., DAHLIA)**                                                   | Prefer **official portal/API if available**; otherwise permitted crawl                                                       |                          **Medium** (only if relevant) | Daily/weekly; low churn                                                                                    | Different “application window” semantics; not standard rentals; eligibility rules                                                                       |

**Key takeaway:** you’ll get the biggest compliant jump in recall by (1) **licensing** where it’s the only route (big portals), and (2) aggressively crawling the **origin long tail** (PM/building sites) where it’s permitted.

---

## B) Connector blueprint

### Core data model (normalized output)

```ts
// Canonical, source-agnostic listing record
type Listing = {
  canonical_id: string;              // your global ID (post-dedup)
  source_records: SourceRecord[];    // provenance

  // Identity
  address_raw?: string;
  address_norm?: {
    line1: string; city: string; state: string; zip?: string;
    unit?: string;
  };
  geo?: { lat: number; lon: number; };
  neighborhood?: string;            // SF neighborhood label (your taxonomy)

  // Offer
  price_monthly?: number;           // numeric
  beds?: number;
  baths?: number;
  sqft?: number;
  lease_term_months?: number;
  deposit?: number;
  fees?: { name: string; amount?: number; text?: string }[];
  utilities?: { included: string[]; excluded: string[] };

  // Availability
  available_date?: string;          // ISO date if parseable
  available_text?: string;          // raw fallback
  status: "active" | "inactive" | "unknown";
  first_seen_at: string;
  last_seen_at: string;

  // Media & text
  title?: string;
  description?: string;
  amenities?: string[];
  photos?: { url: string; phash?: string }[];

  // Contact
  contact?: { name?: string; phone?: string; email?: string; broker?: boolean };

  // Confidence & QA
  extraction_confidence: number;    // 0..1
  field_confidence?: Record<string, number>;
};
type SourceRecord = {
  source: string;                   // e.g., "veritas", "costar", "mls_reso"
  source_listing_id?: string;        // stable if available
  url: string;
  fetched_at: string;
  raw_payload_ref: string;           // blob store pointer
};
```

### Standard connector interface

```ts
type ConnectorCapabilities = {
  supports_incremental: boolean;     // can fetch "changed since"
  supports_detail_pages: boolean;
  supports_search_queries: boolean;
  rate_limit_qps: number;            // per-domain budget
};

interface SourceConnector {
  name(): string;
  capabilities(): ConnectorCapabilities;

  // Discover listing URLs or IDs to fetch (index/search pages)
  enumerate(seeds: SeedSpec, cursor?: Cursor): AsyncGenerator<EnumeratedItem>;

  // Fetch + extract a single listing detail into structured JSON
  fetchAndExtract(item: EnumeratedItem): Promise<Listing>;

  // Optional: verify staleness quickly (HEAD, lightweight status endpoint)
  checkStatus?(item: EnumeratedItem): Promise<"active"|"inactive"|"unknown">;
}
```

### Scheduling + throttling (practical)

* **Central “crawl scheduler”** maintains a queue of `EnumeratedItem`s with a **priority score**:

  * `priority = freshness_weight(source) * (now - last_polled) * expected_yield(slice)`
* **Per-domain budgets**:

  * hard cap QPS + concurrency per domain
  * exponential backoff on 429/503
  * jittered schedules to avoid thundering herd
* **Adaptive cadence**:

  * if a source/slice produces lots of *new* unique listings, shorten cadence
  * if mostly duplicates/stale, lengthen cadence
* **Two-lane pipeline**:

  1. **Index lane** (cheap): fetch search/index pages for new URLs
  2. **Detail lane** (expensive): fetch detail pages + LLM extraction

### Dedup strategy overview (cross-source)

Use **layered matching** and keep it explainable:

1. **Hard keys** (high precision):

   * normalized address + unit + (beds/baths)
   * exact phone number
2. **Geo + fuzzy** (medium precision):

   * same lat/lon within ~20m + same beds/baths + similar price band
3. **Text + image similarity** (high recall):

   * embedding similarity on description/title
   * image pHash match clusters
4. Maintain a **CanonicalListing** record with:

   * current “best” values (by source reliability + recency)
   * per-field provenance
   * historical price/availability timeline

---

## C) Firecrawl integration plan (permitted crawling + change detection)

### 1) Crawl structure

* **Seeds**:

  * curated list of SF PM/building sites (start with top ~200)
  * neighborhood search pages on broker sites that allow it
  * university/medical housing boards that are public
* **Discovery**:

* “site search” queries (via Firecrawl Search) for:
    `("San Francisco" OR "SF") (apartments|rentals|availability) (property management|leasing)`
  * then queue candidate domains for a **policy check** (robots + ToS review)
* **Traversal**:

  * Prefer **sitemaps** (`/sitemap.xml`) and internal “availability” listings
  * Detect pagination via link patterns: `?page=`, `offset=`, `p=`, “Next”
  * Always separate:

    * **index pages** ⇒ extract listing URLs
    * **detail pages** ⇒ extract structured data

### 2) Change detection (freshness + “remove stale quickly”)

* For every URL, store:

  * `etag`, `last_modified` (when present)
  * `content_hash` of cleaned HTML
  * `json_hash` of normalized extracted Listing JSON
* Delta rules:

  * If `content_hash` unchanged ⇒ skip LLM extraction
  * If changed ⇒ extract; if `json_hash` unchanged ⇒ update `last_seen_at` only
  * If HTTP 404 / “unavailable” keyword / status endpoint says gone ⇒ mark inactive
* TTL policy (source-specific):

  * high-churn PM “availability” pages: TTL 48–72h unless re-seen
  * broker/MLS pages: TTL 7–14 days (but verify sooner if “pending”)
  * classifieds-like sources you can’t automate: TTL = manual

### 3) Extraction to structured JSON (OpenAI + schema)

* Use a strict JSON schema and do **two-pass extraction**:

  1. **Extractor**: parse page → `Listing` JSON with confidence per field
  2. **Validator**: rule checks (e.g., price sanity, bed/bath ranges, SF city check), and request a repair if invalid
* Add **cross-source reconciliation**:

  * if same canonical listing appears in multiple sources, prefer:

    * most recent, then most reliable source for that field (e.g., MLS for address, PM site for availability)

### 4) Compliance guardrails (critical)

* For each domain, store `PolicyStatus = crawl_allowed | manual_only | partner_required | unknown`.
* Block Firecrawl jobs for any non-`crawl_allowed` domain (and instead route to manual workflows).
* Never implement bypasses (CAPTCHA, paywalls, login walls).

---

## D) “Coverage score” definition (measurable without perfect ground truth)

### Define Coverage Score (0–100) as a weighted composite

Let:

* `U = unique active canonical listings found in last 7 days`
* `TTD = median time-to-discovery` (from “posted” timestamp if present, else from first-seen vs source’s own sort order)
* `SR = stale removal time` (median time to mark inactive after disappearance)
* `D = diversity score` (neighborhood + price band + unit type entropy)
* `Q = data quality score` (field completeness + validation pass rate)

Example:

* `CoverageScore = 35*norm(U) + 20*(1-norm(TTD)) + 15*(1-norm(SR)) + 15*D + 15*Q`

### How to estimate recall without ground truth

1. **Capture–recapture estimation** (overlap-based):

   * If Source A finds `a`, Source B finds `b`, overlap is `ab`,
   * estimated total `~ (a*b)/ab` (extend to multiple sources via log-linear models).
   * Use this to track “are we approaching saturation?” per neighborhood/price band.
2. **Source contribution curve**:

   * % of listings that are *unique* to each source
   * If a new connector adds mostly duplicates, deprioritize it.
3. **Building registry completeness** (SF multifamily):

   * Maintain a list of known buildings (from CoStar/Yardi/City datasets) and measure:

     * `% buildings with ≥1 active unit listing in last N days`
4. **Human audit sampling**:

   * weekly sample of 50 listings: compare extracted fields vs page truth
   * report per-source error rates and retrain prompts/rules

---

## E) Plans

### 2-week “coverage MVP” plan (get real SF value fast)

**Days 1–2: Data backbone**

* Implement canonical `Listing` schema, provenance model, and blob store.
* Stand up scheduler + per-domain rate limiting + retry/backoff.
* Build dedup v1: address normalization + phone + basic fuzzy.

**Days 3–5: P0 connectors (compliant, high-yield)**

* Firecrawl connectors for:

  * top SF local PM sites (start with 20–50 domains)
  * a handful of big PM portfolios’ “available units” pages (only if permitted)
* MLS connector via a RESO Web API provider/broker partner if you can get credentials quickly. ([reso.org][3])

**Days 6–7: Extraction quality**

* Add schema-driven extraction + validator pass.
* Add price/fee parsing + availability parsing heuristics.
* Build staleness detection + TTL rules.

**Week 2: Scale coverage + diversity**

* Build “long-tail discovery” job:

  * search engine queries by SF neighborhood + “property management” + “availability”
  * queue + policy-check + auto-generate a Firecrawl connector config
* Add diversity sweeps (below) and start measuring:

  * daily unique listings
  * median time-to-discovery
  * duplicates ratio
* Add “manual import” UX:

  * paste a URL (from any portal) → extract only that page for personal tracking (no crawling).

### 2-month “maximum coverage” plan (aggressive, but realistic)

**Phase 1 (Weeks 3–4): Paid + partner coverage**

* License at least one **multifamily data platform** for SF building registry + coverage expansion (CoStar/Yardi Matrix depending on budget and needs). ([CoStar][2])
* Pursue PMS syndication partnerships (RentCafe/Yardi, RealPage/LeaseStar, Entrata) so you receive **direct vacancy feeds** rather than crawling portals.
* Establish a compliance “source gating” workflow so new domains can’t be crawled unless approved.

**Phase 2 (Weeks 5–6): Industrialize long tail**

* Expand long-tail connectors from ~50 → **500+ domains**:

  * auto-detect “availability widgets”
  * site-specific extraction templates (regex + LLM)
* Add “unit-level reconciliation”:

  * handle buildings with multiple identical units and rolling availability
* Add image pHash + embedding dedup for spam/duplicates.

**Phase 3 (Weeks 7–8): Freshness + diversity optimization**

* Implement adaptive scheduler (bandit-style):

  * budget more crawl frequency to slices that produce “good, unique” units
* Add “surge sweeps”:

  * every 5–10 minutes for your highest-priority slices (e.g., 1BR under X in N neighborhoods)
* Add QA automation:

  * automatic anomaly detection (rent drops, impossible sqft, suspicious fees)
  * weekly human audit + prompt/rule iteration

---

## “Search diversity engine” design (so you don’t get stuck)

### 1) Neighborhood sweeps

* Maintain an SF neighborhood taxonomy (Mission, Castro, Noe, Hayes, Richmond, Sunset, SOMA, Potrero, Bernal, etc.).
* For each neighborhood, run:

  * **broad** query (no price cap) weekly
  * **targeted** queries (your likely ranges) hourly
* Enforce **minimum quota** per neighborhood (exploration), even if yield is low.

### 2) Price-band sweeps

* Use overlapping bands (to catch boundary issues and “underpriced gems”):

  * e.g., `0–2500`, `2400–3200`, `3100–4000`, `3900–5200`, `5000+`
* For each band, track yield of “high match score” listings and adjust frequency.

### 3) Unit-type sweeps

* Separate pipelines for:

  * studios / 1BR / 2BR+
  * in-law / ADU / rooms (often not well structured)
  * furnished / short-term (if relevant)
* This prevents your model from overfitting to one unit type.

### 4) New listing surge sweeps

* For sources you can legally poll quickly (PM sites), do:

  * high-frequency index page polling (5–15 min)
  * “detail fetch only on change”
* For sources you can’t crawl, rely on:

  * user alerts + manual import links into your system.

---

### Optional context: RealPage is in the news (vendor risk awareness)

If you license/partner deeply with RealPage’s ecosystem, you may want to be aware of the recent DOJ-related reporting around RealPage’s rent-pricing software (separate from listings ingestion, but relevant to vendor diligence).

[1]: https://www.craigslist.org/about/terms.of.use "https://www.craigslist.org/about/terms.of.use"
[2]: https://www.costar.com/campaign/multifamily-property-data "https://www.costar.com/campaign/multifamily-property-data"
[3]: https://www.reso.org/reso-web-api/ "https://www.reso.org/reso-web-api/"
[4]: https://s3.amazonaws.com/files.hotpads.com/%2Bguides/Rental%2BListing%2BBulk%2BFeed%2BGuide.pdf "https://s3.amazonaws.com/files.hotpads.com/%2Bguides/Rental%2BListing%2BBulk%2BFeed%2BGuide.pdf"
[5]: https://www.yardimatrix.com/property-types/multifamily "https://www.yardimatrix.com/property-types/multifamily"
[6]: https://developer.realpage.com/explore/api "https://developer.realpage.com/explore/api"
[7]: https://www.zillow.com/z/corp/terms/ "https://www.zillow.com/z/corp/terms/"
[8]: https://www.realtor.com/terms-of-service/ "Read Our Terms of Use - realtor.com®"
[9]: https://www.apartments.com/grow/about/terms-of-service "https://www.apartments.com/grow/about/terms-of-service"
[10]: https://www.padmapper.com/tos "https://www.padmapper.com/tos"
[11]: https://www.zumper.com/terms-and-conditions "https://www.zumper.com/terms-and-conditions"
