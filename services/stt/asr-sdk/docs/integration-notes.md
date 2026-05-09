# Integration Notes

## Which Function Loads Models Into RAM?

`AsrEngine::load()` loads:

- sherpa-onnx streaming Zipformer recognizer
- GTCRN online denoiser
- Silero VAD

Call this once when the service starts or when ASR should wake up.

## Which Function Releases Model RAM?

`AsrEngine::unload()` stops the worker and releases model handles.

Call this when ASR should sleep or the process is shutting down.

## Which Function Starts A Recognition Session?

`AsrEngine::start_session()` creates a fresh online stream and clears old
transcript/audio state. The loaded models stay in RAM.

## Which Function Stops A Recognition Session?

`AsrEngine::stop_session()` clears the current stream and queued audio, but keeps
models loaded. Use this when the user stops talking/recording but the service may
start again soon.

## Which Function Pushes Audio?

Use one of:

```cpp
engine.push_audio_f32(samples, frame_count, 16000);
engine.push_audio_i16(samples, frame_count, 16000);
```

`frame_count` is the number of audio frames, not bytes. For mono audio, frames
equals samples.

## How To Receive Text?

Register callbacks:

```cpp
engine.set_callbacks({
    .on_partial = [](const std::string& text) {},
    .on_final = [](const std::string& text) {},
    .on_status = [](asr::AsrStatus status, const std::string& message) {},
    .on_metrics = [](const asr::AsrMetrics& metrics) {}
});
```

Use `on_partial` for realtime display. Use `on_final` as the stable committed
text after endpoint detection.

## What Not To Do

- Do not feed compressed audio such as MP3/AAC/Opus.
- Do not feed 48 kHz unless resampled to 16 kHz first.
- Do not call `load()` for every chunk.
- Do not filter or remove transcript text after ASR unless the product has a
clear domain rule. This SDK intentionally avoids post-filtering to prevent lost
Vietnamese words.
