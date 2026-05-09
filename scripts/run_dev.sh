#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH_DIR="${ROOT_DIR}/services/orchestrator"

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

mkdir -p \
  "${ROOT_DIR}/storage/audio" \
  "${ROOT_DIR}/storage/vector_db" \
  "${ROOT_DIR}/storage/logs" \
  "${ROOT_DIR}/documents/source"

if [ -f "${ORCH_DIR}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${ORCH_DIR}/.venv/bin/activate"
elif [ -f "${ROOT_DIR}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.venv/bin/activate"
fi

if ! python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "Missing orchestrator dependencies."
  echo "Install them with:"
  echo "  cd services/orchestrator"
  echo "  python3 -m venv .venv"
  echo "  . .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

cd "${ROOT_DIR}"
exec python3 -m uvicorn services.orchestrator.main:app \
  --host "${ORCHESTRATOR_HOST:-0.0.0.0}" \
  --port "${ORCHESTRATOR_PORT:-8000}" \
  --reload
