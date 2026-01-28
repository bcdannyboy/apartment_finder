STATUS: Non-authoritative research notes. Superseded where conflicts with architecture_source_of_truth.md and architecture_decisions_and_naming.md.

Overrides:
- Paid services limited to OpenAI and Firecrawl.
- Retrieval uses Postgres FTS + pgvector only.
- Extraction is centralized in Extraction Service; connectors do not extract.
- Manual-only sources are ImportTask only; no automated crawling.
- Geo and routing are local-only (Pelias, Nominatim fallback, OTP, Valhalla; OSRM secondary).
- Alerts are local notifications or SMTP only.

## Flow map

```text
[Start / “New move”]
   |
   v
[Onboarding: Criteria + Anchors] ---------------------------+
   |                                                       |
   | (creates Default Profile + weights + alerts prefs)     |
   v                                                       |
[Search Home: Split View (Map + List) + Chat Refinement] <--+
   |        |                 |                 |
   |        |                 |                 |
   |        |                 |                 +--> [Near‑Miss Explorer]
   |        |                 |                        (relax 1 constraint;
   |        |                 |                         see tradeoffs + new set)
   |        |                 |
   |        |                 +--> [Listing Detail Drawer/Modal]
   |        |                         |  |   |    |
   |        |                         |  |   |    +--> [Verify / Ask Agent / Capture Missing]
   |        |                         |  |   +--> [Add to Compare (2–6)]
   |        |                         |  +--> [Shortlist + Tag + Notes]
   |        |                         +--> [Open Source / Save PDF / Share]
   |        |
   |        +--> [Compare (2–6)]
   |                 |
   |                 +--> [Decide Next Action]
   |                         - schedule visit
   |                         - request application info
   |                         - apply
   |                         - reject with reason (teaches model)
   |
   +--> [Saved Searches / Alerts Center]
             |
             +--> (New match / price drop / status change) -> [Triage Queue]
                        |
                        +--> [Quick actions]
                              - Save to shortlist
                              - Hide
                              - “More like this”
                              - “Tell me what changed”
                              - Adjust profile rules

[Shortlist Workspace (Pipeline)]
   |
   +--> [Visit Plan Mode]
   |       - cluster by neighborhood
   |       - optimal route
   |       - checklist + questions
   |
   +--> [Application Pack Mode]
           - required docs
           - deadlines
           - risk flags
           - contact log

[Profile Manager]
   |
   +--> multiple profiles (Aggressive / Stretch / Roommate / Sublet)
   +--> A/B compare profiles on same listings
   +--> “Diversity dial” (strict ↔ explore)
```

Design rationale baked into the map: split map+list is a proven “evaluation-friendly” pattern in lodging/property discovery because it reduces the cost of switching contexts while scanning options. ([Baymard Institute][1])

---

## Wireframes (text)

### Screen list (primary)

1. Onboarding (criteria + anchors)
2. Search Home (Split View: map + list + conversational refinement)
3. Listing detail (drawer/modal)
4. Compare (2–6 listings)
5. Shortlist workspace (pipeline + notes/tags)
6. Near‑Miss Explorer (tradeoff sandbox)
7. Profiles (manage multiple preference specs)
8. Alerts center (triage queue + notification settings)

---

