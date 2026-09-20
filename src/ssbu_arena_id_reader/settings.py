from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".ssbu-arena-id-reader" / "config.json"

MIN_CROP_OFFSET_X = -20
MAX_CROP_OFFSET_X = 0
DEFAULT_CROP_OFFSET_X = 0


@dataclass(frozen=True)
class AppSettings:
    obs_password: str = ""
    obs_source: str = ""
    crop_offset_x: int = DEFAULT_CROP_OFFSET_X


def load_settings(path: Path = CONFIG_PATH) -> AppSettings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return AppSettings()

    if not isinstance(data, dict):
        return AppSettings()

    password = data.get("obs_password")
    source = data.get("obs_source")
    crop_offset_x = data.get("crop_offset_x")

    if (
        type(crop_offset_x) is not int
        or not MIN_CROP_OFFSET_X
        <= crop_offset_x
        <= MAX_CROP_OFFSET_X
    ):
        crop_offset_x = DEFAULT_CROP_OFFSET_X

    return AppSettings(
        obs_password=password if isinstance(password, str) else "",
        obs_source=source if isinstance(source, str) else "",
        crop_offset_x=crop_offset_x,
    )


def save_settings(settings: AppSettings, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "obs_password": settings.obs_password,
        "obs_source": settings.obs_source,
        "crop_offset_x": settings.crop_offset_x,
    }

    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.chmod(0o600)
    temp_path.replace(path)
    path.chmod(0o600)
