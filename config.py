import os
import json

import numpy as np

DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080
CONFIG_FILE = os.path.expanduser('~/sandbox_config.json')
FLOOR_FILE = os.path.expanduser('~/sandbox_floor.npy')

# Esquinas objetivo en espacio de proyector para la calibracion de homografia
# (con margen para que la mano quepa completa dentro de la caja al calibrar)
HOMOGRAPHY_MARGIN = 150
HOMOGRAPHY_TARGETS = [
    (HOMOGRAPHY_MARGIN,                  HOMOGRAPHY_MARGIN),
    (DISPLAY_WIDTH - HOMOGRAPHY_MARGIN,  HOMOGRAPHY_MARGIN),
    (DISPLAY_WIDTH - HOMOGRAPHY_MARGIN,  DISPLAY_HEIGHT - HOMOGRAPHY_MARGIN),
    (HOMOGRAPHY_MARGIN,                  DISPLAY_HEIGHT - HOMOGRAPHY_MARGIN),
]

config = {
    'depth_min': 400,
    'depth_max': 2000,
    'mode': 'calibration',
    'homography': None,   # matriz 3x3 (lista de listas) o None si no calibrada
    'crop': None,          # [x0,y0,x1,y1] en espacio Kinect 640x480, o None
    'range_calibrated': False,   # True solo cuando auto_calibrate() midio un rango real
    'zero_offset': 0,      # unidades crudas restadas a floor_frame antes de medir elevacion
                            # (positivo = sube el nivel cero, ver calibration.get_effective_floor)
    'geo_corners': None,    # [[x,y]x4] TL,TR,BR,BL en espacio 1920x1080, o None
                            # (None == pantalla completa, ver calibration.current_geo_corners)
    'kinect_quad': None,    # [[x,y]x4] TL,TR,BR,BL en espacio Kinect nativo 640x480, o None
                            # (None == usa el rectangulo de crop, ver calibration.extract_sand_quad)
}

last_depth_frame = [None]
last_preview_frame = [None]  # ultimo frame ya coloreado/recortado, para /preview.jpg
floor_frame = [None]
live_stretch = [False]
auto_calib_status = ['Listo']
homography_step = [-1]      # -1 = inactivo, 0..3 = esperando captura de esa esquina
homography_points = [[]]    # puntos Kinect (x,y) capturados hasta ahora
homography_floor = [None]   # referencia de suelo plano solo para detectar la mano
                             # durante la calibracion de esquinas (no afecta el render)


def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            saved = json.load(f)
            config.update(saved)

    # El suelo (floor_frame) es un array en memoria, no parte de `config` --
    # se guarda por separado como .npy para sobrevivir a un reinicio del
    # proceso sin tener que volver a nivelar y calibrar la arena.
    if os.path.exists(FLOOR_FILE):
        try:
            loaded = np.load(FLOOR_FILE)
            if loaded.shape == (480, 640):
                floor_frame[0] = loaded
        except (OSError, ValueError):
            pass


def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump({k: v for k, v in config.items()}, f)
