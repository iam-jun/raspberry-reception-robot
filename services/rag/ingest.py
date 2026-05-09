#!/usr/bin/env python3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = REPO_ROOT / "documents" / "source"
VECTOR_DB_DIR = REPO_ROOT / "storage" / "vector_db"


def main() -> None:
    print(f"Preparing to ingest documents from: {DOCUMENTS_DIR}")
    print(f"Vector index output directory: {VECTOR_DB_DIR}")
    # TODO: Add document loading and chunking.
    # TODO: Add embedding model integration.
    # TODO: Add vector store creation/update.


if __name__ == "__main__":
    main()

