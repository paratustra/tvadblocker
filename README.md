# TV Ad blocker
TV Ad blocker using OBS Studio and OpenCV (simple logo detection using template matching)

## Requirements
- Python 3.6+
- [OBS Studio 28.1.2](https://github.com/obsproject/obs-studio/releases/tag/28.1.2) (didn't test with other versions)
- [OBS Websocket plugin](https://github.com/obsproject/obs-websocket/releases/tag/4.9.1-compat).. The one that comes with OBS is not compatible with this script.
- ```pip install -r requirements.txt```
### Optional
*If you are going to send the TV signal by capturing the screen of a streaming service instead of using a capture card, you will need:*
- [obs-ndi plugin](https://github.com/Palakis/obs-ndi/releases/)
- NDI runtime

## Usage
1. Run OBS Studio and create two scenes:
    - **tv**: This is the scene that will be shown when there is no ad
    - **adbreak**: This is the scene that will be shown when an ad is detected. Put anything you want here, a cute video, or a message saying "Ad break".

    (Optional) If you are going to use NDI to send the signal to the script, you will need to add the NDI filter to the **TV** scene.
2. Install the OBS Websocket plugin and configure it to use the default port (4444), and enable authentication (default script password is "secret"). Restart OBS and start the websocket server.
3. Replace ```logo.png``` with the logo of the channel you want to block ads from. You can use any image format supported by OpenCV.
4. Set the config file (```config.ini```) to your liking.
5. Run the script: ```python main.py```