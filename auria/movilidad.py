"""Presencia de gente por zona y hora con los datos de telefonía móvil del Ministerio de Transportes.

Fuente: Estudio de movilidad con Big Data (MITMS), "estudios básicos" por municipios (v2, desde 2022):
    https://movilidad-opendata.mitma.es/estudios_basicos/por-municipios/viajes/ficheros-diarios/AAAA-MM/
    AAAAMMDD_Viajes_municipios.csv.gz   (viajes por hora y par origen-destino, a partir de registros
    anónimos de móviles; ~80 MB por día para toda España)
El servidor solo responde desde España: la descarga la hace el navegador del usuario, que se queda
con los viajes que LLEGAN a zonas de Bizkaia, por hora y según si quien viaja reside en Bizkaia
(provincia 48) o viene de fuera. Resultado: datos/movilidad/llegadas_bizkaia.csv
    fecha, zona (código MITMS: municipio o agrupación), tipo (local|visitante), h00…h23 (viajes)

Este módulo:
  * asigna cada zona a un parque (municipios de la agrupación → parque mayoritario)
  * presencia habitual: llegadas por parque, tipo de día y hora (mediana de los días de muestra)
  * índice de aglomeración por parque y día = llegadas de visitantes ÷ lo habitual de ese tipo de día
  * cuánto sube la llegada de visitantes en fiestas locales (para anticiparla en la predicción)
Salidas: datos/modelo/movilidad_perfil.csv, datos/modelo/movilidad_dias.csv, datos/modelo/movilidad.json,
         informes/movilidad.md
Nota: el MITMS cambió de metodología el 1-7-2025; el índice compara cada día con días del mismo periodo.
"""
import json
from datetime import date

import numpy as np
import pandas as pd

from . import config
from .parques import INE_A_PARQUE, PARQUES

DIR = config.DATOS / "movilidad"
RUTA = DIR / "llegadas_bizkaia.csv"
RUTA_ZONAS = DIR / "zonas_mitma_bizkaia.json"     # {zona_mitma: [INE, …]}


def zona_a_parque():
    z = json.loads(RUTA_ZONAS.read_text())
    out = {}
    for zona, ines in z.items():
        ps = [INE_A_PARQUE.get(i, "BILBAO" if i == "48020" else None) for i in ines]
        ps = [p for p in ps if p]
        out[zona] = max(set(ps), key=ps.count) if ps else None
    return out


def cargar():
    d = pd.read_csv(RUTA, dtype={"zona": str})
    d["fecha"] = pd.to_datetime(d["fecha"])
    d["parque"] = d["zona"].map(zona_a_parque())
    horas = [f"h{h:02d}" for h in range(24)]
    largo = d.melt(id_vars=["fecha", "zona", "tipo", "parque"], value_vars=horas, var_name="h", value_name="viajes")
    largo["hora"] = largo["h"].str[1:].astype(int)
    return largo.drop(columns="h")


def tipo_dia(f):
    from .riesgo_trafico import tipo_dia as td
    return td(pd.Timestamp(f))


