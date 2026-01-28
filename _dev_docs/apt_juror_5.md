STATUS: Non-authoritative research notes. Superseded where conflicts with architecture_source_of_truth.md and architecture_decisions_and_naming.md.

Overrides:
- Paid services limited to OpenAI and Firecrawl.
- Retrieval uses Postgres FTS + pgvector only.
- Extraction is centralized in Extraction Service; connectors do not extract.
- Manual-only sources are ImportTask only; no automated crawling.
- Geo and routing are local-only (Pelias, Nominatim fallback, OTP, Valhalla; OSRM secondary).
- Alerts are local notifications or SMTP only.

## Metrics

### 1) Coverage proxies (accuracy + recall-focused)

You can’t directly measure “true recall of all SF listings,” so you instrument **coverage proxies** that are (a) measurable, (b) stratified, and (c) sensitive to blind spots.

#### A. Source coverage

**Goal:** detect missing sources and under-crawling within sources.

* **Integrated-source footprint**

  * *Definition:* `# integrated sources / # target sources`
  * *Use:* accountability / roadmap, not quality by itself.

* **Per-source capture recall (gold-audit recall)**

  * *Definition:* For a given source `s` and audit window `w`:

    * `Recall_source(s,w) = |Captured ∩ Gold_s,w| / |Gold_s,w|`
  * *Notes:* Gold set comes from manual snapshot/audit (see Ground truth plan).
  * *Why it matters:* this is the closest thing to “coverage” you can measure with high confidence.

* **Crawl success rate (by source + template)**

  * *Definition:* `Successful fetch+parse pages / attempted pages`
  * *Stratify by:* source, URL pattern/template, HTTP status, rendering mode.
  * *Alert when:* dips occur or a template’s success changes sharply.

#### B. Neighborhood coverage

**Goal:** ensure you’re not “great in Mission + Soma, blind elsewhere.”

* **Neighborhood recall vs gold**

  * *Definition:* For neighborhood `n`:

    * `Recall_nbhd(n,w) = |Captured ∩ Gold_n,w| / |Gold_n,w|`
  * *Require:* a neighborhood mapping strategy (lat/long → neighborhood polygon or canonical neighborhood lookup).

* **Neighborhood distribution drift**

  * *Definition:* compare distribution of listings by neighborhood over time (or vs audited sources).
  * *Simple metric:* max absolute deviation in share by neighborhood; optionally KL divergence.
  * *Use:* flags silent coverage regressions.

#### C. Price band coverage (even with unlimited budget)

**Goal:** avoid a system that only finds luxury buildings (or only mid-market).

* **Band recall vs gold**

  * Bands example: `<$3k`, `$3–5k`, `$5–8k`, `$8–12k`, `$12k+` (tune to SF reality).
  * `Recall_price(b,w) = |Captured ∩ Gold_b,w| / |Gold_b,w|`

* **Price parsing validity rate**

  * *Definition:* `% listings with rent parseable into numeric monthly rent (or rent range)`
  * *Why:* if parsing breaks, “coverage” looks high but ranking/filtering becomes wrong.

#### D. Listing velocity coverage

**Goal:** detect lag: great listings exist, but you see them too late.

* **New-listing capture recall (sampled)**

  * For each source/day: sample `m` newly posted listings directly from source; measure:

    * `Recall_new(s,day) = |Captured within T hours ∩ Gold_new| / |Gold_new|`
  * Choose `T` (e.g., 2h, 6h, 24h) based on market competitiveness.

* **Relevant-page acquisition rate / harvest ratio (crawler effectiveness)**

  * Borrowing focused crawling evaluation language: measure how quickly “relevant” items are acquired and how efficiently irrelevant items are filtered. ([cse.iitb.ac.in][1])
  * In your context:

    * `HarvestRatio = relevant_listings_found / total_pages_crawled` (per strategy/template)

---

### 2) Ranking quality (what you actually care about when deciding)

Treat ranking as an **information retrieval / recommender ranking** problem with graded relevance.

#### Label scale (recommended)

* **0:** not relevant (fails must-haves)
* **1:** relevant but not good (barely meets must-haves)
* **2:** good candidate
* **3:** great / would tour ASAP

#### Metrics

