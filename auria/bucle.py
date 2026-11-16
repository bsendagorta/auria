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
from .recolector_online import TZ, capturar


def publicar_directo(datos):
    """Deja la situación en directo en prediccion/directo.json (lo lee el panel)."""
    d = enriquecer(datos)
    (config.DIR_PREDICCION / "directo.json").write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")


def subir(mensaje):
    r = subprocess.run(["scripts/subir_datos.sh", mensaje], capture_output=True, text=True)
    print((r.stdout + r.stderr).strip() or "subido", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=float, default=57)
    ap.add_argument("--intervalo", type=int, default=60, help="segundos entre capturas")
    ap.add_argument("--subir-cada", type=float, default=10, help="minutos entre subidas a git (0 = no subir)")
    a = ap.parse_args(argv)

    fin = time.monotonic() + a.minutos * 60
    ultima_subida = time.monotonic()
    ok = fallos = 0
    while time.monotonic() < fin:
        t0 = time.monotonic()
        try:
            publicar_directo(capturar())
            ok += 1
        except Exception:
            fallos += 1          # ya queda registrado en capturas_*.csv con ok=0
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
