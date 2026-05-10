from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import Any

from .chunker import Chunk
from .config import INDEX_DIR, ensure_directories
from .embeddings import EmbeddingProvider


class VectorStore:
    def __init__(
        self,
        index_dir: Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        ensure_directories()
        self.index_dir = index_dir or INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_provider = embedding_provider or EmbeddingProvider()
        self.fallback_path = self.index_dir / "fallback_index.json"

    def reset_index(self) -> None:
        if self.index_dir.exists():
            for child in self.index_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_provider.embed_texts(texts)
        self._write_fallback(chunks, embeddings)

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        query_text = query_text.strip()
        if not query_text:
            return []
        query_embedding = self.embedding_provider.embed_text(query_text)
        return self._query_fallback(query_text, query_embedding, top_k)

    def _write_fallback(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        rows = []
        for chunk, embedding in zip(chunks, embeddings):
            rows.append(
                {
                    "id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                    "embedding": embedding,
                }
            )
        self.fallback_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def _query_fallback(self, query_text: str, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        if not self.fallback_path.exists():
            return []
        rows = json.loads(self.fallback_path.read_text(encoding="utf-8"))
        scored = []
        for row in rows:
            semantic_similarity = _cosine_similarity(query_embedding, row["embedding"])
            lexical_similarity = _lexical_overlap(query_text, row["text"])
            similarity = (0.15 * semantic_similarity) + (0.85 * lexical_similarity)
            scored.append(
                {
                    "chunk_id": row["id"],
                    "text": row["text"],
                    "metadata": row["metadata"],
                    "score": round(float(similarity), 6),
                    "distance": round(float(1 - similarity), 6),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]


def reset_index() -> None:
    VectorStore().reset_index()


def add_chunks(chunks: list[Chunk]) -> None:
    VectorStore().add_chunks(chunks)


def query(query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
    return VectorStore().query(query_text, top_k=top_k)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)


def _lexical_overlap(query_text: str, document_text: str) -> float:
    query_terms = _terms(query_text)
    if not query_terms:
        return 0.0
    document_terms = _terms(document_text)
    if not document_terms:
        return 0.0
    matches = sum(1 for term in query_terms if term in document_terms)
    phrase_bonus = 0.2 if query_text.lower().strip("? ") in document_text.lower() else 0.0
    return min(1.0, (matches / len(query_terms)) + phrase_bonus)


def _terms(text: str) -> set[str]:
    import re

    stopwords = {
        "là",
        "có",
        "ở",
        "gì",
        "của",
        "và",
        "cho",
        "được",
        "không",
        "trong",
        "nào",
        "bao",
        "nhiêu",
        "tôi",
        "muốn",
        "hỏi",
        "uit",
        "trường",
        "thông",
        "tin",
        "mới",
        "nhất",
        "đâu",
    }
    words = re.findall(r"[\wÀ-ỹ]+", text.lower(), flags=re.UNICODE)
    return {word for word in words if (len(word) > 1 or word == "y") and word not in stopwords}
