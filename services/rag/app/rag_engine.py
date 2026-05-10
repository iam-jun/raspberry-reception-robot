from __future__ import annotations

import os
from typing import Any

from .config import RagSettings
from .vector_store import VectorStore


FALLBACK_MESSAGE = (
    "Hiện tại em chưa tìm thấy thông tin này trong tài liệu đã được nạp. "
    "Anh/chị vui lòng liên hệ bộ phận tuyển sinh UIT để được hỗ trợ chính xác hơn."
)

SYSTEM_PROMPT = f"""You are a Smart Reception Robot for UIT admission information.
Only answer using the provided CONTEXT.
If the context does not contain the answer, say in Vietnamese:
"{FALLBACK_MESSAGE}"
Do not fabricate information.
Answer politely, clearly, and concisely in Vietnamese.
At the end, include the source name if available."""


class RagEngine:
    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self.vector_store = vector_store or VectorStore()
        self.settings = RagSettings()

    def retrieve(self, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.vector_store.query(question, top_k=top_k)

    def answer_question(self, question: str, top_k: int = 5) -> dict[str, Any]:
        chunks = self.retrieve(question, top_k=top_k)
        relevant_chunks = [chunk for chunk in chunks if float(chunk.get("score", 0.0)) >= self.settings.min_relevance_score]
        if not relevant_chunks:
            return {"answer": FALLBACK_MESSAGE, "chunks": chunks}
        if not _context_seems_grounded(question, relevant_chunks[0].get("text", "")):
            return {"answer": FALLBACK_MESSAGE, "chunks": chunks}

        if os.getenv("OPENAI_API_KEY"):
            try:
                return {"answer": self._answer_with_openai(question, relevant_chunks), "chunks": relevant_chunks}
            except Exception:
                pass
        return {"answer": self._answer_extractive(relevant_chunks), "chunks": relevant_chunks}

    def _answer_extractive(self, chunks: list[dict[str, Any]]) -> str:
        best = chunks[0]
        text = best.get("text", "").strip()
        metadata = best.get("metadata", {})
        source_name = metadata.get("title") or metadata.get("source_id") or "tài liệu UIT"
        sentences = _first_useful_lines(text, limit=5)
        if not sentences:
            return FALLBACK_MESSAGE
        answer = "\n".join(sentences)
        return f"{answer}\n\nNguồn: {source_name}"

    def _answer_with_openai(self, question: str, chunks: list[dict[str, Any]]) -> str:
        from openai import OpenAI

        context = "\n\n".join(
            f"[{chunk['metadata'].get('title') or chunk['metadata'].get('source_id')} | {chunk['chunk_id']}]\n{chunk['text']}"
            for chunk in chunks
        )
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION:\n{question}"},
            ],
        )
        return (response.choices[0].message.content or "").strip() or FALLBACK_MESSAGE


def _first_useful_lines(text: str, limit: int) -> list[str]:
    lines = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("---"):
            continue
        lines.append(clean)
        if len(lines) >= limit:
            break
    return lines


def _context_seems_grounded(question: str, best_text: str) -> bool:
    question_lower = question.lower()
    text_lower = best_text.lower()
    required_phrases = []
    for phrase in ("học bổng", "ngành y"):
        if phrase in question_lower:
            required_phrases.append(phrase)
    return all(phrase in text_lower for phrase in required_phrases)
