import freenect
import numpy as np
import cv2
import json
import os
import threading

os.environ['LIBUSB_DEBUG'] = '0'

DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080
CONFIG_FILE = os.path.expanduser('~/sandbox_config.json')

config = {
    'depth_min': 400,
    'depth_max': 2000,
    'mode': 'calibration'
}

colormap_idx = [0]

# Colormaps disponibles
colormaps_builtin = [cv2.COLORMAP_JET, cv2.COLORMAP_TURBO, cv2.COLORMAP_RAINBOW, cv2.COLORMAP_HOT]
colormap_names = ['JET', 'TURBO', 'RAINBOW', 'TOPO']

def make_topo_colormap():
    """Colormap topográfico: azul oscuro → azul → verde → amarillo → rojo → blanco"""
    colors = [
        (0,   [0,   0,   80]),   # azul muy oscuro
        (60,  [0,   60,  180]),  # azul
        (100, [0,   160, 200]),  # azul claro
        (140, [0,   180, 80]),   # verde
        (180, [180, 210, 0]),    # amarillo verde
        (210, [255, 160, 0]),    # naranja
        (240, [200, 0,   0]),    # rojo
        (255, [255, 255, 255]),  # blanco
    ]
    lut = np.zeros((256, 1, 3), dtype=np.uint8)
    for i in range(len(colors) - 1):
        v0, c0 = colors[i]
        v1, c1 = colors[i + 1]
        for v in range(v0, v1):
            t = (v - v0) / (v1 - v0)
            lut[v, 0] = [int(c0[j] + t * (c1[j] - c0[j])) for j in range(3)]
    lut[255, 0] = colors[-1][1]
    return lut

topo_lut = make_topo_colormap()

def apply_colormap(gray, idx):
    if colormap_names[idx] == 'TOPO':
        return cv2.applyColorMap(gray, topo_lut)
    return cv2.applyColorMap(gray, colormaps_builtin[idx])

def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            saved = json.load(f)
            config.update(saved)

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump({k: v for k, v in config.items() if k != 'colormap'}, f)

def draw_calibration_ui(frame):
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (440, 200), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    cv2.putText(frame, 'MODO CALIBRACION', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(frame, f'depth_min: {config["depth_min"]}  (a/z)', (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
    cv2.putText(frame, f'depth_max: {config["depth_max"]}  (s/x)', (20, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
    cv2.putText(frame, f'colormap: {colormap_names[colormap_idx[0]]}  (c)', (20, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
    cv2.putText(frame, 'g=guardar  e=exhibicion  q=salir', (20, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
    return frame

def get_depth(dev, data, timestamp):
    depth = data.astype(np.float32)
    depth = np.clip(depth, config['depth_min'], config['depth_max'])
    depth = (depth - config['depth_min']) / (config['depth_max'] - config['depth_min'])
    depth = 1.0 - depth
    depth = (depth * 255).astype(np.uint8)
    color = apply_colormap(depth, colormap_idx[0])
    color = cv2.resize(color, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    if config['mode'] == 'calibration':
        color = draw_calibration_ui(color)
    cv2.imshow('Sandbox', color)
    cv2.waitKey(1)

def get_video(dev, data, timestamp):
    pass

def print_status():
    print("=" * 40)
    print(f"  depth_min  : {config['depth_min']}")
    print(f"  depth_max  : {config['depth_max']}")
    print(f"  colormap   : {colormap_names[colormap_idx[0]]}")
    print(f"  modo       : {config['mode']}")
    print("=" * 40)

def command_listener():
    os.system('clear')
    print("=" * 40)
    print("  SANDBOX - CONTROL DESDE TERMINAL")
    print("=" * 40)
    print("  a = depth_min -50")
    print("  z = depth_min +50")
    print("  s = depth_max -50")
    print("  x = depth_max +50")
    print("  c = cambiar colormap")
    print("  g = guardar configuracion")
    print("  e = modo exhibicion")
    print("  b = modo calibracion")
    print("  q = salir")
    print("=" * 40)
    while True:
        cmd = input("cmd> ").strip()
        os.system('clear')
        if cmd == 'a':
            config['depth_min'] = max(0, config['depth_min'] - 50)
        elif cmd == 'z':
            config['depth_min'] = min(config['depth_max'] - 50, config['depth_min'] + 50)
        elif cmd == 's':
            config['depth_max'] = max(config['depth_min'] + 50, config['depth_max'] - 50)
        elif cmd == 'x':
            config['depth_max'] = min(4000, config['depth_max'] + 50)
        elif cmd == 'c':
            colormap_idx[0] = (colormap_idx[0] + 1) % len(colormap_names)
        elif cmd == 'g':
            save_config()
            print("✅ Configuracion guardada")
        elif cmd == 'e':
            config['mode'] = 'exhibition'
        elif cmd == 'b':
            config['mode'] = 'calibration'
        elif cmd == 'q':
            freenect.kill_runloop()
            break
        print_status()

load_config()
t = threading.Thread(target=command_listener, daemon=True)
t.start()
cv2.namedWindow('Sandbox', cv2.WINDOW_NORMAL)
cv2.moveWindow('Sandbox', 0, 0)
cv2.resizeWindow('Sandbox', DISPLAY_WIDTH, DISPLAY_HEIGHT)
cv2.setWindowProperty('Sandbox', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
freenect.runloop(depth=get_depth, video=get_video)