* **NDCG@k (primary offline metric)**

  * *Definition:* normalized discounted cumulative gain at rank k (graded relevance; discounts lower ranks). It’s a standard ranking-quality metric designed for ranked lists. ([faculty.cc.gatech.edu][2])
  * *Compute:* per query/session; report mean and distribution.

* **Hit Rate@k (top-k hit rate)**

  * *Definition:* `1` if at least one item with label ≥ threshold appears in top k, else `0`; averaged across sessions/queries.
  * Useful when the user only needs “a few great options,” not exhaustive recall. (Common in recommender top‑K evaluation.) ([tzin.bgu.ac.il][3])

* **Precision@k / Recall@k**

  * Precision@k: fraction of top-k that are relevant (label ≥ 1 or ≥2).
  * Recall@k: fraction of all relevant items (in gold pool) that appear in top-k. (Classic IR framing.) ([nlp.stanford.edu][4])

* **Time-to-first-great-option (TTFGO)**

  * *Definition (session-based):* time from session start (or daily digest generation) until first label=3 item is shown to user.
  * *Alternate (ingestion-based):* time from listing posted → first surfaced in top-k for user.
  * *Report:* median, p90; by neighborhood + source.

* **Regret proxy (optional, strong signal)**

  * *Definition:* if user eventually contacts/applies to item `i`, compute how far down it was ranked historically; aggregate as “missed opportunity cost.”

**Why these are grounded:** standard recommender evaluation distinguishes offline metrics, user studies, and online experiments; use all three depending on what you can measure. ([tzin.bgu.ac.il][3])

---

### 3) Freshness and staleness (crawl + marketplace reality)

Freshness is not just “last crawled”; it’s whether your copy reflects the source’s current truth.

Classic crawler literature defines **freshness** (up-to-date vs not) and **age** (time since it became stale). ([VLDB][5])

* **Time-to-discovery (TTD)**

  * *Definition:* `ingested_time - source_posted_time`
  * *Report:* median, p90, p99; by source, by strategy, by neighborhood.

* **Freshness rate**

  * *Definition:* `% of “active” listings in your DB that are still active on source when checked`
  * Operationally: on a sample, verify listing still exists / still available.

* **Stale rate**

  * *Definition:* `% of listings marked active in your DB that are removed/unavailable on source`
  * *Why:* stale inventory wastes user attention and corrupts ranking training signals.

* **Time-to-removal (TTR)**

  * *Definition:* `system_remove_time - source_remove_time` (source_remove_time may be inferred as “first observed missing”)
  * *Report:* median + p90; by source.

* **Age of stale listings**

  * *Definition:* for stale items, `now - (time it became stale)`
  * *Use:* prioritize recrawl scheduling and removal checks.

---

### 4) Extraction accuracy (field-level correctness + completeness)

This is *data quality* measurement: accuracy + completeness + timeliness + consistency are core dimensions in widely used data quality frameworks. ([iso25000.com][6])

For each key field `f` (rent, beds, baths, sqft, address, unit, neighborhood, availability date, pet policy, parking, lease term, fees, contact, lat/long):

* **Field accuracy(f)**

  * *Definition:* `# correct values / # evaluated values`
  * Measured against gold labels (manual truth) per listing.

* **Field missingness(f)**

  * *Definition:* `# null/unknown / # listings where field should exist`
  * “Should exist” can be source-dependent (e.g., sqft often missing on Craigslist).

* **Field validity(f)**

  * *Definition:* `% values passing schema + range checks`
  * Examples: rent > 0, beds in [0..10], baths in [0..10], sqft reasonable, dates parseable.

* **Critical-field pass rate**

  * *Definition:* `% listings with all critical fields valid`
  * Critical fields: rent, beds/baths, neighborhood, address (or geo), availability.

**Tip:** For text-derived amenities (laundry, AC, parking, pets), treat as extraction of entities/attributes and evaluate with precision/recall/F1 where appropriate. ([Google for Developers][7])

---

### 5) Dedupe / entity resolution accuracy

Duplicate listings across sources are an **entity resolution** problem; evaluation commonly uses pairwise and cluster metrics (pairwise precision/recall/F1, B‑cubed, purity/completeness). ([arXiv][8])

* **Pairwise precision / recall / F1**

  * Consider all pairs of records:

    * True duplicate pair if they refer to the same unit.
    * Predicted duplicate pair if your system clustered them together.
  * Precision: fraction of predicted duplicate pairs that are true duplicates.
  * Recall: fraction of true duplicate pairs that you successfully predicted.

