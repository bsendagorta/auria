"""Incidencias de tráfico de Open Data Euskadi (sin API key), resumidas por parque.

Tipos que aparecen: Accidente, Obra/Obras, Mantenimiento, Seguridad vial (avería, caída de objetos,
desprendimiento), Puertos de montaña, Vialidad invernal, Evento, Retención...
"""
from datetime import date

import pandas as pd
import requests

from . import config
from .familias import normaliza
from .parques import PARQUES, parque_mas_cercano


def descargar(dia: date = None, max_paginas: int = 40) -> pd.DataFrame:
    dia = dia or date.today()
    url = config.TRAFICO_INCIDENCIAS.format(y=dia.year, m=dia.month, d=dia.day)
    filas, pagina = [], 1
    while pagina <= max_paginas:
        r = requests.get(url, params={"_page": pagina}, timeout=30, headers={"User-Agent": config.USER_AGENT})
        r.raise_for_status()
        j = r.json()
        filas += j.get("incidences", [])
        if pagina >= int(j.get("totalPages", 1)):
            break
        pagina += 1
    return pd.DataFrame(filas)


def por_parque(df: pd.DataFrame) -> pd.DataFrame:
    """Nº de incidencias activas en Bizkaia por parque y categoría."""
    cols = ["accidentes", "retenciones", "obras", "seguridad_vial", "puertos_cerrados"]
    vacio = pd.DataFrame(0, index=list(PARQUES), columns=cols)
    if df.empty:
        return vacio
    d = df[df["province"].map(normaliza).str.contains("BIZKAIA", na=False)].copy()
    d["lat"] = pd.to_numeric(d["latitude"], errors="coerce")
    d["lon"] = pd.to_numeric(d["longitude"], errors="coerce")
    d = d[(d["lat"] > 42.9) & (d["lat"] < 43.5) & (d["lon"] < -2.3) & (d["lon"] > -3.5)]
    if d.empty:
        return vacio
    d["parque"] = [parque_mas_cercano(a, b) for a, b in zip(d["lat"], d["lon"])]
    tipo = (d["incidenceType"].map(normaliza) + " " + d["cause"].map(normaliza))
    nivel = d.get("incidenceLevel", pd.Series("", index=d.index)).fillna("").map(normaliza)
    d["accidentes"] = tipo.str.contains("ACCIDENTE")
    d["retenciones"] = tipo.str.contains("RETENCION|CONGESTION|LENTA")
    d["obras"] = tipo.str.contains("OBRA|MANTENIMIENTO")
    d["seguridad_vial"] = tipo.str.contains("SEGURIDAD VIAL|DESPRENDIMIENTO|CAIDA DE OBJETOS|AVERIA")
    d["puertos_cerrados"] = tipo.str.contains("PUERTOS") & nivel.str.contains("CERRADO|CADENAS|C: CON")
    out = d.groupby("parque")[cols].sum().reindex(list(PARQUES), fill_value=0).astype(int)
    return out


def resumen_hoy() -> pd.DataFrame:
    try:
        return por_parque(descargar())
    except Exception as e:      # el tráfico es un complemento: si falla, se sigue sin él
        print(f"Aviso tráfico: {e}")
        return None
