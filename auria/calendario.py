"""Calendario: festivos (España + Euskadi), fines de semana, puentes, vacaciones.

Festivos locales / fiestas patronales: añádelos en datos/festivos_locales.csv
    cod_ine,fecha,descripcion
    48013,2026-07-16,El Carmen (Barakaldo)
"""
from datetime import date, timedelta

import holidays
import pandas as pd

from . import config


def festivos(anios) -> dict:
    f = {}
    for a in anios:
        f.update(holidays.Spain(subdiv="PV", years=a))
    return f


def diario(desde: str, hasta: str) -> pd.DataFrame:
    dias = pd.date_range(desde, hasta, freq="D")
    fest = festivos(sorted(set(dias.year)))
    d = pd.DataFrame({"fecha": dias})
    d["dow"] = d["fecha"].dt.dayofweek
    d["finde"] = d["dow"] >= 5
    d["festivo"] = d["fecha"].dt.date.map(lambda x: x in fest)
    d["no_laborable"] = d["finde"] | d["festivo"]
    nl = set(d.loc[d["no_laborable"], "fecha"].dt.date)
    # puente: laborable entre dos no laborables (p.ej. lunes entre domingo y martes festivo)
    d["puente"] = d["fecha"].dt.date.map(
        lambda x: x not in nl and (x - timedelta(1)) in nl and (x + timedelta(1)) in nl)
    d["vispera_festivo"] = d["fecha"].dt.date.map(lambda x: (x + timedelta(1)) in fest)
    mes, dia = d["fecha"].dt.month, d["fecha"].dt.day
    d["vacaciones_verano"] = (mes == 7) | (mes == 8) | ((mes == 6) & (dia >= 22))
    d["navidad"] = ((mes == 12) & (dia >= 23)) | ((mes == 1) & (dia <= 7))
    return d


def mensual(desde: str, hasta: str) -> pd.DataFrame:
    d = diario(desde, hasta)
    d["anio"], d["mes"] = d["fecha"].dt.year, d["fecha"].dt.month
    g = d.groupby(["anio", "mes"])
    return pd.DataFrame({
        "dias_mes": g.size(),
        "dias_finde": g["finde"].sum(),
        "dias_festivo": g["festivo"].sum(),
        "dias_no_laborables": g["no_laborable"].sum(),
        "dias_puente": g["puente"].sum(),
        "dias_vacaciones_verano": g["vacaciones_verano"].sum(),
        "dias_navidad": g["navidad"].sum(),
    }).reset_index()


def festivos_locales() -> pd.DataFrame:
    p = config.DATOS / "festivos_locales.csv"
    if not p.exists():
        p.write_text("cod_ine,fecha,descripcion\n", encoding="utf-8")
    return pd.read_csv(p, dtype={"cod_ine": str}, parse_dates=["fecha"])


# ------------------------------------------------------------------ variables horarias
_cache = {}


def _no_laborables(anio):
    if anio not in _cache:
        d = diario(f"{anio - 1}-12-01", f"{anio + 1}-01-31")
        _cache[anio] = (set(d.loc[d["festivo"], "fecha"].dt.date), set(d.loc[d["no_laborable"], "fecha"].dt.date))
    return _cache[anio]


def es_festivo(dia) -> bool:
    return dia in _no_laborables(dia.year)[0]


def _bloque(dia):
    """Longitud del bloque de días no laborables que contiene a 'dia' (0 si es laborable)."""
    _, nl = _no_laborables(dia.year)
    if dia not in nl:
        return 0, None, None
    ini = fin = dia
    while ini - timedelta(1) in nl:
        ini -= timedelta(1)
    while fin + timedelta(1) in nl:
        fin += timedelta(1)
    return (fin - ini).days + 1, ini, fin


def variables_hora(ts) -> dict:
    """ts: pandas Timestamp en hora local."""
    dia, h, dow = ts.date(), ts.hour, ts.dayofweek
    festivo = es_festivo(dia)
    noche_finde = (dow == 4 and h >= 22) or (dow == 5 and (h < 7 or h >= 22)) or (dow == 6 and h < 7)
    # operación salida: tarde del laborable anterior a un bloque de ≥3 días; retorno: tarde del último día
    manana = dia + timedelta(1)
    largo_sig, _, _ = _bloque(manana)
    largo, _, fin = _bloque(dia)
    salida = largo == 0 and largo_sig >= 3 and 15 <= h < 22
    retorno = largo >= 3 and fin == dia and 16 <= h < 23
    mes = ts.month
    verano = mes in (7, 8) and ((dia.day <= 2 or dia.day >= 30) and 9 <= h < 21)
    return {"festivo": festivo, "finde": dow >= 5, "noche_finde": noche_finde,
            "operacion_trafico": salida or retorno or verano, "dow": dow}
