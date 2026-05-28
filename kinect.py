import cv2
import numpy as np

from config import config, last_depth_frame, floor_frame, live_stretch, auto_calib_status, DISPLAY_WIDTH, DISPLAY_HEIGHT
from colormap import apply_colormap

_stretch_tick = [0]


def _update_live_stretch(depth):
    """Recalcula el rango cada 5 frames con suavizado exponencial para evitar parpadeo."""
    _stretch_tick[0] = (_stretch_tick[0] + 1) % 5
    if _stretch_tick[0] != 0:
        return

    alpha = 0.15  # qué tan rápido se adapta (0.1 = lento/suave, 0.3 = rápido)

    if floor_frame[0] is not None:
        elev = np.clip(floor_frame[0] - depth, 0, None)
        valid = elev[elev > 8]
        if len(valid) < 500:
            return
        new_max = max(int(np.percentile(valid, 97)), 20)
        config['depth_max'] = int(alpha * new_max + (1 - alpha) * config['depth_max'])
        config['depth_min'] = 0
    else:
        valid = depth[(depth > 0) & (depth < 2047)]
        if len(valid) < 500:
            return
        new_min = max(0, int(np.percentile(valid, 2)) - 5)
        new_max = min(2047, int(np.percentile(valid, 98)) + 5)
        config['depth_min'] = int(alpha * new_min + (1 - alpha) * config['depth_min'])
        config['depth_max'] = int(alpha * new_max + (1 - alpha) * config['depth_max'])


def draw_calibration_ui(frame):
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (520, 175), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    mode_label = 'MODO: ELEVACION SUELO' if floor_frame[0] is not None else 'MODO CALIBRACION'
    cv2.putText(frame, mode_label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(frame, f'depth_min: {config["depth_min"]}', (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.putText(frame, f'depth_max: {config["depth_max"]}', (20, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    floor_txt = 'suelo: calibrado' if floor_frame[0] is not None else 'suelo: sin calibrar'
    cv2.putText(frame, floor_txt, (20, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
    stretch_txt = 'live stretch: ON' if live_stretch[0] else 'live stretch: OFF'
    stretch_color = (0, 255, 100) if live_stretch[0] else (150, 150, 150)
    cv2.putText(frame, stretch_txt, (20, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.5, stretch_color, 1)
    return frame


def get_depth(dev, data, timestamp):
    last_depth_frame[0] = data.copy()
    depth = data.astype(np.float32)

    invalid = (data == 0) | (data == 2047)

    if live_stretch[0]:
        _update_live_stretch(depth)

    if floor_frame[0] is not None:
        elev = np.clip(floor_frame[0] - depth, 0, None)
        height_range = max(1, config['depth_max'] - config['depth_min'])
        depth_norm = np.clip(elev / height_range, 0.0, 1.0)
    else:
        rng = max(1, config['depth_max'] - config['depth_min'])
        depth_norm = 1.0 - np.clip((depth - config['depth_min']) / rng, 0.0, 1.0)

    # Pixels inválidos (sin lectura del sensor) → nivel cero = azul oscuro del TOPO
    depth_norm[invalid] = 0.0

    gray = (depth_norm * 255).astype(np.uint8)
    color = apply_colormap(gray)
    color = cv2.resize(color, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    if config['mode'] == 'calibration':
        color = draw_calibration_ui(color)
    cv2.imshow('Sandbox', color)
    cv2.waitKey(1)


def get_video(dev, data, timestamp):
    pass


def calibrate_floor():
    if last_depth_frame[0] is None:
        return False
    floor_frame[0] = last_depth_frame[0].astype(np.float32)
    return True


def reset_floor():
    floor_frame[0] = None


def auto_calibrate():
    auto_calib_status[0] = 'Leyendo...'
    if last_depth_frame[0] is None:
        auto_calib_status[0] = 'Error: sin datos'
        return
    depth = last_depth_frame[0].astype(np.float32)

    if floor_frame[0] is not None:
        elev = np.clip(floor_frame[0] - depth, 0, None)
        valid_elev = elev[elev > 8]
        if len(valid_elev) == 0:
            config['depth_min'] = 0
            config['depth_max'] = 100
            auto_calib_status[0] = 'Sin elevacion detectada, rango por defecto'
            return
        max_elev = int(np.percentile(valid_elev, 95))
        config['depth_min'] = 0
        config['depth_max'] = max(max_elev + 20, 30)
        auto_calib_status[0] = f'OK: elevacion 0-{config["depth_max"]} unidades'
    else:
        valid = depth[(depth > 0) & (depth < 2047)]
        if len(valid) == 0:
            auto_calib_status[0] = 'Error: sin datos validos'
            return
        p2 = int(np.percentile(valid, 2))
        p98 = int(np.percentile(valid, 98))
        config['depth_min'] = max(0, p2 - 5)
        config['depth_max'] = min(2047, p98 + 5)
        auto_calib_status[0] = f'OK: min={config["depth_min"]} max={config["depth_max"]}'
