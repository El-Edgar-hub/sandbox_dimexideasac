import os
import json

DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080
CONFIG_FILE = os.path.expanduser('~/sandbox_config.json')

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
}

last_depth_frame = [None]
floor_frame = [None]
live_stretch = [False]
auto_calib_status = ['Listo']
homography_step = [-1]      # -1 = inactivo, 0..3 = esperando captura de esa esquina
homography_points = [[]]    # puntos Kinect (x,y) capturados hasta ahora


def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            saved = json.load(f)
            config.update(saved)


def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump({k: v for k, v in config.items()}, f)
