# Traceability Matrix (Authoritative)

## Purpose
Maps each constraint and contract surface to the authoritative docs and test plans.

| Item | Authoritative doc | Tests |
| --- | --- | --- |
| CONSTRAINT_LOCAL_ONLY_BINDING | architecture_decisions_and_naming.md, architecture_compliance_enforcement.md | phase_tests_phase1.md, phase_tests_integration.md |
| CONSTRAINT_PAID_SERVICES_ONLY | architecture_decisions_and_naming.md, architecture_compliance_enforcement.md | phase_tests_phase1.md, phase_tests_integration.md |
| CONSTRAINT_COMPLIANCE_GATING | architecture_decisions_and_naming.md, architecture_compliance_enforcement.md | phase_tests_phase1.md, phase_tests_phase2.md, phase_tests_integration.md |
| CONSTRAINT_MANUAL_ONLY_IMPORT | architecture_decisions_and_naming.md, architecture_tasks_queue.md | phase_tests_phase1.md, phase_tests_phase2.md |
| CONSTRAINT_PROVENANCE_FIRST | architecture_decisions_and_naming.md, architecture_schema.md, architecture_evidence.md | phase_tests_phase1.md, phase_tests_phase3.md |
| CONSTRAINT_EVIDENCE_REQUIRED | architecture_evidence.md, architecture_schema.md | phase_tests_phase1.md, phase_tests_phase3.md, phase_tests_phase8.md |
| CONSTRAINT_EVIDENCE_NORMALIZED | architecture_schema.md | phase_tests_phase1.md, phase_tests_phase3.md |
| CONSTRAINT_RETRIEVAL_AUDIT | architecture_retrieval.md | phase_tests_phase6.md |
| CONSTRAINT_GEO_LOCAL_ONLY | architecture_geo_commute.md | phase_tests_phase5.md, phase_tests_integration.md |
| CONSTRAINT_ALERT_CHANNELS | architecture_decisions_and_naming.md, architecture_api_contracts.md | phase_tests_phase7.md |
| CONSTRAINT_QUEUE_REDIS_RQ | architecture_decisions_and_naming.md | phase_tests_phase2.md |
| CONSTRAINT_OBJECT_STORE_FILESYSTEM | architecture_decisions_and_naming.md | phase_tests_phase1.md |
| CONSTRAINT_UI_FULL_SPA | architecture_decisions_and_naming.md | phase_tests_phase8.md |
| CONSTRAINT_NETWORK_EGRESS_OPEN | architecture_compliance_enforcement.md | phase_tests_integration.md |
| Policy Gate API contract | architecture_api_contracts.md | phase_tests_phase1.md, phase_tests_integration.md |
| Snapshot Store API contract | architecture_api_contracts.md | phase_tests_phase1.md, phase_tests_integration.md |
| Ranking API contract | architecture_api_contracts.md | phase_tests_phase6.md, phase_tests_integration.md |
| Alert API contract | architecture_api_contracts.md | phase_tests_phase7.md, phase_tests_integration.md |
| SearchSpec schema | architecture_searchspec.md | phase_tests_phase6.md |
| Evidence locator schema | architecture_evidence.md | phase_tests_phase3.md, phase_tests_phase8.md |
| Task schema | architecture_tasks_queue.md | phase_tests_phase2.md |
