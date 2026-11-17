"""Accidentes con hora exacta en las carreteras de Bizkaia y su relación con la meteo de ESA hora.

Fuente: histórico de incidencias de tráfico de Open Data Euskadi (sin clave)
    https://api.euskadi.eus/traffic/v1.0/incidences/byDate/{a}/{m}/{d}?_page=n
Cada incidencia trae tipo, causa, municipio, carretera, PK, coordenadas e inicio al minuto. Se guardan las
de Bizkaia (sin Bilbao ciudad ni la fuente municipal), de 2021 en adelante:
    accidentes   (alcance, salida de vía, vuelco, atropello…)
    obstáculos   (caída de objetos, desprendimientos, socavones, árboles; lo que suele traer el temporal)

Modelo (por hora y zona de parque, solo meses con publicación completa):
    accidentes(parque, hora) ~ Poisson( base · exp(Σ β·x) )
    base = accidentes de ese parque en ese MES × reparto típico por tipo de día y hora.
    Al fijar el total del mes, lo que se mide es cómo se reparten los accidentes dentro del mes según
    la meteo de cada hora: no lo confunde la estación, ni que un mes se publiquen más incidencias.
    x = lluvia débil / moderada / fuerte, primera lluvia tras ≥3 días secos, posible niebla (HR ≥97 %,
    viento <6 km/h, sin lluvia), helada, nieve, rachas ≥70, sur racheado, norte persistente, lluvia
    persistente, calor, borrasca.
Validación: se ajusta con 2021-2024 y se prueba en 2025-2026. Solo se usa en directo si mejora.

Uso:  python -m auria.accidentes_hora [--descargar] [--desde 2021-01-01]
Salidas: datos/trafico/incidencias_bizkaia.csv.gz · datos/modelo/accidentes_hora.json ·
         informes/accidentes_hora.md
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
import requests
from scipy.optimize import minimize

from . import config
from .parques import PARQUES, parque_de_nombre, parque_mas_cercano

BASE = "https://api.euskadi.eus/traffic/v1.0/"
DIR = config.DATOS / "trafico"
RUTA = DIR / "incidencias_bizkaia.csv.gz"
RUTA_DIAS = DIR / "incidencias_dias_descargados.txt"
RUTA_MODELO = config.DIR_MODELO / "accidentes_hora.json"
OBSTACULOS = ("caída de objetos", "caida de objetos", "desprendimiento", "socavón", "socavon", "árbol",
              "arbol", "inundación", "inundacion", "balsa de agua", "agua", "barro", "nieve", "hielo")
GUARDAR = {"Accidente", "Seguridad vial", "Otras incidencias", "Vialidad invernal tramos", "Evento"}
VARIABLES = {
    "lluvia_debil": "Lluvia débil (0,1-1 mm/h)", "lluvia_moderada": "Lluvia moderada (1-4 mm/h)",
    "lluvia_fuerte": "Lluvia fuerte (≥4 mm/h)", "primera_lluvia": "Primera lluvia tras ≥3 días secos",
    "niebla": "Posible niebla (HR ≥97 %, sin viento)", "HELADA": "Helada", "NIEVE": "Nieve",
    "VIENTO_FUERTE": "Rachas ≥70 km/h", "SUR_RACHEADO": "Sur racheado", "NORTE_PERSISTENTE": "Norte persistente",
    "LLUVIA_PERSISTENTE": "Lluvia persistente", "CALOR": "Calor", "BORRASCA": "Borrasca",
    "fiesta_local": "Fiesta local en la zona (y su víspera por la tarde)",
}
_S = requests.Session()
_S.headers["User-Agent"] = config.USER_AGENT


# ------------------------------------------------------------------ descarga
def _get(ruta):
    for i in range(4):
        try:
            r = _S.get(BASE + ruta, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return {}
        except (requests.RequestException, ValueError):
            pass
        time.sleep(3 * (i + 1))
    return None


def _dia(d):
    filas, p = [], 1
    while True:
        j = _get(f"incidences/byDate/{d:%Y/%m/%d}?_page={p}")
        if j is None:
            return None                        # fallo de red: se reintenta otro día
        for x in j.get("incidences", []) or []:
            if (x.get("province") or "").upper() != "BIZKAIA" or x.get("incidenceType") not in GUARDAR:
                continue
            filas.append({k: x.get(k) for k in ("incidenceId", "sourceId", "incidenceType", "cause", "cityTown",
                                                 "road", "pkStart", "direction", "startDate", "endDate",
                                                 "incidenceLevel", "latitude", "longitude")})
        if p >= (j.get("totalPages") or 1):
            return filas
        p += 1


def descargar(desde="2021-01-01", hilos=12):
    DIR.mkdir(parents=True, exist_ok=True)
    hechos = set(RUTA_DIAS.read_text().split()) if RUTA_DIAS.exists() else set()
    d0, d1 = date.fromisoformat(desde), date.today() - timedelta(days=1)
    dias = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    dias = [d for d in dias if d.isoformat() not in hechos or d >= d1 - timedelta(days=3)]
    print(f"Días por descargar: {len(dias)}", flush=True)
    nuevas, ok = [], []
    with ThreadPoolExecutor(hilos) as ex:
        for i, (d, r) in enumerate(zip(dias, ex.map(_dia, dias))):
            if r is not None:
                nuevas += r
                ok.append(d.isoformat())
            if i % 200 == 0:
                print(f"  {i}/{len(dias)} · {len(nuevas)} incidencias", flush=True)
    previo = pd.read_csv(RUTA, dtype=str) if RUTA.exists() else pd.DataFrame()
    todo = pd.concat([previo, pd.DataFrame(nuevas).astype(str)], ignore_index=True)
    # la API repite incidencias en varios días y páginas: una por id
    todo = todo.drop_duplicates("incidenceId", keep="first")
    todo.to_csv(RUTA, index=False, compression="gzip")
    RUTA_DIAS.write_text("\n".join(sorted(hechos | set(ok))))
    return todo


# ------------------------------------------------------------------ preparación
def preparar(inc=None):
    inc = inc if inc is not None else pd.read_csv(RUTA, dtype=str)
    d = inc[(inc["sourceId"] != "5")].copy()
    d["t"] = pd.to_datetime(d["startDate"].str[:16], errors="coerce")
    d = d.dropna(subset=["t"])
    ciudad = d["cityTown"].fillna("").str.strip()
    d = d[~ciudad.str.upper().isin(["BILBAO", "BILBO"])]
    causa = d["cause"].fillna("").str.lower()
    d["clase"] = np.where(d["incidenceType"] == "Accidente", "accidente",
                          np.where(causa.str.contains("|".join(OBSTACULOS)), "obstaculo", "otra"))
    lat = pd.to_numeric(d["latitude"], errors="coerce")
    lon = pd.to_numeric(d["longitude"], errors="coerce")
    par = d["cityTown"].map(lambda n: parque_de_nombre(n) if isinstance(n, str) and n else None)
    cerca = [parque_mas_cercano(a, o) if pd.notna(a) and pd.notna(o) and 42.9 < a < 43.5 else None
             for a, o in zip(lat, lon)]
    d["parque"] = [p if p in PARQUES else c for p, c in zip(par, cerca)]
    d = d[d["parque"].isin(PARQUES)]
    d["hora"] = d["t"].dt.floor("h")
    return d


def meses_completos(d, clase="accidente"):
    """Meses en los que la publicación parece completa: accidentes ≥40 % de la mediana mensual."""
    m = d[d["clase"] == clase].groupby(d["hora"].dt.to_period("M")).size()
    if m.empty:
        return set()
    return set(m[m >= 0.4 * m.median()].index)


def tabla_horaria(d, clase, sit):
    """Una fila por parque y hora (solo meses completos) con accidentes, base y variables meteo."""
    from .riesgo_trafico import tipo_dia
    meses = meses_completos(d, clase)
    x = sit.copy()
    x["hora"] = pd.to_datetime(x["hora"])
    x["mes"] = x["hora"].dt.to_period("M")
    x = x[x["mes"].isin(meses)]
    y = d[d["clase"] == clase].groupby(["parque", "hora"]).size().rename("y")
    x = x.merge(y, left_on=["parque", "hora"], right_index=True, how="left")
    x["y"] = x["y"].fillna(0)
    x["tipo_dia"] = x["hora"].map(tipo_dia)
    x["h"] = x["hora"].dt.hour
    x["anio"] = x["hora"].dt.year
    # variables
    ll = x["lluvia_1h"].fillna(0)
    x["lluvia_debil"] = ll.between(0.1, 1, inclusive="left")
    x["lluvia_moderada"] = ll.between(1, 4, inclusive="left")
    x["lluvia_fuerte"] = ll >= 4
    x["primera_lluvia"] = (ll >= 0.1) & (x["dias_sin_lluvia"] >= 3)
    x["niebla"] = (x["humedad"] >= 97) & (x["viento_kmh"] < 6) & (ll < 0.1)
    x["fiesta_local"] = _fiestas(x)
    return x


def _fiestas(x):
    """Hora en la que algún municipio de la zona del parque celebra su fiesta local (o la víspera desde las 18 h)."""
    from .parques import INE_A_PARQUE
    ruta = config.DATOS / "festivos_locales.csv"
    if not ruta.exists():
        return False
    f = pd.read_csv(ruta, dtype={"cod_ine": str})
    f["parque"] = f["cod_ine"].map(INE_A_PARQUE)
    f["fecha"] = pd.to_datetime(f["fecha"]).dt.date
    dias = set(zip(f["parque"], f["fecha"]))
    vispera = set(zip(f["parque"], f["fecha"] - pd.Timedelta(days=1)))
    fecha = x["hora"].dt.date
    en_dia = pd.Series([(p, d) in dias for p, d in zip(x["parque"], fecha)], index=x.index)
    en_visp = pd.Series([(p, d) in vispera for p, d in zip(x["parque"], fecha)], index=x.index) & (x["hora"].dt.hour >= 18)
    return en_dia | en_visp


def _reparto(tr):
    s = tr.groupby(["tipo_dia", "h"])["y"].sum() + 0.5
    return s / s.mean()


def _base(x, reparto):
    w = x.set_index(["tipo_dia", "h"]).index.map(reparto).to_numpy(float)
    x = x.assign(w=w)
    tot = x.groupby(["parque", "mes"])["y"].transform("sum")
    sw = x.groupby(["parque", "mes"])["w"].transform("sum")
    return (tot * x["w"] / sw).to_numpy(float)


def _ajustar(y, b, X, lam=2.0):
    k = X.shape[1]
    lb = np.log(np.clip(b, 1e-9, None))

    def f(g):
        eta = lb + X @ g
        return float(np.sum(np.exp(eta) - y * eta) + lam * g @ g)

    def gr(g):
        mu = np.exp(lb + X @ g)
        return (mu - y) @ X + 2 * lam * g

    res = minimize(f, np.zeros(k), jac=gr, method="L-BFGS-B", bounds=[(-3, 3)] * k)
    g = res.x
    mu = np.exp(lb + X @ g)
    H = (X * mu[:, None]).T @ X + 2 * lam * np.eye(k)
    se = np.sqrt(np.clip(np.diag(np.linalg.inv(H)), 0, None))
    return g, se


def _dev(y, mu):
    mu = np.clip(mu, 1e-9, None)
    return float(2 * np.sum(np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / mu), 0) - (y - mu)))


def modelo(x, nombre):
    vars_ = [v for v in VARIABLES if v in x and x[v].fillna(False).astype(bool).sum() >= 50]
    x = x.copy()
    for v in vars_:
        x[v] = x[v].fillna(False).astype(float)
    tr, te = x[x["anio"] <= 2024], x[x["anio"] >= 2025]
    rep = _reparto(tr)
    out = {"clase": nombre, "variables": {}, "validacion": None, "activo": False,
           "eventos": int(x["y"].sum()), "horas": int(len(x)),
           "meses": int(x["mes"].nunique()), "desde": str(x["hora"].min())[:10], "hasta": str(x["hora"].max())[:10]}
    if tr["y"].sum() < 200 or not vars_:
        out["motivo"] = "pocos casos"
        return out
    g, _ = _ajustar(tr["y"].to_numpy(float), _base(tr, rep), tr[vars_].to_numpy(float))
    if te["y"].sum() >= 50:
        b = _base(te, rep)
        mu = b * np.exp(te[vars_].to_numpy(float) @ g)
        mu *= te.groupby(["parque", "mes"])["y"].transform("sum").to_numpy(float) / np.clip(
            pd.Series(mu, index=te.index).groupby([te["parque"], te["mes"]]).transform("sum").to_numpy(float),
            1e-9, None)
        d0, d1 = _dev(te["y"].to_numpy(float), b), _dev(te["y"].to_numpy(float), mu)
        out["validacion"] = {"dev_base": round(d0, 1), "dev_meteo": round(d1, 1),
                             "mejora_pct": round(100 * (1 - d1 / d0), 2), "eventos_test": int(te["y"].sum())}
        out["activo"] = d1 < d0
    # ajuste final con todo
    g, se = _ajustar(x["y"].to_numpy(float), _base(x, _reparto(x)), x[vars_].to_numpy(float))
    for i, v in enumerate(vars_):
        con = x[v] > 0
        out["variables"][v] = {"rr": round(float(np.exp(g[i])), 2),
                               "lo": round(float(np.exp(g[i] - 1.96 * se[i])), 2),
                               "hi": round(float(np.exp(g[i] + 1.96 * se[i])), 2),
                               "horas": int(con.sum()), "eventos": int(x.loc[con, "y"].sum())}
    return out


def informe(res):
    L = ["# AURIA — Accidentes y obstáculos con hora exacta frente a la meteo de esa hora",
         f"Generado {date.today()}. Incidencias de tráfico de Open Data Euskadi (Bizkaia sin Bilbao ciudad) × "
         "meteo horaria ERA5 de la zona de cada parque.", ""]
    for r in res.values():
        L += [f"## {r['clase'].capitalize()}: {r['eventos']:,} casos en {r['meses']} meses completos "
              f"({r['desde']} → {r['hasta']})"]
        if r.get("validacion"):
            v = r["validacion"]
            L.append(f"Validación 2025-2026 ({v['eventos_test']} casos): desviación {v['dev_base']} → "
                     f"{v['dev_meteo']} (**{v['mejora_pct']:+.2f} %**) · en directo: "
                     f"{'sí' if r['activo'] else 'no'}")
        L += ["", "| situación en esa hora | riesgo relativo | IC 95 % | horas | casos |", "|---|---:|---|---:|---:|"]
        for k, e in sorted(r["variables"].items(), key=lambda t: -t[1]["rr"]):
            marca = " ✓" if e["lo"] > 1 or e["hi"] < 1 else ""
            L.append(f"| {VARIABLES[k]} | ×{e['rr']}{marca} | {e['lo']}-{e['hi']} | {e['horas']:,} | {e['eventos']} |")
        L.append("")
    L.append("_Riesgo relativo = accidentes en una hora con esa situación ÷ en una hora parecida (mismo parque, "
             "mes, tipo de día y hora) sin ella. ✓ = efecto claro._")
    (config.INFORMES / "accidentes_hora.md").write_text("\n".join(L), encoding="utf-8")


def main(argv=None):
    from .efectos_meteo import RUTA_HORARIA
    from .situaciones import clasificar
    ap = argparse.ArgumentParser()
    ap.add_argument("--descargar", action="store_true")
    ap.add_argument("--desde", default="2021-01-01")
    a = ap.parse_args(argv)
    inc = descargar(a.desde) if (a.descargar or not RUTA.exists()) else pd.read_csv(RUTA, dtype=str)
    d = preparar(inc)
    print(d.groupby("clase").size().to_string())
    sit = clasificar(pd.read_csv(RUTA_HORARIA))
    res = {}
    for clase in ("accidente", "obstaculo"):
        res[clase] = modelo(tabla_horaria(d, clase, sit), clase)
    res["fecha"] = date.today().isoformat()
    RUTA_MODELO.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    informe({k: v for k, v in res.items() if isinstance(v, dict)})
    print(open(config.INFORMES / "accidentes_hora.md", encoding="utf-8").read())


# ------------------------------------------------------------------ uso en directo
@lru_cache(maxsize=1)
def _cargar(_mtime):
    try:
        return json.loads(RUTA_MODELO.read_text(encoding="utf-8"))
    except Exception:
        return {}


# a qué tipo de salida de bomberos se aplica cada modelo horario (obstáculos en calzada = árboles, objetos y
# desprendimientos: es lo más parecido con hora exacta a las salidas de "saneados, árboles, achiques")
APLICA = {"accidente": "TRAFICO", "obstaculo": "METEO_ASISTENCIA"}
NOMBRE = {"accidente": "accidentes", "obstaculo": "caídas de objetos/árboles"}


def factor_hora(v: dict, clase="accidente"):
    """(multiplicador, [textos]) según la meteo de la hora, o None si no hay modelo validado."""
    try:
        m = _cargar(RUTA_MODELO.stat().st_mtime).get(clase, {})
    except FileNotFoundError:
        return None
    if not m.get("activo"):
        return None
    ll = float(v.get("lluvia_1h") or 0)
    x = {"lluvia_debil": 0.1 <= ll < 1, "lluvia_moderada": 1 <= ll < 4, "lluvia_fuerte": ll >= 4,
         "primera_lluvia": ll >= 0.1 and float(v.get("dias_sin_lluvia") or 0) >= 3,
         "niebla": float(v.get("humedad") or 0) >= 97 and float(v.get("viento_kmh") or 99) < 6 and ll < 0.1}
    # si la hora no trae la situación ya clasificada, se deduce de la variable básica
    x.setdefault("VIENTO_FUERTE", v.get("VIENTO_FUERTE", float(v.get("racha_kmh") or 0) >= 70))
    x.setdefault("HELADA", v.get("HELADA", float(v.get("temp", 15)) <= 0.5))
    x.setdefault("NIEVE", v.get("NIEVE", float(v.get("nieve") or 0) > 0))
    x.setdefault("CALOR", v.get("CALOR", float(v.get("temp", 15)) >= 30))
    x.setdefault("fiesta_local", "Fiesta local" in str(v.get("evento_nombre", "")))
    k, textos = 1.0, []
    for nombre, e in m.get("variables", {}).items():
        activa = x.get(nombre, bool(v.get(nombre, False)))
        if activa and (e["lo"] > 1 or e["hi"] < 1):          # solo efectos claros
            k *= e["rr"]
            if e["rr"] >= 1.1:
                textos.append(f"{VARIABLES[nombre]}: {NOMBRE[clase]} ×{e['rr']:.1f} (medido por horas)")
    return min(max(k, 0.5), 4.0 if clase == "accidente" else 6.0), textos


if __name__ == "__main__":
    main()
