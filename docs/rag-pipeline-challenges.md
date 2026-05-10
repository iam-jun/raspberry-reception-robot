# RAG Pipeline Design, Challenges, and Fixes

This note records how the RAG knowledge base was introduced into the Smart Reception Robot project, what the first solution looked like, which problems appeared during implementation, and how they were handled.

## Goal

The RAG service gives the reception robot a grounded knowledge base for UIT admission questions. Instead of relying only on a general LLM, the robot first retrieves relevant content from public UIT admission pages and then answers using that retrieved context.

The first target source is:

```text
https://tuyensinh.uit.edu.vn/cau-hoi-thuong-gap
```

The service intentionally does not crawl the whole UIT website. It only crawls URLs explicitly configured in:

```text
services/rag/knowledge_base/sources.yaml
```

## First Solution

The first design was a simple end-to-end RAG pipeline:

```text
Configured URLs
  -> crawler
  -> raw HTML
  -> cleaned Markdown
  -> chunks
  -> embeddings
  -> local vector index
  -> retrieval API
  -> grounded answer
```

The implementation lives under:

```text
services/rag/
  app/
  scripts/
  knowledge_base/
  tests/
```

The main workflow is:

```bash
cd services/rag
python scripts/crawl_sources.py
python scripts/ingest_documents.py
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

The service exposes:

- `GET /health`
- `POST /ask`
- `POST /retrieve`
- `GET /sources`

For answer generation, the RAG engine uses a fully local composer. No external LLM API is called by the default `/ask` flow.

The composer treats retrieved chunks as evidence only. It cleans Markdown, splits text into candidate lines/sentences, scores those candidates against the user question, and applies simple Vietnamese templates for common UIT admission intents.

The grounding rule is strict: if the indexed documents do not contain the answer, the robot must return:

```text
Hiện tại em chưa tìm thấy thông tin này trong tài liệu đã được nạp. Anh/chị vui lòng liên hệ bộ phận tuyển sinh UIT để được hỗ trợ chính xác hơn.
```

## Why Markdown Is Used Before Indexing

The crawler saves both raw HTML and cleaned Markdown.

Raw HTML is useful for debugging because it preserves the original downloaded page. Markdown is better for RAG because it is easier to inspect, easier to split by headings, and less noisy than website HTML.

For the UIT FAQ page, Markdown also makes questions and answers more visible:

```text
## 1. Trường ĐH Công nghệ Thông tin là đại học công lập hay đại học dân lập?

## 4. Các chính sách đặc biệt trong đào tạo tại UIT?

### a) Chuyển ngành ...
```

This structure helps the chunker keep related question and answer content together.

## Problem 1: The Initial Dependency Set Was Too Heavy for Raspberry Pi

### Symptom

Installing `services/rag/requirements.txt` started downloading the `sentence-transformers` dependency chain. This pulled in `torch`, CUDA-related packages, and large aarch64 wheels.

The installation was slow and fragile on Raspberry Pi. It eventually failed during a network timeout while downloading dependencies. Because the install stopped early, basic crawler dependencies such as `beautifulsoup4` were not installed, causing:

```text
ModuleNotFoundError: No module named 'bs4'
```

### Root Cause

The first dependency list treated high-quality semantic retrieval as mandatory. On Raspberry Pi, `sentence-transformers` depends on `torch`, and recent `torch` wheels can pull very large packages. That is too heavy for a student MVP that only needs to crawl, ingest, and answer basic FAQ questions reliably.

### Solution

The RAG embedding backend was changed to FastEmbed:

```text
fastembed
RAG_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

FastEmbed can run the multilingual MiniLM model through ONNX Runtime and avoids importing the full `sentence-transformers` Python package and its `torch` dependency chain.

The dependency list was also simplified.

Base install:

```text
services/rag/requirements.txt
```

This contains the crawler, API, FastEmbed, and test dependencies.

The code already supports graceful fallback:

- If FastEmbed is installed, it uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- If FastEmbed is not available, it uses a deterministic local hash embedding fallback.
- The vector index is stored as a local JSON file under `knowledge_base/index/`.

This made the Raspberry Pi path simple:

```bash
cd services/rag
pip install -r requirements.txt
python scripts/crawl_sources.py
python scripts/ingest_documents.py
```

## Problem 2: The UIT FAQ Page Did Not Convert Cleanly at First

### Symptom

The first crawler pass produced Markdown where most FAQ content appeared as one long paragraph. Numbered questions, answer text, bus routes, and tuition information were mixed together.

This made chunking weak. The chunker could split by character length, but it could not reliably preserve each FAQ question and answer as a clear unit.

### Root Cause

