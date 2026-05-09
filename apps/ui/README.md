# UI App

This folder contains the static touch-screen UI served by the orchestrator at `/`.

The UI calls orchestrator endpoints only:

- `GET /health`
- `POST /documents/ingest`
- `POST /ask`
- `POST /voice/ask`

It shows typed or transcribed questions, answers, sources, emotion status, and the generated audio playback control.
