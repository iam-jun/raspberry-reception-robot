# TTS Service

This module handles text-to-speech. It is separate from STT/ASR and uses the OpenAI TTS API for the MVP.

- Input: answer text.
- Output: MP3 file under `storage/audio`.
- Config: `OPENAI_API_KEY`, `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE`, `AUDIO_OUTPUT_DIR`.

No local TTS model is required on Raspberry Pi. If `OPENAI_API_KEY` is missing, the service returns a clear skipped reason and the orchestrator still returns the text answer.

Run directly:

```bash
services/tts/run_tts.sh "Hello, welcome to the reception desk."
```
