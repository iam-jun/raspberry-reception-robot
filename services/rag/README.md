# RAG Service

This module ingests `.txt`, `.md`, and `.pdf` files from `documents/source`, chunks them, embeds them, and persists a local retrieval index under `storage/vector_db`.

`service.py` exposes:

- `ingest_documents()`
- `retrieve(question, top_k=4)`
- `generate_answer(question, contexts)`

OpenAI embeddings are used when `OPENAI_API_KEY` is configured. Without a key, ingestion falls back to a small local hash embedding so local endpoint testing can still run.

Run directly:

```bash
python3 services/rag/ingest.py
python3 services/rag/ask.py --question "What can visitors ask?"
```
