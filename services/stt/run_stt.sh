#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASR_SDK_DIR="${SCRIPT_DIR}/asr-sdk"
BUILD_DIR="${ASR_SDK_DIR}/build"

if [ ! -d "${ASR_SDK_DIR}" ]; then
  echo "ASR SDK directory not found: ${ASR_SDK_DIR}" >&2
  exit 1
fi

if [ ! -d "${BUILD_DIR}" ]; then
  echo "ASR SDK is not built yet."
  echo "Build it with:"
  echo "  cd services/stt/asr-sdk"
  echo "  mkdir -p build"
  echo "  cd build"
  echo "  cmake .."
  echo "  make -j4"
  exit 1
fi

# TODO: Replace this with the exact ASR binary name and arguments after confirming
# the generated target in services/stt/asr-sdk/build.
echo "STT wrapper scaffold. ASR SDK build directory: ${BUILD_DIR}"
echo "TODO: run the correct ASR SDK binary with WAV or microphone input."

