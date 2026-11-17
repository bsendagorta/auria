"""Estaciones meteorológicas de Euskalmet: lo que MIDEN (no lo que prevé un modelo).

API (con la clave de auria.euskalmet):
  /euskalmet/stations                                  lista (una entrada por versión de cada estación)
  /euskalmet/stations/{id}/{fecha}                     ficha: nombre, provincia, posición, sensores
  /euskalmet/readings/aggregated/byDay/forStation/{id}/at/{a}/{m}/{d}
        todas las medidas del día, en tramos de 10 min (24 lecturas horarias × 6 valores)
Para cada parque se usa la estación de Bizkaia más cercana que mide lluvia y viento (y otra de reserva).
Salidas:
  datos/meteo/estaciones_euskalmet.csv            catálogo (Bizkaia), con parque asignado y distancia
  datos/meteo/estaciones_horaria.csv.gz           histórico horario por parque desde 2021 (incremental)
  datos/online/<origen>/estaciones_AAAA-MM.csv    lecturas en directo (último día) por parque y hora
Uso: python -m auria.estaciones [--catalogo] [--historico --desde 2021-01-01] [--directo]
"""
import argparse
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import config, euskalmet
from .parques import PARQUES

DIR = config.DATOS / "meteo"
RUTA_CAT = DIR / "estaciones_euskalmet.csv"
RUTA_HIST = DIR / "estaciones_horaria.csv.gz"
# medidas que interesan -> nombre en AURIA y cómo se agregan los 6 tramos de 10 min de cada hora
MEDIDAS = {"precipitation": ("lluvia_obs", "sum"), "temperature": ("temp_obs", "mean"),
           "humidity": ("humedad_obs", "mean"), "mean_speed": ("viento_obs", "mean"),
           "max_speed": ("racha_obs", "max"), "mean_direction": ("dir_obs", "circ")}


def _dist_km(a, b, c, d):
    return math.hypot((a - c) * 111.0, (b - d) * 111.0 * math.cos(math.radians(43.2)))


def catalogo():
    lista = euskalmet.get("/euskalmet/stations")
    ultima = {}
    for s in lista:
        ultima[s["stationId"]] = s["key"]          # vienen ordenadas: la última versión gana
    fichas = []

    def ficha(k):
        try:
            return euskalmet.get("/" + k)
        except Exception:
            return None
    with ThreadPoolExecutor(8) as ex:
        for f in ex.map(ficha, ultima.values()):
            if not f:
                continue
            prov = (f.get("province") or {}).get("SPANISH", "")
            pos = ((f.get("position") or {}).get("position") or {}).get("GOOGLE") or {}
            if "Bizkaia" not in prov and "Vizcaya" not in prov:
                continue
            fichas.append({"estacion": f["stationId"], "nombre": (f.get("name") or {}).get("SPANISH", ""),
                           "municipio": (f.get("municipality") or {}).get("SPANISH", ""), "tipo": f.get("stationType"),
                           "altitud": f.get("altitude"), "lat": pos.get("y"), "lon": pos.get("x")})
    cat = pd.DataFrame(fichas).dropna(subset=["lat", "lon"])
    cat = cat[cat["tipo"] == "METEOROLOGICAL"]
    # ¿qué mide cada una? (un día reciente)
    ayer = date.today() - timedelta(days=1)

    def medidas(e):
        try:
            d = euskalmet.get(f"/euskalmet/readings/aggregated/byDay/forStation/{e}/at/{ayer:%Y/%m/%d}")
            return e, sorted({i["measureId"] for i in d.get("items", [])})
        except Exception:
            return e, []
    with ThreadPoolExecutor(8) as ex:
        mide = dict(ex.map(medidas, cat["estacion"]))
    cat["medidas"] = cat["estacion"].map(lambda e: ",".join(mide.get(e, [])))
    cat["lluvia"] = cat["medidas"].str.contains("precipitation")
    cat["viento"] = cat["medidas"].str.contains("max_speed")
    # estación principal y de reserva por parque (las más cercanas que miden lluvia y viento; altitud < 700 m)
    filas = []
    for p, info in PARQUES.items():
        c = cat[cat["lluvia"] & cat["viento"] & (pd.to_numeric(cat["altitud"], errors="coerce").fillna(0) < 700)].copy()
        c["dist_km"] = [_dist_km(a, b, info["lat"], info["lon"]) for a, b in zip(c["lat"], c["lon"])]
        for orden, r in enumerate(c.nsmallest(2, "dist_km").itertuples()):
            filas.append({"parque": p, "orden": orden, "estacion": r.estacion, "dist_km": round(r.dist_km, 1)})
    asig = pd.DataFrame(filas)
    cat = cat.merge(asig, on="estacion", how="left")
    DIR.mkdir(parents=True, exist_ok=True)
    cat.to_csv(RUTA_CAT, index=False)
    print(asig.merge(cat[["estacion", "nombre"]].drop_duplicates(), on="estacion").to_string(index=False))
    return cat