* **Cluster purity (over-merge detector)**

  * For each predicted cluster: proportion of records belonging to the dominant true unit.
  * Low purity = you merged distinct units (catastrophic for ranking + user trust).

* **Cluster completeness (under-merge detector)**

  * For each true unit: proportion of its records captured in one predicted cluster.
  * Low completeness = duplicates remain split (annoying but less fatal than over-merges).

* **Duplicate collapse rate**

  * *Definition:* `# raw source records / # canonical listings`
  * Track by source and neighborhood; sudden changes often indicate breakages.

---

## Ground truth plan

### A) Golden set strategy (periodic manual audits)

Use a **TREC-style pooling mindset**: you can’t label everything, so you label a carefully chosen subset that’s maximally informative. In IR evaluation, pooling combines top results from multiple runs into a pool for human judging. ([trec.nist.gov][9])

**Golden set design (SF apartment context):**

1. **Select “Tier 1” sources** (highest volume + highest value): e.g., Craigslist, Zillow-family pages, Apartments.com, HotPads, Zumper, large property managers, luxury buildings, etc.

2. **Define audit strata** to prevent blind spots:

   * neighborhoods (Mission, Hayes, Marina, Richmond, Sunset, SOMA, Nob Hill, etc.)
   * unit types (studio/1/2/3+, condo vs apartment)
   * price bands (including very high-end)
   * posting recency (new today vs older active)

3. **Weekly “snapshot audit”**

   * For each tier-1 source, pick a time window (e.g., Tuesday 10:00–11:00 PT).
   * Manually export/screenshot/search results for broad queries.
   * This becomes `Gold(source, window)`.

4. **Monthly “deep audit”**

   * Broader sweeps (more neighborhoods, more sources, deeper pagination).
   * Add “weird cases”: sublets, short-term, furnished, SROs, ADUs, newly built buildings.

### B) Labeling workflow: what to label

For each **golden listing**, label:

1. **Identity**

   * canonical unit ID (address + unit, or building+unit)
   * duplicate group ID across sources

2. **Availability status**

   * active/available vs removed/unavailable (at audit time)

3. **Relevance to your criteria**

   * 0/1/2/3 scale (with written guidelines)

4. **Field truth for critical fields**

   * rent (numeric or range), beds, baths, neighborhood, geo/address, availability date
   * plus 2–3 “decision fields” you care about (parking, pets, laundry, outdoor space, elevator, etc.)

5. **Source metadata**

   * posted_time, last_updated_time (if present), URL, source listing ID

### C) “How much is enough?”

Because you want **high confidence**, you should size labeling around confidence intervals for proportions (recall, accuracy). Practical approach:

* **Start**: 300–500 labeled listings across strata in the first 2 weeks.
* **Target by day 30**: 1,000–2,000 labeled listings total.
* **Rule:** if any stratum (e.g., neighborhood+source) has <30 labeled examples, treat its metrics as “low confidence” and prioritize it next audit.

With unlimited budget, you can:

* hire 1–2 human auditors to label daily,
* measure inter-annotator agreement on a small overlap set to keep labels consistent (especially for “greatness”).

### D) User feedback as labels (online signals)

Instrument explicit + implicit signals:

* **Explicit:** save, hide, “tour?”, “contacted”, “applied”, star rating.
* **Implicit:** dwell time, scroll depth, clicks to source, map opens.

Convert to labels:

* Positive: save/contact/apply (strong), click (weak)
* Negative: hide (strong), bounce (weak)

**Bias warning:** user signals are influenced by the ranking. To counter:

* add a small exploration rate (e.g., 5–10% of slots are “diverse candidates”) so you can learn about items you’d otherwise never show.

This matches recommender evaluation best practice: combine offline evaluation with user studies/online experiments when possible. ([tzin.bgu.ac.il][3])

---

## Audit plan

### 1) “Missed listing detector” evaluation (systematic sweeps)

This is your coverage safety net: an independent mechanism that tries to “prove you missed something.”

#### A. Sweep design

Run **independent broad searches** that do NOT reuse your production queries/templates:

* **Source-native sweeps**

  * use each source’s own filters/sort (e.g., “newest”, map bounds)
  * randomize neighborhoods + price bands
  * go deeper than your normal pagination

