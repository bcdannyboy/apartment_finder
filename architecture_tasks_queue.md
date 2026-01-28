# Task and Queue Schema (Authoritative)

## Task types
- SearchTask
- MapTask
- CrawlTask
- ScrapeTask
- ImportTask

## Task schema
```
{
  "task_id": "uuid",
  "task_type": "SearchTask" | "MapTask" | "CrawlTask" | "ScrapeTask" | "ImportTask",
  "source_id": "uuid",
  "policy_id": "uuid",
  "domain": "string",
  "payload": { },
  "status": "queued" | "running" | "succeeded" | "failed" | "denied",
  "attempt": 0,
  "max_attempts": 0,
  "scheduled_at": "timestamp",
  "created_at": "timestamp"
}
```

## Queue rules
- Policy Gate is checked before enqueue and before execution.
- Per-domain rate limits and politeness must be enforced.
- manual_only sources allow ImportTask only.
- Unknown or partner_required sources deny automation.
- Audit logging is required for every attempt.

## Determinism
- Task derivation is deterministic for identical inputs and seed.
- Task IDs are stable for identical inputs.
