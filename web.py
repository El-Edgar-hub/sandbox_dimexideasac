from flask import Flask, render_template_string, request, jsonify

from config import config, auto_calib_status, floor_frame, live_stretch, save_config
from kinect import auto_calibrate, calibrate_floor, reset_floor

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
        .card p { font-size: 12px; color: #aaa; margin-bottom: 12px; }
        .slider-row { margin-bottom: 15px; }
        label { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 14px; }
        label span { color: #00d4ff; font-weight: bold; }
        input[type=range] { width: 100%; height: 8px; accent-color: #00d4ff; }
        .btn-row { display: flex; gap: 10px; flex-wrap: wrap; }
        button { flex: 1; padding: 12px; border: none; border-radius: 8px; cursor: pointer;
                 font-size: 14px; font-weight: bold; transition: opacity 0.2s; }
        button:active { opacity: 0.7; }
        .btn-calib  { background: #e94560; color: white; }
        .btn-exhib  { background: #0f9b58; color: white; }
        .btn-save   { background: #f5a623; color: #1a1a2e; }
        .btn-auto   { background: #7b2ff7; color: white; width: 100%; margin-bottom: 10px; padding: 15px; font-size: 16px; }
        .btn-floor  { background: #00897b; color: white; }
        .btn-floor-reset { background: #37474f; color: #ccc; }
        .btn-stretch-off { background: #1a3a5c; color: #00d4ff; border: 2px solid #00d4ff; width: 100%; padding: 14px; font-size: 15px; }
        .btn-stretch-on  { background: #00d4ff; color: #1a1a2e; width: 100%; padding: 14px; font-size: 15px; }
        .floor-active { border: 2px solid #00e5ff; }
        .status { background: #0f3460; border-radius: 8px; padding: 15px; font-size: 13px; line-height: 2; }
        .status span { color: #00d4ff; }
        .calib-status { text-align: center; color: #aaa; font-size: 12px; margin-top: 8px; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; margin-top: 8px; }
        .badge-on  { background: #00897b; color: white; }
        .badge-off { background: #37474f; color: #aaa; }
    </style>
</head>
<body>
    <h1>🏔️ Sandbox Control</h1>

    <!-- LIVE STRETCH -->
    <div class="card">
        <h2>⚡ Live Auto-Stretch</h2>
        <p>Ajusta el rango de colores automáticamente en tiempo real según la elevación actual. Actívalo después de fijar el suelo.</p>
        <button id="btn_stretch" class="btn-stretch-off" onclick="toggleStretch()">
            ACTIVAR LIVE STRETCH
        </button>
        <div class="calib-status" id="stretch_status">Desactivado — usa los sliders o Auto Calibrar</div>
    </div>

    <!-- SUELO -->
    <div class="card" id="floor_card">
        <h2>📐 Calibración de Suelo</h2>
        <p>Deja la superficie <b>plana y vacía</b>, luego presiona para fijar el nivel base.</p>
        <div class="btn-row" style="margin-bottom:10px;">
            <button class="btn-floor" onclick="calibrateFloor()">📐 Fijar Suelo Plano</button>
            <button class="btn-floor-reset" onclick="resetFloor()">🔄 Quitar</button>
        </div>
        <div class="calib-status" id="floor_status">Sin calibrar — modo clásico activo</div>
        <div style="text-align:center;">
            <span class="badge badge-off" id="floor_badge">SIN SUELO</span>
        </div>
    </div>

    <!-- AUTO CALIBRAR -->
    <div class="card">
        <h2>🎯 Auto Calibración (snapshot)</h2>
        <button class="btn-auto" onclick="autoCalibrate()">⚡ Auto Calibrar Rango</button>
        <div class="calib-status" id="calib_status">
            Con suelo fijado: detecta altura del montón. Sin suelo: ajusta rango clásico.
        </div>
    </div>

    <!-- RANGO MANUAL -->
    <div class="card">
        <h2>Rango <span id="range_label" style="font-size:12px; color:#aaa;">(profundidad)</span></h2>
        <div class="slider-row">
            <label>depth_min <span id="val_min">0</span></label>
            <input type="range" id="depth_min" min="0" max="2047" value="400" oninput="update()">
        </div>
        <div class="slider-row">
            <label>depth_max <span id="val_max">2000</span></label>
            <input type="range" id="depth_max" min="1" max="2047" value="2000" oninput="update()">
        </div>
    </div>

    <!-- MODO -->
    <div class="card">
        <h2>Modo</h2>
        <div class="btn-row">
            <button class="btn-calib" onclick="setMode('calibration')">🔧 Calibración</button>
            <button class="btn-exhib" onclick="setMode('exhibition')">🎬 Exhibición</button>
        </div>
    </div>

    <!-- GUARDAR -->
    <div class="card">
        <button class="btn-save" onclick="saveConfig()" style="width:100%">💾 Guardar Configuración</button>
    </div>

    <!-- STATUS -->
    <div class="card status" id="status">Cargando...</div>

    <script>
        function update() {
            const min = parseInt(document.getElementById('depth_min').value);
            const max = parseInt(document.getElementById('depth_max').value);
            document.getElementById('val_min').textContent = min;
            document.getElementById('val_max').textContent = max;
            fetch('/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({depth_min: min, depth_max: max})
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

        function autoCalibrate() {
            const btn = document.querySelector('.btn-auto');
            btn.textContent = '⏳ Leyendo Kinect...';
            btn.disabled = true;
            fetch('/auto_calibrate', {method: 'POST'}).then(r => r.json()).then(data => {
                document.getElementById('calib_status').textContent = '✅ ' + data.status;
                btn.textContent = '⚡ Auto Calibrar Rango';
                btn.disabled = false;
                updateStatus(data);
            });
        }

        function calibrateFloor() {
            const btn = document.querySelector('.btn-floor');
            btn.textContent = '⏳ Capturando...';
            btn.disabled = true;
            fetch('/calibrate_floor', {method: 'POST'}).then(r => r.json()).then(data => {
                btn.textContent = '📐 Fijar Suelo Plano';
                btn.disabled = false;
                document.getElementById('floor_status').textContent = '✅ ' + data.msg;
                updateStatus(data);
            });
        }

        function resetFloor() {
            fetch('/reset_floor', {method: 'POST'}).then(r => r.json()).then(data => {
                document.getElementById('floor_status').textContent = data.msg;
                updateStatus(data);
            });
        }

        function toggleStretch() {
            fetch('/toggle_stretch', {method: 'POST'}).then(r => r.json()).then(data => {
                updateStatus(data);
            });
        }

        function updateStatus(data) {
            // sliders
            document.getElementById('depth_min').value = data.depth_min;
            document.getElementById('depth_max').value = data.depth_max;
            document.getElementById('val_min').textContent = data.depth_min;
            document.getElementById('val_max').textContent = data.depth_max;

            // floor badge
            const badge = document.getElementById('floor_badge');
            const card  = document.getElementById('floor_card');
            if (data.floor_active) {
                badge.textContent = 'SUELO ACTIVO';
                badge.className = 'badge badge-on';
                card.classList.add('floor-active');
            } else {
                badge.textContent = 'SIN SUELO';
                badge.className = 'badge badge-off';
                card.classList.remove('floor-active');
            }

            // range label
            document.getElementById('range_label').textContent =
                data.floor_active ? '(elevación máxima sobre suelo)' : '(profundidad)';

            // live stretch button
            const btn = document.getElementById('btn_stretch');
            if (data.live_stretch) {
                btn.textContent = '⏹ DESACTIVAR LIVE STRETCH';
                btn.className = 'btn-stretch-on';
                const warn = !data.floor_active ? ' ⚠️ Primero fija el suelo para mejores resultados' : '';
                document.getElementById('stretch_status').textContent = '🟢 Activo — rango se ajusta solo en tiempo real' + warn;
            } else {
                btn.textContent = '▶ ACTIVAR LIVE STRETCH';
                btn.className = 'btn-stretch-off';
                document.getElementById('stretch_status').textContent = 'Desactivado — usa los sliders o Auto Calibrar';
            }

            // status panel
            document.getElementById('status').innerHTML =
                `<span>depth_min:</span> ${data.depth_min}<br>
                 <span>depth_max:</span> ${data.depth_max}<br>
                 <span>modo:</span> ${data.mode}<br>
                 <span>suelo:</span> ${data.floor_active ? 'calibrado ✅' : 'sin calibrar'}<br>
                 <span>live stretch:</span> ${data.live_stretch ? 'ON 🟢' : 'OFF'}`;
        }

        function loadStatus() {
            fetch('/status').then(r => r.json()).then(updateStatus);
        }

        loadStatus();
        setInterval(loadStatus, 2000);
    </script>
</body>
</html>
'''


def _payload():
    return {
        'depth_min':    config['depth_min'],
        'depth_max':    config['depth_max'],
        'mode':         config['mode'],
        'floor_active': floor_frame[0] is not None,
        'live_stretch': live_stretch[0],
    }


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/status')
def status():
    return jsonify(_payload())


@app.route('/update', methods=['POST'])
def update():
    data = request.json
    config['depth_min'] = int(data['depth_min'])
    config['depth_max'] = int(data['depth_max'])
    return jsonify(_payload())


@app.route('/mode', methods=['POST'])
def set_mode():
    config['mode'] = request.json['mode']
    return jsonify(_payload())


@app.route('/save', methods=['POST'])
def save():
    save_config()
    return jsonify({'msg': 'Configuracion guardada'})


@app.route('/auto_calibrate', methods=['POST'])
def auto_calibrate_route():
    auto_calibrate()
    p = _payload()
    p['status'] = auto_calib_status[0]
    return jsonify(p)


@app.route('/calibrate_floor', methods=['POST'])
def calibrate_floor_route():
    ok = calibrate_floor()
    p = _payload()
    p['msg'] = 'Suelo fijado — colormap muestra elevacion sobre la base' if ok else 'Error: sin datos del Kinect'
    return jsonify(p)


@app.route('/reset_floor', methods=['POST'])
def reset_floor_route():
    reset_floor()
    p = _payload()
    p['msg'] = 'Calibracion de suelo eliminada — modo clasico activo'
    return jsonify(p)


@app.route('/toggle_stretch', methods=['POST'])
def toggle_stretch():
    live_stretch[0] = not live_stretch[0]
    return jsonify(_payload())



@app.route('/depth_stats')
def depth_stats():
    from config import last_depth_frame, floor_frame, config
    import numpy as np
    if last_depth_frame[0] is None:
        return jsonify({'error': 'no data'})
    d = last_depth_frame[0].astype(float)
    valid = d[(d > 0) & (d < 2047)]
    h, w = d.shape
    cx, cy = w//2, h//2
    center = d[cy-20:cy+20, cx-20:cx+20]
    cv = center[(center>0)&(center<2047)]
    result = {
        'frame_min': int(valid.min()) if len(valid) else -1,
        'frame_max': int(valid.max()) if len(valid) else -1,
        'frame_mean': int(valid.mean()) if len(valid) else -1,
        'center_mean': int(cv.mean()) if len(cv) else -1,
        'center_min': int(cv.min()) if len(cv) else -1,
        'valid_pct': round(len(valid)/d.size*100, 1),
        'floor_center': int(floor_frame[0][cy-20:cy+20, cx-20:cx+20].mean()) if floor_frame[0] is not None else -1,
    }
    return jsonify(result)

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
