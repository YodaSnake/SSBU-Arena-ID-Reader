# SSBU Arena ID Reader

SSBU Arena ID Reader reads the 5-character Battle Arena ID from a Super Smash Bros. Ultimate capture source in OBS Studio and copies the recognized ID to the clipboard.

The application is deliberately small:

- OBS Studio is the only video input path.
- Pressing **Read ID** captures one source screenshot first. A clearly separated valid recognition is accepted immediately; an ambiguous or invalid first result automatically falls back to the adaptive multi-read path.
- The Arena ID region is cropped and normalized with OpenCV.
- A bundled SSBU-specific character template matcher recognizes the crop.
- Shape reranking uses local brightness contrast against a Gaussian-smoothed estimate of the background, which reduces sensitivity to broad brightness changes and bright UI effects behind the text.
- The fixed-size Arena ID crop can be adjusted a small distance horizontally by dragging the red crop outline. Releasing it runs a fresh recognition from OBS.
- The result is displayed and copied automatically.
- **Copy ID** copies the displayed result again without running recognition.
- **Save Image** saves the retained unprocessed Arena ID crop as a lossless PNG for template-reference collection.
- The adaptive 3-to-5-read majority-vote path is used automatically for ambiguous or invalid first reads, and a source-level development switch can force that path for every read.

## Requirements

- OBS Studio 28 or newer with obs-websocket enabled.
- Python 3.11 or 3.12.

The current version has been developed and tested on macOS. Other platforms have not yet been validated.

Recognition is designed to tolerate moderate differences in brightness and capture appearance, but accuracy may vary depending on the capture device, scaling, capture-device image processing, or OBS filters. Capture devices beyond the development and test setup have not been broadly validated.

Arena ID recognition is restricted to the observed 30-character code alphabet `0123456789BCDFGHJKLMNPQRSTVWXY`; `A`, `E`, `I`, `O`, `U`, and `Z` are not treated as valid Arena ID characters.

Arena ID recognition runs locally and does not require Internet access. OBS communication stays on `127.0.0.1:4455`.

After a successful OBS connection, the WebSocket password, selected source, and horizontal crop offset are stored in the operating system's per-user application-data location so they do not need to be entered again on every launch. On macOS this is `~/Library/Application Support/SSBU Arena ID Reader/config.json`; on Windows it is `%APPDATA%\SSBU Arena ID Reader\config.json`. Existing macOS development settings from `~/.ssbu-arena-id-reader/config.json` are migrated automatically when the new settings file does not yet exist, without deleting the legacy file. On macOS, the settings file is set to mode `0600`.

The OBS Source list refreshes automatically when its dropdown is opened, so there is no separate source-refresh step.

After a capture is available, the surrounding Arena ID area is shown above the recognition result and the red outline marks the fixed-size recognition crop. The outline can be dragged horizontally within a small range; releasing it saves the new position and performs a fresh read from OBS. The Arena ID field is editable, so recognition mistakes can be corrected before pressing **Save Image**. If recognition cannot produce a valid Arena ID at all, the captured crop remains available and the Arena ID can be entered manually before saving. During development from source, images are stored in the repository-local `template_samples/raw/` directory. In a packaged build, they are stored in `template_samples/raw/` beside the distributed executable or `.app`. The current Arena ID field is used as the filename, such as `JPQHX.png`. If that name already exists, a numeric suffix such as `JPQHX_002.png` is used instead of overwriting the earlier image. The development raw collection directory is ignored by Git.

## Setup

```bash
uv sync --python 3.11
uv run ssbu-arena-id-reader
```

In OBS, open **Tools > WebSocket Server Settings**, enable the server, and use the default port `4455`. Enter the WebSocket password in SSBU Arena ID Reader, then open the **OBS Source** dropdown. The source list refreshes automatically. Select the capture-card input source itself rather than a composed scene.

## Build a macOS app

The repository includes a PyInstaller specification for building a native macOS `.app` bundle for the architecture of the Mac performing the build.

```bash
uv sync --python 3.11
uv run pyinstaller \
  --noconfirm \
  --clean \
  --distpath dist \
  --workpath .ep-work/pyinstaller-macos \
  installer/ssbu_arena_id_reader_macos.spec
```

The resulting application is `dist/SSBU Arena ID Reader.app`. The character templates required by the recognizer are bundled inside the application, so the packaged app does not require a separate Python installation.

The current macOS packaged build has been built and exercised on Apple silicon, including OBS Arena ID recognition and **Save Image**. It is architecture-specific and is not currently distributed with an Apple Developer ID signature or notarization.

When **Save Image** is used from the packaged application, `template_samples/raw/` is created beside `SSBU Arena ID Reader.app`. Keep the application in a location where files can be created beside it if sample collection is needed.

