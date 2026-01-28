# Retrieval Stack (Authoritative)

## Allowed retrieval paths
- Postgres filters for structured fields.
- Postgres FTS for text retrieval.
- pgvector for semantic retrieval.
- External search engines and hosted vector databases are permitted when configured.

## Prohibited retrieval paths
- None (external retrieval is allowed when enabled).

## Instrumentation requirements
- Query audits must record which retrieval layers are used (FTS, pgvector, external).
- Retrieval requests must declare external search usage when enabled.
