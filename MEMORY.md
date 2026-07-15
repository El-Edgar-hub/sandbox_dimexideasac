# MEMORY.md — AR Sandbox (sandbox_dimexideasac)

Ultima actualizacion: 2026-07-15 (commit `2736ac8`, branch `v2`).

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

Construido pero **deshabilitado**: calibracion geometrica por homografia
(4 esquinas con la mano). El codigo se conserva intacto en `homography.py`
pero **no se importa desde `web.py`** — no hay rutas activas para
usarlo. Deshabilitado desde el commit `a845686` por ruido USB confirmado
en esta RPi especifica (ver "Decisiones clave").

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
  aplica homografia si existe, dibuja el overlay de estado, y muestra.
- **`overlay.py`** — todo lo que se dibuja encima del frame ya renderizado:
  el panel de calibracion (paso 1/2), el badge de "EXHIBICION", y la marca
  de esquina para la calibracion de homografia (sin usar hoy).
- **`calibration.py`** — medir y calibrar la instalacion fisica:
  `calibrate_floor()`/`reset_floor()` (captura/borra el suelo de
  referencia), `get_effective_floor()` (suelo + `zero_offset`),
  `_update_live_stretch()` (ajuste continuo opcional, no usado por
  defecto), `detect_sand_crop()` (recorte automatico del area de arena),
  `auto_calibrate()` (mide el relieve real y fija el rango de color).
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
| `/set_base` | POST | Paso 1: captura suelo plano + detecta recorte de arena + auto-guarda |
| `/set_max_height` | POST | Legacy, no usado por ningun boton (gesto manual de altura) |
| `/update` | POST | Ajuste manual de `depth_min`/`depth_max` + auto-guarda |
| `/mode` | POST | Cambia `calibration`/`exhibition` + auto-guarda |
| `/set_zero_offset` | POST | Mueve el nivel cero (`zero_offset`) + auto-guarda |
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
- **Por que `HOME=/home/fran` explicito en el servicio systemd**:
  `config.py` usa `os.path.expanduser('~')` para ubicar
  `sandbox_config.json`/`sandbox_floor.npy`. systemd con `User=root` fija
  `HOME=/root` si no se especifica, y el proceso no encontraba los
  archivos guardados en `/home/fran` — arrancaba con la config de
  fabrica en vez de la calibracion real. Confirmado con un reinicio real
  de la RPi antes del fix.

## Pendientes

- Calibracion geometrica (homografia) sigue deshabilitada — retomar
  requeriria hardware mas estable (fuente de alimentacion sin
  subvoltaje) o una tecnica de deteccion de mano distinta.
- El usuario ajusta el techo/valle manualmente cuando quiere ver mas
  rojo/blanco/azul profundo; no hay plan de reducir el margen +20 de
  `auto_calibrate()`.
- `/set_max_height`, `/calibrate_floor`, `/reset_floor`, `/toggle_stretch`
  son rutas legacy sin boton en la UI — conservadas por si se necesitan
  para debug, no forman parte del flujo normal.
- No hay pruebas automatizadas — la verificacion es manual/sintetica por
  SSH contra la RPi real (ver `DEVELOPMENT.md`).
