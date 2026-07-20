# MEMORY.md — AR Sandbox (sandbox_dimexideasac)

Ultima actualizacion: 2026-07-20 (commit `34bff15`, branch `v2`).

Este archivo es el que hay que leer primero para entender el estado actual
del codigo y como se llego hasta aqui. `DEVELOPMENT.md` (fuera del repo,
en la carpeta padre `sandbox/`) tiene el flujo de trabajo diario y enlaza
aqui para el resto.

## Estado del proyecto

Sandbox funcionando con Kinect v1 + proyector + Raspberry Pi ("Fran").
Modo de render activo: **suelo relativo bipolar** — se fija un suelo plano
de referencia una vez, y la elevacion se mide con signo respecto a ese
suelo (monticulo positivo, valle negativo), en vez del modo clasico
profundidad-absoluta.

Construido y en uso hoy:
- Recorte automatico del area de arena (sin marcar esquinas a mano).
- Auto-calibracion de rango de color a partir del relieve real construido
  en la arena (sin gestos de mano).
- Overlay de estado (paso 1/2 completados, modo actual) dibujado
  directamente sobre la proyeccion.
- Colormap bipolar: verde = elevacion cero, azules hacia abajo, calidos
  hacia arriba.
- Nivel cero movible manualmente (`zero_offset`) sin recapturar el suelo.
- Auto-guardado de la calibracion en cada cambio (no depende de presionar
  "Guardar").
- Arranque automatico al encender la RPi via systemd (ver
  `systemd/sandbox.service`).
- Vista previa en vivo del mapa de colores de la arena dentro de la app de
  calibracion (`/preview.jpg`), en vez de solo un numero y un color plano.
- Alineacion manual de geometria (keystone) por ajuste de 4 esquinas con
  botones de flecha, mirando la proyeccion real — Paso 3 de la app,
  `config['geo_corners']` + `/nudge_corner` + `/reset_geometry`. Es una
  **alternativa independiente** a la homografia por deteccion de mano de
  abajo, no la reemplaza ni la revive: reutiliza el mismo mecanismo de
  aplicacion (`config['homography']` + `cv2.warpPerspective`), pero la
  matriz se calcula desde 4 puntos que el usuario ajusta a ojo, sin que el
  Kinect tenga que detectar nada — inmune al ruido USB.
- Forma real de la arena extraída de los datos de profundidad
  (`config['kinect_quad']`, `calibration.extract_sand_quad()`) en vez de
  asumir un rectángulo alineado a los ejes — corrige la inclinación real
  del Kinect respecto a la caja en el lado *origen* de la homografía (el
  Paso 3 de arriba corrige el lado *destino*, el del proyector). Se activa
  al presionar "Capturar Base Plana" de nuevo con este código — ya
  confirmado activo en producción (`quad_active: true`) tras que el
  usuario recapturara la base y reajustara el Paso 3.
- Control de energía desde el celular (`/restart_program`,
  `/stop_program`, `/shutdown_rpi`) — antes solo existía en la app de Mac
  (un servidor separado que corre en la Mac, no en la RPi). "Reiniciar" sí
  puede autoservirse (systemd levanta una instancia nueva); "Detener" no
  deja nada corriendo para un "Arrancar" futuro desde la misma página —
  para eso hace falta SSH, la app de Mac, o reiniciar la RPi.
- El servicio systemd se autorepara: `Restart=always` (antes
  `on-failure`) + `StartLimitIntervalSec=0` — ver "Decisiones clave".

Construido pero **deshabilitado**: calibracion geometrica por homografia
(4 esquinas con la mano). El codigo se conserva intacto en `homography.py`
pero **no se importa desde `web.py`** — no hay rutas activas para
usarlo. Deshabilitado desde el commit `a845686` por ruido USB confirmado
en esta RPi especifica (ver "Decisiones clave"). El ajuste manual de
geometria (punto anterior) es la via que se usa hoy en su lugar.

## Mapa de archivos

- **`main.py`** — arranca Flask en un hilo, abre la ventana `cv2` a
  pantalla completa, y entra al loop de captura de `freenect`
  (`freenect.runloop(depth=get_depth, video=get_video)`). Carga la config
  guardada al inicio (`load_config()`).
