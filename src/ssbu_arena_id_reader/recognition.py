from __future__ import annotations

from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ALLOWED_CHARS = "0123456789ABCDEFGHJKLMNPQRSTUVWXY"
ARENA_ID_LENGTH = 5
MODEL_FILENAME = "english_g2.pth"
ROI_1080P = (1798, 100, 1920, 130)
ROI_BASE_SIZE = (1920, 1080)


class RecognitionError(RuntimeError):
    pass


def decode_png(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RecognitionError("Could not decode the OBS screenshot.")
    return image


def preprocess_frame(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    base_width, base_height = ROI_BASE_SIZE
    x1, y1, x2, y2 = ROI_1080P
    left = round(width * x1 / base_width)
    top = round(height * y1 / base_height)
    right = round(width * x2 / base_width)
    bottom = round(height * y2 / base_height)
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        raise RecognitionError("The Arena ID crop area is empty.")
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    inverted = cv2.bitwise_not(gray)
    return cv2.resize(inverted, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)


def sanitize_candidate(text: str) -> str:
    return "".join(char for char in text.upper() if char in ALLOWED_CHARS)


def character_majority(candidates: list[str]) -> str:
    valid = [candidate for candidate in candidates if len(candidate) == ARENA_ID_LENGTH]
    if not valid:
        raise RecognitionError("No valid OCR samples were produced.")

    result: list[str] = []
    for index in range(ARENA_ID_LENGTH):
        char, count = Counter(candidate[index] for candidate in valid).most_common(1)[0]
        if count * 2 <= len(candidates):
            raise RecognitionError(
                "OCR samples did not reach a stable character majority."
            )
        result.append(char)
    return "".join(result)


class EasyOcrRecognizer:
    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir or Path.home() / ".ssbu-arena-id-reader" / "models"
        self._reader = None

    def ensure_ready(self) -> None:
        if self._reader is not None:
            return

        self.model_dir.mkdir(parents=True, exist_ok=True)
        model_path = self.model_dir / MODEL_FILENAME
        download_enabled = not model_path.is_file()
        try:
            import easyocr

            self._reader = easyocr.Reader(
                ["en"],
                gpu=False,
                detector=False,
                recognizer=True,
                quantize=False,
                model_storage_directory=str(self.model_dir),
                download_enabled=download_enabled,
                verbose=False,
            )
        except Exception as exc:
            if download_enabled:
                raise RecognitionError(
                    "Could not prepare the OCR model. Internet access is required "
                    "only for the first model setup."
                ) from exc
            raise RecognitionError("Could not load the local OCR model.") from exc

    def recognize(self, image: np.ndarray) -> str:
        self.ensure_ready()
        results = self._reader.recognize(
            image,
            allowlist=ALLOWED_CHARS,
            detail=1,
            paragraph=False,
        )
        if not results:
            return ""
        return sanitize_candidate(str(results[0][1]))
