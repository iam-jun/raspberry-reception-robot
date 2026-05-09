# Orchestrator Service

The orchestrator coordinates the Smart Reception Robot workflow. It will receive UI requests, call STT when audio is involved, call RAG to produce an answer, and call TTS to generate audio output.

Current development endpoints:

- `GET /health`
- `POST /ask`

Run from the repository root with:

```bash
scripts/run_dev.sh
```

