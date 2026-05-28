from flask import Flask, render_template_string, request, jsonify

from config import config, colormap_idx, colormap_names, auto_calib_status, floor_frame, save_config
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
        .slider-row { margin-bottom: 15px; }
        label { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 14px; }
        label span { color: #00d4ff; font-weight: bold; }
        input[type=range] { width: 100%; height: 8px; accent-color: #00d4ff; }
        .btn-row { display: flex; gap: 10px; flex-wrap: wrap; }
        button { flex: 1; padding: 12px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold; transition: opacity 0.2s; }
        button:active { opacity: 0.7; }
        .btn-color { background: #0f3460; color: #00d4ff; }
        .btn-color.active { background: #00d4ff; color: #1a1a2e; }
        .btn-calib { background: #e94560; color: white; }
        .btn-exhib { background: #0f9b58; color: white; }
        .btn-save { background: #f5a623; color: #1a1a2e; }
        .btn-auto { background: #7b2ff7; color: white; width: 100%; margin-bottom: 10px; padding: 15px; font-size: 16px; }
        .btn-floor { background: #00897b; color: white; }
        .btn-floor-reset { background: #37474f; color: #ccc; }
        .floor-active { border: 2px solid #00e5ff; }
        .status { background: #0f3460; border-radius: 8px; padding: 15px; font-size: 13px; line-height: 2; }
        .status span { color: #00d4ff; }
        .calib-status { text-align: center; color: #aaa; font-size: 12px; margin-top: 8px; }
        .floor-badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; margin-top: 8px; }
        .floor-badge.on { background: #00897b; color: white; }
        .floor-badge.off { background: #37474f; color: #aaa; }
    </style>
</head>
<body>
    <h1>🏔️ Sandbox Control</h1>

    <div class="card" id="floor_card">
        <h2>📐 Calibración de Suelo</h2>
        <p style="font-size:12px; color:#aaa; margin-bottom:12px;">
            Deja la superficie <b>plana y vacía</b>, luego presiona para fijar el nivel base.
            El colormap mostrará solo la elevación sobre ese suelo.
        </p>
        <div class="btn-row" style="margin-bottom:10px;">
            <button class="btn-floor" onclick="calibrateFloor()">📐 Fijar Suelo Plano</button>
            <button class="btn-floor-reset" onclick="resetFloor()">🔄 Quitar Calibración</button>
        </div>
        <div class="calib-status" id="floor_status">Sin calibrar — modo clásico activo</div>
        <div style="text-align:center;">
            <span class="floor-badge off" id="floor_badge">SIN SUELO</span>
        </div>
    </div>

    <div class="card">
        <h2>🎯 Auto Calibración</h2>
        <button class="btn-auto" onclick="autoCalibrate()">⚡ Auto Calibrar Rango</button>
        <div class="calib-status" id="calib_status">
            Con suelo calibrado: detecta altura del montón. Sin suelo: ajusta rango clásico.
        </div>
    </div>

    <div class="card">
        <h2>Rango <span id="range_label" style="font-size:12px; color:#aaa;">(profundidad)</span></h2>
        <div class="slider-row">
            <label>depth_min <span id="val_min">400</span></label>
            <input type="range" id="depth_min" min="0" max="2047" value="400" oninput="update()">
        </div>
        <div class="slider-row">
            <label>depth_max <span id="val_max">2000</span></label>
            <input type="range" id="depth_max" min="1" max="2047" value="2000" oninput="update()">
        </div>
    </div>

    <div class="card">
        <h2>Colormap</h2>
        <div class="btn-row">
            <button class="btn-color" id="cm0" onclick="setColormap(0)">JET</button>
            <button class="btn-color" id="cm1" onclick="setColormap(1)">TURBO</button>
            <button class="btn-color" id="cm2" onclick="setColormap(2)">RAINBOW</button>
            <button class="btn-color" id="cm3" onclick="setColormap(3)">TOPO 🏔️</button>
        </div>
    </div>

    <div class="card">
        <h2>Modo</h2>
        <div class="btn-row">
            <button class="btn-calib" onclick="setMode('calibration')">🔧 Calibración</button>
            <button class="btn-exhib" onclick="setMode('exhibition')">🎬 Exhibición</button>
        </div>
    </div>

    <div class="card">
        <button class="btn-save" onclick="saveConfig()" style="width:100%">💾 Guardar Configuración</button>
    </div>

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

        function setColormap(idx) {
            document.querySelectorAll('[id^=cm]').forEach(b => b.classList.remove('active'));
            document.getElementById('cm' + idx).classList.add('active');
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

        function autoCalibrate() {
            const btn = document.querySelector('.btn-auto');
            btn.textContent = '⏳ Leyendo Kinect...';
            btn.disabled = true;
            fetch('/auto_calibrate', {method: 'POST'}).then(r => r.json()).then(data => {
                document.getElementById('calib_status').textContent = '✅ ' + data.status;
                document.getElementById('depth_min').value = data.depth_min;
                document.getElementById('depth_max').value = data.depth_max;
                document.getElementById('val_min').textContent = data.depth_min;
                document.getElementById('val_max').textContent = data.depth_max;
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
                updateFloorBadge(data.floor_active);
                updateRangeLabel(data.floor_active);
            });
        }

        function resetFloor() {
            fetch('/reset_floor', {method: 'POST'}).then(r => r.json()).then(data => {
                document.getElementById('floor_status').textContent = data.msg;
                updateFloorBadge(data.floor_active);
                updateRangeLabel(data.floor_active);
            });
        }

        function updateFloorBadge(active) {
            const badge = document.getElementById('floor_badge');
            const card = document.getElementById('floor_card');
            if (active) {
                badge.textContent = 'SUELO ACTIVO';
                badge.className = 'floor-badge on';
                card.classList.add('floor-active');
            } else {
                badge.textContent = 'SIN SUELO';
                badge.className = 'floor-badge off';
                card.classList.remove('floor-active');
            }
        }

        function updateRangeLabel(floorActive) {
            document.getElementById('range_label').textContent =
                floorActive ? '(elevación máxima sobre suelo)' : '(profundidad)';
        }

        function updateStatus(data) {
            document.getElementById('status').innerHTML =
                `<span>depth_min:</span> ${data.depth_min}<br>
                 <span>depth_max:</span> ${data.depth_max}<br>
                 <span>colormap:</span> ${data.colormap}<br>
                 <span>modo:</span> ${data.mode}<br>
                 <span>suelo:</span> ${data.floor_active ? 'calibrado ✅' : 'sin calibrar'}`;
            updateFloorBadge(data.floor_active);
            updateRangeLabel(data.floor_active);
        }

        function loadStatus() {
            fetch('/status').then(r => r.json()).then(data => {
                document.getElementById('depth_min').value = data.depth_min;
                document.getElementById('depth_max').value = data.depth_max;
                document.getElementById('val_min').textContent = data.depth_min;
                document.getElementById('val_max').textContent = data.depth_max;
                const idx = ['JET','TURBO','RAINBOW','TOPO'].indexOf(data.colormap);
                if (idx >= 0) {
                    document.querySelectorAll('[id^=cm]').forEach(b => b.classList.remove('active'));
                    document.getElementById('cm' + idx).classList.add('active');
                }
                updateStatus(data);
            });
        }

        loadStatus();
        setInterval(loadStatus, 3000);
    </script>
</body>
</html>
'''


def _status_payload():
    return {
        'depth_min': config['depth_min'],
        'depth_max': config['depth_max'],
        'colormap': colormap_names[colormap_idx[0]],
        'mode': config['mode'],
        'floor_active': floor_frame[0] is not None
    }


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/status')
def status():
    return jsonify(_status_payload())


@app.route('/update', methods=['POST'])
def update():
    data = request.json
    config['depth_min'] = int(data['depth_min'])
    config['depth_max'] = int(data['depth_max'])
    return jsonify(_status_payload())


@app.route('/colormap', methods=['POST'])
def set_colormap():
    colormap_idx[0] = int(request.json['idx'])
    return jsonify(_status_payload())


@app.route('/mode', methods=['POST'])
def set_mode():
    config['mode'] = request.json['mode']
    return jsonify(_status_payload())


@app.route('/save', methods=['POST'])
def save():
    save_config()
    return jsonify({'msg': 'Configuracion guardada'})


@app.route('/auto_calibrate', methods=['POST'])
def auto_calibrate_route():
    auto_calibrate()
    payload = _status_payload()
    payload['status'] = auto_calib_status[0]
    return jsonify(payload)


@app.route('/calibrate_floor', methods=['POST'])
def calibrate_floor_route():
    ok = calibrate_floor()
    msg = 'Suelo fijado — ahora el colormap muestra solo elevacion' if ok else 'Error: sin datos del Kinect'
    payload = _status_payload()
    payload['msg'] = msg
    return jsonify(payload)


@app.route('/reset_floor', methods=['POST'])
def reset_floor_route():
    reset_floor()
    payload = _status_payload()
    payload['msg'] = 'Calibracion de suelo eliminada — modo clasico activo'
    return jsonify(payload)


def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
