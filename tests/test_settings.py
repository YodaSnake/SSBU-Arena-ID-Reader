import stat

from ssbu_arena_id_reader.settings import AppSettings, load_settings, save_settings


def test_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "nested" / "config.json"
    settings = AppSettings(
        obs_password="example-password",
        obs_source="キャプボ",
        sample_count=2,
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


def test_invalid_sample_count_returns_default(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"sample_count": 9}', encoding="utf-8")

    assert load_settings(path).sample_count == 1
