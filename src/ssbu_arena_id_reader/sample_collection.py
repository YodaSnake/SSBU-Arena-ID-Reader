from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .recognition import ALLOWED_CHARS, ARENA_ID_LENGTH

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIRECTORY = REPOSITORY_ROOT / "template_samples" / "raw"


class SampleCollectionError(RuntimeError):
    pass


def save_template_sample(
    image: np.ndarray,
    arena_id: str,
    directory: Path = SAMPLE_DIRECTORY,
) -> Path:
    if (
        len(arena_id) != ARENA_ID_LENGTH
        or any(char not in ALLOWED_CHARS for char in arena_id)
    ):
        raise SampleCollectionError("The current Arena ID is not valid for sample naming.")

    try:
        encoded_ok, encoded = cv2.imencode(".png", image)
    except cv2.error as exc:
        raise SampleCollectionError("Could not encode the Arena ID sample as PNG.") from exc

    if not encoded_ok:
        raise SampleCollectionError("Could not encode the Arena ID sample as PNG.")

    try:
        directory.mkdir(parents=True, exist_ok=True)

        sample_path = directory / f"{arena_id}.png"
        sequence = 2
        while sample_path.exists():
            sample_path = directory / f"{arena_id}_{sequence:03d}.png"
            sequence += 1

        sample_path.write_bytes(encoded.tobytes())
    except OSError as exc:
        raise SampleCollectionError("Could not save the Arena ID sample.") from exc

    return sample_path
