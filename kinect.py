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
        elev = floor_frame[0] - depth  # con signo -- monticulos y valles
        # Excluye picos de corrupcion USB (1000+ unidades) del calculo,
        # mismo problema y arreglo que en auto_calibrate().
        pos_valid = elev[(elev > 8) & (elev < 300)]
        neg_valid = elev[(elev < -8) & (elev > -300)]
        if len(pos_valid) + len(neg_valid) < 500:
            return
        if len(pos_valid) > 0:
            new_max = max(int(np.percentile(pos_valid, 97)), 20)
            config['depth_max'] = int(alpha * new_max + (1 - alpha) * config['depth_max'])
        if len(neg_valid) > 0:
            new_valley = max(int(np.percentile(-neg_valid, 97)), 20)
            config['depth_min'] = int(alpha * new_valley + (1 - alpha) * config['depth_min'])
    else:
        valid = depth[(depth > 0) & (depth < 2047)]
        if len(valid) < 500:
            return
        new_min = max(0, int(np.percentile(valid, 2)) - 5)
        new_max = min(2047, int(np.percentile(valid, 98)) + 5)
        config['depth_min'] = int(alpha * new_min + (1 - alpha) * config['depth_min'])
        config['depth_max'] = int(alpha * new_max + (1 - alpha) * config['depth_max'])


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
        # Elevacion CON SIGNO respecto al suelo fijado: positiva = monticulo,
        # negativa = valle/hueco (ya no se recorta en 0 -- antes un valle se
        # via identico a la arena plana, ambos clipeados a elevacion 0).
        elev = floor_frame[0] - depth
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


def calibrate_floor():
    if last_depth_frame[0] is None:
        return False
    floor_frame[0] = last_depth_frame[0].astype(np.float32)
    np.save(FLOOR_FILE, floor_frame[0])
    return True


def reset_floor():
    floor_frame[0] = None
    config['range_calibrated'] = False
    if os.path.exists(FLOOR_FILE):
        os.remove(FLOOR_FILE)


def detect_sand_crop(floor):
    """Encuentra el rectangulo de arena dentro del frame del Kinect, a partir
    de un snapshot de suelo plano y vacio (floor_frame). Distingue la arena
    del marco de madera (mas cerca del Kinect) y del fondo mas alla de la
    caja (mas lejos) por su banda de profundidad -- sin necesitar rastreo en
    vivo ni gestos, evitando el ruido USB que afecto la deteccion de mano.
    Nunca falla de forma destructiva: cualquier caso ambiguo devuelve
    (None, mensaje, None), preservando pantalla completa sin recortar.
    """
    h, w = floor.shape
    valid = (floor > 0) & (floor < 2047)
    if np.count_nonzero(valid) < 0.5 * floor.size:
        return None, 'cobertura insuficiente, se usa pantalla completa', None

    depths = floor[valid]
    hist, edges = np.histogram(depths, bins=64, range=(1, 2046))
    peak = np.argmax(hist)
    lo, hi = edges[peak], edges[peak + 1]
    dominant = float(depths[(depths >= lo) & (depths < hi)].mean())

    tol = 50.0  # gaps reales observados ~170-300 unidades entre marco/arena/fondo
    mask = ((np.abs(floor - dominant) <= tol) & valid).astype(np.uint8) * 255
    k = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)   # limpia ruido puntual (corrupcion USB)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)  # rellena huecos

    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return None, 'no se distinguió la arena del marco/fondo, se usa pantalla completa', None

    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y = int(stats[best, cv2.CC_STAT_LEFT]), int(stats[best, cv2.CC_STAT_TOP])
    bw, bh = int(stats[best, cv2.CC_STAT_WIDTH]), int(stats[best, cv2.CC_STAT_HEIGHT])
    area = int(stats[best, cv2.CC_STAT_AREA])

    if area < 0.15 * h * w or bw < 40 or bh < 40:
        return None, f'área detectada demasiado pequeña ({bw}x{bh}px), se usa pantalla completa', None
    if x <= 1 and y <= 1 and x + bw >= w - 1 and y + bh >= h - 1:
        return None, 'no se detectó un borde real (ocupa todo el cuadro), se usa pantalla completa', None

    crop = [x, y, x + bw, y + bh]
    long_s, short_s = max(bw, bh), min(bw, bh)
    ratio_expected = 71.0 / 41.0  # medidas reales de la arena
    warn = None
    if abs(long_s / short_s - ratio_expected) / ratio_expected > 0.30:
        warn = f'área detectada ({bw}x{bh}px) no coincide con proporciones esperadas de la caja (41x71cm) — verifica visualmente'
    return crop, f'área de arena detectada: {bw}x{bh}px en ({x},{y})', warn


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
        # Elevacion CON SIGNO (monticulos positivos, valles negativos) --
        # se analizan ambos lados por separado para calibrar el techo
        # (depth_max) y la profundidad de valle (depth_min) de forma
        # independiente, segun el relieve real construido.
        elev = floor_frame[0] - depth
        # Suaviza para diluir picos aislados de corrupcion USB del Kinect
        # (confirmados en esta RPi, ver commit d6ec428) y excluye lo que
        # quede por encima/debajo de un techo sano -- sin esto, unos pocos
        # pixeles con elevacion falsa de 1000+ jalan el percentil muy por
        # encima de cualquier monticulo o valle real (~150 unidades como
        # mucho).
        elev_smooth = cv2.blur(elev, (9, 9))
        pos_elev = elev_smooth[(elev_smooth > 8) & (elev_smooth < 300)]
        neg_elev = elev_smooth[(elev_smooth < -8) & (elev_smooth > -300)]

        if len(pos_elev) == 0 and len(neg_elev) == 0:
            config['depth_max'] = 100
            config['depth_min'] = 30
            auto_calib_status[0] = 'Sin relieve detectado, rango por defecto'
            return

        if len(pos_elev) > 0:
            max_elev = int(np.percentile(pos_elev, 95))
            config['depth_max'] = max(max_elev + 20, 30)
        if len(neg_elev) > 0:
            max_valley = int(np.percentile(-neg_elev, 95))
            config['depth_min'] = max(max_valley + 20, 30)

        config['range_calibrated'] = True
        auto_calib_status[0] = f'OK: relieve -{config["depth_min"]} a +{config["depth_max"]} unidades'
    else:
        valid = depth[(depth > 0) & (depth < 2047)]
        if len(valid) == 0:
            auto_calib_status[0] = 'Error: sin datos validos'
            return
        p2 = int(np.percentile(valid, 2))
        p98 = int(np.percentile(valid, 98))
        config['depth_min'] = max(0, p2 - 5)
        config['depth_max'] = min(2047, p98 + 5)
        config['range_calibrated'] = True
        auto_calib_status[0] = f'OK: min={config["depth_min"]} max={config["depth_max"]}'
