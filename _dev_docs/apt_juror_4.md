## API/dataset recommendations (cited)

### Geocoding (robust, “partial address” tolerant)

**Recommended stack (best overall for SF apartment listings):**

* **Primary (high-quality + caching-friendly): Mapbox Geocoding API**

  * You can explicitly choose **Permanent vs Temporary** storage; **Permanent results can be cached/stored indefinitely** (Temporary cannot). ([Mapbox][1])
  * Good fit if you want to build your own map UX (Mapbox/OSM) without Google display constraints.

* **Secondary “truth check” (often best raw accuracy): Google Geocoding API**

  * Useful for resolving messy/partial addresses, business names, and new buildings—but note policy constraints: caching/storage is **generally restricted** (except **place IDs can be stored indefinitely**), and **Geocoding results displayed on a map must be shown on a Google Map**. ([Google for Developers][2])
  * Practical use: run it as a *validation / disambiguation step* and store only place IDs + your own derived features.

* **Local/offline/fully-controllable: Pelias (self-host)**

  * Open-source geocoder that turns addresses/place names into coordinates using open data. Great when you want “unlimited” internal queries and custom SF-specific tuning (parcel/building-aware). ([pelias.io][3])

**Nice-to-have / fallback:**

* **Nominatim (self-host recommended)**

  * Nominatim powers OSM’s geocoding; but the **public API has limited capacity** and you’re expected to be gentle—so for an apartment-hunting tool at scale, self-host or use a paid host. ([operations.osmfoundation.org][4])
* **OpenCage (hosted “open data” geocoding)**

  * Geocoding API based on open data via REST; useful as a cost-effective first pass before expensive providers. ([opencagedata.com][5])

---

### Routing & travel times (walk/bike/transit + time-of-day)

You’ll likely want **two layers**: (1) a high-quality commercial estimator, plus (2) an engine you can control (for bulk scoring + transparency).

**Time-of-day transit (commercial):**

* **Google Routes/Directions (Transit)**

  * Transit routing supports specifying **departure_time or arrival_time** (time-of-day commute scoring). ([Google for Developers][6])
  * Also has a **Compute Route Matrix** endpoint for batching. ([Google for Developers][7])
  * Caveat: Google platform terms/policies can constrain caching and how you display results. ([Google for Developers][2])

* **TravelTime (time-based search at scale)**

  * Strong for “**search/sort by travel time**” products: fast **time-map (isochrones)** + **time-filter (matrix)** workflows. ([TravelTime API Documentation][8])
  * Practical advantage: purpose-built for *filtering* large candidate sets by journey time, not just point-to-point directions.

**Self-host / full control (especially for advanced filters & explainability):**

* **OpenTripPlanner (OTP) for transit**

  * Open-source multimodal trip planning built to use **OpenStreetMap + GTFS**, and can consume **GTFS-Realtime** for delays/cancellations. ([OpenStreetMap][9])
  * This is the best path if you want “your own Google Transit” behavior and reproducible scoring logic.

* **Valhalla for walk/bike/driving (plus matrices + isochrones)**

  * Open-source routing engine on OSM; includes **time+distance matrix**, **isochrones**, and **elevation sampling**. ([GitHub][10])

* **GraphHopper (commercial APIs + open-source core)**

  * Offers isochrone + other routing capabilities; good option if you want a managed service built on open-source routing. ([GraphHopper Directions API][11])

**Batch routing for walk/bike/driving:**

* **Mapbox Matrix API** to efficiently compute travel times/distances among many points (very useful for scoring many listings vs many anchors). ([Mapbox][12])

---

### Isochrones (15/30/45 min “within reach” polygons)

You’ll want **isochrones for each anchor + commute window** so you can instantly filter the map and avoid per-listing routing calls.

Best-in-class options:

* **Mapbox Isochrone API**: returns reachable regions as polygon/line contours; supports **walking/cycling/driving**, typically up to **60 minutes**. ([Mapbox][13])
* **TravelTime time-map**: isochrones designed for high-performance “reachable area” search. ([TravelTime API Documentation][8])
* **openrouteservice Isochrones**: Isochrone service supports time/distance analyses and returns **GeoJSON** features. ([giscience.github.io][14])

---

### SF transit datasets for reliability (real-time feeds)

