# API Contracts (Authoritative)

## Purpose
Defines request and response schemas for core service contracts.

## Common response envelope
```
{
  "schema_version": "v1",
  "status": "ok" | "error",
  "data": { }
}
```

## Error schema
```
{
  "schema_version": "v1",
  "status": "error",
  "error": {
    "code": "STRING_CODE",
    "message": "Human readable message",
    "details": { }
  }
}
```

## Idempotency and versioning
- schema_version must be v1 for all requests and responses.
- Policy Gate evaluation is deterministic for identical inputs.
- Snapshot creation is idempotent at the content_hash level but always yields a new snapshot_id for each fetch.
- Alert dispatch uses an idempotency key derived from (alert_id, channel).
- Ranking responses are deterministic for fixed inputs and seeds.

## Policy Gate API

### Evaluate policy
Request
```
POST /policy/evaluate
{
  "schema_version": "v1",
  "source_id": "uuid",
  "domain": "example.com",
  "task_type": "CrawlTask",
  "requested_operation": "automated_fetch"
}
```
Response
```
{
  "schema_version": "v1",
  "status": "ok",
  "data": {
    "decision": "crawl_allowed" | "manual_only" | "partner_required" | "unknown",
    "allowed_operations": ["ImportTask", "CrawlTask"],
    "reason": "string",
    "policy_id": "uuid"
  }
}
```

## Snapshot Store API

### Create snapshot
Request
```
POST /snapshots
{
  "schema_version": "v1",
  "source_id": "uuid",
  "url": "string",
  "fetched_at": "timestamp",
  "http_status": 200,
  "formats": { "html": true, "markdown": true, "screenshot": false },
  "storage_refs": { "html": "path", "markdown": "path" },
  "content_hash": "string",
  "change_tracking": { }
}
```
Response
```
{
  "schema_version": "v1",
  "status": "ok",
  "data": { "snapshot_id": "uuid", "content_hash": "string" }
}
```

### Fetch snapshot
Request
```
GET /snapshots/{snapshot_id}
```
Response
```
{
  "schema_version": "v1",
  "status": "ok",
  "data": { "snapshot_id": "uuid", "url": "string", "content_hash": "string", "formats": { }, "storage_refs": { } }
}
```

## Ranking API

### Rank listings
Request
```
POST /rank
{
  "schema_version": "v1",
  "search_spec_id": "uuid",
  "options": { "limit": 50 }
}
```
Response
```
{
  "schema_version": "v1",
  "status": "ok",
  "data": {
    "results": [
      {
        "listing_id": "uuid",
        "rank": 1,
        "scores": { "utility": 0.8, "confidence": 0.9, "final": 0.85 },
        "explanation": { "why": ["string"], "tradeoffs": ["string"], "verify": ["string"] }
      }
    ]
  }
}
```

## Alert API

### Run alert matching
Request
```
POST /alerts/run
{
  "schema_version": "v1",
  "search_spec_id": "uuid",
  "since": "timestamp"
}
```
Response
```
{
  "schema_version": "v1",
  "status": "ok",
  "data": { "alerts_created": 10 }
}
```

### Dispatch alerts
Request
```
POST /alerts/dispatch
{
  "schema_version": "v1",
  "alert_ids": ["uuid"],
  "channel": "local" | "smtp"
}
```
Response
```
{
  "schema_version": "v1",
  "status": "ok",
  "data": { "dispatched": 10 }
}
```
