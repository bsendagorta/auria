"""Tasa base de salidas por hora: parque × familia × mes × franja, a partir del histórico abierto.

tasa_hora = salidas / horas expuestas (días del mes × años con datos × horas de la franja)
Es el "lo normal" contra el que se compara el riesgo de cada hora.
Salida: datos/modelo/base_horaria.csv (pequeño, se sube a git)
"""
import calendar

import pandas as pd

from . import config
from .familias import FAMILIAS
from .parques import PARQUES

HORAS_FRANJA = {"M": 6, "T": 6, "N": 12}      # 08-14, 14-20, 20-08


def franja_de_hora(h: int) -> str:
    return "M" if 8 <= h < 14 else ("T" if 14 <= h < 20 else "N")


def construir(df: pd.DataFrame = None, desde: int = 2023) -> pd.DataFrame:
    if df is None:
        df = pd.read_csv(config.PROCESADO / "intervenciones.csv", dtype={"cod_ine": str}, keep_default_na=False)
    d = df[(df["operativa"].astype(str) == "True") & (pd.to_numeric(df["anio"]) >= desde)
           & df["parque"].isin(list(PARQUES)) & df["franja"].isin(list(HORAS_FRANJA))].copy()
    d["anio"] = pd.to_numeric(d["anio"]).astype(int)
    d["mes"] = pd.to_numeric(d["mes"]).astype(int)

    # meses con datos (para no penalizar el año en curso, que está incompleto)
    meses = d[["anio", "mes"]].drop_duplicates()
    dias = meses.assign(dias=[calendar.monthrange(a, m)[1] for a, m in zip(meses["anio"], meses["mes"])])
    dias_por_mes = dias.groupby("mes")["dias"].sum()

    conteo = d.groupby(["parque", "familia", "mes", "franja"]).size().rename("n")
    rejilla = pd.MultiIndex.from_product(
        [list(PARQUES), FAMILIAS, range(1, 13), list(HORAS_FRANJA)],
        names=["parque", "familia", "mes", "franja"]).to_frame(index=False)
    t = rejilla.merge(conteo.reset_index(), how="left").fillna({"n": 0})
    t["horas"] = t["mes"].map(dias_por_mes).fillna(0) * t["franja"].map(HORAS_FRANJA)
    t = t[t["horas"] > 0]
    # suavizado: se mezcla con la media anual de la celda (evita tasas 0 en meses sin casos)
    anual = t.groupby(["parque", "familia", "franja"]).apply(
        lambda g: g["n"].sum() / g["horas"].sum(), include_groups=False).rename("tasa_anual")
    t = t.merge(anual.reset_index(), on=["parque", "familia", "franja"])
    a = 300.0   # horas "ficticias" de la media anual: evita tasas 0 en meses sin casos
    t["tasa_hora"] = (t["n"] + a * t["tasa_anual"]) / (t["horas"] + a)
    out = t[["parque", "familia", "mes", "franja", "n", "horas", "tasa_hora"]]
    out.to_csv(config.DIR_MODELO / "base_horaria.csv", index=False)
    print("\nTasa base: salidas/día medias por parque (todas las familias):")
    pf = out.groupby(["parque", "mes", "franja"])["tasa_hora"].sum().reset_index()
    pf["dia"] = pf["tasa_hora"] * pf["franja"].map(HORAS_FRANJA)
    print(pf.groupby(["parque", "mes"])["dia"].sum().groupby("parque").mean().round(2).to_string())
    return out


def cargar() -> pd.DataFrame:
    return pd.read_csv(config.DIR_MODELO / "base_horaria.csv")


if __name__ == "__main__":
    construir()
