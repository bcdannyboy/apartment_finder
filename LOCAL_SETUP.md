# Local Data Platform Setup (Phase 1)

This setup provides a local-only stack that satisfies the Phase 1 hard constraints:
- Postgres with PostGIS and pgvector
- Redis + RQ worker
- Filesystem object store
- Local-only binding for services
- Outbound network allowlist for OpenAI and Firecrawl only

## What is included
- docker-compose.yml: local-only Postgres, Redis, RQ worker, and egress proxy
- docker/postgres: Postgres image with PostGIS and pgvector
- docker/egress: Squid proxy with strict allowlist
- scripts/: reproducible setup and verification scripts

## Quick start
1) Start the stack
```
./scripts/local_up.sh
```

2) Initialize database extensions
```
./scripts/db_init.sh
```

## Connection details
- Postgres: `postgresql://af:af_local@127.0.0.1:5432/apartment_finder`
- Redis: `redis://127.0.0.1:6379/0`

## Filesystem object store
- Local path: `./data/object_store`
- This is the only supported object store. Do not use S3 or other cloud storage.

## Networking and allowlist enforcement
- Services are attached to the `internal` Docker network (internal: true).
- Only the egress proxy is attached to the external `egress` network.
- Application containers must use the proxy via:
  - `HTTP_PROXY=http://egress-proxy:3128`
  - `HTTPS_PROXY=http://egress-proxy:3128`
- Allowed domains are defined in `docker/egress/allowed_domains.txt` and are limited to OpenAI and Firecrawl.

## Verify local-only binding
```
./scripts/verify_local_only.sh
```
Expected: Postgres, Redis, and the proxy are only bound to 127.0.0.1.

## Verify egress allowlist
```
./scripts/verify_egress_allowlist.sh
```
Expected: OpenAI and Firecrawl return a non-403 status code; a non-allowed domain returns 403.

## Stop the stack
```
docker compose down
```
