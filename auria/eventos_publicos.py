"""Eventos públicos y fiestas de Bizkaia a partir de datos abiertos (sin mantenimiento a mano).

1. Fiestas locales (patronales) por municipio — Calendario laboral de Euskadi (Open Data Euskadi):
     https://opendata.euskadi.eus/contenidos/ds_eventos/calendario_laboral_AAAA/opendata/calendario_laboral_AAAA.json
   municipalitycode = código INE de 3 cifras (Bizkaia: 48 + código).  -> datos/festivos_locales.csv
2. Agenda cultural (Kulturklik, API de Open Data Euskadi): conciertos, fiestas, festivales, ferias…
     https://api.euskadi.eus/culture/events/v1.0/events/upcoming?_elements=…&_page=…
   Cada evento trae municipio y coordenadas: se asigna al parque cuyo término municipal lo contiene.
   Se acumula día a día en datos/eventos_publicos.csv (la API solo guarda lo próximo).
Salida para la predicción: datos/eventos_auto.csv, mismo formato que datos/eventos.csv
  (inicio, fin, nombre, nivel, parques); nivel 1 = fiesta/evento con público, 2 = masivo.
Uso: python -m auria.eventos_publicos   (cada noche y en el recolector una vez al día)
"""
import json
import re
from datetime import date, datetime, timedelta

import pandas as pd
import requests

from . import config
from .parques import INE_A_PARQUE, PARQUES

URL_CAL = "https://opendata.euskadi.eus/contenidos/ds_eventos/calendario_laboral_{a}/opendata/calendario_laboral_{a}.json"
URL_AGENDA = "https://api.euskadi.eus/culture/events/v1.0/events/upcoming"
RUTA_FEST = config.DATOS / "festivos_locales.csv"
RUTA_EVP = config.DATOS / "eventos_publicos.csv"
RUTA_AUTO = config.DATOS / "eventos_auto.csv"
TIPOS = {16: "Fiestas", 13: "Festival", 8: "Feria", 1: "Concierto", 10: "Eventos/jornadas"}
# recintos con miles de personas (nivel 2)
MASIVOS = re.compile(r"san mam[eé]s|bilbao arena|bizkaia arena|\bbec\b|kobetamendi|bbk live|aste nagusia|"
                     r"estadio|frontón bizkaia|lezama|ipurua|pabellón", re.I)
# Bilbao tiene servicio propio, pero un evento masivo allí mueve tráfico en los parques de alrededor
ENTORNO_BILBAO = "ARTAZA;URIOSTE;BASAURI;DERIO"


def _get(url, **kw):
    r = requests.get(url, timeout=60, headers={"User-Agent": config.USER_AGENT}, **kw)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ fiestas locales
def festivos_locales(anios=None):
    anios = anios or range(2021, date.today().year + 2)
    filas = []
    for a in anios:
        try:
            j = _get(URL_CAL.format(a=a))
        except Exception as e:
            print(f"Calendario {a}: {e}")
            continue
        for x in j:
            if "bizkaia" not in str(x.get("territory", "")).lower() or x.get("municipalitycode") in (None, ""):
                continue
            ine = "48" + str(int(x["municipalitycode"])).zfill(3)
            y, m, d = [int(v) for v in str(x["date"]).split("/")]
            filas.append({"cod_ine": ine, "fecha": f"{y:04d}-{m:02d}-{d:02d}",
                          "descripcion": str(x.get("descripcionEs", "")).strip()})
    if not filas:
        return pd.read_csv(RUTA_FEST, dtype={"cod_ine": str}) if RUTA_FEST.exists() else pd.DataFrame()
    f = pd.DataFrame(filas).drop_duplicates()
    f.sort_values(["fecha", "cod_ine"]).to_csv(RUTA_FEST, index=False)
    print(f"Fiestas locales de Bizkaia: {len(f)} ({f['fecha'].min()} → {f['fecha'].max()})")
    return f


# ------------------------------------------------------------------ agenda cultural
def _municipios():
    from shapely.geometry import shape
    g = json.loads((config.DATOS / "geo" / "municipios_bizkaia.geojson").read_text(encoding="utf-8"))
    return [(f["properties"]["ine"], shape(f["geometry"])) for f in g["features"]]


def _ine_de_punto(lat, lon, munis):
    from shapely.geometry import Point
    p = Point(lon, lat)
    for ine, geom in munis:
        if geom.contains(p):
            return ine
    return None


