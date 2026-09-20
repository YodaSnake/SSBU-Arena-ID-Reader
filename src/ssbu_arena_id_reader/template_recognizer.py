from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from pathlib import Path

import cv2
import numpy as np

from .recognition import ALLOWED_CHARS, ARENA_ID_LENGTH, RecognitionError

TEMPLATE_ROI_SIZE = (130, 30)
TEMPLATE_DIRECTORY = (
    Path(__file__).resolve().parent / "assets" / "arena_id_templates"
)
PEAK_SCORE_FLOOR = 0.45
PEAKS_PER_VARIANT = 8
CANDIDATES_PER_CHARACTER = 8
PEAK_DEDUP_DISTANCE = 2
CENTER_DEDUP_DISTANCE = 2.0
ALIGNMENT_RADIUS = 2
MIN_CENTER_DISTANCE = 12.0
MAX_CENTER_DISTANCE = 24.0
TARGET_CENTER_DISTANCE = 19.0
CENTER_DISTANCE_PENALTY = 0.015
RERANK_BEAM_WIDTH = 128
RERANK_SEQUENCE_LIMIT = 16
SHAPE_WEIGHT = 0.60
SHAPE_CORE_LIGHTNESS = 180
SHAPE_LOW_LIGHTNESS_FLOOR = 120
SHAPE_BORDER_MARGIN = 12
SHAPE_GROW_RADIUS = 2.25
SHAPE_BINARY_ALPHA_THRESHOLD = 128
OBSERVED_BACKGROUND_SIGMA = 3.0
OBSERVED_SHAPE_CORE_CONTRAST = 12
OBSERVED_SHAPE_GROW_CONTRAST = 6
MIN_OBSERVED_COMPONENT_AREA = 20
MIN_OBSERVED_COMPONENT_HEIGHT = 8
CHAMFER_SCALE = 2.0
CHARACTER_CANDIDATE_CENTER_RADIUS = 6
TEMPLATE_FILENAMES = {
    character: (f"{character}.png",)
    for character in ALLOWED_CHARS
}
TEMPLATE_FILENAMES["5"] = (
    "5.png",
    "5_alt1.png",
    "5_alt2.png",
)
TEMPLATE_FILENAMES["6"] = (
    "6.png",
    "6_alt1.png",
    "6_alt2.png",
)


@dataclass(frozen=True)
class TemplateVariant:
    image: np.ndarray
    width: int


@dataclass(frozen=True)
class Candidate:
    character: str
    center: float
    score: float


@dataclass(frozen=True)
class State:
    score: float
    sequence: tuple[Candidate, ...]


@dataclass(frozen=True)
class ScoredState:
    state: State
    ncc_score: float
    dice_score: float
    chamfer_score: float
    shape_score: float
    final_score: float


@dataclass(frozen=True)
class TemplateRecognitionResult:
    text: str
    character_candidates: tuple[tuple[str, ...], ...]
    confidence_margin: float | None = None


