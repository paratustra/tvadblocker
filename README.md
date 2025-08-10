## TV Ad Blocker

Simple TV ad blocker that switches OBS scenes based on logo detection in the top‑right corner. Uses NDI for video input and OpenCV template matching to detect when the channel logo is visible (program) vs faded/absent (ad break).

### Requirements

- Python 3.8+
- OBS Studio
- OBS WebSocket (v4) enabled
- obs-ndi plugin + NDI runtime

Install Python deps:

```bash
pip install -r requirements.txt
```

### OBS Setup

1. Create two scenes:
   - `tv`: main program
   - `adbreak`: what to show during ads (e.g., a calm video)
2. Add the NDI source/filter to the `tv` scene.
3. Enable OBS WebSocket on port 4444 with a password.

### Configure

Edit `config.ini`:

```ini
[websocket]
host = localhost
port = 4444
password = secret

[opencv]
logo_path = logo.png
threshold = 0.5
interval_seconds = 1.0
roi_width_ratio = 0.25
roi_height_ratio = 0.25

[obs]
tv_scene = tv
ad_scene = adbreak
```

- `threshold`: higher means stricter logo match.
- `interval_seconds`: how often to sample frames.
- `roi_*_ratio`: size of top‑right region of interest.

Replace `logo.png` with the channel logo (cropped and clear works best).

### Run

```bash
python main.py --config config.ini --log-level INFO
```

### Notes

- The script reads the NDI top‑right ROI to speed up matching.
- Scenes are switched via OBS WebSocket `SetCurrentScene`.
- Stop with Ctrl+C.
