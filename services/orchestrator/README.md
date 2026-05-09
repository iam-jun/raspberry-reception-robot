# Orchestrator Service

The orchestrator coordinates the Smart Reception Robot workflow. It will receive UI requests, call STT when audio is involved, call RAG to produce an answer, and call TTS to generate audio output.

Current MVP endpoints:

- `GET /health`
- `POST /ask`
- `POST /voice/ask`
- `POST /documents/ingest`
- `GET /documents`
- `GET /audio/{filename}`
- `GET /vision/emotion`

Run from the repository root with:

```bash
scripts/run_dev.sh
```

The static touch UI in `apps/ui` is served at `/`.