def normalize_roi(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        raise RecognitionError("The Arena ID crop is empty.")
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 3 and image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        raise RecognitionError("The Arena ID crop has an unsupported image format.")
    target_width, target_height = TEMPLATE_ROI_SIZE
    if gray.shape != (target_height, target_width):
        interpolation = (
            cv2.INTER_AREA
            if gray.shape[0] > target_height or gray.shape[1] > target_width
            else cv2.INTER_CUBIC
        )
        gray = cv2.resize(
            gray,
            TEMPLATE_ROI_SIZE,
            interpolation=interpolation,
        )
    return gray


def normalize_color_roi(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        raise RecognitionError("The Arena ID crop is empty.")
    if image.ndim == 2:
        color = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.ndim == 3 and image.shape[2] == 3:
        color = image
    elif image.ndim == 3 and image.shape[2] == 4:
        color = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    else:
        raise RecognitionError("The Arena ID crop has an unsupported image format.")
    target_width, target_height = TEMPLATE_ROI_SIZE
    if color.shape[:2] != (target_height, target_width):
        interpolation = (
            cv2.INTER_AREA
            if color.shape[0] > target_height or color.shape[1] > target_width
            else cv2.INTER_CUBIC
        )
        color = cv2.resize(
            color,
            TEMPLATE_ROI_SIZE,
            interpolation=interpolation,
        )
    return color


def score_map(target: np.ndarray, template: np.ndarray) -> np.ndarray:
    result = cv2.matchTemplate(
        target,
        template,
        cv2.TM_CCOEFF_NORMED,
    )
    return np.nan_to_num(
        result[0],
        nan=-1.0,
        posinf=-1.0,
        neginf=-1.0,
    )


def local_peaks(
    scores: np.ndarray,
    limit: int,
) -> list[tuple[float, int]]:
    peaks: list[tuple[float, int]] = []
    for x, raw_score in enumerate(scores):
        score = float(raw_score)
        if score < PEAK_SCORE_FLOOR:
            continue
        left = float(scores[x - 1]) if x > 0 else float("-inf")
        right = (
            float(scores[x + 1])
            if x + 1 < len(scores)
            else float("-inf")
        )
        if score < left or score < right:
            continue
        peaks.append((score, x))
    peaks.sort(reverse=True)
    selected: list[tuple[float, int]] = []
    for score, x in peaks:
        if any(
            abs(x - existing_x) <= PEAK_DEDUP_DISTANCE
            for _, existing_x in selected
        ):
            continue
        selected.append((score, x))
        if len(selected) >= limit:
            break
    return selected


def aligned_match(
    scores: np.ndarray,
    width: int,
    center: float,
) -> tuple[float, float]:
    expected_x = round(center - width / 2)
    start = max(0, expected_x - ALIGNMENT_RADIUS)
    end = min(
        len(scores),
        expected_x + ALIGNMENT_RADIUS + 1,
    )
    if start >= end:
        return -1.0, center
    local = scores[start:end]
    offset = int(np.argmax(local))
    x = start + offset
    return float(scores[x]), x + width / 2


def generate_character_candidates(
    target: np.ndarray,
    character: str,
    variants: list[TemplateVariant],
) -> list[Candidate]:
    variant_maps: list[tuple[TemplateVariant, np.ndarray]] = []
    for variant in variants:
        variant_maps.append(
            (
                variant,
                score_map(target, variant.image),
            )
        )
    anchor_centers: list[float] = []
    for variant, scores in variant_maps:
        for _, x in local_peaks(scores, PEAKS_PER_VARIANT):
            anchor_centers.append(x + variant.width / 2)
    provisional: list[Candidate] = []
    for anchor_center in anchor_centers:
        matched_scores: list[float] = []
        matched_centers: list[float] = []
        for variant, scores in variant_maps:
            score, matched_center = aligned_match(
                scores,
                variant.width,
                anchor_center,
            )
            matched_scores.append(score)
            matched_centers.append(matched_center)
        aggregate_score = float(np.median(matched_scores))
        if aggregate_score < PEAK_SCORE_FLOOR:
            continue
        provisional.append(
            Candidate(
                character=character,
                center=float(np.median(matched_centers)),
                score=aggregate_score,
            )
        )
    provisional.sort(
        key=lambda candidate: candidate.score,
        reverse=True,
    )
    selected: list[Candidate] = []
    for candidate in provisional:
        if any(
            abs(candidate.center - existing.center)
            <= CENTER_DEDUP_DISTANCE
            for existing in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= CANDIDATES_PER_CHARACTER:
            break
    return selected


def generate_candidates(
    target: np.ndarray,
    template_bank: dict[str, list[TemplateVariant]],
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for character in ALLOWED_CHARS:
        candidates.extend(
            generate_character_candidates(
                target,
                character,
                template_bank[character],
            )
        )
    candidates.sort(
        key=lambda candidate: (
            candidate.center,
            candidate.character,
        )
    )
    return candidates


def transition_score(
    previous: Candidate,
    current: Candidate,
) -> float | None:
    distance = current.center - previous.center
    if (
        distance < MIN_CENTER_DISTANCE
        or distance > MAX_CENTER_DISTANCE
    ):
        return None
    penalty = CENTER_DISTANCE_PENALTY * abs(
        distance - TARGET_CENTER_DISTANCE
    )
    return current.score - penalty


def reconstruct(candidates: list[Candidate]) -> State | None:
    if not candidates:
        return None
    layers: list[dict[int, State]] = []
    first_layer = {
        index: State(
            score=candidate.score,
            sequence=(candidate,),
        )
        for index, candidate in enumerate(candidates)
    }
    layers.append(first_layer)
    for _ in range(1, ARENA_ID_LENGTH):
        previous_layer = layers[-1]
        current_layer: dict[int, State] = {}
        for current_index, current in enumerate(candidates):
            best_state: State | None = None
            for previous_index, previous_state in previous_layer.items():
                previous = candidates[previous_index]
                if current.center <= previous.center:
                    continue
                added_score = transition_score(previous, current)
                if added_score is None:
                    continue
                candidate_state = State(
                    score=previous_state.score + added_score,
                    sequence=previous_state.sequence + (current,),
                )
                if (
                    best_state is None
                    or candidate_state.score > best_state.score
                ):
                    best_state = candidate_state
            if best_state is not None:
                current_layer[current_index] = best_state
        if not current_layer:
            return None
        layers.append(current_layer)
    return max(
        layers[-1].values(),
        key=lambda state: state.score,
        default=None,
    )


def state_text(state: State) -> str:
    return "".join(
        candidate.character
        for candidate in state.sequence
    )


def top_sequence_states(
    candidates: list[Candidate],
) -> list[State]:
    if not candidates:
        return []
    states = [
        State(
            score=candidate.score,
            sequence=(candidate,),
        )
        for candidate in candidates
    ]
    for _ in range(1, ARENA_ID_LENGTH):
        expanded: list[State] = []
        for state in states:
            previous = state.sequence[-1]
            for current in candidates:
                distance = current.center - previous.center
                if distance <= 0:
                    continue
                if distance > MAX_CENTER_DISTANCE:
                    break
                added_score = transition_score(
                    previous,
                    current,
                )
                if added_score is None:
                    continue
                expanded.append(
                    State(
                        score=state.score + added_score,
                        sequence=state.sequence + (current,),
                    )
                )
        if not expanded:
            return []
        states = heapq.nlargest(
            RERANK_BEAM_WIDTH,
            expanded,
            key=lambda state: state.score,
        )
    best_by_text: dict[str, State] = {}
    for state in states:
        text = state_text(state)
        previous = best_by_text.get(text)
        if (
            previous is None
            or state.score > previous.score
        ):
            best_by_text[text] = state
    return heapq.nlargest(
        RERANK_SEQUENCE_LIMIT,
        best_by_text.values(),
        key=lambda state: state.score,
    )


def shape_low_lightness(lightness: np.ndarray) -> int:
    border = np.concatenate(
        (
            lightness[0, :],
            lightness[-1, :],
            lightness[:, 0],
            lightness[:, -1],
        )
    )
    border90 = float(
        np.percentile(
            border,
            90,
        )
    )
    return max(
        SHAPE_LOW_LIGHTNESS_FLOOR,
        round(
            border90
            + SHAPE_BORDER_MARGIN
        ),
    )


def choose_template_shape_core(
    core_mask: np.ndarray,
) -> np.ndarray:
    count, labels, stats, centers = (
        cv2.connectedComponentsWithStats(
            core_mask,
            connectivity=8,
        )
    )
    if count <= 1:
        raise RecognitionError(
            "Arena ID template has no foreground shape."
        )
    height, width = core_mask.shape
    image_center_x = (width - 1) / 2
    image_center_y = (height - 1) / 2
    best_label: int | None = None
    best_score: float | None = None
    for label in range(1, count):
        area = float(
            stats[
                label,
                cv2.CC_STAT_AREA,
            ]
        )
        center_x, center_y = centers[label]
        x_distance = abs(
            center_x - image_center_x
        ) / max(width, 1)
        y_distance = abs(
            center_y - image_center_y
        ) / max(height, 1)
        center_penalty = (
            4.0 * x_distance
            + 2.0 * y_distance
        )
        score = area - center_penalty
        if (
            best_score is None
            or score > best_score
        ):
            best_score = score
            best_label = label
    if best_label is None:
        raise RecognitionError(
            "Could not select Arena ID template foreground shape."
        )
    return np.where(
        labels == best_label,
        255,
        0,
    ).astype(np.uint8)


def select_observed_shape_core(
    core_mask: np.ndarray,
) -> np.ndarray:
    count, labels, stats, _ = (
        cv2.connectedComponentsWithStats(
            core_mask,
            connectivity=8,
        )
    )
    eligible: list[tuple[int, int]] = []
    for label in range(1, count):
        area = int(
            stats[
                label,
                cv2.CC_STAT_AREA,
            ]
        )
        height = int(
            stats[
                label,
                cv2.CC_STAT_HEIGHT,
            ]
        )
        if area < MIN_OBSERVED_COMPONENT_AREA:
            continue
        if height < MIN_OBSERVED_COMPONENT_HEIGHT:
            continue
        eligible.append((area, label))
    eligible.sort(reverse=True)
    selected_labels = {
        label
        for _, label in eligible[
            :ARENA_ID_LENGTH
        ]
    }
    if not selected_labels:
        return np.zeros_like(
            core_mask,
            dtype=np.uint8,
        )
    return np.where(
        np.isin(
            labels,
            list(selected_labels),
        ),
        255,
        0,
    ).astype(np.uint8)


def observed_local_contrast(
    lightness: np.ndarray,
) -> np.ndarray:
    background = cv2.GaussianBlur(
        lightness,
        (0, 0),
        sigmaX=OBSERVED_BACKGROUND_SIGMA,
        sigmaY=OBSERVED_BACKGROUND_SIGMA,
    )
    return cv2.subtract(
        lightness,
        background,
    )


def grow_observed_shape_mask(
    local_contrast: np.ndarray,
    selected_core: np.ndarray,
) -> np.ndarray:
    if not np.any(selected_core):
        return np.zeros_like(
            selected_core,
            dtype=np.uint8,
        )
    outside_core = np.where(
        selected_core == 0,
        1,
        0,
    ).astype(np.uint8)
    distance = cv2.distanceTransform(
        outside_core,
        cv2.DIST_L2,
        cv2.DIST_MASK_PRECISE,
    )
    support = (
        (distance <= SHAPE_GROW_RADIUS)
        & (
            local_contrast
            >= OBSERVED_SHAPE_GROW_CONTRAST
        )
    )
    return np.where(
        (selected_core > 0)
        | support,
        255,
        0,
    ).astype(np.uint8)


def grow_shape_mask(
    lightness: np.ndarray,
    selected_core: np.ndarray,
) -> np.ndarray:
    if not np.any(selected_core):
        return np.zeros_like(
            selected_core,
            dtype=np.uint8,
        )
    low_lightness = shape_low_lightness(
        lightness
    )
    outside_core = np.where(
        selected_core == 0,
        1,
        0,
    ).astype(np.uint8)
    distance = cv2.distanceTransform(
        outside_core,
        cv2.DIST_L2,
        cv2.DIST_MASK_PRECISE,
    )
    support = (
        (distance <= SHAPE_GROW_RADIUS)
        & (
            lightness
            >= low_lightness
        )
    )
    denominator = max(
        SHAPE_CORE_LIGHTNESS
        - low_lightness,
        1,
    )
    alpha_float = (
        (
            lightness.astype(
                np.float32
            )
            - low_lightness
        )
        / denominator
        * 255.0
    )
    alpha = np.clip(
        alpha_float,
        0,
        255,
    ).astype(np.uint8)
    alpha = np.where(
        support,
        alpha,
        0,
    ).astype(np.uint8)
    alpha = np.where(
        selected_core > 0,
        255,
        alpha,
    ).astype(np.uint8)
    return np.where(
        alpha >= SHAPE_BINARY_ALPHA_THRESHOLD,
        255,
        0,
    ).astype(np.uint8)


def build_template_shape_mask(
    image: np.ndarray,
) -> np.ndarray:
    lab = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2LAB,
    )
    lightness = lab[:, :, 0]
    core = np.where(
        lightness >= SHAPE_CORE_LIGHTNESS,
        255,
        0,
    ).astype(np.uint8)
    selected_core = choose_template_shape_core(
        core
    )
    return grow_shape_mask(
        lightness,
        selected_core,
    )


def build_observed_shape_mask(
    image: np.ndarray,
) -> np.ndarray:
    color = normalize_color_roi(image)
    lab = cv2.cvtColor(
        color,
        cv2.COLOR_BGR2LAB,
    )
    lightness = lab[:, :, 0]
    local_contrast = observed_local_contrast(
        lightness
    )
    core = np.where(
        local_contrast
        >= OBSERVED_SHAPE_CORE_CONTRAST,
        255,
        0,
    ).astype(np.uint8)
    selected_core = select_observed_shape_core(
        core
    )
    return grow_observed_shape_mask(
        local_contrast,
        selected_core,
    )


def render_sequence_mask(
    state: State,
    shape_masks: dict[str, np.ndarray],
) -> np.ndarray:
    rendered = np.zeros(
        (
            TEMPLATE_ROI_SIZE[1],
            TEMPLATE_ROI_SIZE[0],
        ),
        dtype=np.uint8,
    )
    for candidate in state.sequence:
        glyph = shape_masks[
            candidate.character
        ]
        width = glyph.shape[1]
        left = round(
            candidate.center
            - width / 2
        )
        right = left + width
        source_left = 0
        source_right = width
        if left < 0:
            source_left = -left
            left = 0
        if right > rendered.shape[1]:
            source_right -= (
                right
                - rendered.shape[1]
            )
            right = rendered.shape[1]
        if (
            left >= right
            or source_left >= source_right
        ):
            continue
        rendered[
            :,
            left:right,
        ] = np.maximum(
            rendered[
                :,
                left:right,
            ],
            glyph[
                :,
                source_left:source_right,
            ],
        )
    return rendered


def dice_similarity(
    predicted: np.ndarray,
    observed: np.ndarray,
) -> float:
    predicted_foreground = predicted > 0
    observed_foreground = observed > 0
    predicted_count = int(
        np.count_nonzero(
            predicted_foreground
        )
    )
    observed_count = int(
        np.count_nonzero(
            observed_foreground
        )
    )
    denominator = (
        predicted_count
        + observed_count
    )
    if denominator == 0:
        return 0.0
    intersection = int(
        np.count_nonzero(
            predicted_foreground
            & observed_foreground
        )
    )
    return (
        2.0
        * intersection
        / denominator
    )


def distance_to_foreground(
    mask: np.ndarray,
) -> np.ndarray:
    inverse = np.where(
        mask > 0,
        0,
        1,
    ).astype(np.uint8)
    return cv2.distanceTransform(
        inverse,
        cv2.DIST_L2,
        cv2.DIST_MASK_PRECISE,
    )


def chamfer_similarity(
    predicted: np.ndarray,
    observed: np.ndarray,
    distance_to_observed: np.ndarray,
) -> float:
    predicted_foreground = predicted > 0
    observed_foreground = observed > 0
    if (
        not np.any(predicted_foreground)
        or not np.any(observed_foreground)
    ):
        return 0.0
    predicted_to_observed = float(
        np.mean(
            distance_to_observed[
                predicted_foreground
            ]
        )
    )
    distance_to_predicted = (
        distance_to_foreground(
            predicted
        )
    )
    observed_to_predicted = float(
        np.mean(
            distance_to_predicted[
                observed_foreground
            ]
        )
    )
    distance = (
        predicted_to_observed
        + observed_to_predicted
    ) / 2.0
    return math.exp(
        -distance / CHAMFER_SCALE
    )


def rank_states(
    states: list[State],
    observed: np.ndarray,
    shape_masks: dict[str, np.ndarray],
) -> list[ScoredState]:
    if not states:
        return []
    distance_to_observed = (
        distance_to_foreground(
            observed
        )
    )
    scored: list[ScoredState] = []
    for state in states:
        rendered = render_sequence_mask(
            state,
            shape_masks,
        )
        dice = dice_similarity(
            rendered,
            observed,
        )
        chamfer = chamfer_similarity(
            rendered,
            observed,
            distance_to_observed,
        )
        shape = (
            dice
            + chamfer
        ) / 2.0
        ncc = (
            state.score
            / ARENA_ID_LENGTH
        )
        scored.append(
            ScoredState(
                state=state,
                ncc_score=ncc,
                dice_score=dice,
                chamfer_score=chamfer,
                shape_score=shape,
                final_score=(
                    ncc
                    + SHAPE_WEIGHT
                    * shape
                ),
            )
        )
    scored.sort(
        key=lambda item: (
            item.final_score,
            item.state.score,
        ),
        reverse=True,
    )
    return scored


def sequence_score(
    sequence: tuple[Candidate, ...],
) -> float | None:
    if not sequence:
        return None

    score = sequence[0].score

    for previous, current in zip(
        sequence,
        sequence[1:],
    ):
        added_score = transition_score(
            previous,
            current,
        )

        if added_score is None:
            return None

        score += added_score

    return score


def rank_character_candidates(
    target: np.ndarray,
    selected_state: State,
    observed: np.ndarray,
    template_bank: dict[str, list[TemplateVariant]],
    shape_masks: dict[str, np.ndarray],
) -> tuple[tuple[str, ...], ...]:
    variant_maps: dict[
        str,
        list[tuple[TemplateVariant, np.ndarray]],
    ] = {}

    for character in ALLOWED_CHARS:
        variant_maps[character] = [
            (
                variant,
                score_map(
                    target,
                    variant.image,
                ),
            )
            for variant in template_bank[
                character
            ]
        ]

    ranked_positions: list[
        tuple[str, ...]
    ] = []

    for index, selected_candidate in enumerate(
        selected_state.sequence
    ):
        alternatives: list[State] = []

        for character in ALLOWED_CHARS:
            maps = variant_maps[
                character
            ]
            seen_centers: set[float] = set()

            for offset in range(
                -CHARACTER_CANDIDATE_CENTER_RADIUS,
                CHARACTER_CANDIDATE_CENTER_RADIUS + 1,
            ):
                anchor_center = (
                    selected_candidate.center
                    + offset
                )

                matched_scores: list[float] = []
                matched_centers: list[float] = []

                for variant, scores in maps:
                    (
                        score,
                        matched_center,
                    ) = aligned_match(
                        scores,
                        variant.width,
                        anchor_center,
                    )
                    matched_scores.append(
                        score
                    )
                    matched_centers.append(
                        matched_center
                    )

                center = float(
                    np.median(
                        matched_centers
                    )
                )

                if center in seen_centers:
                    continue

                seen_centers.add(
                    center
                )

                replacement = Candidate(
                    character=character,
                    center=center,
                    score=float(
                        np.median(
                            matched_scores
                        )
                    ),
                )

                sequence = list(
                    selected_state.sequence
                )
                sequence[index] = replacement
                candidate_sequence = tuple(
                    sequence
                )

                score = sequence_score(
                    candidate_sequence
                )

                if score is None:
                    continue

                alternatives.append(
                    State(
                        score=score,
                        sequence=candidate_sequence,
                    )
                )

        scored = rank_states(
            alternatives,
            observed,
            shape_masks,
        )

        ordered: list[str] = []

        for item in scored:
            character = (
                item.state.sequence[
                    index
                ].character
            )

            if character in ordered:
                continue

            ordered.append(
                character
            )

            if len(ordered) == len(
                ALLOWED_CHARS
            ):
                break

        for character in ALLOWED_CHARS:
            if character not in ordered:
                ordered.append(
                    character
                )

        ranked_positions.append(
            tuple(ordered)
        )

    return tuple(
        ranked_positions
    )


class TemplateRecognizer:
    def __init__(self, template_dir: Path | None = None) -> None:
        self.template_dir = template_dir or TEMPLATE_DIRECTORY
        self._template_bank: dict[str, list[TemplateVariant]] | None = None
        self._shape_masks: dict[str, np.ndarray] | None = None

    def ensure_ready(self) -> None:
        if (
            self._template_bank is not None
            and self._shape_masks is not None
        ):
            return
        bank: dict[str, list[TemplateVariant]] = {}
        shape_masks: dict[str, np.ndarray] = {}
        for character in ALLOWED_CHARS:
            variants: list[TemplateVariant] = []
            for filename in TEMPLATE_FILENAMES[character]:
                path = self.template_dir / filename
                image = cv2.imread(
                    str(path),
                    cv2.IMREAD_GRAYSCALE,
                )
                if image is None:
                    raise RecognitionError(
                        f"Could not load Arena ID template: {filename}"
                    )
                if image.shape[0] != TEMPLATE_ROI_SIZE[1]:
                    raise RecognitionError(
                        "Arena ID template has an unexpected height: "
                        f"{filename}"
                    )
                variants.append(
                    TemplateVariant(
                        image=image,
                        width=image.shape[1],
                    )
                )
            base_filename = f"{character}.png"
            base_path = (
                self.template_dir
                / base_filename
            )
            base_image = cv2.imread(
                str(base_path),
                cv2.IMREAD_COLOR,
            )
            if base_image is None:
                raise RecognitionError(
                    f"Could not load Arena ID template: {base_filename}"
                )
            shape_masks[character] = (
                build_template_shape_mask(
                    base_image
                )
            )
            bank[character] = variants
        self._template_bank = bank
        self._shape_masks = shape_masks

    def _recognize_state(
        self,
        image: np.ndarray,
    ) -> tuple[
        np.ndarray,
        State | None,
        np.ndarray | None,
        float | None,
    ]:
        self.ensure_ready()

        if (
            self._template_bank is None
            or self._shape_masks is None
        ):
            raise RecognitionError(
                "Arena ID templates are not available."
            )

        target = normalize_roi(image)
        candidates = generate_candidates(
            target,
            self._template_bank,
        )
        states = top_sequence_states(
            candidates
        )

        observed: np.ndarray | None = None
        confidence_margin: float | None = None

        if states:
            observed = (
                build_observed_shape_mask(
                    image
                )
            )

            if np.any(observed):
                ranked = rank_states(
                    states,
                    observed,
                    self._shape_masks,
                )

                if ranked:
                    state = ranked[0].state

                    if len(ranked) >= 2:
                        confidence_margin = max(
                            ranked[0].final_score
                            - ranked[1].final_score,
                            0.0,
                        )
                else:
                    state = reconstruct(
                        candidates
                    )
            else:
                state = reconstruct(
                    candidates
                )
        else:
            state = reconstruct(
                candidates
            )

        return (
            target,
            state,
            observed,
            confidence_margin,
        )

    def recognize_with_candidates(
        self,
        image: np.ndarray,
    ) -> TemplateRecognitionResult:
        (
            target,
            state,
            observed,
            confidence_margin,
        ) = self._recognize_state(
            image
        )

        empty_candidates = tuple(
            ()
            for _ in range(
                ARENA_ID_LENGTH
            )
        )

        if state is None:
            return TemplateRecognitionResult(
                text="",
                character_candidates=(
                    empty_candidates
                ),
                confidence_margin=confidence_margin,
            )

        result = state_text(
            state
        )

        if len(result) != ARENA_ID_LENGTH:
            return TemplateRecognitionResult(
                text="",
                character_candidates=(
                    empty_candidates
                ),
                confidence_margin=confidence_margin,
            )

        if (
            observed is None
            or not np.any(observed)
        ):
            return TemplateRecognitionResult(
                text=result,
                character_candidates=tuple(
                    (character,)
                    for character in result
                ),
                confidence_margin=confidence_margin,
            )

        if (
            self._template_bank is None
            or self._shape_masks is None
        ):
            raise RecognitionError(
                "Arena ID templates are not available."
            )

        character_candidates = (
            rank_character_candidates(
                target,
                state,
                observed,
                self._template_bank,
                self._shape_masks,
            )
        )

        return TemplateRecognitionResult(
            text=result,
            character_candidates=(
                character_candidates
            ),
            confidence_margin=confidence_margin,
        )

    def recognize(self, image: np.ndarray) -> str:
        _, state, _, _ = self._recognize_state(
            image
        )

        if state is None:
            return ""

        result = state_text(
            state
        )

        if len(result) != ARENA_ID_LENGTH:
            return ""

        return result
