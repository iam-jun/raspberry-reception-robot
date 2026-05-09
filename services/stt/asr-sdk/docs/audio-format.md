# Audio Format Contract

`AsrEngine` does not capture audio. The caller must provide PCM frames.

Required input:

- Mono PCM
- 16000 Hz
- Little-endian `int16` or normalized `float32`
- Small realtime chunks, usually 20 ms, 40 ms, 60 ms, or 100 ms

Recommended chunk sizes:

```text
20 ms  = 320 samples at 16 kHz
40 ms  = 640 samples at 16 kHz
60 ms  = 960 samples at 16 kHz
100 ms = 1600 samples at 16 kHz
```

If the device gives stereo or multichannel audio, downmix before calling the SDK
or pass `channels > 1`; SDK v1 keeps the first channel.

If the device gives 44.1 kHz, 48 kHz, or another sample rate, resample before
calling the SDK. The SDK validates sample rate and throws on mismatch so bad
integration is detected early.