- **`config.py`** — estado compartido entre todos los modulos: el dict
  `config`, las listas de un elemento (`last_depth_frame`, `floor_frame`,
  etc.), y `load_config()`/`save_config()` para persistir en disco. Ver
  detalle abajo.
- **`kinect.py`** — solo `get_depth()`/`get_video()`, los callbacks que
  usa `freenect.runloop`. Por frame: calcula elevacion (via
  `calibration.get_effective_floor()`), aplica el colormap, recorta,
  aplica homografia si existe (deformando el frame COMPLETO en vez del
  recortado cuando `config['kinect_quad']` esta presente — ver
  "Decisiones clave"), dibuja el overlay de estado, y muestra.
- **`overlay.py`** — todo lo que se dibuja encima del frame ya renderizado:
  el panel de calibracion (paso 1/2), el badge de "EXHIBICION", y la marca
  de esquina para la calibracion de homografia (sin usar hoy).
- **`calibration.py`** — medir y calibrar la instalacion fisica:
  `calibrate_floor()`/`reset_floor()` (captura/borra el suelo de
  referencia), `get_effective_floor()` (suelo + `zero_offset`),
  `_update_live_stretch()` (ajuste continuo opcional, no usado por
  defecto), `detect_sand_crop()` (recorte rectangular del area de arena,
  ahora envoltorio delgado sobre `_dominant_sand_component()`),
  `extract_sand_quad()` (forma REAL, no rectangular, de la arena —
  comparte la seleccion de blob con `detect_sand_crop` via
  `_dominant_sand_component`), `check_quad_against_measurements()`
  (verificacion de sanidad contra medidas fisicas a cinta metrica),
  `auto_calibrate()` (mide el relieve real y fija el rango de color),
  `current_geo_corners()`/`nudge_geo_corner()`/`reset_geo_corners()`/
  `recompute_geo_homography()` (ajuste manual de keystone, ver abajo).
- **`homography.py`** — calibracion de 4 esquinas por deteccion de mano,
  **deshabilitada** (ver arriba). Conservada intacta por si se retoma con
  mejor hardware o otra tecnica de deteccion.
- **`colormap.py`** — construye el LUT de 256 colores bipolar
  (`make_topo_colormap()`) y `apply_colormap()`.
- **`web.py`** — Flask: la UI del asistente de calibracion (HTML+JS
  embebido en un string) y todas las rutas. Ver tabla de rutas abajo.
- **`systemd/sandbox.service`** — copia de referencia del servicio
  systemd instalado en la RPi (`/etc/systemd/system/sandbox.service`) para
  que `main.py` arranque solo al encender, sin SSH ni la app de Mac.

Direccion de imports (sin ciclos): `kinect.py` → `calibration.py` +
`overlay.py`; `web.py` → `calibration.py`; todos → `config.py`.
`homography.py` no lo importa nadie hoy (deshabilitado).

## Estado compartido (`config.py`)

```python
config = {
    'depth_min': 400,
    'depth_max': 2000,
    'mode': 'calibration',       # o 'exhibition'
    'homography': None,          # matriz 3x3 o None (no usado, ver arriba)
    'crop': None,                # [x0,y0,x1,y1] en espacio Kinect 640x480
    'range_calibrated': False,   # True solo si auto_calibrate() midio un rango real
    'zero_offset': 0,            # unidades crudas restadas a floor_frame (ver abajo)
    'geo_corners': None,          # [[x,y]x4] TL,TR,BR,BL en 1920x1080, o None
                                  # (None == pantalla completa, ver Paso 3 / keystone manual)
    'kinect_quad': None,          # [[x,y]x4] TL,TR,BR,BL en espacio Kinect 640x480, o None
                                  # (None == usa el rectangulo de crop, ver extract_sand_quad)
}
```

Listas de un elemento (mutables por referencia entre modulos):
`last_depth_frame`, `floor_frame`, `live_stretch`, `auto_calib_status`,
`homography_step`, `homography_points`, `homography_floor`.

Persistencia — dos mecanismos separados:
- `config` → `~/sandbox_config.json` via `save_config()`/`load_config()`.
  Se auto-guarda en cada ruta que cambia algo (`set_base`,
  `auto_calibrate` cuando `range_calibrated` pasa a `True`, `mode`,
  `update`, `set_zero_offset`) — no depende de presionar "Guardar".
