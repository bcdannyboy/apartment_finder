# Compliance and Network Enforcement (Authoritative)

## Policy Gate enforcement
- Policy Gate must evaluate every task before enqueue and before execution.
- policy_status = crawl_allowed is required for any automated task.
- manual_only sources allow ImportTask only.
- partner_required and unknown sources deny automation until reviewed.

## Restricted portals
- Restricted portals are manual-only unless licensed.
- No login automation, CAPTCHA bypass, or paywall circumvention.

## Network egress enforcement
- Outbound network allowlist includes Firecrawl and OpenAI endpoints only.
- All other outbound HTTP requests are blocked.
- Enforcement is required at runtime (client allowlist) and at host or container network policy.

## Local-only binding
- Services must bind to localhost or local container network addresses.
- Any attempt to bind to non-local addresses is rejected.