* **511 SF Bay Open Transit Data**

  * Provides bulk + API access to **GTFS** and **GTFS-Realtime** feeds (Trip Updates, Vehicle Positions, Service Alerts), plus APIs modeled after SIRI/NeTEx; requires a token and has documented rate limits. ([511.org][15])
  * This is your backbone for “transit reliability” and time-of-day scoring that reflects reality.

---

### SF open datasets for QoL proxies (noise, hills, parks, bike, etc.)

These are the datasets I’d treat as “first-class signals” in your GeoScore.

**Geocoding/address normalization helpers**

* **Streets – Active and Retired (street centerlines, includes CNN IDs)**
  Useful for canonical street name normalization, cross-street inference, and resolving partial addresses. ([Data.gov][16])
* **Parcels – Active and Retired**
  Recorded parcel geography (active + retired), helpful for snapping a listing to the correct parcel/building footprint. ([Data.gov][17])
* **Building Footprints**
  Great for “drop pin to the building” precision and to resolve ambiguous geocodes in dense areas. ([catalog-beta.data.gov][18])

**Noise proxy**

* **311 Cases (DataSF)**

  * Contains place-associated cases since July 1, 2008; refreshed daily; not every case has lat/lon; duplicates are common; description text may be withheld for privacy, but categories/types are published (good for “noise complaint density”). ([SF Digital Services][19])

**Bike friendliness & safety**

* **MTA Bike Network Linear Features** (bikeway network geometry; quarterly updates) ([Data.gov][20])
* **Traffic Crashes Resulting in Injury**
  Geocoded crash injury data (collected via CHP 555 reports; published on a schedule; includes accuracy caveats). Use it for a “crash risk” or “high-injury proximity” penalty. ([datagov-catalog-dev.app.cloud.gov][21])

**Parks / green space**

* **Recreation and Parks Properties** (parks, golf courses, campgrounds, etc.) ([Data.gov][22])
* **Street Tree List** (DPW-maintained street trees with location/species/planting date) — excellent proxy for shade/pleasant walks. ([Data.gov][23])

**Neighborhood boundaries (for labels, not scoring)**

* **Analysis Neighborhoods**
  41 “analysis” neighborhoods; explicitly **not an official neighborhood boundary** dataset—use it for UI labels and grouping only. ([San Francisco Data][24])

**Hills / elevation**

* **Elevation Contours (5-foot interval)** for SF mainland + Treasure/Yerba Buena. ([San Francisco Data][25])
* (Optional higher-res) **USGS 3DEP** elevation/terrain products (for DEM-based slope and route elevation gain). ([OpenTopography][26])

**Microclimate (foggy vs sunny)**

* **PRISM gridded climate datasets**

  * PRISM provides gridded datasets (and notes 800m datasets are available), including **solar radiation variables** (e.g., soltotal normals). Great foundation for “sunny score.” ([Prism Group][27])
* (Optional add-on) **USGS Pacific Coastal Fog Project** for fog/low cloud patterns along the CA coast. ([USGS][28])

**POIs (coffee/gym/grocery/etc.)**

* **OpenStreetMap via Overpass API** for free/complete POI coverage you can store locally. ([OpenStreetMap][29])
* (Optional enrichment) **Foursquare Places** and/or **Yelp Fusion** for richer categories/reviews and “open-now” signals. ([docs.foursquare.com][30])

---

## Architecture

### Core principle

Separate the system into:

1. **Truth layers** (raw datasets + geocodes + travel-time results)
2. **Feature layers** (noise density, slope, park access, reliability, etc.)
3. **Scoring layer** (user-specific weights + explainability)

### Proposed geo pipeline (high-level)

**1) Listing ingestion**

* **Firecrawl** pulls listing HTML + embedded JSON (where available).
* **OpenAI extraction** → structured fields:

  * address string(s), cross streets, building name, neighborhood hints, unit #, listing lat/lon if present.

**2) Address normalization + candidate generation**

* Normalize address tokens (St/Street, directional prefixes, unit extraction).
* Generate **candidate address hypotheses** when partial:

  * “123 Main near 2nd St” → candidate set (street centerline matches + cross-street constraints).

**3) Robust geocoding (multi-stage, confidence-scored)**

* Stage A: **Local snap** using SF datasets (fast, deterministic)

  * If listing includes cross streets or parcel/APN hints, try to resolve using:

    * Streets centerlines (CNN), Parcels, Building Footprints. ([Data.gov][16])
* Stage B: **Primary geocoder** (Mapbox Permanent)

  * Store result + confidence + feature type. ([Mapbox][1])
