from __future__ import annotations

from pathlib import Path

import cv2 as cv
import numpy as np
import pytest

from tvadblocker.config import DetectionConfig
from tvadblocker.detector import LogoDetector, _split_template, _to_gray


def _write_logo(path: Path, *, channels: int) -> np.ndarray:
    """Write a small logo PNG with the given channel count; return the array."""
    if channels == 2:  # grayscale
        logo = np.full((20, 40), 200, np.uint8)
    elif channels == 3:  # BGR
        logo = np.full((20, 40, 3), 255, np.uint8)
    else:  # BGRA with a partially transparent border
        logo = np.zeros((20, 40, 4), np.uint8)
        logo[:, :, :3] = 255
        logo[:, :, 3] = 255
        logo[0, :, 3] = 0  # top row transparent -> should land in the mask
    cv.imwrite(str(path), logo)
    return logo


def test_split_template_bgra_uses_alpha_as_mask() -> None:
    logo = np.zeros((10, 10, 4), np.uint8)
    logo[:, :, 3] = 128
    gray, mask = _split_template(logo)
    assert gray.ndim == 2
    assert mask.shape == (10, 10)
    assert np.all(mask == 128)


def test_split_template_bgr_full_mask() -> None:
    logo = np.full((10, 10, 3), 255, np.uint8)
    gray, mask = _split_template(logo)
    assert gray.ndim == 2
    assert np.all(mask == 255)


def test_split_template_grayscale_full_mask() -> None:
    logo = np.full((10, 10), 128, np.uint8)
    gray, mask = _split_template(logo)
    assert gray.shape == (10, 10)
    assert np.all(mask == 255)


def test_to_gray_handles_bgra_and_bgr() -> None:
    assert _to_gray(np.zeros((4, 4, 4), np.uint8)).ndim == 2
    assert _to_gray(np.zeros((4, 4, 3), np.uint8)).ndim == 2
    assert _to_gray(np.zeros((4, 4), np.uint8)).ndim == 2


@pytest.mark.parametrize("channels", [2, 3, 4])
def test_load_various_formats(tmp_path: Path, channels: int) -> None:
    path = tmp_path / "logo.png"
    _write_logo(path, channels=channels)
    det = LogoDetector(DetectionConfig(logo_path=path))
    det.load()  # must not raise


def test_load_missing_raises(tmp_path: Path) -> None:
    det = LogoDetector(DetectionConfig(logo_path=tmp_path / "absent.png"))
    with pytest.raises(FileNotFoundError):
        det.load()


def test_score_high_when_logo_present_low_when_absent(tmp_path: Path) -> None:
    path = tmp_path / "logo.png"
    _write_logo(path, channels=4)
    det = LogoDetector(DetectionConfig(logo_path=path))
    det.load()

    present = np.zeros((200, 300, 4), np.uint8)
    present[:, :, 3] = 255
    present[5:25, 255:295, :3] = 255  # bright block in the top-right ROI

    absent = np.zeros((200, 300, 4), np.uint8)
    absent[:, :, 3] = 255

    s_present = det.score(present)
    s_absent = det.score(absent)
    assert s_present is not None and s_absent is not None
    assert s_present > s_absent
    assert s_present > 0.9


def test_score_returns_none_when_roi_smaller_than_template(tmp_path: Path) -> None:
    path = tmp_path / "logo.png"
    _write_logo(path, channels=4)  # 40x20 template
    # Frame so small that even a grown ROI cannot fit the 40px-wide template.
    det = LogoDetector(DetectionConfig(logo_path=path))
    det.load()
    tiny = np.zeros((10, 20, 4), np.uint8)
    tiny[:, :, 3] = 255
    assert det.score(tiny) is None


def test_compute_roi_is_top_right_and_clamped(tmp_path: Path) -> None:
    path = tmp_path / "logo.png"
    _write_logo(path, channels=4)
    det = LogoDetector(DetectionConfig(logo_path=path, roi_width_ratio=0.25, roi_height_ratio=0.25))
    det.load()
    x, y, w, h = det.compute_roi(height=400, width=800)
    assert y == 0  # top
    assert x + w == 800  # flush to the right edge
    assert w <= 800 and h <= 400


def test_score_before_load_raises(tmp_path: Path) -> None:
    det = LogoDetector(DetectionConfig(logo_path=tmp_path / "logo.png"))
    with pytest.raises(RuntimeError, match="load"):
        det.score(np.zeros((100, 100, 4), np.uint8))
