"""Uso en tiempo real de las tablas de accidentes (generadas por auria.accidentes).

- factor(parque, hora)         -> cuánto más (o menos) tráfico-accidente hay a esa hora y tipo de día
                                  respecto a la media de su franja SPEIS (para la familia TRAFICO)
- rr_lluvia(mm_h)              -> riesgo relativo de accidente con lluvia, aprendido de la DGT + Open-Meteo
- carreteras(parque, horas, …) -> tramos de carretera con más probabilidad de accidente con víctimas
Si las tablas no existen, todo devuelve valores neutros (factor 1, sin carreteras).
"""
import json
import math
from functools import lru_cache

import pandas as pd

from . import calendario, config

RUTA_PERFIL = config.DIR_MODELO / "trafico_perfil_horario.csv"
RUTA_TRAMOS = config.DIR_MODELO / "trafico_tramos.csv"
RUTA_FACTORES = config.DIR_MODELO / "trafico_factores.json"


def tipo_dia(ts) -> str:
    """Tipos de la DGT agrupados: LJ (lunes-jueves), V, S, D. Un festivo se trata como domingo."""
    if calendario.es_festivo(ts.date()):
        return "D"
    return {0: "LJ", 1: "LJ", 2: "LJ", 3: "LJ", 4: "V", 5: "S", 6: "D"}[ts.dayofweek]


@lru_cache(maxsize=1)
def _perfil():
    if not RUTA_PERFIL.exists():
        return None
    p = pd.read_csv(RUTA_PERFIL)
    return p.set_index(["parque", "tipo_dia", "hora"])[["factor", "factor_dia"]]


@lru_cache(maxsize=1)
def _factores():
    if not RUTA_FACTORES.exists():
        return {}
    return json.loads(RUTA_FACTORES.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _tramos():
    if not RUTA_TRAMOS.exists():
        return None
    return pd.read_csv(RUTA_TRAMOS)


def disponible() -> bool:
    return _perfil() is not None


def factor(parque, ts):
    """(factor sobre la franja, factor sobre la media semanal) para la familia TRAFICO."""
    p = _perfil()
    if p is None:
        return 1.0, 1.0
    try:
        f = p.loc[(parque, tipo_dia(ts), ts.hour)]
        return float(f["factor"]), float(f["factor_dia"])
    except KeyError:
        return 1.0, 1.0


def rr_lluvia(mm_h: float):
    """Riesgo relativo aprendido; None si no hay tablas (se usan las reglas por defecto)."""
    ll = _factores().get("lluvia", {})
    if not ll.get("rr_lluvia"):
        return None
    if mm_h >= ll.get("umbral_lluvia_fuerte_mm_h", 2.5) and ll.get("rr_lluvia_fuerte"):
        return float(ll["rr_lluvia_fuerte"])
    if mm_h >= ll.get("umbral_lluvia_mm_h", 0.3):
        return float(ll["rr_lluvia"])
    return 1.0


def factor_seco() -> float:
    """Si con lluvia el riesgo sube, sin lluvia baja un poco (para que la media siga siendo 1)."""
    ll = _factores().get("lluvia", {})
    rr, p = ll.get("rr_lluvia"), ll.get("p_horas_lluvia")
    if not rr or not p or p >= 1:
        return 1.0
    return max(0.5, (1 - p * rr) / (1 - p))


def carreteras(parque, horas, lluvias, n=3):
    """Tramos del parque con más probabilidad de accidente con víctimas en las horas dadas.

    λ_tramo = Σ_h  tasa_media_hora_tramo × factor_dia(parque, h) × riesgo_lluvia(h)
    """
    t = _tramos()
    if t is None:
        return []
    t = t[t["parque"] == parque]
    if t.empty:
        return []
    mult = 0.0
    for ts, mm in zip(horas, lluvias):
        rr = rr_lluvia(mm)
        mult += factor(parque, ts)[1] * (rr if rr is not None else 1.0) * (factor_seco() if rr == 1.0 else 1.0)
    t = t.assign(esperados=t["tasa_hora"] * mult)
    t = t.sort_values("esperados", ascending=False).head(n)
    return [{"carretera": r.CARRETERA, "km_ini": int(r.km_ini), "km_fin": int(r.km_fin),
             "esperados": round(float(r.esperados), 4), "prob": round(1 - math.exp(-float(r.esperados)), 4),
             "accidentes_anio": float(r.accidentes_anio), "pct_graves": float(r.pct_graves),
             "hora_pico": int(r.hora_pico),
             "imd": (None if pd.isna(getattr(r, "imd", float("nan"))) else int(r.imd)),
             "ip": (None if pd.isna(getattr(r, "ip", float("nan"))) else float(r.ip))} for r in t.itertuples()]


def resumen():
    f = _factores()
    return {"lluvia": f.get("lluvia", {}), "anios": f.get("anios", [])} if f else {}
