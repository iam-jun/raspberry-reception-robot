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

Validate with a WAV file first before wiring microphone capture. Once the correct SDK binary and arguments are confirmed, update `services/stt/run_stt.sh`.

