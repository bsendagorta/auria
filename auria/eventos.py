"""Eventos masivos (manual): datos/eventos.csv

Columnas: inicio, fin, nombre, nivel, parques
  inicio/fin : 'AAAA-MM-DD HH:MM' hora local
  nivel      : 1 = medio (Bilbao Arena, BEC, concierto)  2 = masivo (San Mamés, Aste Nagusia, BBK Live)
  parques    : lista separada por ';' (URIOSTE;ARTAZA) o TODOS
Se considera activo desde 3 h antes del inicio hasta 3 h después del fin (llegadas y salidas).
"""
import pandas as pd

from . import config

RUTA = config.DATOS / "eventos.csv"
PLANTILLA = """inicio,fin,nombre,nivel,parques
# Ejemplo (las líneas con # se ignoran):
# 2026-11-29 18:30,2026-11-29 20:30,Athletic - partido en San Mamés,2,URIOSTE;ARTAZA;BASAURI;DERIO
"""


def cargar() -> pd.DataFrame:
    if not RUTA.exists():
        RUTA.write_text(PLANTILLA, encoding="utf-8")
    try:
        e = pd.read_csv(RUTA, comment="#", skipinitialspace=True)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=["inicio", "fin", "nombre", "nivel", "parques"])
    if e.empty:
        return e
    e["inicio"] = pd.to_datetime(e["inicio"])
    e["fin"] = pd.to_datetime(e["fin"])
    e["nivel"] = pd.to_numeric(e["nivel"], errors="coerce").fillna(1).astype(int)
    return e


def en_hora(eventos: pd.DataFrame, parque: str, hora: pd.Timestamp):
    """Devuelve (nivel máximo, horas hasta el inicio, nombre) del evento que afecta a esa hora."""
    if eventos is None or eventos.empty:
        return 0, None, ""
    mejor = (0, None, "")
    for _, e in eventos.iterrows():
        ps = str(e["parques"]).upper()
        if ps != "TODOS" and parque not in [p.strip() for p in ps.split(";")]:
            continue
        if e["inicio"] - pd.Timedelta(hours=3) <= hora <= e["fin"] + pd.Timedelta(hours=3):
            if e["nivel"] > mejor[0]:
                mejor = (int(e["nivel"]), int((e["inicio"] - hora).total_seconds() // 3600), e["nombre"])
    return mejor


