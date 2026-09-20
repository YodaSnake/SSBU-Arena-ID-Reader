from pathlib import Path

import cv2
import numpy as np
import pytest

from ssbu_arena_id_reader.recognition import (
    ALLOWED_CHARS,
    RecognitionError,
)
from ssbu_arena_id_reader.template_recognizer import (
    TEMPLATE_DIRECTORY,
    TEMPLATE_ROI_SIZE,
    Candidate,
    State,
    TemplateRecognizer,
    normalize_roi,
    rank_states,
    render_sequence_mask,
    state_text,
)


def test_bundled_template_bank_has_expected_variants() -> None:
    recognizer = TemplateRecognizer()
    recognizer.ensure_ready()
    assert recognizer._template_bank is not None
    assert recognizer._shape_masks is not None
    assert set(recognizer._template_bank) == set(ALLOWED_CHARS)
    assert set(recognizer._shape_masks) == set(ALLOWED_CHARS)
    for character, variants in recognizer._template_bank.items():
        expected = 3 if character in {"5", "6"} else 1
        assert len(variants) == expected


def test_bundled_template_assets_exist() -> None:
    expected = {
        f"{character}.png"
        for character in ALLOWED_CHARS
    }
    expected.update(
        {
            "5_alt1.png",
            "5_alt2.png",
            "6_alt1.png",
            "6_alt2.png",
        }
    )
    actual = {
        path.name
        for path in TEMPLATE_DIRECTORY.glob("*.png")
    }
    assert actual == expected


def test_normalize_roi_resizes_to_template_reference_size() -> None:
    roi = np.zeros((20, 87, 3), dtype=np.uint8)
    normalized = normalize_roi(roi)
    assert normalized.shape == (
        TEMPLATE_ROI_SIZE[1],
        TEMPLATE_ROI_SIZE[0],
    )


def test_normalize_roi_rejects_empty_image() -> None:
    with pytest.raises(RecognitionError):
        normalize_roi(
            np.empty((0, 0, 3), dtype=np.uint8)
        )


def test_recognizer_reads_synthetic_reference_sequence() -> None:
    arena_id = "JPQHX"
    centers = [20, 39, 58, 77, 96]
    roi = np.zeros(
        (
            TEMPLATE_ROI_SIZE[1],
            TEMPLATE_ROI_SIZE[0],
        ),
        dtype=np.uint8,
    )
    for character, center in zip(arena_id, centers):
        template = cv2.imread(
            str(TEMPLATE_DIRECTORY / f"{character}.png"),
            cv2.IMREAD_GRAYSCALE,
        )
        assert template is not None
        width = template.shape[1]
        left = round(center - width / 2)
        roi[:, left : left + width] = template
    recognizer = TemplateRecognizer()
    recognition = (
        recognizer.recognize_with_candidates(
            roi
        )
    )

    assert recognition.text == arena_id
    assert len(
        recognition.character_candidates
    ) == len(arena_id)

    for index, candidates in enumerate(
        recognition.character_candidates
    ):
        assert len(candidates) == len(
            ALLOWED_CHARS
        )
        assert set(candidates) == set(
            ALLOWED_CHARS
        )
        assert candidates[0] == arena_id[index]

    assert recognizer.recognize(roi) == arena_id


def test_shape_reranking_prefers_complete_glyph_shape() -> None:
    recognizer = TemplateRecognizer()
    recognizer.ensure_ready()
    assert recognizer._shape_masks is not None

    centers = [20, 39, 58, 77, 96]

    true_state = State(
        score=3.98,
        sequence=tuple(
            Candidate(
                character=character,
                center=center,
                score=0.0,
            )
            for character, center in zip(
                "LYBH2",
                centers,
            )
        ),
    )

    partial_state = State(
        score=4.00,
        sequence=tuple(
            Candidate(
                character=character,
                center=center,
                score=0.0,
            )
            for character, center in zip(
                "1YBH2",
                centers,
            )
        ),
    )

    assert partial_state.score > true_state.score

    observed = render_sequence_mask(
        true_state,
        recognizer._shape_masks,
    )

    ranked = rank_states(
        [
            partial_state,
            true_state,
        ],
        observed,
        recognizer._shape_masks,
    )

    assert len(ranked) == 2
    assert state_text(ranked[0].state) == "LYBH2"
    assert ranked[0].shape_score > ranked[1].shape_score


def test_missing_template_asset_is_reported(tmp_path: Path) -> None:
    recognizer = TemplateRecognizer(tmp_path)
    with pytest.raises(RecognitionError):
        recognizer.ensure_ready()
