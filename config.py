import os
import json

DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080
CONFIG_FILE = os.path.expanduser('~/sandbox_config.json')

config = {
    'depth_min': 400,
    'depth_max': 2000,
    'mode': 'calibration'
}

colormap_idx = [0]
colormap_names = ['JET', 'TURBO', 'RAINBOW', 'TOPO']
last_depth_frame = [None]
floor_frame = [None]
auto_calib_status = ['Listo']


def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            saved = json.load(f)
            config.update(saved)


def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump({k: v for k, v in config.items()}, f)
