from pathlib import Path

import ssbu_arena_id_reader.app as app_module
from ssbu_arena_id_reader.app import ArenaIdApp


class FakeVar:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class FakeRoot:
    def update_idletasks(self) -> None:
        pass


class FakeObsClient:
    calls = 0

    def __init__(self, password: str) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get_source_screenshot(self, source_name: str) -> bytes:
        type(self).calls += 1
        return b"fake"


class FakeRecognizer:
    def __init__(self) -> None:
        self.results = iter(["JPQHX", "JPQHY", "JPQHX"])

    def ensure_ready(self) -> None:
        pass

    def recognize(self, image) -> str:
        return next(self.results)


class AlwaysInvalidRecognizer:
    def ensure_ready(self) -> None:
        pass

    def recognize(self, image) -> str:
        return "BAD"


def test_read_id_automatically_rescues_split_after_selected_reads(monkeypatch) -> None:
    FakeObsClient.calls = 0

    monkeypatch.setattr(app_module, "ObsClient", FakeObsClient)
    monkeypatch.setattr(app_module, "decode_png", lambda data: object())
    monkeypatch.setattr(
        app_module,
        "extract_arena_id_roi",
        lambda frame: "raw-roi",
    )
    monkeypatch.setattr(app_module, "preprocess_roi", lambda roi: roi)
    monkeypatch.setattr(app_module.time, "sleep", lambda seconds: None)

    app = ArenaIdApp.__new__(ArenaIdApp)
    app.root = FakeRoot()
    app.recognizer = FakeRecognizer()
    app.password_var = FakeVar("fake-password")
    app.source_var = FakeVar("キャプボ")
    app.sample_count_var = FakeVar("2")
    app.result_var = FakeVar()
    app.status_var = FakeVar()

    copied = []
    previews = []
    app._copy_to_clipboard = copied.append
    app._save_settings = lambda: None
    app._set_busy = lambda busy: None
    app._show_sample_preview = previews.append

    app._read_id()

    assert FakeObsClient.calls == 3
    assert app.result_var.get() == "JPQHX"
    assert copied == ["JPQHX"]
    assert previews == ["raw-roi", "raw-roi", "raw-roi"]
    assert app._last_sample_roi == "raw-roi"
    assert app.status_var.get() == "Copied JPQHX to the clipboard (3 reads)."


def test_failed_ocr_keeps_latest_crop_available_for_manual_save(monkeypatch) -> None:
    FakeObsClient.calls = 0

    monkeypatch.setattr(app_module, "ObsClient", FakeObsClient)
    monkeypatch.setattr(app_module, "decode_png", lambda data: object())
    monkeypatch.setattr(
        app_module,
        "extract_arena_id_roi",
        lambda frame: "raw-roi",
    )
    monkeypatch.setattr(app_module, "preprocess_roi", lambda roi: roi)
    monkeypatch.setattr(app_module.time, "sleep", lambda seconds: None)

    app = ArenaIdApp.__new__(ArenaIdApp)
    app.root = FakeRoot()
    app.recognizer = AlwaysInvalidRecognizer()
    app.password_var = FakeVar("fake-password")
    app.source_var = FakeVar("キャプボ")
    app.sample_count_var = FakeVar("1")
    app.result_var = FakeVar("OLD12")
    app.status_var = FakeVar()
    app._last_sample_roi = "old-roi"

    previews = []
    copied = []
    errors = []
    app._show_sample_preview = previews.append
    app._copy_to_clipboard = copied.append
    app._save_settings = lambda: None
    app._set_busy = lambda busy: None
    app._show_error = errors.append

    app._read_id()

    assert FakeObsClient.calls == 5
    assert app.result_var.get() == ""
    assert app._last_sample_roi == "raw-roi"
    assert previews == ["raw-roi"] * 5
    assert copied == []
    assert len(errors) == 1
    assert "Enter the Arena ID manually and press Save Sample." in errors[0]


class FakeSourceBox:
    def __init__(self, values=()) -> None:
        self.values = tuple(values)

    def __setitem__(self, key, value) -> None:
        assert key == "values"
        self.values = tuple(value)


class FakeRefreshObsClient:
    calls = 0

    def __init__(self, password: str) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def list_inputs(self) -> list[str]:
        type(self).calls += 1
        return ["キャプボ", "別ソース"]


def test_refresh_sources_updates_dropdown_and_preserves_valid_selection(
    monkeypatch,
) -> None:
    FakeRefreshObsClient.calls = 0
    monkeypatch.setattr(app_module, "ObsClient", FakeRefreshObsClient)

    app = ArenaIdApp.__new__(ArenaIdApp)
    app.root = FakeRoot()
    app.password_var = FakeVar("fake-password")
    app.source_var = FakeVar("キャプボ")
    app.status_var = FakeVar()
    app.source_box = FakeSourceBox(("old-source",))
    app._refreshing_sources = False
    app._save_settings = lambda: None

    app._refresh_sources()

    assert FakeRefreshObsClient.calls == 1
    assert app.source_box.values == ("キャプボ", "別ソース")
    assert app.source_var.get() == "キャプボ"
    assert app._refreshing_sources is False


def test_refresh_sources_ignores_reentrant_call(monkeypatch) -> None:
    FakeRefreshObsClient.calls = 0
    monkeypatch.setattr(app_module, "ObsClient", FakeRefreshObsClient)

    app = ArenaIdApp.__new__(ArenaIdApp)
    app._refreshing_sources = True

    app._refresh_sources()

    assert FakeRefreshObsClient.calls == 0


class FakeButton:
    def __init__(self) -> None:
        self.state = None

    def configure(self, *, state: str) -> None:
        self.state = state


def test_save_sample_uses_current_ocr_result_and_consumes_latest_roi(
    monkeypatch,
) -> None:
    saved = []
    expected_path = Path("/tmp/SSBU-Arena-ID-Reader-Samples/JPQHX.png")

    def fake_save_template_sample(image, arena_id):
        saved.append((image, arena_id))
        return expected_path

    monkeypatch.setattr(
        app_module,
        "save_template_sample",
        fake_save_template_sample,
    )

    app = ArenaIdApp.__new__(ArenaIdApp)
    app.result_var = FakeVar(" jpqhx ")
    app.status_var = FakeVar()
    app._last_sample_roi = "raw-roi"
    app.save_sample_button = FakeButton()

    app._save_sample()

    assert saved == [("raw-roi", "JPQHX")]
    assert app.result_var.get() == "JPQHX"
    assert app._last_sample_roi is None
    assert app.save_sample_button.state == "disabled"
    assert app.status_var.get() == f"Saved Arena ID sample to {expected_path}"
