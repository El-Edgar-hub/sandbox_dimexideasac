import numpy as np
from flask import Flask, render_template_string, request, jsonify

from config import config, auto_calib_status, floor_frame, live_stretch, save_config, last_depth_frame, homography_step
from kinect import auto_calibrate, calibrate_floor, reset_floor, detect_sand_crop

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
    .ft-input{font-size:16px;font-weight:700;color:#e5e7eb;min-width:64px;text-align:center;
               background:#0d1117;border:1px solid #374151;border-radius:6px;padding:5px 2px}
    .ft-input:focus{outline:none;border-color:#7c3aed}
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
    .btn-exhib{flex:1;padding:15px;border:2px solid transparent;border-radius:10px;
               background:#065f46;color:#6ee7b7;font-size:15px;font-weight:700;
               cursor:pointer;transition:opacity .2s,border-color .2s}
    .btn-exhib.active{border-color:#6ee7b7}
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
    <span id="floor-status">suelo: sin calibrar</span>
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
  <!-- fine-tune de depth_max oculto aqui: este valor es solo informativo en
       modo suelo, el que de verdad importa para el render es el del Paso 2 -->
  <div class="fine-tune" style="display:none">
    <span class="ft-label">depth_max</span>
    <button class="ft-btn" onclick="adjust('max',-5)">−</button>
    <span class="ft-val" id="val-max">---</span>
    <button class="ft-btn" onclick="adjust('max',+5)">+</button>
  </div>
  <div class="feedback" id="fb-base"></div>
</div>

<!-- PASO 2: RANGO DE COLOR -->
<div class="step-card" id="step2">
  <div class="step-header">
    <div class="step-num" id="num2">2</div>
    <div class="step-title">Calibrar Rango de Color</div>
  </div>
  <p class="step-desc">Construye montículos/valles en la arena, luego presiona Auto Calibrar Rango — mide el relieve real (arriba y abajo del suelo fijado) y ajusta el color automáticamente. La elevación cero (el suelo) se ve <b>verde</b>; montículos van hacia amarillo/naranja/rojo/blanco; valles van hacia tonos de <b>azul</b>. También puedes ajustar el techo y la profundidad de valle manualmente, a tu gusto.</p>
  <button class="btn-capture btn-height" id="btn-height" onclick="autoCalibrateRange()">📊 Auto Calibrar Rango</button>
  <div class="fine-tune">
    <span class="ft-label">techo monticulo (depth_max)</span>
    <button class="ft-btn" onclick="adjust('max',-5)">−</button>
    <input class="ft-input" id="val-max2" type="number" onchange="setDepthMax(this.value)">
    <button class="ft-btn" onclick="adjust('max',+5)">+</button>
  </div>
  <div class="fine-tune">
    <span class="ft-label">profundidad valle (depth_min)</span>
    <button class="ft-btn" onclick="adjust('min',-5)">−</button>
    <input class="ft-input" id="val-min" type="number" onchange="setDepthMin(this.value)">
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
  // Aproxima el colormap bipolar real (colormap.py): 0.5 = elevacion cero
  // (verde), sube hacia amarillo/naranja/rojo/blanco, baja hacia
  // cian/azul/azul profundo. Mismos 8 tonos que el LUT real de OpenCV.
  function depthColor(elev, depthMinVal, depthMaxVal) {
    if (elev === null) return '#1e3a5f';
    var norm = elev >= 0
      ? 0.5 + 0.5 * Math.max(0, Math.min(1, elev / Math.max(1, depthMaxVal)))
      : 0.5 - 0.5 * Math.max(0, Math.min(1, -elev / Math.max(1, depthMinVal)));
    if (norm < 0.11) return '#000050';
    if (norm < 0.29) return '#003cb4';
    if (norm < 0.44) return '#00a0c8';
    if (norm < 0.60) return '#00b450';
    if (norm < 0.76) return '#b4d200';
    if (norm < 0.88) return '#ffa000';
    if (norm < 0.97) return '#c80000';
    return '#ffffff';
  }

  function updateSensor(data) {
    state.centerMean = data.center_mean;
    var el = document.getElementById('sensor-val');
    el.textContent = data.center_mean || '---';
    document.getElementById('valid-pct').textContent = (data.valid_pct || 0) + '% válido';
    var ok = data.valid_pct > 30;
    document.getElementById('dot-conn').style.background = ok ? '#22c55e' : '#ef4444';
    document.getElementById('conn-txt').textContent = ok ? 'Kinect activo' : 'señal baja';
    var bg;
    if (data.floor_center !== undefined && data.floor_center >= 0) {
      // Modo suelo: el render usa elevacion con signo (floor - profundidad),
      // positiva = monticulo, negativa = valle -- mismo calculo que get_depth().
      var elev = data.floor_center - data.center_mean;
      bg = depthColor(elev, state.depthMin, state.depthMax);
    } else {
      // Modo clasico (sin suelo fijado) -- previsualizacion simple, no bipolar.
      var rng = Math.max(1, state.depthMax - state.depthMin);
      var cnorm = 1.0 - Math.max(0, Math.min(1, (data.center_mean - state.depthMin) / rng));
      bg = cnorm < 0.3 ? '#000050' : (cnorm < 0.6 ? '#00b450' : (cnorm < 0.85 ? '#ffa000' : '#ffffff'));
    }
    document.getElementById('sensor-card').style.background = bg;
  }

  function updateConfig(data) {
    state.depthMin = data.depth_min;
    state.depthMax = data.depth_max;
    state.mode = data.mode;
    document.getElementById('val-max').textContent = data.depth_max;
    document.getElementById('val-max2').value = data.depth_max;
    document.getElementById('val-min').value = data.depth_min;
    var pill = document.getElementById('mode-pill');
    if (data.mode === 'exhibition') {
      pill.textContent = 'EXHIBICIÓN';
      pill.className = 'pill pill-exhib';
    } else {
      pill.textContent = 'CALIBRACIÓN';
      pill.className = 'pill pill-calib';
    }
    var exhibBtn = document.querySelector('.btn-exhib');
    if (exhibBtn) exhibBtn.classList.toggle('active', data.mode === 'exhibition');
    if (data.floor_active !== undefined) {
      var fs = document.getElementById('floor-status');
      fs.textContent = data.floor_active ? 'suelo: calibrado' : 'suelo: sin calibrar';
      fs.style.color = data.floor_active ? '#6ee7b7' : '#fbbf24';
      document.getElementById('step1').classList.toggle('done', data.floor_active);
      document.getElementById('num1').textContent = data.floor_active ? '✓' : '1';
    }
    if (data.range_calibrated !== undefined) {
      document.getElementById('step2').classList.toggle('done', data.range_calibrated);
      document.getElementById('num2').textContent = data.range_calibrated ? '✓' : '2';
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
      var msg = '✓ Base fijada en ' + data.depth_max;
      if (data.crop_msg) msg += ' — ' + data.crop_msg;
      if (data.crop_warn) msg += ' ⚠ ' + data.crop_warn;
      setFeedback('fb-base', msg, data.crop_warn ? 'warn' : 'ok');
    }).catch(function(){ btn.disabled=false; btn.textContent='📷 Capturar Base Plana'; });
  }

  // Ya no se usa desde ningun boton -- se deja intacta por si se retoma el
  // gesto manual de mano en el futuro (mismo patron de "ocultar, no borrar").
  function captureHeight() {
    var btn = document.getElementById('btn-height');
    btn.disabled = true; btn.textContent = '⏳ Capturando...';
    fetch('/set_max_height', {method:'POST'}).then(function(r){ return r.json(); }).then(function(data) {
      btn.disabled = false; btn.textContent = '↑ Capturar Altura Máxima';
      if (data.error) { setFeedback('fb-height', '✗ ' + data.error, 'err'); return; }
      updateConfig(data);
      setFeedback('fb-height', '✓ Rango de color fijado: 0–' + data.depth_max + ' unidades', 'ok');
      document.getElementById('step2').classList.add('done');
      document.getElementById('num2').textContent = '✓';
    }).catch(function(){ btn.disabled=false; btn.textContent='↑ Capturar Altura Máxima'; });
  }

  function autoCalibrateRange() {
    var btn = document.getElementById('btn-height');
    btn.disabled = true; btn.textContent = '⏳ Calibrando...';
    fetch('/auto_calibrate', {method:'POST'}).then(function(r){ return r.json(); }).then(function(data) {
      btn.disabled = false; btn.textContent = '📊 Auto Calibrar Rango';
      updateConfig(data);
      var isError = (data.status || '').indexOf('Error') === 0;
      setFeedback('fb-height', (isError ? '✗ ' : '✓ ') + data.status, isError ? 'err' : 'ok');
    }).catch(function(){ btn.disabled=false; btn.textContent='📊 Auto Calibrar Rango'; });
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

  function setDepthMax(val) {
    var dmax = Math.max(1, Math.min(2047, parseInt(val, 10) || state.depthMax));
    fetch('/update', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({depth_min: state.depthMin, depth_max: dmax})
    }).then(function(r){ return r.json(); }).then(updateConfig);
  }

  function setDepthMin(val) {
    var dmin = Math.max(0, Math.min(2046, parseInt(val, 10) || state.depthMin));
    fetch('/update', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({depth_min: dmin, depth_max: state.depthMax})
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
    }).then(function(r){ return r.json(); }).then(function(data){
      updateConfig(data);
      var btn = document.querySelector('.btn-exhib');
      btn.textContent = '✓ Exhibición activada';
      setTimeout(function(){ btn.textContent = '🎬 Exhibición'; }, 2000);
    });
  }

  function toggleMode() {
    var next = state.mode === 'exhibition' ? 'calibration' : 'exhibition';
    fetch('/mode', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({mode: next})
    }).then(function(r){ return r.json(); }).then(function(data){
      updateConfig(data);
      var btn = document.querySelector('.btn-exhib');
      btn.textContent = next === 'exhibition' ? '✓ Exhibición activada' : '✓ Modo calibración';
      setTimeout(function(){ btn.textContent = '🎬 Exhibición'; }, 2000);
    });
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
        'crop_active':      config.get('crop') is not None,
        'range_calibrated': config.get('range_calibrated', False),
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
    # Captura el frame completo como referencia de suelo -- asi el marco de
    # la caja (estatico, siempre mas cerca del Kinect que la arena) nunca
    # cambia respecto a esta foto y se renderiza oscuro, no solo el centro.
    if not calibrate_floor():
        return jsonify({'error': 'sin datos del Kinect'}), 503
    config['depth_max'] = int(np.mean(valid))  # valor informativo, no se usa para el render

    # Detecta automaticamente el rectangulo de arena (distinto del marco y de
    # lo que hay mas alla de la caja) para que el render use solo esa area.
    crop, crop_msg, crop_warn = detect_sand_crop(floor_frame[0])
    config['crop'] = crop
    payload = _payload()
    payload['crop_msg'] = crop_msg
    if crop_warn:
        payload['crop_warn'] = crop_warn
    return jsonify(payload)


@app.route('/set_max_height', methods=['POST'])
def set_max_height():
    if floor_frame[0] is None:
        return jsonify({'error': 'primero completa el Paso 1 (Calibrar Base)'}), 503
    if last_depth_frame[0] is None:
        return jsonify({'error': 'sin datos del Kinect'}), 503
    d = last_depth_frame[0].astype(np.float32)
    h, w = d.shape
    cy, cx = h // 2, w // 2
    roi = d[cy-30:cy+30, cx-40:cx+40]
    valid = roi[(roi > 0) & (roi < 2047)]
    if len(valid) < 100:
        return jsonify({'error': 'cobertura insuficiente'}), 503
    froi = floor_frame[0][cy-30:cy+30, cx-40:cx+40]
    fvalid = froi[(froi > 0) & (froi < 2047)]
    if len(fvalid) < 100:
        return jsonify({'error': 'referencia de suelo insuficiente'}), 503
    elev = float(np.mean(fvalid)) - float(np.mean(valid))
    config['depth_min'] = 0
    config['depth_max'] = max(int(elev), 10)
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


# Usada por el Paso 2 del asistente ("Auto Calibrar Rango")
@app.route('/auto_calibrate', methods=['POST'])
def auto_calibrate_route():
    auto_calibrate()
    p = _payload()
    p['status'] = auto_calib_status[0]
    return jsonify(p)


# Endpoints legacy (no expuestos en UI, conservados por si acaso)


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
