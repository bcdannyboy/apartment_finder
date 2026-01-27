## Pipeline

### A) Ranking pipeline diagram

```
                    OFFLINE / CONTINUOUS INDEXING
┌───────────────┐   ┌──────────────────────────────┐   ┌──────────────────────────┐
│ Firecrawl +   │→→ │ Extract → Canonical Schema   │→→ │ Entity resolution +       │
│ connectors    │   │ (fields + provenance +       │   │ de-dupe + contradiction   │
│ (many sources)│   │ evidence snippets)           │   │ resolution               │
└───────────────┘   └──────────────────────────────┘   └──────────────────────────┘
                                                           │
                                                           ▼
                                             ┌──────────────────────────┐
                                             │ Data quality & spam score │
                                             │ + field confidences       │
                                             └──────────────────────────┘
                                                           │
                                                           ▼
                                             ┌──────────────────────────┐
                                             │ Feature store (SQL) +     │
                                             │ Vector index (embeddings) │
                                             └──────────────────────────┘


                    ONLINE / PER-QUERY RANKING
┌──────────────────────────────┐
│ User natural-language spec   │
│ + saved prefs + constraints  │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Parse to structured “search  │
│ spec” (hard/soft, weights,   │
│ commute target, stretch)     │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Stage 1: HARD FILTER         │  → (also produce a “near-miss” pool)
│ (probabilistic if uncertain) │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Stage 2: FAST SCORER         │
│ (feature-based utility)      │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Stage 3: LLM RE-RANK (top N) │
│ grounded in extracted fields │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Diversity rerank (MMR/xQuAD) │
│ + exploration slots (bandit) │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Output: ranked list +         │
│ “why ranked #1” breakdown +   │
│ verify queue for missing data │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Feedback logger: clicks/saves │
│ contacts/hides + pairwise     │
└──────────────────────────────┘
               ▼
┌──────────────────────────────┐
│ Online personalization +      │
│ Offline learning-to-rank      │
└──────────────────────────────┘
```

### What makes this robust for apartments

* **Provenance-first schema**: every field is `(value, confidence, sources[], evidence_snippets[])`. Contradictions are *kept* (as distributions) rather than overwritten.
* **Separate “hard filter” vs “near-miss” pool**: prevents the system from hiding “almost perfect except +$150” apartments.
* **Diversity as a final re-ranking layer**: avoids accidentally biasing the relevance model; this matches how classic IR diversification approaches are applied on top of a relevance ranking (e.g., MMR, xQuAD). 

---

## Scoring model

### B) Core scoring formula

Let a listing be (d), user spec be (u).

**Stage 1 (hard constraints):** pass/fail, but *probabilistic if uncertain*
For each hard constraint (c), compute (P(c\text{ satisfied}\mid d)). Keep the listing if:

[
\min_{c \in \text{hard}} P(c\mid d) \ge p_{\min}
]

Typical: (p_{\min} = 0.95). If it fails but is “close” (or uncertainty is high), it goes to the **near-miss** set with a labeled reason.

**Stage 2 (fast utility score):**
[
S_2(d) ;=; \underbrace{\sum_{k} w_k , \tilde{s}*k(d,u)}*{\text{multi-objective utility}} ;-;
\underbrace{\beta_{\text{risk}},R(d)}*{\text{spam/contradictions}} ;-;
\underbrace{\beta*{\text{unc}},U(d)}_{\text{missing/low-confidence}}
]

Where:

* (s_k \in [0,1]) is a satisfaction score for objective (k) (price, commute, size, amenities, …).
* (\tilde{s}_k) is *confidence-adjusted* satisfaction:
  [
  \tilde{s}_k = c_k , s_k + (1-c_k),\mu_k
  ]
  (c_k) is field confidence; (\mu_k) is a conservative prior (or worst-case for safety).
* (R(d)): risk score (scam likelihood, contradictions, suspicious patterns).
* (U(d)): uncertainty penalty (important fields missing/low confidence).

**Stage 3 (LLM grounded re-rank on top N):**
[
S_3(d)=\alpha S_2(d) + (1-\alpha) , S_{\text{LLM}}(d,u) - \gamma , \text{LLM_flags}(d)
]

