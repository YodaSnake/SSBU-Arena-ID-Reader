from __future__ import annotations

from dataclasses import dataclass
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


class TemplateRecognizer:
    def __init__(self, template_dir: Path | None = None) -> None:
        self.template_dir = template_dir or TEMPLATE_DIRECTORY
        self._template_bank: dict[str, list[TemplateVariant]] | None = None

    def ensure_ready(self) -> None:
        if self._template_bank is not None:
            return

        bank: dict[str, list[TemplateVariant]] = {}

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

            bank[character] = variants

        self._template_bank = bank

    def recognize(self, image: np.ndarray) -> str:
        self.ensure_ready()

        if self._template_bank is None:
            raise RecognitionError("Arena ID templates are not available.")

        target = normalize_roi(image)
        candidates = generate_candidates(
            target,
            self._template_bank,
        )
        state = reconstruct(candidates)

        if state is None:
            return ""

        result = "".join(
            candidate.character
            for candidate in state.sequence
        )

        if len(result) != ARENA_ID_LENGTH:
            return ""

        return result
