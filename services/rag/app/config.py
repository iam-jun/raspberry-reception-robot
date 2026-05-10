from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


RAG_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_DIR = RAG_ROOT / "knowledge_base"
SOURCES_PATH = KNOWLEDGE_BASE_DIR / "sources.yaml"
RAW_HTML_DIR = KNOWLEDGE_BASE_DIR / "raw_html"
MARKDOWN_DIR = KNOWLEDGE_BASE_DIR / "markdown"
INDEX_DIR = KNOWLEDGE_BASE_DIR / "index"


@dataclass(frozen=True)
class RagSettings:
    embedding_model: str = os.getenv(
        "RAG_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    min_relevance_score: float = float(os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.15"))


def ensure_directories() -> None:
    for path in (RAW_HTML_DIR, MARKDOWN_DIR, INDEX_DIR):
        path.mkdir(parents=True, exist_ok=True)
