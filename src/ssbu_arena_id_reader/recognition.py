from __future__ import annotations

from collections import Counter

import cv2
import numpy as np

ALLOWED_CHARS = "0123456789BCDFGHJKLMNPQRSTVWXY"
ARENA_ID_LENGTH = 5
ROI_1080P = (1790, 100, 1920, 130)
ROI_BASE_SIZE = (1920, 1080)


class RecognitionError(RuntimeError):
    pass


def decode_png(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RecognitionError("Could not decode the OBS screenshot.")
    return image


def extract_arena_id_roi(frame: np.ndarray) -> np.ndarray:
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
    return crop.copy()


def preprocess_roi(crop: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    inverted = cv2.bitwise_not(gray)
    return cv2.resize(inverted, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)


def preprocess_frame(frame: np.ndarray) -> np.ndarray:
    return preprocess_roi(extract_arena_id_roi(frame))


def sanitize_candidate(text: str) -> str:
    return "".join(char for char in text.upper() if char in ALLOWED_CHARS)


def character_majority(candidates: list[str]) -> str:
    valid = [candidate for candidate in candidates if len(candidate) == ARENA_ID_LENGTH]
    if not valid:
        raise RecognitionError("No valid recognition samples were produced.")

    result: list[str] = []
    for index in range(ARENA_ID_LENGTH):
        char, count = Counter(candidate[index] for candidate in valid).most_common(1)[0]
        if count * 2 <= len(candidates):
            raise RecognitionError(
                "Recognition samples did not reach a stable character majority."
            )
        result.append(char)
    return "".join(result)
