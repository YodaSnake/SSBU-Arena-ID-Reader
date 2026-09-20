from __future__ import annotations

import base64
import time
import tkinter as tk
from tkinter import messagebox, ttk

import cv2

from .obs_client import ObsClient, ObsError
from .recognition import (
    ALLOWED_CHARS,
    ARENA_ID_LENGTH,
    ROI_1080P,
    ROI_BASE_SIZE,
    RecognitionError,
    character_majority,
    decode_png,
    extract_arena_id_roi,
)
from .sample_collection import SampleCollectionError, save_template_sample
from .template_recognizer import TemplateRecognizer
from .settings import (
    MAX_CROP_OFFSET_X,
    MIN_CROP_OFFSET_X,
    AppSettings,
    load_settings,
    save_settings,
)

SAMPLE_INTERVAL_SECONDS = 0.10
USE_ADAPTIVE_MULTI_READ = False
CONFIDENCE_MARGIN_THRESHOLD = 0.015
STABLE_READ_COUNT = 3
MAX_READ_COUNT = 5
MAX_DISPLAYED_CHARACTER_CANDIDATES = 10

CROP_CONTEXT_1080P = (
    1765,
    100,
    1920,
    130,
)
CROP_PREVIEW_SCALE = 2
CROP_BOX_OUTLINE_INSET = 2
CROP_BOX_OUTLINE_WIDTH = 3
CROP_CONTEXT_WIDTH = (
    CROP_CONTEXT_1080P[2]
    - CROP_CONTEXT_1080P[0]
)
CROP_CONTEXT_HEIGHT = (
    CROP_CONTEXT_1080P[3]
    - CROP_CONTEXT_1080P[1]
)


class ArenaIdApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.recognizer = TemplateRecognizer()

        settings = load_settings()

        self.password_var = tk.StringVar(value=settings.obs_password)
        self.source_var = tk.StringVar(value=settings.obs_source)
        self.crop_offset_x = settings.crop_offset_x
        self.result_var = tk.StringVar()
        self.candidate_vars = [
            tk.StringVar()
            for _ in range(
                ARENA_ID_LENGTH
            )
        ]

        if settings.obs_password and settings.obs_source:
            initial_status = "Ready."
        elif settings.obs_password:
            initial_status = "Open OBS Source to choose a capture source."
        else:
            initial_status = "Enter the OBS WebSocket password, then open OBS Source."

        self.status_var = tk.StringVar(value=initial_status)

        self._refreshing_sources = False
        self._last_sample_roi = None
        self._last_sample_frame = None
        self._crop_preview_image = None
        self._crop_preview_item = None
        self._crop_box_item = None
        self._crop_adjustment_enabled = True
        self._crop_drag_anchor_x = None
        self._crop_drag_origin_x = None

        self.root.title("SSBU Arena ID Reader")
        self.root.resizable(False, False)

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0)

        ttk.Label(frame, text="OBS WebSocket Password").grid(
            row=0, column=0, sticky="w"
        )

        ttk.Entry(
            frame,
            textvariable=self.password_var,
            show="•",
            width=34,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(frame, text="OBS Source").grid(row=2, column=0, sticky="w")

        self.source_box = ttk.Combobox(
            frame,
            textvariable=self.source_var,
            state="readonly",
            width=31,
            postcommand=self._refresh_sources,
        )
        self.source_box.grid(row=3, column=0, sticky="ew", pady=(4, 12))

        self.read_button = ttk.Button(
            frame,
            text="Read ID",
            command=self._read_id,
            default="active",
        )
        self.read_button.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(0, 12),
            ipady=6,
        )
        self.root.bind(
            "<Return>",
            lambda _event: self.read_button.invoke(),
        )

        self.crop_canvas = tk.Canvas(
            frame,
            width=(
                CROP_CONTEXT_WIDTH
                * CROP_PREVIEW_SCALE
            ),
            height=(
                CROP_CONTEXT_HEIGHT
                * CROP_PREVIEW_SCALE
            ),
            highlightthickness=1,
        )
        self.crop_canvas.grid(
            row=5,
            column=0,
            pady=(0, 6),
        )

        self._crop_box_item = (
            self.crop_canvas.create_rectangle(
                *self._crop_box_canvas_coords(),
                outline="red",
                width=CROP_BOX_OUTLINE_WIDTH,
            )
        )

        self.crop_canvas.bind(
            "<ButtonPress-1>",
            self._on_crop_drag_start,
        )
        self.crop_canvas.bind(
            "<B1-Motion>",
            self._on_crop_drag_motion,
        )
        self.crop_canvas.bind(
            "<ButtonRelease-1>",
            self._on_crop_drag_release,
        )

        self.reset_crop_button = ttk.Button(
            frame,
            text="Reset Crop",
            command=self._reset_crop,
        )

        self.save_sample_button = ttk.Button(
            frame,
            text="Save Image",
            command=self._save_sample,
            state="disabled",
        )
        self.save_sample_button.grid(
            row=6,
            column=0,
            sticky="w",
            pady=(0, 12),
        )

        ttk.Label(frame, text="Arena ID").grid(row=7, column=0, sticky="w")

        result_row = ttk.Frame(frame)
        result_row.grid(row=8, column=0, sticky="ew", pady=(4, 12))

        ttk.Entry(
            result_row,
            textvariable=self.result_var,
            justify="center",
            width=22,
        ).grid(row=0, column=0, sticky="ew")

        self.copy_button = ttk.Button(
            result_row,
            text="Copy ID",
            command=self._copy_result,
        )
        self.copy_button.grid(row=0, column=1, padx=(8, 0))

        ttk.Label(
            frame,
            text="Character Candidates",
        ).grid(
            row=9,
            column=0,
            sticky="w",
        )

        candidate_row = ttk.Frame(frame)
        candidate_row.grid(
            row=10,
            column=0,
            sticky="w",
            pady=(4, 12),
        )

        self.candidate_boxes = []

        for index, variable in enumerate(
            self.candidate_vars
        ):
            box = ttk.Combobox(
                candidate_row,
                textvariable=variable,
                state="readonly",
                width=3,
                justify="center",
            )
            box.grid(
                row=0,
                column=index,
                padx=(
                    0 if index == 0 else 4,
                    0,
                ),
            )
            box.bind(
                "<<ComboboxSelected>>",
                self._candidate_selected,
            )
            self.candidate_boxes.append(
                box
            )

        ttk.Label(
            frame,
            textvariable=self.status_var,
            wraplength=420,
        ).grid(
            row=11,
            column=0,
            sticky="w",
        )

    def _refresh_sources(self) -> None:
        if self._refreshing_sources:
            return

        self._refreshing_sources = True
        self.status_var.set("Refreshing OBS sources...")
        self.root.update_idletasks()

        try:
            with ObsClient(self.password_var.get()) as client:
                sources = client.list_inputs()

            self.source_box["values"] = sources

            if sources:
                if self.source_var.get() not in sources:
                    self.source_var.set(sources[0])

                self._save_settings()
                self.status_var.set(f"Found {len(sources)} OBS input source(s).")
            else:
                self.source_var.set("")
                self.status_var.set("OBS returned no input sources.")

        except ObsError as exc:
            self.status_var.set(f"Could not refresh OBS sources: {exc}")
        finally:
            self._refreshing_sources = False

    def _read_id(self) -> None:
        source_name = self.source_var.get()

        if not source_name:
            self._show_error("Select an OBS source first.")
            return

        self._last_sample_roi = None
        self._last_sample_frame = None
        self.result_var.set("")
        self._clear_character_candidates()
        self._set_busy(True)

        try:
            self.status_var.set("Preparing Arena ID recognizer...")
            self.root.update_idletasks()

            self.recognizer.ensure_ready()

            candidates: list[str] = []
            samples = []
            arena_id: str | None = None
            latest_roi = None
            first_recognition = None

            with ObsClient(self.password_var.get()) as client:
                for index in range(MAX_READ_COUNT):
                    read_number = index + 1

                    self.status_var.set(f"Reading sample {read_number}...")
                    self.root.update_idletasks()

                    screenshot = client.get_source_screenshot(source_name)
                    frame = decode_png(screenshot)
                    latest_roi = extract_arena_id_roi(
                        frame,
                        crop_offset_x=self.crop_offset_x,
                    )

                    self._last_sample_frame = frame
                    self._last_sample_roi = latest_roi
                    self._show_crop_adjustment_preview(
                        frame
                    )
                    self.root.update_idletasks()

                    if (
                        not USE_ADAPTIVE_MULTI_READ
                        and read_number == 1
                    ):
                        first_recognition = (
                            self.recognizer
                            .recognize_with_candidates(
                                latest_roi
                            )
                        )
                        candidate = (
                            first_recognition.text
                        )
                    else:
                        candidate = (
                            self.recognizer.recognize(
                                latest_roi
                            )
                        )

                    candidates.append(candidate)
                    samples.append(
                        (
                            candidate,
                            latest_roi,
                            frame,
                        )
                    )

                    if (
                        not USE_ADAPTIVE_MULTI_READ
                        and read_number == 1
                    ):
                        valid_candidate = (
                            len(candidate)
                            == ARENA_ID_LENGTH
                            and all(
                                character
                                in ALLOWED_CHARS
                                for character
                                in candidate
                            )
                        )
                        confidence_margin = (
                            first_recognition
                            .confidence_margin
                        )

                        if (
                            valid_candidate
                            and confidence_margin
                            is not None
                            and confidence_margin
                            >= CONFIDENCE_MARGIN_THRESHOLD
                        ):
                            arena_id = candidate
                            break

                    if read_number == STABLE_READ_COUNT:
                        stable_candidate = candidates[0]

                        if (
                            len(stable_candidate) == ARENA_ID_LENGTH
                            and all(
                                candidate == stable_candidate
                                for candidate in candidates
                            )
                        ):
                            arena_id = stable_candidate
                            break

                    if read_number == MAX_READ_COUNT:
                        arena_id = character_majority(
                            candidates
                        )
                        break

                    time.sleep(SAMPLE_INTERVAL_SECONDS)

            if arena_id is None:
                raise RecognitionError(
                    "Recognition samples did not reach a stable character majority."
                )

            if latest_roi is None:
                raise RecognitionError("No Arena ID sample image was captured.")

            representative_index = (
                self._select_representative_read_index(
                    samples,
                    arena_id,
                )
            )
            (
                _,
                representative_roi,
                representative_frame,
            ) = samples[
                representative_index
            ]

            self._last_sample_frame = (
                representative_frame
            )
            self._last_sample_roi = (
                representative_roi
            )

            if representative_index != len(samples) - 1:
                self._show_crop_adjustment_preview(
                    representative_frame
                )
                self.root.update_idletasks()

            if (
                representative_index == 0
                and first_recognition is not None
            ):
                recognition = first_recognition
            else:
                recognition = (
                    self.recognizer
                    .recognize_with_candidates(
                        representative_roi
                    )
                )
            latest_character_candidates = (
                recognition.character_candidates
            )

            read_count = len(candidates)
            read_label = "read" if read_count == 1 else "reads"

            self.result_var.set(arena_id)
            self._set_character_candidates(
                arena_id,
                latest_character_candidates,
            )
            self._copy_to_clipboard(arena_id)
            self._save_settings()

            self.status_var.set(
                f"Copied {arena_id} to the clipboard "
                f"({read_count} {read_label})."
            )

        except RecognitionError as exc:
            if self._last_sample_roi is not None:
                self._show_error(
                    f"{exc}\n\n"
                    "The captured crop is still available. "
                    "Enter the Arena ID manually and press Save Image."
                )
            else:
                self._show_error(str(exc))

        except ObsError as exc:
            self._show_error(str(exc))
        except Exception as exc:
            self._show_error(f"Unexpected error: {exc}")
        finally:
            self._set_busy(False)

    def _select_representative_read_index(
        self,
        samples,
        arena_id: str,
    ) -> int:
        if not samples:
            raise RecognitionError(
                "No Arena ID sample image was captured."
            )

        def ranking(index: int) -> tuple[bool, int, int]:
            candidate = samples[index][0]

            if len(candidate) == ARENA_ID_LENGTH:
                agreement = sum(
                    candidate[position]
                    == arena_id[position]
                    for position in range(
                        ARENA_ID_LENGTH
                    )
                )
            else:
                agreement = -1

            return (
                candidate == arena_id,
                agreement,
                index,
            )

        return max(
            range(len(samples)),
            key=ranking,
        )

    def _crop_box_canvas_coords(
        self,
    ) -> tuple[int, int, int, int]:
        context_left, context_top, _, _ = (
            CROP_CONTEXT_1080P
        )
        roi_left, roi_top, roi_right, roi_bottom = (
            ROI_1080P
        )

        left = (
            (
                roi_left
                + self.crop_offset_x
                - context_left
            )
            * CROP_PREVIEW_SCALE
        )
        right = (
            (
                roi_right
                + self.crop_offset_x
                - context_left
            )
            * CROP_PREVIEW_SCALE
        )
        canvas_width = (
            CROP_CONTEXT_WIDTH
            * CROP_PREVIEW_SCALE
        )
        canvas_height = (
            CROP_CONTEXT_HEIGHT
            * CROP_PREVIEW_SCALE
        )

        return (
            max(
                CROP_BOX_OUTLINE_INSET,
                left,
            ),
            CROP_BOX_OUTLINE_INSET,
            min(
                canvas_width
                - CROP_BOX_OUTLINE_INSET,
                right,
            ),
            canvas_height
            - CROP_BOX_OUTLINE_INSET,
        )

    def _update_crop_box(self) -> None:
        if self._crop_box_item is not None:
            self.crop_canvas.coords(
                self._crop_box_item,
                *self._crop_box_canvas_coords(),
            )

    def _crop_context_image(
        self,
        frame,
    ):
        if frame is None or frame.size == 0:
            raise RecognitionError(
                "The capture frame is empty."
            )

        height, width = frame.shape[:2]
        base_width, base_height = ROI_BASE_SIZE
        x1, y1, x2, y2 = CROP_CONTEXT_1080P

        left = round(width * x1 / base_width)
        top = round(height * y1 / base_height)
        right = round(width * x2 / base_width)
        bottom = round(height * y2 / base_height)

        context = frame[
            top:bottom,
            left:right,
        ]

        if context.size == 0:
            raise RecognitionError(
                "The crop adjustment preview is empty."
            )

        interpolation = (
            cv2.INTER_AREA
            if (
                context.shape[1] > CROP_CONTEXT_WIDTH
                or context.shape[0] > CROP_CONTEXT_HEIGHT
            )
            else cv2.INTER_CUBIC
        )

        return cv2.resize(
            context,
            (
                CROP_CONTEXT_WIDTH,
                CROP_CONTEXT_HEIGHT,
            ),
            interpolation=interpolation,
        )

    def _show_crop_adjustment_preview(
        self,
        frame,
    ) -> None:
        context = self._crop_context_image(
            frame
        )

        try:
            encoded_ok, encoded = cv2.imencode(
                ".png",
                context,
            )
        except cv2.error as exc:
            raise RecognitionError(
                "Could not prepare the crop adjustment preview."
            ) from exc

        if not encoded_ok:
            raise RecognitionError(
                "Could not prepare the crop adjustment preview."
            )

        encoded_data = base64.b64encode(
            encoded.tobytes()
        ).decode("ascii")

        source_image = tk.PhotoImage(
            master=self.root,
            data=encoded_data,
            format="png",
        )

        self._crop_preview_image = (
            source_image.zoom(
                CROP_PREVIEW_SCALE,
                CROP_PREVIEW_SCALE,
            )
        )

        if self._crop_preview_item is None:
            self._crop_preview_item = (
                self.crop_canvas.create_image(
                    0,
                    0,
                    anchor="nw",
                    image=self._crop_preview_image,
                )
            )
        else:
            self.crop_canvas.itemconfigure(
                self._crop_preview_item,
                image=self._crop_preview_image,
            )

        self.crop_canvas.tag_lower(
            self._crop_preview_item
        )
        self._update_crop_box()

    def _on_crop_drag_start(
        self,
        event,
    ) -> None:
        if (
            not self._crop_adjustment_enabled
            or self._last_sample_frame is None
        ):
            return

        (
            left,
            top,
            right,
            bottom,
        ) = self._crop_box_canvas_coords()

        if not (
            left <= event.x <= right
            and top <= event.y <= bottom
        ):
            return

        self._crop_drag_anchor_x = event.x
        self._crop_drag_origin_x = (
            self.crop_offset_x
        )

    def _on_crop_drag_motion(
        self,
        event,
    ) -> None:
        if (
            self._crop_drag_anchor_x is None
            or self._crop_drag_origin_x is None
        ):
            return

        delta_x = round(
            (
                event.x
                - self._crop_drag_anchor_x
            )
            / CROP_PREVIEW_SCALE
        )

        self.crop_offset_x = min(
            MAX_CROP_OFFSET_X,
            max(
                MIN_CROP_OFFSET_X,
                self._crop_drag_origin_x
                + delta_x,
            ),
        )

        self._update_crop_box()

    def _on_crop_drag_release(
        self,
        event,
    ) -> None:
        if (
            self._crop_drag_anchor_x is None
            or self._crop_drag_origin_x is None
        ):
            return

        original_offset_x = (
            self._crop_drag_origin_x
        )

        self._on_crop_drag_motion(
            event
        )

        self._crop_drag_anchor_x = None
        self._crop_drag_origin_x = None

        if self.crop_offset_x != original_offset_x:
            self._save_settings()
            self._read_id()

    def _reset_crop(self) -> None:
        self.crop_offset_x = 0
        self._update_crop_box()

        if self._last_sample_frame is None:
            self._save_settings()
            self.status_var.set(
                "Crop position reset to default."
            )
            return

        self._save_settings()
        self._read_id()

    def _save_sample(self) -> None:
        arena_id = self.result_var.get().strip().upper()

        if not arena_id or self._last_sample_roi is None:
            self._show_error("Read an Arena ID before saving a sample.")
            return

        self.result_var.set(arena_id)

        try:
            sample_path = save_template_sample(
                self._last_sample_roi,
                arena_id,
            )
        except SampleCollectionError as exc:
            self._show_error(str(exc))
            return

        self._last_sample_roi = None
        self.save_sample_button.configure(
            state="disabled"
        )
        self.status_var.set(f"Saved Arena ID sample to {sample_path}")

    def _clear_character_candidates(self) -> None:
        for variable, box in zip(
            self.candidate_vars,
            self.candidate_boxes,
        ):
            variable.set("")
            box["values"] = ()

    def _set_character_candidates(
        self,
        arena_id: str,
        candidates: tuple[
            tuple[str, ...],
            ...,
        ],
    ) -> None:
        for index, (
            variable,
            box,
        ) in enumerate(
            zip(
                self.candidate_vars,
                self.candidate_boxes,
            )
        ):
            selected = (
                arena_id[index]
                if index < len(arena_id)
                else ""
            )

            options = (
                list(
                    candidates[index][
                        :MAX_DISPLAYED_CHARACTER_CANDIDATES
                    ]
                )
                if index < len(candidates)
                else []
            )

            if (
                selected
                and selected not in options
            ):
                options = [
                    selected,
                    *options[
                        :MAX_DISPLAYED_CHARACTER_CANDIDATES
                        - 1
                    ],
                ]

            box["values"] = tuple(
                options
            )
            variable.set(selected)

    def _candidate_selected(
        self,
        _event=None,
    ) -> None:
        characters = [
            variable.get()
            for variable in self.candidate_vars
        ]

        if (
            len(characters) != ARENA_ID_LENGTH
            or any(
                len(character) != 1
                or character not in ALLOWED_CHARS
                for character in characters
            )
        ):
            return

        arena_id = "".join(
            characters
        )

        self.result_var.set(
            arena_id
        )
        self._copy_to_clipboard(
            arena_id
        )
        self.status_var.set(
            f"Copied {arena_id} to the clipboard."
        )

    def _copy_result(self) -> None:
        arena_id = self.result_var.get()

        if not arena_id:
            self._show_error("There is no Arena ID to copy yet.")
            return

        self._copy_to_clipboard(arena_id)
        self.status_var.set(f"Copied {arena_id} to the clipboard.")

    def _copy_to_clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def _save_settings(self) -> None:
        save_settings(
            AppSettings(
                obs_password=self.password_var.get(),
                obs_source=self.source_var.get(),
                crop_offset_x=self.crop_offset_x,
            )
        )

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self._crop_adjustment_enabled = not busy
        self.read_button.configure(state=state)
        self.copy_button.configure(state=state)
        self.reset_crop_button.configure(
            state=state
        )
        self.save_sample_button.configure(
            state=(
                "disabled"
                if busy or self._last_sample_roi is None
                else "normal"
            )
        )

        candidate_state = (
            "disabled"
            if busy
            else "readonly"
        )

        for box in self.candidate_boxes:
            box.configure(
                state=candidate_state
            )

    def _show_error(self, message: str) -> None:
        self.status_var.set(message)
        messagebox.showerror("SSBU Arena ID Reader", message)


def main() -> None:
    root = tk.Tk()
    ArenaIdApp(root)
    root.mainloop()
