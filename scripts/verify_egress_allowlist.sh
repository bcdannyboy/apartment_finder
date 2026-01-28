#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_PROFILES=tools

# Uses the internal-only netcheck container with the egress proxy configured.
docker compose -f "${REPO_ROOT}/docker-compose.yml" run --rm netcheck sh -c '
  set -e
  echo "OpenAI (expect 200/401/403 but not proxy deny for allowed domain):"
  curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models || true
  echo "Firecrawl (expect 200/401/403 but not proxy deny for allowed domain):"
  curl -sS -o /dev/null -w "%{http_code}\n" https://api.firecrawl.dev/ || true
  echo "Blocked domain (expect 403 from proxy):"
  curl -sS -o /dev/null -w "%{http_code}\n" https://example.com/ || true
'
