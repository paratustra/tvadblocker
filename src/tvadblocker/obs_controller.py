"""OBS Studio control over WebSocket v5 (OBS 28+).

Wraps :mod:`obsws_python`, which has no built-in reconnection or keepalive
(see aatikturk/obsws-python#45): a long-running session can be dropped
server-side, after which the next request raises. We therefore rebuild the
client on failure and retry once, so a hours-long detection loop survives OBS
restarts and transient drops.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import obsws_python as obs

from .config import ObsConfig

if TYPE_CHECKING:
    from types import TracebackType

log = logging.getLogger(__name__)


class OBSController:
    """Switches the current OBS program scene, reconnecting as needed."""

    def __init__(self, config: ObsConfig) -> None:
        self._config = config
        self._client: obs.ReqClient | None = None
        self._current_scene: str | None = None

    def __enter__(self) -> OBSController:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()

    def connect(self) -> None:
        """Open the WebSocket connection. Raises if OBS is unreachable."""
        cfg = self._config
        log.info("Connecting to OBS WebSocket at %s:%s", cfg.host, cfg.port)
        self._client = obs.ReqClient(
            host=cfg.host,
            port=cfg.port,
            password=cfg.password,
            timeout=cfg.timeout,
        )
        # Seed the known scene so we can skip a redundant first switch.
        try:
            self._current_scene = self._client.get_current_program_scene().scene_name
        except Exception:
            self._current_scene = None

    def disconnect(self) -> None:
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.disconnect()
            self._client = None

    def switch_to(self, scene_name: str) -> bool:
        """Set the current program scene. No-op if already active.

        Returns ``True`` on success. On failure the client is rebuilt and the
        request retried once; if it still fails we log and return ``False``
        rather than raise, so the caller's loop keeps running.
        """
        if scene_name == self._current_scene:
            return True

        # A dropped session surfaces as an arbitrary exception (often a
        # JSONDecodeError, not an OBS SDK error), so we catch broadly and
        # reconnect. Two attempts: the first may fail on a stale socket, the
        # second runs against a freshly built client.
        for attempt in (1, 2):
            try:
                if self._client is None:
                    self.connect()
                assert self._client is not None
                self._client.set_current_program_scene(scene_name)
                self._current_scene = scene_name
                log.info("Switched OBS scene to %r", scene_name)
                return True
            except Exception as exc:
                log.warning(
                    "OBS scene switch to %r failed (attempt %d/2): %s",
                    scene_name,
                    attempt,
                    exc,
                )
                self.disconnect()  # force a fresh client on the next attempt

        log.error("Giving up switching OBS scene to %r; will retry on next change", scene_name)
        return False
