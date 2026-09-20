import stat

from ssbu_arena_id_reader.settings import (
    AppSettings,
    config_path_for_platform,
    load_settings,
    save_settings,
)


def test_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "nested" / "config.json"
    settings = AppSettings(
        obs_password="example-password",
        obs_source="キャプボ",
        crop_offset_x=-12,
    )

    save_settings(settings, path)

    assert load_settings(path) == settings
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_missing_settings_return_defaults(tmp_path) -> None:
    path = tmp_path / "missing.json"

    assert load_settings(path) == AppSettings()


def test_invalid_settings_return_defaults(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{not-json", encoding="utf-8")

    assert load_settings(path) == AppSettings()


def test_invalid_crop_offset_returns_default(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        '{"crop_offset_x": 1}',
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.crop_offset_x == 0


def test_macos_config_path_uses_application_support(tmp_path) -> None:
    assert config_path_for_platform(
        "darwin",
        tmp_path,
    ) == (
        tmp_path
        / "Library"
        / "Application Support"
        / "SSBU Arena ID Reader"
        / "config.json"
    )


def test_windows_config_path_uses_appdata(tmp_path) -> None:
    appdata = tmp_path / "Roaming"

    assert config_path_for_platform(
        "win32",
        tmp_path,
        str(appdata),
    ) == (
        appdata
        / "SSBU Arena ID Reader"
        / "config.json"
    )


def test_windows_config_path_falls_back_to_roaming(tmp_path) -> None:
    assert config_path_for_platform(
        "win32",
        tmp_path,
    ) == (
        tmp_path
        / "AppData"
        / "Roaming"
        / "SSBU Arena ID Reader"
        / "config.json"
    )


def test_legacy_settings_migrate_without_deleting_source(tmp_path) -> None:
    legacy_path = tmp_path / "legacy" / "config.json"
    new_path = tmp_path / "new" / "config.json"
    settings = AppSettings(
        obs_password="example-password",
        obs_source="Capture Card",
        crop_offset_x=-8,
    )

    save_settings(settings, legacy_path)

    loaded = load_settings(
        new_path,
        legacy_path=legacy_path,
    )

    assert loaded == settings
    assert load_settings(new_path) == settings
    assert new_path.exists()
    assert legacy_path.exists()


def test_existing_new_settings_take_precedence_over_legacy(tmp_path) -> None:
    legacy_path = tmp_path / "legacy" / "config.json"
    new_path = tmp_path / "new" / "config.json"
    legacy_settings = AppSettings(
        obs_password="old-password",
        obs_source="Old Source",
        crop_offset_x=-10,
    )
    new_settings = AppSettings(
        obs_password="new-password",
        obs_source="New Source",
        crop_offset_x=-4,
    )

    save_settings(legacy_settings, legacy_path)
    save_settings(new_settings, new_path)

    assert load_settings(
        new_path,
        legacy_path=legacy_path,
    ) == new_settings
