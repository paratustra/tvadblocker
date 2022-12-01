# TV Ad blocker
TV Ad blocker using OBS Studio and OpenCV (simple logo detection using template matching)

## Requirements
- Python (3.7-3.10)
- [OBS Studio](https://github.com/obsproject/obs-studio/releases/).
- [OBS Websocket plugin](https://github.com/obsproject/obs-websocket/releases).
- [obs-ndi plugin](https://github.com/Palakis/obs-ndi/releases/). Be sure to also download the NDI runtime.
- Install the required packages with:
- ```pip install -r requirements.txt```

## Usage
1. Run OBS Studio and create two scenes:
    - **tv**: This is the scene that will be shown when there is no ad
    - **adbreak**: This is the scene that will be shown when an ad is detected. Put anything you want here, a cute video, or a message saying "Ad break".
    - Add the NDI filter to the **tv** scene.
2. Install the OBS Websocket plugin and configure it to use the default port (4444), and enable authentication (default script password is "secret"). Restart OBS and start the websocket server.
3. Replace ```logo.png``` with the logo of the channel you want to block ads from. You can use any image format supported by OpenCV.
4. Set the config file (```config.ini```) to your liking.
5. Run the script: ```python main.py```