* Stage C: **Secondary resolver** (Google / OpenCage / Pelias) if confidence low

  * Use to disambiguate and then snap to the nearest building footprint centroid.
  * Keep a **geocode_confidence** scalar and a **geocode_source** enum.

**4) Anchor management**

* Anchors = user-specific points (work, partner, gym, favorite park, etc.).
* Each anchor gets:

  * location, active days, **time windows** (e.g., “weekday 8:30am depart”), preferred modes.

**5) Travel time computation (batch + cache-first)**

* Use **matrix APIs** whenever possible:

  * E.g., Google Compute Route Matrix supports up to hundreds of route elements per request; TravelTime supports very large “time filter” searches; Mapbox Matrix for walk/bike/driving. ([Google for Developers][7])
* Time-of-day strategy:

  * Define *buckets* (weekday AM peak, midday, weekday PM peak, weekend).
  * For each (anchor, bucket, mode), compute either:

    * matrix (anchor → many listings) or (many listings → anchor), depending on API constraints.
* Cache keys:

  * `(origin_h3, destination_id, mode, time_bucket, provider, provider_version)`
* TTL policy:

  * **Walking/biking**: long TTL (weeks/months)
  * **Transit “typical”** (schedule-based): medium TTL (days/week)
  * **Transit real-time reliability** (GTFS-RT): short TTL (minutes-hours)

**6) Isochrone precompute (for fast “within X minutes” filters)**

* For each anchor + time bucket + mode, compute 15/30/45-minute polygons:

  * Mapbox Isochrones (walk/bike/driving) ([Mapbox][13])
  * TravelTime time-map (excellent for time-based search) ([TravelTime API Documentation][8])
  * ORS Isochrones (GeoJSON) ([giscience.github.io][14])
* Store polygons and also **materialize listing membership**:

  * listing_id → boolean flags: `within_15m_work_transit_am`, etc.

**7) QoL feature engineering (PostGIS batch jobs)**

* Noise proxy:

  * Spatial join listing point with 311 case density by radius + time window (e.g., last 12 months). ([SF Digital Services][19])
* Park access:

  * Distance to nearest Rec/Park polygon; optional “park area within 10-min walk.” ([Data.gov][22])
* Bike friendliness:

  * Distance to protected lanes / bike network segments; crash-density penalty. ([Data.gov][20])
* Hilliness:

  * Slope around listing from contours/DEM; optional elevation gain to key destinations. ([San Francisco Data][25])
* Microclimate:

  * PRISM solar radiation/temperature normals → “sunny index”; optional fog index overlay. ([Prism Group][27])
* Greenness:

  * Street tree density within 250m–500m. ([Data.gov][23])

**8) Scoring + search**

* Persist all features and scores into:

  * **PostGIS** for spatial queries/joins
  * **Search index** (OpenSearch/Elasticsearch) for text filters + faceting
  * Optional: **Vector DB** for semantic “vibe queries” (LLM-generated embeddings)

**9) Explainability store**

* Every score write includes a **trace** object:

  * which datasets, which anchors, which time bucket, which transformations.

---

## GeoScore schema

### Data model (conceptual)

```json
{
  "listing_id": "abc123",
  "geocode": {
    "lat": 37.76,
    "lon": -122.42,
    "confidence": 0.86,
    "method": "mapbox_permanent_then_snap_to_building"
  },
  "anchors": [
    {
      "anchor_id": "work",
      "label": "Work",
      "weight": 0.6,
      "mode_priority": ["transit", "bike", "walk"],
      "time_buckets": ["weekday_am_0830"]
    },
    {
      "anchor_id": "partner",
      "label": "Partner",
      "weight": 0.4,
      "mode_priority": ["transit", "bike"],
      "time_buckets": ["weekday_pm_1800"]
    }
  ],
  "subscores": {
    "commute": 0-100,
    "walk_amenities": 0-100,
    "bike_friendliness": 0-100,
    "hilliness": 0-100,
    "noise_quiet": 0-100,
    "microclimate_sunny": 0-100
  },
  "geoscore_total": 0-100,
  "explain": {
    "top_drivers": [],
    "raw_metrics": {}
  }
}
```

### Suggested scoring functions (practical, explainable)

**1) Commute score (multi-anchor, weighted)**

