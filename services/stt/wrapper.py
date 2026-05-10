from __future__ import annotations

import os
import re
import shutil
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]
STT_DIR = Path(__file__).resolve().parent
ASR_SDK_DIR = STT_DIR / "asr-sdk"
DEFAULT_AUDIO_DIR = REPO_ROOT / "storage" / "audio"


class SttService:
    def __init__(self) -> None:
        if load_dotenv is not None:
            load_dotenv(REPO_ROOT / ".env")

        self.binary = os.getenv("STT_BINARY") or self._find_default_binary()
        self.model_dir = self._resolve_path(os.getenv("STT_MODEL_DIR") or ASR_SDK_DIR)
        self.sample_rate = int(os.getenv("STT_SAMPLE_RATE", "16000"))
        self.timeout_seconds = int(os.getenv("STT_TIMEOUT_SECONDS", "60"))
        self.audio_dir = self._resolve_path(os.getenv("AUDIO_OUTPUT_DIR") or DEFAULT_AUDIO_DIR)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def health(self) -> dict[str, Any]:
        binary_path = Path(self.binary).expanduser() if self.binary else None
        binary_exists = bool(binary_path and binary_path.exists())
        model_ready = self._model_root_ready(self.model_dir)
        status = "ok" if binary_exists and model_ready else "degraded"
        return {
            "status": status,
            "binary": str(binary_path) if binary_path else None,
            "binary_exists": binary_exists,
            "model_dir": str(self.model_dir),
            "model_ready": model_ready,
            "sample_rate": self.sample_rate,
        }

    def transcribe_wav(self, path: str | Path) -> str:
        wav_path = self._resolve_path(path)
        if not wav_path.exists():
            raise FileNotFoundError(f"WAV file does not exist: {wav_path}")
        if not self.binary:
            raise RuntimeError(
                "STT_BINARY is not configured and no asr_from_wav binary was found under services/stt/asr-sdk/build. "
                "Build the SDK examples or set STT_BINARY explicitly."
            )

        binary_path = Path(self.binary).expanduser()
        if not binary_path.is_absolute():
            binary_path = (REPO_ROOT / binary_path).resolve()
        if not binary_path.exists():
            raise FileNotFoundError(f"Configured STT_BINARY does not exist: {binary_path}")
        if not self._model_root_ready(self.model_dir):
            raise FileNotFoundError(
                f"STT model root is not ready: {self.model_dir}. Expected an asr-sdk root containing a models directory."
            )

        command = [str(binary_path), str(self.model_dir), str(wav_path)]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            env=self._subprocess_env(),
        )
        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        if completed.returncode != 0:
            if completed.returncode == -11:
                raise RuntimeError(
                    "STT command crashed with SIGSEGV. Verify that SHERPA_ONNX_ROOT points to the same sherpa-onnx "
                    "version used for headers and libraries, and that LD_LIBRARY_PATH includes $SHERPA_ONNX_ROOT/lib.\n"
                    f"{output.strip()}"
                )
            raise RuntimeError(f"STT command failed with exit code {completed.returncode}:\n{output.strip()}")

        transcript = self._extract_transcript(output)
        if not transcript:
            raise RuntimeError(f"STT completed but no transcript was found in output:\n{output.strip()}")
        return transcript

    def record_audio(self, duration_seconds: int = 5, output_path: str | Path | None = None) -> str:
        duration_seconds = max(1, int(duration_seconds))
        wav_path = self._resolve_path(output_path) if output_path else self._new_recording_path()
        wav_path.parent.mkdir(parents=True, exist_ok=True)

        arecord = shutil.which("arecord")
        if arecord:
            command = [
                arecord,
                "-d",
                str(duration_seconds),
                "-f",
                "S16_LE",
                "-r",
                str(self.sample_rate),
                "-c",
                "1",
                str(wav_path),
            ]
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            if completed.returncode != 0:
                raise RuntimeError(f"arecord failed with exit code {completed.returncode}: {completed.stderr.strip()}")
            return str(wav_path)

        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as error:
            raise RuntimeError(
                "No microphone recorder is available. Install ALSA arecord or pip install sounddevice numpy."
            ) from error

        recording = sd.rec(
            int(duration_seconds * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()
        samples = np.asarray(recording).reshape(-1)
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(samples.tobytes())
        return str(wav_path)

    def _extract_transcript(self, output: str) -> str:
        finals = []
        partials = []
        for line in output.splitlines():
            final_match = re.match(r"\s*final:\s*(.*)\s*$", line, re.IGNORECASE)
            partial_match = re.match(r"\s*partial:\s*(.*)\s*$", line, re.IGNORECASE)
            if final_match and final_match.group(1).strip():
                finals.append(final_match.group(1).strip())
            elif partial_match and partial_match.group(1).strip():
                partials.append(partial_match.group(1).strip())
        if finals:
            return " ".join(finals).strip()
        return partials[-1].strip() if partials else ""

    def _find_default_binary(self) -> str | None:
        candidates = [
            ASR_SDK_DIR / "build" / "asr_from_wav",
            ASR_SDK_DIR / "build-asr-sdk" / "asr_from_wav",
        ]
        candidates.extend(sorted(ASR_SDK_DIR.glob("build*/asr_from_wav")))
        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve())
        return None

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        sherpa_root = env.get("SHERPA_ONNX_ROOT")
        if sherpa_root:
            lib_dir = str((Path(sherpa_root).expanduser() / "lib").resolve())
            current = env.get("LD_LIBRARY_PATH", "")
            paths = [path for path in current.split(":") if path]
            if lib_dir not in paths:
                env["LD_LIBRARY_PATH"] = ":".join([lib_dir, *paths])
        return env

    def _model_root_ready(self, path: Path) -> bool:
        return (path / "models").exists()

    def _new_recording_path(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return self.audio_dir / f"question_{timestamp}.wav"

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return candidate.resolve()


def transcribe_wav(path: str) -> str:
    return SttService().transcribe_wav(path)


def record_audio(duration_seconds: int, output_path: str) -> str:
    return SttService().record_audio(duration_seconds, output_path)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe a mono 16 kHz WAV file with the configured STT SDK.")
    parser.add_argument("wav_path", help="Path to a WAV file.")
    args = parser.parse_args()
    print(transcribe_wav(args.wav_path))


if __name__ == "__main__":
    main()
