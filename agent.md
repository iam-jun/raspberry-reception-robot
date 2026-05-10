# Agent Notes

This repository targets a Raspberry Pi 5 touch-screen reception robot. Keep changes pragmatic and MVP-oriented.

## Architecture

Primary flow:

```text
apps/ui -> services/orchestrator -> services/stt -> services/rag -> services/tts
                                      |
                                      -> services/vision
```

OpenAI is used for chat answers, embeddings, and TTS. Do not add heavy local TTS to the Pi.

## STT State

The working STT assets live under:

```text
services/stt/asr-sdk
```

Do not rewrite or delete the SDK models. The Python app should call:

```text
services/stt/wrapper.py
```

The wrapper expects:

```bash
STT_BINARY=/absolute/path/to/services/stt/asr-sdk/build/asr_from_wav
STT_MODEL_DIR=/absolute/path/to/services/stt/asr-sdk
SHERPA_ONNX_ROOT=/absolute/path/to/sherpa-onnx-runtime
```

`SHERPA_ONNX_ROOT` must contain:

```text
include/sherpa-onnx/c-api/c-api.h
include/sherpa-onnx/c-api/cxx-api.h
lib/libsherpa-onnx-cxx-api.so
lib/libsherpa-onnx-c-api.so
lib/libonnxruntime.so
```

The `asr_from_wav` example intentionally uses the sherpa C ABI directly. This avoids a segfault seen when the WAV smoke test went through the custom `AsrEngine` C++ wrapper on Raspberry Pi.

Build STT:

```bash
cd services/stt/asr-sdk
rm -rf build
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DASR_ENGINE_BUILD_EXAMPLES=ON \
  -DSHERPA_ONNX_ROOT="$SHERPA_ONNX_ROOT"
cmake --build build -j4
```

Verify shared libraries:

```bash
ldd build/asr_from_wav | grep -E 'sherpa|onnx'
```

Expected paths should point to `$SHERPA_ONNX_ROOT/lib`.

Run STT smoke test:

```bash
cd /path/to/repo
export STT_BINARY="$PWD/services/stt/asr-sdk/build/asr_from_wav"
export STT_MODEL_DIR="$PWD/services/stt/asr-sdk"
export LD_LIBRARY_PATH="$SHERPA_ONNX_ROOT/lib:${LD_LIBRARY_PATH:-}"

services/stt/run_stt.sh services/stt/asr-sdk/models/sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10/test_wavs/en.wav
```

## Runtime

Run the MVP:

```bash
scripts/run_dev.sh
```

Open:

```text
http://localhost:8000
```

Useful checks:

```bash
curl http://127.0.0.1:8000/health
scripts/ingest_documents.sh
scripts/test_ask.sh "What can visitors ask?"
```

## Development Rules

- Keep Raspberry Pi dependencies lightweight.
- Prefer OpenAI TTS over local TTS.
- Keep paths configurable through `.env`.
- Use `pathlib` in Python.
- Do not break the existing `services/stt/asr-sdk` model layout.
- If hardware is unavailable, keep graceful degradation with clear errors.
