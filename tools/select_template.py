from __future__ import annotations

import argparse
import base64
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import cv2


DISPLAY_SCALE = 5
ALLOWED = "0123456789BCDFGHJKLMNPQRSTVWXY"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("character")
    parser.add_argument("image")
    parser.add_argument(
        "--output-dir",
        default="template_samples/extracted",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    character = args.character.upper()
    if len(character) != 1 or character not in ALLOWED:
        raise SystemExit(
            f"character must be one of: {ALLOWED}"
        )

    source_path = Path(args.image)
    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"could not read image: {source_path}")

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise SystemExit("could not encode source image")

    encoded_data = base64.b64encode(encoded.tobytes()).decode("ascii")

    root = tk.Tk()
    root.title(f"Select template: {character}")

    source = tk.PhotoImage(
        master=root,
        data=encoded_data,
        format="png",
    )
    displayed = source.zoom(DISPLAY_SCALE, DISPLAY_SCALE)

    canvas = tk.Canvas(
        root,
        width=displayed.width(),
        height=displayed.height(),
        highlightthickness=0,
    )
    canvas.pack(padx=12, pady=(12, 4))
    canvas.create_image(0, 0, anchor="nw", image=displayed)

    instruction = tk.Label(
        root,
        text="Drag horizontally across exactly one character.",
    )
    instruction.pack(padx=12, pady=(4, 12))

    selection = {
        "start_x": None,
        "end_x": None,
        "rectangle": None,
    }

    def clamp_x(value: int) -> int:
        return max(0, min(value, displayed.width() - 1))

    def on_press(event) -> None:
        x = clamp_x(event.x)
        selection["start_x"] = x
        selection["end_x"] = x

        if selection["rectangle"] is not None:
            canvas.delete(selection["rectangle"])

        selection["rectangle"] = canvas.create_rectangle(
            x,
            0,
            x,
            displayed.height() - 1,
            outline="red",
            width=2,
        )

    def on_drag(event) -> None:
        if selection["start_x"] is None:
            return

        x = clamp_x(event.x)
        selection["end_x"] = x
        canvas.coords(
            selection["rectangle"],
            selection["start_x"],
            0,
            x,
            displayed.height() - 1,
        )

    def save_selection() -> None:
        if (
            selection["start_x"] is None
            or selection["end_x"] is None
        ):
            messagebox.showerror(
                "Template selector",
                "Select one character first.",
            )
            return

        left_display = min(
            selection["start_x"],
            selection["end_x"],
        )
        right_display = max(
            selection["start_x"],
            selection["end_x"],
        )

        left = left_display // DISPLAY_SCALE
        right = (
            right_display + DISPLAY_SCALE - 1
        ) // DISPLAY_SCALE

        left = max(0, left)
        right = min(image.shape[1], right)

        if right <= left:
            messagebox.showerror(
                "Template selector",
                "The selected range is empty.",
            )
            return

        template = image[:, left:right]

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{character}.png"
        source_info_path = output_dir / f"{character}.source.txt"

        if not cv2.imwrite(str(output_path), template):
            messagebox.showerror(
                "Template selector",
                f"Could not save {output_path}.",
            )
            return

        source_info_path.write_text(
            f"{source_path.name}\n"
            f"{left}\n"
            f"{right}\n",
            encoding="utf-8",
        )

        print(
            f"SAVED character={character} "
            f"source={source_path.name} "
            f"x={left}:{right} "
            f"size={template.shape[1]}x{template.shape[0]} "
            f"path={output_path}"
        )
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)

    button = tk.Button(
        root,
        text="Save Template",
        command=save_selection,
    )
    button.pack(padx=12, pady=(0, 12))

    root.mainloop()


if __name__ == "__main__":
    main()