* (S_{\text{LLM}}) is a semantic alignment score the LLM produces **only from structured fields + evidence snippets** (no free-form guesses).
* You keep (\alpha) high (e.g. 0.6–0.85) so the LLM “nudges” rather than overrides.

Why this shape:

* Stage-2 is your *calibrated, testable* ranker (like classic LTR pipelines). LambdaRank/LambdaMART are standard approaches for optimizing ranking metrics like NDCG. ([NeurIPS Papers][1])
* Multi-objective ranking is a known extension; you can treat multiple business/objective signals jointly. 

---

### Feature list (practical + diversity-ready)

**Hard-constraint fields (filter):**

* price (monthly), deposit/fees, lease length
* beds/baths, availability date
* pets allowed (cats/dogs, restrictions)
* location bounding (SF + neighborhoods), max commute time
* must-have amenities (if truly hard): e.g. “in-unit W/D required”

**Core utility features (score):**

1. **Price utility** (with stretch logic)
2. **Commute utility** (by transit/walk/bike; time-of-day aware)
3. **Space utility** (sqft, layout quality, storage)
4. **Amenity match** (in-unit laundry, dishwasher, elevator, parking, outdoor space, AC, gym)
5. **Neighborhood preference** (explicit neighborhoods + learned taste embedding)
6. **Building type preference** (Victorian vs modern high-rise, condo vs rental building)
7. **Move-in/lease fit** (date window, lease length match)
8. **Quality/trust**

   * listing recency, source reputation
   * completeness % of key fields
   * duplicate/cross-post evidence
9. **LLM semantic tags** (but stored as structured tags)

   * “quiet street”, “great natural light”, “top floor”, “walkable”, “near park”
   * each tag has a confidence + evidence quote id

**Risk & robustness features (penalties):**

* contradiction score: e.g., pets policy differs across sources
* “too good to be true” patterns: price outlier vs neighborhood distribution, missing address, “wire money” language
* duplicate suspicion: same photos, same contact #, same rent with varied addresses
* stale listing probability: older than X days, repeated reposting

---

### Multi-objective utilities (with “stretch budget”)

A clean, explainable set of satisfaction functions:

**Price** (budget (B), stretch limit (B_s), decay (\tau)):
[
s_{\text{price}}(p)=
\begin{cases}
1 & p \le B \
\exp\left(-\frac{p-B}{\tau}\right) & B < p \le B_s \
0 & p > B_s \quad(\text{hard fail})
\end{cases}
]

Interpretation: within stretch you can “pay for perfection,” but it must earn it.

**Commute** (target (t_0), max (t_{\max}), decay (\tau_c)):
[
s_{\text{commute}}(t)=
\begin{cases}
1 & t \le t_0 \
\exp\left(-\frac{t-t_0}{\tau_c}\right) & t_0 < t \le t_{\max} \
0 & t > t_{\max} \quad(\text{hard fail})
\end{cases}
]

**Size** (min (a_{\min}), “good enough” (a_{sat})):
[
s_{\text{size}}(a)=\text{clip}\left(\frac{a-a_{\min}}{a_{sat}-a_{\min}}, 0, 1\right)
]

**Amenities** (weighted checklist):
[
s_{\text{amen}} = \sum_{m} w_m \cdot \mathbb{1}[m\in d]
]

Where ( \sum_m w_m = 1).

---

### Constraint relaxation + “near-miss” suggestions

For each hard constraint (c), define a *slack* (\Delta_c(d)) (how far it misses).

Examples:

* price slack: (\Delta_{$}=\max(0, p-B))
* commute slack: (\Delta_t=\max(0, t-t_{\max}))
* bedroom slack: studio vs 1BR

Near-miss score:
[
S_{\text{near-miss}}(d)= S_2(d) - \sum_{c} \lambda_c , \text{normalized}(\Delta_c(d))
]

Then you present:

* **Top-K strict matches**
* **Top-K near-misses** grouped by “what to relax” (e.g., “+5 min commute adds 18 options”).

---

## Diversity algorithm

### C) Diversity strategy (algorithm + parameters)

You want diversity across:

