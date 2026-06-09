# Sandbox AR — Augmented Reality Sandbox

Kinect sensor reads sand elevation in real time and projects a topographic colormap onto the surface. A Flask web interface controls all parameters from any device on the same network.

> _Add a photo or GIF of the projection here_

---

## Hardware

| Component | Details |
|---|---|
| Depth sensor | Microsoft Kinect v1 (Xbox 360) |
| Computer | Raspberry Pi 4 (or any Linux machine) |
| Display | Projector mounted above the sandbox |

Kinect and projector both point **down** at the sand surface.

---

## Setup

```bash
# libfreenect (Debian/Ubuntu/Raspberry Pi OS)
sudo apt-get install freenect python3-freenect
pip install opencv-python numpy flask

git clone https://github.com/El-Edgar-hub/sandbox_dimexideasac.git
cd sandbox_dimexideasac
git checkout v2
python main.py
```

OpenCV window opens fullscreen. Web interface: `http://<device-ip>:5000`

---

## Calibration

1. Empty sandbox → web UI → **"Fijar Suelo Plano"** (captures floor baseline)
2. Add sand → **"Auto Calibrar Rango"** (stretches colormap to pile height)
3. Switch to **Exhibición** to hide the debug overlay

Enable **Live Auto-Stretch** to skip manual calibration — colormap adjusts every frame automatically.

---

## Web Controls

| Control | Description |
|---|---|
| Live Auto-Stretch | Auto-fits colormap to current elevation range |
| Fijar Suelo Plano | Capture floor baseline |
| Quitar Calibración | Revert to raw depth mode |
| Auto Calibrar Rango | One-shot range detection |
| depth_min / depth_max | Manual range sliders |
| Calibración / Exhibición | Toggle debug overlay |
| Guardar Configuración | Save settings to `~/sandbox_config.json` |

---

## License

MIT