- `floor_frame[0]` → `~/sandbox_floor.npy` via `np.save`/`np.load`
  (array separado, no es JSON-serializable). Se guarda en
  `calibrate_floor()`, se borra en `reset_floor()`.

Ambos archivos viven en el `$HOME` del proceso. El servicio systemd fija
`HOME=/home/fran` explicitamente porque `User=root` sin esa variable
hace que systemd use `/root` (ver "Decisiones clave").

## Logica de elevacion actual

En `get_depth()` (`kinect.py`), cuando hay suelo fijado
(`get_effective_floor()` no es `None`):

```python
ref = get_effective_floor()          # floor_frame - zero_offset
elev = ref - depth                   # con signo: + monticulo, - valle
pos_norm = clip(elev / depth_max, 0, 1)
neg_norm = clip(-elev / depth_min, 0, 1)
depth_norm = 0.5 + 0.5*pos_norm   si elev >= 0
           = 0.5 - 0.5*neg_norm  si elev <  0
```

`depth_max` = techo del monticulo mas alto; `depth_min` = profundidad del
valle mas hondo (nombres heredados del modo clasico, hoy son los dos
extremos del relieve con signo). `depth_norm = 0.5` es la elevacion cero.

Sin suelo fijado, cae al modo clasico (profundidad absoluta, sin signo,
recortada entre `depth_min`/`depth_max`).

`get_effective_floor()` (`calibration.py`) es el suelo real usado en todos
los calculos de elevacion — `floor_frame[0] - zero_offset`. Mover
`zero_offset` desplaza el nivel cero (verde) sin recapturar el suelo.
Una nueva `calibrate_floor()`/`reset_floor()` resetea `zero_offset` a `0`.

## Colormap (`colormap.py`)

LUT de 256 valores, BGR, bipolar con el verde fijo en el indice 128:

| indice | color | significado |
|---|---|---|
| 0 | azul profundo `[80,0,0]` | valle mas hondo |
| 55 | azul `[180,60,0]` | |
| 95 | cian `[200,160,0]` | |
| **128** | **verde `[80,180,0]`** | **elevacion cero (suelo fijado)** |
| 180 | amarillo-verde `[0,210,180]` | |
| 210 | naranja `[0,160,255]` | |
| 240 | rojo `[0,0,200]` | |
| 255 | blanco `[255,255,255]` | monticulo mas alto |

## Rutas Flask (`web.py`)

| Ruta | Metodo | Que hace |
|---|---|---|
| `/` | GET | Sirve la UI del asistente de calibracion |
| `/status` | GET | `_payload()` — estado completo actual |
| `/depth_stats` | GET | Lectura en vivo del centro del frame, para la tarjeta de sensor de la UI |
| `/preview.jpg` | GET | Ultimo frame ya coloreado/recortado (el mismo que se proyecta), codificado a JPEG al vuelo, para la vista previa en vivo de la UI |
| `/set_base` | POST | Paso 1: captura suelo plano + detecta recorte de arena + extrae su forma real + auto-guarda |
| `/set_max_height` | POST | Legacy, no usado por ningun boton (gesto manual de altura) |
| `/update` | POST | Ajuste manual de `depth_min`/`depth_max` + auto-guarda |
| `/mode` | POST | Cambia `calibration`/`exhibition` + auto-guarda |
| `/set_zero_offset` | POST | Mueve el nivel cero (`zero_offset`) + auto-guarda |
| `/nudge_corner` | POST | Paso 3: mueve una esquina de geometria (keystone) + auto-guarda |
| `/reset_geometry` | POST | Quita el ajuste manual de geometria (vuelve a pantalla completa) + auto-guarda |
| `/restart_program` | POST | `systemctl restart sandbox.service` tras una pausa corta (en un hilo aparte, para que la respuesta HTTP llegue antes de que el proceso se caiga) |
| `/stop_program` | POST | `systemctl stop sandbox.service` (mismo patron de hilo con pausa) |
| `/shutdown_rpi` | POST | `shutdown -h now` (mismo patron de hilo con pausa) |
| `/save` | POST | Guarda `config` a disco explicitamente (boton "Guardar", ya no estrictamente necesario) |
| `/auto_calibrate` | POST | Paso 2: mide relieve real y fija el rango de color + auto-guarda si queda calibrado |
| `/calibrate_floor` | POST | Legacy, no expuesto en la UI |
| `/reset_floor` | POST | Legacy, no expuesto en la UI |
| `/toggle_stretch` | POST | Legacy, no expuesto en la UI |

