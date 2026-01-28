# Phase 2 Test Plan - Acquisition Pipeline

## References
- architecture_decisions_and_naming.md
- architecture_tasks_queue.md
- architecture_api_contracts.md
- architecture_compliance_enforcement.md


## Scope
- Focus: acquisition pipeline from task creation through snapshot persistence and audit logging.
- Components: Source Registry and Policy Gate, Acquisition Orchestrator, Scheduler/Queue/Workers, Firecrawl Adapter, Snapshot Store, Audit Logging.
- Out of scope: extraction, normalization, dedupe, ranking, alerts.

## Hard constraints (same as Phase 1)
- Automation runs only when policy_status is crawl_allowed.
- Manual-only sources allow ImportTask only; all automated tasks are blocked.
- Policy Gate check is required before enqueue and again before execution.
- Per-domain rate limits and politeness rules are always enforced.
- Firecrawl Adapter enforces allowed formats and changeTracking on all requests.
- Snapshot metadata must include content_hash; if missing, a fallback hash is computed and stored.
- Audit logs are required for every task attempt with policy_id, params, and outcome.
- Task scheduling is deterministic given identical inputs and seed.

## Evidence model (same as Phase 1)
- Each test must capture inputs, outputs, and logs as evidence artifacts.
- Required evidence artifacts:
  - Task spec and schema validation report.
  - Policy record snapshot used by the Policy Gate.
  - Queue payloads and task state transitions.
  - Worker execution log and adapter request metadata (redacted where needed).
  - Snapshot metadata record (including content_hash and change_tracking fields).
  - Audit log record with policy_id, params, outcome, attempt, and error_class when applicable.
- Evidence must be linked by stable test id and remain consistent across artifacts.
- A test passes only when all required evidence is present and consistent.

## Test cases

### T2-VAL Task schema and queue payload validation
| ID | Scenario | Assertions | Evidence |
| --- | --- | --- | --- |
| T2-VAL-001 | Missing required field in task schema | Validation fails; task is not enqueued; error is recorded | Schema validation report; queue state showing no enqueue; audit log for rejection |
| T2-VAL-002 | Invalid task_type value | Validation fails with clear error; no worker execution | Schema validation report; worker log shows no execution; audit log for rejection |
| T2-VAL-003 | Queue payload missing policy_id or domain | Payload validation fails; task is rejected before enqueue | Queue payload validation report; audit log for rejection |
| T2-VAL-004 | Payload contains unsupported format field | Payload rejected; no adapter call | Queue payload validation report; adapter log shows no call |

### T2-POL Policy Gate checks before task execution
| ID | Scenario | Assertions | Evidence |
| --- | --- | --- | --- |
| T2-POL-001 | crawl_allowed source with CrawlTask | Policy Gate allows enqueue and execution | Policy decision record; queue payload; worker log |
| T2-POL-002 | manual_only source with CrawlTask | Policy Gate blocks before enqueue; no execution | Policy decision record; queue state; audit log with denial |
| T2-POL-003 | unknown or partner_required source | Policy Gate blocks all automation tasks | Policy decision record; audit log with denial reason |
| T2-POL-004 | Policy changes between enqueue and execution | Execution is blocked if policy is no longer allowed | Pre-exec policy decision record; worker log shows abort; audit log outcome |

### T2-RATE Per-domain rate limits and politeness
| ID | Scenario | Assertions | Evidence |
| --- | --- | --- | --- |
| T2-RATE-001 | Concurrency cap per domain | Active workers never exceed domain cap | Worker metrics; scheduler log; task timeline |
| T2-RATE-002 | Minimum delay between requests | Inter-request gap meets or exceeds configured delay | Worker log timestamps; scheduler delay decisions |
| T2-RATE-003 | Error backoff applies per domain | Backoff increases after errors; no burst on recovery | Scheduler log; queue schedule updates; worker log |
| T2-RATE-004 | Per-domain budget enforcement | Total requests per window do not exceed budget | Scheduler summary; queue counts; audit log totals |

### T2-FC Firecrawl Adapter format rules
| ID | Scenario | Assertions | Evidence |
| --- | --- | --- | --- |
| T2-FC-001 | changeTracking omitted in request | Adapter rejects request before API call | Adapter validation log; audit log for rejection |
| T2-FC-002 | Unsupported format requested | Adapter rejects request; no API call | Adapter validation log; audit log for rejection |
| T2-FC-003 | Upstream response missing content_hash | Fallback content_hash computed and stored | Snapshot metadata; adapter log showing fallback |
| T2-FC-004 | changeTracking required for snapshots | change_tracking metadata stored for each snapshot | Snapshot metadata; adapter request log |

### T2-MAN Manual-only sources reject automation
| ID | Scenario | Assertions | Evidence |
| --- | --- | --- | --- |
| T2-MAN-001 | manual_only source with SearchTask/MapTask/CrawlTask/ScrapeTask | Policy Gate blocks all automated tasks | Policy decision record; queue state; audit log |
| T2-MAN-002 | manual_only source with ImportTask | ImportTask allowed and processed | Policy decision record; queue payload; worker log |
| T2-MAN-003 | Retry after policy flips to manual_only | Subsequent attempts blocked; no automation resumes | Policy history; pre-exec decision log; audit log |

### T2-AUD Audit logging completeness
| ID | Scenario | Assertions | Evidence |
| --- | --- | --- | --- |
| T2-AUD-001 | Successful task execution | Audit log includes policy_id, params, outcome, task_id, source_id, domain, attempt | Audit log record; task record |
| T2-AUD-002 | Denied task | Audit log includes policy_id, params, outcome=denied, reason | Audit log record; policy decision record |
| T2-AUD-003 | Failed task with retry | Each attempt logged with attempt number and error_class | Audit log records; worker error logs |

### T2-ERR Error handling and retry behavior with policy constraints
| ID | Scenario | Assertions | Evidence |
| --- | --- | --- | --- |
| T2-ERR-001 | Transient network error | Retry occurs with backoff; respects rate limits | Scheduler log; worker error log; retry schedule |
| T2-ERR-002 | Policy denial error | No retry occurs; task marked denied | Policy decision record; audit log |
| T2-ERR-003 | Rate limit error from target | Domain cooldown applied; tasks rescheduled | Scheduler log; queue state; audit log |
| T2-ERR-004 | Max retry exceeded | Task marked failed; no further attempts | Audit log; task state transition log |

### T2-DET Deterministic task scheduling inputs
| ID | Scenario | Assertions | Evidence |
| --- | --- | --- | --- |
| T2-DET-001 | Identical inputs and seed | Same task list, ordering, and payloads | Scheduler output snapshots; task ids |
| T2-DET-002 | Deterministic task_id derivation | task_id is stable for same inputs | Task id derivation log; scheduler output |
| T2-DET-003 | Duplicate inputs | Dedupe produces stable, repeatable task set | Scheduler output; dedupe log |
