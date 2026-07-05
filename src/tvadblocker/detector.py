"""Logo detection and temporal debouncing.

Detects whether a broadcast channel "bug" (a small, often semi-transparent
station logo) is present in the top-right corner of a frame, then debounces the
raw per-frame signal into a stable program/ad state.

Design notes (grounded in the OpenCV template-matching docs):

- The logo PNG's *alpha channel is the signal*, not clutter. We load it with
  ``IMREAD_UNCHANGED`` and use the alpha as a match mask so only the glyph's
  visible pixels are compared -- crucial for a semi-transparent overlay on
  arbitrary program content. (The old code loaded BGR and discarded alpha.)
- Matching is done on a single grayscale channel: faster, illumination-robust,
  and free of the dead constant-alpha channel that polluted the old 4-channel
  correlation.
- ``TM_CCORR_NORMED`` is used because it is one of only two methods that accept
  a mask, and its score is a bounded "higher = better" value that is easy to
  threshold.
- ``matchTemplate`` is not scale-invariant, so if the logo was captured at a
  different resolution than the live feed we rescale it once.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

import cv2 as cv
import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from .config import DetectionConfig

log = logging.getLogger(__name__)


class State(Enum):
    """Confirmed playback state."""

    PROGRAM = "program"
    AD = "ad"


def _split_template(logo: NDArray[np.uint8]) -> tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    """Return (grayscale template, match mask) for a loaded logo image.

    The mask restricts matching to the visible part of the logo: the alpha
    channel when present, otherwise a fully-opaque mask.
    """
    if logo.ndim == 2:  # already grayscale, no alpha
        return logo, np.full(logo.shape, 255, np.uint8)
    channels = logo.shape[2]
    if channels == 4:  # BGRA -- alpha is the mask
        gray = cv.cvtColor(logo, cv.COLOR_BGRA2GRAY)
        return gray, logo[:, :, 3].copy()
    gray = cv.cvtColor(logo, cv.COLOR_BGR2GRAY)  # BGR, no alpha
    return gray, np.full(logo.shape[:2], 255, np.uint8)


class LogoDetector:
    """Scores logo presence in the top-right ROI of a BGRA frame."""

    def __init__(self, config: DetectionConfig) -> None:
        self._config = config
        self._template: NDArray[np.uint8] | None = None
        self._mask: NDArray[np.uint8] | None = None
        # Nothing to rescale when no capture width is configured.
        self._scaled = config.logo_capture_width == 0

    def load(self) -> None:
        """Load the logo template from disk. Raises if it cannot be read."""
        path = self._config.logo_path
        if not path.exists():
            raise FileNotFoundError(f"Logo not found: {path}")
        logo = cv.imread(str(path), cv.IMREAD_UNCHANGED)
        if logo is None:
            raise RuntimeError(f"Unable to read logo image: {path}")
        self._template, self._mask = _split_template(logo)
        th, tw = self._template.shape[:2]
        log.info("Loaded logo %s (%dx%d, mask=%s)", path, tw, th, self._mask is not None)

    def _ensure_scaled(self, frame_width: int) -> None:
        """Rescale the template to the live feed the first time we see a frame."""
        if self._scaled:
            return
        assert self._template is not None and self._mask is not None
        cap_w = self._config.logo_capture_width
        if cap_w and cap_w != frame_width:
            scale = frame_width / cap_w
            self._template = cv.resize(
                self._template, None, fx=scale, fy=scale, interpolation=cv.INTER_AREA
            )
            self._mask = cv.resize(
                self._mask, None, fx=scale, fy=scale, interpolation=cv.INTER_NEAREST
            )
            log.info("Rescaled logo template by %.3f for %dpx feed", scale, frame_width)
        self._scaled = True

    def compute_roi(self, height: int, width: int) -> tuple[int, int, int, int]:
        """Return the top-right region of interest as ``(x, y, w, h)``.

        Grown if necessary so the template fits, then clamped to the frame.
        """
        roi_w = max(1, int(width * self._config.roi_width_ratio))
        roi_h = max(1, int(height * self._config.roi_height_ratio))
        if self._template is not None:
            th, tw = self._template.shape[:2]
            roi_w = max(roi_w, tw)
            roi_h = max(roi_h, th)
        roi_w = min(roi_w, width)
        roi_h = min(roi_h, height)
        x = max(0, width - roi_w)
        return x, 0, roi_w, roi_h

    def score(self, frame: NDArray[np.uint8]) -> float | None:
        """Return the best match score in ``[0, 1]`` for the top-right ROI.

        ``None`` means the frame could not be scored (e.g. the ROI is smaller
        than the template) and should be ignored rather than treated as absent.
        """
        if self._template is None or self._mask is None:
            raise RuntimeError("LogoDetector.load() was not called")

        height, width = frame.shape[:2]
        self._ensure_scaled(width)
        x, y, rw, rh = self.compute_roi(height, width)
        roi = frame[y : y + rh, x : x + rw]
        th, tw = self._template.shape[:2]
        if roi.size == 0 or rh < th or rw < tw:
            log.warning("ROI %dx%d too small for template %dx%d; skipping frame", rw, rh, tw, th)
            return None

        roi_gray = _to_gray(roi)
        result = cv.matchTemplate(roi_gray, self._template, cv.TM_CCORR_NORMED, mask=self._mask)
        # Masked normalized correlation can emit NaN/Inf where the masked
        # region is flat; treat those as "no match".
        result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
        _, max_val, _, _ = cv.minMaxLoc(result)
        return float(max_val)


def _to_gray(frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Convert a BGRA/BGR/gray frame to single-channel grayscale."""
    if frame.ndim == 2:
        return frame
    if frame.shape[2] == 4:
        return cv.cvtColor(frame, cv.COLOR_BGRA2GRAY)
    return cv.cvtColor(frame, cv.COLOR_BGR2GRAY)


class AdStateMachine:
    """Debounces raw logo scores into confirmed program/ad transitions.

    Uses hysteresis (two thresholds) plus N-consecutive-frame confirmation so a
    single noisy frame or a momentary logo fade never flips the scene:

    - score >= ``present_threshold``  -> wants PROGRAM (logo present)
    - score <= ``absent_threshold``   -> wants AD (logo absent)
    - in between                      -> hold current state
    A state change is only confirmed after ``debounce_frames`` consecutive
    frames agree on the new state.
    """

    def __init__(
        self,
        present_threshold: float,
        absent_threshold: float,
        debounce_frames: int,
        initial: State = State.PROGRAM,
    ) -> None:
        self._present = present_threshold
        self._absent = absent_threshold
        self._debounce = debounce_frames
        self._state = initial
        self._candidate: State | None = None
        self._pending = 0

    @property
    def state(self) -> State:
        return self._state

    def update(self, score: float | None) -> State | None:
        """Feed one frame's score. Returns the new State on a confirmed
        transition, else ``None``.
        """
        if score is None:
            return None  # unscored frame: keep state, don't count it

        if score >= self._present:
            want = State.PROGRAM
        elif score <= self._absent:
            want = State.AD
        else:
            self._reset_candidate()  # in the hysteresis band: hold
            return None

        if want == self._state:
            self._reset_candidate()
            return None

        if want == self._candidate:
            self._pending += 1
        else:
            self._candidate = want
            self._pending = 1

        if self._pending >= self._debounce:
            self._state = want
            self._reset_candidate()
            return want
        return None

    def _reset_candidate(self) -> None:
        self._candidate = None
        self._pending = 0
