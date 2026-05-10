from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .app.chunker import chunk_markdown, parse_frontmatter
from .app.config import INDEX_DIR, MARKDOWN_DIR, SOURCES_PATH
from .app.crawler import load_sources
from .app.rag_engine import RagEngine
from .app.vector_store import VectorStore


@dataclass
class RetrievedChunk:
    filename: str
    chunk_index: int
    text: str
    score: float


@dataclass
class IngestResult:
    documents_processed: int
    chunks_processed: int
    vector_dir: str
    embedding_provider: str
    indexed_at: str


class RagService:
    """Compatibility facade used by the existing orchestrator service."""

    def __init__(self) -> None:
        self.store = VectorStore()
        self.engine = RagEngine(self.store)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "document_source_dir": str(MARKDOWN_DIR),
            "vector_dir": str(INDEX_DIR),
            "documents": len(self.list_documents()),
            "vector_backend": "fastembed_json",
        }

    def list_documents(self) -> list[dict[str, Any]]:
        docs = []
        for path in sorted(MARKDOWN_DIR.glob("*.md")):
            metadata, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
            docs.append(
                {
                    "filename": path.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "indexed": any(INDEX_DIR.iterdir()) if INDEX_DIR.exists() else False,
                    "source_id": metadata.get("source_id", path.stem),
                }
            )
        return docs

    def ingest_documents(self) -> IngestResult:
        chunks = []
        source_ids = set()
        for path in sorted(MARKDOWN_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            metadata, _ = parse_frontmatter(text)
            source_ids.add(metadata.get("source_id", path.stem))
            chunks.extend(chunk_markdown(text))
        self.store.reset_index()
        self.store.add_chunks(chunks)
        return IngestResult(
            documents_processed=len(source_ids),
            chunks_processed=len(chunks),
            vector_dir=str(INDEX_DIR),
            embedding_provider=self.store.embedding_provider.model_name,
            indexed_at=datetime.now(timezone.utc).isoformat(),
        )

    def retrieve(self, question: str, top_k: int = 4) -> list[RetrievedChunk]:
        rows = self.engine.retrieve(question, top_k=top_k)
        contexts = []
        for row in rows:
            metadata = row.get("metadata", {})
            filename = f"{metadata.get('source_id', 'unknown')}.md"
            contexts.append(
                RetrievedChunk(
                    filename=filename,
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    text=row.get("text", ""),
                    score=float(row.get("score", 0.0)),
                )
            )
        return contexts

    def generate_answer(self, question: str, contexts: list[RetrievedChunk] | None = None) -> str:
        result = self.engine.answer_question(question, top_k=len(contexts or []) or 4)
        return result["answer"]

    def configured_sources(self) -> list[dict[str, Any]]:
        return [source.__dict__ for source in load_sources(SOURCES_PATH, enabled_only=False)]
