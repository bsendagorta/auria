"""Cuánto cambia cada situación meteorológica las salidas de cada parque y tipo de siniestro (datos reales).

1. Meteo horaria real 2021-hoy en los 8 parques (Open-Meteo, reanálisis ERA5) + oleaje en los de costa.
2. Cada hora se clasifica en situaciones (auria.situaciones) y se cuentan los DÍAS de cada situación por
   parque y mes.
3. Salidas SPEIS por parque × tipo × mes (Open Data Bizkaia) frente a esos días:
       salidas_mes = referencia × (1 + Σ_s  fracción_de_días_s × γ_s)
   referencia = mismo parque, tipo y mes de los OTROS años, ajustado al nivel de cada año.
   ⇒ multiplicador en un día con la situación s:  m_s = 1 + γ_s   (p.ej. 2,1 = el doble de salidas).
   Se ajusta por máxima verosimilitud de Poisson con penalización hacia "sin efecto"; por parque, con
   penalización hacia el efecto de toda Bizkaia (si un parque tiene pocos casos, se queda cerca de la media).
4. Validación honesta: se ajusta con 2021-2024 y se prueba en 2025. Solo se usan en directo los tipos de
   siniestro en los que las situaciones mejoran la predicción de 2025.

Uso: python -m auria.efectos_meteo   (reentreno nocturno; renueva la meteo el día 1 de cada mes)
Salidas: datos/modelo/situaciones_efectos.json, datos/modelo/situaciones_mes.csv,
         informes/situaciones_meteo.md
"""
import argparse
import json
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests
from scipy.optimize import minimize

from . import config
from .parques import PARQUES
from .situaciones import COSTA, SITUACIONES, VARS_ARCHIVO, clasificar, dias_por_mes

RUTA_HORARIA = config.DATOS / "meteo" / "horaria_parques.csv.gz"
RUTA_MES = config.DIR_MODELO / "situaciones_mes.csv"
RUTA_EFECTOS = config.DIR_MODELO / "situaciones_efectos.json"
MARINA = "https://marine-api.open-meteo.com/v1/marine"
MIN_DIAS = 8                 # días con la situación en todo el periodo para estimar su efecto
L_BIZKAIA, L_PARQUE = 3.0, 8.0


# ------------------------------------------------------------------ 1. meteo horaria histórica
def _get(url, params, intentos=5):
    for i in range(intentos):
        try:
            r = requests.get(url, params=params, timeout=300, headers={"User-Agent": config.USER_AGENT})
            if r.status_code == 200:
                return r.json()
            print(f"  aviso {r.status_code}: {r.text[:150]}", flush=True)
            if r.status_code == 400:
                return None
        except requests.RequestException as e:
            print(f"  aviso red: {e}", flush=True)
        time.sleep(30 * (i + 1))
    return None


def descargar_horaria(desde="2021-01-01", hasta=None):
    hasta = hasta or (date.today() - timedelta(days=6)).isoformat()
    partes = []
    for p, info in PARQUES.items():
        j = _get(config.OPENMETEO_ARCHIVO, {
            "latitude": info["lat"], "longitude": info["lon"], "start_date": desde, "end_date": hasta,
            "hourly": ",".join(VARS_ARCHIVO), "timezone": "Europe/Madrid", "wind_speed_unit": "kmh"})
        if j is None:
            raise RuntimeError(f"Open-Meteo no devolvió la meteo de {p}")
        d = pd.DataFrame(j["hourly"]).rename(columns={"time": "hora"})
        d["parque"] = p
        if p in COSTA:
            mj = _get(MARINA, {"latitude": info["lat"] + 0.08, "longitude": info["lon"], "start_date": desde,
                               "end_date": hasta, "hourly": "wave_height", "timezone": "Europe/Madrid"})
            if mj and "hourly" in mj:
                d = d.merge(pd.DataFrame(mj["hourly"]).rename(columns={"time": "hora", "wave_height": "ola_m"}),
                            on="hora", how="left")
            else:
                print(f"  sin oleaje para {p}", flush=True)
        partes.append(d)
        print(f"  meteo horaria {p}: {len(d):,} horas", flush=True)
        time.sleep(2)
    h = pd.concat(partes, ignore_index=True)
    RUTA_HORARIA.parent.mkdir(parents=True, exist_ok=True)
    h.to_csv(RUTA_HORARIA, index=False, compression="gzip")
    return h


