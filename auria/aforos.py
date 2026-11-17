"""Intensidad de tráfico real en las carreteras de Bizkaia (aforadores del Gobierno Vasco).

API de tráfico de Open Data Euskadi (sin clave): https://api.euskadi.eus/traffic/v1.0
  meters/byProvince/48                               detectores de Bizkaia (uno por carril y sentido)
  flows/byDate/{a}/{m}/{d}/byMeter/{id}?_page=n      vehículos cada 30 min, velocidad media,
                                                     intervalos de velocidad y de longitud (>7 m = pesados)
Lo que hay (comprobado en nov. 2026):
  * fuente 1 (Gobierno Vasco): A-8, AP-8, AP-68, N-634, N-644, BI-604, BI-625… con flujos 2017-2024.
  * fuente 2 (Diputación de Bizkaia): sin flujos publicados.  Fuente 5 (Ayto. Bilbao): urbano, se excluye.
  Por eso los aforos dan la EXPOSICIÓN histórica (IMD y perfil horario), no el tráfico en directo; el
  estado en directo sigue saliendo de las incidencias (auria.trafico).

Muestra: por cada mes de --desde a --hasta, un martes, un viernes, un sábado y un domingo (2.º de cada).
Salidas:
  datos/aforos/flujos_bizkaia.csv.gz      estación × fecha × hora (vehículos, pesados, velocidad media)
  datos/modelo/aforos_estaciones.csv      IMD, % pesados, velocidad y hora punta por estación
  datos/modelo/aforos_perfil_horario.csv  reparto horario del tráfico por tipo de día
  datos/modelo/trafico_tramos.csv         + imd e índice de peligrosidad (accidentes con víctimas por
                                          100 millones de veh·km) en los tramos con aforo cercano
  datos/modelo/trafico_riesgo_vehiculo.csv  riesgo por vehículo según la hora (accidentes ÷ tráfico)
Uso: python -m auria.aforos [--desde 2022 --hasta 2024]   (en GitHub: workflow "Aforos de tráfico")
"""
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from . import config

BASE = "https://api.euskadi.eus/traffic/v1.0/"
DIR = config.DATOS / "aforos"
RUTA_FLUJOS = DIR / "flujos_bizkaia.csv.gz"
PESO_DIA = {"LJ": 4, "V": 1, "S": 1, "D": 1}          # días de cada tipo en una semana
_S = requests.Session()
_S.headers["User-Agent"] = config.USER_AGENT


def _get(ruta, intentos=4):
    for i in range(intentos):
        try:
            r = _S.get(BASE + ruta, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 * (i + 1))
    return None


def _pk(txt):
    m = re.search(r"pk\s*([\d]+(?:[.,]\d+)?)", txt or "", re.I)
    return float(m.group(1).replace(",", ".")) if m else np.nan


def estaciones() -> pd.DataFrame:
    """Detectores interurbanos de Bizkaia (fuente 1), con carretera, PK y sentido."""
    filas, p = [], 1
    while True:
        j = _get(f"meters/byProvince/48?_page={p}")
        if not j or not j.get("features"):
            break
        filas += [f["properties"] for f in j["features"]]
        if p >= j.get("totalPages", 1):
            break
        p += 1
    m = pd.DataFrame(filas)
    m = m[m["sourceId"] == "1"].copy()
    m["carretera"] = m["etd"].str.extract(r"\[\s*([A-Z]+-\d+)\s*\]")[0]
    m["pk"] = m["etd"].map(_pk)
    m["estacion"] = m["etd"].str.extract(r"\]\s*([\d]+-ETD-\d+[^,]*)")[0].str.strip()
    m["lat"] = pd.to_numeric(m["latitude"], errors="coerce")
    m["lon"] = pd.to_numeric(m["longitude"], errors="coerce")
    return m[["meterId", "carretera", "pk", "estacion", "detector", "municipality", "lat", "lon"]]


def dias(desde, hasta):
    out = []
    for a in range(desde, hasta + 1):
        for mes in range(1, 13):
            d0 = date(a, mes, 1)
            for wd in (1, 4, 5, 6):                          # martes, viernes, sábado, domingo
                d = d0 + timedelta(days=(wd - d0.weekday()) % 7 + 7)
                if d < date.today():
                    out.append(d)
    return out


def _flujos_meter_dia(meter, d):
    filas, p = [], 1
    while True:
        j = _get(f"flows/byDate/{d:%Y/%m/%d}/byMeter/{meter}?_page={p}")
        if not j or not j.get("flows"):
            break
        for f in j["flows"]:
            pes = sum(x["vehicles"] for x in f.get("lengthIntervals", []) if x.get("lengthMin", 0) >= 7)
            filas.append({"meterId": meter, "fecha": d.isoformat(), "hora": int(f["timeRank"][:2]),
                          "vehiculos": float(f["totalVehicles"] or 0), "pesados": pes,
                          "vel": pd.to_numeric(f.get("speedAvg"), errors="coerce")})
        if p >= j.get("totalPages", 1):
            break
        p += 1
    return filas


