# Ranking/Evaluation/Alerts Architecture (v1)

## SearchSpec Schema

Consolidated schema (hard vs soft vs tradeoffs vs anchors). This merges the SearchSpec from `architecture_kickoff.md` + `apt_judge.md` with the Preference Spec constructs in `apt_juror_2.txt`.

```ts
// SearchSpec is immutable and versioned; edits create a new spec_id.

type SearchSpec = {
  spec_id: string;
  created_at: string;           // ISO
  raw_prompt: string;
  locale: "sf";                // for now

  // 1) Hard constraints (must satisfy; allow probabilistic checks)
  hard: {
    price_max?: number;         // monthly
    price_stretch?: number;     // optional upper stretch
    beds_min?: number;
    baths_min?: number;
    sqft_min?: number;
    property_types?: string[];  // apartment/condo/sfh/room

    neighborhoods_include?: string[];
    neighborhoods_exclude?: string[];
    geo_bbox?: { min_lat: number; min_lng: number; max_lat: number; max_lng: number };

    commute_max_min?: Array<{
      anchor_id: string;        // reference into anchors[]
      mode: "transit"|"drive"|"bike"|"walk";
      max_min: number;
    }>;

    move_in_by?: string;        // ISO date
    lease_min_months?: number;
    lease_max_months?: number;

    must_have?: string[];       // e.g. ["in_unit_laundry", "parking"]
    exclude?: string[];         // e.g. ["shared_bath", "ground_floor"]

    pet_policy?: {
      cats?: "required"|"ok"|"no";
      dogs?: "required"|"ok"|"no";
      size_limits?: string;     // e.g. "<40lb"
    };
  };

  // 2) Soft preferences (scored, can be violated)
  soft: {
    weights: Record<string, number>;   // feature weight map
    nice_to_have?: string[];           // amenity list
    vibe?: string[];                   // e.g. ["quiet", "sunny", "modern"]
    neighborhood_boosts?: Record<string, number>;
    building_type_boosts?: Record<string, number>;
  };

  // 3) Tradeoffs (explicit relax rules)
  tradeoffs?: Array<{
    relax: string;                     // e.g. "price_max"
    benefit: string;                   // e.g. "commute_max_min"
    ratio: number;                     // e.g. 1.0 = $1 for 1 minute
  }>;

  // 4) Commute anchors + time windows
  anchors: Array<{
    anchor_id: string;
    label: string;                     // "Financial District"
    address?: string;
    lat: number;
    lng: number;
    modes: Array<"transit"|"drive"|"bike"|"walk">;
    time_windows?: Array<{             // optional; otherwise default peak
      days: string[];                  // ["mon","tue",...]
      depart_after: string;            // HH:MM local
      arrive_by?: string;              // HH:MM local
    }>;
    target_min?: number;               // preferred commute time
    max_min?: number;                  // hard ceiling
  }>;

  // 5) Diversity/exploration budget
  exploration: {
    pct: number;                       // % of top-K for exploration
    rules?: string[];                  // e.g. "underrepresented_neighborhoods"
  };

  // 6) Missing info prompts (for verify queue)
  missing_info?: string[];             // e.g. ["pets", "exact_sqft"]
};
```

Notes:
- Hard constraints must be enforceable from structured fields; if uncertain, use probabilistic filtering (see pipeline).
- Tradeoffs are used to score near-misses and to explain relaxations to the user.
- Anchors are first-class and shared by ranking + alerts.

---

## Ranking Pipeline (stages + scoring)

### Stage 0: Candidate retrieval
- Structured filters in Postgres/PostGIS (price, beds, neighborhoods, availability).
- Full-text search over descriptions/amenities.
- Semantic retrieval via embeddings (pgvector) for long-tail preferences (e.g., “quiet top floor”).
- Retrieve top-N (e.g., 1,000) candidates before scoring.

### Stage 1: Hard filter (+ near-miss pool)
- For each hard constraint `c`, compute `P(c satisfied | listing)` using field confidence and uncertainty.
- Keep if `min_c P(c) ≥ p_min` (default 0.95).
- If fails but slack is small or uncertainty high → put in **near-miss pool** with failure reason + slack.

### Stage 2: Fast utility scorer (deterministic, testable)
Weighted, confidence-adjusted utility with penalties:

```
S2(d) = Σ_k w_k * (c_k * s_k + (1 - c_k) * prior_k)
        - β_risk * R(d)
        - β_unc * U(d)
        + β_fresh * Fresh(d)
```

Where:
- `s_k ∈ [0,1]` are satisfaction functions (price, commute, size, amenities, neighborhood, lease fit).
- `c_k` are field confidences; `prior_k` is conservative default when uncertain.
- `R(d)` includes contradiction score, scam signals, source trust penalties.
- `U(d)` captures missing/low-confidence critical fields.
- `Fresh(d)` boosts recently updated listings (tempered by source cadence).

Example satisfaction functions:
- **Price**: full score at/below budget, exponential decay to stretch limit, zero beyond.
- **Commute**: full at/below target, exponential decay to hard max, zero beyond.

### Stage 3: LLM rerank (top N → top K)
- Rerank top ~100 using **structured fields + evidence snippets only**.
- LLM returns `score`, `reasons`, `tradeoffs`, `verify_questions`.
- Blend with fast scorer to prevent LLM override:

```
S3(d) = α * S2(d) + (1 - α) * S_LLM(d) - γ * LLM_flags(d)
```

### Stage 4: Diversity rerank + caps
- Apply MMR/xQuAD with similarity over neighborhood, building, source, and embedding similarity.
- Enforce caps: max per building, per neighborhood, per source in top-K.

