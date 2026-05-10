from __future__ import annotations

from pathlib import Path

from app.chunker import Chunk
from app.rag_engine import FALLBACK_MESSAGE, RagEngine
from app.vector_store import VectorStore


class FakeEmbeddings:
    model_name = "fake"

    def embed_text(self, text: str) -> list[float]:
        return [1.0, 0.0] if "uit" in text.lower() else [0.0, 1.0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


def test_vector_store_can_add_and_retrieve_chunks(tmp_path: Path) -> None:
    store = VectorStore(index_dir=tmp_path, embedding_provider=FakeEmbeddings())
    store.reset_index()
    store.add_chunks(
        [
            Chunk(
                chunk_id="uit-0",
                text="UIT là trường đại học công lập.",
                metadata={
                    "source_id": "uit_admission_faq",
                    "source_url": "https://example.test",
                    "title": "FAQ",
                    "domain": "UIT tuyển sinh",
                    "language": "vi",
                    "chunk_index": 0,
                },
            )
        ]
    )

    rows = store.query("UIT là trường gì?", top_k=1)

    assert rows
    assert rows[0]["chunk_id"] == "uit-0"
    assert rows[0]["metadata"]["source_id"] == "uit_admission_faq"


def test_rag_engine_returns_fallback_when_no_relevant_context(tmp_path: Path) -> None:
    store = VectorStore(index_dir=tmp_path, embedding_provider=FakeEmbeddings())
    store.reset_index()
    engine = RagEngine(vector_store=store)

    result = engine.answer_question("UIT có đào tạo ngành Y không?", top_k=3)

    assert result["answer"] == FALLBACK_MESSAGE