No hay rutas de homografia activas — se quitaron todas en el commit
`a845686`.

## Historial de cambios grandes (desde `cf8e6d2`, `2026-06-09`)

1. **Fix de direccion de profundidad + `/depth_stats`** (`c8e0c72`) — el
   render tenia la escala de profundidad invertida.
2. **Rediseno de la interfaz de calibracion** (`117fb9a`) — asistente de 2
   pasos + fix de orden de canales BGR en el colormap.
3. **Flask threaded** (`1b22900`) — el servidor bloqueaba al hacer polling
   de estado mientras el render corria en el mismo proceso.
4. **Homografia construida y luego deshabilitada** (`fb235c6` .. `a845686`,
   9 commits) — calibracion geometrica de 4 esquinas por deteccion de
   mano; varias iteraciones intentando hacerla robusta a corrupcion USB
   confirmada del Kinect en esta RPi (paquetes perdidos, "Invalid magic"),
   hasta deshabilitarla por completo (rutas quitadas de `web.py`, no solo
   ocultas en la UI). Codigo conservado en `homography.py`.
5. **Reconexion al modo suelo relativo** (`34bfcc2`) — para ocultar el
   borde de la caja de madera, que el modo absoluto no distinguia de la
   arena.
6. **Reemplazo del gesto de mano por auto-calibracion de terreno**
   (`6bb6442`) — la deteccion de altura por gesto tenia el mismo problema
   de ruido USB que la homografia; se reemplazo por medir el relieve real
   ya construido en la arena.
7. **Recorte automatico del area de arena** (`2f09d31`) — distingue el
   rectangulo de arena del marco de madera y del fondo por banda de
   profundidad, sin marcar esquinas a mano.
8. **Fix de rango inflado por corrupcion USB** (`72dfa8f`) — picos de
   corrupcion de 1000+ unidades inflaban el percentil usado por
   `auto_calibrate()`; se agrego blur + exclusion explicita de rango.
9. **Overlay de estado en el proyector** (`86e62b1`) — panel de
   paso 1/2 completados y badge de modo, dibujados sobre la proyeccion
   misma (no solo en la UI web).
10. **Controles manuales de rango** (`b9a58b1`) — ajuste fino de
    techo/valle ademas de la auto-calibracion.
11. **Colormap bipolar** (`a658146`) — verde = cero, azules abajo,
    calidos arriba (reemplaza el colormap recortado en 0 anterior).
12. **Division de `kinect.py` en 4 modulos + `zero_offset`** (`fd49ac4`) —
    separacion en `kinect.py`/`overlay.py`/`calibration.py`/
    `homography.py`; nuevo `zero_offset` para mover el nivel cero sin
    recapturar; auto-guardado en las rutas que cambian calibracion.
13. **Arranque automatico via systemd** (`9db8597`, `2736ac8`) — servicio
    que arranca `main.py` solo al encender la RPi; fix de `HOME` (systemd
    con `User=root` ponia `HOME=/root` por defecto, y el proceso no
    encontraba la config/suelo guardados en `/home/fran`).
14. **Vista previa en vivo en la app de calibracion** (`be4a83d`) — antes
    solo se veia un numero y un color plano (promedio del centro); ahora
    `/preview.jpg` sirve el mismo frame coloreado/recortado que se
    proyecta, sin costo extra por frame (se codifica a JPEG solo cuando
    se pide, no en cada callback del Kinect).
15. **Alineacion manual de geometria (keystone)** (`b9d48c4`) — la
    proyeccion tenia una distorsion trapezoidal real (confirmada por el
    usuario). En vez de revivir la homografia por deteccion de mano
    (ya descartada por no confiable), se agrego un ajuste manual de las 4
    esquinas destino con botones de flecha, mirando la proyeccion real —
    inmune al ruido USB porque no depende de datos de profundidad para
    calibrar. Por defecto (`geo_corners=None`) es geometricamente idéntico
    al `cv2.resize` de siempre, asi que no cambia nada hasta que se ajusta
    una esquina.
