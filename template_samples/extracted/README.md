# Extracted Template Workspace

This directory is the default output workspace for `tools/select_template.py`.

The selector used during Arena ID recognizer development manually crops one character from a saved 5-character Arena ID image. It writes:

- `<character>.png` — the selected full-height character crop.
- `<character>.source.txt` — the source image filename followed by the selected left and right pixel coordinates.

Example:

    uv run python tools/select_template.py F template_samples/raw/F1JHY.png

Generated PNG and `.source.txt` files in this directory are development artifacts and are ignored by Git.

Reviewed templates used by the application belong in:

    src/ssbu_arena_id_reader/assets/arena_id_templates/

The `template_samples/raw/` directory remains the local source-image workspace populated by the application's **Save Image** function.
