"""Descarga y limpieza del histórico de intervenciones del SPEIS (Open Data Bizkaia).

Uso:
    python -m auria.historico            # descarga + procesa
    python -m auria.historico --offline  # solo procesa lo ya descargado en datos/crudo

Salida: datos/procesado/intervenciones.csv  (una fila por intervención)
        datos/procesado/municipios.csv      (centroides lat/lon por municipio)

Limitación de la fuente: solo trae AÑO + MES + FRANJA HORARIA (3 franjas), no el día.
"""
import argparse
import io
import re
import sys

import pandas as pd
import requests

from . import config
from .familias import ESTADOS_NO_OPERATIVOS, NO_OPERATIVO, familia, normaliza
from .geo import utm_a_latlon
from .parques import SIN_PARQUE, parque_de_ine, parque_mas_cercano

FRANJAS = {
    "ENTRE 08:00 Y 13:59": "M",   # mañana
    "ENTRE 14:00 Y 19:59": "T",   # tarde
    "ENTRE 20:00 Y 07:59": "N",   # noche
}


def descargar():
    for nombre, recurso in config.RECURSOS_HISTORICO.items():
        url = f"{config.OPENDATA_BASE}/{recurso}?format=csv"
        print(f"Descargando {nombre} ...", flush=True)
        r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=120)
        r.raise_for_status()
        (config.CRUDO / f"intervenciones_{nombre}.csv").write_bytes(r.content)
        print(f"  {len(r.content)/1e6:.1f} MB")


def _num_es(v):
    """'500707,5' -> 500707.5 ; '' -> NaN"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return float("nan")
    s = str(v).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _columnas_estandar(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra por la parte en castellano tras '/', p.ej. 'DEIAREN HILABETE/MES AVISO' -> MES_AVISO."""
    nuevas = {}
    for c in df.columns:
        base = c.split("/")[-1].strip().upper().replace(" ", "_")
        nuevas[c] = base
    df = df.rename(columns=nuevas)
    alias = {
        "TIPO_SINIESTRO": "TIPO",
        "TIPO_INTERVENCION": "TIPO",
        "COD_MUNICIPIO": "COD_INE",
        "CODIGO_INE_MUNICIPIO": "COD_INE",
        "SIN_INTERVENCION": "ESTADO",
        "ESTADO_INTERVENCION": "ESTADO",
        "LUGAR_DE_SINIESTRO": "LUGAR_OTRO",
        "LUGAR_DISTINTO_DE_MUNIC_BIZKAIA": "LUGAR_OTRO",
    }
    return df.rename(columns={k: v for k, v in alias.items() if k in df.columns})


def _cod_ine(v):
    s = str(v or "").strip()
    if not s or s.upper() == "NAN":
        return ""
    s = s.lstrip("=")
    s = re.sub(r"\.0$", "", s)
    if len(s) == 3:          # formato 2021-22: '=044' -> 48044
        s = "48" + s
    return s