def descargar(est, desde, hasta, hilos=16):
    DIR.mkdir(parents=True, exist_ok=True)
    previo = pd.read_csv(RUTA_FLUJOS) if RUTA_FLUJOS.exists() else pd.DataFrame(columns=["meterId", "fecha"])
    hechos = set(zip(previo["meterId"].astype(str), previo["fecha"]))
    ds = dias(desde, hasta)
    # primero se mira qué detectores tienen datos (un día por año) para no pedir miles de vacíos
    activos = set()
    with ThreadPoolExecutor(hilos) as ex:
        for a in range(desde, hasta + 1):
            d = next((x for x in ds if x.year == a), None)
            if d is None:
                continue
            res = ex.map(lambda m: (m, _get(f"flows/byDate/{d:%Y/%m/%d}/byMeter/{m}")), est["meterId"])
            activos |= {m for m, j in res if j and j.get("totalItems")}
    print(f"Detectores con datos: {len(activos)} de {len(est)}", flush=True)
    tareas = [(m, d) for d in ds for m in sorted(activos) if (m, d.isoformat()) not in hechos]
    print(f"Peticiones pendientes: {len(tareas)} (detector × día)", flush=True)
    filas = []
    with ThreadPoolExecutor(hilos) as ex:
        for i, r in enumerate(ex.map(lambda t: _flujos_meter_dia(*t), tareas)):
            filas += r
            if i % 500 == 0:
                print(f"  {i}/{len(tareas)}", flush=True)
    nuevo = pd.DataFrame(filas)
    if len(nuevo):
        # media hora -> hora
        g = nuevo.assign(vxv=nuevo["vel"] * nuevo["vehiculos"]).groupby(["meterId", "fecha", "hora"])
        nuevo = g.agg(vehiculos=("vehiculos", "sum"), pesados=("pesados", "sum"), vxv=("vxv", "sum")).reset_index()
        nuevo["vel"] = (nuevo["vxv"] / nuevo["vehiculos"].where(nuevo["vehiculos"] > 0)).round(1)
        nuevo = nuevo.drop(columns="vxv")
    todo = pd.concat([previo, nuevo], ignore_index=True)
    todo["meterId"] = todo["meterId"].astype(str)
    todo = todo.drop_duplicates(["meterId", "fecha", "hora"], keep="last")
    todo.to_csv(RUTA_FLUJOS, index=False, compression="gzip")
    return todo


def tipo_dia(fechas):
    from .riesgo_trafico import tipo_dia as td
    return pd.to_datetime(fechas).map(td)


def analizar(flujos, est):
    f = flujos.merge(est.astype({"meterId": str}), on="meterId")
    f["tipo_dia"] = tipo_dia(f["fecha"])
    # estación = suma de sus carriles y sentidos
    clave = ["carretera", "pk", "estacion"]
    dia = f.groupby(clave + ["fecha", "tipo_dia"]).agg(veh=("vehiculos", "sum"), pes=("pesados", "sum"),
                                                       horas=("hora", "nunique"), n_det=("meterId", "nunique"))
    dia = dia[dia["horas"] >= 20].reset_index()          # días casi completos
    pt = dia.groupby(clave + ["tipo_dia"])["veh"].median().unstack()
    w = pd.Series(PESO_DIA)
    pt = pt.T.fillna(pt.mean(axis=1)).T.reindex(columns=list(PESO_DIA))
    pt = pt.T.fillna(pt.mean(axis=1)).T
    imd = (pt * w).sum(axis=1) / w.sum()
    pes = dia.groupby(clave).apply(lambda x: x["pes"].sum() / max(x["veh"].sum(), 1), include_groups=False)
    fv = f.dropna(subset=["vel"])
    vel = fv.groupby(clave).apply(lambda x: np.average(x["vel"], weights=x["vehiculos"] + 1e-9),
                                  include_groups=False)
    hp = f[f["tipo_dia"] == "LJ"].groupby(clave + ["hora"])["vehiculos"].sum().groupby(level=clave).idxmax()
    pos = est.groupby(clave)[["lat", "lon"]].mean()
    e = pd.DataFrame({"imd": imd.round(0), "pct_pesados": (100 * pes).round(1), "vel_media": vel.round(0)})
    e["hora_punta"] = hp.map(lambda t: t[-1])
    e = e.join(pos).reset_index()
    e["dias_medidos"] = e.set_index(clave).index.map(dia.groupby(clave).size())
    e = e[e["imd"] > 0].sort_values("imd", ascending=False)

    # perfil horario del tráfico por tipo de día (Bizkaia), 1 = hora media del tipo de día
    ph = f.groupby(["tipo_dia", "hora"])["vehiculos"].sum()
    ph = ph / ph.groupby(level=0).transform("mean")
    perfil = ph.rename("factor_trafico").round(4).reset_index()
    return e, perfil


