from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIO_DIR = REPO_ROOT / "storage" / "audio"


@dataclass
class TtsResult:
    audio_path: str | None
    audio_url: str | None
    skipped_reason: str | None = None


class TtsService:
    def __init__(self, audio_output_dir: str | Path | None = None) -> None:
        if load_dotenv is not None:
            load_dotenv(REPO_ROOT / ".env")

        self.audio_output_dir = self._resolve_path(
            audio_output_dir or os.getenv("AUDIO_OUTPUT_DIR") or DEFAULT_AUDIO_DIR
        )
        self.audio_output_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
        self.voice = os.getenv("OPENAI_TTS_VOICE", "coral")

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.api_key else "degraded",
            "openai_configured": bool(self.api_key),
            "model": self.model,
            "voice": self.voice,
            "audio_output_dir": str(self.audio_output_dir),
        }

    def synthesize(self, text: str) -> TtsResult:
        text = text.strip()
        if not text:
            return TtsResult(audio_path=None, audio_url=None, skipped_reason="No text was provided for TTS.")
        if not self.api_key:
            return TtsResult(
                audio_path=None,
                audio_url=None,
                skipped_reason="OPENAI_API_KEY is not configured; skipping TTS generation.",
            )

        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("The openai package is not installed. Run pip install -r requirements.txt.") from error

        filename = self._safe_filename("answer", "mp3")
        output_path = self.audio_output_dir / filename
        client = OpenAI(api_key=self.api_key)
        with client.audio.speech.with_streaming_response.create(
            model=self.model,
            voice=self.voice,
            input=text,
        ) as response:
            response.stream_to_file(output_path)

        return TtsResult(audio_path=str(output_path), audio_url=f"/audio/{filename}")

    def _safe_filename(self, prefix: str, suffix: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        token = re.sub(r"[^a-zA-Z0-9]", "", uuid.uuid4().hex[:10])
        return f"{prefix}_{timestamp}_{token}.{suffix}"

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return candidate.resolve()
