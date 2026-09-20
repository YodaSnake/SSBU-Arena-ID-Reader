import sys

import cv2
import numpy as np

import ssbu_arena_id_reader.sample_collection as sample_collection
from ssbu_arena_id_reader.sample_collection import (
    REPOSITORY_ROOT,
    SAMPLE_DIRECTORY,
    save_template_sample,
)


def test_default_sample_directory_is_project_local() -> None:
    assert SAMPLE_DIRECTORY == REPOSITORY_ROOT / "template_samples" / "raw"


def test_application_directory_uses_windows_executable_parent(
    monkeypatch,
    tmp_path,
) -> None:
    executable = tmp_path / "SSBU-Arena-ID-Reader.exe"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "platform", "win32")

    assert sample_collection.application_directory() == tmp_path


def test_application_directory_uses_macos_app_parent(
    monkeypatch,
    tmp_path,
) -> None:
    app = tmp_path / "SSBU Arena ID Reader.app"
    executable = app / "Contents" / "MacOS" / "SSBU Arena ID Reader"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "platform", "darwin")

    assert sample_collection.application_directory() == tmp_path


def test_save_template_sample_preserves_raw_roi_and_uses_ocr_name(tmp_path) -> None:
    image = np.zeros((4, 6, 3), dtype=np.uint8)
    image[0, 0] = (10, 20, 30)
    image[3, 5] = (200, 150, 100)

    first_path = save_template_sample(image, "JPQHX", tmp_path)
    second_path = save_template_sample(image, "JPQHX", tmp_path)

    assert first_path.name == "JPQHX.png"
    assert second_path.name == "JPQHX_002.png"

    decoded = cv2.imread(str(first_path), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert np.array_equal(decoded, image)
