#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "${REPO_ROOT}/data/object_store"

docker compose -f "${REPO_ROOT}/docker-compose.yml" up -d --build
