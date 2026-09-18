from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk

from .obs_client import ObsClient, ObsError
from .recognition import (
    EasyOcrRecognizer,
    RecognitionError,
    character_majority,
    decode_png,
    preprocess_frame,
)
from .settings import MAX_SAMPLE_COUNT, AppSettings, load_settings, save_settings

SAMPLE_COUNT_OPTIONS = tuple(str(count) for count in range(1, MAX_SAMPLE_COUNT + 1))
SAMPLE_INTERVAL_SECONDS = 0.15


class ArenaIdApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.recognizer = EasyOcrRecognizer()
        settings = load_settings()
        self.password_var = tk.StringVar(value=settings.obs_password)
        self.source_var = tk.StringVar(value=settings.obs_source)
        self.sample_count_var = tk.StringVar(value=str(settings.sample_count))
        self.result_var = tk.StringVar()

        if settings.obs_password and settings.obs_source:
            initial_status = "Ready."
        elif settings.obs_password:
            initial_status = "Open OBS Source to choose a capture source."
        else:
            initial_status = "Enter the OBS WebSocket password, then open OBS Source."

        self.status_var = tk.StringVar(value=initial_status)
        self._refreshing_sources = False

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

        ttk.Label(frame, text="Reads").grid(row=4, column=0, sticky="w")
        self.sample_count_box = ttk.Combobox(
            frame,
            textvariable=self.sample_count_var,
            values=SAMPLE_COUNT_OPTIONS,
            state="readonly",
            width=31,
        )
        self.sample_count_box.grid(row=5, column=0, sticky="ew", pady=(4, 16))

        self.read_button = ttk.Button(
            frame,
            text="Read ID",
            command=self._read_id,
        )
        self.read_button.grid(row=6, column=0, sticky="ew", pady=(0, 16))

        ttk.Label(frame, text="Arena ID").grid(row=7, column=0, sticky="w")
        result_row = ttk.Frame(frame)
        result_row.grid(row=8, column=0, sticky="ew", pady=(4, 12))

        ttk.Entry(
            result_row,
            textvariable=self.result_var,
            state="readonly",
            justify="center",
            width=22,
        ).grid(row=0, column=0, sticky="ew")

        self.copy_button = ttk.Button(
            result_row,
            text="Copy",
            command=self._copy_result,
        )
        self.copy_button.grid(row=0, column=1, padx=(8, 0))

        ttk.Label(
            frame,
            textvariable=self.status_var,
            wraplength=320,
        ).grid(row=9, column=0, sticky="w")

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

        self._set_busy(True)
        try:
            self.status_var.set("Preparing OCR model...")
            self.root.update_idletasks()
            self.recognizer.ensure_ready()

            initial_reads = int(self.sample_count_var.get())
            candidates: list[str] = []
            arena_id: str | None = None

            with ObsClient(self.password_var.get()) as client:
                for index in range(MAX_SAMPLE_COUNT):
                    read_number = index + 1
                    self.status_var.set(f"Reading sample {read_number}...")
                    self.root.update_idletasks()

                    screenshot = client.get_source_screenshot(source_name)
                    frame = decode_png(screenshot)
                    candidate = self.recognizer.recognize(
                        preprocess_frame(frame)
                    )
                    candidates.append(candidate)

                    if read_number >= initial_reads:
                        try:
                            arena_id = character_majority(candidates)
                        except RecognitionError:
                            if read_number == MAX_SAMPLE_COUNT:
                                raise
                        else:
                            break

                    if read_number < MAX_SAMPLE_COUNT:
                        time.sleep(SAMPLE_INTERVAL_SECONDS)

            if arena_id is None:
                raise RecognitionError(
                    "OCR samples did not reach a stable character majority."
                )

            read_count = len(candidates)
            read_label = "read" if read_count == 1 else "reads"

            self.result_var.set(arena_id)
            self._copy_to_clipboard(arena_id)
            self._save_settings()
            self.status_var.set(
                f"Copied {arena_id} to the clipboard "
                f"({read_count} {read_label})."
            )
        except (ObsError, RecognitionError) as exc:
            self._show_error(str(exc))
        except Exception as exc:
            self._show_error(f"Unexpected error: {exc}")
        finally:
            self._set_busy(False)

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
                sample_count=int(self.sample_count_var.get()),
            )
        )

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.read_button.configure(state=state)
        self.copy_button.configure(state=state)

    def _show_error(self, message: str) -> None:
        self.status_var.set(message)
        messagebox.showerror("SSBU Arena ID Reader", message)


def main() -> None:
    root = tk.Tk()
    ArenaIdApp(root)
    root.mainloop()
