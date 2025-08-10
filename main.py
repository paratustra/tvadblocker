from __future__ import annotations

import argparse
import logging
import time
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import NDIlib as ndi
import cv2 as cv
import numpy as np
from obswebsocket import obsws, requests


@dataclass
class AppConfig:
    host: str
    port: int
    password: str
    logo_path: Path
    tv_scene: str
    ad_scene: str
    threshold: float
    interval_seconds: float = 1.0
    roi_width_ratio: float = 0.25
    roi_height_ratio: float = 0.25


def load_config(config_path: Path) -> AppConfig:
    parser = ConfigParser()
    parser.read(config_path)

    host = parser.get("websocket", "host", fallback="localhost")
    port = parser.getint("websocket", "port", fallback=4444)
    password = parser.get("websocket", "password", fallback="secret")

    logo_path = Path(parser.get("opencv", "logo_path", fallback="logo.png")).expanduser()
    threshold = parser.getfloat("opencv", "threshold", fallback=0.5)
    interval_seconds = parser.getfloat("opencv", "interval_seconds", fallback=1.0)
    roi_width_ratio = parser.getfloat("opencv", "roi_width_ratio", fallback=0.25)
    roi_height_ratio = parser.getfloat("opencv", "roi_height_ratio", fallback=0.25)

    tv_scene = parser.get("obs", "tv_scene", fallback="tv")
    ad_scene = parser.get("obs", "ad_scene", fallback="adbreak")

    return AppConfig(
        host=host,
        port=port,
        password=password,
        logo_path=logo_path,
        tv_scene=tv_scene,
        ad_scene=ad_scene,
        threshold=threshold,
        interval_seconds=interval_seconds,
        roi_width_ratio=roi_width_ratio,
        roi_height_ratio=roi_height_ratio,
    )


class TVAdBlocker:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.ws = obsws(self.config.host, self.config.port, self.config.password)
        self.ndi_recv: Optional[ndi.RecvInstance] = None
        self.logo_image_bgra: Optional[np.ndarray] = None

    def connect_obs(self) -> None:
        logging.info("Connecting to OBS WebSocket %s:%s", self.config.host, self.config.port)
        self.ws.connect()

    def disconnect_obs(self) -> None:
        try:
            self.ws.disconnect()
        except Exception:
            pass

    def initialize_ndi(self) -> None:
        if not ndi.initialize():
            raise RuntimeError("Failed to initialize NDI")

        ndi_find = ndi.find_create_v2()
        if ndi_find is None:
            raise RuntimeError("Failed to create NDI finder")

        try:
            sources = []
            while not sources:
                logging.info("Waiting for NDI sources ...")
                ndi.find_wait_for_sources(ndi_find, 1000)
                sources = ndi.find_get_current_sources(ndi_find)

            recv_create = ndi.RecvCreateV3()
            recv_create.color_format = ndi.RECV_COLOR_FORMAT_BGRX_BGRA
            self.ndi_recv = ndi.recv_create_v3(recv_create)
            if self.ndi_recv is None:
                raise RuntimeError("Failed to create NDI receiver")

            ndi.recv_connect(self.ndi_recv, sources[0])
            logging.info("Connected to NDI source: %s", sources[0].p_ndi_name)
        finally:
            ndi.find_destroy(ndi_find)

    def destroy_ndi(self) -> None:
        try:
            if self.ndi_recv is not None:
                ndi.recv_destroy(self.ndi_recv)
        finally:
            try:
                ndi.destroy()
            except Exception:
                pass

    def load_logo_image(self) -> None:
        if not self.config.logo_path.exists():
            raise FileNotFoundError(f"Logo not found: {self.config.logo_path}")

        img = cv.imread(str(self.config.logo_path))
        if img is None:
            raise RuntimeError(f"Unable to read logo image: {self.config.logo_path}")

        self.logo_image_bgra = cv.cvtColor(img, cv.COLOR_BGR2BGRA)
        logging.info(
            "Loaded logo %s (%dx%d)",
            self.config.logo_path,
            self.logo_image_bgra.shape[1],
            self.logo_image_bgra.shape[0],
        )

    def compute_top_right_roi(self, frame_shape: Tuple[int, int, int]) -> Tuple[int, int, int, int]:
        h, w = frame_shape[0], frame_shape[1]
        roi_w = max(1, int(w * self.config.roi_width_ratio))
        roi_h = max(1, int(h * self.config.roi_height_ratio))
        x = max(0, w - roi_w)
        y = 0

        if self.logo_image_bgra is not None:
            tpl_h, tpl_w = self.logo_image_bgra.shape[0], self.logo_image_bgra.shape[1]
            roi_w = max(roi_w, tpl_w + 2)
            roi_h = max(roi_h, tpl_h + 2)
            x = max(0, w - roi_w)

        roi_w = min(roi_w, w)
        roi_h = min(roi_h, h)
        return x, y, roi_w, roi_h

    def set_scene(self, scene_name: str) -> None:
        try:
            self.ws.call(requests.SetCurrentScene(scene_name))
        except Exception as exc:
            logging.warning("Failed to switch scene to %s: %s", scene_name, exc)

    def run(self) -> int:
        self.connect_obs()
        self.initialize_ndi()
        self.load_logo_image()

        assert self.ndi_recv is not None
        assert self.logo_image_bgra is not None

        try:
            logging.info(
                "Starting detection loop (interval=%.2fs, threshold=%.2f)",
                self.config.interval_seconds,
                self.config.threshold,
            )
            while True:
                t, v, _, _ = ndi.recv_capture_v2(self.ndi_recv, 5000)
                if t != ndi.FRAME_TYPE_VIDEO:
                    continue

                frame = np.copy(v.data)

                x, y, rw, rh = self.compute_top_right_roi(frame.shape)
                roi = frame[y : y + rh, x : x + rw]

                res = cv.matchTemplate(roi, self.logo_image_bgra, cv.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv.minMaxLoc(res)

                if max_val > self.config.threshold:
                    logging.debug("Logo detected (score=%.3f)", max_val)
                    self.set_scene(self.config.tv_scene)
                else:
                    logging.debug("Logo not detected (score=%.3f)", max_val)
                    self.set_scene(self.config.ad_scene)

                ndi.recv_free_video_v2(self.ndi_recv, v)
                time.sleep(self.config.interval_seconds)
        except KeyboardInterrupt:
            logging.info("Interrupted, shutting down ...")
        finally:
            self.destroy_ndi()
            self.disconnect_obs()
        return 0


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="TV Ad blocker using OBS and NDI")
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("config.ini"),
        help="Path to configuration file",
    )
    ap.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = load_config(args.config)
    app = TVAdBlocker(config)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
