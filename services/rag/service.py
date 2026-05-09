from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency may not be installed yet
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOCUMENT_SOURCE_DIR = REPO_ROOT / "documents" / "source"
DEFAULT_VECTOR_DIR = REPO_ROOT / "storage" / "vector_db"


@dataclass
class DocumentChunk:
    id: str
    filename: str
    path: str
    chunk_index: int
    text: str


@dataclass
class RetrievedChunk:
    filename: str
    chunk_index: int
    text: str
    score: float


@dataclass
class IngestResult:
    documents_processed: int
    chunks_processed: int
    vector_dir: str
    embedding_provider: str
    indexed_at: str


class RagService:
    def __init__(
        self,
        document_source_dir: str | Path | None = None,
        vector_dir: str | Path | None = None,
    ) -> None:
        if load_dotenv is not None:
            load_dotenv(REPO_ROOT / ".env")

        self.document_source_dir = self._resolve_path(
            document_source_dir or os.getenv("DOCUMENT_SOURCE_DIR") or DEFAULT_DOCUMENT_SOURCE_DIR
        )
        self.vector_dir = self._resolve_path(os.getenv("RAG_VECTOR_DIR") or vector_dir or DEFAULT_VECTOR_DIR)
        self.vector_dir.mkdir(parents=True, exist_ok=True)

        self.chat_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.collection_name = "smart_reception_documents"

    def health(self) -> dict[str, Any]:
        manifest = self._read_manifest()
        return {
            "status": "ok",
            "document_source_dir": str(self.document_source_dir),
            "vector_dir": str(self.vector_dir),
            "documents": len(self.list_documents()),
            "chunks_indexed": manifest.get("chunks_processed", 0),
            "embedding_provider": manifest.get("embedding_provider"),
            "last_ingested_at": manifest.get("indexed_at"),
            "openai_configured": bool(self.openai_api_key),
            "vector_backend": self._preferred_backend_name(),
        }

    def list_documents(self) -> list[dict[str, Any]]:
        self.document_source_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._read_manifest()
        indexed_files = set(manifest.get("filenames", []))
        docs: list[dict[str, Any]] = []
        for path in sorted(self.document_source_dir.iterdir()):
            if path.name.startswith(".") or not path.is_file():
                continue
            if path.suffix.lower() not in {".txt", ".md", ".pdf"}:
                continue
            docs.append(
                {
                    "filename": path.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    "indexed": path.name in indexed_files,
                }
            )
        return docs

    def ingest_documents(self) -> IngestResult:
        chunks = self._load_chunks()
        embeddings = self._embed_many([chunk.text for chunk in chunks]) if chunks else []
        provider = self._embedding_provider()

        self._clear_chroma_collection()
        if chunks:
            if self._use_chroma():
                self._write_chroma(chunks, embeddings)
            self._write_fallback_index(chunks, embeddings)

        filenames = sorted({chunk.filename for chunk in chunks})
        result = IngestResult(
            documents_processed=len(filenames),
            chunks_processed=len(chunks),
            vector_dir=str(self.vector_dir),
            embedding_provider=provider,
            indexed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._write_manifest(result, filenames)
        return result

    def retrieve(self, question: str, top_k: int = 4) -> list[RetrievedChunk]:
        question = question.strip()
        if not question:
            return []

        query_embedding = self._embed_one(question)
        if self._use_chroma() and self._chroma_has_data():
            try:
                return self._retrieve_chroma(query_embedding, top_k)
            except Exception:
                # Fall back to the plain persisted index. The orchestrator should
                # keep answering if Chroma metadata becomes temporarily unhappy.
                pass
        return self._retrieve_fallback(query_embedding, top_k)

    def generate_answer(self, question: str, contexts: list[RetrievedChunk]) -> str:
        if not self.openai_api_key:
            if contexts:
                return (
                    "OPENAI_API_KEY is not configured, so I cannot generate the final answer yet. "
                    "Relevant document context was retrieved successfully."
                )
            return "OPENAI_API_KEY is not configured, and no document context is available yet."

        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("The openai package is not installed. Run pip install -r requirements.txt.") from error

        context_text = "\n\n".join(
            f"[{item.filename} #{item.chunk_index}]\n{item.text}" for item in contexts
        )
        if not context_text:
            context_text = "No relevant document snippets were retrieved."

        system_prompt = (
            "You are a polite touch-screen reception robot. Answer concisely and warmly. "
            "Use Vietnamese when the visitor asks in Vietnamese; use English when they ask in English. "
            "Base the answer on the provided document context when possible. "
            "If the answer is not in the documents, say the system does not have enough information."
        )
        user_prompt = f"Document context:\n{context_text}\n\nVisitor question:\n{question}"

        client = OpenAI(api_key=self.openai_api_key)
        response = client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        answer = response.choices[0].message.content or ""
        return answer.strip()

    def _load_chunks(self) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        self.document_source_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.document_source_dir.iterdir()):
            if path.name.startswith(".") or not path.is_file():
                continue
            text = self._read_document(path)
            if not text:
                continue
            for index, chunk_text in enumerate(self._chunk_text(text)):
                digest = hashlib.sha1(f"{path.name}:{index}:{chunk_text}".encode("utf-8")).hexdigest()[:16]
                chunks.append(
                    DocumentChunk(
                        id=f"{path.stem}-{index}-{digest}",
                        filename=path.name,
                        path=str(path),
                        chunk_index=index,
                        text=chunk_text,
                    )
                )
        return chunks

    def _read_document(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="ignore").strip()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as error:
                raise RuntimeError("PDF ingestion requires pypdf. Run pip install -r requirements.txt.") from error
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        return ""

    def _chunk_text(self, text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
        normalized = "\n".join(line.strip() for line in text.splitlines())
        normalized = "\n".join(part for part in normalized.splitlines() if part)
        if len(normalized) <= chunk_size:
            return [normalized] if normalized else []

        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + chunk_size, len(normalized))
            if end < len(normalized):
                paragraph_break = normalized.rfind("\n", start, end)
                sentence_break = max(normalized.rfind(". ", start, end), normalized.rfind("? ", start, end))
                split_at = paragraph_break if paragraph_break > start + 400 else sentence_break
                if split_at > start + 400:
                    end = split_at + 1
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(normalized):
                break
            start = max(0, end - overlap)
        return chunks

    def _embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.openai_api_key:
            return [self._hash_embedding(text) for text in texts]
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("The openai package is not installed. Run pip install -r requirements.txt.") from error

        client = OpenAI(api_key=self.openai_api_key)
        embeddings: list[list[float]] = []
        batch_size = 64
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            response = client.embeddings.create(model=self.embedding_model, input=batch)
            embeddings.extend([item.embedding for item in response.data])
        return embeddings

    def _embed_one(self, text: str) -> list[float]:
        return self._embed_many([text])[0]

    def _embedding_provider(self) -> str:
        return f"openai:{self.embedding_model}" if self.openai_api_key else "local-hash-fallback"

    def _hash_embedding(self, text: str, dimensions: int = 384) -> list[float]:
        vector = [0.0] * dimensions
        tokens = [token for token in text.lower().replace("/", " ").split() if token]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    def _use_chroma(self) -> bool:
        try:
            import chromadb  # noqa: F401
        except ImportError:
            return False
        return True

    def _preferred_backend_name(self) -> str:
        return "chromadb" if self._use_chroma() else "json-fallback"

    def _chroma_client(self) -> Any:
        import chromadb

        return chromadb.PersistentClient(path=str(self.vector_dir / "chroma"))

    def _clear_chroma_collection(self) -> None:
        if not self._use_chroma():
            return
        client = self._chroma_client()
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass

    def _write_chroma(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        client = self._chroma_client()
        collection = client.get_or_create_collection(self.collection_name)
        collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {"filename": chunk.filename, "path": chunk.path, "chunk_index": chunk.chunk_index}
                for chunk in chunks
            ],
            embeddings=embeddings,
        )

    def _chroma_has_data(self) -> bool:
        try:
            collection = self._chroma_client().get_collection(self.collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def _retrieve_chroma(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        collection = self._chroma_client().get_collection(self.collection_name)
        result = collection.query(query_embeddings=[query_embedding], n_results=top_k)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        retrieved: list[RetrievedChunk] = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            retrieved.append(
                RetrievedChunk(
                    filename=str(metadata.get("filename", "unknown")),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    text=str(text),
                    score=max(0.0, 1.0 - float(distance)),
                )
            )
        return retrieved

    def _write_fallback_index(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        index_path = self.vector_dir / "chunks.json"
        vector_path = self.vector_dir / "vectors.json"
        index_path.write_text(json.dumps([asdict(chunk) for chunk in chunks], ensure_ascii=False, indent=2), encoding="utf-8")
        vector_path.write_text(json.dumps(embeddings), encoding="utf-8")

    def _retrieve_fallback(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        index_path = self.vector_dir / "chunks.json"
        vector_path = self.vector_dir / "vectors.json"
        if not index_path.exists() or not vector_path.exists():
            return []

        chunks_data = json.loads(index_path.read_text(encoding="utf-8"))
        vectors = json.loads(vector_path.read_text(encoding="utf-8"))
        if not vectors:
            return []

        scores = [self._cosine_similarity(vector, query_embedding) for vector in vectors]
        top_indices = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)[:top_k]

        retrieved: list[RetrievedChunk] = []
        for index in top_indices:
            data = chunks_data[int(index)]
            score = float(scores[int(index)])
            if math.isnan(score):
                score = 0.0
            retrieved.append(
                RetrievedChunk(
                    filename=data["filename"],
                    chunk_index=int(data["chunk_index"]),
                    text=data["text"],
                    score=score,
                )
            )
        return retrieved

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        length = min(len(left), len(right))
        if length == 0:
            return 0.0
        dot = sum(left[index] * right[index] for index in range(length))
        left_norm = math.sqrt(sum(value * value for value in left[:length]))
        right_norm = math.sqrt(sum(value * value for value in right[:length]))
        denominator = left_norm * right_norm
        if denominator <= 1e-8:
            return 0.0
        return dot / denominator

    def _read_manifest(self) -> dict[str, Any]:
        path = self.vector_dir / "manifest.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write_manifest(self, result: IngestResult, filenames: list[str]) -> None:
        data = asdict(result)
        data["filenames"] = filenames
        (self.vector_dir / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return candidate.resolve()
