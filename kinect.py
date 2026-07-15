import os
import time

import cv2
import numpy as np

from config import (
    config, last_depth_frame, floor_frame, live_stretch, auto_calib_status,
    homography_step, homography_points, homography_floor,
    DISPLAY_WIDTH, DISPLAY_HEIGHT, HOMOGRAPHY_TARGETS, FLOOR_FILE,
)
from colormap import apply_colormap

_stretch_tick = [0]


def _update_live_stretch(depth):
    _stretch_tick[0] = (_stretch_tick[0] + 1) % 5
    if _stretch_tick[0] != 0:
        return

    alpha = 0.15

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
        # depth_max = base (valor alto, lejos del Kinect)
        # depth_min = elevacion maxima (valor bajo, cerca del Kinect)
        # objetos mas lejanos que depth_max se mapean a 0 (azul oscuro)
        depth_norm = 1.0 - np.clip((depth - config['depth_min']) / rng, 0.0, 1.0)

    depth_norm[invalid] = 0.0

    gray = (depth_norm * 255).astype(np.uint8)
    color = apply_colormap(gray)

    homography = config.get('homography')
    if homography is not None:
        h_matrix = np.array(homography, dtype=np.float32)
        display = cv2.warpPerspective(color, h_matrix, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    else:
        display = cv2.resize(color, (DISPLAY_WIDTH, DISPLAY_HEIGHT))

    if homography_step[0] >= 0:
        display = draw_corner_target(display, homography_step[0])
    elif config['mode'] == 'calibration':
        display = draw_calibration_ui(display)

    cv2.imshow('Sandbox', display)
    cv2.waitKey(1)


def get_video(dev, data, timestamp):
    pass


def calibrate_floor():
    if last_depth_frame[0] is None:
        return False
    floor_frame[0] = last_depth_frame[0].astype(np.float32)
    np.save(FLOOR_FILE, floor_frame[0])
    return True


def reset_floor():
    floor_frame[0] = None
    if os.path.exists(FLOOR_FILE):
        os.remove(FLOOR_FILE)


def _find_marker_point():
    """Ubica en espacio Kinect (x,y) el punto mas elevado del frame actual (la mano).

    Requiere una referencia de suelo plano (homography_floor, o floor_frame si
    ya esta activo) para poder distinguir la mano de estructura fija mas
    cercana al Kinect que la arena (p.ej. el borde de madera de la caja).
    """
    if last_depth_frame[0] is None:
        return None
    d = last_depth_frame[0].astype(np.float32)
    valid = (d > 0) & (d < 2047)
    if not np.any(valid):
        return None

    ref = homography_floor[0] if homography_floor[0] is not None else floor_frame[0]
    if ref is None:
        return None

    elev = np.where(valid, ref - d, 0.0).astype(np.float32)
    # Suaviza antes de buscar el maximo: un pixel muerto/defectuoso del sensor
    # produce un pico aislado de un solo pixel que un promedio local aplasta,
    # mientras que una mano real (un blob de muchos pixeles elevados) sobrevive.
    elev_smooth = cv2.blur(elev, (9, 9))

    # Enmascara ANTES del argmax: un paquete USB corrupto (el RPi tiene
    # subvoltaje confirmado) produce regiones de cientos+ unidades que
    # sobreviven al blur. Si se buscara el maximo global sin enmascarar
    # primero, esa corrupcion siempre ganaria y una mano real presente en
    # el mismo frame nunca se consideraria.
    #
    # No basta con excluir solo el nucleo corrupto (>250): el blur arrastra
    # ese pico hacia abajo en un halo de transicion que roza justo debajo del
    # techo de 250, generando un candidato falso que le gana al pico real de
    # una mano (~80 unidades). Se dilata la zona excluida para cubrir tambien
    # ese halo, no solo el pixel/bloque que originalmente excede el rango.
    corrupt_core = (elev_smooth > 250).astype(np.uint8)
    if np.any(corrupt_core):
        corrupt_zone = cv2.dilate(corrupt_core, np.ones((21, 21), np.uint8)) > 0
    else:
        corrupt_zone = None

    in_range = (elev_smooth >= 12) & (elev_smooth <= 250)
    if corrupt_zone is not None:
        in_range &= ~corrupt_zone
    if not np.any(in_range):
        return None

    masked = np.where(in_range, elev_smooth, -np.inf)
    y, x = np.unravel_index(np.argmax(masked), masked.shape)
    print(f'[homografia-debug] peak_enmascarado={elev_smooth[y, x]:.1f} en ({int(x)},{int(y)})', flush=True)

    return int(x), int(y)


def _cluster_dominant_point(points, radius):
    """Encuentra el cluster espacial mas grande entre varios puntos muestreados
    (denso en un radio dado) y devuelve su centro y tamano. Tolera que una
    fraccion de las muestras sean ruido/corrupcion, siempre que la senal real
    (la mano quieta) sea la mas consistente en el tiempo."""
    arr = np.array(points, dtype=np.float32)
    dist = np.linalg.norm(arr[:, None, :] - arr[None, :, :], axis=2)
    seed = int(np.argmax((dist <= radius).sum(axis=1)))
    in_cluster = dist[seed] <= radius
    if not np.any(in_cluster):
        return None, 0
    center = arr[in_cluster].mean(axis=0)
    return center, int(in_cluster.sum())


def _capture_stable_point(samples=20, interval=0.08, cluster_radius=15,
                           min_cluster_abs=6, min_cluster_frac=0.35):
    """Muestrea muchos frames en una ventana de ~1.6s y se queda con el
    cluster espacial dominante -- tolera que la mayoria de las muestras
    individuales esten corrompidas por perdida de paquetes USB del Kinect,
    siempre que la mano real sea la posicion mas consistente en el tiempo."""
    points = []
    for _ in range(samples):
        p = _find_marker_point()
        if p is not None:
            points.append(p)
        time.sleep(interval)

    if len(points) < min_cluster_abs:
        return None

    center, size = _cluster_dominant_point(points, cluster_radius)
    if center is None or size < max(min_cluster_abs, int(round(min_cluster_frac * len(points)))):
        return None

    return int(round(center[0])), int(round(center[1]))


def _polygon_area(points):
    """Area de un poligono via formula del shoelace -- sirve para detectar
    esquinas capturadas demasiado juntas, casi colineales, o en orden
    cruzado (que producen homografias degeneradas)."""
    n = len(points)
    area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def start_homography_calibration():
    if last_depth_frame[0] is None:
        return False
    homography_floor[0] = last_depth_frame[0].astype(np.float32)
    homography_points[0] = []
    homography_step[0] = 0
    return True


def cancel_homography_calibration():
    homography_step[0] = -1
    homography_points[0] = []
    homography_floor[0] = None


def capture_homography_point():
    step = homography_step[0]
    if step < 0 or step > 3:
        return {'error': 'calibracion no iniciada'}

    point = _capture_stable_point()
    if point is None:
        return {'error': 'mantén la mano firme sobre la marca un momento e intenta de nuevo'}

    homography_points[0].append(point)
    print(f'[homografia] esquina {step + 1}/4 capturada en {point}')

    if step == 3:
        pts = homography_points[0]
        area = _polygon_area(pts)
        frame_area = last_depth_frame[0].shape[0] * last_depth_frame[0].shape[1]
        min_area = frame_area * 0.08
        if area < min_area:
            print(f'[homografia] RECHAZADA: puntos={pts} area={area:.0f}px2 (minimo {min_area:.0f}px2)')
            homography_step[0] = -1
            homography_points[0] = []
            homography_floor[0] = None
            return {'error': f'las 4 esquinas quedaron muy juntas o en orden incorrecto (area={int(area)}px²). Vuelve a iniciar y sigue con cuidado cada marca proyectada, en orden.'}

        kinect_pts = np.array(pts, dtype=np.float32)
        screen_pts = np.array(HOMOGRAPHY_TARGETS, dtype=np.float32)
        h_matrix = cv2.getPerspectiveTransform(kinect_pts, screen_pts)
        config['homography'] = h_matrix.tolist()
        print(f'[homografia] CALIBRADA OK: puntos={pts} area={area:.0f}px2')
        homography_step[0] = -1
        homography_points[0] = []
        homography_floor[0] = None
        return {'done': True}

    homography_step[0] = step + 1
    return {'done': False, 'next_step': homography_step[0]}


def reset_homography():
    config['homography'] = None
    homography_step[0] = -1
    homography_points[0] = []
    homography_floor[0] = None


def auto_calibrate():
    auto_calib_status[0] = 'Leyendo...'
    if last_depth_frame[0] is None:
        auto_calib_status[0] = 'Error: sin datos'
        return
    if floor_frame[0] is None:
        auto_calib_status[0] = 'Error: primero completa el Paso 1 (Calibrar Base)'
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
