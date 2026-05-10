#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

RAG_ROOT = Path(__file__).resolve().parents[1]
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from app.crawler import crawl_enabled_sources  # noqa: E402


def main() -> None:
    results = crawl_enabled_sources()
    print(f"Crawled sources: {len(results)}")
    for result in results:
        print(f"- {result['source_id']}: {result['markdown_path']}")


if __name__ == "__main__":
    main()

