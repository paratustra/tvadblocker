"""NDI video receiver.

Thin wrapper over the ``NDIlib`` bindings (buresu/ndi-python) that yields
BGRA frames as owned NumPy copies. The capture path follows the library's
hard-won correctness rules:

- copy the frame *before* freeing it (freeing first is a use-after-free that
  crashes the interpreter -- buresu/ndi-python#33);
- free every captured video frame, even if processing raises, or memory grows
  without bound (10 GB after 17 h in buresu/ndi-python#32);
- request video only (``want_audio``/``want_metadata`` False) so we never own
  audio/metadata frames that would also need freeing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import NDIlib as ndi
import numpy as np

if TYPE_CHECKING:
    from types import TracebackType

    from numpy.typing import NDArray

    from .config import NdiConfig

log = logging.getLogger(__name__)


class NDISource:
    """Discovers an NDI source and receives its video frames as BGRA arrays."""

    def __init__(
        self,
        config: NdiConfig,
        *,
        discovery_timeout_ms: int = 1000,
        capture_timeout_ms: int = 5000,
    ) -> None:
        self._config = config
        self._discovery_timeout_ms = discovery_timeout_ms
        self._capture_timeout_ms = capture_timeout_ms
        self._recv: object | None = None

    def __enter__(self) -> NDISource:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def open(self) -> None:
        """Initialise NDI, find a source, and connect a receiver."""
        if not ndi.initialize():
            raise RuntimeError("NDIlib.initialize() failed (is the NDI runtime installed?)")

        finder = ndi.find_create_v2()
        if finder is None:
            ndi.destroy()
            raise RuntimeError("ndi.find_create_v2() failed")

        try:
            source = self._find_source(finder)
            recv_create = ndi.RecvCreateV3()
            recv_create.color_format = ndi.RECV_COLOR_FORMAT_BGRX_BGRA
            recv = ndi.recv_create_v3(recv_create)
            if recv is None:
                raise RuntimeError("ndi.recv_create_v3() failed")
            ndi.recv_connect(recv, source)
            self._recv = recv
            log.info("Connected to NDI source: %s", source.p_ndi_name)
        finally:
            # The finder is only needed to locate a source.
            ndi.find_destroy(finder)

    def _find_source(self, finder: object):
        """Block until a matching source appears and return it."""
        wanted = self._config.source_name.strip().lower()
        while True:
            ndi.find_wait_for_sources(finder, self._discovery_timeout_ms)
            sources = ndi.find_get_current_sources(finder)
            if not sources:
                log.info("Waiting for NDI sources ...")
                continue
            if not wanted:
                return sources[0]
            for src in sources:
                if wanted in src.p_ndi_name.lower():
                    return src
            log.info(
                "NDI sources found but none match %r; available: %s",
                self._config.source_name,
                ", ".join(s.p_ndi_name for s in sources),
            )

    def read(self, timeout_ms: int | None = None) -> NDArray[np.uint8] | None:
        """Capture one video frame as an owned BGRA copy, or ``None``.

        Returns ``None`` on timeout or non-video frames (status change / error),
        which the caller should treat as "no new frame this cycle".
        """
        if self._recv is None:
            raise RuntimeError("NDISource is not open")
        timeout = self._capture_timeout_ms if timeout_ms is None else timeout_ms

        frame_type, video, _audio, _meta = ndi.recv_capture_v2(
            self._recv, timeout, want_audio=False, want_metadata=False
        )
        if frame_type != ndi.FRAME_TYPE_VIDEO:
            # FRAME_TYPE_NONE (timeout), STATUS_CHANGE, or ERROR: nothing to free.
            return None
        try:
            # v.data is an H x W x 4 uint8 view onto an SDK-owned buffer.
            # np.copy detaches it before we free the buffer below.
            return np.copy(video.data)
        finally:
            ndi.recv_free_video_v2(self._recv, video)

    def read_latest(self, timeout_ms: int | None = None) -> NDArray[np.uint8] | None:
        """Return the freshest available frame, draining any backlog.

        Blocks up to ``timeout_ms`` for the first frame, then non-blockingly
        drains queued frames so a slow sampling loop stays current instead of
        replaying a growing buffer.
        """
        frame = self.read(timeout_ms)
        if frame is None:
            return None
        while True:
            newer = self.read(0)
            if newer is None:
                return frame
            frame = newer

    def close(self) -> None:
        try:
            if self._recv is not None:
                ndi.recv_destroy(self._recv)
                self._recv = None
        finally:
            ndi.destroy()
