from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="Smart Reception Orchestrator")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    answer: str
    audio_path: Optional[str] = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    # TODO: Call STT service or CLI when request input is audio.
    # TODO: Call RAG service to retrieve context and generate the answer.
    # TODO: Call TTS service to synthesize the answer to audio.
    # TODO: Add error handling and timeouts around service calls.
    return AskResponse(
        question=request.question,
        answer="This is a placeholder answer from orchestrator.",
        audio_path=None,
    )

