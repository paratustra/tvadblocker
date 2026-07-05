"""Application wiring: NDI frames -> logo detection -> OBS scene switching."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .detector import AdStateMachine, LogoDetector, State
from .ndi_source import NDISource
from .obs_controller import OBSController

if TYPE_CHECKING:
    from .config import AppConfig

log = logging.getLogger(__name__)


def run(config: AppConfig) -> int:
    """Run the detection loop until interrupted. Returns a process exit code."""
    detection = config.detection

    detector = LogoDetector(detection)
    detector.load()  # fail fast if the logo template is missing/unreadable

    state_machine = AdStateMachine(
        present_threshold=detection.present_threshold,
        absent_threshold=detection.absent_threshold,
        debounce_frames=detection.debounce_frames,
    )
    scene_for = {State.PROGRAM: config.obs.tv_scene, State.AD: config.obs.ad_scene}

    with NDISource(config.ndi) as source, OBSController(config.obs) as obs:
        log.info(
            "Detection loop started (interval=%.2fs, present>=%.2f, absent<=%.2f, debounce=%d)",
            detection.interval_seconds,
            detection.present_threshold,
            detection.absent_threshold,
            detection.debounce_frames,
        )
        try:
            while True:
                frame = source.read_latest()
                if frame is not None:
                    transition = state_machine.update(detector.score(frame))
                    if transition is not None:
                        log.info("State -> %s (score-confirmed)", transition.value)
                        obs.switch_to(scene_for[transition])
                if detection.interval_seconds:
                    time.sleep(detection.interval_seconds)
        except KeyboardInterrupt:
            log.info("Interrupted; shutting down ...")
    return 0
