# Smart Reception Robot

Smart Reception Robot is a Raspberry Pi 5 project for a touch-screen reception assistant. The system is organized as multiple services so speech recognition, retrieval, answer generation, speech output, and UI workflows can evolve independently.

## Architecture

The intended request flow is:

```text
UI -> Orchestrator -> STT -> RAG -> TTS
```

## Modules

- `apps/ui`: Touch-screen interaction. The UI should capture user actions, display the current question and answer, and call the orchestrator endpoints.
- `services/orchestrator`: Workflow coordination. It exposes the development API and will call STT, RAG, and TTS components.
- `services/stt`: Speech-to-text. This uses the existing sherpa-onnx ASR SDK now located at `services/stt/asr-sdk`.
- `services/rag`: Document ingestion, retrieval, and answer generation.
- `services/tts`: Text-to-speech. This will turn answers into audio files for speaker playback.
- `models`: Project-level model storage for STT, VAD, embeddings, and TTS assets.
- `documents/source`: Source documents for RAG ingestion.
- `storage`: Generated vector databases, audio files, and logs.

## MVP Phases

1. Button -> record fixed duration -> STT -> show text.
2. STT text -> RAG -> show answer.
3. Answer -> TTS -> speaker.
4. Add VAD and better conversation handling.

## Build STT SDK on Raspberry Pi 5

```bash
cd services/stt/asr-sdk
mkdir -p build
cd build
cmake ..
make -j4
```

Generated binaries will be under the SDK build output. Check `services/stt/asr-sdk/README_RASPBERRY_SDK.md` and the CMake output for exact target names.

Before using microphone input, validate STT with a known WAV file. The wrapper at `services/stt/run_stt.sh` is a scaffold for wiring the exact SDK binary once confirmed.

## Run Orchestrator in Development

Create and activate a Python environment, then install dependencies:

```bash
cd services/orchestrator
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

From the repository root, start the development server:

```bash
scripts/run_dev.sh
```

The API exposes:

- `GET /health`
- `POST /ask` with JSON body `{ "question": "..." }`

