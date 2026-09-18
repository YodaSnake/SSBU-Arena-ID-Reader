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


def test_read_id_automatically_rescues_split_after_selected_reads(monkeypatch) -> None:
    FakeObsClient.calls = 0

    monkeypatch.setattr(app_module, "ObsClient", FakeObsClient)
    monkeypatch.setattr(app_module, "decode_png", lambda data: object())
    monkeypatch.setattr(app_module, "preprocess_frame", lambda frame: frame)
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
    app._copy_to_clipboard = copied.append
    app._save_settings = lambda: None
    app._set_busy = lambda busy: None

    app._read_id()

    assert FakeObsClient.calls == 3
    assert app.result_var.get() == "JPQHX"
    assert copied == ["JPQHX"]
    assert app.status_var.get() == "Copied JPQHX to the clipboard (3 reads)."


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
