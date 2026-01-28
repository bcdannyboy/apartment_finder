#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_USER="${DB_USER:-af}"
DB_NAME="${DB_NAME:-apartment_finder}"

# Ensure extensions exist even if the data volume already exists.
docker compose -f "${REPO_ROOT}/docker-compose.yml" exec -T postgres \
  psql -U "${DB_USER}" -d "${DB_NAME}" -f /docker-entrypoint-initdb.d/00_extensions.sql
