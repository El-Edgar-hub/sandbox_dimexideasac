# Sandbox AR — Context Anchor

> AI handoff document. Read this before touching any file. Last updated: 2026-06-09

---

## Project Status

Core feature-complete. Floor calibration, live auto-stretch, one-shot auto-calibrate, and Flask UI all working. No open bugs known.

**Stack:** Python 3.8+ · freenect · OpenCV · NumPy · Flask · Kinect v1 (640×480, 11-bit depth)

---

## File Map

| File | Role | Key symbols |
|---|---|---|
| `main.py` | Entry point | loads config, starts Flask thread, calls `freenect.runloop(depth=get_depth, video=get_video)` |
| `config.py` | Shared mutable state + persistence | `config` dict, `last_depth_frame`, `floor_frame`, `live_stretch`, `auto_calib_status`, `load_config()`, `save_config()` |
| `kinect.py` | Depth processing + calibration logic | `get_depth()`, `calibrate_floor()`, `reset_floor()`, `auto_calibrate()`, `_update_live_stretch()`, `draw_calibration_ui()` |
| `colormap.py` | TOPO palette LUT | `topo_lut` (256×1×3 uint8), `apply_colormap(gray)` |
| `web.py` | Flask server + embedded HTML/JS UI | `run_flask()` on `0.0.0.0:5000`, `_payload()`, all route handlers |

---

## Shared State Pattern (config.py)

All mutable state lives in **single-element lists** — avoids `global` and is safe for mutation across the C thread that `freenect.runloop` uses (GIL protects simple `list[0] = x` assignments):

```python
config            = {'depth_min': 400, 'depth_max': 2000, 'mode': 'calibration'}
last_depth_frame  = [None]    # raw Kinect uint16 frame, shape (480, 640)
floor_frame       = [None]    # captured baseline as float32; None → classic depth mode
live_stretch      = [False]   # enables per-5-frame exponential smoothing
auto_calib_status = ['Listo'] # string shown in web UI after auto_calibrate()
```

Config persisted to `~/sandbox_config.json` via `save_config()` / loaded at startup via `load_config()`.

---

## Elevation Logic (kinect.py → get_depth)

**Floor mode** (`floor_frame[0] is not None`):
```
elev      = clip(floor_frame - depth, 0, ∞)          # elevation above baseline
depth_norm = clip(elev / depth_max, 0.0, 1.0)        # depth_min is 0 in this mode
```

**Classic mode**:
```
depth_norm = 1.0 - clip((depth - depth_min) / (depth_max - depth_min), 0.0, 1.0)
```

Invalid pixels (`data == 0` or `data == 2047`) → `depth_norm = 0.0` → deep blue (visually natural as void/water).

Frame upscaled 640×480 → 1920×1080 via `cv2.resize` before display.

---

## Live Stretch (_update_live_stretch)

- Runs every 5 frames (`_stretch_tick`), exponential smoothing alpha=0.15
- **Floor mode:** adjusts only `depth_max` ← p97 of elevations > 8 units (min 20)
- **Classic mode:** adjusts `depth_min` ← p2 and `depth_max` ← p98 of valid depth
- Skips update if fewer than 500 valid pixels

## Auto-Calibrate (auto_calibrate)

- **Floor mode:** `depth_max` = p95(valid elevations > 8) + 20 units; `depth_min` = 0
- **Classic mode:** `depth_min` = p2 − 5, `depth_max` = p98 + 5 (clamped to 0–2047)
- Sets `auto_calib_status[0]` string for web UI feedback

---

## TOPO Colormap LUT (colormap.py)

Keypoints in `make_topo_colormap()` — linear interpolation between stops:

```python
(value, [ch0, ch1, ch2])   # stored as 3-channel uint8 in LUT
(  0,  [  0,   0,  80])    # deep blue   (low elevation)
( 60,  [  0,  60, 180])    # blue
(100,  [  0, 160, 200])    # cyan
(140,  [  0, 180,  80])    # green
(180,  [180, 210,   0])    # yellow-green
(210,  [255, 160,   0])    # orange
(240,  [200,   0,   0])    # red
(255,  [255, 255, 255])    # white        (high elevation)
```

Applied via `cv2.applyColorMap(gray_uint8, topo_lut)`. Note: OpenCV treats LUT channels as BGR — verify visually if editing.

---

## Flask API Routes (web.py)

| Method | Route | Action | Returns |
|---|---|---|---|
| GET | `/` | Serve embedded HTML UI | HTML |
| GET | `/status` | Current state | `_payload()` |
| POST | `/update` | Set `depth_min`, `depth_max` | `_payload()` |
| POST | `/mode` | Set `mode` (`calibration`/`exhibition`) | `_payload()` |
| POST | `/save` | Persist config to JSON | `{msg}` |
| POST | `/auto_calibrate` | Run `auto_calibrate()` | `_payload()` + `{status}` |
| POST | `/calibrate_floor` | Run `calibrate_floor()` | `_payload()` + `{msg}` |
| POST | `/reset_floor` | Run `reset_floor()` | `_payload()` + `{msg}` |
| POST | `/toggle_stretch` | Toggle `live_stretch[0]` | `_payload()` |

`_payload()` = `{depth_min, depth_max, mode, floor_active, live_stretch}`

Status polled by UI every 2 s via `setInterval(loadStatus, 2000)`.

---

## Key Decisions

| Decision | Why |
|---|---|
| Single-element lists for shared state | Kinect callbacks run in a C thread; list mutation is GIL-safe without locks |
| Live stretch every 5 frames, alpha=0.15 | Empirical: less flicker than every frame, responsive enough for live shaping |
| Invalid pixels → `depth_norm=0.0` (deep blue) | Visually maps voids to "water" — natural for a topo palette |
| Auto-calibrate margin +20 units | Prevents peaks from clipping at the top of the colormap |
| `render_template_string(HTML)` | Single-file deploy — no templates/ folder needed on Raspberry Pi |
| Display: 1920×1080 constants in config.py | Easy to change for different projectors without touching rendering code |

---

## Display Constants (config.py)

```python
DISPLAY_WIDTH  = 1920
DISPLAY_HEIGHT = 1080
CONFIG_FILE    = os.path.expanduser('~/sandbox_config.json')
```

---

## Next Steps / Future Phases

_(update here as work progresses)_

- [ ] Add demo photo/GIF to README
- [ ] Consider multi-display support (projector on secondary output)
- [ ] Potential: network stream of depth frame for remote monitoring
