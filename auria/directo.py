"""Lectura en tiempo real de bizkaia.eus: actuaciones activas, parque, familia y estado de cada vehículo.

La web lista, para cada actuación en curso, el tipo, el municipio, la calle y los vehículos con su estado:
  "Bomba urbana pesada (Vehículo va a un siniestro)"      -> EN_RUTA
  "Furgón utiles varios (Vehículo parado en siniestro)"  -> EN_SINIESTRO
  "Bomba urbana pesada (Vehículo volviendo de un sin.)"  -> REGRESANDO
  "Auto escala articulada (Vehículo propuesto)"           -> PROPUESTO (asignado, aún sin salir)
Si hay varios, la tarjeta dice "Varios vehículos implicados" y la lista va en el desplegable
"Conocer todos los vehículos" (se lee del HTML aunque esté plegado).
El parque se deduce del municipio (zona oficial de cada parque); la web no dice de qué parque sale cada vehículo.

Uso: python -m auria.directo          (imprime la situación actual)
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .familias import familia
from .parques import PARQUES, SIN_PARQUE, parque_de_nombre

TZ = ZoneInfo("Europe/Madrid")
ESTADOS = {
    "PROPUESTO": ("propuesto", "asignado"),
    "EN_RUTA": ("va a", "en camino", "salida"),
    "EN_SINIESTRO": ("parado en", "en siniestro", "trabajando"),
    "REGRESANDO": ("volviendo", "regresa", "vuelta"),
}
ESTADO_TXT = {"PROPUESTO": "📋 propuesto", "EN_RUTA": "🚨 en ruta", "EN_SINIESTRO": "🔥 en el siniestro", "REGRESANDO": "↩️ regresando",
              "OTRO": "· otro"}
_RX = re.compile(r"^(.*?)\s*\((.*)\)\s*$")


def vehiculo(texto: str) -> dict:
    m = _RX.match(texto or "")
    tipo, est = (m.group(1), m.group(2)) if m else (texto, "")
    e = est.lower()
    estado = next((k for k, claves in ESTADOS.items() if any(c in e for c in claves)), "OTRO")
    return {"tipo": tipo.strip(), "estado": estado, "estado_txt": est.strip()}


def enriquecer(datos: dict) -> dict:
    """Añade parque, familia y estado de vehículos a la salida de recolector_online.parsear()."""
    acts = []
    for t in datos["activas"]:
        p = parque_de_nombre(t["ubicacion"])
        vs = [vehiculo(v) for v in t["vehiculos"]]
        acts.append({
            "tipo": t["tipo"], "familia": familia(t["tipo"]), "ubicacion": t["ubicacion"], "zona": t["zona"],
            "parque": p, "parque_nombre": PARQUES.get(p, {}).get("nombre", "Fuera de zona / Bilbao"),
            "vehiculos": vs, "n_vehiculos": len(vs),
            "estado": _estado_actuacion(vs),
        })
    por_parque = {}
    for p in list(PARQUES) + [SIN_PARQUE]:
        mias = [a for a in acts if a["parque"] == p]
        vs = [v for a in mias for v in a["vehiculos"]]
        por_parque[p] = {"actuaciones": len(mias), "vehiculos": len(vs),
                         **{k.lower(): sum(v["estado"] == k for v in vs)
                            for k in ("PROPUESTO", "EN_RUTA", "EN_SINIESTRO", "REGRESANDO")}}
    return {"ts": datetime.now(TZ).isoformat(timespec="seconds"), "salidas_desde_8": datos["desde_8"],
            "salidas_anio": datos["anio"], "actuaciones": acts, "por_parque": por_parque}


def _estado_actuacion(vs):
    est = {v["estado"] for v in vs}
    for k in ("EN_RUTA", "EN_SINIESTRO", "PROPUESTO", "REGRESANDO"):
        if k in est:
            return k
    return "OTRO"


def leer(html: str = None) -> dict:
    from .recolector_online import descargar_html, parsear
    return enriquecer(parsear(html if html is not None else descargar_html()))


def main():
    d = leer()
    print(f"{d['ts']} · salidas hoy desde las 08:00: {d['salidas_desde_8']} · este año: {d['salidas_anio']}")
    if not d["actuaciones"]:
        print("Sin actuaciones activas.")
    for a in d["actuaciones"]:
        vs = ", ".join(f"{v['tipo']} [{ESTADO_TXT[v['estado']]}]" for v in a["vehiculos"])
        print(f"- {a['parque_nombre']:<20} {a['tipo']} · {a['ubicacion']} ({a['zona']}) · {vs}")


if __name__ == "__main__":
    main()


