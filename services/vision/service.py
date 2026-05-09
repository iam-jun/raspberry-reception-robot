from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class EmotionSnapshot:
    face_detected: bool
    emotion: str
    confidence: float
    timestamp: str
    provider: str = "fallback"
    message: str | None = None


class VisionService:
    def __init__(self) -> None:
        if load_dotenv is not None:
            load_dotenv(REPO_ROOT / ".env")

        self.enabled = os.getenv("VISION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self.camera_index = int(os.getenv("CAMERA_INDEX", "0"))
        self.latest = EmotionSnapshot(
            face_detected=False,
            emotion="unknown",
            confidence=0.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider="not-sampled",
            message="Vision has not sampled a frame yet.",
        )

    def health(self) -> dict[str, Any]:
        status = "ok" if self.enabled else "disabled"
        return {
            "status": status,
            "enabled": self.enabled,
            "camera_index": self.camera_index,
            "latest": asdict(self.latest),
        }

    def latest_result(self) -> dict[str, Any]:
        return asdict(self.latest)

    def capture_once(self) -> dict[str, Any]:
        if not self.enabled:
            self.latest = self._snapshot(False, "unknown", 0.0, "disabled", "Vision is disabled.")
            return asdict(self.latest)

        try:
            frame = self._capture_picamera2()
            provider = "picamera2"
        except Exception as picamera_error:
            try:
                frame = self._capture_opencv()
                provider = "opencv"
            except Exception as opencv_error:
                self.latest = self._snapshot(
                    False,
                    "unknown",
                    0.0,
                    "fallback",
                    f"Camera capture unavailable. picamera2: {picamera_error}; opencv: {opencv_error}",
                )
                return asdict(self.latest)

        self.latest = self._detect_face_emotion(frame, provider)
        return asdict(self.latest)

    def _capture_picamera2(self) -> Any:
        from picamera2 import Picamera2

        camera = Picamera2()
        config = camera.create_preview_configuration(main={"size": (640, 480)})
        camera.configure(config)
        camera.start()
        try:
            return camera.capture_array()
        finally:
            camera.stop()
            camera.close()

    def _capture_opencv(self) -> Any:
        import cv2

        camera = cv2.VideoCapture(self.camera_index)
        if not camera.isOpened():
            raise RuntimeError(f"OpenCV could not open camera index {self.camera_index}.")
        try:
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError("OpenCV did not return a camera frame.")
            return frame
        finally:
            camera.release()

    def _detect_face_emotion(self, frame: Any, provider: str) -> EmotionSnapshot:
        try:
            import cv2
        except ImportError:
            return self._snapshot(
                True,
                "unknown",
                0.2,
                provider,
                "Captured a frame, but OpenCV is not installed for face detection.",
            )

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        if not cascade_path.exists():
            return self._snapshot(False, "unknown", 0.0, provider, "OpenCV Haar cascade file was not found.")

        detector = cv2.CascadeClassifier(str(cascade_path))
        faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0:
            return self._snapshot(False, "unknown", 0.0, provider, "No face detected.")

        # MVP emotion provider: reliable face presence first, neutral estimate
        # second. This keeps the Pi 5 workload light and leaves a clear swap-in
        # point for a real emotion classifier later.
        return self._snapshot(True, "neutral", 0.5, provider, f"Detected {len(faces)} face(s).")

    def _snapshot(
        self,
        face_detected: bool,
        emotion: str,
        confidence: float,
        provider: str,
        message: str | None,
    ) -> EmotionSnapshot:
        return EmotionSnapshot(
            face_detected=face_detected,
            emotion=emotion,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=provider,
            message=message,
        )
