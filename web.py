import numpy as np
from flask import Flask, render_template_string, request, jsonify

from config import config, auto_calib_status, floor_frame, live_stretch, save_config, last_depth_frame, homography_step
from kinect import auto_calibrate, calibrate_floor, reset_floor

app = Flask(__name__)

HTML = '''<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sandbox</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#111827;color:#e5e7eb;font-family:system-ui,Arial,sans-serif;
         max-width:480px;margin:0 auto;padding:16px;min-height:100vh}

    /* HEADER */
    header{display:flex;justify-content:space-between;align-items:center;
           margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #1f2937}
    header h1{font-size:18px;font-weight:700;color:#f9fafb;letter-spacing:.5px}
    .pill{padding:4px 12px;border-radius:99px;font-size:11px;font-weight:700;
          letter-spacing:.5px;cursor:pointer;border:none;transition:background .3s}
    .pill-calib{background:#1d4ed8;color:#fff}
    .pill-exhib{background:#065f46;color:#6ee7b7}

    /* SENSOR CARD */
    .sensor-card{border-radius:12px;padding:20px;margin-bottom:14px;
                 transition:background .5s;text-align:center;position:relative}
    .sensor-val{font-size:52px;font-weight:800;line-height:1;letter-spacing:-2px}
    .sensor-label{font-size:12px;color:rgba(255,255,255,.6);margin-top:4px}
    .sensor-sub{display:flex;justify-content:center;gap:16px;margin-top:10px;font-size:12px;opacity:.8}
    .sensor-sub span{display:flex;align-items:center;gap:4px}
    .dot{width:7px;height:7px;border-radius:50%;display:inline-block}

    /* STEP CARDS */
    .step-card{background:#1f2937;border-radius:12px;padding:18px;
               margin-bottom:12px;border:2px solid transparent;transition:border-color .3s}
    .step-card.done{border-color:#065f46}
    .step-header{display:flex;align-items:center;gap:10px;margin-bottom:12px}
    .step-num{width:28px;height:28px;border-radius:50%;background:#374151;
              display:flex;align-items:center;justify-content:center;
              font-size:13px;font-weight:700;color:#9ca3af;flex-shrink:0}
    .step-card.done .step-num{background:#065f46;color:#6ee7b7}
    .step-title{font-size:15px;font-weight:600;color:#f3f4f6}
    .step-desc{font-size:13px;color:#9ca3af;margin-bottom:14px;line-height:1.5}

    .btn-capture{width:100%;padding:16px;border:none;border-radius:10px;
                 font-size:15px;font-weight:700;cursor:pointer;
                 transition:opacity .2s;margin-bottom:12px;letter-spacing:.3px}
    .btn-capture:active{opacity:.7}
    .btn-base{background:#1d4ed8;color:#fff}
    .btn-height{background:#7c3aed;color:#fff}
    .btn-geo{background:#0891b2;color:#fff}
    .btn-geo-reset{background:#374151;color:#e5e7eb}
    .btn-capture:disabled{opacity:.45;cursor:not-allowed}

    /* FINE TUNE */
    .fine-tune{display:flex;align-items:center;gap:8px;
               background:#111827;border-radius:8px;padding:10px 14px}
    .ft-label{font-size:12px;color:#6b7280;flex:1}
    .ft-val{font-size:16px;font-weight:700;color:#e5e7eb;min-width:48px;text-align:center}
    .ft-btn{width:32px;height:32px;border-radius:8px;border:1px solid #374151;
            background:#1f2937;color:#e5e7eb;font-size:18px;cursor:pointer;
            display:flex;align-items:center;justify-content:center;line-height:1}
    .ft-btn:active{background:#374151}

    /* FEEDBACK */
    .feedback{min-height:20px;margin-top:10px;font-size:12px;border-radius:6px;
              padding:0;transition:all .3s}
    .feedback.ok{color:#6ee7b7;padding:6px 10px;background:#064e3b22}
    .feedback.warn{color:#fbbf24;padding:6px 10px;background:#78350f22}
    .feedback.err{color:#f87171;padding:6px 10px;background:#7f1d1d22}

    /* FOOTER */
    .footer{display:flex;gap:10px;margin-top:4px;padding-top:4px}
    .btn-save{flex:1;padding:15px;border:none;border-radius:10px;
              background:#d97706;color:#1c1917;font-size:15px;font-weight:700;
              cursor:pointer;transition:opacity .2s}
    .btn-exhib{flex:1;padding:15px;border:none;border-radius:10px;
               background:#065f46;color:#6ee7b7;font-size:15px;font-weight:700;
               cursor:pointer;transition:opacity .2s}
    .btn-save:active,.btn-exhib:active{opacity:.7}
  </style>
</head>
<body>

<header>
  <h1>🏔 AR Sandbox</h1>
  <button class="pill pill-calib" id="mode-pill" onclick="toggleMode()">CALIBRACIÓN</button>
</header>

<!-- SENSOR EN VIVO -->
<div class="sensor-card" id="sensor-card" style="background:#1e3a5f">
  <div class="sensor-val" id="sensor-val">---</div>
  <div class="sensor-label">profundidad central (raw)</div>
  <div class="sensor-sub">
    <span><span class="dot" id="dot-conn" style="background:#6b7280"></span> <span id="conn-txt">conectando</span></span>
    <span id="valid-pct">--% válido</span>
  </div>
</div>

<!-- PASO 1: BASE -->
<div class="step-card" id="step1">
  <div class="step-header">
    <div class="step-num" id="num1">1</div>
    <div class="step-title">Calibrar Base</div>
  </div>
  <p class="step-desc">Deja la arena <b>completamente plana y vacía</b>, luego captura el nivel base.</p>
  <button class="btn-capture btn-base" id="btn-base" onclick="captureBase()">📷 Capturar Base Plana</button>
  <div class="fine-tune">
    <span class="ft-label">depth_max</span>
    <button class="ft-btn" onclick="adjust('max',-5)">−</button>
    <span class="ft-val" id="val-max">---</span>
    <button class="ft-btn" onclick="adjust('max',+5)">+</button>
  </div>
  <div class="feedback" id="fb-base"></div>
</div>

<!-- PASO 2: ALTURA -->
<div class="step-card" id="step2">
  <div class="step-header">
    <div class="step-num" id="num2">2</div>
    <div class="step-title">Calibrar Altura Máxima</div>
  </div>
  <p class="step-desc">Pon tu mano a <b>15–20 cm</b> sobre la arena y captura la altura máxima de color.</p>
  <button class="btn-capture btn-height" id="btn-height" onclick="captureHeight()">↑ Capturar Altura Máxima</button>
  <div class="fine-tune">
    <span class="ft-label">depth_min</span>
    <button class="ft-btn" onclick="adjust('min',-5)">−</button>
    <span class="ft-val" id="val-min">---</span>
    <button class="ft-btn" onclick="adjust('min',+5)">+</button>
  </div>
  <div class="feedback" id="fb-height"></div>
</div>

<!-- PASO 3: GEOMETRIA (oculto por ahora -- codigo intacto por si se retoma) -->
<div class="step-card" id="step3" style="display:none">
  <div class="step-header">
    <div class="step-num" id="num3">3</div>
    <div class="step-title">Calibrar Geometría</div>
  </div>
  <p class="step-desc" id="geo-desc">Alinea la imagen proyectada con la posición real de la arena. Usa <b>un solo dedo</b> (no la palma abierta) a unos <b>8-10 cm</b> sobre la arena — bajo, para minimizar el paralaje — y mantenlo quieto sobre cada marca roja que verás proyectada.</p>
  <button class="btn-capture btn-geo" id="btn-geo-start" onclick="startHomography()">🎯 Iniciar Calibración de Esquinas</button>
  <button class="btn-capture btn-geo" id="btn-geo-capture" onclick="captureCorner()" style="display:none">✋ Capturar Esquina</button>
  <button class="btn-capture btn-geo-reset" id="btn-geo-reset" onclick="resetHomography()" style="display:none">↺ Reiniciar Geometría</button>
  <div class="feedback" id="fb-geo"></div>
</div>

<!-- FOOTER -->
<div class="footer">
  <button class="btn-save" onclick="save()">💾 Guardar</button>
  <button class="btn-exhib" onclick="setExhibition()">🎬 Exhibición</button>
</div>

<script>
  var state = {depthMin: 640, depthMax: 715, mode: 'calibration', centerMean: null};

  // Color según profundidad (igual que el colormap del proyector)
  function depthColor(center, dmin, dmax) {
    if (center === null || dmax <= dmin) return '#1e3a5f';
    var rng = dmax - dmin;
    var norm = 1.0 - Math.max(0, Math.min(1, (center - dmin) / rng));
    if (norm < 0.12) return '#00004a';
    if (norm < 0.30) return '#003cb4';
    if (norm < 0.55) return '#007820';
    if (norm < 0.78) return '#b86000';
    return '#8b0000';
  }

  function updateSensor(data) {
    state.centerMean = data.center_mean;
    var el = document.getElementById('sensor-val');
    el.textContent = data.center_mean || '---';
    document.getElementById('valid-pct').textContent = (data.valid_pct || 0) + '% válido';
    var ok = data.valid_pct > 30;
    document.getElementById('dot-conn').style.background = ok ? '#22c55e' : '#ef4444';
    document.getElementById('conn-txt').textContent = ok ? 'Kinect activo' : 'señal baja';
    var bg = depthColor(data.center_mean, state.depthMin, state.depthMax);
    document.getElementById('sensor-card').style.background = bg;
  }

  function updateConfig(data) {
    state.depthMin = data.depth_min;
    state.depthMax = data.depth_max;
    state.mode = data.mode;
    document.getElementById('val-max').textContent = data.depth_max;
    document.getElementById('val-min').textContent = data.depth_min;
    var pill = document.getElementById('mode-pill');
    if (data.mode === 'exhibition') {
      pill.textContent = 'EXHIBICIÓN';
      pill.className = 'pill pill-exhib';
    } else {
      pill.textContent = 'CALIBRACIÓN';
      pill.className = 'pill pill-calib';
    }
    if (data.homography_active !== undefined) refreshGeoUI(data);
  }

  function startHomography() {
    fetch('/start_homography', {method:'POST'}).then(function(r){ return r.json(); }).then(function(data){
      updateConfig(data);
      if (data.error) { setFeedback('fb-geo', '✗ ' + data.error, 'err'); return; }
      setFeedback('fb-geo', 'Esquina 1/4 — coloca tu mano sobre la marca roja proyectada', 'ok');
    });
  }

  function captureCorner() {
    var btn = document.getElementById('btn-geo-capture');
    btn.disabled = true; btn.textContent = '⏳ Capturando...';
    fetch('/capture_homography_point', {method:'POST'}).then(function(r){ return r.json(); }).then(function(data){
      btn.disabled = false; btn.textContent = '✋ Capturar Esquina';
      if (data.error) { setFeedback('fb-geo', '✗ ' + data.error, 'err'); return; }
      updateConfig(data);
      if (data.done) {
        setFeedback('fb-geo', '✓ Geometría calibrada', 'ok');
      } else {
        setFeedback('fb-geo', 'Esquina ' + (data.next_step + 1) + '/4 — mueve la mano a la nueva marca y captura', 'ok');
      }
    }).catch(function(){ btn.disabled=false; btn.textContent='✋ Capturar Esquina'; });
  }

  function resetHomography() {
    fetch('/reset_homography', {method:'POST'}).then(function(r){ return r.json(); }).then(function(data){
      updateConfig(data);
      setFeedback('fb-geo', 'Geometría reiniciada', 'warn');
    });
  }

  function refreshGeoUI(data) {
    var start   = document.getElementById('btn-geo-start');
    var capture = document.getElementById('btn-geo-capture');
    var reset   = document.getElementById('btn-geo-reset');
    var step3   = document.getElementById('step3');
    var num3    = document.getElementById('num3');
    var desc    = document.getElementById('geo-desc');

    if (data.homography_active) {
      start.style.display = 'none';
      capture.style.display = 'none';
      reset.style.display = 'block';
      step3.classList.add('done');
      num3.textContent = '✓';
      desc.textContent = 'Geometría calibrada — la proyección está alineada con la arena.';
    } else if (data.homography_step >= 0) {
      start.style.display = 'none';
      capture.style.display = 'block';
      reset.style.display = 'block';
      step3.classList.remove('done');
      num3.textContent = '3';
      desc.textContent = 'Coloca tu mano sobre la marca roja proyectada (esquina ' + (data.homography_step + 1) + '/4) y presiona Capturar Esquina.';
    } else {
      start.style.display = 'block';
      capture.style.display = 'none';
      reset.style.display = 'none';
      step3.classList.remove('done');
      num3.textContent = '3';
      desc.textContent = 'Alinea la imagen proyectada con la posición real de la arena marcando las 4 esquinas con la mano.';
    }
  }

  function setFeedback(id, msg, type) {
    var el = document.getElementById(id);
    el.textContent = msg;
    el.className = 'feedback ' + type;
  }

  function captureBase() {
    var btn = document.getElementById('btn-base');
    btn.disabled = true; btn.textContent = '⏳ Capturando...';
    fetch('/set_base', {method:'POST'}).then(function(r){ return r.json(); }).then(function(data) {
      btn.disabled = false; btn.textContent = '📷 Capturar Base Plana';
      if (data.error) { setFeedback('fb-base', '✗ ' + data.error, 'err'); return; }
      updateConfig(data);
      setFeedback('fb-base', '✓ Base fijada en ' + data.depth_max, 'ok');
      document.getElementById('step1').classList.add('done');
      document.getElementById('num1').textContent = '✓';
    }).catch(function(){ btn.disabled=false; btn.textContent='📷 Capturar Base Plana'; });
  }

  function captureHeight() {
    var btn = document.getElementById('btn-height');
    btn.disabled = true; btn.textContent = '⏳ Capturando...';
    fetch('/set_max_height', {method:'POST'}).then(function(r){ return r.json(); }).then(function(data) {
      btn.disabled = false; btn.textContent = '↑ Capturar Altura Máxima';
      if (data.error) { setFeedback('fb-height', '✗ ' + data.error, 'err'); return; }
      updateConfig(data);
      if (data.depth_min >= data.depth_max) {
        setFeedback('fb-height', '⚠ depth_min ≥ depth_max — sube más la mano y vuelve a capturar', 'warn');
      } else {
        var rng = data.depth_max - data.depth_min;
        setFeedback('fb-height', '✓ Altura fijada en ' + data.depth_min + '  (rango: ' + rng + ' unidades)', 'ok');
        document.getElementById('step2').classList.add('done');
        document.getElementById('num2').textContent = '✓';
      }
    }).catch(function(){ btn.disabled=false; btn.textContent='↑ Capturar Altura Máxima'; });
  }

  function adjust(which, delta) {
    var dmin = state.depthMin;
    var dmax = state.depthMax;
    if (which === 'min') dmin = Math.max(0, Math.min(2046, dmin + delta));
    else                 dmax = Math.max(1, Math.min(2047, dmax + delta));
    fetch('/update', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({depth_min: dmin, depth_max: dmax})
    }).then(function(r){ return r.json(); }).then(updateConfig);
  }

  function save() {
    fetch('/save', {method:'POST'}).then(function(r){ return r.json(); }).then(function(d) {
      var btn = document.querySelector('.btn-save');
      btn.textContent = '✓ Guardado';
      setTimeout(function(){ btn.textContent = '💾 Guardar'; }, 2000);
    });
  }

  function setExhibition() {
    fetch('/mode', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({mode:'exhibition'})
    }).then(function(r){ return r.json(); }).then(updateConfig);
  }

  function toggleMode() {
    var next = state.mode === 'exhibition' ? 'calibration' : 'exhibition';
    fetch('/mode', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({mode: next})
    }).then(function(r){ return r.json(); }).then(updateConfig);
  }

  // Polling
  function pollSensor() {
    fetch('/depth_stats').then(function(r){ return r.json(); }).then(updateSensor).catch(function(){});
  }
  function pollStatus() {
    fetch('/status').then(function(r){ return r.json(); }).then(updateConfig).catch(function(){});
  }

  pollSensor(); pollStatus();
  setInterval(pollSensor, 1000);
  setInterval(pollStatus, 3000);
</script>
</body>
</html>
'''