# ------------------------------------------------------------------ 3. modelo
def salidas_mes():
    d = pd.read_csv(config.PROCESADO / "intervenciones.csv", dtype={"cod_ine": str}, low_memory=False)
    d = d[(d["operativa"].astype(str) == "True") & d["parque"].isin(PARQUES)]
    return d.groupby(["parque", "familia", "anio", "mes"]).size().rename("y").reset_index()


def _referencia(t, anios_ref):
    """Para cada fila: media del mismo parque·tipo·mes en los otros años de anios_ref, al nivel de su año."""
    piv = t.pivot_table(index=["parque", "familia", "mes"], columns="anio", values="y", fill_value=0)
    tot = t.groupby(["familia", "anio"])["y"].sum().unstack()
    refs = []
    for r in t.itertuples():
        otros = [a for a in anios_ref if a != r.anio and a in piv.columns]
        if not otros:
            refs.append(np.nan)
            continue
        base = piv.loc[(r.parque, r.familia, r.mes), otros].to_numpy(float)
        nivel = 1.0
        if r.anio in tot.columns and r.anio in anios_ref:     # años de entrenamiento: nivel conocido
            nivel = tot.at[r.familia, r.anio] / max(tot.loc[r.familia, otros].mean(), 1e-9)
        refs.append(max((base.sum() + 0.5) / (len(otros) + 1), 0.02) * nivel)
    return np.array(refs)


def _ajustar(y, r, X, centro, lam):
    """μ = r · (c + X·γ): c = nivel libre (absorbe el sesgo de la referencia), γ penalizado hacia 'centro'.
    Devuelve el efecto relativo γ/c (multiplicador en un día con la situación = 1 + γ/c) y su error."""
    k = X.shape[1]
    Z = np.column_stack([np.ones(len(y)), X])
    cen = np.r_[1.0, centro]
    pen = np.r_[0.0, np.full(k, lam)]

    def f(g):
        mu = r * np.clip(Z @ g, 0.05, None)
        return float(np.sum(mu - y * np.log(mu)) + np.sum(pen * (g - cen) ** 2))

    def grad(g):
        mu = r * np.clip(Z @ g, 0.05, None)
        return (r * (1 - y / mu)) @ Z + 2 * pen * (g - cen)

    res = minimize(f, cen.copy(), jac=grad, method="L-BFGS-B", bounds=[(0.2, 5)] + [(-0.9, 12)] * k)
    g = res.x
    mu = r * np.clip(Z @ g, 0.05, None)
    H = (Z * (y * r ** 2 / mu ** 2)[:, None]).T @ Z + 2 * np.diag(pen)
    try:
        se = np.sqrt(np.clip(np.diag(np.linalg.inv(H)), 0, None))[1:]
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)
    c = g[0]
    return g[1:] / c, se / c, c


def _dev(y, mu):
    mu = np.clip(mu, 1e-9, None)
    return float(2 * np.sum(np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / mu), 0) - (y - mu)))


