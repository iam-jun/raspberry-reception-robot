#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "${ROOT_DIR}/.env" ]; then
  while IFS='=' read -r key value; do
    case "${key}" in
      ""|\#*) continue ;;
    esac
    if [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] && [ -z "${!key+x}" ]; then
      export "${key}=${value}"
    fi
  done < "${ROOT_DIR}/.env"
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
