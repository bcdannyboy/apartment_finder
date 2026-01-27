# UI/Deployment/Security Architect Report

## UX Flows + Core Screens

### Core flow (happy path)
1) Onboarding -> capture NL criteria, structured SearchSpec preview, commute anchors, alert prefs.
2) Search Home -> split map/list with chat refinement; filters + chips show hard/soft rules.
3) Listing detail -> why it matches, what is missing, evidence snippets/photos, change history.
4) Compare -> side-by-side structured fields for 2-6 listings.
5) Shortlist pipeline -> New -> Considering -> Shortlisted -> Contacted -> Tour scheduled -> Applied -> Won/Lost.
6) Alerts Center -> triage queue for new matches and changes, quick actions.

### Screens (minimum set)
- Onboarding (criteria + anchors + alert prefs)
- Search Home (split map/list + chat refinement)
- Listing Detail (drawer/modal) with evidence and change history
- Compare (2-6 listings)
- Shortlist Workspace (pipeline + notes/tags)
- Near-Miss Explorer (relax one constraint, show tradeoffs)
- Profiles/Specs (manage multiple SearchSpecs)
- Alerts Center (triage queue + settings)

### Interaction principles (from source docs)
- Always show why a listing matches and what is missing to verify.
- Near-miss explicitly exposes tradeoffs (count gained, which rules relaxed).
- Diversity dial controls strict vs explore behavior.
- Alerts are profile-based: new matches, price drops, availability changes, listing removed.
- Delivery: instant vs daily digest, with quiet hours.

## API Surface (endpoints + payloads)

### Core resources (high level contracts)
- SearchSpec: hard/soft constraints, exploration settings, commute limits.
- Listing: building + unit + listing facts with confidence/evidence refs.
- Match: scores + explanation (why/tradeoffs/verify).
- AlertSubscription: profile-based rules + delivery settings.
- AlertEvent: new match or listing change with quick actions.

### Endpoints (FastAPI, local-only)

1) Search specs and query
- POST /api/search-specs
  - request: { raw_prompt?, hard?, soft?, exploration?, commute_targets? }
  - response: SearchSpec
- GET /api/search-specs/{spec_id}
  - response: SearchSpec
- POST /api/search
  - request: { spec_id? , spec? , page?, page_size?, sort? }
  - response: { results: ListingSummary[], matches: Match[], map: MapOverlay, total }

2) Listings
- GET /api/listings/{listing_id}
  - response: ListingDetail
- POST /api/listings/compare
  - request: { listing_ids: UUID[] }
  - response: { field_matrix: CompareField[], listings: ListingSummary[] }

3) Near-miss / exploration
- POST /api/near-miss
  - request: { spec_id, relax_rule?, exploration_override? }
  - response: { delta_count, relaxed_rule, new_results: ListingSummary[], tradeoffs }

4) Shortlist pipeline + notes
- GET /api/shortlist
  - response: { items: PipelineItem[] }
- POST /api/shortlist
  - request: { listing_id, stage, notes?, tags? }
  - response: PipelineItem
- PATCH /api/shortlist/{item_id}
  - request: { stage?, notes?, tags? }
  - response: PipelineItem

5) Alerts
- GET /api/alerts/subscriptions
- POST /api/alerts/subscriptions
  - request: { spec_id, channels, frequency, quiet_hours? }
  - response: AlertSubscription
- GET /api/alerts/events
  - response: { events: AlertEvent[] }
- POST /api/alerts/events/{event_id}/action
  - request: { action: "save"|"hide"|"more_like_this"|"explain_change" }

6) Commute overlays
- POST /api/commute/isochrone
  - request: { targets[], mode, depart_time, max_min }
  - response: { polygons[], provider }
- POST /api/commute/matrix
  - request: { listing_ids[], targets[], mode, depart_time }
  - response: { results: CommuteResult[] }

### Payload sketches (condensed)
- ListingSummary: { listing_id, price_monthly, beds, baths, neighborhood, status, score, why[] }
- ListingDetail: { listing, building, unit, evidence[], change_history[] }
- EvidenceRef: { snapshot_id, kind, locator, excerpt? }
- Match: { listing_id, scores, explanation: { why[], tradeoffs[], verify[] } }
- MapOverlay: { pins[], clusters?, neighborhood_bounds?, isochrones? }

## Local Deployment Architecture

### Docker components
- ui: web app (Next.js/React) serving map/list, compare, alerts
- api: FastAPI (search, listings, compare, alerts)
- worker: background tasks (ranking, change processing, alert fanout)
- scheduler: APScheduler or cron-like service for ingest/recrawl/alerts
- db: Postgres + PostGIS (source of truth)
- vector: pgvector extension in same Postgres
- redis: queues + short-lived cache
- object_store: local filesystem or MinIO for snapshots/images
- routing: OpenTripPlanner OR Valhalla/OSRM for commute overlays

### Storage layout
- Postgres stores canonical tables (sources, listings, search_specs, matches, alerts).
- Object store holds HTML/markdown/screenshots/images for evidence.
- Redis holds queues and recent search caches.

### Local compose notes
- Bind all service ports to 127.0.0.1 only.
- Use named volumes for db and object_store data.
- Route data volumes for OSM/GTFS and routing graph caches.
- .env for secrets and API keys (Mapbox, SMS/email if enabled).

## Security/Privacy Requirements

- Local-only: API bound to localhost; no public listener by default.
- CORS restricted to local UI origin.
- Secrets in env files; keys kept separate from data volumes.
- Minimize PII in logs; redact sensitive fields where possible.
- Optional encrypted backups; provide delete-all-data command.
- Compliance gating: sources marked as crawl_allowed, partner_required, or manual_only.
- No external telemetry without explicit user opt-in.

## Conflicts / Open Questions

- Routing engine choice (OpenTripPlanner vs Valhalla vs OSRM) for commute overlays.
- Map provider and caching rules (Mapbox-first vs Google fallback).
- Object store strategy: local filesystem vs MinIO.
- Alert delivery: local notifications only vs email/SMS (Twilio) opt-in.
- Multi-profile support in MVP vs single SearchSpec.
- Near-miss rules: which constraints are relaxable and how to explain tradeoffs.
- Evidence UX: how much snippet/image evidence to show on listing detail.