The UIT page HTML is not a clean article with each FAQ item represented as separate semantic sections. Much of the meaningful content is rendered as continuous text inside broad layout containers.

Generic HTML-to-text extraction preserved the words, but not enough structure.

### Solution

The cleaner was kept simple, but a small FAQ structure pass was added:

- Convert numbered FAQ items such as `1.`, `2.`, `3.` into Markdown `##` headings.
- Convert sub-items such as `a) Chuyển ngành` into `###` headings.
- Put `Trả lời:` and common list-like text on clean lines.
- Keep contact details, tuition information, bus routes, and source URL metadata.

This changed ingestion from a few broad chunks to more useful FAQ-level chunks.

Example result:

```text
Loaded documents: 1
Created chunks: 13
Indexed source: uit_admission_faq
```

## Problem 3: Retrieval Was Weak Without a Real Embedding Model

### Symptom

Before FastEmbed was installed, the fallback hash embedding could retrieve a related but wrong chunk. For example, a question about transfer conditions could initially retrieve content about the competency assessment exam.

### Root Cause

Hash embeddings are useful for offline tests because they are deterministic and require no model download, but they do not understand Vietnamese semantics deeply. They can confuse chunks when several sections share common admission words.

### Solution

The JSON fallback retrieval now combines two signals:

- A deterministic embedding similarity score.
- A lexical overlap score based on important query terms.

This is still simple, but it makes the offline MVP much more stable for FAQ-style questions. For example:

```text
Question: Điều kiện chuyển ngành ở UIT là gì?
Top chunk: a) Chuyển ngành ...
```

The system also includes basic grounding checks for questions that are likely out of scope, such as `ngành Y` or `học bổng`, so it can return the fallback message instead of answering from a weakly related chunk.

## Problem 4: The RAG Service Needed to Avoid Breaking the Existing Orchestrator

### Symptom

The project already had a lightweight `services/rag/service.py` used by:

```text
services/orchestrator/main.py
```

Replacing the RAG service structure could have broken the orchestrator import:

```python
from services.rag.service import RagService, RetrievedChunk
```

### Root Cause

The new RAG service was designed as its own FastAPI app under `services/rag/app/`, while the existing orchestrator expected the older Python facade.

### Solution

A compatibility facade was kept in:

```text
services/rag/service.py
```

It wraps the new chunker, vector store, and RAG engine while preserving the old class names used by the orchestrator:

- `RagService`
- `RetrievedChunk`
- `IngestResult`

This allows two integration modes:

- The orchestrator can continue importing `RagService`.
- Other services can call the standalone RAG API:

```text
POST http://localhost:8003/ask
```

## Problem 5: Network Access Is Required Only for Crawling and Installing Packages

### Symptom

The crawler failed when the environment could not resolve the UIT domain:

```text
Failed to resolve 'tuyensinh.uit.edu.vn'
```

### Root Cause

The crawler fetches public website content using `requests`, so it needs internet access at crawl time. After the page is saved as Markdown and indexed, asking questions can work offline in local extractive mode.

### Solution

The pipeline separates crawl time from runtime:

```text
crawl once -> save raw HTML and Markdown -> ingest -> run local retrieval
```

If the robot is deployed in a place with unreliable network, the team can crawl and ingest on a laptop first, then copy the `knowledge_base/` folder to the Raspberry Pi.

## Verification

The current RAG implementation was checked with:

```bash
cd services/rag
python scripts/crawl_sources.py
python scripts/ingest_documents.py
python scripts/evaluate_rag.py
pytest tests
```

Expected ingestion summary:

```text
Loaded documents: 1
Created chunks: 13
Indexed source: uit_admission_faq
Vector index saved to: services/rag/knowledge_base/index
```

The test suite covers:

- Cleaner removes scripts and styles.
- Chunker creates non-empty chunks with metadata.
- Vector store can add and retrieve chunks.
- RAG engine returns the fallback message when no relevant context is found.

## Current Tradeoffs

The current implementation is intentionally MVP-oriented:

- It is not a general website crawler.
- It only crawls configured source URLs.
- It prioritizes readable Markdown and simple scripts over complex indexing infrastructure.
- FastEmbed gives better semantic retrieval than the hash fallback while staying practical on Raspberry Pi 5.
- The local answer composer is more stable for Raspberry Pi demos than an external LLM dependency, but it is intentionally simpler than full natural-language generation.

## Recommended Next Steps

Good next improvements are:

- Add more UIT admission source URLs to `sources.yaml`.
- Improve page-specific cleaning for tuition tables and contact sections.
- Add source freshness metadata and a scheduled recrawl command.
- Add a small manual evaluation report with expected answers.
- Add a small cache/warm-up step so the FastEmbed model is downloaded before demo day.