def ajustar(mes_sit, sal, anio_test=None):
    sits_all = list(SITUACIONES)
    t = sal.merge(mes_sit, on=["parque", "anio", "mes"], how="inner")
    anios = sorted(t["anio"].unique())
    anio_test = anio_test or anios[-1]
    for s in sits_all:
        t[f"f_{s}"] = t[s] / t["dias_mes"]
    familias = sorted(t["familia"].unique())
    res = {"anios": [int(a) for a in anios], "anio_test": int(anio_test), "validacion": {}, "efectos": {},
           "por_parque": {p: {} for p in PARQUES}, "activo": {}}
    for fam in familias:
        tf = t[t["familia"] == fam].copy()
        # completa meses sin salidas (y = 0)
        rej = mes_sit[["parque", "anio", "mes"]].assign(familia=fam)
        tf = rej.merge(tf.drop(columns=["familia"]), on=["parque", "anio", "mes"], how="left")
        tf["y"] = tf["y"].fillna(0)
        tf = tf.drop(columns=sits_all + ["dias_mes"], errors="ignore").merge(mes_sit, on=["parque", "anio", "mes"])
        for s in sits_all:
            tf[f"f_{s}"] = tf[s] / tf["dias_mes"]
        sits = [s for s in sits_all if tf[s].sum() >= MIN_DIAS]
        if tf["y"].sum() < 30 or not sits:
            continue
        cols = [f"f_{s}" for s in sits]
        # --- validación: entrena sin el año de prueba
        tr = tf[tf["anio"] != anio_test].copy()
        te = tf[tf["anio"] == anio_test].copy()
        anios_tr = sorted(tr["anio"].unique())
        tr["ref"] = _referencia(pd.concat([tr]), anios_tr)
        te_ref = []
        piv = tr.pivot_table(index=["parque", "mes"], columns="anio", values="y", fill_value=0)
        ult = anios_tr[-2:]                                  # nivel reciente (mismas tipologías)
        for r in te.itertuples():
            base = piv.loc[(r.parque, r.mes), ult].to_numpy(float) if (r.parque, r.mes) in piv.index else np.zeros(1)
            te_ref.append(max((base.sum() + 0.5) / (len(base) + 1), 0.02))
        te["ref"] = te_ref
        tr = tr.dropna(subset=["ref"])
        g, _, _ = _ajustar(tr["y"].to_numpy(float), tr["ref"].to_numpy(float), tr[cols].to_numpy(float),
                           np.zeros(len(cols)), L_BIZKAIA)
        # nivel del año de prueba: se calibra con la propia referencia (igual para los dos modelos)
        mu_ref = te["ref"].to_numpy(float)
        mu_sit = mu_ref * np.clip(1 + te[cols].to_numpy(float) @ g, 0.05, None)
        y_te = te["y"].to_numpy(float)
        mu_ref = mu_ref * y_te.sum() / max(mu_ref.sum(), 1e-9)
        mu_sit = mu_sit * y_te.sum() / max(mu_sit.sum(), 1e-9)
        d_ref, d_sit = _dev(y_te, mu_ref), _dev(y_te, mu_sit)
        mejora = 100 * (1 - d_sit / max(d_ref, 1e-9))
        res["validacion"][fam] = {"dev_ref": round(d_ref, 1), "dev_situaciones": round(d_sit, 1),
                                  "mejora_pct": round(mejora, 1), "salidas_test": int(y_te.sum())}
        res["activo"][fam] = bool(mejora > 0.5)
        # --- ajuste final con todos los años
        tf["ref"] = _referencia(tf, anios)
        tf = tf.dropna(subset=["ref"])
        y, r, X = tf["y"].to_numpy(float), tf["ref"].to_numpy(float), tf[cols].to_numpy(float)
        g, se, _ = _ajustar(y, r, X, np.zeros(len(cols)), L_BIZKAIA)
        res["efectos"][fam] = {s: {"m": round(1 + g[i], 2), "lo": round(max(0.1, 1 + g[i] - 1.96 * se[i]), 2),
                                   "hi": round(1 + g[i] + 1.96 * se[i], 2),
                                   "z": round(float(g[i] / se[i]), 1) if se[i] > 0 else 0.0,
                                   "dias": int(tf.drop_duplicates(["parque", "anio", "mes"])[s].sum())}
                               for i, s in enumerate(sits)}
        for p in PARQUES:
            tp = tf[tf["parque"] == p]
            if tp["y"].sum() < 5:
                gp = g
            else:
                gp, _, _ = _ajustar(tp["y"].to_numpy(float), tp["ref"].to_numpy(float),
                                    tp[cols].to_numpy(float), g, L_PARQUE)
            res["por_parque"][p][fam] = {s: round(1 + gp[i], 2) for i, s in enumerate(sits)}
    tv = res["validacion"]
    if tv:
        dr = sum(v["dev_ref"] for v in tv.values())
        ds = sum(v["dev_situaciones"] for v in tv.values() if True)
        res["validacion_total"] = {"dev_ref": round(dr, 1), "dev_situaciones": round(ds, 1),
                                   "mejora_pct": round(100 * (1 - ds / max(dr, 1e-9)), 1)}
    res["fecha"] = date.today().isoformat()
    res["lectura"] = ("m = salidas en un día con esa situación ÷ salidas en un día normal del mismo mes y parque. "
                      "lo-hi = intervalo del 95 %. Solo se aplican en directo los tipos marcados como activos "
                      "(los que mejoran la predicción del año de prueba).")
    return res


