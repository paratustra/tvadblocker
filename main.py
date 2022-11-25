import numpy as np
import cv2 as cv
import NDIlib as ndi
import time
from obswebsocket import obsws, requests
from configparser import ConfigParser

class TVAdBlocker:
    def __init__(self):
        config = ConfigParser()
        config.read("config.ini")

        # datos websocket
        self.host = config["websocket"]["host"]
        self.port = config["websocket"]["port"]
        self.password = config["websocket"]["password"]
        self.ws = obsws(self.host, self.port, self.password)

        self.logo_path = config["opencv"]["logo_path"]  # logo to detect
        self.tv_scene = config["obs"]["tv_scene"]  # OBS scene where the TV program is
        self.ad_scene = config["obs"]["ad_scene"]  # OBS scene to show during ads
        self.threshold = float(config["opencv"]["threshold"])  # threshold to detect the logo

    def main(self):
        self.ws.connect()

        if not ndi.initialize():
            return 0

        ndi_find = ndi.find_create_v2()

        if ndi_find is None:
            return 0

        sources = []
        while not len(sources) > 0:
            print("Buscando fuentes ...")
            ndi.find_wait_for_sources(ndi_find, 1000)
            sources = ndi.find_get_current_sources(ndi_find)

        ndi_recv_create = ndi.RecvCreateV3()
        ndi_recv_create.color_format = ndi.RECV_COLOR_FORMAT_BGRX_BGRA

        img = cv.imread(self.logo_path)
        img = cv.cvtColor(img, cv.COLOR_BGR2BGRA)

        ndi_recv = ndi.recv_create_v3(ndi_recv_create)

        if ndi_recv is None:
            return 0

        ndi.recv_connect(ndi_recv, sources[0])

        ndi.find_destroy(ndi_find)

        cv.startWindowThread()

        while True:
            t, v, _, _ = ndi.recv_capture_v2(ndi_recv, 5000)

            if t == ndi.FRAME_TYPE_VIDEO:
                frame = np.copy(v.data)

                # Check if img is in frame
                res = cv.matchTemplate(frame, img, cv.TM_CCOEFF_NORMED)

                min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)

                # cv.imshow("ndi image", res)
                if max_val > self.threshold:
                    print("Logo detected")
                    self.ws.call(requests.SetCurrentScene(self.tv_scene))
                else:
                    self.ws.call(requests.SetCurrentScene(self.ad_scene))
                    print("No logo detected, ads? 👀")

                ndi.recv_free_video_v2(ndi_recv, v)
                time.sleep(1)

            if cv.waitKey(1) & 0xFF == 27:
                break

        ndi.recv_destroy(ndi_recv)
        ndi.destroy()
        cv.destroyAllWindows()

        self.ws.disconnect()
        return 0


if __name__ == "__main__":
    TVAdBlocker().main()
