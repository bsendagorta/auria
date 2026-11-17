"""Paso 4 — reentrenamiento nocturno del modelo horario por parque (LightGBM, pérdida Poisson).

Datos de entrenamiento (se generan solos con el uso):
  variables : prediccion/historial/variables_*.csv  (lo que el sistema "sabía" al empezar cada hora)
  objetivo  : actuaciones vistas por el recolector que empezaron en esa hora y parque
Como el recolector no ve las actuaciones muy cortas, se calcula un factor de cobertura
(salidas del contador anual / actuaciones vistas) y las predicciones se expresan en salidas reales.

El modelo solo se activa si, en los últimos 7 días (no usados para entrenar), predice mejor que la
tasa base y que las reglas. Si no, el sistema sigue con base+reglas.

Uso: python -m auria.horario            (entrena si hay datos suficientes)
"""
import json
import math
from datetime import datetime

import numpy as np
import pandas as pd

from . import config
from .parques import PARQUES

MIN_DIAS = 21
MIN_EVENTOS = 300
DIAS_VALIDACION = 7
RUTA_MODELO = config.DIR_MODELO / "modelo_horario.txt"
RUTA_META = config.DIR_MODELO / "modelo_horario.json"
PARQUE_COD = {p: i for i, p in enumerate(PARQUES)}

FEATURES = ["parque_cod", "hora_sin", "hora_cos", "dow", "mes_sin", "mes_cos", "festivo", "noche_finde",
            "operacion_trafico", "temp", "humedad", "lluvia_1h", "lluvia_12h", "racha_kmh", "viento_sur",
            "nieve", "dias_sin_lluvia", "trafico_accidentes", "trafico_seguridad", "trafico_obras",
            "evento_nivel", "nuevas_parque_1h", "log_base", "log_reglas"]


def _features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    hora = pd.to_datetime(d["hora"], format="mixed")
    d["parque_cod"] = d["parque"].map(PARQUE_COD)
    d["hora_sin"], d["hora_cos"] = np.sin(2 * np.pi * hora.dt.hour / 24), np.cos(2 * np.pi * hora.dt.hour / 24)
    d["mes_sin"], d["mes_cos"] = np.sin(2 * np.pi * hora.dt.month / 12), np.cos(2 * np.pi * hora.dt.month / 12)
    d["dow"] = hora.dt.dayofweek
    d["log_base"] = np.log(d["lambda_base"].clip(lower=1e-6))
    d["log_reglas"] = np.log(d["lambda_reglas"].clip(lower=1e-6))
    for c in FEATURES:
        if c not in d:
            d[c] = 0
    return d[FEATURES].astype(float).fillna(0)


def dataset():
    from .resumen_online import resumir
    var = [pd.read_csv(p) for p in sorted((config.DIR_PREDICCION / "historial").glob("variables_*.csv"))]
    if not var:
        return None, None
    v = pd.concat(var, ignore_index=True)
    v["hora"] = pd.to_datetime(v["hora"], format="mixed")
    v = v.drop_duplicates(["parque", "hora"], keep="first")
    r = resumir(guardar=False)
    if r is None:
        return None, None
    diario, horario, acts = r
    obj = horario[[c for c in horario.columns if c.startswith("vistas_")]].copy()
    obj = obj.stack().rename("y").reset_index()
    obj.columns = ["hora", "parque", "y"]
    obj["parque"] = obj["parque"].str.replace("vistas_", "", regex=False)
    d = v.merge(obj, on=["hora", "parque"], how="inner")
    # cobertura del recolector en el periodo con variables
    h = horario[horario.index.isin(d["hora"].unique())]
    vistas = h[[c for c in h.columns if c.startswith("vistas_")]].sum().sum()
    cobertura = float(h["salidas"].sum() / vistas) if vistas > 0 else 1.0
    return d, max(1.0, min(cobertura, 3.0))


def _desviacion(y, mu):
    mu = np.clip(mu, 1e-6, None)
    t = np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / mu), 0) - (y - mu)
    return float(2 * t.mean())


def entrenar():
    import lightgbm as lgb
    d, cobertura = dataset()
    resumen = {"fecha": datetime.now().isoformat(timespec="minutes"), "activo": False}
    if d is None or d.empty:
        resumen["motivo"] = "aún no hay variables registradas o capturas"
        _guardar_meta(resumen)
        print(resumen["motivo"])
        return resumen
    dias = d["hora"].dt.date.nunique()
    eventos = int(d["y"].sum())
    resumen.update({"dias": dias, "eventos": eventos, "cobertura": round(cobertura, 2)})
    if dias < MIN_DIAS or eventos < MIN_EVENTOS:
        resumen["motivo"] = (f"datos insuficientes: {dias}/{MIN_DIAS} días y {eventos}/{MIN_EVENTOS} "
                             f"actuaciones. Se sigue con base+reglas.")
        _guardar_meta(resumen)
        print(resumen["motivo"])
        return resumen

    corte = d["hora"].max() - pd.Timedelta(days=DIAS_VALIDACION)
    tr, te = d[d["hora"] <= corte], d[d["hora"] > corte]
    params = {"objective": "poisson", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 50,
              "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
              "verbose": -1}
    m = lgb.train(params, lgb.Dataset(_features(tr), tr["y"]), num_boost_round=300)
    y = te["y"].to_numpy()
    metr = {
        "base": _desviacion(y, te["lambda_base"].to_numpy() / cobertura),
        "reglas": _desviacion(y, te["lambda_reglas"].to_numpy() / cobertura),
        "lightgbm": _desviacion(y, m.predict(_features(te))),
    }
    resumen["desviacion_poisson_validacion"] = {k: round(v, 4) for k, v in metr.items()}
    mejor = min(metr, key=metr.get)
    resumen["mejor"] = mejor
    if mejor == "lightgbm":
        final = lgb.train(params, lgb.Dataset(_features(d), d["y"]), num_boost_round=300)
        final.save_model(str(RUTA_MODELO))
        imp = pd.Series(final.feature_importance("gain"), index=FEATURES).sort_values(ascending=False)
        resumen.update({"activo": True, "importancia": imp.head(12).round(1).to_dict()})
    else:
        resumen["motivo"] = f"LightGBM no mejora a '{mejor}' en validación: se mantiene base+reglas"
        if RUTA_MODELO.exists():
            RUTA_MODELO.unlink()
    _guardar_meta(resumen)
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return resumen


def _guardar_meta(meta):
    RUTA_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


class ModeloHorario:
    def __init__(self, booster, cobertura):
        self.b, self.cobertura = booster, cobertura

    @classmethod
    def cargar(cls):
        if not (RUTA_MODELO.exists() and RUTA_META.exists()):
            return None
        meta = json.loads(RUTA_META.read_text(encoding="utf-8"))
        if not meta.get("activo"):
            return None
        import lightgbm as lgb
        return cls(lgb.Booster(model_file=str(RUTA_MODELO)), meta.get("cobertura", 1.0))

    def predecir(self, parque, hora, v, lam_normal, lam_reglas):
        if parque not in PARQUE_COD:
            return None
        fila = {"parque": parque, "hora": hora, "lambda_base": lam_normal, "lambda_reglas": lam_reglas,
                **{k: (int(x) if isinstance(x, bool) else x) for k, x in v.items() if x is not None}}
        mu_vistas = float(self.b.predict(_features(pd.DataFrame([fila])))[0])
        lam = mu_vistas * self.cobertura
        return lam if math.isfinite(lam) else None


if __name__ == "__main__":
    entrenar()
