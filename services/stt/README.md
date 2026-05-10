# STT Service

This module handles speech-to-text and ASR. It is separate from TTS.

The existing sherpa-onnx ASR SDK lives in:

```text
services/stt/asr-sdk
```

## Build the ASR SDK

On Raspberry Pi 5:

```bash
cd services/stt/asr-sdk
mkdir -p build
cd build
cmake ..
make -j4
```

Generated binaries should appear in the SDK build output. Check the CMake output and `services/stt/asr-sdk/README_RASPBERRY_SDK.md` for the exact executable names.

## Run Strategy

Validate with a WAV file first before wiring microphone capture:

```bash
services/stt/run_stt.sh path/to/mono-16khz.wav
```

The Python wrapper in `wrapper.py` exposes:

- `transcribe_wav(path: str) -> str`
- `record_audio(duration_seconds: int, output_path: str) -> str`

Config:

- `STT_BINARY`: ASR executable path, for example `services/stt/asr-sdk/build/asr_from_wav`.
- `STT_MODEL_DIR`: ASR SDK root containing the `models` directory.
- `STT_SAMPLE_RATE`: default `16000`.
- `SHERPA_ONNX_ROOT`: sherpa-onnx runtime root containing `include` and `lib`.

The wrapper does not modify model files. It shells out to the configured binary and extracts `final:` transcript lines from stdout. If `SHERPA_ONNX_ROOT` is set, the wrapper automatically prepends `$SHERPA_ONNX_ROOT/lib` to `LD_LIBRARY_PATH` for the STT subprocess.
