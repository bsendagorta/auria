"""Tabla maestra + modelos de conteo (fase 1: resolución MENSUAL, la que permite el histórico abierto).

Uso:
    python -m auria.modelo                       # Bizkaia total × familia × mes
    python -m auria.modelo --nivel municipio     # municipio × familia × mes
    python -m auria.modelo --desde 2021          # usar también 2021-22 (tipologías antiguas)

Compara 3 modelos con validación temporal (entrena años anteriores, prueba el último año completo):
    referencia : media del mismo mes en años anteriores (lo que hay que batir)
    glm        : regresión de Poisson (interpretable)
    gbm        : gradient boosting con pérdida Poisson
Informe en informes/modelo_<nivel>.md y detalle de la validación en informes/validacion_<nivel>.csv
"""
import argparse
from datetime import date

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import calendario, config
from .familias import FAMILIAS

SIN_UBICAR = "00000"


# ---------------------------------------------------------------- tabla maestra
def _asignar_municipio(df, mun):
    """Intervenciones sin municipio (p.ej. carreteras) -> municipio más cercano si hay coordenadas."""
    df = df.copy()
    falta = df["cod_ine"].eq("") | df["cod_ine"].isna()
    con_geo = falta & df["lat"].notna()
    m = mun.dropna(subset=["lat"])
    if con_geo.any() and len(m):
        a = df.loc[con_geo, ["lat", "lon"]].to_numpy()
        b = m[["lat", "lon"]].to_numpy()
        idx = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1).argmin(1)
        df.loc[con_geo, "cod_ine"] = m["cod_ine"].to_numpy()[idx]
    df.loc[df["cod_ine"].eq("") | df["cod_ine"].isna(), "cod_ine"] = SIN_UBICAR
    return df


def tabla_maestra(nivel="bizkaia", desde=2023):
    inter = pd.read_csv(config.PROCESADO / "intervenciones.csv", dtype={"cod_ine": str},
                        keep_default_na=False, na_values={"lat": [""], "lon": [""]})
    mun = pd.read_csv(config.PROCESADO / "municipios.csv", dtype={"cod_ine": str})
    inter = inter[(inter["operativa"].astype(str) == "True") & (inter["anio"] >= desde)]
    inter = _asignar_municipio(inter, mun)

    clave = ["cod_ine"] if nivel == "municipio" else []
    conteo = inter.groupby(clave + ["anio", "mes", "familia"]).size().rename("y")

    anios = range(desde, int(inter["anio"].max()) + 1)
    meses = pd.MultiIndex.from_product([anios, range(1, 13)], names=["anio", "mes"]).to_frame(index=False)
    ultimo = inter[["anio", "mes"]].drop_duplicates().sort_values(["anio", "mes"]).iloc[-1]
    meses = meses[(meses["anio"] * 100 + meses["mes"]) <= ultimo["anio"] * 100 + ultimo["mes"]]
    rejilla = meses.merge(pd.DataFrame({"familia": FAMILIAS}), how="cross")
    if nivel == "municipio":
        cods = sorted(set(inter["cod_ine"]))
        rejilla = rejilla.merge(pd.DataFrame({"cod_ine": cods}), how="cross")
    t = rejilla.merge(conteo.reset_index(), how="left", on=clave + ["anio", "mes", "familia"])
    t["y"] = t["y"].fillna(0)
    return _variables(t, nivel)


def _variables(t, nivel):
    t = t.sort_values(["anio", "mes"]).copy()
    t["idx_mes"] = (t["anio"] - t["anio"].min()) * 12 + t["mes"] - 1
    t["mes_sin"] = np.sin(2 * np.pi * t["mes"] / 12)
    t["mes_cos"] = np.cos(2 * np.pi * t["mes"] / 12)
    grupo = (["cod_ine"] if nivel == "municipio" else []) + ["familia"]

    # retardos (solo información disponible ANTES del mes a predecir)
    t = t.sort_values(grupo + ["idx_mes"])
    g = t.groupby(grupo)["y"]
    t["lag_12"] = g.shift(12)
    t["media_3m_prev"] = g.transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    t["media_hist_mes"] = t.groupby(grupo + ["mes"])["y"].transform(
        lambda s: s.shift(1).expanding().mean())
    for c in ("lag_12", "media_3m_prev", "media_hist_mes"):   # escala log, acorde al enlace Poisson
        t[f"log_{c}"] = np.log1p(t[c])

    cal = calendario.mensual(f"{t['anio'].min()}-01-01", f"{t['anio'].max()}-12-31")
    t = t.merge(cal, on=["anio", "mes"], how="left")

    p = config.PROCESADO / "meteo_mensual.csv"
    if p.exists():
        met = pd.read_csv(p, dtype={"cod_ine": str})
        if nivel == "municipio":
            t = t.merge(met, on=["cod_ine", "anio", "mes"], how="left")
        else:
            agg = met.drop(columns="cod_ine").groupby(["anio", "mes"]).mean().reset_index()
            t = t.merge(agg, on=["anio", "mes"], how="left")
    else:
        print("Aviso: no hay meteo_mensual.csv (ejecuta python -m auria.meteo). Se entrena sin meteorología.")
    return t


