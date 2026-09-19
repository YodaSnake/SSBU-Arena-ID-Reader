import cv2
import numpy as np

from ssbu_arena_id_reader.sample_collection import (
    REPOSITORY_ROOT,
    SAMPLE_DIRECTORY,
    save_template_sample,
)


def test_default_sample_directory_is_project_local() -> None:
    assert SAMPLE_DIRECTORY == REPOSITORY_ROOT / "template_samples" / "raw"


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
