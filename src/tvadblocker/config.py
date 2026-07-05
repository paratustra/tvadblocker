"""Configuration loading and validation.

Pure standard-library code: importing this module pulls in no native
dependencies, so it can be unit-tested in isolation.
"""

from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when a configuration file is missing or has invalid values."""


@dataclass(frozen=True)
class ObsConfig:
    """OBS Studio WebSocket v5 connection and scene names."""

    host: str = "localhost"
    port: int = 4455
    password: str = ""
    timeout: float = 3.0
    tv_scene: str = "tv"
    ad_scene: str = "adbreak"

    def __post_init__(self) -> None:
        if not 0 < self.port <= 65535:
            raise ConfigError(f"obs.port must be in 1..65535, got {self.port}")
        if self.timeout <= 0:
            raise ConfigError(f"obs.timeout must be positive, got {self.timeout}")
        if not self.tv_scene or not self.ad_scene:
            raise ConfigError("obs.tv_scene and obs.ad_scene must be non-empty")


@dataclass(frozen=True)
class NdiConfig:
    """NDI source selection."""

    # Case-insensitive substring used to pick a source; empty = first found.
    source_name: str = ""


@dataclass(frozen=True)
class DetectionConfig:
    """Logo template matching and temporal debouncing."""

    logo_path: Path = Path("logo.png")
    present_threshold: float = 0.90
    absent_threshold: float = 0.85
    debounce_frames: int = 3
    interval_seconds: float = 1.0
    roi_width_ratio: float = 0.25
    roi_height_ratio: float = 0.25
    # Width (px) of the source the logo was captured from; 0 disables rescaling.
    logo_capture_width: int = 0

    def __post_init__(self) -> None:
        for name in ("present_threshold", "absent_threshold"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ConfigError(f"detection.{name} must be in 0.0..1.0, got {value}")
        if self.absent_threshold > self.present_threshold:
            raise ConfigError(
                "detection.absent_threshold must be <= present_threshold "
                f"({self.absent_threshold} > {self.present_threshold})"
            )
        if self.debounce_frames < 1:
            raise ConfigError(
                f"detection.debounce_frames must be >= 1, got {self.debounce_frames}"
            )
        if self.interval_seconds < 0:
            raise ConfigError(
                f"detection.interval_seconds must be >= 0, got {self.interval_seconds}"
            )
        for name in ("roi_width_ratio", "roi_height_ratio"):
            value = getattr(self, name)
            if not 0.0 < value <= 1.0:
                raise ConfigError(f"detection.{name} must be in (0.0, 1.0], got {value}")
        if self.logo_capture_width < 0:
            raise ConfigError(
                f"detection.logo_capture_width must be >= 0, got {self.logo_capture_width}"
            )


@dataclass(frozen=True)
class AppConfig:
    """Top-level configuration, grouped by concern."""

    obs: ObsConfig
    ndi: NdiConfig
    detection: DetectionConfig


def load_config(config_path: Path) -> AppConfig:
    """Load and validate configuration from an ``.ini`` file.

    Missing keys fall back to the dataclass defaults, so a partial file is
    valid. A missing file raises :class:`ConfigError`.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    parser = ConfigParser()
    # read() silently ignores unreadable files; we already checked existence,
    # but this guards against permission errors mid-read.
    if not parser.read(config_path):
        raise ConfigError(f"Could not read configuration file: {config_path}")

    obs_defaults = ObsConfig()
    obs = ObsConfig(
        host=parser.get("obs", "host", fallback=obs_defaults.host),
        port=parser.getint("obs", "port", fallback=obs_defaults.port),
        password=parser.get("obs", "password", fallback=obs_defaults.password),
        timeout=parser.getfloat("obs", "timeout", fallback=obs_defaults.timeout),
        tv_scene=parser.get("obs", "tv_scene", fallback=obs_defaults.tv_scene),
        ad_scene=parser.get("obs", "ad_scene", fallback=obs_defaults.ad_scene),
    )

    ndi_defaults = NdiConfig()
    ndi = NdiConfig(
        source_name=parser.get("ndi", "source_name", fallback=ndi_defaults.source_name),
    )

    det_defaults = DetectionConfig()
    detection = DetectionConfig(
        logo_path=Path(
            parser.get("detection", "logo_path", fallback=str(det_defaults.logo_path))
        ).expanduser(),
        present_threshold=parser.getfloat(
            "detection", "present_threshold", fallback=det_defaults.present_threshold
        ),
        absent_threshold=parser.getfloat(
            "detection", "absent_threshold", fallback=det_defaults.absent_threshold
        ),
        debounce_frames=parser.getint(
            "detection", "debounce_frames", fallback=det_defaults.debounce_frames
        ),
        interval_seconds=parser.getfloat(
            "detection", "interval_seconds", fallback=det_defaults.interval_seconds
        ),
        roi_width_ratio=parser.getfloat(
            "detection", "roi_width_ratio", fallback=det_defaults.roi_width_ratio
        ),
        roi_height_ratio=parser.getfloat(
            "detection", "roi_height_ratio", fallback=det_defaults.roi_height_ratio
        ),
        logo_capture_width=parser.getint(
            "detection", "logo_capture_width", fallback=det_defaults.logo_capture_width
        ),
    )

    return AppConfig(obs=obs, ndi=ndi, detection=detection)