* For each anchor *a*, pick best mode according to user priority (or show all modes).
* Convert time to score using a piecewise mapping (easy to explain):

  * 0 min → 100
  * 15 min → 90
  * 30 min → 70
  * 45 min → 50
  * 60 min → 30
  * 90+ min → 0
* Aggregate:
  [
  CommuteScore = \sum_a w_a \cdot Score(time_{a})
  ]

**2) Walkability to amenities**

* Define POI categories: coffee, gym, grocery, parks, etc.
* For each category, compute **walking time to nearest N** (e.g., N=3) and take a weighted blend (nearest matters most).
* Convert time to category score (same idea: piecewise).
* Aggregate across categories and normalize by category weights.

**3) Hilliness / elevation penalty (optional preference)**

* Compute a “hill index”:

  * median slope in 250m radius
  * * penalty for steepest nearby streets (e.g., 95th percentile slope)
* Convert to score: flat=100, very hilly=0.
* Apply only if user cares (weight can be 0).

**4) Noise proxy (“quiet mode”)**

* Use a blended proxy:

  * 311 noise-related case density (radius + recency) ([SF Digital Services][19])
  * proximity to high-activity corridors (optional: zoning + nightlife POIs)
* Convert to percentile score: quietest areas near 100.

**5) Microclimate proxy (“sunny mode”)**

* Base layer: PRISM solar radiation normals (soltotal, etc.) → higher = sunnier ([Prism Group][27])
* Optional: add fog/low-cloud frequency layer (USGS fog project) ([USGS][28])
* Score = weighted combination.

---

### Example computation (illustrative)

User preferences:

* Work (weight 0.6): transit at **8:30am weekday**
* Partner (weight 0.4): transit at **6:00pm weekday**
* Wants: **sunny + quiet**, mild hill sensitivity

Raw computed metrics for Listing L:

* Transit to Work @ 8:30am: **22 min**
* Transit to Partner @ 6:00pm: **28 min**
* Walk to coffee: **3 min**
* Walk to gym: **8 min**
* Walk to grocery: **10 min**
* Walk to park: **6 min**
* Hill index: moderate → hilliness subscore **70**
* Noise proxy: somewhat noisy corridor → noise subscore **40**
* Sunny proxy: above-average solar exposure → microclimate subscore **80**
* Bike friendliness: good bike network access → **85** ([Data.gov][20])

Convert commute times (piecewise):

* 22 min → ~80.7
* 28 min → ~72.7
  Weighted:
* CommuteScore = 0.6×80.7 + 0.4×72.7 = **77.5**

Amenities (category weights sum to 0.7 → normalize):

* coffee(0.2): 3 min → 95
* gym(0.1): 8 min → 80
* grocery(0.2): 10 min → 75
* park(0.2): 6 min → 85
  Weighted sum = 59 → normalized 59/0.7 = **84.3**

Final GeoScore weights (example):

* commute 0.45
* walk amenities 0.25
* bike 0.10
* sunny 0.10
* quiet 0.07
* hilliness 0.03

[
GeoScore = 0.45(77.5)+0.25(84.3)+0.10(85)+0.10(80)+0.07(40)+0.03(70)=77.4
]

**Explainability snippet you’d show:**

* “Commute drives 45% of your score: **22 min transit to Work at 8:30am**, **28 min transit to Partner at 6:00pm**.”
* “Amenities strong: coffee **3 min walk**, park **6 min walk**.”
* “Quiet mode penalty: higher 311 complaint density nearby (proxy signal).”
* “Sunny preference satisfied: PRISM solar radiation normals are above SF median for this location.” ([SF Digital Services][19])

---

## UI features

### Map & overlays

* **Listings heatmap** by GeoScore (and toggle by subscore: Commute / Quiet / Sunny / Bike / Walkability).
* **Isochrone overlays**:

  * “15/30/45 min from Work (Transit @ 8:30am)” polygons
  * Same for Partner / Gym / any anchor
* **Noise overlay** (toggle):

  * 311 noise case density (rolling 6–12 months) with smoothing.
* **Hill overlay**:

  * slope shading or “steep streets” highlight using elevation source.
* **Bike overlay**:

  * bike network segments + “low-stress” emphasis.

### Advanced geo search filters

* Natural language + structured:

  * “Within 25 min transit of work at 8:30am and within 10 min walk of a park; prefer sunny and quiet”
