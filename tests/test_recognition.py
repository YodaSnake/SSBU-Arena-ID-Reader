import numpy as np
import pytest

from ssbu_arena_id_reader.recognition import (
    RecognitionError,
    arena_id_roi_bounds,
    character_majority,
    extract_arena_id_roi,
    preprocess_frame,
    sanitize_candidate,
)


def test_character_majority_is_per_position() -> None:
    candidates = ["7K3XV", "7K8XY", "7J3XY", "8K3XY", "7K3WV"]
    assert "7K3XY" not in candidates
    assert character_majority(candidates) == "7K3XY"


def test_character_majority_requires_strict_majority() -> None:
    with pytest.raises(RecognitionError):
        character_majority(["ABC12", "ABC13", "ABC12", "ABC13"])


def test_character_majority_accepts_one_valid_read() -> None:
    assert character_majority(["ABC12"]) == "ABC12"


def test_character_majority_counts_invalid_reads_against_stability() -> None:
    with pytest.raises(RecognitionError):
        character_majority(["ABC12", "BAD"])


def test_sanitize_candidate_keeps_only_ssbu_id_characters() -> None:
    assert sanitize_candidate(" 7k3xy\n") == "7K3XY"
    assert sanitize_candidate("AEIOUZ") == ""


def test_extract_arena_id_roi_uses_reference_1080p_roi() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    crop = extract_arena_id_roi(frame)
    assert crop.shape == (30, 130, 3)


def test_extract_arena_id_roi_applies_horizontal_reference_pixel_offset() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[100, 1778] = (11, 22, 33)
    frame[129, 1907] = (44, 55, 66)

    crop = extract_arena_id_roi(
        frame,
        crop_offset_x=-12,
    )

    assert crop.shape == (30, 130, 3)
    assert tuple(crop[0, 0]) == (11, 22, 33)
    assert tuple(crop[-1, -1]) == (44, 55, 66)


def test_arena_id_roi_bounds_reject_position_outside_frame() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    with pytest.raises(RecognitionError):
        arena_id_roi_bounds(
            frame,
            crop_offset_x=1,
        )


def test_preprocess_frame_uses_reference_1080p_roi() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    processed = preprocess_frame(frame)
    assert processed.shape == (120, 520)