* neighborhood
* building (avoid showing 5 units in the same complex)
* source domain (avoid one aggregator dominating)
* building type / era
* price tier (sometimes)
* “vibe clusters” (quiet/green vs nightlife, modern vs classic)

#### 1) Greedy MMR re-ranking (simple + strong baseline)

MMR’s core idea is a linear tradeoff between relevance and novelty: pick items that are relevant **and** not too similar to already-picked items. 

Given candidates (C) with relevance score (S_3(d)), produce top-K list (L):

[
\text{MMR}(d)= \lambda , S_3(d) ;-; (1-\lambda),\max_{l\in L}\text{sim}(d,l)
]

* **sim(d,l)** combines:

  * geo/neighborhood similarity (geohash distance)
  * same-building indicator
  * same-source indicator
  * embedding cosine similarity of the “description+amenities” text

**Recommended parameters (start):**

* K = 10 or 20
* (\lambda = 0.70) (70% relevance, 30% novelty)
* Hard caps (guardrails):

  * max_per_building = 1 (or 2 if user explicitly wants that building)
  * max_per_neighborhood = 3 in top 10
  * max_per_source = 3 in top 10
    These caps prevent the “one building dominates” problem even if sim is imperfect.

#### 2) xQuAD-style coverage (explicit “aspects”)

xQuAD is a probabilistic framework that diversifies by explicitly modeling aspects/sub-queries and selecting items that balance base relevance with uncovered aspects. ([IW3C2 Archives][2])

You can adapt “aspects” to apartments:

* neighborhoods (Mission, Sunset, …)
* building types (Victorian, mid-rise, high-rise)
* commute modes/lines (Muni, BART lines)
* amenity bundles (W/D+DW, parking+elevator, outdoor space)

In practice:

* derive aspect weights (P(a\mid u)) from the user spec + learned preferences
* derive (P(a\mid d)) from listing metadata + LLM-tag probabilities (grounded)

Then rerank top-K with xQuAD after Stage 3.

**Recommended parameters (start):**

* (\lambda_{\text{xquad}} = 0.3) (diversify but don’t tank relevance)
* 5–15 aspects total (too many makes it noisy)

#### 3) Exploration/exploitation (so you discover options you didn’t think to search)

To avoid filter bubbles, reserve **exploration slots** (e.g., 20% of top-10) where you promote items with high *expected upside* or underrepresented facets.

Two proven approaches:

* **LinUCB / contextual bandits**: choose items by upper-confidence bounds (estimate + uncertainty), explicitly trading off exploration and exploitation. ([Artificial Intelligence Lab Brussels][3])
* **Thompson sampling**: sample from a posterior and pick the best under that sample; works well in contextual bandits too. ([Proceedings of Machine Learning Research][4])

**A practical hybrid policy**

* Top (K-K_explore): MMR/xQuAD diversified relevance list
* Remaining K_explore: pick from underrepresented neighborhoods/building types with highest bandit score

Start with:

* explore_rate ε = 0.2
* only explore among candidates above a relevance floor (e.g., (S_3(d) \ge \text{percentile}_{70})) so you don’t waste slots

#### (Optional) DPP as “later upgrade”

Determinantal Point Processes are another principled way to select diverse sets; YouTube has published on using DPPs for diversified recommendations. ([ACM Digital Library][5])
You likely don’t need DPP at v1; MMR + caps + exploration gets you 90% of the value with easier debugging.

---

## Feedback loop

### D) Feedback learning plan (short-term + long-term)

#### What to log

Every impression should log:

* query/user spec snapshot (structured)
* shown rank position (for position bias)
* listing features + confidences at serve-time
* actions: click, dwell, save, hide, contact, schedule tour

#### Short-term personalization (minutes → days)

1. **Pairwise preference prompts (high signal)**

   * Occasionally ask: “Do you prefer A or B?” plus “why?”
   * Turn “why” into *reason codes* (price, commute, vibe, light, noise, neighborhood, amenities)
2. **Online weight updates**

   * Lightweight online learning on top of stage-2 features:

     * logistic regression / Bayesian linear model for (w_k)
     * per-feature learning rates based on reason codes
3. **Pairwise preference model**

   * Use Bradley–Terry style modeling to map pairwise choices into a consistent latent utility scale. ([Wikipedia][6])
   * This is especially good when you have only dozens/hundreds of explicit comparisons.

