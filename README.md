# Sandbox AR — Augmented Reality Sandbox

An augmented reality sandbox that uses a Kinect sensor to read sand elevation in real time and projects a topographic colormap directly onto the surface. A Flask web interface lets you control all parameters remotely from any device on the same network.

---

## Demo

> _Add a photo or GIF of the projection here_

---

## How It Works

1. The **Kinect** reads a depth frame (11-bit, 640×480) at ~30 fps.
2. Each pixel's depth value is normalized and mapped to a color.
3. **OpenCV** renders the colormap fullscreen and the **projector** displays it on top of the sand.
4. A **Flask server** exposes a mobile-friendly UI to tune parameters live — no keyboard needed.

### Floor calibration mode

The key feature for accurate topography: capture the empty flat surface as a baseline, then the colormap shows only **elevation above that floor**. A 3 cm sand pile uses the full color range instead of a tiny fraction of it.

| Without floor calibration | With floor calibration |
|---|---|
| Colormap stretched over entire depth range | Colormap stretched over elevation above floor |
| Flat surface looks multicolored | Flat surface = one solid color |
| Sand pile barely distinguishable | Sand pile uses full colormap range |

---

## Hardware

| Component | Details |
|---|---|
| Depth sensor | Microsoft Kinect v1 (Xbox 360) |
| Computer | Raspberry Pi 4 (or any Linux machine) |
| Display | Projector mounted above the sandbox |
| Container | Any tray or box filled with sand |

**Setup:** Kinect and projector both point **down** at the sand surface. The projector output is the OpenCV window rendered fullscreen.

---

## Software Requirements

- Python 3.8+
- [libfreenect](https://github.com/OpenKinect/libfreenect) + Python bindings (`freenect`)
- OpenCV (`opencv-python`)
- NumPy
- Flask

### Install dependencies

```bash
# libfreenect (Debian/Ubuntu/Raspberry Pi OS)
sudo apt-get install freenect python3-freenect

# Python packages
pip install opencv-python numpy flask
```

---

## Installation

```bash
git clone https://github.com/El-Edgar-hub/sandbox_dimexideasac.git
cd sandbox_dimexideasac
git checkout v2
python main.py
```

The OpenCV window opens fullscreen on the primary display. The web interface starts at `http://<device-ip>:5000`.

---

## Calibration Flow

### First time (or after moving the hardware)

1. Leave the sandbox **empty and flat**.
2. Open the web UI → **"Fijar Suelo Plano"** — captures the floor baseline.
3. Add sand and shape it.
4. Press **"Auto Calibrar Rango"** — detects the sand pile height and stretches the colormap to match.
5. Switch to **Exhibición** mode to hide the calibration overlay.

### Manual fine-tuning

Use the `depth_min` / `depth_max` sliders to adjust contrast. In floor mode these control the **maximum expected elevation** (in Kinect units). Decrease the range for more contrast on shallow piles; increase it for tall features.

---

## Web Interface

Accessible from any phone, tablet, or computer on the same network.

| Control | Description |
|---|---|
| Fijar Suelo Plano | Capture empty surface as elevation baseline |
| Quitar Calibración | Revert to classic depth mode |
| Auto Calibrar Rango | Auto-detect range from current frame |
| depth_min / depth_max | Manual range adjustment |
| Colormap | JET · TURBO · RAINBOW · TOPO (custom) |
| Calibración / Exhibición | Toggle on-screen debug overlay |
| Guardar Configuración | Persist settings to `~/sandbox_config.json` |

---

## Colormaps

| Name | Description |
|---|---|
| JET | Classic blue→red gradient |
| TURBO | Improved perceptual version of JET |
| RAINBOW | Full spectrum |
| TOPO | Custom hand-crafted topographic palette — deep blue (low) → green → orange → white (high) |

---

## Project Structure

```
sandbox_dimexideasac/
├── main.py        # Entry point — init, start Flask thread, run Kinect loop
├── config.py      # Constants, shared state, load/save config
├── colormap.py    # Custom TOPO LUT + apply_colormap()
├── kinect.py      # Depth callbacks, floor calibration, auto-calibrate
└── web.py         # Flask app, routes, HTML/CSS/JS UI
```

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?logo=opencv&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.x-000000?logo=flask&logoColor=white)
![Kinect](https://img.shields.io/badge/Kinect-v1-107C10?logo=xbox&logoColor=white)

---

## License

MIT
