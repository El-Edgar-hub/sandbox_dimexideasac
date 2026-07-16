import os
import threading

import cv2
import numpy as np

from config import (
    config, last_depth_frame, floor_frame, auto_calib_status, FLOOR_FILE,
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
)

_stretch_tick = [0]
_geo_lock = threading.Lock()


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


def _dominant_sand_component(floor):
    """Aisla el componente conectado dominante de arena dentro del frame de
    Kinect, a partir de un snapshot de suelo plano y vacio -- banda de
    profundidad dominante + morfologia 7x7 + mayor area conectada. Usado
    tanto por detect_sand_crop() (rectangulo) como por extract_sand_quad()
    (poligono real), para que ambos hablen siempre del mismo blob y nunca
    puedan estar en desacuerdo sobre cual region es la arena.

    Devuelve (comp_mask, stats_row, dominant, tol, error) -- comp_mask es
    la mascara SOLO del componente elegido (no la mascara completa), o
    (None, None, None, None, mensaje) si no se pudo aislar nada confiable.
    Nunca lanza excepcion.
    """
    valid = (floor > 0) & (floor < 2047)
    if np.count_nonzero(valid) < 0.5 * floor.size:
        return None, None, None, None, 'cobertura insuficiente, se usa pantalla completa'

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

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return None, None, None, None, 'no se distinguió la arena del marco/fondo, se usa pantalla completa'

    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    comp_mask = (labels == best).astype(np.uint8) * 255
    return comp_mask, stats[best], dominant, tol, None


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
    comp_mask, stats_row, dominant, tol, err = _dominant_sand_component(floor)
    if err is not None:
        return None, err, None

    x, y = int(stats_row[cv2.CC_STAT_LEFT]), int(stats_row[cv2.CC_STAT_TOP])
    bw, bh = int(stats_row[cv2.CC_STAT_WIDTH]), int(stats_row[cv2.CC_STAT_HEIGHT])
    area = int(stats_row[cv2.CC_STAT_AREA])

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


def _order_quad_tl_tr_br_bl(pts):
    """Ordena 4 puntos como TL,TR,BR,BL usando suma/diferencia de
    coordenadas (x+y minimo/maximo para TL/BR, x-y maximo/minimo para
    TR/BL) -- no depende del orden ni sentido en que OpenCV recorrio el
    contorno. Valido mientras la caja no aparezca rotada ~45 grados dentro
    del cuadro del Kinect (no es el caso de este montaje: la inclinacion
    real es de "profundidad" -- Kinect no perpendicular -- no una rotacion
    del cuadro en el plano de la imagen)."""
    pts = np.asarray(pts, dtype=np.float64)
    s = pts.sum(axis=1)
    d = pts[:, 0] - pts[:, 1]
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmax(d)]
    bl = pts[np.argmin(d)]
    return np.array([tl, tr, br, bl])


def extract_sand_quad(floor):
    """Extrae las 4 esquinas REALES (TL,TR,BR,BL) de la arena, en vez de
    asumir un rectangulo alineado a los ejes como detect_sand_crop() --
    traza el contorno real tal como el Kinect lo ve (banda de profundidad
    dominante + morfologia + envolvente convexa + reduccion a 4 vertices),
    sin necesitar saber nada sobre el montaje fisico del Kinect (posicion,
    angulo, campo de vision). Devuelve (quad, mensaje, warn) -- quad es
    [[x,y]x4] en el mismo espacio nativo de floor (640x480), o None si la
    extraccion no fue confiable (el llamador debe seguir usando el
    rectangulo de detect_sand_crop). Nunca lanza excepcion.
    """
    h, w = floor.shape
    comp_mask, _, _, _, err = _dominant_sand_component(floor)
    if err is not None:
        return None, err, None

    # Cierre extra sobre una COPIA (nunca se toca la mascara que usa
    # detect_sand_crop) + envolvente convexa: el hull no puede introducir
    # concavidades falsas por ruido, solo suaviza hacia afuera.
    k2 = np.ones((11, 11), np.uint8)
    smoothed = cv2.morphologyEx(comp_mask.copy(), cv2.MORPH_CLOSE, k2)
    contours, _ = cv2.findContours(smoothed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, 'no se encontró un contorno de arena, se usa el rectángulo', None

    contour = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)
    if hull_area < 0.15 * h * w:
        return None, 'contorno de arena demasiado pequeño, se usa el rectángulo', None

    peri = cv2.arcLength(hull, True)
    approx = None
    for frac in (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12):
        cand = cv2.approxPolyDP(hull, frac * peri, True)
        if len(cand) == 4:
            approx = cand
            break
    if approx is None:
        return None, 'no se pudo reducir el contorno a 4 esquinas, se usa el rectángulo', None
    if not cv2.isContourConvex(approx):
        return None, 'el contorno de arena no es convexo, se usa el rectángulo', None

    pts = approx.reshape(4, 2).astype(np.float64)
    quad = _order_quad_tl_tr_br_bl(pts)

    quad_area = _quad_area(quad.tolist())
    if hull_area > 0 and abs(quad_area - hull_area) / hull_area > 0.30:
        return None, 'las esquinas extraídas no formaron un polígono válido, se usa el rectángulo', None

    quad_list = [[float(px), float(py)] for px, py in quad]
    return quad_list, 'forma real de la arena extraída de los datos de profundidad', None


MEASURED_DISTANCES_CM = {'TL': 102.0, 'TR': 96.0, 'BR': 94.0, 'BL': 98.0}  # medidas con cinta metrica


