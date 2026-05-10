from __future__ import annotations

from typing import Any

from .answer_composer import FALLBACK_MESSAGE, LocalAnswerComposer
from .vector_store import VectorStore


class RagEngine:
    def __init__(
        self,
        vector_store: VectorStore | None = None,
        answer_composer: LocalAnswerComposer | None = None,
    ) -> None:
        self.vector_store = vector_store or VectorStore()
        self.answer_composer = answer_composer or LocalAnswerComposer()

    def retrieve(self, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.vector_store.query(question, top_k=top_k)

    def answer_question(self, question: str, top_k: int = 5) -> dict[str, Any]:
        chunks = self.retrieve(question, top_k=top_k)
        composed = self.answer_composer.compose_answer(
            question=question,
            retrieved_chunks=chunks,
            min_score=None,
        )
        return {
            "answer": composed["answer"],
            "confidence": composed["confidence"],
            "chunks": composed["used_chunks"],
            "retrieved_chunks": chunks,
        }
