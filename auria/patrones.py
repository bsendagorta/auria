"""Patrones reales de las intervenciones SPEIS 2021-2026 (Open Data Bizkaia).

El histórico abierto da año, mes y franja (M 08-14, T 14-20, N 20-08), sin día. Con eso se miden:
  * estacionalidad: índice por mes y familia (1 = mes medio)
  * franja: intervenciones por hora en mañana / tarde / noche
  * tendencia: total anual por familia (2026 se proyecta a año completo)
  * meteorología mensual (si existe meteo_mensual.csv): cuánto más hay en los meses más lluviosos,
    ventosos, cálidos o fríos que en los más tranquilos (tercil alto vs tercil bajo, misma estación)
  * calendario: los festivos y puentes no se pueden medir sin día; el contraste festivo/laborable sale de
    las capturas por minuto (auria.evaluacion) y del perfil horario DGT.

Uso: python -m auria.patrones   ->  datos/modelo/patrones.json + informes/patrones.md
"""
import json
from datetime import date

import numpy as np
import pandas as pd

from . import config
from .base_horaria import HORAS_FRANJA

ETIQ = {
    "INCENDIO_URBANO": "Incendio urbano", "INCENDIO_INDUSTRIAL": "Incendio industrial",
    "INCENDIO_FORESTAL_EXTERIOR": "Incendio forestal/exterior", "TRAFICO": "Tráfico",
    "RESCATE_SALVAMENTO": "Rescate y salvamento", "METEO_ASISTENCIA": "Meteo (árboles, agua, viento)",
    "ABEJAS_AVISPAS": "Abejas y avispas", "GAS_MMPP": "Gas y mercancías peligrosas",
    "OTRAS_ASISTENCIAS": "Otras asistencias", "OTROS": "Otros",
}
METEO = {"lluvia_total": "lluvia", "dias_racha_60": "días de racha ≥60 km/h",
         "tmax_media": "temperatura máxima", "dias_helada": "días de helada",
         "dias_riesgo_incendio": "días secos y cálidos"}


def cargar():
    d = pd.read_csv(config.PROCESADO / "intervenciones.csv", dtype={"cod_ine": str}, low_memory=False)
    d = d[d["operativa"].astype(str) == "True"]
    return d[d["familia"].isin(ETIQ)]


def estacionalidad(d):
    c = d[d["anio"] < date.today().year].groupby(["familia", "anio", "mes"]).size().unstack(fill_value=0)
    m = c.groupby(level="familia").mean()
    return m.div(m.mean(axis=1), axis=0)


def franjas(d):
    c = d.groupby(["familia", "franja"]).size().unstack(fill_value=0)
    por_h = c / pd.Series(HORAS_FRANJA)
    return por_h.div(por_h.mean(axis=1), axis=0)[["M", "T", "N"]]


def tendencia(d):
    t = d.groupby(["familia", "anio"]).size().unstack(fill_value=0).astype(float)
    hoy = date.today()
    ultimo = int(d["anio"].max())
    meses = d.loc[d["anio"] == ultimo, "mes"].max()
    if ultimo == hoy.year and meses < 12:
        # proyecta con la estacionalidad: fracción del año que suelen sumar esos meses
        e = estacionalidad(d)
        frac = e.loc[:, 1:meses].sum(axis=1) / 12
        t[f"{ultimo} (proy.)"] = (t[ultimo] / frac.reindex(t.index).clip(lower=0.05)).round(0)
        t = t.drop(columns=ultimo)
    return t


def meteo(d):
    p = config.PROCESADO / "meteo_mensual.csv"
    if not p.exists():
        return None
    m = pd.read_csv(p, dtype={"cod_ine": str}).groupby(["anio", "mes"]).mean(numeric_only=True)
    c = d.groupby(["familia", "anio", "mes"]).size().unstack("familia", fill_value=0)
    t = c.join(m, how="inner")
    if len(t) < 18:
        return None
    t = t.reset_index()
    t["estacion"] = (t["mes"] % 12) // 3
    out = {}
    for var in METEO:
        if var not in t:
            continue
        fila = {}
        for f in ETIQ:
            if f not in t:
                continue
            r = []
            for _, g in t.groupby("estacion"):       # compara meses de la misma estación
                if len(g) < 6 or g[var].nunique() < 3:
                    continue
                lo, hi = g[var].quantile([1 / 3, 2 / 3])
                a, b = g.loc[g[var] >= hi, f].mean(), g.loc[g[var] <= lo, f].mean()
                if b > 0:
                    r.append(a / b)
            if r:
                fila[f] = round(float(np.exp(np.mean(np.log(r)))), 2)
        out[var] = fila
    return out


def calcular(guardar=True):
    d = cargar()
    est, fr, ten, met = estacionalidad(d), franjas(d), tendencia(d), meteo(d)
    meta = {
        "fecha": date.today().isoformat(),
        "intervenciones": int(len(d)),
        "anios": sorted(int(a) for a in d["anio"].unique()),
        "nota": ("Histórico sin día exacto: festivos y meteo del día se miden con las capturas por minuto."),
    }
    res = {
        **meta, "etiquetas": ETIQ, "meteo_etiquetas": METEO,
        "estacionalidad": {f: {int(k): round(float(v), 2) for k, v in r.items()} for f, r in est.iterrows()},
        "franja": {f: {k: round(float(v), 2) for k, v in r.items()} for f, r in fr.iterrows()},
        "tendencia": {f: {str(k): float(v) for k, v in r.items()} for f, r in ten.iterrows()},
        "meteo": met,
    }
    if guardar:
        (config.DIR_MODELO / "patrones.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
        informe(res, est, fr, ten)
    return res


def informe(res, est, fr, ten):
    meses = "E F M A M J J A S O N D".split()
    L = [f"# AURIA — Patrones reales SPEIS ({res['anios'][0]}-{res['anios'][-1]})",
         f"Generado {res['fecha']} · {res['intervenciones']:,} intervenciones operativas (sin Bilbao).", "",
         "## Estacionalidad (1 = mes medio)"]
    e = est.rename(index=ETIQ).round(2)
    e.columns = meses
    L += [e.to_markdown(), "", "## Intervenciones por hora según franja (1 = media)",
          fr.rename(index=ETIQ).rename(columns={"M": "Mañana 08-14", "T": "Tarde 14-20", "N": "Noche 20-08"})
          .round(2).to_markdown(), "", "## Total anual por familia", ten.rename(index=ETIQ).astype(int).to_markdown()]
    if res["meteo"]:
        L += ["", "## Meteorología del mes (tercil alto ÷ tercil bajo, misma estación)",
              "Ej.: 1.40 = en los meses más lluviosos hay un 40 % más de esa familia que en los más secos."]
        t = pd.DataFrame(res["meteo"]).rename(index=ETIQ, columns=METEO)
        L += [t.to_markdown()]
    else:
        L += ["", "_Meteorología mensual pendiente (la descarga de Open-Meteo se hace en el reentreno nocturno)._"]
    L += ["", f"_{res['nota']}_"]
    (config.INFORMES / "patrones.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    r = calcular()
    print(open(config.INFORMES / "patrones.md", encoding="utf-8").read())