def agenda(paginas=120, por_pagina=100):
    filas, p = [], 1
    while p <= paginas:
        try:
            j = _get(URL_AGENDA, params={"_elements": por_pagina, "_page": p})
        except Exception as e:
            print(f"Agenda página {p}: {e}")
            break
        for x in j.get("items", []):
            if str(x.get("provinceNoraCode")) != "48" or int(x.get("type") or 0) not in TIPOS:
                continue
            filas.append({k: x.get(k) for k in ("id", "type", "typeEs", "nameEs", "startDate", "endDate",
                                                 "openingHoursEs", "municipalityEs", "municipalityLatitude",
                                                 "municipalityLongitude", "placeEs")})
        if p >= (j.get("totalPages") or 1):
            break
        p += 1
    nuevos = pd.DataFrame(filas)
    if nuevos.empty:
        return pd.read_csv(RUTA_EVP, dtype=str) if RUTA_EVP.exists() else nuevos
    munis = _municipios()
    nuevos["ine"] = [_ine_de_punto(float(a), float(o), munis) if a and o else None
                     for a, o in zip(nuevos["municipalityLatitude"], nuevos["municipalityLongitude"])]
    nuevos["leido"] = date.today().isoformat()
    previo = pd.read_csv(RUTA_EVP, dtype=str) if RUTA_EVP.exists() else pd.DataFrame()
    todo = pd.concat([previo, nuevos.astype(str)], ignore_index=True).drop_duplicates("id", keep="last")
    todo.to_csv(RUTA_EVP, index=False)
    print(f"Agenda: {len(nuevos)} eventos próximos en Bizkaia · {len(todo)} acumulados")
    return todo


# ------------------------------------------------------------------ eventos para la predicción
def _hora(txt, defecto=18):
    m = re.search(r"(\d{1,2})[:.h](\d{2})?", str(txt or ""))
    return (int(m.group(1)) % 24, int(m.group(2) or 0)) if m else (defecto, 0)


def construir(fest=None, evp=None):
    fest = fest if fest is not None else (pd.read_csv(RUTA_FEST, dtype={"cod_ine": str})
                                          if RUTA_FEST.exists() else pd.DataFrame())
    evp = evp if evp is not None else (pd.read_csv(RUTA_EVP, dtype=str) if RUTA_EVP.exists() else pd.DataFrame())
    hoy = date.today()
    filas = []
    # fiestas locales: desde la víspera por la tarde hasta el final del día
    for r in fest.itertuples() if len(fest) else []:
        d = date.fromisoformat(str(r.fecha)[:10])
        if not (hoy - timedelta(days=2) <= d <= hoy + timedelta(days=30)):
            continue
        p = INE_A_PARQUE.get(str(r.cod_ine))
        if p not in PARQUES:
            continue
        filas.append({"inicio": f"{d - timedelta(days=1)} 18:00", "fin": f"{d} 23:59",
                      "nombre": f"Fiesta local: {r.descripcion}", "nivel": 1, "parques": p})
    for r in evp.itertuples() if len(evp) else []:
        try:
            d0 = date.fromisoformat(str(r.startDate)[:10])
            d1 = date.fromisoformat(str(r.endDate)[:10]) if str(r.endDate) not in ("", "nan", "None") else d0
        except ValueError:
            continue
        if d1 < hoy - timedelta(days=1) or d0 > hoy + timedelta(days=30) or (d1 - d0).days > 10:
            continue                                   # exposiciones y temporadas largas: fuera
        texto = f"{r.nameEs} {r.placeEs}"
        masivo = bool(MASIVOS.search(texto))
        tipo = int(float(r.type))
        if tipo == 1 and not masivo:
            continue                                   # conciertos pequeños: no mueven gente
        nivel = 2 if masivo else 1
        p = INE_A_PARQUE.get(str(r.ine))
        if p not in PARQUES:
            if str(r.ine) == "48020" and nivel == 2:
                p = ENTORNO_BILBAO
            else:
                continue
        hh, mm = _hora(r.openingHoursEs)
        for k in range((d1 - d0).days + 1):
            d = d0 + timedelta(days=k)
            ini = datetime(d.year, d.month, d.day, hh, mm)
            filas.append({"inicio": f"{ini:%Y-%m-%d %H:%M}", "fin": f"{ini + timedelta(hours=4):%Y-%m-%d %H:%M}",
                          "nombre": f"{TIPOS[tipo]}: {str(r.nameEs)[:80]}", "nivel": nivel, "parques": p})
    out = pd.DataFrame(filas, columns=["inicio", "fin", "nombre", "nivel", "parques"]).drop_duplicates()
    out.to_csv(RUTA_AUTO, index=False)
    print(f"Eventos para la predicción (próximos 30 días): {len(out)}")
    return out


def main():
    f = festivos_locales()
    e = agenda()
    construir(f, e)


if __name__ == "__main__":
    main()
