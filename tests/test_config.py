from __future__ import annotations

from pathlib import Path

import pytest

from tvadblocker.config import (
    ConfigError,
    DetectionConfig,
    ObsConfig,
    load_config,
)


def test_defaults_are_valid() -> None:
    cfg = DetectionConfig()
    assert cfg.present_threshold >= cfg.absent_threshold
    assert ObsConfig().port == 4455


def test_load_partial_file_uses_defaults(tmp_path: Path) -> None:
    ini = tmp_path / "config.ini"
    ini.write_text("[obs]\nport = 5000\n")
    cfg = load_config(ini)
    assert cfg.obs.port == 5000
    assert cfg.obs.host == "localhost"  # default
    assert cfg.detection.debounce_frames == 3  # default


def test_load_full_file(tmp_path: Path) -> None:
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[obs]\nhost = tv.local\nport = 4455\npassword = pw\ntv_scene = live\nad_scene = brb\n"
        "[ndi]\nsource_name = CAMERA 1\n"
        "[detection]\nlogo_path = /tmp/x.png\npresent_threshold = 0.8\n"
        "absent_threshold = 0.7\ndebounce_frames = 5\nlogo_capture_width = 1920\n"
    )
    cfg = load_config(ini)
    assert cfg.obs.host == "tv.local"
    assert cfg.obs.ad_scene == "brb"
    assert cfg.ndi.source_name == "CAMERA 1"
    assert cfg.detection.logo_path == Path("/tmp/x.png")
    assert cfg.detection.debounce_frames == 5
    assert cfg.detection.logo_capture_width == 1920


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.ini")


def test_absent_above_present_rejected() -> None:
    with pytest.raises(ConfigError, match="absent_threshold"):
        DetectionConfig(present_threshold=0.5, absent_threshold=0.9)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"present_threshold": 1.5},
        {"absent_threshold": -0.1},
        {"debounce_frames": 0},
        {"roi_width_ratio": 0.0},
        {"roi_height_ratio": 1.5},
        {"logo_capture_width": -1},
    ],
)
def test_detection_invalid_values_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ConfigError):
        DetectionConfig(**kwargs)


@pytest.mark.parametrize("port", [0, 70000])
def test_obs_invalid_port_rejected(port: int) -> None:
    with pytest.raises(ConfigError, match="port"):
        ObsConfig(port=port)


def test_obs_empty_scene_rejected() -> None:
    with pytest.raises(ConfigError, match="scene"):
        ObsConfig(tv_scene="")
