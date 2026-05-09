#!/usr/bin/env bash
set -euo pipefail

TEXT="${1:-}"

if [ -z "${TEXT}" ]; then
  echo "Usage: services/tts/run_tts.sh \"text to speak\"" >&2
  exit 1
fi

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 - <<'PY' "${TEXT}"
import sys
from services.tts.service import TtsService

result = TtsService().synthesize(sys.argv[1])
print(result)
PY