def _payload():
    return {
        'depth_min':        config['depth_min'],
        'depth_max':        config['depth_max'],
        'mode':             config['mode'],
        'floor_active':     floor_frame[0] is not None,
        'live_stretch':     live_stretch[0],
        'homography_active': config.get('homography') is not None,
        'homography_step':   homography_step[0],
    }


def _center_mean():
    if last_depth_frame[0] is None:
        return None
    d = last_depth_frame[0].astype(np.float32)
    h, w = d.shape
    cy, cx = h // 2, w // 2
    roi = d[cy-30:cy+30, cx-40:cx+40]
    valid = roi[(roi > 0) & (roi < 2047)]
    return valid, int(np.mean(valid)) if len(valid) >= 100 else None


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/status')
def status():
    return jsonify(_payload())


@app.route('/depth_stats')
def depth_stats():
    if last_depth_frame[0] is None:
        return jsonify({'error': 'no data'})
    d = last_depth_frame[0].astype(np.float32)
    valid = d[(d > 0) & (d < 2047)]
    h, w = d.shape
    cx, cy = w // 2, h // 2
    center = d[cy-20:cy+20, cx-20:cx+20]
    cv = center[(center > 0) & (center < 2047)]
    return jsonify({
        'frame_min':   int(valid.min())  if len(valid) else -1,
        'frame_max':   int(valid.max())  if len(valid) else -1,
        'frame_mean':  int(valid.mean()) if len(valid) else -1,
        'center_mean': int(cv.mean())    if len(cv)    else -1,
        'center_min':  int(cv.min())     if len(cv)    else -1,
        'valid_pct':   round(len(valid) / d.size * 100, 1),
        'floor_center': int(floor_frame[0][cy-20:cy+20, cx-20:cx+20].mean())
                        if floor_frame[0] is not None else -1,
    })