* **Web-wide sweeps**

  * search engine queries like `site:propertymanager.com "San Francisco" "available now" "2 bed"`
  * discover property manager sites and building pages you’re missing

* **Sentinel neighborhoods**

  * pick 5–8 neighborhoods you care most about; sweep them daily.

Focused crawling literature explicitly treats evaluation as “rate of acquiring relevant pages” and filtering irrelevant ones—your sweeps emulate a competitor crawler to expose blind spots. ([cse.iitb.ac.in][1])

#### B. Missed-listing metrics

For each sweep `S` (a set of listings discovered independently):

* **Miss rate**

  * `MissRate = |S - Captured| / |S|`
* **Miss rate within T hours**

  * `MissRate_T = |{l in S not captured within T hours}| / |S|`
* **Root-cause breakdown**

  * blocked fetch, dynamic rendering failure, parser/template miss, dedupe error, geo/neighborhood mapping, robots/ToS, etc.

#### C. Auto-generate new search strategies from misses

For each missed listing, auto-extract:

* domain/root source
* URL pattern
* signals that indicate “listing page” (schema.org, keywords, repeating layout)

Then generate candidate actions:

* new Firecrawl extraction recipe/template
* new discovery query (site search, sitemap, RSS, API)
* recrawl schedule adjustments

Track “time-to-fix blind spot”:

* `FixLatency = time(miss detected) → time(capture recall restored)`

---

### 2) Coverage audit checklist (operational, repeatable)

Run weekly; treat like an SRE checklist for your marketplace dataset.

**A. Sources**

* [ ] Tier-1 sources: crawl success rate ≥ target; no template regressions
* [ ] New sources discovered this week? integrated or triaged
* [ ] Robots/ToS changes detected; fallback strategy documented

**B. Geography**

* [ ] Neighborhood recall (gold) meets threshold for top neighborhoods
* [ ] Map coverage: no obvious “holes” in lat/long heatmap

**C. Price + unit types**

* [ ] No price-band collapse (e.g., parsing failures pushing everything to null)
* [ ] Studios/1BR/2BR/3BR+ present as expected

**D. Freshness**

* [ ] Median TTD within target; p95 within target
* [ ] Stale rate below target; worst-offending sources identified

**E. Data quality**

* [ ] Critical-field pass rate above threshold
* [ ] Field missingness spikes investigated

**F. Dedupe**

* [ ] Over-merge alarms (purity drop) not triggered
* [ ] Duplicate collapse rate stable; anomalies explained

**G. Ranking**

* [ ] Offline NDCG@k non-decreasing vs baseline
* [ ] Online TTFGO stable/improving

---

## Regression plan

### 1) Golden tests for extraction (don’t break the parser)

Create a **fixed corpus of listing pages** (HTML snapshots) + expected structured output.

* For each source/template, store:

  * input HTML (or Firecrawl output)
  * expected fields (rent, beds, baths, address, amenities, etc.)
* Run on every change:

  * exact match for deterministic fields
  * fuzzy/normalized comparisons for text fields
* Gate merges on:

  * no regression in critical-field accuracy/missingness

“Golden tests” are widely used to detect subtle regressions by comparing current outputs to a saved baseline. ([Shaped][10])

### 2) Golden tests for ranking (don’t “improve” into worse results)

Maintain:

* a set of **frozen evaluation queries** (your typical searches + edge cases)
* a labeled pool for each query (golden listings + judged relevance)

For each ranking model/version:

* compute NDCG@k, HitRate@k, Precision@k
* set **regression thresholds**, e.g.:

  * NDCG@10 must not drop by > 0.01 absolute
  * HitRate@5 must not drop
  * TTFGO simulation must not worsen

### 3) Data pipeline regression (schema + dedupe + freshness)

* **Schema contracts**

  * every field has type/range checks; block deployment if violated
* **Dedupe regression**

  * run dedupe metrics on labeled duplicate sets; gate on pairwise F1 and purity
* **Freshness regression**

  * if median TTD or stale rate worsens beyond threshold, fail the release

General regression testing goal: re-test existing functionality after changes to ensure nothing regresses. ([DataCamp][11])

---

## 30-day roadmap

### Days 1–7: Instrumentation + baseline (make everything measurable)

