from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class SourcePreview(BaseModel):
    source_id: str
    title: str | None = None
    source_url: str | None = None
    chunk_id: str
    score: float
    preview: str


class AskResponse(BaseModel):
    question: str
    answer: str
    confidence: str
    sources: list[SourcePreview]


class RetrieveResponse(BaseModel):
    question: str
    chunks: list[dict[str, Any]]