# ---------------------------------------------------------------- modelos
def _matriz(t, columnas_fam, enc_mun=None):
    excluir = {"y", "anio", "cod_ine", "familia", "pred_ref", "pred_glm", "pred_gbm"}
    num = [c for c in t.columns if c not in excluir and t[c].dtype != object]
    X = t[num].copy()
    for f in columnas_fam:
        X[f"fam_{f}"] = (t["familia"] == f).astype(float)
    if enc_mun is not None:
        X["mun_nivel"] = t["cod_ine"].map(enc_mun).fillna(0)
    return X


def evaluar(t, nivel):
    anio_test = int(t.loc[t["mes"] == 12, "anio"].max())     # último año completo
    tr = t[t["anio"] < anio_test].copy()
    te = t[t["anio"] == anio_test].copy()
    if tr.empty:
        raise SystemExit("Hace falta al menos un año completo de entrenamiento antes del año de prueba.")

    enc = None
    if nivel == "municipio":
        enc = np.log1p(tr.groupby("cod_ine")["y"].mean())
    Xtr, Xte = _matriz(tr, FAMILIAS, enc), _matriz(te, FAMILIAS, enc)
    rell = Xtr.median()
    Xtr, Xte = Xtr.fillna(rell).fillna(0), Xte.fillna(rell).fillna(0)

    te["pred_ref"] = te["media_hist_mes"].fillna(te["media_3m_prev"]).fillna(tr["y"].mean())

    # GLM: uno por familia (el viento no influye igual en avispas que en saneados)
    te["pred_glm"] = te["pred_ref"]
    coefs = {}
    cols_glm = [c for c in Xtr.columns if not c.startswith("fam_")]
    pocas_filas = len(tr) / len(FAMILIAS) < 100          # nivel Bizkaia: ~36-60 filas por familia
    alpha = 1.0 if pocas_filas else 1e-2
    for f in FAMILIAS:
        mtr, mte = tr["familia"] == f, te["familia"] == f
        if tr.loc[mtr, "y"].sum() < 30:          # muy pocos casos: se queda la referencia
            continue
        glm = make_pipeline(StandardScaler(), PoissonRegressor(alpha=alpha, max_iter=3000))
        glm.fit(Xtr.loc[mtr, cols_glm], tr.loc[mtr, "y"])
        te.loc[mte, "pred_glm"] = glm.predict(Xte.loc[mte, cols_glm])
        coefs[f] = pd.Series(glm[-1].coef_, index=cols_glm)
    gbm = HistGradientBoostingRegressor(loss="poisson", max_iter=400, learning_rate=0.05,
                                        max_leaf_nodes=15, min_samples_leaf=20, random_state=0,
                                        l2_regularization=1.0 if pocas_filas else 0.0)
    gbm.fit(Xtr, tr["y"])
    te["pred_gbm"] = gbm.predict(Xte)

    filas = []
    for nombre in ("ref", "glm", "gbm"):
        p = te[f"pred_{nombre}"].clip(lower=1e-6)
        filas.append({"modelo": nombre, "MAE": mean_absolute_error(te["y"], p),
                      "desv_poisson": mean_poisson_deviance(te["y"], p),
                      "total_real": te["y"].sum(), "total_pred": p.sum()})
    metricas = pd.DataFrame(filas)

    por_fam = te.groupby("familia").apply(lambda d: pd.Series({
        "real": d["y"].sum(),
        "ref": d["pred_ref"].sum(), "glm": d["pred_glm"].sum(), "gbm": d["pred_gbm"].sum(),
        "MAE_ref": mean_absolute_error(d["y"], d["pred_ref"]),
        "MAE_gbm": mean_absolute_error(d["y"], d["pred_gbm"]),
    }), include_groups=False).round(1)

    return anio_test, metricas, por_fam, coefs, te


def informe(nivel, desde, anio_test, metricas, por_fam, coef, te):
    mejor = metricas.sort_values("desv_poisson").iloc[0]["modelo"]
    lineas = [
        f"# AURIA — Modelo mensual ({nivel})",
        f"Generado: {date.today()} · datos desde {desde} · año de prueba: {anio_test}",
        "",
        "## Métricas en el año de prueba (menor = mejor)",
        metricas.round(3).to_markdown(index=False),
        "",
        f"**Mejor modelo: {mejor}.** Si no es claramente mejor que `ref`, las variables aún no aportan.",
        "",
        "## Totales del año de prueba por familia",
        por_fam.to_markdown(),
        "",
        "## Qué variables mueven cada familia (GLM, coeficientes estandarizados)",
        "Positivo = más salidas cuando la variable sube. exp(coef) ≈ multiplicador por cada desviación típica.",
    ]
    for f, c in coef.items():
        top = c.sort_values(key=abs, ascending=False).head(6)
        lineas += ["", f"**{f}**: " + ", ".join(f"{k} {v:+.2f}" for k, v in top.items())]
    ruta = config.INFORMES / f"modelo_{nivel}.md"
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    te.to_csv(config.INFORMES / f"validacion_{nivel}.csv", index=False)
    return ruta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nivel", choices=["bizkaia", "municipio"], default="bizkaia")
    ap.add_argument("--desde", type=int, default=2023,
                    help="2023 = tipologías homogéneas; 2021 = más historia pero clasificación antigua")
    a = ap.parse_args(argv)
    t = tabla_maestra(a.nivel, a.desde)
    t.to_csv(config.PROCESADO / f"tabla_maestra_{a.nivel}.csv", index=False)
    res = evaluar(t, a.nivel)
    ruta = informe(a.nivel, a.desde, *res)
    print(res[1].round(3).to_string(index=False))
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
