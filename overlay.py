import cv2

from config import config, floor_frame, HOMOGRAPHY_TARGETS

_DONE = (183, 231, 110)     # #6ee7b7 (BGR) -- mismo verde "listo" de la interfaz web
_PENDING = (36, 191, 251)   # #fbbf24 (BGR) -- mismo ambar "pendiente" de la interfaz web
_CALIB_BG = (216, 78, 29)   # #1d4ed8 (BGR) -- mismo azul del pill "CALIBRACION"
_EXHIB_BG = (70, 95, 6)     # #065f46 (BGR) -- mismo verde del pill "EXHIBICION"


def _draw_calibration_panel(frame):
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (520, 175), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    cv2.rectangle(frame, (20, 18), (260, 50), _CALIB_BG, -1)
    cv2.putText(frame, 'CALIBRACION', (30, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    floor_ok = floor_frame[0] is not None
    range_ok = config.get('range_calibrated', False)
    p1 = 'Paso 1: Suelo OK' if floor_ok else 'Paso 1: Suelo pendiente'
    cv2.putText(frame, p1, (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, _DONE if floor_ok else _PENDING, 2)
    p2 = f'Paso 2: Rango OK (-{config["depth_min"]} a +{config["depth_max"]}u)' if range_ok else 'Paso 2: Rango pendiente'
    cv2.putText(frame, p2, (20, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.6, _DONE if range_ok else _PENDING, 2)
    cv2.putText(frame, f'depth_min:{config["depth_min"]}  depth_max:{config["depth_max"]}',
                (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1)
    return frame


def _draw_exhibition_badge(frame):
    h, w = frame.shape[:2]
    label = 'EXHIBICION'
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x1, y1 = w - tw - 30, 10
    x2, y2 = w - 10, 20 + th
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), _EXHIB_BG, -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    cv2.putText(frame, label, (x1 + 10, y2 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, _DONE, 2)
    return frame


def draw_status_overlay(frame):
    return _draw_exhibition_badge(frame) if config['mode'] == 'exhibition' else _draw_calibration_panel(frame)


_GEO_GUIDE = (255, 0, 255)  # magenta BGR -- no aparece en el colormap topo, siempre distinguible


def draw_geo_guides(frame, corners):
    """Dibuja las 4 esquinas destino actuales del ajuste manual de keystone
    (ver calibration.current_geo_corners) para que el usuario vea donde
    esta cada esquina mientras las mueve con los botones de flecha de la
    app. Se llama solo en modo calibracion (ver kinect.py)."""
    pts = [(int(x), int(y)) for x, y in corners]
    for i in range(4):
        cv2.line(frame, pts[i], pts[(i + 1) % 4], _GEO_GUIDE, 3)
    for i, (x, y) in enumerate(pts):
        cv2.circle(frame, (x, y), 14, _GEO_GUIDE, -1)
        cv2.putText(frame, str(i + 1), (x + 18, y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return frame


def draw_corner_target(frame, step):
    tx, ty = HOMOGRAPHY_TARGETS[step]
    cv2.drawMarker(frame, (tx, ty), (0, 0, 255), cv2.MARKER_CROSS, 60, 4)
    cv2.circle(frame, (tx, ty), 36, (0, 0, 255), 3)
    line1 = f'Esquina {step + 1}/4 - un dedo (no la palma) sobre la marca'
    line2 = 'Bajo, ~8-10cm de la arena, quieto un momento'
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 85), (0, 0, 0), -1)
    cv2.putText(frame, line1, (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2)
    cv2.putText(frame, line2, (20, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
    return frame