@app.route('/set_base', methods=['POST'])
def set_base():
    if last_depth_frame[0] is None:
        return jsonify({'error': 'sin datos del Kinect'}), 503
    d = last_depth_frame[0].astype(np.float32)
    h, w = d.shape
    cy, cx = h // 2, w // 2
    roi = d[cy-30:cy+30, cx-40:cx+40]
    valid = roi[(roi > 0) & (roi < 2047)]
    if len(valid) < 100:
        return jsonify({'error': 'cobertura insuficiente'}), 503
    config['depth_max'] = int(np.mean(valid))
    return jsonify(_payload())


@app.route('/set_max_height', methods=['POST'])
def set_max_height():
    if last_depth_frame[0] is None:
        return jsonify({'error': 'sin datos del Kinect'}), 503
    d = last_depth_frame[0].astype(np.float32)
    h, w = d.shape
    cy, cx = h // 2, w // 2
    roi = d[cy-30:cy+30, cx-40:cx+40]
    valid = roi[(roi > 0) & (roi < 2047)]
    if len(valid) < 100:
        return jsonify({'error': 'cobertura insuficiente'}), 503
    config['depth_min'] = int(np.mean(valid))
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


# Endpoints legacy (no expuestos en UI, conservados por si acaso)
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
    p['msg'] = 'Suelo fijado' if ok else 'Error: sin datos del Kinect'
    return jsonify(p)


@app.route('/reset_floor', methods=['POST'])
def reset_floor_route():
    reset_floor()
    p = _payload()
    p['msg'] = 'Calibracion de suelo eliminada'
    return jsonify(p)


@app.route('/toggle_stretch', methods=['POST'])
def toggle_stretch():
    live_stretch[0] = not live_stretch[0]
    return jsonify(_payload())


def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
