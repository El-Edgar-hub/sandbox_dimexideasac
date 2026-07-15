import cv2
import numpy as np

from config import (
    config, last_depth_frame, floor_frame, live_stretch, homography_step,
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
)
from colormap import apply_colormap
from calibration import _update_live_stretch, get_effective_floor
from overlay import draw_status_overlay, draw_corner_target


def get_depth(dev, data, timestamp):
    last_depth_frame[0] = data.copy()
    depth = data.astype(np.float32)

    invalid = (data == 0) | (data == 2047)

    if live_stretch[0]:
        _update_live_stretch(depth)

    ref = get_effective_floor()
    if ref is not None:
        # Elevacion CON SIGNO respecto al suelo fijado: positiva = monticulo,
        # negativa = valle/hueco (ya no se recorta en 0 -- antes un valle se
        # via identico a la arena plana, ambos clipeados a elevacion 0).
        elev = ref - depth
        depth_max_safe = max(1, config['depth_max'])  # techo: monticulo mas alto
        depth_min_safe = max(1, config['depth_min'])  # ahora es la profundidad de valle mas honda
        pos_norm = np.clip(elev / depth_max_safe, 0.0, 1.0)
        neg_norm = np.clip(-elev / depth_min_safe, 0.0, 1.0)
        # 0.5 = elevacion cero (verde, el suelo fijado) -- ver colormap.py
        depth_norm = np.where(elev >= 0, 0.5 + 0.5 * pos_norm, 0.5 - 0.5 * neg_norm)
    else:
        rng = max(1, config['depth_max'] - config['depth_min'])
        # depth_max = base (valor alto, lejos del Kinect)
        # depth_min = elevacion maxima (valor bajo, cerca del Kinect)
        # objetos mas lejanos que depth_max se mapean a 0 (azul oscuro)
        depth_norm = 1.0 - np.clip((depth - config['depth_min']) / rng, 0.0, 1.0)

    depth_norm[invalid] = 0.0

    gray = (depth_norm * 255).astype(np.uint8)
    color = apply_colormap(gray)

    crop = config.get('crop')
    if crop is not None:
        x0, y0, x1, y1 = crop
        color = color[y0:y1, x0:x1]

    homography = config.get('homography')
    if homography is not None:
        h_matrix = np.array(homography, dtype=np.float32)
        display = cv2.warpPerspective(color, h_matrix, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    else:
        display = cv2.resize(color, (DISPLAY_WIDTH, DISPLAY_HEIGHT))

    if homography_step[0] >= 0:
        display = draw_corner_target(display, homography_step[0])
    else:
        display = draw_status_overlay(display)

    cv2.imshow('Sandbox', display)
    cv2.waitKey(1)


def get_video(dev, data, timestamp):
    pass
