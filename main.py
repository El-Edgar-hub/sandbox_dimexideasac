import freenect
import numpy as np
import cv2
import json
import os

DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080
CONFIG_FILE = os.path.expanduser('~/sandbox_config.json')

# Configuración por defecto
config = {
    'depth_min': 400,
    'depth_max': 2000,
    'colormap': cv2.COLORMAP_JET,
    'mode': 'calibration'  # 'calibration' o 'exhibition'
}

def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            saved = json.load(f)
            config.update(saved)

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump({k: v for k, v in config.items() if k != 'colormap'}, f)
    print('✅ Configuración guardada')

def draw_calibration_ui(frame):
    h, w = frame.shape[:2]
    # Panel de información
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (400, 180), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    # Texto de controles
    cv2.putText(frame, 'MODO CALIBRACION', (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(frame, f'depth_min: {config["depth_min"]}  (A/Z)', (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    cv2.putText(frame, f'depth_max: {config["depth_max"]}  (S/X)', (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    cv2.putText(frame, 'C: cambiar color  G: guardar', (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    cv2.putText(frame, 'E: modo exhibicion  Q: salir', (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return frame

colormaps = [cv2.COLORMAP_JET, cv2.COLORMAP_HOT, cv2.COLORMAP_RAINBOW, cv2.COLORMAP_TURBO]
colormap_names = ['JET', 'HOT', 'RAINBOW', 'TURBO']
colormap_idx = [0]

def get_depth(dev, data, timestamp):
    depth = data.astype(np.float32)
    depth = np.clip(depth, config['depth_min'], config['depth_max'])
    depth = (depth - config['depth_min']) / (config['depth_max'] - config['depth_min'])
    depth = 1.0 - depth
    depth = (depth * 255).astype(np.uint8)
    color = cv2.applyColorMap(depth, colormaps[colormap_idx[0]])
    color = cv2.resize(color, (DISPLAY_WIDTH, DISPLAY_HEIGHT))

    if config['mode'] == 'calibration':
        color = draw_calibration_ui(color)

    cv2.imshow('Sandbox', color)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        freenect.kill_runloop()
    elif key == ord('a'):
        config['depth_min'] = max(0, config['depth_min'] - 50)
    elif key == ord('z'):
        config['depth_min'] = min(config['depth_max'] - 50, config['depth_min'] + 50)
    elif key == ord('s'):
        config['depth_max'] = max(config['depth_min'] + 50, config['depth_max'] - 50)
    elif key == ord('x'):
        config['depth_max'] = min(4000, config['depth_max'] + 50)
    elif key == ord('c'):
        colormap_idx[0] = (colormap_idx[0] + 1) % len(colormaps)
        print(f'Colormap: {colormap_names[colormap_idx[0]]}')
    elif key == ord('g'):
        save_config()
    elif key == ord('e'):
        config['mode'] = 'exhibition'
        print('Modo exhibición activado')
    elif key == ord('b'):
        config['mode'] = 'calibration'
        print('Modo calibración activado')

def get_video(dev, data, timestamp):
    pass

load_config()
cv2.namedWindow('Sandbox', cv2.WINDOW_NORMAL)
cv2.moveWindow('Sandbox', 0, 0)
cv2.resizeWindow('Sandbox', DISPLAY_WIDTH, DISPLAY_HEIGHT)
cv2.setWindowProperty('Sandbox', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
freenect.runloop(depth=get_depth, video=get_video)
