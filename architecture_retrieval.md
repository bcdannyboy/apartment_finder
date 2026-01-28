# Retrieval Stack (Authoritative)

## Allowed retrieval paths
- Postgres filters for structured fields.
- Postgres FTS for text retrieval.
- pgvector for semantic retrieval.

## Prohibited retrieval paths
- External search engines or hosted vector databases.
- OpenSearch or any separate vector DB.

## Instrumentation requirements
- Query audits must demonstrate only Postgres FTS and pgvector are used.
- Retrieval requests that attempt external search must be rejected.
