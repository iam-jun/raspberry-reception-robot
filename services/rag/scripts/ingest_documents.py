#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

RAG_ROOT = Path(__file__).resolve().parents[1]
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from app.chunker import chunk_markdown, parse_frontmatter  # noqa: E402
from app.config import INDEX_DIR, MARKDOWN_DIR  # noqa: E402
from app.vector_store import VectorStore  # noqa: E402


def main() -> None:
    documents = []
    chunks = []
    for path in sorted(MARKDOWN_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata, _ = parse_frontmatter(text)
        documents.append(metadata.get("source_id", path.stem))
        chunks.extend(chunk_markdown(text))

    store = VectorStore()
    store.reset_index()
    store.add_chunks(chunks)

    print(f"Loaded documents: {len(documents)}")
    print(f"Created chunks: {len(chunks)}")
    for source_id in sorted(set(documents)):
        print(f"Indexed source: {source_id}")
    print(f"Vector index saved to: {INDEX_DIR}")


if __name__ == "__main__":
    main()