def check_quad_against_measurements(quad, floor, measured=None, window=5):
    """Verificacion de sanidad (NO un calculo): compara el ORDEN relativo de
    las 4 distancias medidas a cinta metrica contra el orden relativo de la
    profundidad cruda real leida junto a cada esquina ya extraida por
    extract_sand_quad(). Profundidad cruda mas alta = mas lejos del Kinect
    (ver kinect.py), asi que no hace falta ninguna conversion cruda<->cm --
    solo se compara el signo de la diferencia entre grupos de esquinas, no
    el valor exacto. Nunca lanza excepcion."""
    measured = measured or MEASURED_DISTANCES_CM
    labels = ['TL', 'TR', 'BR', 'BL']
    h, w = floor.shape
    _, _, dominant, tol, err = _dominant_sand_component(floor)
    if err is not None:
        return False, f'no se pudo verificar: {err}'

    raw = {}
    for label, (x, y) in zip(labels, quad):
        xi, yi = int(round(x)), int(round(y))
        x0, x1 = max(0, xi - window), min(w, xi + window + 1)
        y0, y1 = max(0, yi - window), min(h, yi + window + 1)
        patch = floor[y0:y1, x0:x1]
        base = (patch > 0) & (patch < 2047)
        band = base & (np.abs(patch - dominant) <= tol)
        valid = patch[band] if np.any(band) else patch[base]
        if len(valid) == 0:
            return False, f'sin datos válidos junto a la esquina {label}'
        raw[label] = float(np.mean(valid))

    m_right_closer = (measured['TR'] + measured['BR']) < (measured['TL'] + measured['BL'])
    r_right_closer = (raw['TR'] + raw['BR']) < (raw['TL'] + raw['BL'])
    m_bottom_closer = (measured['BL'] + measured['BR']) < (measured['TL'] + measured['TR'])
    r_bottom_closer = (raw['BL'] + raw['BR']) < (raw['TL'] + raw['TR'])

    detail = f"medido(cm)={measured} crudo={raw}"
    fails = []
    if m_right_closer != r_right_closer:
        fails.append('izquierda/derecha')
    if m_bottom_closer != r_bottom_closer:
        fails.append('arriba/abajo')
    if fails:
        return False, f'discrepancia en {", ".join(fails)} -- {detail}'
    return True, f'orden coincide -- {detail}'


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


def _default_geo_corners():
    return [[0, 0], [DISPLAY_WIDTH, 0], [DISPLAY_WIDTH, DISPLAY_HEIGHT], [0, DISPLAY_HEIGHT]]


def current_geo_corners():
    """Las 4 esquinas destino actuales (TL,TR,BR,BL) en espacio 1920x1080 --
    config['geo_corners'] si ya se ajustaron a mano, o el rectangulo de
    pantalla completa por defecto (equivalente geometrico al cv2.resize de
    siempre, sin keystone)."""
    return config.get('geo_corners') or _default_geo_corners()


def _crop_dims():
    crop = config.get('crop')
    if crop is not None:
        x0, y0, x1, y1 = crop
        return x1 - x0, y1 - y0
    return 640, 480  # resolucion nativa Kinect, sin crop activo


def _quad_area(pts):
    area = 0.0
    for i in range(4):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % 4]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _apply_geo_corners(corners):
    """Recalcula config['homography'] a partir de las 4 esquinas destino
    dadas y las dimensiones ACTUALES de crop. Nunca deja config['homography']
    en un estado invalido: si el calculo falla o el area queda demasiado
    chica, no toca nada y devuelve el error."""
    min_area = 0.15 * DISPLAY_WIDTH * DISPLAY_HEIGHT  # mismo umbral que detect_sand_crop
    if _quad_area(corners) < min_area:
        return False, 'las esquinas quedaron demasiado juntas, deshaz el ultimo ajuste'
    quad = config.get('kinect_quad')
    if quad is not None:
        # Forma real de la arena (ver extract_sand_quad) en espacio Kinect
        # nativo 640x480 -- reemplaza el rectangulo ingenuo cuando esta
        # disponible.
        src = np.array(quad, dtype=np.float32)
    else:
        w, h = _crop_dims()
        src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    dst = np.array(corners, dtype=np.float32)
    try:
        h_matrix = cv2.getPerspectiveTransform(src, dst)
    except cv2.error:
        return False, 'no se pudo calcular la geometria con esas esquinas'
    config['geo_corners'] = corners
    config['homography'] = h_matrix.tolist()
    return True, None


def nudge_geo_corner(corner, dx, dy):
    if corner not in (0, 1, 2, 3):
        return False, 'esquina invalida'
    with _geo_lock:
        corners = [list(p) for p in current_geo_corners()]  # copia -- nunca mutar el objeto ya guardado
        x, y = corners[corner]
        corners[corner] = [
            max(0, min(DISPLAY_WIDTH, x + dx)),
            max(0, min(DISPLAY_HEIGHT, y + dy)),
        ]
        return _apply_geo_corners(corners)


def reset_geo_corners():
    with _geo_lock:
        config['geo_corners'] = None
        config['homography'] = None


def recompute_geo_homography():
    """Llamar despues de cualquier cambio a config['crop'] (p.ej. una nueva
    Captura de Base) -- si ya habia geometria ajustada a mano, la recalcula
    contra las nuevas dimensiones de crop en vez de dejarla desalineada."""
    with _geo_lock:
        corners = config.get('geo_corners')
        if corners is None:
            return
        _apply_geo_corners(corners)