def tramos_con_imd(e):
    """IMD del aforo más cercano (misma carretera, ≤ 6 km) e índice de peligrosidad del tramo."""
    p = config.DIR_MODELO / "trafico_tramos.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p).drop(columns=["imd", "aforo", "ip", "dist_aforo_km"], errors="ignore")
    anios = json.loads((config.DIR_MODELO / "trafico_factores.json").read_text()).get("anios", [])
    n_anios = len(anios) or 7
    imd, af, dist = [], [], []
    for r in t.itertuples():
        c = e[e["carretera"] == r.CARRETERA]
        mid = (r.km_ini + r.km_fin) / 2
        if c.empty or c["pk"].isna().all():
            imd.append(np.nan); af.append(""); dist.append(np.nan)
            continue
        d = (c["pk"] - mid).abs()
        k = d.idxmin()
        ok = d[k] <= 6
        imd.append(c.at[k, "imd"] if ok else np.nan)
        af.append(c.at[k, "estacion"] if ok else "")
        dist.append(round(float(d[k]), 1) if ok else np.nan)
    t["imd"], t["aforo"], t["dist_aforo_km"] = imd, af, dist
    longitud = (t["km_fin"] - t["km_ini"]).clip(lower=1)
    vehkm = t["imd"] * 365 * longitud
    t["ip"] = (t["accidentes"] / n_anios / vehkm * 1e8).round(1)   # acc. con víctimas / 100 M veh·km
    t.to_csv(p, index=False)
    return t


def riesgo_por_vehiculo(perfil):
    """Accidentes por hora (DGT) ÷ tráfico por hora (aforos): cuánto más peligroso es cada vehículo."""
    p = config.DIR_MODELO / "trafico_perfil_horario.csv"
    if not p.exists():
        return None
    a = pd.read_csv(p)
    w = a.groupby(["tipo_dia", "hora"]).apply(lambda x: np.average(x["factor_dia"], weights=x["n"]),
                                              include_groups=False).rename("factor_accidentes").reset_index()
    r = w.merge(perfil, on=["tipo_dia", "hora"])
    r["riesgo_por_vehiculo"] = (r["factor_accidentes"] / r["factor_trafico"].clip(lower=0.05)).round(3)
    # normalizado: 1 = riesgo medio por vehículo del tipo de día
    r["riesgo_por_vehiculo"] = (r["riesgo_por_vehiculo"] /
                                r.groupby("tipo_dia")["riesgo_por_vehiculo"].transform("mean")).round(3)
    r.to_csv(config.DIR_MODELO / "trafico_riesgo_vehiculo.csv", index=False)
    return r


def informe(e, t, r):
    L = ["# AURIA — Intensidad de tráfico (aforos Gobierno Vasco, Bizkaia)", f"Generado {date.today()}", "",
         "## Estaciones de aforo (IMD = vehículos/día, media semanal)",
         e.drop(columns=["lat", "lon"]).head(40).to_markdown(index=False)]
    if t is not None:
        c = t.dropna(subset=["ip"]).sort_values("ip", ascending=False)
        L += ["", "## Tramos con aforo: índice de peligrosidad",
              "IP = accidentes con víctimas por cada 100 millones de vehículos·km (más alto = más peligroso por "
              "vehículo, no solo por cantidad de tráfico).",
              c[["CARRETERA", "km_ini", "km_fin", "parque", "accidentes_anio", "imd", "aforo", "ip"]]
              .head(30).to_markdown(index=False)]
    if r is not None:
        x = r.pivot(index="hora", columns="tipo_dia", values="riesgo_por_vehiculo")
        L += ["", "## Riesgo por vehículo según la hora (1 = media del tipo de día)",
              "Accidentes (DGT) ÷ tráfico (aforos). Las madrugadas tienen poco tráfico pero mucho riesgo por coche.",
              x.to_markdown()]
    (config.INFORMES / "aforos_trafico.md").write_text("\n".join(L), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=2022)
    ap.add_argument("--hasta", type=int, default=2024)
    ap.add_argument("--offline", action="store_true", help="no descargar: recalcular con lo guardado")
    a = ap.parse_args(argv)
    est = estaciones() if not a.offline else pd.read_csv(DIR / "estaciones.csv", dtype={"meterId": str})
    DIR.mkdir(parents=True, exist_ok=True)
    est.to_csv(DIR / "estaciones.csv", index=False)
    flujos = descargar(est, a.desde, a.hasta) if not a.offline else pd.read_csv(RUTA_FLUJOS, dtype={"meterId": str})
    print(f"Flujos: {len(flujos):,} filas (detector × hora)")
    e, perfil = analizar(flujos, est)
    e.to_csv(config.DIR_MODELO / "aforos_estaciones.csv", index=False)
    perfil.to_csv(config.DIR_MODELO / "aforos_perfil_horario.csv", index=False)
    t = tramos_con_imd(e)
    r = riesgo_por_vehiculo(perfil)
    informe(e, t, r)
    print(e.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