def _circ(v):
    v = [x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return np.nan
    s, c = sum(math.sin(math.radians(x)) for x in v), sum(math.cos(math.radians(x)) for x in v)
    return round(math.degrees(math.atan2(s, c)) % 360, 0)


def dia(estacion, d):
    """Tabla horaria (24 filas) de una estación y un día."""
    j = euskalmet.get(f"/euskalmet/readings/aggregated/byDay/forStation/{estacion}/at/{d:%Y/%m/%d}")
    out = {}
    for it in j.get("items", []):
        m = it.get("measureId")
        if m not in MEDIDAS:
            continue
        nombre, agg = MEDIDAS[m]
        for r in it.get("readings", []):
            h = int(r["oid"].rsplit("/", 1)[-1])
            v = [x for x in (r.get("values") or []) if x is not None]
            if not v:
                continue
            val = {"sum": sum(v), "mean": sum(v) / len(v), "max": max(v), "circ": _circ(v)}[agg]
            # si un sensor está duplicado (dos alturas), se queda el primero
            out.setdefault(h, {}).setdefault(nombre, round(float(val), 2))
    if not out:
        return pd.DataFrame()
    t = pd.DataFrame.from_dict(out, orient="index").sort_index()
    t.index = [pd.Timestamp(d) + pd.Timedelta(hours=int(h)) for h in t.index]
    t.index.name = "hora"
    return t.reset_index().assign(estacion=estacion)


def _asignacion():
    cat = pd.read_csv(RUTA_CAT)
    return cat.dropna(subset=["parque"]).sort_values(["parque", "orden"])


def _por_parque(lect):
    """Combina principal y reserva: la principal manda; los huecos se rellenan con la de reserva."""
    a = _asignacion()
    filas = []
    for p, g in a.groupby("parque"):
        est = g.sort_values("orden")["estacion"].tolist()
        partes = [lect[lect["estacion"] == e].set_index("hora").drop(columns="estacion") for e in est]
        partes = [x for x in partes if len(x)]
        if not partes:
            continue
        t = partes[0]
        for x in partes[1:]:
            t = t.combine_first(x)
        filas.append(t.assign(parque=p, estacion=est[0]).reset_index())
    return pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()


def historico(desde="2021-01-01", hilos=8):
    a = _asignacion()
    estaciones = sorted(set(a["estacion"]))
    previo = pd.read_csv(RUTA_HIST, parse_dates=["hora"]) if RUTA_HIST.exists() else pd.DataFrame()
    hechos = set()
    if len(previo):
        hechos = set(zip(previo["estacion"], previo["hora"].dt.date.astype(str)))
    d0, d1 = date.fromisoformat(desde), date.today() - timedelta(days=1)
    tareas = [(e, d0 + timedelta(days=i)) for i in range((d1 - d0).days + 1) for e in estaciones]
    tareas = [(e, d) for e, d in tareas if (e, d.isoformat()) not in hechos]
    print(f"Peticiones: {len(tareas)} (estación × día)", flush=True)

    def uno(t):
        for k in range(3):
            try:
                return dia(*t)
            except Exception:
                time.sleep(2 * (k + 1))
        return pd.DataFrame()
    nuevos = []
    t0 = time.time()
    with ThreadPoolExecutor(hilos) as ex:
        for i, r in enumerate(ex.map(uno, tareas)):
            if len(r):
                nuevos.append(r)
            if i % 1000 == 0:
                print(f"  {i}/{len(tareas)} · {time.time() - t0:.0f} s", flush=True)
            if time.time() - t0 > 100 * 60:                     # deja margen al workflow; sigue mañana
                print("  corte por tiempo: se continúa en la próxima ejecución", flush=True)
                break
    todo = pd.concat([previo] + nuevos, ignore_index=True) if nuevos else previo
    todo = todo.drop_duplicates(["estacion", "hora"]).sort_values(["estacion", "hora"])
    todo.to_csv(RUTA_HIST, index=False, compression="gzip")
    print(f"Histórico: {len(todo):,} horas-estación ({todo['hora'].min()} → {todo['hora'].max()})")
    return todo


def horaria_parques():
    """Histórico horario observado por parque (principal + reserva)."""
    if not RUTA_HIST.exists():
        return pd.DataFrame()
    return _por_parque(pd.read_csv(RUTA_HIST, parse_dates=["hora"]))


def directo(carpeta=None):
    """Lecturas de hoy y ayer de las estaciones asignadas, por parque y hora (para corregir la previsión)."""
    if not euskalmet.disponible() or not RUTA_CAT.exists():
        return pd.DataFrame()
    a = _asignacion()
    hoy = date.today()
    partes = []
    for e in sorted(set(a["estacion"])):
        for d in (hoy - timedelta(days=1), hoy):
            try:
                partes.append(dia(e, d))
            except Exception as ex:
                print(f"Aviso estación {e} {d}: {ex}", flush=True)
    lect = pd.concat([x for x in partes if len(x)], ignore_index=True) if partes else pd.DataFrame()
    if lect.empty:
        return lect
    t = _por_parque(lect)
    if carpeta is not None or True:
        from .recolector_online import carpeta_origen
        d = carpeta or carpeta_origen()
        d.mkdir(parents=True, exist_ok=True)
        ruta = d / f"estaciones_{datetime.now():%Y-%m}.csv"
        t.assign(leido=datetime.now().isoformat(timespec="minutes")).to_csv(
            ruta, mode="a", header=not ruta.exists(), index=False)
    (config.DIR_PREDICCION / "estaciones_ultimo.csv").write_text(t.to_csv(index=False), encoding="utf-8")
    return t


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalogo", action="store_true")
    ap.add_argument("--historico", action="store_true")
    ap.add_argument("--desde", default="2021-01-01")
    ap.add_argument("--directo", action="store_true")
    a = ap.parse_args(argv)
    if a.catalogo or not RUTA_CAT.exists():
        catalogo()
    if a.historico:
        h = historico(a.desde)
        if len(h):
            print(h.describe(percentiles=[.5, .99]).round(1).to_string())
    if a.directo:
        print(directo().tail(20).to_string())


if __name__ == "__main__":
    main()
