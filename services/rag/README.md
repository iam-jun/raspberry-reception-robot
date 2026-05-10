cu# Smart Reception RAG Service

This service builds a small Retrieval-Augmented Generation pipeline for UIT admission information. It crawls only URLs listed in `knowledge_base/sources.yaml`, stores cleaned Markdown, chunks the documents, embeds the chunks, and serves retrieval/answer APIs.

Markdown is used as the intermediate format because it is easy to inspect, version, clean, and chunk by headings before building the vector index.

## Install

```bash
cd services/rag
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The default embedding backend is FastEmbed with this multilingual model:

```bash
RAG_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

FastEmbed uses ONNX Runtime and avoids the heavy `sentence-transformers -> torch` dependency chain, which is a better fit for Raspberry Pi 5. If FastEmbed is not available yet, the service still falls back to a deterministic local embedding so tests and offline demos can run.

## Crawl UIT Source

```bash
python scripts/crawl_sources.py
```

The first configured source is the UIT admission FAQ page:

```text
https://tuyensinh.uit.edu.vn/cau-hoi-thuong-gap
```

Raw HTML is saved in `knowledge_base/raw_html/`; cleaned Markdown is saved in `knowledge_base/markdown/`.

## Ingest Documents

```bash
python scripts/ingest_documents.py
```

The vector index is persisted under `knowledge_base/index/` as a local JSON index. This keeps the Pi deployment simple and avoids running a heavier local vector database for the MVP.

## Run API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

Health check:

```bash
curl http://localhost:8003/health
```

Ask:

```bash
curl -X POST http://localhost:8003/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"UIT là trường công lập hay dân lập?","top_k":5}'
```

Retrieve only:

```bash
curl -X POST http://localhost:8003/retrieve \
  -H "Content-Type: application/json" \
  -d '{"question":"Điều kiện chuyển ngành ở UIT là gì?","top_k":5}'
```

List configured sources:

```bash
curl http://localhost:8003/sources
```

## Answer Modes

Without `OPENAI_API_KEY`, the service uses extractive/local mode and returns concise grounded text from the best retrieved chunks.

With `OPENAI_API_KEY`, it calls OpenAI using a grounding prompt that requires the answer to use only retrieved context and to return a Vietnamese fallback message when the context does not contain the answer.

## Evaluation

```bash
python scripts/evaluate_rag.py
```

The script prints each question, top retrieved chunk, generated answer, source-found flag, and response time in milliseconds.

## Tests

```bash
pytest tests
```

## Orchestrator Integration

The current orchestrator can keep using `services.rag.service.RagService`. For service-to-service integration, call:

```text
POST http://localhost:8003/ask
```
