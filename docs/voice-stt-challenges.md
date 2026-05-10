# Voice STT Challenges and Fixes

This note records the main voice interaction issues found during MVP testing and the changes made to keep the reception robot usable in a real kiosk setting.

## Challenge 1: STT Returned `el` During Silence

### Symptom

The live speech-to-text stream often produced the final transcript `el`, even when the visitor did not clearly say anything. The UI treated that transcript as a real question, sent it to `/ask`, and generated an unnecessary answer.

### Root Cause

The streaming recognizer was receiving raw microphone frames immediately after the WebSocket opened, including silence and background noise. With no speech gate in front of sherpa-onnx, the model could hallucinate a short token from low-level noise.

The hotwords file also caused many invalid-token warnings and could bias recognition. Hotwords are useful later, but they should not be enabled by default until the hotword list is aligned with the model token vocabulary.

### Solution

The streaming STT binary now applies a lightweight pre-speech RMS gate before feeding audio into the recognizer:

- Ignore low-energy frames until speech-like audio is detected.
- Require multiple speech-like frames before starting recognition.
- Suppress implausible final transcripts such as empty text, text shorter than 3 characters, and the known hallucination `el`.
- Disable streaming hotwords by default. They can be enabled explicitly with `ASR_ENABLE_HOTWORDS=true`.

Relevant file:

```text
services/stt/asr-sdk/examples/asr_push_stream.cpp
```

Useful tuning variables:

```bash
ASR_MIN_SPEECH_RMS=350
ASR_MIN_SPEECH_FRAMES=3
ASR_ENABLE_HOTWORDS=false
```

If valid speech is missed in a quiet microphone setup, lower `ASR_MIN_SPEECH_RMS`, for example:

```bash
ASR_MIN_SPEECH_RMS=250
```

## Challenge 2: Bot Listened to Its Own TTS Audio

### Symptom

After answering, the browser played TTS audio while the live WebSocket listener could still be active. The microphone heard the robot's own speaker output, transcribed it, and triggered new `/ask` requests. This created an answer loop.

### Root Cause

Voice capture and answer playback were independent UI states. Starting TTS did not forcibly close the active voice WebSocket, and the `Talk` control could still be used while audio was playing.

### Solution

The browser UI now treats listening and speaking as mutually exclusive states:

- Close the voice WebSocket before playing answer audio.
- Disable the `Talk` button while TTS audio is playing.
- Refuse to start voice capture if answer audio is currently playing.
- Re-enable voice capture after audio ends or playback is paused.
- Filter too-short frontend transcripts before sending them to `/ask`.

Relevant file:

```text
apps/ui/app.js
```

## Verification

The fixes were checked with:

```bash
cmake --build services/stt/asr-sdk/build -j4
bash -lc 'dd if=/dev/zero bs=3200 count=20 2>/dev/null | services/stt/asr-sdk/build/asr_push_stream services/stt/asr-sdk'
```

Expected result for the silence test:

```text
status: loading - Creating sherpa-onnx C API recognizer
status: streaming - Decoding stream
status: ready - Stream transcription complete
```

There should be no `partial:` or `final:` transcript for silence.

The WebSocket path was also checked with a local client. It should connect without producing an immediate fake final transcript.

## Operational Notes

- Keep speaker volume and microphone placement separated where possible. Software gating helps, but physical echo control still matters.
- If the environment is noisy, increase `ASR_MIN_SPEECH_RMS`.
- If visitors speak softly or the microphone gain is low, decrease `ASR_MIN_SPEECH_RMS`.
- Leave `ASR_ENABLE_HOTWORDS=false` until the hotword list is cleaned for the sherpa model vocabulary.