### 1) Onboarding: “Capture criteria + anchors”

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Ultimate Apartment Hunter                                            │
│ “Tell me what you want. I’ll learn fast.”                            │
├─────────────────────────────────────────────────────────────────────┤
│ (A) Natural-language intake                                          │
│  [ text box: “2BR, < $5.5k, bright, quiet, dog, near Caltrain…” ]    │
│  [Example prompts chips: Budget | Commute | Pet | Vibe | Must-haves ] │
│                                                                     │
│ (B) Structured spec preview (editable)                               │
│  Must-haves:  [ ] dog ok  [ ] in-unit laundry  [ ] parking?         │
│  Strong prefs:  sunlight ↑  quiet ↑  modern-ish ↑                    │
│  Dealbreakers:  “no ground-floor bedrooms”, “no street-facing”       │
│                                                                     │
│ (C) Anchors + commute constraints                                    │
│  Anchor 1: Work (address/search)  Mode: Transit  Time: 8:30am        │
│  Anchor 2: Partner work / gym / Caltrain / daycare…                  │
│  Max commute: [ 25 min ]  Reliability: [Prefer consistent]           │
│  [Preview isochrone on mini-map]                                     │
│                                                                     │
│ (D) Alerts + iteration posture                                       │
│  “Send me:  ( ) instant for perfect matches  ( ) daily digest”       │
│  Quiet hours: [ 9pm–8am ]                                            │
│                                                                     │
│ [Create Profile]  [Create “Aggressive budget” too]  [Skip]           │
└─────────────────────────────────────────────────────────────────────┘
```

Notes:

* Explicitly support commute-based search as a first-class constraint (Zillow has moved this direction with commute/travel-time features). ([Zillow Group][2])
* The “spec preview” is crucial for trust + fast edits when the conversational agent changes something.

---

### 2) Search Home: Split View (Map + List + Chat refinement)

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ Search: [ “2BR under 5.5k near Caltrain, bright + quiet” ]   Profile: Default ▾     │
│ Chips: [<$5.5k] [2BR+] [Dog ok] [<25m to Work @ 8:30a] [In‑unit W/D] [Explore ▾]    │
├───────────────────────────────┬─────────────────────────────────────────────────────┤
│ MAP (left)                    │ RESULTS LIST (right)                                │
│ - anchor pins                 │ Sort: Best match ▾  |  View: Cards ▾                 │
│ - isochrone overlays          │ ┌───────────────────────────────────────────────┐   │
│ - neighborhood boundaries     │ │ #1  123 Market St — Mission Bay                 │   │
│ - optional data layers        │ │ $5,350  • 2bd/2ba • 980 sqft • W/D • Parking     │   │
│   (value, lot size, etc.)     │ │ Commute: 18m transit (8:30a)                     │   │
│                               │ │ Match: ████████░  86                             │   │
│                               │ │ Why: [Bright] [Quiet-ish] [Dog ok] [Near Caltrain]│  │
│                               │ │ Missing: [Deposit?] [Noise exposure?]            │   │
│                               │ │ Actions: [Quick view] [Save] [Compare] [Hide]    │   │
│                               │ └───────────────────────────────────────────────┘   │
│                               │  … cards continue (with “Near misses” shelf)        │
├───────────────────────────────┴─────────────────────────────────────────────────────┤
│ Conversational refine (dock)                                                         │
│  You: “More like #1 but with a balcony and less street noise.”                       │
│  Assistant: “Got it. I’ll require outdoor space; prioritize noise shielding.”        │
│  [Show diff: +balcony/outdoor space, +quiet weight, +rear-facing preference]         │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

Patterns to borrow explicitly:

* **Split view** map+list for fast scanning and geographic reasoning. ([Baymard Institute][1])
* **Conversational search inside results**: Redfin has made the “back-and-forth dialogue while you search” a mainstream expectation; your tool can go further by pairing the chat with an explicit, editable preference spec (so it’s not a black box). ([Redfin][3])
* **Map layers / overlays**: Realtor.com’s “dynamic map layers” show how powerful it is to turn neighborhood-level signals into immediate visual shading that adapts with zoom. ([Media | Move, Inc.][4])

---

### 3) Listing Detail: “Decision cockpit” (drawer/modal)

```text
┌─────────────────────────────────────────────────────────────────────┐
│ [Photos ▸]  123 Market St (Mission Bay)     Source: Zillow / PM site  │
│ $5,350 • 2bd/2ba • 980 sqft • Available Feb 1                         │
│ Confidence: High (3 sources consistent)  |  Last checked: 2 hours ago │
├─────────────────────────────────────────────────────────────────────┤
│ Match Score 86  (tap for breakdown)                                   │
│  Price fit: 28/30  Commute: 25/30  Amenities: 18/20  Vibe: 10/20      │
│  Risk/uncertainty: -5 (missing info)                                  │
│ “Why this matches”                                                    │
│  ✓ <25m transit to Work @ 8:30am                                      │
│  ✓ Dog ok                                                             │
│  ✓ In-unit laundry                                                    │
│  ~ Quiet: likely (rear unit) but noise exposure unknown               │
│ “Near misses / tradeoffs”                                             │
│  If you require balcony: score drops to 70 (not listed)               │
│  If you allow 30m commute: +14 listings in Noe / Glen Park            │
├─────────────────────────────────────────────────────────────────────┤
│ Missing / verify                                                      │
│  - Deposit amount [Ask agent]                                         │
│  - Package room? [Verify via building site]                           │
│  - Street-noise exposure [Run noise proxy] [Ask for unit #]           │
│  - Lease term flexibility [Ask]                                       │
├─────────────────────────────────────────────────────────────────────┤
│ Next actions                                                          │
│ [Save ▾: Visit / Apply / Maybe / No]  [Add note]  [Add to Compare]    │
│ [Open original] [Message/Call script] [Generate tour checklist]       │
└─────────────────────────────────────────────────────────────────────┘
```

Explainability principle: show *why* it’s recommended, what’s uncertain, and what to do next—aligns with modern guidance for “explainable AI” and helps users calibrate trust instead of blindly following a score. ([Nielsen Norman Group][5])

---

### 4) Compare (2–6): “Make tradeoffs explicit”

```text
┌────────────────────────────────────────────────────────────────────────────────┐
│ Compare (4)   [Export PDF] [Share] [Apply mode]                                │
├────────────────────────────────────────────────────────────────────────────────┤
│                     A               B                 C                D       │
│ Price               5,350           5,150             5,600            4,950    │
│ Commute (8:30a)     18m transit     24m transit       12m bike         27m transit│
│ Sunlight            High (west)     Med               High             Unknown (!)│
│ Noise risk          Med             Low               Med              High      │
│ Laundry             In-unit         In-unit           Shared           In-unit   │
│ Parking             $300/mo         Included          None             $250/mo   │
│ Deposit             Unknown (!)     1 mo              1.5 mo           Unknown (!)│
│ Source confidence   High (3 src)    Med (1 src)       High             Low       │
│ Notes               …               …                 …                …         │
├────────────────────────────────────────────────────────────────────────────────┤
│ “What you gain / lose” summary (auto)                                         │
│ - B wins on quiet + included parking                                           │
│ - C wins on commute but fails “in-unit laundry” (dealbreaker?)                 │
│ - D cheapest but high noise + missing deposit                                  │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

### 5) Shortlist workspace: Pipeline + notes + tags

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shortlist   Profile: Default ▾     [Visit plan] [Application pack] [Metrics] │
├─────────────────────────────────────────────────────────────────────────────┤
│ VISIT               APPLY              MAYBE                 NO               │
│ ┌───────────────┐  ┌───────────────┐ ┌───────────────┐   ┌───────────────┐  │
│ │ 123 Market     │  │ 88 King       │ │ 5th & Folsom  │   │ 16th St        │  │
│ │ tour Sat 2pm   │  │ app due Tue   │ │ waiting info  │   │ too noisy      │  │
│ │ tags: bright   │  │ docs: 3/5     │ │ tags: value   │   │ tag: dealbrk   │  │
│ └───────────────┘  └───────────────┘ └───────────────┘   └───────────────┘  │
│                                                                             │
│ Detail pane: notes + questions + contact log + attachments                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 6) Alerts center: “Triage, don’t distract”

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Alerts Center   [Instant] [Daily Digest] [Quiet hours] [Thresholds]           │
├─────────────────────────────────────────────────────────────────────────────┤
│ New matches (7)          Price drops (2)          Status changes (1)          │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ NEW: 2BR in Noe — 92 match   + fits balcony requirement                  │ │
│ │ Why: commute 23m, bright, quieter street; Missing: deposit               │ │
│ │ [Save->Visit] [Hide] [Tune profile] [Open]                               │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ Bundled summary: “3 new in Mission / 2 in Noe / 2 in Dogpatch”              │
└─────────────────────────────────────────────────────────────────────────────┘
```

Frequency controls mirror what users already see in the market (e.g., Redfin offering Instant vs Daily for rental recommendations), but your UX should push toward triage + batching to avoid fatigue. ([Redfin Support][6])

---

## Component spec

### A) Core system components

**1) Preference Spec (the “source of truth”)**

* **Sections:** Budget, Unit basics, Dealbreakers, Strong preferences, Neighborhood constraints, Commute anchors, Building policies, Risk tolerance, Diversity settings, Notification settings.
* **Types:**

  * Hard constraints (“must”)
  * Soft constraints (“prefer”) with weights
  * “Avoid” constraints (negative weights)
* **Visibility:** Always show a compact version (chips) + an expandable structured panel (JSON/YAML/table).
* **Change tracking:** Every conversational refinement produces a *diff* (added/removed constraints, weight changes). This is your anti-hallucination UX.

**2) Split-View Search Layout**

* **Desktop:** sticky filters + list + map (split view). ([Baymard Institute][1])
* **Mobile:** filters in a bottom tray / overlay; don’t force users to bounce between separate full screens for map vs results. ([Nielsen Norman Group][7])
* **Facet design:** treat major dimensions as facets (price, beds, commute, neighborhood, amenities) rather than one-off filters; facets help users understand the space and iterate. ([Nielsen Norman Group][8])

**3) Conversational Refinement Dock**

* Behaviors inspired by emerging real-estate conversational search patterns: back-and-forth while results update. ([Redfin][3])
* Must support:

  * “More like this listing” (uses listing embedding + extracted attributes)
  * “Near misses” (show what failed + how to relax)
  * “Explain ranking differences between A and B”
  * “Add a new anchor, optimize commute”
* Guardrails:

  * Show confirmations as *diff chips* (not a modal).
  * Keep essential info visible—don’t bury critical logic in tooltips; use tips only for non-essential clarification. ([Nielsen Norman Group][9])

---

### B) Result card information architecture (IA)

**Result card zones (top → bottom):**

1. **Identity + freshness**

* Address / neighborhood
* Source badges (Craigslist / Zillow / PM site / Realtor / etc.)
* Dedupe badge (“seen on 3 sources”)
* Freshness (“checked 2h ago”) + “listing age”
* Confidence level (High/Med/Low) based on cross-source agreement + completeness

2. **Key facts (scanline)**

* Price + effective price (incl. parking fees if known)
* Beds/baths + sqft
* Availability date
* Pet policy summary (dog/cat ok)
* 2–3 “hero amenities” (W/D, AC, outdoor space, elevator, parking)

3. **Commute snapshot (if anchors exist)**

* “18m transit to Work @ 8:30am”
* Mode toggle inline (transit/bike/walk/car)
* Reliability hint (e.g., “high variance” if transit uncertain)

Zillow’s commute/travel-time direction is evidence users expect commute as a first-class element, not a hidden detail. ([Zillow Group][2])

4. **Match score + breakdown (progressive disclosure)**

* One primary score (0–100)
* Tap to expand into breakdown bars:

  * Price fit
  * Commute fit
  * Must-have coverage
  * Soft preference fit
  * Risk/uncertainty penalty

5. **“Why it matches” (explanations)**

* 3–5 reason chips max (avoid overwhelming)
* “Because…” statements anchored to your spec:

  * “Meets max commute”
  * “Matches sunlight preference”
  * “Has outdoor space”
* Aligns with explainable AI principles: show the system’s reasoning so the user can calibrate trust. ([Nielsen Norman Group][5])

6. **Missing data + confidence indicators**

* “Missing: deposit, lease term, parking cost”
* Confidence flags:

  * “Field inferred from photos” (lower confidence)
  * “Conflicting sources” (needs verification)
* Provide a “Why missing?” link (source didn’t list it, extraction failed, behind login, etc.)

7. **Next actions**

* Primary: **Save** (with tag dropdown)
* Secondary: **Quick view**, **Compare**, **Hide**
* Tertiary: **Open source**
* Verification action: “Ask agent/PM to verify X” (generates message template + logs the request)

---

### C) Advanced search UX

**1) Conversational edits that modify the structured spec**

* Always show: `Spec state → Proposed changes → Applied`.
* Offer “Lock” controls:

  * Lock a constraint (“never change my budget cap unless I say so”)
  * Lock a weight (“commute is #1 priority”)
* Offer “undo” + “revert to earlier spec snapshot”.

This keeps the agent powerful without making it feel like it’s secretly changing the rules.

**2) Multiple profiles**

* Profiles behave like “saved search personas,” e.g.:

  * Default (balanced)
  * Aggressive budget (lower cap, smaller sqft)
  * Stretch budget (higher cap, must-have outdoor space)
  * “Commute-obsessed” profile
* UI:

  * Profile switcher in header
  * “Diff from Default” view (only what changed)
  * Ability to run A/B: “show me listings that are Top 20 in Stretch but not Top 20 in Default”

**3) Near‑Miss Explorer**

* Input: current spec + top failures
* Output: interactive “tradeoff cards”:

  * “Relax price +$250 → +38 matches”
  * “Relax commute +5 min → +22 matches (adds Noe/Glen Park)”
  * “Allow 1.5 bath → +17 matches”
* Visual:

  * One constraint slider at a time
  * Show “what you gain” (count + example listings + neighborhoods)
  * Show “what you lose” (which must-haves become less common)
* Bonus: “Pareto shelf” = listings that are best across tradeoffs (price vs commute vs amenities)

**4) Diversity preservation**

* Add a **Diversity dial** in the chips row:

  * Strict (optimize score)
  * Balanced
  * Explore (maximize variety across neighborhoods/building types while staying within guardrails)
* Add **Neighborhood sampler** section:

  * “If you’re open to slightly older buildings, you’ll see more of X.”
* Implementation idea: diversify top N with Maximal Marginal Relevance (MMR) or clustering by neighborhood/type, but expose it as a user-controlled dial (not a hidden algo).

NN/g recommends giving users ways to steer recommendations and provide feedback. ([Nielsen Norman Group][10])

---

### D) Map UX spec

**Map layers**

* Base: listings pins with clustering
* Anchors: user pins (Work, Caltrain, etc.)
* Isochrones: show reachable area polygons for time windows (e.g., 15/25/35 min)

  * Implement via Valhalla isochrones (local only).
* Neighborhood overlays:

  * boundaries + “vibe tags” (user-labeled)
  * dynamic shading layers (e.g., median rent, density of matches) inspired by Realtor.com’s dynamic map layer approach. ([Media | Move, Inc.][4])

**Commute filter UX**

* A dedicated “Commute” facet:

  * “< 25 min transit to Work at 8:30am”
  * weekday/weekend
  * mode priorities (transit preferred; bike fallback)
* Interaction:

  * When user adjusts commute time, update isochrone live
  * Show “Listings remaining” count in-line (not after closing modal)

**Map-to-list coupling**

* Hover/focus pin highlights card; card hover highlights pin
* Draw-to-search (lasso) + “save this region” (Zillow supports drawing custom regions + notifications for new listings in region). ([Zillow][12])
* Multi-region search (support up to ~5 polygons / neighborhoods) inspired by Zillow’s multi-location search direction. ([Zillow MediaRoom][13])

---

### E) Notification strategy (signal > spam)

**Principles**

* Notifications should be relevant + timely + tied to user goals; otherwise they become noise. Carbon’s pattern guidance emphasizes relevance and timeliness. ([Carbon Design System][14])
* Use the right communication method: indicators vs notifications vs validations (don’t “notify” for things that should just be an in-app badge). ([Nielsen Norman Group][15])

**Types**

1. **New matches** (net-new listings that meet constraints)
2. **Near matches** (fail 1 constraint but high potential)
3. **Price drops / status changes / open house** (for saved listings)

   * Zillow explicitly notifies saved-home updates like price adjustments, status changes, open houses. ([Zillow Help Center][16])
4. **Verification needed** (high-score listing missing critical fields)

**Control knobs**

* Frequency: Instant vs Daily Digest (match market expectations like Redfin’s instant/daily rental alerts). ([Redfin Support][6])
* Quiet hours + timezone aware batching
* Thresholds:

  * Only notify if score ≥ X
  * Or if “delta” is meaningful (e.g., price drop > $Y or >Z%)

**Anti-spam mechanics**

* Bundle by neighborhood/time window
* Rate limit (max N notifications/day)
* “Snooze this category for 7 days”
* Every notification has a **one-tap action**: Save/Hide/Tune profile

---

## MVP vs ultimate

### MVP (4–6 weeks of build scope, but “works like magic”)

**Core UX**

* Onboarding with:

  * Natural-language intake
  * 1–2 anchors + commute time constraint
  * Default profile creation
* Split-view Search (desktop) + mobile filter tray
* Result cards with:

  * Key facts
  * 3 reasons + 3 missing fields
  * Save/Hide/Compare
* Listing detail drawer
* Compare (up to 4)
* Shortlist pipeline (Visit/Apply/Maybe/No) + notes
* Alerts:

  * Daily digest email + optional instant for “perfect” matches

**Tech approach (recommended for MVP)**

* **Web app (Next.js/React) + responsive**: fastest iteration, easy sharing, works across devices; maps + split view are strongest on desktop.
* **Map**: MapLibre GL JS + local tiles + Valhalla isochrones.
* **Data**: normalize listing schema + dedupe; store geo in PostGIS; index with pgvector for “more like this”.
* **Commute**: start with Valhalla isochrones; use OTP for time-dependent transit routing.
* **Explainability**: rule-based “reason chips” from structured extraction + model output; show diff whenever spec changes (trust anchor).

### Ultimate (the “this is unfair” apartment hunter)

**Discovery + iteration**

* Multi-profile manager with A/B compare results
* Near‑Miss Explorer with Pareto sets + “what you gain/lose” narratives
* “Style / look-and-feel” similarity search (inspired by Realtor.com’s AI “look-and-feel” concept). ([realtor.com Tech Blog][17])
* Learning loop:

  * thumbs up/down per listing attribute (“more sunlight than this”, “less street-facing”)
  * taste embeddings (photos + description + neighborhood)

**Map intelligence**

* Time-dependent transit routing (8:30am, weekday vs weekend)
* Multiple anchors combined (optimize commute to 2 locations)
* Neighborhood insight layers (your own + external datasets)
* “Visit plan mode”: cluster shortlist by neighborhood + route plan

**Decision automation**

* “Verification agent” workflow:

  * detects missing critical info
  * drafts messages/call scripts
  * tracks responses
* “Application pack mode”:

  * checklist + deadlines + document vault
  * one-click export summary to share with roommates/partner

**Notifications that feel like a concierge**

* Local notifications or SMTP email
* “Explain what changed” notifications
* Smart bundling:

  * “2 perfect matches in Noe; 1 near-miss in Mission (fails parking)”
* Alert fatigue defenses (strict caps, snoozes, and only high-signal notifications)

---

If you want, I can also provide:

* A **structured preference spec schema** (JSON) that your chat agent edits, plus the exact diff format to show users.
* A **component inventory** in “design system” terms (atoms/molecules/organisms) to hand to engineering.

[1]: https://baymard.com/blog/accommodations-split-view?utm_source=chatgpt.com "The Optimal Layout for Hotel & Property Rental Search ..."
[2]: https://www.zillowgroup.com/news/zillows-commute-time-filter/?utm_source=chatgpt.com "Discover your perfect commute with Zillow's commute time ..."
[3]: https://www.redfin.com/blog/redfin-conversational-search/?utm_source=chatgpt.com "Redfin Conversational Search: Master Your Home Search"
[4]: https://mediaroom.realtor.com/2024-09-24-Wheres-the-Best-Deal-on-the-Block-Realtor-com-R-Launches-Dynamic-Map-Layers-to-Help-Homebuyers-Find-It-and-So-Much-More?utm_source=chatgpt.com "Where's the Best Deal on the Block? Realtor.com® Launches ..."
[5]: https://www.nngroup.com/articles/explainable-ai/?utm_source=chatgpt.com "Explainable AI in Chat Interfaces"
[6]: https://support.redfin.com/hc/en-us/articles/360001454951-Notification-Settings?utm_source=chatgpt.com "Notification Settings"
[7]: https://www.nngroup.com/articles/mobile-faceted-search/?utm_source=chatgpt.com "Mobile Faceted Search with a Tray : New and Improved ..."
[8]: https://www.nngroup.com/articles/filters-vs-facets/?utm_source=chatgpt.com "Filters vs. Facets: Definitions"
[9]: https://www.nngroup.com/articles/info-tips-bad/?utm_source=chatgpt.com "Why So Many Info Tips Are Bad (and How to Make Them ..."
[10]: https://www.nngroup.com/articles/recommendation-guidelines/?utm_source=chatgpt.com "UX Guidelines for Recommended Content"
[11]: https://docs.mapbox.com/api/navigation/isochrone/?utm_source=chatgpt.com "Isochrone API | API Docs"
[12]: https://www.zillow.com/learn/zillow-advanced-search/?utm_source=chatgpt.com "How to Use Zillow to Find a Home You'll Love"
[13]: https://zillow.mediaroom.com/2022-07-21-Zillows-new-tool-powers-home-searches-in-up-to-five-areas-at-once%2C-letting-shoppers-move-as-fast-as-the-market?utm_source=chatgpt.com "Zillow's new tool powers home searches in up to five areas at ..."
[14]: https://carbondesignsystem.com/patterns/notification-pattern/?utm_source=chatgpt.com "Notifications"
[15]: https://www.nngroup.com/articles/indicators-validations-notifications/?utm_source=chatgpt.com "Indicators, Validations, and Notifications: Pick the Correct ..."
[16]: https://zillow.zendesk.com/hc/en-us/articles/213395508-Saved-Searches-and-Saved-Homes?utm_source=chatgpt.com "Saved Searches and Saved Homes"
[17]: https://techblog.realtor.com/artificial-intelligence-models-let-home-buyers-find-properties-that-share-the-same-look-and-feel-an-industry-first-new-feature/?utm_source=chatgpt.com "Artificial Intelligence models let home buyers find ..."