def informe(res, mes_sit):
    from .patrones import ETIQ
    L = [f"# AURIA — Situaciones meteorológicas y salidas reales ({res['anios'][0]}-{res['anios'][-1]})",
         f"Generado {res['fecha']}. Meteo horaria ERA5 por parque · salidas SPEIS por parque, tipo y mes.", "",
         "## Días al año de cada situación (media por parque)"]
    n_anios = mes_sit.groupby("parque")["anio"].nunique().mean()
    dias = (mes_sit.groupby("parque")[list(SITUACIONES)].sum() / n_anios).round(1)
    dias.columns = [SITUACIONES[c][1] for c in dias.columns]
    L += [dias.T.to_markdown(), "",
          f"## Validación en {res['anio_test']} (desviación de Poisson, menor = mejor)",
          "| tipo | referencia | con situaciones | mejora | ¿se usa? |", "|---|---:|---:|---:|:--:|"]
    for f, v in res["validacion"].items():
        L.append(f"| {ETIQ.get(f, f)} | {v['dev_ref']} | {v['dev_situaciones']} | {v['mejora_pct']:+.1f} % | "
                 f"{'sí' if res['activo'].get(f) else 'no'} |")
    if "validacion_total" in res:
        L.append(f"\n**Total: {res['validacion_total']['mejora_pct']:+.1f} %**")
    L += ["", "## Multiplicador en un día con la situación (toda Bizkaia)",
          "Solo efectos claros (intervalo del 95 % sin cruzar 1). Entre paréntesis, días con la situación."]
    for f, ef in res["efectos"].items():
        claros = [(s, e) for s, e in ef.items() if e["lo"] > 1 or e["hi"] < 1]
        if claros:
            L.append(f"- **{ETIQ.get(f, f)}**: " + ", ".join(
                f"{SITUACIONES[s][1]} ×{e['m']} [{e['lo']}-{e['hi']}] ({e['dias']} d)"
                for s, e in sorted(claros, key=lambda t: -t[1]["m"])))
    L += ["", "## Por parque (multiplicadores con encogimiento hacia Bizkaia)"]
    for f in res["efectos"]:
        filas = {p: res["por_parque"][p].get(f, {}) for p in PARQUES}
        df = pd.DataFrame(filas).rename(index=lambda s: SITUACIONES[s][1])
        if not df.empty:
            L += ["", f"**{ETIQ.get(f, f)}**", df.to_markdown()]
    L += ["", f"_{res['lectura']}_"]
    (config.INFORMES / "situaciones_meteo.md").write_text("\n".join(L), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--descargar", action="store_true", help="forzar nueva descarga de la meteo horaria")
    a = ap.parse_args(argv)
    if a.descargar or not RUTA_HORARIA.exists():
        print("Descargando meteo horaria 2021-hoy de los 8 parques…", flush=True)
        horaria = descargar_horaria()
    else:
        horaria = pd.read_csv(RUTA_HORARIA)
    sit = clasificar(horaria)
    mes_sit = dias_por_mes(sit)
    mes_sit.to_csv(RUTA_MES, index=False)
    sal = salidas_mes()
    anios = sorted(set(sal["anio"]) & set(mes_sit["anio"]))
    sal = sal[sal["anio"].isin(anios)]
    # solo años completos con salidas publicadas
    mes_fit = mes_sit[mes_sit["anio"].isin(anios)]
    res = ajustar(mes_fit, sal)
    RUTA_EFECTOS.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    informe(res, mes_fit)
    print(open(config.INFORMES / "situaciones_meteo.md", encoding="utf-8").read()[:4000])


if __name__ == "__main__":
    main()
