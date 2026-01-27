# Acquisition and Compliance Plan (v1)

## Compliance Rules (hard constraints)

1) Policy gate is mandatory
- Every acquisition task must pass a policy gate check.
- Only sources marked crawl_allowed can be automated.
- partner_required and unknown are blocked until licensing or review is completed.
- manual_only allows ImportTask only (user-provided URL/file); no automated discovery, crawling, or URL expansion.

2) Prohibited automation
- No login automation, CAPTCHA bypass, or paywall circumvention.
- No stealth proxy mode unless explicitly approved (default is proxy: "basic").
- No automated enumeration on restricted portals (Craigslist, Zillow/HotPads/Trulia, Realtor.com, Apartments.com, PadMapper, Zumper, Facebook Marketplace). These are manual_only unless licensed.
- MLS/IDX/RESO and PMS/ILS access is partner_required by default due to licensing and authorization requirements.

3) Robots and Terms of Service
- Fetch and store robots.txt before onboarding a domain.
- Record ToS URL and a short compliance summary.
- If robots or ToS disallow crawling, classify as manual_only or partner_required and block automation.

4) Firecrawl policy constraints (must comply)
- Lawful use only; do not scrape sensitive personal data without consent.
- Respect robots.txt and site terms.
- Verify Firecrawl webhook signatures (X-Firecrawl-Signature) for crawl/extract callbacks.
- changeTracking comparisons are derived from markdown output and require re-scraping the same URL.

5) Provenance and audit
- Every fetch logs source_id, policy_id, timestamps, HTTP status, response headers, and Firecrawl parameters.
- Each snapshot is immutable and linked to a policy version.

6) Manual-only handling
- Accept only user-provided artifacts (URL/file/email export).
- Store as a DocumentSnapshot and extract only that artifact.
- Do not follow links or enumerate related pages.

## Source Registry Schema + Policy Gate API

### Source registry schema (minimum)

Table: sources
- source_id (UUID)
- name
- kind (pm_site, broker_site, marketplace, licensed_feed, user_import)
- base_domains (array)
- default_policy_id (FK)
- status (active, paused)
- created_at, updated_at

Table: source_policies (versioned)
- policy_id (UUID)
- source_id (FK)
- policy_status (crawl_allowed, partner_required, manual_only, unknown)
- allowed_operations (search, map, crawl, scrape, extract, manual)
- robots_url
- robots_snapshot_ref
- robots_fetched_at
- tos_url
- tos_summary
- compliance_notes
- rate_limits (qps, concurrency)
- crawl_limits (max_pages, max_depth, include_paths, exclude_paths)
- default_cadence (index_hours, detail_hours)
- budget (credits_per_day, max_tasks_per_day)
- reviewed_by
- reviewed_at
- policy_version
- policy_hash

Table: source_budgets (optional)
- source_id
- daily_credits_limit
- daily_request_limit
- burst_qps
- concurrency
- backoff_policy_id

### Policy gate API (service + function signatures)

Endpoint: POST /policy/check
Input:
- source_id
- url
- operation (search, map, crawl, scrape, extract, manual)
- task_type
Output:
- decision: allow | deny | require_manual | require_partner | require_review
- policy_id
- reason
- enforced_limits (qps, concurrency, max_pages, include/exclude paths)

Function: policy_gate.check(source_id, url, operation, task_type)
- Hard block if policy_status != crawl_allowed and operation in {map, crawl, scrape, extract}.
- Allow manual import only when policy_status == manual_only.
- Attach policy_id + enforced limits to the task record.

## Task Types + Scheduler Strategy

### Task types (with required metadata)

1) SearchTask
- Purpose: discover candidate domains and seed URLs.
- Required: query, location, language, time_window, limit, discovery_sweep_id.
- Output: candidate_domains, candidate_urls (untrusted until policy check).

2) MapTask
- Purpose: enumerate URLs on a known crawl_allowed domain.
- Required: source_id, url, limit, search_term (optional), include/exclude paths.

3) CrawlTask
- Purpose: scoped crawl on a known crawl_allowed domain.
- Required: source_id, start_url, limit, max_depth, include/exclude paths, scrape_options.

4) ScrapeTask
- Purpose: refresh a single listing or detail page.
- Required: source_id, url, formats, change_tracking, maxAge.

5) ExtractTask (optional when using Firecrawl extract)
- Purpose: structured extraction over a list of URLs or a crawl result.
- Required: source_id, url_list, json_schema.

6) ImportTask
- Purpose: manual-only ingestion for restricted portals.
- Required: user_artifact_ref (URL/file/email), source_id (manual_only).

Common task metadata (all tasks)
- task_id
- source_id
- policy_id
- priority_score
- queue_lane (index | detail | import)
- scheduled_at
- discovery_context (query, sweep cell: neighborhood/price/bed)
- rate_limits (qps, concurrency)
- retry_count, last_error, backoff_until
- budget_credits_remaining

### Scheduler strategy

Core heuristics
- Two-lane queues: index (Search/Map) and detail (Crawl/Scrape/Extract).
- Per-domain buckets enforce politeness (qps + concurrency caps).
- Priority formula (initial):
  score = w_source * source_velocity
        + w_change * estimated_change_prob
        + w_interest * user_interest
        - w_age * page_age
        - w_fail * error_penalty
