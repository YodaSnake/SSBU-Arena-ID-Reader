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
    build_observed_shape_mask,
    normalize_roi,
    rank_states,
    render_sequence_mask,
    sequence_score,
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
        if character == "3":
            expected = 2
        elif character in {"5", "6"}:
            expected = 3
        else:
            expected = 1
        assert len(variants) == expected


def test_bundled_template_assets_exist() -> None:
    expected = {
        f"{character}.png"
        for character in ALLOWED_CHARS
    }
    expected.update(
        {
            "3_alt1.png",
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


def test_observed_shape_mask_uses_local_lightness_contrast() -> None:
    width, height = TEMPLATE_ROI_SIZE
    background = np.linspace(
        210,
        70,
        width,
        dtype=np.uint8,
    )
    image = np.repeat(
        background[
            np.newaxis,
            :,
            np.newaxis,
        ],
        height,
        axis=0,
    )
    image = np.repeat(
        image,
        3,
        axis=2,
    )

    centers = (
        20,
        39,
        58,
        77,
        96,
    )

    for index, center in enumerate(
        centers
    ):
        contrast = (
            25
            if index < 3
            else 120
        )
        value = min(
            int(background[center])
            + contrast,
            245,
        )
        image[
            7:23,
            center - 2 : center + 2,
        ] = value

    mask = build_observed_shape_mask(
        image
    )

    for center in centers:
        assert np.all(
            mask[
                7:23,
                center - 2 : center + 2,
            ]
            == 255
        )

    assert not np.any(
        mask[:, :10]
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
    assert recognition.confidence_margin is not None
    assert recognition.confidence_margin >= 0.0
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


def test_first_transition_allows_observed_short_spacing_only_at_left_edge() -> None:
    first_short = (
        Candidate(
            character="F",
            center=28.0,
            score=0.0,
        ),
        Candidate(
            character="1",
            center=37.5,
            score=0.0,
        ),
        Candidate(
            character="J",
            center=55.5,
            score=0.0,
        ),
        Candidate(
            character="H",
            center=72.0,
            score=0.0,
        ),
        Candidate(
            character="Y",
            center=89.5,
            score=0.0,
        ),
    )

    later_short = (
        Candidate(
            character="F",
            center=28.0,
            score=0.0,
        ),
        Candidate(
            character="L",
            center=44.5,
            score=0.0,
        ),
        Candidate(
            character="J",
            center=55.5,
            score=0.0,
        ),
        Candidate(
            character="H",
            center=72.0,
            score=0.0,
        ),
        Candidate(
            character="Y",
            center=89.5,
            score=0.0,
        ),
    )

    too_short_first = (
        Candidate(
            character="F",
            center=28.0,
            score=0.0,
        ),
        Candidate(
            character="1",
            center=37.0,
            score=0.0,
        ),
        Candidate(
            character="J",
            center=55.5,
            score=0.0,
        ),
        Candidate(
            character="H",
            center=72.0,
            score=0.0,
        ),
        Candidate(
            character="Y",
            center=89.5,
            score=0.0,
        ),
    )

    assert sequence_score(first_short) is not None
    assert sequence_score(later_short) is None
    assert sequence_score(too_short_first) is None


def test_first_transition_uses_observed_17_pixel_target() -> None:
    ideal = tuple(
        Candidate(
            character=character,
            center=center,
            score=0.0,
        )
        for character, center in zip(
            "F1JHY",
            (
                10.0,
                27.0,
                46.0,
                65.0,
                84.0,
            ),
        )
    )

    wider_first = tuple(
        Candidate(
            character=character,
            center=center,
            score=0.0,
        )
        for character, center in zip(
            "F1JHY",
            (
                10.0,
                29.0,
                48.0,
                67.0,
                86.0,
            ),
        )
    )

    assert sequence_score(
        ideal
    ) == pytest.approx(0.0)

    assert sequence_score(
        wider_first
    ) == pytest.approx(-0.03)


def test_missing_template_asset_is_reported(tmp_path: Path) -> None:
    recognizer = TemplateRecognizer(tmp_path)
    with pytest.raises(RecognitionError):
        recognizer.ensure_ready()