#### Long-term learning-to-rank (weeks → months)

1. **Train a proper LTR model (LambdaMART-style)**

   * Use sessions as “queries,” listings as “documents,” labels from outcomes (contact > save > click > ignore).
   * LambdaMART is a common high-performing baseline for ranking problems. 
2. **Correct for click/position bias**

   * Click logs are biased by rank position; use inverse propensity weighting / unbiased LTR techniques. 
3. **Multi-objective optimization**

   * If you want the model to jointly optimize for “likely-to-contact” *and* “diversity/novelty,” treat them as multiple objectives or incorporate them as constraints/regularizers. 
4. **Explainability**

   * If Stage 2 is a tree model (GBDT), use TreeSHAP-style feature attributions to generate faithful per-listing explanations. ([PubMed][7])

---

## Uncertainty handling

(You asked explicitly; putting the mechanics here because it drives ranking quality.)

### Field confidence + penalties

Each extracted field gets a confidence from:

* extractor certainty (regex/structured data > LLM extraction > heuristic)
* cross-source agreement (multiple sources matching ↑)
* internal consistency checks (beds/baths vs text, rent vs neighborhood distribution)
* recency / staleness

Then:

* **Hard filters use probability of constraint satisfaction**
* **Soft scoring uses confidence-adjusted utility**
* **Uncertainty penalty prevents “unknowns” from dominating top ranks**

If you’re producing calibrated probabilities (e.g., “pets allowed” classifier), calibration methods like temperature scaling are a standard way to make scores more probabilistically meaningful. ([arXiv][8])

### Targeted verification queue (high ROI)

When a listing has:

* high (S_3) **and**
* missing/uncertain a key field (pets, exact rent, sqft, address)

…put it in a “verify” queue:

* re-crawl the listing + linked pages
* scrape structured sources (property site, leasing PDF)
* extract only the missing fields with evidence
* optionally prompt the user: “Want me to verify pets + exact rent?”

This keeps the system honest and reduces time wasted touring non-qualifying units.

---

## Worked example

### E) Example scoring breakdown for 3 hypothetical listings

#### Sample preference spec (structured)

* **Must**: SF proper, allows **cat**, availability within 30 days
* **Budget**: (B=$3,800) / month, **stretch** to (B_s=$4,200) if excellent
* **Commute**: target (t_0 = 25) min transit to downtown/SOMA, hard max (t_{\max}=35)
* **Soft weights**:

  * price 0.35
  * commute 0.25
  * size 0.15 (min 550 sqft, saturates at 750)
  * amenities 0.15 (in-unit W/D 0.4, dishwasher 0.2, elevator 0.1, gym 0.1, near park 0.2)
  * neighborhood preference 0.10

**Stage-3 blend**: (\alpha = 0.7) (70% feature model, 30% LLM semantic)

---

### Listing 1 — “Mission Bay high-rise”

* $4,150, 1BR, 650 sqft
* commute 12 min
* amenities: in-unit W/D ✅, dishwasher ✅, elevator ✅, gym ✅, near park ✅
* neighborhood preference: 0.60
* confidence: 0.95, risk: 0.05
* LLM semantic/vibe score: 0.85

**Satisfaction**

* (s_{price}=\exp(-(4150-3800)/400)=0.4169)
* (s_{commute}=1.0) (≤ 25 min)
* (s_{size}=(650-550)/(750-550)=0.50)
* (s_{amen}=1.00)
* (s_{nbhd}=0.60)

**Stage 2 contributions**

* price: 0.35×0.4169 = 0.1459
* commute: 0.25×1.0 = 0.2500
* size: 0.15×0.50 = 0.0750
* amenities: 0.15×1.00 = 0.1500
* neighborhood: 0.10×0.60 = 0.0600
  Base utility = **0.6809**

Penalties:

* risk: 0.15×0.05 = 0.0075
* uncertainty: 0.10×(1-0.95)=0.0050
  Stage-2 score (S_2)=**0.6684**

**Stage 3 final**
[
S_3=0.7\cdot 0.6684 + 0.3\cdot 0.85 = 0.7229
]

**Why it ranks well**

