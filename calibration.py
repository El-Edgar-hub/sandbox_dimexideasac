import os

import cv2
import numpy as np

from config import config, last_depth_frame, floor_frame, auto_calib_status, FLOOR_FILE

_stretch_tick = [0]


def get_effective_floor():
    """Suelo de referencia real usado para calcular elevacion -- floor_frame
    con un desplazamiento manual (zero_offset) aplicado, para poder mover el
    nivel CERO (verde) sin tener que recapturar el suelo. offset positivo =
    sube el nivel cero (necesita menos profundidad cruda para ser "cero")."""
    if floor_frame[0] is None:
        return None
    return floor_frame[0] - config.get('zero_offset', 0)


def _update_live_stretch(depth):
    _stretch_tick[0] = (_stretch_tick[0] + 1) % 5
    if _stretch_tick[0] != 0:
        return

    alpha = 0.15

    ref = get_effective_floor()
    if ref is not None:
        elev = ref - depth  # con signo -- monticulos y valles
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


def calibrate_floor():
    if last_depth_frame[0] is None:
        return False
    floor_frame[0] = last_depth_frame[0].astype(np.float32)
    config['zero_offset'] = 0  # una nueva captura de suelo ya es el cero real
    np.save(FLOOR_FILE, floor_frame[0])
    return True


def reset_floor():
    floor_frame[0] = None
    config['range_calibrated'] = False
    config['zero_offset'] = 0
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


def auto_calibrate():
    auto_calib_status[0] = 'Leyendo...'
    if last_depth_frame[0] is None:
        auto_calib_status[0] = 'Error: sin datos'
        return
    if floor_frame[0] is None:
        auto_calib_status[0] = 'Error: primero completa el Paso 1 (Calibrar Base)'
        return
    depth = last_depth_frame[0].astype(np.float32)

    ref = get_effective_floor()
    if ref is not None:
        # Elevacion CON SIGNO (monticulos positivos, valles negativos) --
        # se analizan ambos lados por separado para calibrar el techo
        # (depth_max) y la profundidad de valle (depth_min) de forma
        # independiente, segun el relieve real construido.
        elev = ref - depth
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
