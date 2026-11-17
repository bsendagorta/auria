"""Incidencias oficiales de tráfico de Euskadi en DATEX II (Dirección de Tráfico del Gobierno Vasco).

Fuente pública (Punto de Acceso Nacional de la DGT, publicación "Incidencias DT-GV", sin licencia ni clave):
    https://nap.dgt.es/datex2/dt-gv/SituationPublication/all/content.xml
Información validada por el centro de gestión de tráfico de Euskadi y la Ertzaintza.

Cada lectura se guarda (solo Bizkaia, sin Bilbao ciudad) en datos/online/<origen>/datex_AAAA-MM.csv:
    id, versión, tipo de registro DATEX (Accident, Obstruction, PoorEnvironmentConditions, AbnormalTraffic…),
    causa/subtipo, gravedad, inicio, carretera, latitud, longitud, parque y hora de la lectura.
En directo sirve para contar accidentes y obstáculos activos por parque cuando la API de incidencias falla.
"""
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from . import config
from .parques import PARQUES, parque_mas_cercano

URL = "https://nap.dgt.es/datex2/dt-gv/SituationPublication/all/content.xml"   # DATEX II 1.0, cada ~9 min
BBOX = (42.95, 43.47, -3.46, -2.40)          # Bizkaia (lat_min, lat_max, lon_min, lon_max)
BILBAO = (43.235, 43.29, -2.98, -2.89)       # Bilbao ciudad (servicio municipal)
CAMPOS = ["leido", "id", "version", "tipo", "subtipo", "gravedad", "inicio", "carretera", "lat", "lon", "parque"]
TZ = ZoneInfo("Europe/Madrid")


def _local(e):
    return e.tag.rsplit("}", 1)[-1]


def _hijo(e, nombre):
    for x in e.iter():
        if _local(x) == nombre:
            return x
    return None


def _texto(e, nombre):
    x = _hijo(e, nombre) if e is not None else None
    return (x.text or "").strip() if x is not None and x.text else ""


def parsear(xml: bytes):
    raiz = ET.fromstring(xml)
    filas = []
    for r in raiz.iter():
        if _local(r) != "situationRecord":
            continue
        tipo = next((v for k, v in r.attrib.items() if k.endswith("}type") or k == "type"), "")
        tipo = tipo.split(":")[-1]
        lat, lon = _texto(r, "latitude"), _texto(r, "longitude")
        try:
            lat, lon = float(lat), float(lon)
        except ValueError:
            continue
        if not (BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]):
            continue
        if BILBAO[0] <= lat <= BILBAO[1] and BILBAO[2] <= lon <= BILBAO[3]:
            continue
        sub = ""
        for n in ("accidentType", "obstructionType", "poorEnvironmentType", "abnormalTrafficType",
                  "roadMaintenanceType", "causeType", "vehicleObstructionType", "environmentalObstructionType"):
            sub = _texto(r, n)
            if sub:
                break
        filas.append({
            "id": r.attrib.get("id", ""), "version": r.attrib.get("version", ""), "tipo": tipo, "subtipo": sub,
            "gravedad": _texto(r, "overallSeverity") or _texto(r, "impactOnTraffic"), "inicio": _texto(r, "overallStartTime"),
            "carretera": _texto(r, "roadNumber"), "lat": round(lat, 5), "lon": round(lon, 5),
            "parque": parque_mas_cercano(lat, lon),
        })
    return filas


def capturar(carpeta=None):
    """Descarga, filtra y añade al CSV mensual. Devuelve las filas (lista vacía si el servicio falla)."""
    ahora = datetime.now(TZ)
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": config.USER_AGENT})
        r.raise_for_status()
        filas = parsear(r.content)
    except Exception as e:
        print(f"Aviso DATEX II: {e}", flush=True)
        return []
    from .recolector_online import carpeta_origen
    d = carpeta or carpeta_origen()
    d.mkdir(parents=True, exist_ok=True)
    ruta = d / f"datex_{ahora:%Y-%m}.csv"
    nueva = not ruta.exists()
    with open(ruta, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        if nueva:
            w.writeheader()
        for x in filas:
            w.writerow({"leido": ahora.isoformat(timespec="seconds"), **x})
    return filas


def por_parque(filas):
    """Accidentes y obstáculos activos por parque en la última lectura."""
    out = {p: {"accidentes": 0, "obstaculos": 0} for p in PARQUES}
    for x in filas:
        if x["tipo"] == "Accident":
            out[x["parque"]]["accidentes"] += 1
        elif x["tipo"] in ("Obstruction", "EnvironmentalObstruction", "GeneralObstruction",
                           "VehicleObstruction", "AnimalPresenceObstruction"):
            out[x["parque"]]["obstaculos"] += 1
    return out


if __name__ == "__main__":
    f = capturar()
    print(len(f), "incidencias DATEX II en Bizkaia")
    print(por_parque(f))
