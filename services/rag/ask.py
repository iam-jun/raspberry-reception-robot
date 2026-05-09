#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.rag.service import RagService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask the RAG service a question.")
    parser.add_argument("--question", required=True, help="Question to answer.")
    parser.add_argument("--top-k", type=int, default=4, help="Number of chunks to retrieve.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = RagService()
    contexts = service.retrieve(args.question, top_k=args.top_k)
    answer = service.generate_answer(args.question, contexts)
    print(
        json.dumps(
            {
                "question": args.question,
                "answer": answer,
                "sources": [context.__dict__ for context in contexts],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