16. **Extraccion de la forma real de la arena** (`59eb2ac`) — el usuario
    midio con cinta metrica la distancia del Kinect a la arena en las 4
    esquinas (98/94/102/96cm), confirmando una inclinacion real. Se evaluo
    reconstruir esa inclinacion con trigonometria (posicion + orientacion
    del Kinect) pero se descarto por mal condicionada (el Kinect apunta
    casi derecho hacia abajo, ~7° de la vertical, lo que hace inestable el
    calculo de "hacia que lado esta inclinado" — una prueba con los
    numeros reales puso una esquina fuera del cuadro). En su lugar,
    `extract_sand_quad()` traza el contorno real directamente de los
    datos de profundidad ya capturados, sin necesitar saber nada del
    montaje fisico. Reemplaza el rectangulo ingenuo como lado "origen" de
    la homografia (`config['kinect_quad']`), complementando el Paso 3
    (que corrige el lado "destino", el del proyector).
17. **Control de energia desde el celular** (`e69bb5f`) — la app de Mac
    tiene botones de Arrancar/Apagar/Apagar RPi, pero corren en un
    servidor Flask separado en la Mac; un celular que abre
    `Fran.local:5000` directamente nunca los vio ni los vera. Se agregan
    `/stop_program` y `/shutdown_rpi` a la propia app de la RPi (ya corre
    como root via systemd, no hace falta sudo), con un pequeno delay en un
    hilo aparte para que la respuesta HTTP llegue al telefono antes de que
    el proceso/la RPi se detengan.
18. **Boton de reiniciar + auto-reparacion del servicio** (`34bff15`) —
    a diferencia de "Detener", "Reiniciar" (`/restart_program`,
    `systemctl restart`) si puede autoservirse desde el celular: el
    proceso actual sigue vivo al presionarlo, systemd detiene esa
    instancia y levanta una nueva. Ademas, `systemd/sandbox.service` pasa
    de `Restart=on-failure` a `Restart=always` (+ `StartLimitIntervalSec=0`)
    porque se observo el Kinect fallando al inicializar justo despues de
    arrancar ("Error: Can't open device"), lo cual hace que `main.py` salga
    con status 0 (no cuenta como fallo para `on-failure`) llevandose consigo
    tambien al servidor Flask -- dejando la app completamente inalcanzable
    hasta un restart manual por SSH. Confirmado en vivo el mismo dia: tras
    un restart, el Kinect fallo, systemd reintento solo ~6s despues sin
    intervencion, y la segunda instancia quedo sana.

## Decisiones clave

