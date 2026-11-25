"""¿Acierta AURIA? Compara cada hora lo que se predijo con lo que pasó de verdad.

Predicho : prediccion/historial/prediccion_*.csv, horizonte 0 (la hora en curso), primera predicción
           de cada hora; λ sumado sobre los 8 parques.
Ocurrido : salidas reales por hora en Bizkaia según el contador anual de bizkaia.eus (recolector).
           Incluye salidas sin parque asignado (Bilbao no: tiene servicio propio).
Métricas : salidas predichas vs reales (sesgo), error absoluto medio por hora y "skill" = cuánto mejor
           que predecir siempre la tasa normal (desviación de Poisson; > 0 = aporta, < 0 = empeora).

Uso: python -m auria.evaluacion
Salida: datos/modelo/evaluacion.json  y  datos/modelo/evaluacion_horaria.csv (últimos 14 días)
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd

from . import config

RUTA_JSON = config.DIR_MODELO / "evaluacion.json"
RUTA_CSV = config.DIR_MODELO / "evaluacion_horaria.csv"


def _dev(y, mu):
    y, mu = np.asarray(y, float), np.clip(np.asarray(mu, float), 1e-6, None)
    t = np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / mu), 0) - (y - mu)
    return float(2 * t.mean())


def predicciones() -> pd.DataFrame:
    rutas = sorted((config.DIR_PREDICCION / "historial").glob("prediccion_*.csv"))
    if not rutas:
        return pd.DataFrame()
    p = pd.concat([pd.read_csv(r) for r in rutas], ignore_index=True)
    p = p[p["horizonte"] == 0].copy()
    p["hora"] = pd.to_datetime(p["hora"], format="mixed")
    p["generado"] = pd.to_datetime(p["generado"].str[:16])
    p = p.sort_values("generado").drop_duplicates(["parque", "hora"], keep="first")
    g = p.groupby("hora")
    return pd.DataFrame({"pred": g["lambda"].sum(), "normal": g["normal"].sum(),
                         "modelo": g["modelo"].agg(lambda s: s.mode().iat[0])})


def evaluar(guardar=True):
    from .resumen_online import resumir
    pred = predicciones()
    r = resumir(guardar=False)
    if pred.empty or r is None:
        res = {"estado": "sin datos todavía", "fecha": datetime.now().isoformat(timespec="minutes")}
        if guardar:
            RUTA_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        return res
    _, horario, _ = r
    real = horario["salidas"].rename("real")
    d = pred.join(real, how="inner").dropna(subset=["real"])
    d = d[d.index < pd.Timestamp.now().floor("h")]          # solo horas cerradas
    if d.empty:
        res = {"estado": "aún no hay horas cerradas con predicción y dato real"}
    else:
        def bloque(x):
            return {
                "horas": int(len(x)),
                "salidas_reales": round(float(x["real"].sum()), 1),
                "salidas_predichas": round(float(x["pred"].sum()), 1),
                "sesgo_pct": round(100 * (x["pred"].sum() / max(x["real"].sum(), 1e-9) - 1), 1),
                "mae_hora": round(float((x["pred"] - x["real"]).abs().mean()), 3),
                "skill_vs_normal": round(1 - _dev(x["real"], x["pred"]) / max(_dev(x["real"], x["normal"]), 1e-9), 3),
            }
        ult7 = d[d.index >= d.index.max() - pd.Timedelta(days=7)]
        diario = d.resample("D").sum(numeric_only=True)
        diario = diario[diario["real"] > 0]
        res = {
            "estado": "ok", "fecha": datetime.now().isoformat(timespec="minutes"),
            "desde": d.index.min().isoformat(), "hasta": d.index.max().isoformat(),
            "total": bloque(d), "ultimos_7_dias": bloque(ult7),
            "por_dia": [{"dia": i.date().isoformat(), "real": int(v.real), "predicho": round(float(v.pred), 1),
                         "normal": round(float(v.normal), 1)} for i, v in diario.tail(30).iterrows()],
            "lectura": ("skill > 0: el modelo predice mejor que la tasa normal; sesgo > 0: predice de más. "
                        "Las salidas reales incluyen las que no se pueden asignar a un parque."),
        }
    if guardar:
        RUTA_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        if not d.empty:
            d[d.index >= d.index.max() - pd.Timedelta(days=14)].round(3).to_csv(RUTA_CSV)
    return res


if __name__ == "__main__":
    print(json.dumps(evaluar(), ensure_ascii=False, indent=1))
