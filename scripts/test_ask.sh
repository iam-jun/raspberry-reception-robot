#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

HOST="${ORCHESTRATOR_HOST:-127.0.0.1}"
PORT="${ORCHESTRATOR_PORT:-8000}"
QUESTION="${1:-What information is available for visitors?}"

curl -sS -X POST "http://${HOST}:${PORT}/ask" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"${QUESTION}\"}"
echo
