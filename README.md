# SSBU Arena ID Reader

SSBU Arena ID Reader reads the 5-character Battle Arena ID from a Super Smash Bros. Ultimate capture source in OBS Studio and copies the recognized ID to the clipboard.

The initial version is deliberately small:

- OBS Studio is the only video input path.
- Pressing **Read ID** captures the selected number of source screenshots from 1 to 5.
- If the selected reads do not produce a stable result, the app automatically takes additional samples one at a time, up to five total reads.
- The Arena ID region is cropped and preprocessed with OpenCV.
- EasyOCR recognizes each sample.
- A strict character-by-character majority vote produces the final ID.
- The result is displayed and copied automatically.
- **Copy** copies the displayed result again without running OCR.
- **Save Sample** saves the latest successful unprocessed Arena ID crop as a lossless PNG for template-reference collection.

## Requirements

- OBS Studio 28 or newer with obs-websocket enabled.
- Python 3.11 or 3.12.
- Internet access for the first EasyOCR model setup only.

The current version has been developed and tested on macOS. Other platforms have not yet been validated.

Arena ID recognition is restricted to the observed 30-character code alphabet `0123456789BCDFGHJKLMNPQRSTVWXY`; `A`, `E`, `I`, `O`, `U`, and `Z` are not treated as valid Arena ID characters.

After the OCR model has been installed locally, normal use does not require Internet access. OBS communication stays on `127.0.0.1:4455`.

After a successful OBS connection, the WebSocket password, selected source, and Reads setting are stored locally in `~/.ssbu-arena-id-reader/config.json` so they do not need to be entered again on every launch. On macOS, the settings file is set to mode `0600`.

The existing sample-count behavior remains supported internally from 1 to 5, including automatic rescue reads up to five total samples, but the current UI does not expose a Reads control.

The OBS Source list refreshes automatically when its dropdown is opened, so there is no separate source-refresh step.

After a captured Arena ID crop is available, it is shown above the OCR result. The Arena ID field is editable, so OCR mistakes can be corrected before pressing **Save Sample**. If OCR cannot produce a valid Arena ID at all, the captured crop remains available and the Arena ID can be entered manually before saving. Samples are stored in the repository-local `template_samples/raw/` directory using the current Arena ID field as the filename, such as `JPQHX.png`. If that name already exists, a numeric suffix such as `JPQHX_002.png` is used instead of overwriting the earlier sample. The raw collection directory is ignored by Git.

## Setup

```bash
uv sync --python 3.11
uv run ssbu-arena-id-reader
```

In OBS, open **Tools > WebSocket Server Settings**, enable the server, and use the default port `4455`. Enter the WebSocket password in SSBU Arena ID Reader, then open the **OBS Source** dropdown. The source list refreshes automatically. Select the capture-card input source itself rather than a composed scene.

## Privacy and local data

- OCR runs locally on the computer.
- OBS communication is limited to `127.0.0.1:4455`.
- The application has no analytics or telemetry.
- The EasyOCR model is downloaded during first-time model setup and is not bundled in this repository.
- The OBS WebSocket password, selected source, and Reads setting are stored locally in `~/.ssbu-arena-id-reader/config.json`.
- Arena ID sample images are written locally to the repository's `template_samples/raw/` directory only when **Save Sample** is pressed.

## Current scope

The Arena ID crop is based on the SSBU 1920x1080 capture layout and scales proportionally for other 16:9 source resolutions. Source-level OBS filters can change the image returned by OBS and may therefore affect recognition.

Direct capture-device access, continuous monitoring, result history, and custom crop configuration are intentionally deferred.

## License

SSBU Arena ID Reader is released under the MIT License. See `LICENSE` for details.
