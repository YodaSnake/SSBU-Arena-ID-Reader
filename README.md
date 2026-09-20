# SSBU Arena ID Reader

SSBU Arena ID Reader reads the 5-character Battle Arena ID from a Super Smash Bros. Ultimate capture source in OBS Studio and copies the recognized ID to the clipboard.

The application is deliberately small:

- OBS Studio is the only video input path.
- Pressing **Read ID** captures one source screenshot by default and accepts a valid 5-character Arena ID immediately.
- The Arena ID region is cropped and normalized with OpenCV.
- A bundled SSBU-specific character template matcher recognizes the crop.
- Shape reranking uses local brightness contrast against a Gaussian-smoothed estimate of the background, which reduces sensitivity to broad brightness changes and bright UI effects behind the text.
- The fixed-size Arena ID crop can be adjusted a small distance horizontally by dragging the red crop outline. Releasing it runs a fresh recognition from OBS.
- The result is displayed and copied automatically.
- **Copy ID** copies the displayed result again without running recognition.
- **Save Image** saves the retained unprocessed Arena ID crop as a lossless PNG for template-reference collection.
- The earlier adaptive 3-to-5-read majority-vote path is retained as a source-level development option and is disabled by default.

## Requirements

- OBS Studio 28 or newer with obs-websocket enabled.
- Python 3.11 or 3.12.

The current version has been developed and tested on macOS. Other platforms have not yet been validated.

Recognition is designed to tolerate moderate differences in brightness and capture appearance, but accuracy may vary depending on the capture device, scaling, capture-device image processing, or OBS filters. Capture devices beyond the development and test setup have not been broadly validated.

Arena ID recognition is restricted to the observed 30-character code alphabet `0123456789BCDFGHJKLMNPQRSTVWXY`; `A`, `E`, `I`, `O`, `U`, and `Z` are not treated as valid Arena ID characters.

Arena ID recognition runs locally and does not require Internet access. OBS communication stays on `127.0.0.1:4455`.

After a successful OBS connection, the WebSocket password, selected source, and horizontal crop offset are stored locally in `~/.ssbu-arena-id-reader/config.json` so they do not need to be entered again on every launch. On macOS, the settings file is set to mode `0600`.

The OBS Source list refreshes automatically when its dropdown is opened, so there is no separate source-refresh step.

After a capture is available, the surrounding Arena ID area is shown above the recognition result and the red outline marks the fixed-size recognition crop. The outline can be dragged horizontally within a small range; releasing it saves the new position and performs a fresh read from OBS. The Arena ID field is editable, so recognition mistakes can be corrected before pressing **Save Image**. If recognition cannot produce a valid Arena ID at all, the captured crop remains available and the Arena ID can be entered manually before saving. Images are stored in the repository-local `template_samples/raw/` directory using the current Arena ID field as the filename, such as `JPQHX.png`. If that name already exists, a numeric suffix such as `JPQHX_002.png` is used instead of overwriting the earlier image. The raw collection directory is ignored by Git.

## Setup

```bash
uv sync --python 3.11
uv run ssbu-arena-id-reader
```

In OBS, open **Tools > WebSocket Server Settings**, enable the server, and use the default port `4455`. Enter the WebSocket password in SSBU Arena ID Reader, then open the **OBS Source** dropdown. The source list refreshes automatically. Select the capture-card input source itself rather than a composed scene.

## Privacy and local data

- Arena ID recognition runs locally on the computer.
- OBS communication is limited to `127.0.0.1:4455`.
- The application has no analytics or telemetry.
- The character templates used for Arena ID recognition are bundled with the application.
- The OBS WebSocket password, selected source, and horizontal crop offset are stored locally in `~/.ssbu-arena-id-reader/config.json`.
- Arena ID sample images are written locally to the repository's `template_samples/raw/` directory only when **Save Image** is pressed.

## Current scope

The Arena ID crop is based on the SSBU 1920x1080 capture layout and scales proportionally for other 16:9 source resolutions. Recognition is not calibrated separately for each capture card. Moderate brightness and capture-appearance differences are expected to be tolerated, but strong sharpening, denoising, rescaling, color processing, compression, or OBS filters that materially alter the glyph shapes can reduce accuracy.

Adaptive multi-read remains available in the source as the development switch `USE_ADAPTIVE_MULTI_READ` and is disabled by default. When enabled, three identical valid reads are accepted early; otherwise recognition continues to five reads and uses a strict character-by-character majority vote.

Direct capture-device access, continuous monitoring, and result history are intentionally deferred. The current crop remains fixed in size and supports only the small horizontal adjustment exposed by the preview.

## License

SSBU Arena ID Reader is released under the MIT License. See `LICENSE` for details.
