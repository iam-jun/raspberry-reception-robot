#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASR_SDK_DIR="${SCRIPT_DIR}/asr-sdk"
BUILD_DIR="${ASR_SDK_DIR}/build"

if [ ! -d "${ASR_SDK_DIR}" ]; then
  echo "ASR SDK directory not found: ${ASR_SDK_DIR}" >&2
  exit 1
fi

if [ -z "${STT_BINARY:-}" ] && [ ! -d "${BUILD_DIR}" ]; then
  echo "ASR SDK is not built yet."
  echo "Build it with:"
  echo "  cd services/stt/asr-sdk"
  echo "  mkdir -p build"
  echo "  cd build"
  echo "  cmake .. -DASR_ENGINE_BUILD_EXAMPLES=ON"
  echo "  make -j4"
  exit 1
fi

WAV_PATH="${1:-}"

if [ -z "${WAV_PATH}" ]; then
  echo "Usage: services/stt/run_stt.sh path/to/mono-16khz.wav" >&2
  exit 1
fi

cd "${SCRIPT_DIR}/../.."
python3 -m services.stt.wrapper "${WAV_PATH}"
