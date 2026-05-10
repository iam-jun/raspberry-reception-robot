# Smart Reception Robot

Smart Reception Robot is a Raspberry Pi 5 touch-screen reception assistant. The current MVP runs a local FastAPI orchestrator and static browser UI, with local document retrieval, local STT integration hooks, OpenAI answer generation, OpenAI TTS, and lightweight camera face/emotion sampling.

## MVP Architecture

```text
Touch UI -> Orchestrator API -> STT wrapper -> RAG -> OpenAI chat -> OpenAI TTS
                                    |
                                    -> Vision face/emotion snapshot
```

Main folders:

- `apps/ui`: touch-screen web UI served by FastAPI.
- `services/orchestrator`: FastAPI workflow API.
- `services/stt`: sherpa-onnx STT wrapper and existing `asr-sdk`.
- `services/rag`: UIT admission crawling, Markdown cleaning, chunking, FastEmbed retrieval, and answer generation.
- `services/tts`: OpenAI TTS audio generation.
- `services/vision`: camera capture, face detection, and MVP emotion fallback.
- `documents/source`: source `.txt`, `.md`, and `.pdf` files for RAG.
- `storage/vector_db`: generated vector index files.
- `storage/audio`: generated TTS audio and temporary voice recordings.

## Raspberry Pi 5 Setup

Install Python dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

On Raspberry Pi OS, camera and OpenCV support may be better from apt packages:

```bash
sudo apt update
sudo apt install -y alsa-utils python3-opencv python3-picamera2
```

If you use apt-provided `cv2` or `picamera2`, make sure your virtual environment can see system site packages or install the Python packages in the active environment.

## Configure

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Important values:

- `OPENAI_API_KEY`: required for OpenAI embeddings, chat answers, and TTS audio.
- `OPENAI_CHAT_MODEL`: default `gpt-4o-mini`.
- `OPENAI_TTS_MODEL`: default `gpt-4o-mini-tts`.
- `OPENAI_TTS_VOICE`: default `coral`.
- `STT_BINARY`: path to the built sherpa ASR example binary, usually `services/stt/asr-sdk/build/asr_from_wav`.
- `STT_MODEL_DIR`: ASR SDK root, default `services/stt/asr-sdk`.
- `VISION_ENABLED`: set `false` to disable camera sampling.
- `CAMERA_INDEX`: OpenCV camera index, default `0`.

Without `OPENAI_API_KEY`, the app still starts and can ingest/retrieve documents with FastEmbed or the local fallback embedding. It will return an explicit message instead of generating a final OpenAI answer or TTS file.

## Build STT SDK

The existing ASR SDK is kept under `services/stt/asr-sdk` and is not rewritten by the Python MVP. Build the example binary on the Pi:

```bash
cd services/stt/asr-sdk
mkdir -p build
cd build
cmake .. -DASR_ENGINE_BUILD_EXAMPLES=ON -DSHERPA_ONNX_ROOT=/path/to/sherpa-onnx-linux-aarch64
make -j4
```

Validate with a known mono 16 kHz WAV:

```bash
services/stt/run_stt.sh services/stt/asr-sdk/models/sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10/test_wavs/en.wav
```

The Python wrapper expects the ASR binary interface used by `asr_from_wav`:

```text
asr_from_wav <asr-sdk-root> <mono-16k-wav>
```

## Ingest Documents

Put `.txt`, `.md`, or `.pdf` files into `documents/source`, then start the orchestrator and ingest:

```bash
scripts/run_dev.sh
scripts/ingest_documents.sh
```

You can also ingest directly:

```bash
python3 services/rag/ingest.py
```

The RAG service under `services/rag` writes its UIT admission index under `services/rag/knowledge_base/index`. The current Pi-friendly path uses FastEmbed with a local JSON index.

## Run Orchestrator and UI

```bash
scripts/run_dev.sh
```

Open the UI from the Pi browser:

```text
http://localhost:8000
```

From another device on the same network, use the Pi IP address:

```text
http://<raspberry-pi-ip>:8000
```

## API Endpoints

- `GET /health`: status for orchestrator, STT, RAG, TTS, and vision.
- `POST /ask`: typed question flow.
- `POST /voice/ask`: records 5 seconds by default or accepts uploaded WAV/audio bytes.
- `POST /documents/ingest`: ingests `documents/source`.
- `GET /documents`: lists source documents and ingestion state.
- `GET /audio/{filename}`: serves generated OpenAI TTS audio.
- `GET /vision/emotion`: captures and returns the latest face/emotion result.

Typed ask test:

```bash
scripts/test_ask.sh "What can visitors ask the reception assistant?"
```

Voice test with server-side recording:

```bash
scripts/test_voice.sh
```

Voice test with a WAV upload:

```bash
scripts/test_voice.sh path/to/question.wav
```

Camera/emotion test:

```bash
curl http://127.0.0.1:8000/vision/emotion
```

## Current Limitations

- STT depends on the local sherpa-onnx SDK build, model files, and a mono 16 kHz WAV input path.
- Server-side microphone recording requires ALSA `arecord` or the `sounddevice` Python package.
- TTS uses the OpenAI API and is skipped when `OPENAI_API_KEY` is missing.
- OpenAI chat answer generation is required for final natural-language answers.
- Emotion detection is intentionally lightweight: it detects face presence and returns `neutral` for detected faces until a small real emotion model is added.
- Speaker playback is handled by the browser audio control in the MVP; system-level speaker playback can be added later.

## Engineering Notes

- [Voice STT challenges and fixes](docs/voice-stt-challenges.md): documents the `el` silence hallucination, TTS feedback loop, and the guardrails added to resolve them.
- [RAG pipeline design, challenges, and fixes](docs/rag-pipeline-challenges.md): documents the first RAG solution, implementation problems, and the Raspberry Pi-friendly fixes.
