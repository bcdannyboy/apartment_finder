#!/usr/bin/env bash
set -euo pipefail

echo "Checking host bindings (expected 127.0.0.1 only):"

if command -v lsof >/dev/null 2>&1; then
  lsof -nP -iTCP:5432 -sTCP:LISTEN || true
  lsof -nP -iTCP:6379 -sTCP:LISTEN || true
  lsof -nP -iTCP:3128 -sTCP:LISTEN || true
else
  if command -v ss >/dev/null 2>&1; then
    ss -lnt | grep -E '(:5432|:6379|:3128)' || true
  else
    echo "Neither lsof nor ss is available; check your OS networking tools."
  fi
fi
