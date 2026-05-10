#!/usr/bin/env python3
from __future__ import annotations

import sys
import time
from pathlib import Path

RAG_ROOT = Path(__file__).resolve().parents[1]
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from app.rag_engine import RagEngine  # noqa: E402


QUESTIONS = [
    "UIT là trường công lập hay dân lập?",
    "Sinh viên UIT học ở cơ sở nào?",
    "Điều kiện chuyển ngành ở UIT là gì?",
    "UIT có cho học song bằng không?",
    "Mã trường UIT là gì?",
    "Học phí chương trình chính quy năm 2025-2026 là bao nhiêu?",
    "Ký túc xá cách trường bao xa?",
    "Có những tuyến xe bus nào đến ĐHQG-HCM?",
    "UIT có đào tạo ngành Y không?",
    "Tôi muốn hỏi thông tin học bổng mới nhất thì liên hệ ở đâu?",
]


def main() -> None:
    engine = RagEngine()
    for i, question in enumerate(QUESTIONS, start=1):
        started = time.perf_counter()
        result = engine.answer_question(question, top_k=5)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        chunks = result["chunks"]
        top = chunks[0] if chunks else {}
        meta = top.get("metadata", {})
        print("=" * 80)
        print(f"Case: {i}")
        print(f"Question: {question}")
        print(f"Top retrieved source/chunk: {meta.get('source_id', 'N/A')} / {top.get('chunk_id', 'N/A')}")
        print(f"Source found: {bool(chunks)}")
        print(f"Response time ms: {elapsed_ms}")
        print("Generated answer:")
        print(result["answer"])


if __name__ == "__main__":
    main()