* Implement event logging:

  * discovered_at, ingested_at, parsed_at, surfaced_at, removed_at
  * source_posted_at (when available), last_seen_at
* Define canonical schema + validation rules (critical fields)
* Stand up dashboards:

  * crawl success rate by source/template
  * TTD distribution
  * stale rate
  * missingness by field
* Pick Tier‑1 sources and design the first audit strata.

**Deliverable by day 7:** baseline metrics dashboard + first audit schedule.

---

### Days 8–14: Build your first golden set + start offline ranking eval

* Run 2–3 snapshot audits across Tier‑1 sources (pool results).
* Label ~300–500 listings:

  * relevance grade + critical fields + duplicate grouping
* Compute:

  * per-source recall (gold capture)
  * neighborhood + price-band recall
  * first NDCG@k / HitRate@k baselines
* Identify top 3 failure modes (usually: one source template, neighborhood mapping, dedupe over-merge).

**Deliverable by day 14:** first “coverage report” with quantified blind spots.

---

### Days 15–21: Missed listing detector + dedupe evaluation hardening

* Implement weekly (or daily for sentinel neighborhoods) independent sweeps.
* Compute miss rate and root-cause taxonomy.
* Build a labeled dedupe test set:

  * 100–200 duplicate clusters across sources (including tricky “same building different unit” cases)
* Add entity-resolution metrics:

  * pairwise F1 + cluster purity/completeness ([arXiv][8])

**Deliverable by day 21:** automated missed-listing report + dedupe regression gate.

---

### Days 22–30: Regression gates + online feedback loop + steady cadence

* Freeze:

  * extraction golden pages per source/template
  * ranking golden queries + labeled pools
* Add CI checks:

  * extraction accuracy/missingness gates
  * NDCG/HitRate gates
  * freshness gates (TTD, stale rate)
* Integrate user feedback signals:

  * save/hide/contact/apply events as online labels
  * compute TTFGO weekly
* Establish cadence:

  * **Daily:** freshness + crawl health + stale sweep
  * **Weekly:** snapshot audit + missed listing sweeps + coverage report
  * **Monthly:** deep audit + strategy expansion + recalibrate strata

**Deliverable by day 30:** an end-to-end evaluation + audit pipeline that can catch missed listings and prevent regressions automatically.

---

If you want, I can also sketch a minimal schema for the logging events + an example “coverage report” template (the exact charts/tables you’d want on a dashboard) that lines up with the metrics above.

[1]: https://www.cse.iitb.ac.in/~soumen/doc/www1999f/pdf/prelim.pdf?utm_source=chatgpt.com "Focused Crawling: A New Approach to Topic-Specific ..."
[2]: https://faculty.cc.gatech.edu/~zha/CS8803WST/dcg.pdf?utm_source=chatgpt.com "Cumulated Gain-Based Evaluation of IR Techniques"
[3]: https://tzin.bgu.ac.il/~shanigu/Publications/EvaluationMetrics.17.pdf?utm_source=chatgpt.com "Evaluating Recommendation Systems"
[4]: https://nlp.stanford.edu/IR-book/pdf/08eval.pdf?utm_source=chatgpt.com "Evaluation in information retrieval"
[5]: https://www.vldb.org/conf/2000/P200.pdf?utm_source=chatgpt.com "The Evolution of the Web and Implications for an ..."
[6]: https://iso25000.com/index.php/en/iso-25000-standards/iso-25012?utm_source=chatgpt.com "ISO/IEC 25012"
[7]: https://developers.google.com/machine-learning/crash-course/classification/accuracy-precision-recall?utm_source=chatgpt.com "Classification: Accuracy, recall, precision, and related metrics"
[8]: https://arxiv.org/pdf/2404.05622?utm_source=chatgpt.com "How to Evaluate Entity Resolution Systems"
[9]: https://trec.nist.gov/pubs/trec32/papers/overview_32.pdf?utm_source=chatgpt.com "Overview of TREC 2023 - Text REtrieval Conference"
[10]: https://www.shaped.ai/blog/golden-tests-in-ai?utm_source=chatgpt.com "Golden Tests in AI: Ensuring Reliability Without Slowing ..."
[11]: https://www.datacamp.com/tutorial/regression-testing?utm_source=chatgpt.com "Regression Testing: A Complete Guide for Developers"