* UI equivalents:

  * **Within X minutes of Y** (anchor + mode + time bucket)
  * **Max uphill** (e.g., “avoid >8% slopes nearby”)
  * **Quiet mode threshold** (e.g., “below 30th percentile noise proxy”)
  * **Sunny mode threshold** (e.g., “above 60th percentile solar proxy”)

### Compare mode (two listings head-to-head)

* Side-by-side:

  * Commute times per anchor *by time bucket*
  * POI nearest distances (coffee/gym/grocery/parks)
  * Hill index, noise percentile, sunny percentile
* “What changed” explanation:

  * e.g., “Listing B is 7 minutes faster to Work but has 2× noise complaint density.”

### Time-of-day commute panel

* Slider / dropdown:

  * Weekday AM (8:00/8:30/9:00), Midday, PM
* Show:

  * “Typical (schedule)”
  * “Right now (real-time)” if GTFS-RT available ([511.org][15])

### Explainability everywhere

* Every score shows:

  * **Top 5 contributors** (positive/negative)
  * The exact computed facts:

    * “22 min transit @ 8:30am”
    * “3 min walk to coffee”
    * “Noise proxy: 311 density percentile”
  * Confidence badges:

    * “High confidence geocode” vs “Approximate location”

---

## Failure modes table

| Failure mode                                                              | How you detect it                                                      | Mitigation (pipeline)                                                                                                                               | User-facing behavior                                                                              |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **Ambiguous / partial address** (“near Dolores Park”, cross streets only) | Geocoder returns low confidence or multiple candidates                 | Generate candidates using street centerlines/parcels/building footprints; ask user to confirm via pin drop; store confidence score ([Data.gov][16]) | Show “Approximate location” badge + prompt: “Confirm building on map for accurate commute times.” |
| **311 data has missing lat/lon, duplicates, reporting bias**              | Missing coordinates, spikes, repeated cases                            | Use smoothing + rolling windows; treat as proxy only; blend with other signals (traffic corridors, zoning) ([SF Digital Services][19])              | Explain: “Noise score is a proxy based on nearby reports; may under/overestimate.”                |
| **Transit real-time feed gaps** (GTFS-RT down or partial)                 | Feed freshness checks, missing vehicle positions/trip updates          | Fall back to scheduled GTFS-only “typical” times; degrade reliability score                                                                         | “Real-time not available; showing typical commute time.” ([511.org][15])                          |
| **API quota / cost blowups for routing**                                  | Rising latency, rate-limit errors, spend anomalies                     | Cache by H3 + time bucket; prefer matrix endpoints; batch jobs; backoff + provider failover ([Google for Developers][7])                            | Keep UI responsive with cached values + “refresh estimates” button                                |
| **Microclimate proxy too coarse** (sunny/fog varies block-to-block)       | High uncertainty near gradients (west/east edges), conflicting signals | Use multiple layers (PRISM + fog index + distance-to-coast + elevation); expose uncertainty                                                         | “Sunny score: medium confidence” with a tooltip explaining inputs ([Prism Group][27])             |
| **Hilliness differs by route, not just location**                         | Large variance between “local slope” vs “route elevation gain”         | Compute both: neighborhood slope + route elevation gain (Valhalla/DEM); let user weight ([GitHub][10])                                              | “Bike score assumes flattest route; switch to ‘avoid hills’ routing.”                             |
| **Dataset boundaries ≠ “real” neighborhoods**                             | User confusion (“this isn’t my neighborhood”)                          | Use Analysis Neighborhoods only for labels; prefer lat/lon search + user-drawn polygons ([San Francisco Data][24])                                  | Display: “Neighborhood label is for analysis; search uses exact location.”                        |
| **Licensing/policy constraints (esp. Google)**                            | Policy review + automated compliance checks                            | Keep provider-specific caches/TTLs; avoid mixing restricted content with non-compliant map displays ([Google for Developers][2])                    | Transparent: “Some estimates provided by Provider X; details limited by terms.”                   |

---

If you want the “max quality + max freedom” configuration: **Mapbox (map+geocode permanent + walk/bike/driving) + OTP (transit with 511 GTFS/GTFS-RT) + TravelTime (fast isochrone/filtering layer)**, with SF open datasets powering the QoL proxies. That combination avoids most display/caching lock-in while still giving you very high commute fidelity and extremely fast “within X minutes” search.

