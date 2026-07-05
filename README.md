# TV Ad Blocker

Automatically switch OBS scenes when a broadcast goes to an ad break.

A channel "bug" — the small, often semi-transparent station logo in the corner
of the screen — is usually **hidden during commercials** and shown during
normal programming. This tool watches a live TV feed over [NDI], detects
whether that logo is present, and flips OBS between two scenes accordingly:

- **logo present** → normal programming → show your `tv` scene
- **logo absent** → ad break → show your `adbreak` scene (a calm loop, music,
  a "back shortly" card, whatever you like)

Detection uses OpenCV template matching against a cropped image of the logo.

> **Heads up — this is a hobby project.** It works for a fixed, static logo but
> it is not magic: template matching is sensitive to scale, and stations that
> animate, move, or briefly hide the logo will cause false switches. See
> [Limitations](#limitations).

## How it works

```
 TV / capture card ──NDI──►  tvadblocker  ──WebSocket v5──►  OBS Studio
   (raw broadcast)          (this program)                  (scene switch)
                                 │
                     OpenCV logo detection
                     + hysteresis debounce
```

1. **NDI in** — the raw broadcast is published as an NDI source. `tvadblocker`
   receives its frames.
2. **Detect** — every `interval_seconds` it grayscales the top-right region,
   template-matches the logo (using the logo PNG's alpha as a mask), and gets a
   match score in `[0, 1]`.
3. **Debounce** — a hysteresis state machine requires several consecutive
   agreeing frames before it believes the state really changed, so a single
   noisy frame or a momentary logo fade won't flip scenes.
4. **Switch** — on a confirmed change it calls OBS WebSocket v5 to set the
   program scene. It only switches on an actual transition, never per frame.

> ⚠️ **Feed the raw broadcast, not OBS's program output.** The NDI stream you
> point this at must always show the real TV picture, independent of which
> scene OBS is currently displaying. If you feed it OBS's program output, then
> switching to `adbreak` removes the logo from what the detector sees, and it
> gets stuck. Publish a dedicated NDI output of the capture device/source.

## Requirements

- **Python 3.10+**
- **OBS Studio 28+** with **WebSocket v5** (built in: *Tools → WebSocket Server
  Settings*). Note the default port is **4455** (v4's 4444 is gone).
- An **NDI source** carrying the raw broadcast. In OBS this is typically the
  [DistroAV] (formerly obs-ndi) plugin publishing your capture source as NDI.
- The **NDI runtime/SDK** installed on your machine (the `ndi-python` wheel
  needs it to discover and decode sources). On Linux, source discovery also
  needs Avahi.

## Install

```bash
git clone https://github.com/paratustra/tvadblocker
cd tvadblocker
python -m venv .venv && source .venv/bin/activate
pip install -e .            # or: pip install -r requirements.txt
```

## Configure

Copy the example and edit it (your real `config.ini` is git-ignored so you
never commit your OBS password):

```bash
cp config.example.ini config.ini
```

```ini
[obs]
host = localhost
port = 4455
password =
tv_scene = tv
ad_scene = adbreak

[ndi]
# Case-insensitive substring to pick a source; empty = first one found.
source_name =

[detection]
logo_path = logo.png
present_threshold = 0.90     # score >= this  -> logo present (program)
absent_threshold  = 0.85     # score <= this  -> logo absent (ad)
debounce_frames   = 3        # consecutive agreeing frames before switching
interval_seconds  = 1.0      # how often to sample
roi_width_ratio   = 0.25     # size of the top-right search region
roi_height_ratio  = 0.25
logo_capture_width = 0       # width (px) the logo was cropped from; 0 = no rescale
```

The gap between `absent_threshold` and `present_threshold` is a **dead zone**:
scores inside it don't change the state, which prevents flapping at the
boundary. Tune the two thresholds by watching the logged scores during real
programming vs. real ads and placing them in the valley between the two.

### Preparing the logo

- Crop `logo.png` tightly around the logo from a frame of the **same feed** you
  will run against.
- Save it as a **PNG with transparency** if the logo is semi-transparent — the
  alpha channel is used as a match mask, which is what makes a translucent bug
  detectable over changing content.
- Template matching is **not scale-invariant**. If you cropped from a different
  resolution than the live feed, set `logo_capture_width` to the width you
  cropped from and the template is rescaled to match automatically.

## OBS setup

1. Create two scenes named to match your config: `tv` and `adbreak`.
2. Put your capture device in the `tv` scene, and publish it as a dedicated NDI
   source (DistroAV: *NDI Output* / *Dedicated NDI Output* filter on the
   capture source — **not** the program output; see the caveat above).
3. Enable *Tools → WebSocket Server Settings*, set a password, note the port.

## Run

```bash
tvadblocker --config config.ini --log-level INFO
# or, without installing the console script:
python -m tvadblocker --config config.ini
```

Run at `--log-level DEBUG` while tuning to see per-frame scores. Stop with
`Ctrl+C`.

## Project layout

```
src/tvadblocker/
  config.py          # dataclass config + validation (pure stdlib)
  detector.py        # LogoDetector (OpenCV) + AdStateMachine (hysteresis)
  ndi_source.py      # NDI receiver (safe frame capture/free)
  obs_controller.py  # OBS WebSocket v5 client with reconnect
  app.py             # the detection loop
  cli.py             # argument parsing / entry point
tests/               # unit tests for config, detector, state machine
```

## Development

```bash
pip install -e ".[dev]"
ruff check src/ tests/     # lint
mypy                       # strict type check
pytest                     # tests
```

The native NDI/OBS bindings need hardware, so the tests and CI exercise only
the pure logic (config, detection math, state machine); the hardware wrappers
are kept import-isolated so that stays possible.

## Limitations

- **Template matching only.** No scale/rotation invariance beyond the single
  configured rescale; a logo that moves or resizes will not match.
- **Animated/disappearing logos.** Channels that briefly hide the logo during
  programming (lower-thirds, full-screen graphics) can cause false ad switches.
  The debounce mitigates blips, not sustained ones.
- **Per-station tuning.** Thresholds and the logo crop are specific to one
  channel and one feed resolution.
- **No audio/scene-content analysis.** It's a purely visual, single-cue
  heuristic.

## License

[MIT](LICENSE) © Francisco Parata

[NDI]: https://ndi.video/
[DistroAV]: https://github.com/DistroAV/DistroAV
