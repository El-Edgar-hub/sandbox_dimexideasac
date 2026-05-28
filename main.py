import freenect
import numpy as np
import cv2
import json
import os
import threading
from flask import Flask, render_template_string, request, jsonify

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
colormaps_builtin = [cv2.COLORMAP_JET, cv2.COLORMAP_TURBO, cv2.COLORMAP_RAINBOW, cv2.COLORMAP_HOT]
colormap_names = ['JET', 'TURBO', 'RAINBOW', 'TOPO']

def make_topo_colormap():
    colors = [
        (0,   [0,   0,   80]),
        (60,  [0,   60,  180]),
        (100, [0,   160, 200]),
        (140, [0,   180, 80]),
        (180, [180, 210, 0]),
        (210, [255, 160, 0]),
        (240, [200, 0,   0]),
        (255, [255, 255, 255]),
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
        json.dump({k: v for k, v in config.items()}, f)

def draw_calibration_ui(frame):
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (440, 140), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    cv2.putText(frame, 'MODO CALIBRACION', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(frame, f'depth_min: {config["depth_min"]}', (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
    cv2.putText(frame, f'depth_max: {config["depth_max"]}', (20, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
    cv2.putText(frame, f'colormap: {colormap_names[colormap_idx[0]]}', (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
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

# Flask web interface
app = Flask(__name__)

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sandbox Control</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #1a1a2e; color: #eee; font-family: Arial, sans-serif; padding: 20px; }
        h1 { color: #00d4ff; text-align: center; margin-bottom: 30px; font-size: 24px; }
        .card { background: #16213e; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
        .card h2 { color: #00d4ff; margin-bottom: 15px; font-size: 16px; }
        .slider-row { margin-bottom: 15px; }
        label { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 14px; }
        label span { color: #00d4ff; font-weight: bold; }
        input[type=range] { width: 100%; height: 8px; accent-color: #00d4ff; }
        .btn-row { display: flex; gap: 10px; flex-wrap: wrap; }
        button { flex: 1; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold; }
        .btn-color { background: #0f3460; color: #00d4ff; }
        .btn-calib { background: #e94560; color: white; }
        .btn-exhib { background: #0f9b58; color: white; }
        .btn-save { background: #f5a623; color: #1a1a2e; }
        .status { background: #0f3460; border-radius: 8px; padding: 15px; font-size: 13px; line-height: 2; }
        .status span { color: #00d4ff; }
    </style>
</head>
<body>
    <h1>🏔️ Sandbox Control</h1>

    <div class="card">
        <h2>Rango de Profundidad</h2>
        <div class="slider-row">
            <label>depth_min <span id="val_min">400</span></label>
            <input type="range" id="depth_min" min="0" max="3900" value="400" oninput="update()">
        </div>
        <div class="slider-row">
            <label>depth_max <span id="val_max">2000</span></label>
            <input type="range" id="depth_max" min="100" max="4000" value="2000" oninput="update()">
        </div>
    </div>

    <div class="card">
        <h2>Colormap</h2>
        <div class="btn-row">
            <button class="btn-color" onclick="setColormap(0)">JET</button>
            <button class="btn-color" onclick="setColormap(1)">TURBO</button>
            <button class="btn-color" onclick="setColormap(2)">RAINBOW</button>
            <button class="btn-color" onclick="setColormap(3)">TOPO 🏔️</button>
        </div>
    </div>

    <div class="card">
        <h2>Modo</h2>
        <div class="btn-row">
            <button class="btn-calib" onclick="setMode('calibration')">Calibración</button>
            <button class="btn-exhib" onclick="setMode('exhibition')">Exhibición</button>
        </div>
    </div>

    <div class="card">
        <button class="btn-save" onclick="saveConfig()" style="width:100%">💾 Guardar Configuración</button>
    </div>

    <div class="card status" id="status">Cargando...</div>

    <script>
        function update() {
            const min = document.getElementById('depth_min').value;
            const max = document.getElementById('depth_max').value;
            document.getElementById('val_min').textContent = min;
            document.getElementById('val_max').textContent = max;
            fetch('/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({depth_min: parseInt(min), depth_max: parseInt(max)})
            }).then(r => r.json()).then(updateStatus);
        }

        function setColormap(idx) {
            fetch('/colormap', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({idx: idx})
            }).then(r => r.json()).then(updateStatus);
        }

        function setMode(mode) {
            fetch('/mode', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: mode})
            }).then(r => r.json()).then(updateStatus);
        }

        function saveConfig() {
            fetch('/save', {method: 'POST'}).then(r => r.json()).then(d => {
                alert('✅ ' + d.msg);
            });
        }

        function updateStatus(data) {
            document.getElementById('status').innerHTML =
                `<span>depth_min:</span> ${data.depth_min}<br>
                 <span>depth_max:</span> ${data.depth_max}<br>
                 <span>colormap:</span> ${data.colormap}<br>
                 <span>modo:</span> ${data.mode}`;
        }

        function loadStatus() {
            fetch('/status').then(r => r.json()).then(data => {
                document.getElementById('depth_min').value = data.depth_min;
                document.getElementById('depth_max').value = data.depth_max;
                document.getElementById('val_min').textContent = data.depth_min;
                document.getElementById('val_max').textContent = data.depth_max;
                updateStatus(data);
            });
        }

        loadStatus();
        setInterval(loadStatus, 3000);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/status')
def status():
    return jsonify({
        'depth_min': config['depth_min'],
        'depth_max': config['depth_max'],
        'colormap': colormap_names[colormap_idx[0]],
        'mode': config['mode']
    })

@app.route('/update', methods=['POST'])
def update():
    data = request.json
    config['depth_min'] = int(data['depth_min'])
    config['depth_max'] = int(data['depth_max'])
    return jsonify({'depth_min': config['depth_min'], 'depth_max': config['depth_max'],
                    'colormap': colormap_names[colormap_idx[0]], 'mode': config['mode']})

@app.route('/colormap', methods=['POST'])
def set_colormap():
    colormap_idx[0] = int(request.json['idx'])
    return jsonify({'depth_min': config['depth_min'], 'depth_max': config['depth_max'],
                    'colormap': colormap_names[colormap_idx[0]], 'mode': config['mode']})

@app.route('/mode', methods=['POST'])
def set_mode():
    config['mode'] = request.json['mode']
    return jsonify({'depth_min': config['depth_min'], 'depth_max': config['depth_max'],
                    'colormap': colormap_names[colormap_idx[0]], 'mode': config['mode']})

@app.route('/save', methods=['POST'])
def save():
    save_config()
    return jsonify({'msg': 'Configuracion guardada'})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

load_config()
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

cv2.namedWindow('Sandbox', cv2.WINDOW_NORMAL)
cv2.moveWindow('Sandbox', 0, 0)
cv2.resizeWindow('Sandbox', DISPLAY_WIDTH, DISPLAY_HEIGHT)
cv2.setWindowProperty('Sandbox', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
freenect.runloop(depth=get_depth, video=get_video)
