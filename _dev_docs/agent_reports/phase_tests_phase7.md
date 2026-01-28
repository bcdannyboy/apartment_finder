# Phase 7 Alert Service Test Plan

## References
- architecture_api_contracts.md
- architecture_decisions_and_naming.md


## Scope and constraints
- Alert Service consumes ListingChange records and SearchSpec profiles and emits notifications plus dispatch logs.
- Allowed channels: local notifications and SMTP only. No paid messaging or third-party push/SMS/chat.
- Matching must align with ranking hard constraints; alerts must never violate those constraints.
- Dispatch logs are append-only and immutable.

## Test data and fixtures
- Synthetic listings with full and missing fields, boundary values for hard constraints, and conflicting attributes.
- ListingChange fixtures for create/update/remove transitions with stable IDs and payload hashes.
- SearchSpec fixtures that cover strict, loose, and conflicting constraints.
- Local notification stub and SMTP test server with controllable failure modes.

## Matching logic vs ranking hard constraints
- Unit: Hard-constraint evaluation matches ranking spec for each field (price, location, beds, baths, pets, fees, commute, and other must-have filters defined in the ranking spec).
- Unit: Any listing that fails a hard constraint is excluded from alert matching even if other signals are strong.
- Unit: Constraint normalization parity (units, ranges, boolean flags) matches ranking pipeline results.
- Integration: For a fixed SearchSpec and listing set, alert matches are identical to ranking output filtered by hard constraints.
- Negative: Missing required fields or invalid values fail the match and are logged with a clear reason.

## ListingChange triggers and idempotency
- Unit: Each ListingChange emits at most one dispatch per SearchSpec and channel using a deterministic idempotency key.
- Integration: Re-running the alert job with the same ListingChange set produces no duplicate dispatches.
- Integration: When multiple ListingChange records exist for one listing, only the correct changes trigger alerts per spec rules.
- Failure path: Partial send failures do not create duplicate alerts on retry; retries reuse the same idempotency key.
- Negative: Unsupported or malformed ListingChange records are skipped with a logged reason and no dispatch.

## Dispatch logging correctness and immutability
- Schema: Log entries include dispatch_id, listing_change_id, search_spec_id, channel, payload_hash, status, attempt, and error details when present.
- Ordering: A log entry is written before send attempt; retries append new entries without mutating prior records.
- Integrity: Payload hashes and ids are stable across retries; logs are tamper-evident by design (append-only store).
- Coverage: Log entries exist for success, retry, and terminal failure cases.
- Negative: Any attempt to update or delete log entries is rejected at the storage layer.

## Local notification and SMTP-only enforcement
- Unit: Channel validation allows only "local" and "smtp"; all others are rejected before dispatch.
- Integration: Configuration prevents use of paid messaging providers; no outbound calls to SMS, push, or chat APIs.
- Integration: Local notifications route through the OS notification adapter; SMTP sends via configured server only.
- Negative: Missing SMTP configuration or unsupported local notification capability yields a logged, non-fatal failure.

## Error handling and retry rules
- Unit: Transient SMTP errors trigger bounded retries with backoff and do not exceed max attempts.
- Unit: Permanent SMTP errors are not retried and are recorded as terminal failures.
- Unit: Local notification errors are classified as retryable or terminal based on adapter error codes.
- Integration: Retry budget is enforced per dispatch; global failures do not block other dispatches.
- Negative: Alert job completes with partial failures and emits summary metrics without crashing.

## Non-functional and safety tests
- Load: Dispatch throughput remains within resource limits while preserving ordering and idempotency.
- Concurrency: Parallel runs do not duplicate alerts or corrupt logs.
- Security: Logs contain no secrets; SMTP credentials are never logged.
- Recovery: Process restarts do not lose idempotency guarantees; pending retries resume safely.

## Exit criteria
- All tests pass for unit, integration, and end-to-end alert flows.
- No duplicates across repeated runs on identical ListingChange inputs.
- Dispatch logs are complete, immutable, and auditable.
- Only local notifications and SMTP are used for alerts.
