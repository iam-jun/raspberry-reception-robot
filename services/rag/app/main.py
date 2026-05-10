from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from .config import MARKDOWN_DIR, SOURCES_PATH, INDEX_DIR
from .crawler import load_sources
from .rag_engine import RagEngine
from .schemas import AskRequest, AskResponse, RetrieveRequest, RetrieveResponse, SourcePreview


app = FastAPI(title="Smart Reception RAG Service", version="0.1.0")
engine = RagEngine()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rag"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    result = engine.answer_question(question, top_k=request.top_k)
    return AskResponse(
        question=question,
        answer=result["answer"],
        confidence=result["confidence"],
        sources=[_source_preview(chunk) for chunk in result["chunks"]],
    )


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: RetrieveRequest) -> RetrieveResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    return RetrieveResponse(question=question, chunks=engine.retrieve(question, top_k=request.top_k))


@app.get("/sources")
def sources() -> dict[str, Any]:
    configured = []
    for source in load_sources(SOURCES_PATH, enabled_only=False):
        markdown_path = MARKDOWN_DIR / f"{source.id}.md"
        configured.append(
            {
                "id": source.id,
                "name": source.name,
                "url": source.url,
                "enabled": source.enabled,
                "markdown_exists": markdown_path.exists(),
                "markdown_path": str(markdown_path),
                "index_exists": any(INDEX_DIR.iterdir()) if INDEX_DIR.exists() else False,
            }
        )
    return {"sources": configured}


def _source_preview(chunk: dict[str, Any]) -> SourcePreview:
    metadata = chunk.get("metadata", {})
    text = chunk.get("relevant_preview") or chunk.get("text", "")
    preview = " ".join(str(text).split())
    if len(preview) > 180:
        preview = preview[:180].rsplit(" ", 1)[0].rstrip(".,;") + "..."
    return SourcePreview(
        source_id=metadata.get("source_id", ""),
        title=metadata.get("title"),
        source_url=metadata.get("source_url"),
        chunk_id=chunk.get("chunk_id", ""),
        score=float(chunk.get("score", 0.0)),
        preview=preview,
    )