def calcular(guardar=True):
    l = cargar()
    l = l[l["parque"].notna()]
    l["tipo_dia"] = l["fecha"].map(tipo_dia)
    l["metodo"] = np.where(l["fecha"] >= "2025-07-01", "v2025", "v2024")
    # 1) presencia habitual: parque × tipo de día × hora (mediana de los días)
    ph = l.groupby(["parque", "fecha", "tipo_dia", "hora", "tipo"])["viajes"].sum().reset_index()
    perfil = ph.groupby(["parque", "tipo_dia", "hora", "tipo"])["viajes"].median().unstack("tipo").fillna(0)
    perfil["total"] = perfil.sum(axis=1)
    media = perfil.groupby(level="parque")["total"].transform("mean")
    perfil["relativo"] = (perfil["total"] / media).round(3)          # 1 = hora media del parque
    perfil = perfil.round(0).reset_index()
    # 2) índice de aglomeración diario (visitantes) frente a días del mismo tipo y metodología
    dd = l.groupby(["parque", "fecha", "tipo_dia", "metodo", "tipo"])["viajes"].sum().unstack("tipo").fillna(0).reset_index()
    base = dd.groupby(["parque", "tipo_dia", "metodo"])["visitante"].transform("median")
    dd["indice_visitantes"] = (dd["visitante"] / base.clip(lower=1)).round(2)
    base_l = dd.groupby(["parque", "tipo_dia", "metodo"])["local"].transform("median")
    dd["indice_locales"] = (dd["local"] / base_l.clip(lower=1)).round(2)
    # 3) fiestas locales: ¿cuánto suben los visitantes?
    fiestas = set()
    rf = config.DATOS / "festivos_locales.csv"
    if rf.exists():
        f = pd.read_csv(rf, dtype={"cod_ine": str})
        f["parque"] = f["cod_ine"].map(INE_A_PARQUE)
        fiestas = set(zip(f["parque"], pd.to_datetime(f["fecha"])))
    dd["fiesta_local"] = [(p, fe) in fiestas for p, fe in zip(dd["parque"], dd["fecha"])]
    ef = {}
    for p, g in dd.groupby("parque"):
        si, no = g.loc[g["fiesta_local"], "indice_visitantes"], g.loc[~g["fiesta_local"], "indice_visitantes"]
        if len(si):
            ef[p] = {"dias_fiesta": int(len(si)), "visitantes_en_fiesta": round(float(si.mean()), 2),
                     "visitantes_resto": round(float(no.mean()), 2)}
    res = {"fecha": date.today().isoformat(), "dias": int(l["fecha"].nunique()),
           "desde": str(l["fecha"].min().date()), "hasta": str(l["fecha"].max().date()),
           "fiestas_locales": ef,
           "top_aglomeraciones": dd.sort_values("indice_visitantes", ascending=False).head(15)[
               ["parque", "fecha", "tipo_dia", "visitante", "indice_visitantes", "fiesta_local"]]
           .assign(fecha=lambda x: x["fecha"].dt.date.astype(str)).to_dict("records"),
           "nota": "Viajes que llegan a la zona según datos anónimos de móviles (MITMS). "
                   "Índice 2 = el doble de visitantes que un día normal del mismo tipo."}
    if guardar:
        perfil.to_csv(config.DIR_MODELO / "movilidad_perfil.csv", index=False)
        dd.assign(fecha=dd["fecha"].dt.date).to_csv(config.DIR_MODELO / "movilidad_dias.csv", index=False)
        (config.DIR_MODELO / "movilidad.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                          encoding="utf-8")
        informe(res, perfil)
    return res, perfil, dd


def informe(res, perfil):
    L = [f"# AURIA — Presencia de gente por zona (datos de móviles, MITMS)",
         f"{res['dias']} días de muestra ({res['desde']} → {res['hasta']}). {res['nota']}", "",
         "## Mayores aglomeraciones de visitantes de la muestra",
         pd.DataFrame(res["top_aglomeraciones"]).to_markdown(index=False), "",
         "## Fiestas locales: visitantes (índice medio)"]
    if res["fiestas_locales"]:
        L.append(pd.DataFrame(res["fiestas_locales"]).T.to_markdown())
    t = perfil[perfil["tipo_dia"] == "S"].pivot(index="hora", columns="parque", values="relativo")
    L += ["", "## Sábado: presencia relativa por hora (1 = hora media del parque)", t.round(2).to_markdown()]
    (config.INFORMES / "movilidad.md").write_text("\n".join(L), encoding="utf-8")


def presencia(parque, ts):
    """Presencia relativa esperada (1 = hora media del parque) y fracción de visitantes, para la predicción."""
    p = config.DIR_MODELO / "movilidad_perfil.csv"
    if not p.exists():
        return None
    global _PERFIL
    try:
        _PERFIL
    except NameError:
        _PERFIL = pd.read_csv(p).set_index(["parque", "tipo_dia", "hora"])
    k = (parque, tipo_dia(ts), ts.hour)
    if k not in _PERFIL.index:
        return None
    r = _PERFIL.loc[k]
    return {"presencia_rel": float(r["relativo"]),
            "frac_visitantes": float(r["visitante"] / max(r["total"], 1))}


if __name__ == "__main__":
    r, _, _ = calcular()
    print(open(config.INFORMES / "movilidad.md", encoding="utf-8").read()[:3000])
