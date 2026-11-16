"""Combina las capturas de todos los recolectores y las convierte en series útiles.

Uso: python -m auria.resumen_online
Salida (datos/procesado/):
  online_actuaciones.csv  una fila por actuación (primera/última vez vista, parque, familia, vehículos)
  online_horario.csv      salidas por hora en toda Bizkaia (contador anual) + actuaciones vistas por parque
  online_diario.csv       lo mismo por día
"""
from pathlib import Path

import pandas as pd

from . import config
from .familias import familia
from .parques import PARQUES, parque_de_nombre

HUECO_MIN = 30   # si una actuación desaparece más de 30 min, la siguiente aparición es otra actuación


def cargar(raiz=None):
    raiz = Path(raiz or config.DIR_ONLINE)
    cap = [pd.read_csv(p) for p in sorted(raiz.glob("**/capturas_*.csv"))]
    act = [pd.read_csv(p, keep_default_na=False) for p in sorted(raiz.glob("**/activas_*.csv"))]
    cap = pd.concat(cap, ignore_index=True) if cap else pd.DataFrame()
    act = pd.concat(act, ignore_index=True) if act else pd.DataFrame()
    if not cap.empty:
        cap["t"] = pd.to_datetime(cap["ts"].str[:19])        # hora local
        cap = cap.sort_values("t").drop_duplicates("ts")
    if not act.empty:
        act["t"] = pd.to_datetime(act["ts"].str[:19])
        act = act.drop_duplicates(["ts", "tipo", "ubicacion", "zona"])
    return cap, act


def actuaciones(act: pd.DataFrame) -> pd.DataFrame:
    if act.empty:
        return pd.DataFrame(columns=["tipo", "ubicacion", "zona", "primera_vez", "ultima_vez",
                                     "n_capturas", "max_vehiculos", "vehiculos", "parque", "familia"])
    a = act.sort_values(["tipo", "ubicacion", "zona", "t"]).copy()
    clave = ["tipo", "ubicacion", "zona"]
    nueva = (a[clave] != a[clave].shift()).any(axis=1) | (a["t"].diff() > pd.Timedelta(minutes=HUECO_MIN))
    a["id"] = nueva.cumsum()
    g = a.groupby("id")
    out = pd.DataFrame({
        "tipo": g["tipo"].first(), "ubicacion": g["ubicacion"].first(), "zona": g["zona"].first(),
        "primera_vez": g["t"].min(), "ultima_vez": g["t"].max(), "n_capturas": g.size(),
        "max_vehiculos": g["n_vehiculos"].max(), "vehiculos": g["vehiculos"].last(),
    }).reset_index(drop=True)
    out["duracion_min"] = (out["ultima_vez"] - out["primera_vez"]).dt.total_seconds() / 60
    out["parque"] = out["ubicacion"].map(parque_de_nombre)
    out["familia"] = out["tipo"].map(familia)
    return out


def incrementos(cap: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Salidas por periodo = salto del contador anual entre el último valor de cada periodo."""
    c = cap[cap["ok"] == 1].dropna(subset=["salidas_anio"])
    if c.empty:
        return pd.DataFrame(columns=["salidas", "contador_anio", "capturas"])
    s = c.set_index("t")["salidas_anio"].astype(float).resample(freq).last()
    s_ff = s.ffill()
    d = s_ff.diff()
    reinicio = d < 0                          # 1 de enero: el contador vuelve a 0
    d[reinicio] = s_ff[reinicio]
    out = pd.DataFrame({"salidas": d, "contador_anio": s,
                        "capturas": c.set_index("t")["salidas_anio"].resample(freq).size()})
    # periodos sin capturas: salidas desconocidas (el salto se acumula en el siguiente con captura)
    hueco = out["capturas"] == 0
    out.loc[hueco, "salidas"] = float("nan")
    return out.iloc[1:]


def resumir(raiz=None, guardar=True):
    cap, act = cargar(raiz)
    if cap.empty:
        print("Aún no hay capturas.")
        return None
    acts = actuaciones(act)
    horario = incrementos(cap, "h")
    diario = incrementos(cap, "D")
    if not acts.empty:
        acts["hora"] = acts["primera_vez"].dt.floor("h")
        vistas = acts.pivot_table(index="hora", columns="parque", values="tipo", aggfunc="count", fill_value=0)
        vistas = vistas.reindex(columns=list(PARQUES), fill_value=0).add_prefix("vistas_")
        horario = horario.join(vistas, how="left").fillna({c: 0 for c in vistas.columns})
        dv = vistas.resample("D").sum()
        diario = diario.join(dv, how="left")
    if guardar:
        acts.to_csv(config.PROCESADO / "online_actuaciones.csv", index=False)
        horario.to_csv(config.PROCESADO / "online_horario.csv")
        diario.to_csv(config.PROCESADO / "online_diario.csv")
    fallos = int((cap["ok"] == 0).sum())
    print(f"Capturas: {len(cap)} (fallidas: {fallos}) | actuaciones distintas: {len(acts)}")
    if len(diario):
        print(diario[["salidas", "capturas"]].tail(7).to_string())
    return diario, horario, acts


if __name__ == "__main__":
    resumir()
