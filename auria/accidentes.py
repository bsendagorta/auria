"""Probabilidad de accidente de tráfico por hora y por carretera en Bizkaia.

Fuentes
  - DGT, microdatos de accidentes con víctimas (una fila por accidente, 2019-2025): año, mes, día de
    la semana, hora, municipio, carretera, km, tipo de vía, víctimas, meteo, firme, luz.
  - SPEIS (Open Data Bizkaia, ya en datos/modelo/base_horaria.csv): nivel real de salidas de bomberos
    a accidentes de tráfico por parque. La DGT da la FORMA (horas, días, tramos, lluvia); el SPEIS el NIVEL.
  - Open-Meteo (reanálisis horario): horas de lluvia, para calcular el riesgo relativo con lluvia.
  - Gobierno Vasco (Memoria de la Dirección de Tráfico): totales anuales, solo para contrastar.

Salidas (datos/modelo/, se suben a git)
  dgt_accidentes_bizkaia.csv   accidentes con víctimas en Bizkaia con parque asignado
  trafico_perfil_horario.csv   parque × tipo de día × hora -> factor sobre la media de su franja
  trafico_tramos.csv           carretera × tramo de 5 km -> accidentes/año, graves, parque
  trafico_factores.json        riesgo relativo con lluvia, salidas SPEIS por accidente, resumen
  informes/accidentes_trafico.md

Uso: python -m auria.accidentes            (descarga + calcula)
     python -m auria.accidentes --offline  (recalcula desde dgt_accidentes_bizkaia.csv)
"""
import argparse
import io
import json
import sys
from datetime import date

import numpy as np
import pandas as pd
import requests

from . import config
from .base_horaria import HORAS_FRANJA, franja_de_hora
from .parques import PARQUES, SIN_PARQUE, parque_de_ine

DGT = "https://www.dgt.es/export/sites/web-DGT/.galleries/downloads/dgt-en-cifras"
FICHEROS = {   # la DGT cambia el nombre y la carpeta de un año a otro: se prueban en orden
    2019: ["publicaciones/Ficheros_microdatos_de_accidentalidad_con_victimas/Tabla-Accidentes-2019.xlsx"],
    2020: ["24h/TABLA_ACCIDENTES_20.xlsx"],
    2021: ["24h/TABLA_ACCIDENTES_21.xlsx", "24h/TABLA_ACCIDENTES_21.XLSX",
           "publicaciones/Ficheros_microdatos_de_accidentalidad_con_victimas/TABLA_ACCIDENTES_21.xlsx"],
    2022: ["24h/TABLA_ACCIDENTES_22.xlsx"],
    2023: ["24h/TABLA_ACCIDENTES_23.XLSX"],
    2024: ["publicaciones/Ficheros_microdatos_de_accidentalidad_con_victimas/TABLA_ACCIDENTES_24.XLSX"],
    2025: ["publicaciones/Ficheros_microdatos_de_accidentalidad_con_victimas/TABLA_ACCIDENTES_2025.XLSX"],
}
COLUMNAS = ["ANYO", "MES", "DIA_SEMANA", "HORA", "COD_PROVINCIA", "COD_MUNICIPIO", "ZONA", "ZONA_AGRUPADA",
            "CARRETERA", "KM", "TITULARIDAD_VIA", "TIPO_VIA", "TIPO_ACCIDENTE", "TOTAL_MU30DF", "TOTAL_HG30DF",
            "TOTAL_HL30DF", "TOTAL_VICTIMAS_30DF", "TOTAL_VEHICULOS", "CONDICION_FIRME", "CONDICION_ILUMINACION",
            "CONDICION_METEO"]
BIZKAIA = 48
BILBAO = "48020"
TRAMO_KM = 5
RUTA_ACC = config.DIR_MODELO / "dgt_accidentes_bizkaia.csv"
RUTA_PERFIL = config.DIR_MODELO / "trafico_perfil_horario.csv"
RUTA_TRAMOS = config.DIR_MODELO / "trafico_tramos.csv"
RUTA_FACTORES = config.DIR_MODELO / "trafico_factores.json"
TIPOS_DIA = {1: "LJ", 2: "LJ", 3: "LJ", 4: "LJ", 5: "V", 6: "S", 7: "D"}   # DGT: 1 = lunes ... 7 = domingo
DIAS_TIPO = {"LJ": 4, "V": 1, "S": 1, "D": 1}