## Recognition algorithm

The recognizer is specialized for the fixed 5-character SSBU Arena ID display rather than using a general-purpose OCR model. Given the same saved crop, recognition is deterministic and does not require a learned model or network service.

The pipeline is roughly:

1. Crop the Arena ID area from the OBS source and normalize it to `130x30`.
2. Match templates for the observed 30-character Arena ID alphabet with normalized cross-correlation (NCC), retaining multiple character candidates and positions.
3. Build plausible 5-character sequences using character-spacing constraints. The first-to-second-character transition is modeled separately because the development corpus showed that it can be narrower than later transitions. The current first-transition minimum/target are `9.5`/`17.0` pixels; later transitions use `12.0`/`19.0`.
4. Build an observed foreground-shape mask from local lightness contrast relative to a Gaussian-smoothed background. This reduces sensitivity to broad brightness changes and bright animated UI effects behind the text.
5. Render candidate sequence shapes and rerank them using Dice overlap and Chamfer-distance similarity together with the NCC sequence score.
6. Compare the top two final sequence scores. A valid result with a score margin of at least `0.015` is accepted immediately; a smaller or unavailable margin falls back to adaptive multi-read confirmation.

Adaptive multi-read accepts three identical valid reads early. Otherwise it continues to five reads and uses a strict character-by-character majority vote.

These constants are empirical parameters for the current SSBU display and development capture corpus. The score margin is not a calibrated probability or a general OCR confidence percentage.

## Development corpus and template tooling

The raw development/regression corpus is distributed separately in the Raw Corpus v1 GitHub release rather than being stored in Git history:

https://github.com/YodaSnake/SSBU-Arena-ID-Reader/releases/tag/raw-corpus-v1

Raw Corpus v1 contains 107 lossless `130x30` PNG Arena ID crops. Each filename records the expected 5-character Arena ID, with suffixes such as `_002` distinguishing repeated captures of the same ID. The archive also contains a SHA-256 manifest.

Archive SHA-256: `c6dc8ed96c02396c9f62abdb2354d64a153020ffcc74e564545ebc44333269e0`

At commit `4d08de2cb9f4a221e83c0178a8387f2de9897e30`, the production `TemplateRecognizer` path reads all 107 named corpus samples correctly. Because this corpus was used during development and tuning, that result is a regression check rather than an independent benchmark or a claim about arbitrary capture hardware.

Additional raw crops can be collected with **Save Image**. Source-development runs write them to the ignored repository-local `template_samples/raw/` directory; packaged builds create the same relative directory beside the distributed executable or `.app`.

`tools/select_template.py` is the manual template-selection utility used during recognizer development. It displays a saved 5-character raw crop, lets a developer drag horizontally across one character, and writes the selected crop plus source-coordinate metadata to `template_samples/extracted/`. Reviewed templates used by the application live in `src/ssbu_arena_id_reader/assets/arena_id_templates/`.

## Privacy and local data

- Arena ID recognition runs locally on the computer.
- OBS communication is limited to `127.0.0.1:4455`.
- The application has no analytics or telemetry.
- The character templates used for Arena ID recognition are bundled with the application.
- The OBS WebSocket password, selected source, and horizontal crop offset are stored locally in `~/.ssbu-arena-id-reader/config.json`.
- Arena ID sample images are written locally only when **Save Image** is pressed. Source-development runs use the repository's `template_samples/raw/` directory; packaged builds use `template_samples/raw/` beside the distributed executable or `.app`.

## Current scope

The Arena ID crop is based on the SSBU 1920x1080 capture layout and scales proportionally for other 16:9 source resolutions. Recognition is not calibrated separately for each capture card. Moderate brightness and capture-appearance differences are expected to be tolerated, but strong sharpening, denoising, rescaling, color processing, compression, or OBS filters that materially alter the glyph shapes can reduce accuracy.

By default, the first valid recognition is accepted immediately when the final ranking-score margin between the top two sequence candidates is at least `0.015`. A smaller margin, a missing margin, or an invalid first result falls back to adaptive multi-read. This margin is a ranking-score separation, not a probability or calibrated confidence percentage.

The source-level development switch `USE_ADAPTIVE_MULTI_READ` can force adaptive multi-read for every recognition. In adaptive mode, three identical valid reads are accepted early; otherwise recognition continues to five reads and uses a strict character-by-character majority vote.

Direct capture-device access, continuous monitoring, and result history are intentionally deferred. The current crop remains fixed in size and supports only the small horizontal adjustment exposed by the preview.

## License

SSBU Arena ID Reader is released under the MIT License. See `LICENSE` for details.