* “Exceptional commute + perfect amenity bundle” offsets stretching the budget.

---

### Listing 2 — “Inner Sunset classic 1BR”

* $3,600, 1BR, 720 sqft
* commute 33 min
* amenities: dishwasher ✅, near park ✅, in-unit W/D ❌, elevator ❌, gym ❌
* neighborhood preference: 0.90
* confidence: 0.80, risk: 0.15
* LLM semantic/vibe score: 0.82

**Satisfaction**

* (s_{price}=1.0) (≤ budget)
* (s_{commute}=\exp(-(33-25)/5)=0.2019)
* (s_{size}=0.85)
* (s_{amen}=0.40)
* (s_{nbhd}=0.90)

**Stage 2**

* base utility = 0.6780
* penalties: risk 0.0225, uncertainty 0.0200
  (S_2=0.6355)

**Stage 3**
[
S_3=0.7\cdot 0.6355 + 0.3\cdot 0.82 = 0.6908
]

**Why it ranks slightly lower than #1**

* Strong neighborhood + price + size, but commute is meaningfully worse than target.

---

### Listing 3 — “Nob Hill studio view”

* $3,250, studio, 550 sqft
* commute 22 min
* amenities: elevator ✅, dishwasher ❌, laundry unknown, near park ❌
* neighborhood preference: 0.70
* **pet policy contradictory across sources** (cats ok vs no pets)
* confidence: 0.60, risk: 0.35
* LLM semantic/vibe score: 0.70

**Satisfaction**

* (s_{price}=1.0)
* (s_{commute}=1.0)
* (s_{size}=0.0) (at minimum threshold)
* (s_{amen}=0.10)
* (s_{nbhd}=0.70)

**Stage 2**

* base utility = 0.6850
* penalties: risk 0.0525, uncertainty 0.0400
  (S_2=0.5925)

**Stage 3**
[
S_3=0.7\cdot 0.5925 + 0.3\cdot 0.70 = 0.6248
]

**Why it ranks lower**

* Size/amenity mismatch + major uncertainty/contradiction on a *hard* constraint (pets).
* This is exactly the kind of listing you’d push into a **verification queue** rather than silently drop.

---

### Final ranked order (before diversity rerank)

1. Mission Bay high-rise — **0.723**
2. Inner Sunset 1BR — **0.691**
3. Nob Hill studio — **0.625** (verify pets)

With many results, the **diversity reranker** (MMR/xQuAD + caps) would prevent “8 Mission Bay high-rises” from filling the top 10 unless they truly dominate on relevance—mirroring classic diversification methods’ relevance/novelty tradeoff. 

---

If you want, I can also sketch the exact JSON schema I’d use for: (1) listing canonical records (with provenance/confidence), and (2) the parsed user preference spec—because getting those two schemas right is what makes the whole pipeline testable and non-hallucination-prone.

[1]: https://papers.nips.cc/paper/2971-learning-to-rank-with-nonsmooth-cost-functions?utm_source=chatgpt.com "Learning to Rank with Nonsmooth Cost Functions - NIPS"
[2]: https://archives.iw3c2.org/www2010/proceedings/www/p881.pdf "fig-lambda.eps"
[3]: https://ai.vub.ac.be/sites/default/files/Contextual-Bandit%20Approach%20to%20Recommendation.pdf?utm_source=chatgpt.com "A Contextual-Bandit Approach to Personalized News ..."
[4]: https://proceedings.mlr.press/v28/agrawal13.html?utm_source=chatgpt.com "Thompson Sampling for Contextual Bandits with Linear Payoffs"
[5]: https://dl.acm.org/doi/10.1145/3269206.3272018?utm_source=chatgpt.com "Practical Diversified Recommendations on YouTube with ..."
[6]: https://en.wikipedia.org/wiki/Bradley%E2%80%93Terry_model?utm_source=chatgpt.com "Bradley–Terry model"
[7]: https://pubmed.ncbi.nlm.nih.gov/32607472/?utm_source=chatgpt.com "From Local Explanations to Global Understanding ... - PubMed"
[8]: https://arxiv.org/pdf/1706.04599?utm_source=chatgpt.com "On Calibration of Modern Neural Networks"