# ------------------------------------------------------------------------------------- descarga
def _leer_xlsx_bizkaia(contenido: bytes, anio: int) -> pd.DataFrame:
    """Lee el XLSX en modo streaming y se queda solo con las filas de Bizkaia (el fichero completo
    son ~100.000 accidentes y 200 MB descomprimido)."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    filas = ws.iter_rows(values_only=True)
    cab = [str(c).strip().upper() if c is not None else "" for c in next(filas)]
    if "ANYO" not in cab and "AÑO" in cab:
        cab[cab.index("AÑO")] = "ANYO"
    ip = cab.index("COD_PROVINCIA")
    idx = {c: cab.index(c) for c in COLUMNAS if c in cab}
    datos = []
    for f in filas:
        try:
            if int(f[ip]) != BIZKAIA:
                continue
        except (TypeError, ValueError):
            continue
        datos.append({c: f[i] for c, i in idx.items()})
    wb.close()
    df = pd.DataFrame(datos)
    if "ANYO" not in df:
        df["ANYO"] = anio
    return df


def descargar(anios=None) -> pd.DataFrame:
    partes = []
    for anio in anios or sorted(FICHEROS):
        for ruta in FICHEROS[anio]:
            url = f"{DGT}/{ruta}"
            try:
                r = requests.get(url, timeout=300, headers={"User-Agent": config.USER_AGENT})
                if r.status_code != 200 or len(r.content) < 100_000:
                    continue
                df = _leer_xlsx_bizkaia(r.content, anio)
                df["ANYO"] = pd.to_numeric(df["ANYO"], errors="coerce").fillna(anio).astype(int)
                if (df["ANYO"] != anio).all():          # el enlace de la DGT apuntaba a otro año
                    print(f"  {anio}: {ruta} contiene {df['ANYO'].iat[0]}, se descarta")
                    continue
                print(f"  {anio}: {len(df):,} accidentes en Bizkaia ({len(r.content) / 1e6:.0f} MB)", flush=True)
                partes.append(df)
                break
            except Exception as e:
                print(f"  {anio}: fallo con {ruta}: {e}", flush=True)
        else:
            print(f"  {anio}: no disponible")
    if not partes:
        raise SystemExit("No se pudo descargar ningún fichero de la DGT")
    return pd.concat(partes, ignore_index=True)


# ------------------------------------------------------------------------------------- limpieza
def _ine(v) -> str:
    s = str(v or "").strip().split(".")[0]
    return s.zfill(5) if s.isdigit() else ""


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in ["ANYO", "MES", "DIA_SEMANA", "HORA", "ZONA_AGRUPADA", "TIPO_VIA", "CONDICION_METEO",
              "CONDICION_FIRME", "CONDICION_ILUMINACION", "TOTAL_MU30DF", "TOTAL_HG30DF", "TOTAL_VICTIMAS_30DF"]:
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d["KM"] = pd.to_numeric(d.get("KM"), errors="coerce")
    d["COD_MUNICIPIO"] = d["COD_MUNICIPIO"].map(_ine)
    d["CARRETERA"] = d["CARRETERA"].fillna("").astype(str).str.upper().str.replace(" ", "", regex=False)
    d["interurbana"] = d["ZONA_AGRUPADA"] == 1
    d["grave"] = (d["TOTAL_MU30DF"].fillna(0) + d["TOTAL_HG30DF"].fillna(0)) > 0
    d["lluvia"] = d["CONDICION_METEO"].isin([3, 4])
    d["lluvia_fuerte"] = d["CONDICION_METEO"] == 4
    d["firme_mojado"] = d["CONDICION_FIRME"].isin([3, 4])
    d["tipo_dia"] = d["DIA_SEMANA"].map(TIPOS_DIA)
    return _asignar_parque(d)


def _asignar_parque(d: pd.DataFrame) -> pd.DataFrame:
    """Municipio INE -> parque. Si el municipio viene como 00000 (municipios < 5.000 hab.), se usa el
    parque de los accidentes con municipio conocido en la misma carretera y el km más cercano."""
    d = d.copy()
    d["parque"] = d["COD_MUNICIPIO"].map(parque_de_ine)
    d.loc[d["COD_MUNICIPIO"] == BILBAO, "parque"] = "BILBAO"
    d["parque_por"] = np.where(d["parque"].isin(list(PARQUES) + ["BILBAO"]), "municipio", "")
    ref = d[d["parque"].isin(PARQUES) & d["KM"].notna() & (d["CARRETERA"] != "")]
    falta = (d["parque_por"] == "") & d["KM"].notna() & (d["CARRETERA"] != "")
    for i in d.index[falta]:
        r = ref[ref["CARRETERA"] == d.at[i, "CARRETERA"]]
        if r.empty:
            continue
        j = (r["KM"] - d.at[i, "KM"]).abs().idxmin()
        if abs(r.at[j, "KM"] - d.at[i, "KM"]) <= 8:     # a más de 8 km no nos fiamos
            d.at[i, "parque"] = r.at[j, "parque"]
            d.at[i, "parque_por"] = "carretera_km"
    d.loc[d["parque_por"] == "", "parque"] = SIN_PARQUE
    return d


# ------------------------------------------------------------------------------------- tablas
def _suavizar_horas(t: pd.Series) -> pd.Series:
    """Media móvil circular 1-2-1 entre horas vecinas, dentro de cada tipo de día."""
    out = t.copy()
    for td in DIAS_TIPO:
        v = t.loc[td].to_numpy()
        out.loc[td] = (0.25 * np.roll(v, 1) + 0.5 * v + 0.25 * np.roll(v, -1))
    return out


def perfil_horario(d: pd.DataFrame, k: float = 400.0) -> pd.DataFrame:
    """Factor multiplicativo f(parque, tipo_dia, hora) sobre la tasa media de la franja SPEIS.

    tasa(h, tipo_dia) = accidentes / (nº de días de ese tipo); se suaviza cada parque hacia el perfil de
    toda Bizkaia (k = accidentes ficticios). Se normaliza para que, dentro de cada franja (M/T/N) y
    promediando sobre los 7 días de la semana, el factor medio sea 1: así no cambia el nivel del SPEIS.
    """
    d = d[d["parque"].isin(PARQUES) & d["HORA"].between(0, 23) & d["tipo_dia"].notna()]
    rejilla = pd.MultiIndex.from_product([list(DIAS_TIPO), range(24)], names=["tipo_dia", "hora"])

    def tasa(x):
        c = x.groupby(["tipo_dia", "HORA"]).size().rename_axis(["tipo_dia", "hora"]).reindex(rejilla, fill_value=0)
        return c / c.index.get_level_values(0).map(DIAS_TIPO).to_numpy()

    def media_semana(t):
        return float(np.average(t.to_numpy(), weights=t.index.get_level_values(0).map(DIAS_TIPO).to_numpy()))

    glob = _suavizar_horas(tasa(d))
    glob = glob / media_semana(glob)
    filas = []
    for p in PARQUES:
        dp = d[d["parque"] == p]
        n = len(dp)
        tp = _suavizar_horas(tasa(dp))
        tp = tp / media_semana(tp) if tp.sum() > 0 else glob
        t = (n * tp + k * glob) / (n + k)          # suavizado hacia Bizkaia (k accidentes ficticios)
        df = t.rename("tasa").reset_index()
        df["parque"], df["n"] = p, n
        df["franja"] = df["hora"].map(franja_de_hora)
        df["peso"] = df["tipo_dia"].map(DIAS_TIPO)
        media = df.groupby("franja").apply(lambda g: np.average(g["tasa"], weights=g["peso"]), include_groups=False)
        df["factor"] = df["tasa"] / df["franja"].map(media)          # sobre la media de su franja
        df["factor_dia"] = df["tasa"] / np.average(df["tasa"], weights=df["peso"])   # sobre la media semanal
        filas.append(df)
    out = pd.concat(filas, ignore_index=True)[["parque", "tipo_dia", "hora", "franja", "factor", "factor_dia", "n"]]
    out[["factor", "factor_dia"]] = out[["factor", "factor_dia"]].round(4)
    return out


def tramos(d: pd.DataFrame) -> pd.DataFrame:
    """Accidentes con víctimas por carretera y tramo de 5 km (solo vías interurbanas)."""
    anios = d["ANYO"].nunique()
    t = d[d["interurbana"] & d["KM"].notna() & ~d["CARRETERA"].isin(["", "NOINVENTARIADA", "NAN"])].copy()
    t["km_ini"] = (t["KM"] // TRAMO_KM * TRAMO_KM).astype(int)
    g = t.groupby(["CARRETERA", "km_ini"])
    out = pd.DataFrame({
        "accidentes": g.size(), "graves": g["grave"].sum(), "con_lluvia": g["lluvia"].sum(),
        "parque": g["parque"].agg(lambda s: s.mode().iat[0] if len(s.mode()) else SIN_PARQUE),
        "hora_pico": g["HORA"].agg(lambda s: int(s.mode().iat[0]) if len(s.mode()) else -1),
    }).reset_index()
    out["km_fin"] = out["km_ini"] + TRAMO_KM
    out["accidentes_anio"] = (out["accidentes"] / anios).round(3)
    out["tasa_hora"] = out["accidentes_anio"] / (365.25 * 24)
    out["pct_graves"] = (100 * out["graves"] / out["accidentes"]).round(1)
    return out.sort_values("accidentes", ascending=False).reset_index(drop=True)


def lluvia_openmeteo(desde="2019-01-01", hasta=None) -> pd.Series:
    """Precipitación horaria en un punto central de Bizkaia (Open-Meteo, reanálisis)."""
    hasta = hasta or f"{date.today().year - 1}-12-31"
    r = requests.get(config.OPENMETEO_ARCHIVO, timeout=120, params={
        "latitude": 43.26, "longitude": -2.85, "start_date": desde, "end_date": hasta,
        "hourly": "precipitation", "timezone": "Europe/Madrid"})
    r.raise_for_status()
    h = r.json()["hourly"]
    return pd.Series(h["precipitation"], index=pd.to_datetime(h["time"])).fillna(0)


def riesgo_lluvia(d: pd.DataFrame, precip: pd.Series = None) -> dict:
    """Riesgo relativo de accidente con lluvia = P(lluvia | accidente) / P(lluvia en una hora cualquiera),
    ponderando las horas por el perfil de accidentes (de noche llueve igual pero se circula menos)."""
    con_meteo = d[d["CONDICION_METEO"].isin([1, 2, 3, 4, 5, 6])]
    p_acc = float(con_meteo["lluvia"].mean())
    p_acc_f = float((con_meteo["CONDICION_METEO"] == 4).mean())
    res = {"p_lluvia_en_accidentes": round(p_acc, 4), "p_lluvia_fuerte_en_accidentes": round(p_acc_f, 4)}
    if precip is None:
        return res
    pesos = d.groupby("HORA").size().reindex(range(24), fill_value=0)
    w = precip.index.hour.map(pesos).to_numpy(dtype=float)
    llueve = (precip.to_numpy() >= 0.3)
    fuerte = (precip.to_numpy() >= 2.5)
    p_h = float(np.average(llueve, weights=w))
    p_hf = float(np.average(fuerte, weights=w))
    res.update({
        "p_horas_lluvia": round(p_h, 4), "p_horas_lluvia_fuerte": round(p_hf, 4),
        "rr_lluvia": round(p_acc / p_h, 3) if p_h else None,
        "rr_lluvia_fuerte": round(p_acc_f / p_hf, 3) if p_hf else None,
        "umbral_lluvia_mm_h": 0.3, "umbral_lluvia_fuerte_mm_h": 2.5,
    })
    return res


def calibracion_speis(d: pd.DataFrame) -> dict:
    """Salidas SPEIS de la familia TRAFICO por accidente con víctimas DGT (mismos años, por parque)."""
    base = config.DIR_MODELO / "base_horaria.csv"
    if not base.exists():
        return {}
    b = pd.read_csv(base)
    b = b[b["familia"] == "TRAFICO"]
    # salidas/año SPEIS por parque = suma de n / años del histórico (2023-2025)
    speis = b.groupby("parque")["n"].sum() / 3
    dgt = d[d["parque"].isin(PARQUES) & d["ANYO"].between(2023, 2025)].groupby("parque").size() / \
        max(1, d.loc[d["ANYO"].between(2023, 2025), "ANYO"].nunique())
    tabla = pd.DataFrame({"salidas_speis_anio": speis.round(1), "accidentes_dgt_anio": dgt.round(1)})
    tabla["salidas_por_accidente"] = (tabla["salidas_speis_anio"] / tabla["accidentes_dgt_anio"]).round(3)
    return tabla.reindex(list(PARQUES)).fillna(0).to_dict(orient="index")


# ------------------------------------------------------------------------------------- informe
def informe(d, perfil, tr, fac):
    anios = sorted(d["ANYO"].unique())
    pb = d[d["parque"] != "BILBAO"]
    lineas = [
        "# AURIA — Accidentes de tráfico en Bizkaia (DGT)",
        f"Generado: {date.today()} · años {anios[0]}-{anios[-1]} · {len(d):,} accidentes con víctimas "
        f"({len(pb):,} fuera de Bilbao, {int(pb['interurbana'].sum()):,} en vías interurbanas)",
        "",
        "## Asignación a parque",
        d["parque_por"].replace("", "sin asignar").value_counts().to_frame("accidentes").to_markdown(),
        "",
        d[d["parque"] != "BILBAO"]["parque"].value_counts().to_frame("accidentes").to_markdown(),
        "",
        "## Accidentes por año",
        d.groupby("ANYO").agg(accidentes=("HORA", "size"), interurbanos=("interurbana", "sum"),
                              graves=("grave", "sum")).to_markdown(),
        "",
        "## Riesgo con lluvia",
        "```", json.dumps(fac.get("lluvia", {}), ensure_ascii=False, indent=1), "```",
        "",
        "## Salidas SPEIS por accidente con víctimas (2023-2025)",
        pd.DataFrame(fac.get("calibracion_speis", {})).T.to_markdown() if fac.get("calibracion_speis") else "—",
        "",
        "## Perfil horario Bizkaia (factor sobre la media de su franja)",
        perfil.groupby(["tipo_dia", "hora"])["factor"].mean().unstack(0)[list(DIAS_TIPO)].round(2).to_markdown(),
        "",
        "## 25 tramos con más accidentes (5 km, vías interurbanas)",
        tr.head(25)[["CARRETERA", "km_ini", "km_fin", "parque", "accidentes", "accidentes_anio", "graves",
                     "pct_graves", "hora_pico"]].to_markdown(index=False),
    ]
    ruta = config.INFORMES / "accidentes_trafico.md"
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--sin-meteo", action="store_true")
    a = ap.parse_args(argv)
    if a.offline:
        crudo = pd.read_csv(RUTA_ACC, dtype={"COD_MUNICIPIO": str})[COLUMNAS]
    else:
        print("Descargando microdatos de la DGT…", flush=True)
        crudo = descargar()
    d = preparar(crudo)
    d.to_csv(RUTA_ACC, index=False)
    perfil = perfil_horario(d)
    perfil.to_csv(RUTA_PERFIL, index=False)
    tr = tramos(d[d["parque"] != "BILBAO"])
    tr.to_csv(RUTA_TRAMOS, index=False)
    precip = None
    if not a.sin_meteo:
        try:
            precip = lluvia_openmeteo(f"{d['ANYO'].min()}-01-01", f"{d['ANYO'].max()}-12-31")
        except Exception as e:
            print(f"Aviso: sin lluvia horaria de Open-Meteo ({e})")
    fac = {"lluvia": riesgo_lluvia(d[d["parque"] != "BILBAO"], precip),
           "calibracion_speis": calibracion_speis(d),
           "anios": [int(x) for x in sorted(d["ANYO"].unique())], "generado": str(date.today())}
    RUTA_FACTORES.write_text(json.dumps(fac, ensure_ascii=False, indent=1), encoding="utf-8")
    ruta = informe(d, perfil, tr, fac)
    print(f"{len(d):,} accidentes · tramos: {len(tr)} · informe: {ruta}")
    print(json.dumps(fac["lluvia"], ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
