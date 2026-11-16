"""Meteorología diaria por municipio (Open-Meteo, reanálisis ERA5 + modelos; gratis y sin clave).

Uso: python -m auria.meteo --desde 2021-01-01
Necesita datos/procesado/municipios.csv (lo genera auria.historico).
Salida: datos/procesado/meteo_diaria.csv  (municipio × día)
        datos/procesado/meteo_mensual.csv (municipio × mes, variables de riesgo)

Cuando tengas la API key de Euskalmet se puede sustituir/añadir sus estaciones.
"""
import argparse
import time
from datetime import date, timedelta

import pandas as pd
import requests

from . import config

VARIABLES = [
    "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
    "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant",
    "relative_humidity_2m_min", "snowfall_sum",
]
LOTE = 20   # coordenadas por petición


def descargar(municipios: pd.DataFrame, desde: str, hasta: str) -> pd.DataFrame:
    m = municipios.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    filas = []
    for i in range(0, len(m), LOTE):
        trozo = m.iloc[i:i + LOTE]
        params = {
            "latitude": ",".join(f"{v:.4f}" for v in trozo["lat"]),
            "longitude": ",".join(f"{v:.4f}" for v in trozo["lon"]),
            "start_date": desde, "end_date": hasta,
            "daily": ",".join(VARIABLES), "timezone": "Europe/Madrid",
        }
        for intento in range(4):
            r = requests.get(config.OPENMETEO_ARCHIVO, params=params, timeout=120,
                             headers={"User-Agent": config.USER_AGENT})
            if r.status_code == 429:
                time.sleep(30 * (intento + 1))
                continue
            r.raise_for_status()
            break
        res = r.json()
        res = res if isinstance(res, list) else [res]
        for (_, mun), bloque in zip(trozo.iterrows(), res):
            d = pd.DataFrame(bloque["daily"])
            d["cod_ine"] = mun["cod_ine"]
            filas.append(d)
        print(f"  meteo {min(i + LOTE, len(m))}/{len(m)} municipios", flush=True)
        time.sleep(1)
    df = pd.concat(filas, ignore_index=True).rename(columns={"time": "fecha"})
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def _racha_seca_max(lluvia: pd.Series) -> int:
    seco = (lluvia.fillna(0) < 1).astype(int).to_numpy()
    mejor = act = 0
    for v in seco:
        act = act + 1 if v else 0
        mejor = max(mejor, act)
    return mejor


def mensual(diaria: pd.DataFrame) -> pd.DataFrame:
    d = diaria.copy()
    d["anio"] = d["fecha"].dt.year
    d["mes"] = d["fecha"].dt.month
    dirv = d["wind_direction_10m_dominant"]
    d["sur"] = dirv.between(135, 225) & (d["wind_gusts_10m_max"] >= 40)
    d["riesgo_incendio"] = (d["relative_humidity_2m_min"] < 40) & (d["temperature_2m_max"] > 20)
    g = d.groupby(["cod_ine", "anio", "mes"])
    out = pd.DataFrame({
        "lluvia_total": g["precipitation_sum"].sum(),
        "dias_lluvia_10": g["precipitation_sum"].apply(lambda s: (s >= 10).sum()),
        "dias_lluvia_30": g["precipitation_sum"].apply(lambda s: (s >= 30).sum()),
        "lluvia_max_dia": g["precipitation_sum"].max(),
        "racha_max": g["wind_gusts_10m_max"].max(),
        "dias_racha_60": g["wind_gusts_10m_max"].apply(lambda s: (s >= 60).sum()),
        "dias_racha_80": g["wind_gusts_10m_max"].apply(lambda s: (s >= 80).sum()),
        "tmax_media": g["temperature_2m_max"].mean(),
        "tmax_max": g["temperature_2m_max"].max(),
        "tmin_min": g["temperature_2m_min"].min(),
        "dias_helada": g["temperature_2m_min"].apply(lambda s: (s <= 0).sum()),
        "dias_frio_5": g["temperature_2m_min"].apply(lambda s: (s <= 5).sum()),
        "hum_min_media": g["relative_humidity_2m_min"].mean(),
        "dias_viento_sur": g["sur"].sum(),
        "dias_riesgo_incendio": g["riesgo_incendio"].sum(),
        "racha_seca_max": g["precipitation_sum"].apply(_racha_seca_max),
        "nieve_total": g["snowfall_sum"].sum(),
    }).reset_index()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2021-01-01")
    ap.add_argument("--hasta", default=(date.today() - timedelta(days=6)).isoformat())
    a = ap.parse_args(argv)
    mun = pd.read_csv(config.PROCESADO / "municipios.csv", dtype={"cod_ine": str})
    sin = mun[mun["lat"].isna()]
    if len(sin):
        print(f"Aviso: {len(sin)} municipios sin coordenadas se omiten: {', '.join(sin['municipio'])}")
    diaria = descargar(mun, a.desde, a.hasta)
    diaria.to_csv(config.PROCESADO / "meteo_diaria.csv", index=False)
    mensual(diaria).to_csv(config.PROCESADO / "meteo_mensual.csv", index=False)
    print(f"Meteo diaria: {len(diaria):,} filas")


if __name__ == "__main__":
    main()
