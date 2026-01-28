STATUS: Non-authoritative research notes. Superseded where conflicts with architecture_source_of_truth.md and architecture_decisions_and_naming.md.

Overrides:
- Paid services limited to OpenAI and Firecrawl.
- Retrieval uses Postgres FTS + pgvector only.
- Extraction is centralized in Extraction Service; connectors do not extract.
- Manual-only sources are ImportTask only; no automated crawling.
- Geo and routing are local-only (Pelias, Nominatim fallback, OTP, Valhalla; OSRM secondary).
- Alerts are local notifications or SMTP only.

[![The San Francisco Microclimate Map :: Behance](https://tse3.mm.bing.net/th/id/OIP.mabHv2kZM_F6YUKbkkHvxwHaEy?pid=Api)](https://www.behance.net/gallery/23314167/The-San-Francisco-Microclimate-Map?utm_source=chatgpt.com)

## Ranked frontier features (top 10 by impact)

1. **SF Rental Graph + Long‑Tail Discovery Engine (PM site crawler discovery)**

   * Builds a *superset* of inventory by systematically finding small property management (PM) sites, single-building “availability” pages, PDFs, and niche sources—then deduping them into one canonical “building → units → listings” graph.
   * Leverages Firecrawl’s **Search / Map / Crawl / Extract** to go from “unknown URLs” → “validated PM site” → “structured unit inventory.” ([Firecrawl][1])

2. **Multimodal Listing Intelligence (photo + text → structured truth with uncertainty)**

   * Extracts *hard-to-filter* signals: sunlight/brightness, renovation quality, layout clues, flooring (carpet vs hardwood), appliance tier, street-facing vs courtyard, noise hints, staging tricks, and “too good to be true” patterns.
   * Uses OpenAI vision-capable models via the **Responses API** (image inputs) plus schema-locked extraction via **Structured Outputs**. ([OpenAI Platform][2])

3. **Lease / Fees / Specials Intelligence + Bait‑and‑Switch Language Detection**

   * Parses hidden fees (trash/admin/amenity), parking constraints, income requirements, pet policies, utility responsibility, move-in specials and their fine print.
   * Flags “starting at / subject to change / photos may not be of actual unit / call for details” patterns and cross-checks across sources.

4. **Hidden‑Gem Value Engine (comp model + anomaly detection + evidence)**

   * Estimates “fair rent” and identifies undervalued units that match your tastes (not just cheap).
   * Combines a hedonic rent model with photo-derived renovation/condition scores and building-level signals (permits/violations) to avoid “cheap for a reason.” ([San Francisco Data][3])

5. **Action Advantage: Rent‑Fast Prediction + Next‑Best Action Queue**

   * Predicts which listings will rent quickly and what to do *now* (tour request timing, application readiness, questions to ask).
   * Turns the hunt into a prioritized pipeline rather than browsing.

6. **SF Environment Model: Sun/Fog + Hills + Transit + Noise Corridors (SF‑specific, decision‑quality boost)**

   * Microclimate-aware comfort score (fog/wind likelihood), hill/grade penalty for walking/biking, transit time distributions, plus noise exposure proxies (flight paths, nightlife, arterials).
   * Uses GTFS (Muni/BART) for commute modeling ([gtfs.org][4]), SFO noise contours/flight tracking ([San Francisco International Airport][5]), fog datasets ([USGS][6]), and elevation data ([USGS][7]).

7. **Building Health & Management Signal Layer (public records intelligence)**

   * Augments listings with building-level risk signals: DBI complaints, notices of violation, renovation/permit activity, Rent Board petitions—useful for weeding out headache buildings. ([San Francisco Data][8])

8. **Near‑Miss Reasoning + Pareto Frontier Explorer**

   * Shows apartments that barely miss constraints (e.g., $150 over budget, 0.3 miles farther, shared laundry) and explains the trade.

9. **“What should I adjust?” Preference Sensitivity Advisor**

   * Computes minimal preference relaxations that unlock disproportionately better options (e.g., “+ $200 budget unlocks 14 units with in‑unit laundry and +25% sunlight score”).

10. **Personal Feedback Loop: Tour Intelligence + Model Calibration**

* You take quick notes/photos during tours; the system turns that into structured labels to re-rank future options and calibrate its own predictions.

---

## Deep dives: architecture + implementation for the top 5

### 1) SF Rental Graph + Long‑Tail Discovery Engine

**Why it’s #1**
Most people lose because they’re searching the same handful of aggregators. The best ROI comes from *coverage* + *dedupe* + *freshness*.

#### Architecture

**Pipeline stages (seed → expand → validate → extract → normalize → monitor):**

1. **Seed generation**

   * Inputs:

     * Known aggregator sources you’re allowed to access programmatically.
     * Your own “target neighborhoods/buildings/streets” wishlist.
     * Public geographic scaffolding (SF building footprints for address/building entity resolution). ([San Francisco Data][9])
   * Output: a queue of candidate domains/URLs.

2. **Expand with web discovery**

   * Use Firecrawl **Search** to find PM/building availability pages with query templates:

     * `"site:.com \"availability\" \"San Francisco\" studio"`
     * `"\"apply now\" \"San Francisco\" \"units available\""`
   * Firecrawl Search can return results and optionally scrape content. ([Firecrawl][1])

3. **Site mapping + targeted crawling**

   * For each candidate domain:

     * Firecrawl **Map** to list URLs quickly; filter with heuristics (`/availability`, `/floorplans`, `units`, `vacancies`, PDFs). ([Firecrawl][10])
     * Firecrawl **Crawl** to pull content from the selected URL subsets. ([Firecrawl][11])

4. **Structured extraction**

   * Firecrawl **Extract** with a JSON Schema for:

     * address, building name, unit identifier, rent range, beds/baths, sqft, availability date, deposit, parking, pet policy, utilities, application link, contact info, and evidence URLs.
   * (Important) Enforce schema with OpenAI **Structured Outputs** when post-processing any LLM extraction so you never “lose” a field. ([Firecrawl][12])

5. **Normalization + entity resolution**

   * Deduplicate across sources into a canonical graph:

     * **Building entity**: normalized address + lat/lng + footprint polygon.
     * **Unit entity**: unit number/floorplan + sqft + bed/bath.
     * **Listing instance**: source URL + timestamp + price + photos.
   * Use embeddings for “same building?” fuzzy matching (building names vary a lot). ([OpenAI Platform][13])

6. **Monitoring**

   * Re-crawl high-yield domains on schedules; prioritize “availability pages” over marketing pages.

#### Models & storage

* **OpenAI embeddings** for similarity matching (dedupe, building name variants, “same floorplan” clustering). ([OpenAI Platform][13])
* **pgvector (Postgres)** for semantic retrieval over raw scraped pages + extracted facts, enabling “show me all listings that imply south-facing light and quiet bedrooms.”
* **Batch API** for large-scale offline processing (e.g., nightly extraction refreshes) while keeping “hot listings” on real-time processing. ([OpenAI Platform][15])

#### UX outputs

* “**New inventory discovered**” feed (long-tail wins).
* For each listing: provenance (source list), confidence, and “why we think this is real / updated”.

---

### 2) Multimodal Listing Intelligence (Photo + Text)

**Why it’s #2**
In SF, *the delta between “looks fine” and “actually great” is often in light/noise/layout/condition*—all under-specified in filters.

#### Core capabilities

1. **Sunlight / brightness inference**

   * Visual cues: direct sun patches, shadow hardness, window size, exposure hints.
   * Combine with geometry:

     * Building footprint polygons + neighborhood geometry to estimate window-facing direction proxies. ([San Francisco Data][9])
     * Elevation/hillshade to infer “blocked by hill/adjacent building.” ([USGS][7])
   * Optional SF-specific: fog likelihood as a “sun reliability” modifier using fog datasets. ([USGS][6])

2. **Renovation quality & finish tier**

   * Detect: quartz vs laminate, cabinet style, appliance brands/age class, lighting fixtures, bathroom tile work.
   * Output: a *calibrated* “finish tier score” + “condition risk score”.

3. **Layout hints**

   * Estimate: open plan vs chopped, galley kitchen vs L-shape, bedroom size, “railroad” layouts, awkward columns.
   * Strategy: derive a “layout embedding” from photo sequences so you can search “layouts like this one.”

4. **Noise hints**

   * From photos: street-visible windows, proximity to commercial corridors, single-pane/double-pane cues, bedroom placement clues.
   * From geo: 311 noise complaint density near the block + known corridors (arterials, nightlife). ([San Francisco Data][16])
   * From SFO: flight path/noise contour overlays. ([San Francisco International Airport][5])

5. **“Too good to be true” patterns**

   * Not security theater—pure decision quality:

     * Photos reused across unrelated addresses (perceptual hashing + web lookups).
     * Over-processed HDR interiors with missing “real” context photos.
     * Inconsistencies: text says “hardwood”, photos show wall-to-wall carpet; “in-unit laundry” but no washer/dryer pictured.

#### Architecture

**Two-pass vision pipeline (fast → deep):**

* **Fast pass (all listings)**

  * OpenAI vision model via Responses API ingests 8–20 photos + listing text and emits structured attributes (with confidence and evidence). ([OpenAI Platform][2])
  * Use **Structured Outputs** to force an `ApartmentVisualSignals` schema:

    * `flooring: {type: enum, confidence}`
    * `natural_light_score: 0-100`
    * `kitchen_finish_tier: 1-5`
    * `noise_risk: 0-100`
    * `red_flags: [...]` (each with photo index + rationale)
    * `questions_to_ask: [...]` (targeted follow-ups)

* **Deep pass (top candidates / near-misses)**

  * Add specialist CV models:

    * **Segment Anything (SAM)** for segmentation masks (windows/floors/appliances), improving consistency and enabling measurement-like features (window-to-wall ratio proxy). ([GitHub][17])
    * **CLIP** embeddings for image similarity (duplicate detection, “find kitchens like this”). ([GitHub][18])
  * Optional: train a small custom classifier on your own preferences (“I like this style”) using tour feedback.

#### Workflow

1. Ingest photos → normalize sizes → compute hashes/embeddings.
2. Run fast pass structured extraction.
3. If high-score or high-uncertainty: run deep pass segmentation + second-stage reasoning.
4. Store:

   * raw photo embeddings
   * extracted attributes + confidence
   * evidence pointers (photo index, quote spans)

#### Key implementation trick

**Evidence-first UI**: every inferred attribute links to:

* the exact photos that support it, and/or
* the exact text snippets that support it.

This is how you avoid “LLM vibes” and get decision-grade outputs.

---

### 3) Lease / Fees / Specials Intelligence + Bait-and-Switch Detection

**Why it’s #3**
Listings are often written to sell, not to inform. This feature prevents wasted tours and surprise costs.

#### What it extracts (beyond basics)

* **Move-in specials**: duration, conditions, whether the net effective rent hides higher base rent.
* **Hidden fees**: trash/valet trash, admin, amenity, parking add-ons, “technology package,” insurance requirements.
* **Constraints**: income multiple, credit score, guarantor rules, roommates, subletting, lease length, early termination.
* **Parking truth**: assigned vs tandem vs optional; EV charging; waitlists; height limits.
* **Utility split**: RUBS, included vs not, mandatory internet.

#### Architecture

1. **Document capture**

   * Listing description + “fine print” sections + PDFs (house rules, sample lease).
   * Firecrawl scrape/crawl for the page + linked documents (where allowed). ([Firecrawl][11])

2. **Schema extraction**

   * Use OpenAI **Structured Outputs** with a strict `LeaseAndCostSchema` so every listing has consistent fields. ([OpenAI Platform][19])

3. **Bait-and-switch signals**

   * A classifier + rules layer for phrases like:

     * “starting at”, “price may vary”, “photos of similar unit”, “limited time”, “call for details”
   * Cross-source diffs:

     * Compare PM site vs aggregator listing for rent ranges, sqft, and specials.
     * If inconsistent → generate “discrepancy report” + suggested questions.

4. **Missing-data handling**

   * If parking fee missing, infer plausible range from building/area comps, but label as estimate with confidence.
   * Generate “ask list” tailored to what’s missing.

#### Implementation detail

Use **function calling** to:

* fetch additional pages for the same building,
* run a “difference check,”
* and push structured “issues” into your workflow system. ([OpenAI Platform][20])

---

### 4) Hidden-Gem Value Engine (Comps + Anomalies + Evidence)

**Why it’s #4**
This is the “find the deal that feels like cheating” module.

#### Core idea

Build a model that predicts rent given:

* location + commute distribution + microclimate/noise
* extracted interior quality (photo intelligence)
* building attributes (age proxies, permit activity)
  Then rank by **(predicted fair rent − asking rent)** subject to your preferences.

#### Data sources

* Your unified listing dataset (from feature #1).
* SF building permits data as a proxy for recent renovations at the address. ([San Francisco Data][3])
* DBI complaints / notices of violation as a risk modifier (avoid “cheap for a reason”). ([San Francisco Data][8])

#### Modeling stack

* **Hedonic model** (e.g., gradient boosting / GAM) trained on your continuously refreshed dataset.
* **Uncertainty estimation**: prediction intervals so you don’t overreact to weak signals.
* **Counterfactual explanations**:

  * “This is undervalued because it’s priced like a dated unit, but photos show renovated kitchen + good light.”

#### UX outputs

* “Hidden gems” tab with:

  * *Value score* (with confidence)
  * evidence cards (photos/text)
  * “why priced low” hypotheses (location, noise risk, missing amenities)
  * questions to validate quickly

---

### 5) Action Advantage (Rent‑Fast Prediction + Next‑Best Actions)

**Why it’s #5**
Finding great apartments is necessary; acting at the right time is how you actually get them.

#### Inputs

* Listing freshness + update patterns from crawls.
* Value score + desirability score.
* “Friction score” (application complexity, required docs).
* Market signals: how many similar units show up and disappear.

#### Modeling

* A **survival / hazard model** or simpler logistic model:

  * predicts probability the unit is gone in 24/48/72 hours.
* Features:

  * days on market, price vs comps, neighborhood demand proxy, photo quality/quantity, whether it’s a “rare combo” (e.g., 2br + in-unit laundry + parking).

#### Outputs

* A prioritized queue:

  * **Now**: contact + schedule tour
  * **Soon**: watchlist + prepare docs
  * **Later**: low urgency / likely to linger
* “Next best action” generator:

  * pre-drafted email/text questions based on missing fields (parking, utilities, specials fine print).
* Use **function calling** to integrate with your own CRM-like tracker (status, outreach, tours, outcomes). ([OpenAI Platform][20])

---

## Implementation notes (cross-cutting)

### Data model that makes everything else work

* **Canonical entities**

  * Building (address, lat/lng, footprint polygon)
  * Unit / floorplan
  * Listing instance (source URL, timestamp, price, media)
* **Attribute store with uncertainty**

  * Every extracted field is `(value, confidence, evidence_refs, source)` rather than a single “truth.”

### Retrieval that feels “superhuman”

* **Hybrid search**

  * Structured filters (beds/baths, price, parking)
  * Semantic search over:

    * raw text
    * extracted “pros/cons”
    * photo embeddings (kitchen vibe, sunlight vibe)
* Embeddings + vector search are built for this kind of similarity and clustering. ([OpenAI Platform][13])

### Scale strategy

* Use **Batch API** for nightly/weekly reprocessing (e.g., recompute all photo scores or rerun extraction after schema upgrades). ([OpenAI Platform][21])
* Keep low-latency processing for newly discovered listings and your shortlists.

### SF-specific “unfair advantages” that are actually actionable

* **Commute distribution (not just distance)**

  * GTFS schedule-based door-to-door estimates (Muni/BART), optionally augmented by real-time regional transit feeds via 511. ([SFMTA][22])
* **Noise**

  * 311 noise complaints density as a proxy (imperfect, but useful when aggregated). ([San Francisco Data][16])
  * SFO flight path/noise contour overlays for “sleep risk.” ([San Francisco International Airport][5])
* **Sun/fog**

  * Fog datasets help estimate “sun reliability” by area/season. ([USGS][6])

---

## Risks, failure modes, and mitigations (accuracy + hallucination risks)

### 1) **Photo inference overconfidence**

* **Failure mode:** Model says “hardwood” when it’s LVP; “quiet” when it’s on a bus corridor.
* **Mitigations:**

  * Always output **confidence** + **evidence photo indices**.
  * Use two-stage verification: LLM vision → specialist CV checks (SAM segmentation; CLIP similarity). ([GitHub][17])
  * Add a “must-see confirmations” checklist for top candidates.

### 2) **Text extraction misses edge-case lease clauses**

* **Failure mode:** Hidden fee buried in a PDF or only mentioned on application page.
* **Mitigations:**

  * Crawl the *application and FAQ pages* for the same domain/building when found (within allowed access).
  * Use schema-based extraction with strict required fields + “unknown” allowed (don’t force guesses). ([OpenAI Platform][19])
  * Diff across sources and surface inconsistencies.

### 3) **Entity resolution mistakes (wrong building / wrong unit)**

* **Failure mode:** Merge two addresses with similar names; mis-attach photos to the wrong unit.
* **Mitigations:**

  * Strong address normalization + geocoding + building footprint joins. ([San Francisco Data][9])
  * Keep listing instances separate until a threshold of match signals is met (name + coordinates + phone + photo overlap).
  * Preserve provenance so you can “unmerge” cleanly.

### 4) **Value model flags scams or “cheap for a reason” as hidden gems**

* **Failure mode:** Underpriced listing is missing key negatives or isn’t real inventory.
* **Mitigations:**

  * “Undervalue” requires **multiple evidence channels**:

    * price residual + photo quality + consistent cross-source data.
  * Penalize “uncertain / inconsistent” listings.
  * Use building health signals (complaints/violations) as risk modifiers. ([San Francisco Data][8])

### 5) **SF-specific layers mislead when used naively**

* **Failure mode:** 311 noise complaints reflect reporting behavior, not actual decibel levels.
* **Mitigations:**

  * Treat as *probabilistic proxy*; combine with multiple indicators (arterials, venues, flight paths).
  * Display “why this score exists” and allow user weighting.

---

## MVP subset I’d build first (highest leverage, fastest learning)

1. **Inventory backbone**

   * Firecrawl-based ingestion + URL discovery (Search/Map/Crawl) + a clean normalized schema + dedupe graph. ([Firecrawl][1])

2. **Text intelligence v1**

   * Structured extraction for lease constraints/fees/specials + discrepancy flags.
   * This immediately reduces wasted tours and lets you rank with real total cost.

3. **Photo intelligence v1 (high-signal, low-risk)**

   * Start with robust, easier-to-detect attributes:

     * flooring type (carpet vs not), washer/dryer presence, window size proxy, kitchen/bath condition tier, obvious street-facing cues.
   * Store evidence and confidence from day one. ([OpenAI Platform][23])

4. **Near-miss explorer + preference tuning**

   * Simple Pareto frontier: show “almost matches” + explain trade-offs.
   * Add “adjust one thing” recommendations (budget/parking/laundry/commute).

5. **Action advantage (heuristics → model)**

   * MVP: heuristics (freshness + rare-combo + price vs comps) to create a prioritized queue.
   * Then upgrade to a learned hazard model as you collect outcomes.

If you want, I can also sketch the **exact JSON Schemas** (for Firecrawl Extract + OpenAI Structured Outputs) for: `ListingCore`, `LeaseAndCosts`, and `VisualSignals`, because those schemas are the “spine” that makes the whole system reliable.

[1]: https://docs.firecrawl.dev/api-reference/endpoint/search?utm_source=chatgpt.com "Search - Firecrawl Docs"
[2]: https://platform.openai.com/docs/api-reference/responses?utm_source=chatgpt.com "Responses | OpenAI API Reference"
[3]: https://data.sfgov.org/Housing-and-Buildings/Building-Permits/i98e-djp9?utm_source=chatgpt.com "Building Permits | DataSF - San Francisco Open Data - SF.gov"
[4]: https://gtfs.org/?utm_source=chatgpt.com "General Transit Feed Specification: Home"
[5]: https://www.flysfo.com/about/community-noise/noise-office/live-flight-tracking?utm_source=chatgpt.com "Aircraft Noise and Flight Tracking"
[6]: https://www.usgs.gov/centers/western-geographic-science-center/science/pacific-coastal-fog-project?utm_source=chatgpt.com "The Pacific Coastal Fog Project | U.S. Geological Survey"
[7]: https://www.usgs.gov/3d-elevation-program?utm_source=chatgpt.com "3D Elevation Program | U.S. Geological Survey"
[8]: https://data.sfgov.org/Housing-and-Buildings/Department-of-Building-Inspection-Complaints-All-D/gm2e-bten?utm_source=chatgpt.com "Department of Building Inspection Complaints (All Divisions)"
[9]: https://data.sfgov.org/Geographic-Locations-and-Boundaries/Building-Footprints/ynuv-fyni?utm_source=chatgpt.com "Building Footprints | DataSF - San Francisco Open Data"
[10]: https://docs.firecrawl.dev/api-reference/endpoint/map?utm_source=chatgpt.com "Map"
[11]: https://docs.firecrawl.dev/features/crawl?utm_source=chatgpt.com "Crawl"
[12]: https://docs.firecrawl.dev/api-reference/endpoint/extract?utm_source=chatgpt.com "Extract"
[13]: https://platform.openai.com/docs/guides/embeddings?utm_source=chatgpt.com "Vector embeddings | OpenAI API"
[14]: https://platform.openai.com/docs/api-reference/vector-stores?utm_source=chatgpt.com "Vector stores | OpenAI API Reference"
[15]: https://platform.openai.com/docs/api-reference/batch?utm_source=chatgpt.com "Batch | OpenAI API Reference"
[16]: https://data.sfgov.org/City-Infrastructure/311-Cases/vw6y-z8j6?utm_source=chatgpt.com "311 Cases | DataSF - San Francisco Open Data"
[17]: https://github.com/facebookresearch/segment-anything?utm_source=chatgpt.com "facebookresearch/segment-anything"
[18]: https://github.com/openai/CLIP?utm_source=chatgpt.com "CLIP (Contrastive Language-Image Pretraining), Predict ..."
[19]: https://platform.openai.com/docs/guides/structured-outputs?utm_source=chatgpt.com "Structured model outputs | OpenAI API"
[20]: https://platform.openai.com/docs/guides/function-calling?utm_source=chatgpt.com "Function calling | OpenAI API"
[21]: https://platform.openai.com/docs/guides/batch?utm_source=chatgpt.com "Batch API"
[22]: https://www.sfmta.com/reports/gtfs-transit-data?utm_source=chatgpt.com "GTFS Transit Data"
[23]: https://platform.openai.com/docs/guides/images-vision?utm_source=chatgpt.com "Images and vision | OpenAI API"