### Stage 5: Exploration slots (optional, controlled)
- Reserve `exploration.pct` of slots for underrepresented neighborhoods/building types with high upside.
- Use bandit scoring but only among candidates above a relevance floor.

---

## Diversity / Near-Miss Strategy

### Diversity
**Baseline:** Greedy MMR re-rank.

```
MMR(d) = λ * S3(d) - (1-λ) * max_{l in L} sim(d, l)
```

`sim(d,l)` combines:
- same building indicator
- same neighborhood
- same source
- embedding cosine similarity (description + amenities)

**Caps (guardrails):**
- max_per_building = 1–2
- max_per_neighborhood = 3 in top-10
- max_per_source = 3 in top-10

**Aspect coverage (xQuAD):** optionally ensure coverage across neighborhoods, building types, price bands, and commute lines.

### Near-Miss
- For each failed hard constraint `c`, compute slack Δc (e.g., price overage, commute overage, beds deficit).
- Score near-miss list as:

```
S_near(d) = S2(d) - Σ_c λ_c * normalized(Δc)
```

- Present near-misses grouped by “what to relax,” with explicit tradeoffs (e.g., “+5 min commute yields 14 more options”).

---

## Evaluation Plan + Metrics

### Golden sets (ground truth)
- **Extraction golden set**: 200–500 listings (frozen HTML snapshots + expected fields).
- **Dedupe golden pairs**: 200 duplicate + 200 non-duplicate pairs; later expand to clusters.
- **Ranking labels**: 0–3 relevance scale per SearchSpec:
  - 0 = not relevant (fails must-haves)
  - 1 = barely acceptable
  - 2 = good candidate
  - 3 = great / would tour
- **Audits**: weekly snapshot audits + monthly deep audits; stratify by neighborhood, price band, unit type.

### Core metrics
**Ranking quality**
- NDCG@k (primary)
- HitRate@k
- Precision@k / Recall@k
- Time-to-first-great-option (TTFGO)

**Coverage & discovery**
- Per-source capture recall vs gold
- Neighborhood recall + distribution drift
- Price-band recall
- Harvest ratio (relevant listings / pages crawled)

**Freshness**
- Time-to-discovery (TTD)
- Stale rate (% active in DB but removed at source)
- Time-to-removal (TTR)

**Extraction quality**
- Field accuracy, missingness, validity
- Critical-field pass rate (rent, beds/baths, neighborhood/geo, availability)

**Dedupe quality**
- Pairwise precision/recall/F1
- Cluster purity / completeness
- Duplicate collapse rate

**Diversity**
- Entropy across neighborhoods/sources in top-K
- Max-per-building violations

### Regression gates (initial)
- NDCG@10 drop ≤ 0.01 absolute
- HitRate@5 non-decreasing
- Extraction critical-field pass rate ≥ 90%
- Dedupe pairwise precision ≥ 0.95
- Median TTD ≤ 6h for crawl-allowed sources
- Stale rate ≤ 5%

### Cadence
- Nightly: re-evaluate ranking on frozen queries; freshness checks; parse regression on golden HTML.
- Weekly: coverage audits + missed-listing sweeps.
- Monthly: expand golden sets; recalibrate thresholds.

---

## Alerts + Change Events

### Change-event taxonomy (listing_changes)
- `new_listing`
- `price_change` (increase/decrease; include delta)
- `status_change` (active ↔ pending/off_market)
- `availability_change` (date moved earlier/later)
- `content_change` (amenities, description, photos)
- `removed` / `reactivated`

Each event stores: listing_id, detected_at, old_value, new_value, source_snapshot_id, change_confidence.

### Alert linkage rules
For each change event:
1. Re-evaluate listing against all active SearchSpecs (or indexed watchers by constraints).
2. Emit alerts when:
   - **New match**: listing becomes a strict match.
   - **Near-miss → match**: price drop or commute update crosses a hard threshold.
   - **Price drop**: drop ≥ user threshold or ≥ X% of rent.
   - **Availability moved earlier** within user’s window.
   - **Removed**: notify if listing was saved/shortlisted.

### Alert policies
- **Instant vs digest**: high-priority (new match, price drop) vs daily digest.
- **Cooldown**: suppress repeat alerts for the same listing within 24–72h unless change magnitude crosses another threshold.
- **Dedup**: collapse multiple changes in a short window into one alert with a summary.

### Priority scoring (alert ranking)
```
AlertScore = match_score_delta + price_drop_weight + freshness_weight + user_interest_weight
```
Use AlertScore to order digests and to decide push vs email.

---

## Conflicts / Open Questions

1. **Search backend split:** architecture references both OpenSearch and pgvector; decide if full-text uses Postgres FTS or OpenSearch (affects infrastructure).
2. **Confidence calibration:** define how extractor confidence is produced and calibrated (especially for LLM extraction and vibe tags).
3. **Hard-filter probability threshold:** default `p_min=0.95` vs more permissive; needs tuning against near-miss volume.
4. **LLM rerank budget:** top-N size and cost envelope; decide how often to rerank per search vs cached.
5. **Diversity caps:** user-editable vs fixed defaults (e.g., max per neighborhood/building).
6. **Alert semantics:** thresholds for “price drop” and “availability change” that warrant an alert; user-configurable?
7. **Gold set ownership:** who labels, how to ensure consistent 0–3 relevance guidelines.
8. **Risk signals:** define scam/contradiction score inputs and thresholds.
9. **Near-miss UX:** how many near-miss slots by default and how to present tradeoffs without overwhelming users.