- Discovery sweeps: scheduled neighborhood x price x beds grids; query expansion for aliases and availability keywords.

Cadence and TTL
- High-churn PM sites: TTL 48-72 hours unless re-seen.
- Static broker pages: TTL 7-14 days.
- Manual-only sources: TTL only when user refreshes.

Backoff and errors
- Exponential backoff on 429/503 and repeated failures.
- Deprioritize sources with persistent errors.
- Jitter schedules to avoid spikes.

Change detection integration
- Use Firecrawl changeTracking when available and markdown is included.
- Maintain local content hashes and field-level hashes to skip redundant extraction.

## Firecrawl Adapter Standards

### Global guardrails
- Every Firecrawl call must include policy_id and pass policy gate checks.
- Avoid stealth proxy unless explicitly approved.
- Prefer caching with maxAge (default cache is 2 days / 172,800 ms); set maxAge=0 only when freshness is critical.
- Disable PDF parsing by default (parsers: []) to avoid per-page PDF charges unless needed.

### Search usage profile
- Use /search to discover candidate domains and seed URLs.
- Do not scrape search results unless each result domain is crawl_allowed.
- Use limit, location, language, and time windows to control cost (2 credits per 10 results, +1 credit per scraped page).
- Store search query, parameters, and result URLs for audit.

### Map usage profile
- Use /map for crawl_allowed domains only.
- Apply limit and optional search_term to narrow to listing or availability pages.
- Treat map output as a fast-but-not-exhaustive URL set.

### Crawl usage profile
- Use /crawl only for crawl_allowed domains.
- Always set limit, includePaths, excludePaths, and maxDiscoveryDepth.
- Prefer start_crawl + status polling for large jobs.
- Scrape options: formats (markdown + html + links), proxy "basic", maxAge as policy dictates.

### Scrape usage profile
- Use /scrape for single-page refresh.
- Standard formats: markdown + html + links; screenshot optional when evidence is needed.
- changeTracking requires markdown and the same URL; use git-diff by default.
- Use JSON diff mode only when stable schema justifies extra credits (JSON diff adds 5 credits per page).

### Extract usage profile
- Use /extract to produce structured JSON from a list of URLs (policy-gated).
- Provide a JSON schema; avoid wildcard domains unless domain is crawl_allowed.
- Note: extract and scrape consume credits per page; JSON mode and stealth add costs.

### Rate limits and concurrency
- Respect plan-based limits (requests per minute and concurrent browsers).
- Enforce per-domain limits lower than plan limits for politeness.
- Plan guardrails from the Jan 27, 2026 Firecrawl limits report (examples):
  - Free: 2 concurrent, /scrape+map 10 rpm, /crawl 1 rpm, /search 5 rpm, /agent 10 rpm
  - Hobby: 5 concurrent, /scrape+map 100 rpm, /crawl 15 rpm, /search 50 rpm, /agent 100 rpm
  - Standard: 50 concurrent, /scrape+map 500 rpm, /crawl 50 rpm, /search 250 rpm, /agent 500 rpm
  - Growth: 100 concurrent, /scrape+map 5000 rpm, /crawl 250 rpm, /search 2500 rpm, /agent 1000 rpm

## Priority Source Plan (explicit in-scope vs out-of-scope)

### In-scope (automated, crawl_allowed only)
1) Long-tail property manager and building sites with permissive robots/ToS.
2) Broker or agent sites that explicitly allow crawling.
3) Public housing/affordable housing portals only when ToS permits automation (otherwise manual import).
4) University/medical housing boards if public and crawl_allowed.

### In-scope (manual-only)
- Craigslist
- Zillow / HotPads / Trulia
- Realtor.com
- Apartments.com (CoStar)
- PadMapper
- Zumper
- Facebook Marketplace

Manual-only means: user-provided URL/file only, no automated discovery or crawling.

### Out-of-scope unless licensing changes (partner_required)
- MLS/IDX/RESO feeds (require MLS/vendor licensing, facilitating-MLS authorization in the NorCal MLS Alliance, and compliance with IDX display rules).
- PMS/ILS vacancy feeds (Yardi, RealPage, Entrata, AppFolio, etc.) which require vendor programs (e.g., Yardi Data Exchange, RealPage LeaseStar, Entrata ILS Portal), mutual client authorization, MITS 5.0 or vendor JSON formats, and contractual confidentiality/rate limits.
- CoStar, Yardi Matrix, RealPage ecosystem data products.

These sources are excluded because only Firecrawl and OpenAI are allowed paid services.

## Conflicts with constraints (if any)

1) High-velocity portal crawling (e.g., Craigslist, Zillow, Facebook Marketplace) is mentioned in some acquisition strategies but is not compliant here. These must remain manual-only unless licensing is obtained.
2) MLS/IDX/RESO and PMS/ILS feeds provide high coverage but require paid licensing and authorization, which conflicts with the "only Firecrawl + OpenAI paid" constraint.
3) Firecrawl Search may surface restricted portals; policy gate must block automation and route to manual-only flow.
