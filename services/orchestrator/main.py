from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from services.rag.service import RagService, RetrievedChunk
from services.stt.wrapper import SttService
from services.tts.service import TtsService
from services.vision.service import VisionService


REPO_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = REPO_ROOT / "apps" / "ui"

if load_dotenv is not None:
    load_dotenv(REPO_ROOT / ".env")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class SourceSnippet(BaseModel):
    filename: str
    chunk_index: int
    text: str
    score: float


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceSnippet]
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None
    tts_skipped_reason: Optional[str] = None
    tts_error: Optional[str] = None
    emotion: Optional[dict[str, Any]] = None
    processing_time_seconds: float


class VoiceAskResponse(AskResponse):
    transcription: str
    recorded_audio_path: Optional[str] = None


app = FastAPI(title="Smart Reception Orchestrator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_service = RagService()
tts_service = TtsService()
stt_service = SttService()
vision_service = VisionService()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "orchestrator": {
            "status": "ok",
            "host": os.getenv("ORCHESTRATOR_HOST", "0.0.0.0"),
            "port": int(os.getenv("ORCHESTRATOR_PORT", "8000")),
        },
        "stt": _safe_health(stt_service),
        "rag": _safe_health(rag_service),
        "tts": _safe_health(tts_service),
        "vision": _safe_health(vision_service),
    }


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    return _ask_pipeline(request.question, emotion=vision_service.latest_result())


@app.post("/voice/ask", response_model=VoiceAskResponse)
async def voice_ask(request: Request, duration_seconds: int = 5) -> VoiceAskResponse:
    started = time.perf_counter()
    emotion = vision_service.capture_once()
    audio_path: str | None = None

    try:
        audio_path = await _get_voice_audio(request, duration_seconds)
        transcription = stt_service.transcribe_wav(audio_path)
        emotion = vision_service.capture_once()
        response = _ask_pipeline(transcription, emotion=emotion, started_at=started)
        payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        return VoiceAskResponse(**payload, transcription=transcription, recorded_audio_path=audio_path)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    session = None
    try:
        session = await stt_service.start_streaming()
        
        async def read_from_stt() -> None:
            assert session is not None
            while True:
                line = await session.read_line()
                if not line:
                    break
                if line.startswith("partial: ") or line.startswith("final: "):
                    parts = line.split(": ", 1)
                    event_type = parts[0]
                    text = parts[1] if len(parts) > 1 else ""
                    try:
                        await websocket.send_json({"type": event_type, "text": text})
                    except Exception:
                        break

        stt_reader_task = asyncio.create_task(read_from_stt())

        try:
            while True:
                data = await websocket.receive_text()
                if data == "stop":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await stt_reader_task
    except Exception as error:
        try:
            await websocket.send_json({"type": "error", "error": str(error)})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if session:
            await session.close()


@app.post("/documents/ingest")
def ingest_documents() -> dict[str, Any]:
    try:
        return rag_service.ingest_documents().__dict__
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/documents")
def documents() -> dict[str, Any]:
    return {
        "documents": rag_service.list_documents(),
        "ingestion": rag_service.health(),
    }


@app.get("/audio/{filename}")
def audio(filename: str) -> FileResponse:
    audio_dir = tts_service.audio_output_dir.resolve()
    path = (audio_dir / filename).resolve()
    if path.parent != audio_dir:
        raise HTTPException(status_code=400, detail="Invalid audio filename.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return FileResponse(path)


@app.get("/vision/emotion")
def vision_emotion(sample: bool = True) -> dict[str, Any]:
    return vision_service.capture_once() if sample else vision_service.latest_result()


def _ask_pipeline(question: str, emotion: dict[str, Any] | None, started_at: float | None = None) -> AskResponse:
    started = started_at or time.perf_counter()
    clean_question = question.strip()
    if not clean_question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    try:
        contexts = rag_service.retrieve(clean_question, top_k=4)
        answer = rag_service.generate_answer(clean_question, contexts)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"RAG answer generation failed: {error}") from error

    audio_path: str | None = None
    audio_url: str | None = None
    tts_skipped_reason: str | None = None
    tts_error: str | None = None
    try:
        tts_result = tts_service.synthesize(answer)
        audio_path = tts_result.audio_path
        audio_url = tts_result.audio_url
        tts_skipped_reason = tts_result.skipped_reason
    except Exception as error:
        tts_error = str(error)

    return AskResponse(
        question=clean_question,
        answer=answer,
        sources=[_source_from_context(context) for context in contexts],
        audio_path=audio_path,
        audio_url=audio_url,
        tts_skipped_reason=tts_skipped_reason,
        tts_error=tts_error,
        emotion=emotion,
        processing_time_seconds=round(time.perf_counter() - started, 3),
    )


async def _get_voice_audio(request: Request, duration_seconds: int) -> str:
    content_type = request.headers.get("content-type", "")
    audio_dir = tts_service.audio_output_dir
    audio_dir.mkdir(parents=True, exist_ok=True)
    upload_path = audio_dir / f"uploaded_question_{int(time.time())}.wav"

    if "multipart/form-data" in content_type:
        form = await request.form()
        if "duration_seconds" in form:
            duration_seconds = int(str(form["duration_seconds"]))
        upload = form.get("file") or form.get("audio")
        if upload is not None and hasattr(upload, "read"):
            data = await upload.read()
            upload_path.write_bytes(data)
            return str(upload_path)

    if content_type.startswith("audio/") or content_type in {"application/octet-stream", "application/wav"}:
        data = await request.body()
        if data:
            upload_path.write_bytes(data)
            return str(upload_path)

    return stt_service.record_audio(duration_seconds=duration_seconds)


def _source_from_context(context: RetrievedChunk) -> SourceSnippet:
    return SourceSnippet(
        filename=context.filename,
        chunk_index=context.chunk_index,
        text=context.text,
        score=context.score,
    )


def _safe_health(service: Any) -> dict[str, Any]:
    try:
        return service.health()
    except Exception as error:
        return {"status": "error", "error": str(error)}


if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