- **Por que se deshabilito la homografia**: esta RPi tiene subvoltaje
  confirmado (`dmesg`: "Undervoltage detected!") que corrompe el stream
  USB del Kinect ("Invalid magic", miles de "Lost too many packets,
  resyncing" por sesion). La deteccion de mano por altura, necesaria para
  capturar las 4 esquinas, no era confiable en la practica a pesar de
  varias iteraciones (suavizado, exclusion de picos corruptos,
  clustering temporal). Se opto por quitar las rutas en vez de solo
  ocultar el boton, para que quede claro que no esta en uso — el codigo
  se conserva por si se retoma con mejor hardware.
- **Por que el mismo problema de corrupcion USB aparece en varios
  lugares** (`auto_calibrate`, `_update_live_stretch`, y antes en la
  deteccion de mano): la mitigacion es siempre la misma — suavizar
  (`cv2.blur`) y excluir explicitamente un rango numerico razonable
  (elevaciones reales son de pocas decenas de unidades; la corrupcion
  produce cientos o miles) antes de calcular percentiles o buscar
  maximos.
- **Por que el margen +20 en `auto_calibrate()`**: deliberado, para dejar
  algo de "techo" por encima del relieve medido en vez de saturar el
  color justo en el punto mas alto/hondo detectado. El usuario prefiere
  ajustar el techo manualmente si quiere mas rojo/azul profundo, en vez
  de reducir este margen (ver "Pendientes").
- **Por que `zero_offset` en vez de recapturar el suelo**: permite mover
  el nivel cero (verde) hacia arriba o abajo sin tener que repetir
  "Capturar Base Plana" cada vez que el nivel de arena cambia levemente.
  Se resetea a `0` en cada nueva captura de suelo, para que una captura
  nueva sea siempre el cero real.
- **Por que dividir `kinect.py`**: tenia 437 lineas con 4
  responsabilidades entrelazadas fuera de orden (render, overlays,
  calibracion, homografia deshabilitada). Separado para poder tocar cada
  parte sin leer todo el archivo.
- **Por que la geometria se ajusta a mano (nudge) y no con un homografia
  detectada**: la deteccion de mano ya se probo y se descarto (ver arriba)
  por el ruido USB de esta RPi. El ajuste manual logra lo mismo
  (corregir keystone) sin depender en absoluto de los datos de
  profundidad — el usuario ve la proyeccion real y ajusta a ojo, algo que
  ninguna cantidad de suavizado de señal puede reemplazar cuando el
  problema de fondo es hardware.
- **Cuidado al probar rutas que auto-guardan contra el `~/sandbox_config.json`
  real**: no solo `FLOOR_FILE` es una ruta real compartida entre "test" y
  produccion (ver incidente anterior en el historial de este proyecto) —
  `CONFIG_FILE` tambien lo es. Un script de prueba que llama una ruta de
  `web.py` que termina en `save_config()` (p.ej. `/nudge_corner`,
  `/reset_geometry`, `/set_zero_offset`, etc.) escribe al archivo real sin
  importar de que copia del modulo se haya importado `config.py`, porque
  `CONFIG_FILE = os.path.expanduser('~/sandbox_config.json')` siempre
  resuelve a la misma ruta. Esto causo la perdida temporal de una
  calibracion real durante el desarrollo de la geometria manual (restaurada
  desde capturas de pantalla). Cualquier prueba sintetica que ejercite una
  ruta con auto-guardado debe respaldar `~/sandbox_config.json` antes (igual
  que ya se hacia con `sandbox_floor.npy`), o evitar llamar esas rutas
  directamente.
- **Por que se descarto la trigonometria para corregir el lado Kinect**:
  con 4 distancias medidas + el tamano real de la caja se puede triangular
  la posicion del Kinect, pero no su orientacion (las distancias no llevan
  informacion de rumbo) — hace falta asumir que apunta al centro y que no
  tiene "roll". Como el Kinect apunta casi derecho hacia abajo, esa segunda
  cuenta se vuelve numericamente inestable (division por un valor casi
  cero). Se prefirio extraer la forma real directamente de `floor_frame`
  (dato ya capturado, cero suposiciones sobre el montaje) en vez de
  calcularla con angulos.
- **Verificacion de las 4 esquinas contra las medidas fisicas**: al probar
  `check_quad_against_measurements()` contra el suelo real, el eje
  arriba/abajo coincidio exacto con lo medido, pero izquierda/derecha salio
  invertido. Diagnostico: es casi seguro un espejo entre el punto de vista
  del usuario (de espaldas a la pared) y como el Kinect ve la imagen
  internamente — que solo UN eje este invertido mientras el otro coincide
  perfecto es la firma tipica de esto, no de un error de extraccion. No se
  "corrigio" el codigo por esto; si se repite la verificacion y se quiere
  que deje de marcar esta discrepancia esperada, hay que invertir las
  etiquetas izquierda/derecha en `MEASURED_DISTANCES_CM`, no la logica.
- **Por que `HOME=/home/fran` explicito en el servicio systemd**:
  `config.py` usa `os.path.expanduser('~')` para ubicar
  `sandbox_config.json`/`sandbox_floor.npy`. systemd con `User=root` fija
  `HOME=/root` si no se especifica, y el proceso no encontraba los
  archivos guardados en `/home/fran` — arrancaba con la config de
  fabrica en vez de la calibracion real. Confirmado con un reinicio real
  de la RPi antes del fix.

## Pendientes

- Calibracion geometrica por deteccion de mano sigue deshabilitada —
  retomarla requeriria hardware mas estable (fuente de alimentacion sin
  subvoltaje) o una tecnica de deteccion distinta. El ajuste manual de
  keystone (Paso 3) es la via que se usa en su lugar.
- El usuario ajusta el techo/valle manualmente cuando quiere ver mas
  rojo/blanco/azul profundo; no hay plan de reducir el margen +20 de
  `auto_calibrate()`.
- `/set_max_height`, `/calibrate_floor`, `/reset_floor`, `/toggle_stretch`
  son rutas legacy sin boton en la UI — conservadas por si se necesitan
  para debug, no forman parte del flujo normal.
- No hay pruebas automatizadas — la verificacion es manual/sintetica por
  SSH contra la RPi real (ver `DEVELOPMENT.md`).
