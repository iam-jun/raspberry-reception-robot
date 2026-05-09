#!/usr/bin/env bash
set -euo pipefail

TEXT="${1:-}"

if [ -z "${TEXT}" ]; then
  echo "Usage: services/tts/run_tts.sh \"text to speak\"" >&2
  exit 1
fi

# TODO: Replace this with the piper command once the voice model is selected.
# Example shape:
#   echo "${TEXT}" | piper --model models/tts/voice.onnx --output_file storage/audio/answer.wav
echo "TTS placeholder. Text received: ${TEXT}"

