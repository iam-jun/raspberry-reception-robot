# AsrEngine C++ SDK

This SDK exposes a small C++ interface for Raspberry/Linux integration.
It does not open microphones and does not depend on UI/webview/miniaudio.
The host application owns audio capture and pushes PCM frames into `AsrEngine`.

## Runtime Pipeline

```text
PCM mono 16 kHz
-> light high-pass
-> sherpa-onnx GTCRN online denoiser
-> sherpa-onnx Silero VAD
-> VAD pre-roll + hangover gate
-> sherpa-onnx streaming Zipformer ASR
-> partial/final transcript callbacks
```

No transcript post-filter is applied. Hotwords are used only as decoder biasing.

## Lifecycle

```cpp
#include "asr/AsrEngine.h"

asr::AsrConfig config;
config.model_dir = "/opt/asr-sdk/models/sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10";
config.denoiser_model = "/opt/asr-sdk/models/sherpa-official-ns-vad/gtcrn_simple.onnx";
config.vad_model = "/opt/asr-sdk/models/sherpa-official-ns-vad/silero_vad.onnx";
config.hotwords_file = "/opt/asr-sdk/hotwords/hotwords_vi.txt";
config.bpe_vocab = "/opt/asr-sdk/models/sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10/bpe.vocab";

asr::AsrEngine engine(config);

engine.set_callbacks({
    .on_partial = [](const std::string& text) {
        // Realtime unstable transcript.
    },
    .on_final = [](const std::string& text) {
        // Stable endpointed transcript segment.
    },
    .on_status = [](asr::AsrStatus status, const std::string& message) {
        // Log loading/ready/listening/streaming/error.
    },
    .on_metrics = [](const asr::AsrMetrics& metrics) {
        // Observe RMS/peak/VAD/queue health.
    }
});

engine.load();          // Loads ASR, GTCRN NS, and Silero VAD into RAM.
engine.start_session(); // Starts a new stream. Now push_audio_* is accepted.

// Push 20-100 ms chunks. Expected format: mono 16 kHz PCM.
engine.push_audio_f32(samples, frame_count, 16000);

engine.stop_session();  // Stops current stream, clears queued audio/transcript.
engine.unload();        // Releases model RAM; call this to let the model sleep.
```

## Required Audio Format

- PCM mono
- 16 kHz
- `float32` in `[-1, 1]` via `push_audio_f32()`, or signed `int16` via `push_audio_i16()`
- Feed small realtime chunks, normally 20-100 ms.

If the device/server captures another sample rate, resample before calling the SDK.
SDK v1 validates the sample rate instead of silently resampling, so bad input is obvious.

## Hotwords

If `hotwords_file` or `hotwords_text` is set, `AsrEngine` switches sherpa decoding to
`modified_beam_search` and applies `hotwords_score`.

For BPE hotwords, provide `bpe.vocab` if available. If the package only has
`bpe.model`, generate `bpe.vocab` during deployment with SentencePiece tools.

Start with a moderate hotword list. Very large or over-boosted lists can make the
decoder hallucinate favored words.

## Build On Raspberry/Linux

Install/download a Linux ARM64 sherpa-onnx runtime that contains headers and libs:

```text
<sherpa-onnx-root>/include
<sherpa-onnx-root>/lib/libsherpa-onnx-cxx-api.so
<sherpa-onnx-root>/lib/libsherpa-onnx-c-api.so
<sherpa-onnx-root>/lib/libonnxruntime.so
```

Then build:

```bash
cmake -S sdk/asr -B build-asr-sdk \
  -DCMAKE_BUILD_TYPE=Release \
  -DSHERPA_ONNX_ROOT=/path/to/sherpa-onnx-linux-aarch64 \
  -DASR_ENGINE_BUILD_EXAMPLES=ON
cmake --build build-asr-sdk
```

Run WAV example:

```bash
./build-asr-sdk/asr_from_wav /opt/asr-sdk /opt/asr-sdk/models/sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10/test_wavs/en.wav
```

## Threading Notes

- `load()`, `unload()`, `start_session()`, and `stop_session()` are lifecycle calls.
- `push_audio_*()` is safe to call repeatedly from one audio feeder thread.
- The SDK has an internal worker thread for denoise/VAD/ASR decode.
- If audio is pushed faster than decode, old queued audio is dropped after `max_queue_seconds` to avoid unbounded RAM growth.
