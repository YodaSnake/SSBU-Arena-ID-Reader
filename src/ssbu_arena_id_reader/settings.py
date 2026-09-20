from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "SSBU Arena ID Reader"
LEGACY_CONFIG_PATH = Path.home() / ".ssbu-arena-id-reader" / "config.json"

MIN_CROP_OFFSET_X = -20
MAX_CROP_OFFSET_X = 0
DEFAULT_CROP_OFFSET_X = 0


def config_path_for_platform(
    platform: str,
    home: Path,
    appdata: str | None = None,
) -> Path:
    if platform == "darwin":
        base = home / "Library" / "Application Support"
    elif platform == "win32":
        base = (
            Path(appdata)
            if appdata
            else home / "AppData" / "Roaming"
        )
    else:
        base = home / ".config"

    return base / APP_NAME / "config.json"


CONFIG_PATH = config_path_for_platform(
    sys.platform,
    Path.home(),
    os.environ.get("APPDATA"),
)


@dataclass(frozen=True)
class AppSettings:
    obs_password: str = ""
    obs_source: str = ""
    crop_offset_x: int = DEFAULT_CROP_OFFSET_X


def _read_settings(path: Path) -> AppSettings | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

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


def load_settings(
    path: Path | None = None,
    legacy_path: Path | None = None,
) -> AppSettings:
    use_default_path = path is None
    target_path = CONFIG_PATH if path is None else path

    if target_path.exists():
        settings = _read_settings(target_path)
        return settings if settings is not None else AppSettings()

    migration_path = (
        LEGACY_CONFIG_PATH
        if use_default_path and legacy_path is None
        else legacy_path
    )

    if migration_path is None:
        return AppSettings()

    settings = _read_settings(migration_path)

    if settings is None:
        return AppSettings()

    try:
        save_settings(settings, target_path)
    except OSError:
        pass

    return settings


def save_settings(
    settings: AppSettings,
    path: Path | None = None,
) -> None:
    target_path = CONFIG_PATH if path is None else path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "obs_password": settings.obs_password,
        "obs_source": settings.obs_source,
        "crop_offset_x": settings.crop_offset_x,
    }

    temp_path = target_path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.chmod(0o600)
    temp_path.replace(target_path)
    target_path.chmod(0o600)