def leer_crudo(path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df = _columnas_estandar(df)
    # 2022 publica extracciones trimestrales acumuladas en el mismo fichero: nos quedamos con la última
    if "FECHA_EXTRACCION" in df.columns and df["FECHA_EXTRACCION"].nunique() > 1:
        df = df[df["FECHA_EXTRACCION"] == df["FECHA_EXTRACCION"].max()]
    return df


def procesar(rutas) -> pd.DataFrame:
    partes = [leer_crudo(p) for p in rutas]
    df = pd.concat(partes, ignore_index=True, sort=False)

    out = pd.DataFrame({
        "anio": pd.to_numeric(df["EJERCICIO"], errors="coerce").astype("Int64"),
        "mes": pd.to_numeric(df["MES_AVISO"], errors="coerce").astype("Int64"),
        "franja": df["FRANJA_HORARIA"].map(lambda s: FRANJAS.get(normaliza(s), "")),
        "origen": df.get("ORIGEN_AVISO", "").map(normaliza),
        "tipo": df["TIPO"].map(normaliza),
        "nivel": pd.to_numeric(df.get("NIVEL_SINIESTRO"), errors="coerce"),
        "cod_ine": df["COD_INE"].map(_cod_ine),
        "municipio": df["MUNICIPIO"].map(normaliza),
        "lugar_otro": df.get("LUGAR_OTRO", "").map(normaliza),
        "estado": df["ESTADO"].map(normaliza),
        "recursos": pd.to_numeric(df.get("RECURSOS_MOVILIZADOS"), errors="coerce"),
        "heridos": pd.to_numeric(df.get("PERSONAS_HERIDAS"), errors="coerce"),
        "fallecidos": pd.to_numeric(df.get("PERSONAS_FALLECIDAS"), errors="coerce"),
        "utm_x": df.get("LONGITUDE", pd.Series([""] * len(df))).map(_num_es),
        "utm_y": df.get("LATITUDE", pd.Series([""] * len(df))).map(_num_es),
    })

    out["familia"] = out["tipo"].map(familia)
    # En 2021-22 las avispas iban dentro de "AUXILIARES (I)": las recuperamos por el origen del aviso
    out.loc[out["origen"].str.contains("VESPA", na=False) & (out["familia"] == "METEO_ASISTENCIA"),
            "familia"] = "ABEJAS_AVISPAS"
    out["operativa"] = (out["familia"] != NO_OPERATIVO) & ~out["estado"].isin(ESTADOS_NO_OPERATIVOS)
    out["falsa_alarma"] = out["estado"].str.contains("FALSA ALARMA", na=False)

    ok = out["utm_x"].between(400000, 700000) & out["utm_y"].between(4700000, 4900000)
    latlon = [utm_a_latlon(x, y) if v else (float("nan"), float("nan"))
              for x, y, v in zip(out["utm_x"], out["utm_y"], ok)]
    out["lat"] = [a for a, _ in latlon]
    out["lon"] = [b for _, b in latlon]

    # Parque de referencia: por municipio; si no hay municipio (carreteras) pero sí coordenadas, el más cercano
    out["parque"] = out["cod_ine"].map(parque_de_ine)
    sin = (out["parque"] == SIN_PARQUE) & out["lat"].notna() & (out["cod_ine"] != "48020")
    out.loc[sin, "parque"] = [parque_mas_cercano(a, b) for a, b in zip(out.loc[sin, "lat"], out.loc[sin, "lon"])]
    return out


def centroides(df: pd.DataFrame) -> pd.DataFrame:
    con = df[df["cod_ine"].ne("") & df["lat"].notna()]
    c = con.groupby("cod_ine").agg(lat=("lat", "median"), lon=("lon", "median"), n_geo=("lat", "size"))
    nombres = (df[df["cod_ine"].ne("")].groupby("cod_ine")["municipio"]
               .agg(lambda s: s.mode().iat[0] if len(s.mode()) else ""))
    return nombres.to_frame().join(c, how="left").reset_index()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    if not a.offline:
        descargar()
    rutas = sorted(config.CRUDO.glob("intervenciones_*.csv"))
    if not rutas:
        sys.exit("No hay ficheros en datos/crudo. Ejecuta sin --offline.")
    df = procesar(rutas)
    df.to_csv(config.PROCESADO / "intervenciones.csv", index=False)
    cen = centroides(df)
    cen.to_csv(config.PROCESADO / "municipios.csv", index=False)

    op = df[df["operativa"]]
    print(f"\nIntervenciones totales: {len(df):,} | operativas: {len(op):,}")
    print(op.groupby("anio").size().rename("salidas operativas").to_string())
    print("\nPor familia:")
    print(op["familia"].value_counts().to_string())
    print(f"\nMunicipios: {len(cen)} (con coordenadas: {cen['lat'].notna().sum()})")
    print("\nPor parque (operativas):")
    print(op["parque"].value_counts().to_string())

    from .base_horaria import construir
    construir(df)


if __name__ == "__main__":
    main()
