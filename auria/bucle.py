"""Captura continua: lee bizkaia.eus cada N segundos durante M minutos y sube los datos cada K minutos.

GitHub Actions no permite tareas programadas más frecuentes que cada 5 min, así que la tarea
'Recolector cada minuto' arranca cada hora y ejecuta este bucle durante ~57 minutos.

Uso: python -m auria.bucle --minutos 57 --intervalo 60 --subir-cada 10
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime

import json

from . import config
from .directo import enriquecer
from .recolector_online import Bloqueado, PAUSA_BLOQUEO, TZ, bloqueo_pendiente, capturar


def publicar_directo(datos):
    """Deja la situación en directo en prediccion/directo.json (lo lee el panel)."""
    d = enriquecer(datos)
    (config.DIR_PREDICCION / "directo.json").write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")


def publicar_estado_bloqueo(desde):
    """Marca en directo.json que la lectura está bloqueada por la web (el panel lo explica)."""
    ruta = config.DIR_PREDICCION / "directo.json"
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        d = {"actuaciones": [], "por_parque": {}}
    previo = (d.get("bloqueado") or {}).get("desde")          # se conserva el inicio entre tramos
    d["bloqueado"] = {"desde": previo or desde.isoformat(timespec="minutes"),
                      "motivo": "bizkaia.eus responde con una verificación antibots a las lecturas automáticas",
                      "comprobado": datetime.now(TZ).isoformat(timespec="seconds")}
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def subir(mensaje):
    r = subprocess.run(["scripts/subir_datos.sh", mensaje], capture_output=True, text=True)
    print((r.stdout + r.stderr).strip() or "subido", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=float, default=57)
    ap.add_argument("--intervalo", type=int, default=60, help="segundos entre capturas")
    ap.add_argument("--subir-cada", type=float, default=10, help="minutos entre subidas a git (0 = no subir)")
    ap.add_argument("--prevision-cada", type=float, default=0, help="minutos entre predicciones (0 = no)")
    a = ap.parse_args(argv)

    fin = time.monotonic() + a.minutos * 60
    ultima_subida = time.monotonic()
    ultima_prevision = None
    ultimo_datex = None
    ultimo_euskalmet = None
    ultimo_eventos = None
    ultima_estacion = None
    ok = fallos = 0
    bloqueado_desde = None
    proximo_intento = time.monotonic() + bloqueo_pendiente(datetime.now(TZ))
    while time.monotonic() < fin:
        t0 = time.monotonic()
        if time.monotonic() >= proximo_intento:
            try:
                publicar_directo(capturar())        # directo.json nuevo: sin la marca de bloqueo
                ok += 1
                bloqueado_desde, proximo_intento = None, 0.0
            except Bloqueado:
                # la web no quiere lecturas automáticas: no se insiste cada minuto (se prueba cada 30 min)
                fallos += 1
                bloqueado_desde = bloqueado_desde or datetime.now(TZ)
                proximo_intento = time.monotonic() + PAUSA_BLOQUEO
                publicar_estado_bloqueo(bloqueado_desde)
            except Exception:
                fallos += 1          # ya queda registrado en capturas_*.csv con ok=0
        # incidencias oficiales DATEX II (Tráfico Euskadi) cada 5 min
        if ultimo_datex is None or time.monotonic() - ultimo_datex >= 300:
            try:
                from .datex import capturar as capturar_datex
                print(f"DATEX II: {len(capturar_datex())} incidencias en Bizkaia", flush=True)
            except Exception as e:
                print(f"Aviso DATEX II: {e}", flush=True)
            # avisos de Euskalmet cada 30 min (solo si hay clave en los secretos)
            try:
                from . import euskalmet
                if euskalmet.disponible() and (ultimo_euskalmet is None or time.monotonic() - ultimo_euskalmet >= 1800):
                    print(f"Euskalmet: avisos de {len(euskalmet.capturar())} zonas", flush=True)
                    ultimo_euskalmet = time.monotonic()
            except Exception as e:
                print(f"Aviso Euskalmet: {e}", flush=True)
            # estaciones de Euskalmet (lo medido) cada 10 min; agenda y fiestas una vez al día
            try:
                from . import estaciones
                if ultima_estacion is None or time.monotonic() - ultima_estacion >= 600:
                    t = estaciones.directo()
                    print(f"Estaciones: {len(t)} horas-parque medidas", flush=True)
                    ultima_estacion = time.monotonic()
            except Exception as e:
                print(f"Aviso estaciones: {e}", flush=True)
            try:
                if ultimo_eventos is None or time.monotonic() - ultimo_eventos >= 6 * 3600:
                    from . import eventos_publicos
                    eventos_publicos.main()
                    ultimo_eventos = time.monotonic()
            except Exception as e:
                print(f"Aviso eventos: {e}", flush=True)
            ultimo_datex = time.monotonic()
        if a.prevision_cada and (ultima_prevision is None
                                 or time.monotonic() - ultima_prevision >= a.prevision_cada * 60):
            try:
                from .prevision import predecir
                predecir(6)
                print("predicción actualizada", flush=True)
                from .evaluacion import evaluar     # acierto real: predicho vs contador de la web
                evaluar()
            except BaseException as e:      # incluye SystemExit si falta la tasa base
                print(f"Aviso predicción: {e}", flush=True)
            ultima_prevision = time.monotonic()
        if a.subir_cada and time.monotonic() - ultima_subida >= a.subir_cada * 60:
            subir(f"datos: capturas por minuto hasta {datetime.now(TZ):%H:%M}")
            ultima_subida = time.monotonic()
        espera = a.intervalo - (time.monotonic() - t0)
        if espera > 0 and time.monotonic() + espera < fin:
            time.sleep(espera)
        elif espera > 0:
            break
    if a.subir_cada:
        subir(f"datos: capturas por minuto hasta {datetime.now(TZ):%H:%M} (fin de tramo)")
    print(f"Fin del tramo: {ok} capturas correctas, {fallos} fallidas", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