[1]: https://docs.mapbox.com/api/search/geocoding/ "https://docs.mapbox.com/api/search/geocoding/"
[2]: https://developers.google.com/maps/documentation/geocoding/policies "https://developers.google.com/maps/documentation/geocoding/policies"
[3]: https://pelias.io/ "https://pelias.io/"
[4]: https://operations.osmfoundation.org/policies/nominatim/ "https://operations.osmfoundation.org/policies/nominatim/"
[5]: https://opencagedata.com/api "https://opencagedata.com/api"
[6]: https://developers.google.com/maps/documentation/directions/get-directions "https://developers.google.com/maps/documentation/directions/get-directions"
[7]: https://developers.google.com/maps/documentation/routes/compute-route-matrix-over "https://developers.google.com/maps/documentation/routes/compute-route-matrix-over"
[8]: https://docs.traveltime.com/api/reference/isochrones "https://docs.traveltime.com/api/reference/isochrones"
[9]: https://wiki.openstreetmap.org/wiki/OpenTripPlanner "https://wiki.openstreetmap.org/wiki/OpenTripPlanner"
[10]: https://github.com/valhalla/valhalla "https://github.com/valhalla/valhalla"
[11]: https://www.graphhopper.com/open-source/ "https://www.graphhopper.com/open-source/"
[12]: https://docs.mapbox.com/api/navigation/matrix/ "https://docs.mapbox.com/api/navigation/matrix/"
[13]: https://docs.mapbox.com/api/navigation/isochrone/ "https://docs.mapbox.com/api/navigation/isochrone/"
[14]: https://giscience.github.io/openrouteservice/api-reference/endpoints/isochrones/ "https://giscience.github.io/openrouteservice/api-reference/endpoints/isochrones/"
[15]: https://511.org/open-data/transit "https://511.org/open-data/transit"
[16]: https://catalog.data.gov/dataset/streets-active-and-retired "https://catalog.data.gov/dataset/streets-active-and-retired"
[17]: https://catalog.data.gov/dataset/?publisher=data.sfgov.org&tags=parcels "https://catalog.data.gov/dataset/?publisher=data.sfgov.org&tags=parcels"
[18]: https://catalog-beta.data.gov/dataset/building-footprints-04ba1 "https://catalog-beta.data.gov/dataset/building-footprints-04ba1"
[19]: https://sfdigitalservices.gitbook.io/dataset-explainers/311-cases "https://sfdigitalservices.gitbook.io/dataset-explainers/311-cases"
[20]: https://catalog.data.gov/dataset/?publisher=data.sfgov.org&q=bike&res_format=JSON "https://catalog.data.gov/dataset/?publisher=data.sfgov.org&q=bike&res_format=JSON"
[21]: https://datagov-catalog-dev.app.cloud.gov/dataset/traffic-crashes-resulting-in-injury "https://datagov-catalog-dev.app.cloud.gov/dataset/traffic-crashes-resulting-in-injury"
[22]: https://catalog.data.gov/dataset/recreation-and-parks-properties "https://catalog.data.gov/dataset/recreation-and-parks-properties"
[23]: https://catalog.data.gov/dataset/street-tree-list "https://catalog.data.gov/dataset/street-tree-list"
[24]: https://data.sfgov.org/Geographic-Locations-and-Boundaries/Analysis-Neighborhoods/p5b7-5n3h/about "https://data.sfgov.org/Geographic-Locations-and-Boundaries/Analysis-Neighborhoods/p5b7-5n3h/about"
[25]: https://data.sfgov.org/Energy-and-Environment/Elevation-Contours/rnbg-2qxw "https://data.sfgov.org/Energy-and-Environment/Elevation-Contours/rnbg-2qxw"
[26]: https://portal.opentopography.org/usgsDataset?dsid=CA_SanFrancisco_1_B23 "https://portal.opentopography.org/usgsDataset?dsid=CA_SanFrancisco_1_B23"
[27]: https://prism.oregonstate.edu/documents/PRISM_datasets.pdf "https://prism.oregonstate.edu/documents/PRISM_datasets.pdf"
[28]: https://www.usgs.gov/centers/western-geographic-science-center/science/pacific-coastal-fog-project "https://www.usgs.gov/centers/western-geographic-science-center/science/pacific-coastal-fog-project"
[29]: https://wiki.openstreetmap.org/wiki/Overpass_API "https://wiki.openstreetmap.org/wiki/Overpass_API"
[30]: https://docs.foursquare.com/data-products/docs/categories "https://docs.foursquare.com/data-products/docs/categories"
