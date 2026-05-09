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
WAV_PATH="${1:-}"

if [ -n "${WAV_PATH}" ]; then
  curl -sS -X POST "http://${HOST}:${PORT}/voice/ask" \
    -H "Content-Type: audio/wav" \
    --data-binary @"${WAV_PATH}"
else
  curl -sS -X POST "http://${HOST}:${PORT}/voice/ask?duration_seconds=5"
fi
echo
