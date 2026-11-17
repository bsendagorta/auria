"""Situaciones meteorológicas concretas de Bizkaia, por parque y hora.

No es lo mismo un sur racheado y seco que un noroeste constante con mar de fondo, aunque la racha sea la misma.
Cada hora de cada parque se clasifica (puede haber varias situaciones a la vez):

  SUR_RACHEADO        dirección 135-225°, racha ≥50 km/h, racha ≥1,6 × viento medio, HR <55 %
  NORTE_PERSISTENTE   dirección 280-30°, viento medio ≥25 km/h sostenido 6 h (constante, no racheado)
  GALERNA             mayo-octubre: viento 270-360°, la temperatura baja ≥5 °C en 2 h y racha ≥45 km/h
  BORRASCA            la presión cae ≥6 hPa en 12 h
  VIENTO_FUERTE       racha ≥70 km/h (cualquier dirección)
  LLUVIA_INTENSA      ≥10 mm en 1 h
  LLUVIA_PERSISTENTE  ≥60 mm en 72 h, o ≥30 mm en 24 h con el suelo húmedo
  TORMENTA            CAPE ≥800 J/kg y chubasco ≥3 mm/h (solo en previsión: el reanálisis no trae CAPE)
  HELADA              ≤0,5 °C
  NIEVE               nevada > 0
  CALOR               ≥30 °C, o noche (22-07 h) ≥20 °C
  SECO_PROLONGADO     ≥7 días sin lluvia y HR <50 %
  MAR_GRUESO          ola ≥4 m (solo parques de costa: Artaza, Urioste, Arratzu, Markina)

Variables derivadas que también se guardan: factor de racha (racha ÷ viento medio), tendencia de presión,
lluvia 24/72 h, anomalía de temperatura frente a los 7 días anteriores.
"""
import numpy as np
import pandas as pd

SITUACIONES = {
    "SUR_RACHEADO": ("🌬️", "Sur racheado"), "NORTE_PERSISTENTE": ("🌊", "Norte/noroeste persistente"),
    "GALERNA": ("⛈️", "Galerna"), "BORRASCA": ("🌀", "Borrasca (presión cayendo)"),
    "VIENTO_FUERTE": ("💨", "Rachas ≥70 km/h"), "LLUVIA_INTENSA": ("🌧️", "Lluvia intensa"),
    "LLUVIA_PERSISTENTE": ("☔", "Lluvia persistente / suelo saturado"), "TORMENTA": ("⚡", "Tormenta"),
    "HELADA": ("🧊", "Helada"), "NIEVE": ("❄️", "Nieve"), "CALOR": ("🔥", "Calor"),
    "SECO_PROLONGADO": ("🍂", "Seco prolongado"), "MAR_GRUESO": ("🌊", "Mar grueso (ola ≥4 m)"),
}
COSTA = {"ARTAZA", "URIOSTE", "ARRATZU", "MARKINA"}
# para contar un "día de situación" basta 1 hora en las breves y 3 en las de fondo
HORAS_DIA = {"GALERNA": 1, "LLUVIA_INTENSA": 1, "TORMENTA": 1, "BORRASCA": 2, "VIENTO_FUERTE": 2}

# Open-Meteo: nombre en previsión / en archivo (reanálisis)
VARS_PREVISION = ["temperature_2m", "relative_humidity_2m", "precipitation", "snowfall", "wind_speed_10m",
                  "wind_gusts_10m", "wind_direction_10m", "pressure_msl", "soil_moisture_0_to_1cm", "cape"]
VARS_ARCHIVO = ["temperature_2m", "relative_humidity_2m", "precipitation", "snowfall", "wind_speed_10m",
                "wind_gusts_10m", "wind_direction_10m", "pressure_msl", "soil_moisture_0_to_7cm"]


def _col(d, *nombres, defecto=np.nan):
    for n in nombres:
        if n in d:
            return pd.to_numeric(d[n], errors="coerce")
    return pd.Series(defecto, index=d.index, dtype=float)


def clasificar(m: pd.DataFrame) -> pd.DataFrame:
    """m: columnas horarias de Open-Meteo + 'parque' + 'hora' (y opcionalmente 'ola_m').
    Devuelve una fila por parque y hora con variables derivadas y una columna booleana por situación.
    Solo usa el pasado y la hora en curso (las ventanas son hacia atrás)."""
    out = []
    for p, d in m.sort_values(["parque", "hora"]).groupby("parque"):
        d = d.copy()
        d["hora"] = pd.to_datetime(d["hora"])
        t = _col(d, "temperature_2m")
        hr = _col(d, "relative_humidity_2m")
        ll = _col(d, "precipitation").fillna(0)
        vel = _col(d, "wind_speed_10m").fillna(0)
        rac = _col(d, "wind_gusts_10m").fillna(0)
        dirv = _col(d, "wind_direction_10m")
        pres = _col(d, "pressure_msl")
        suelo = _col(d, "soil_moisture_0_to_1cm", "soil_moisture_0_to_7cm")
        cape = _col(d, "cape")
        ola = _col(d, "ola_m")
        ll24 = ll.rolling(24, min_periods=1).sum()
        ll72 = ll.rolling(72, min_periods=1).sum()
        dia = pd.Series(ll.to_numpy(), index=d["hora"]).resample("D").sum()
        seco = (dia < 1).astype(int)
        racha_seca = seco.groupby((seco == 0).cumsum()).cumsum().shift(1).fillna(0)
        sin_lluvia = d["hora"].dt.floor("D").map(racha_seca).fillna(0).to_numpy()
        factor_racha = rac / vel.clip(lower=5)
        dpres12 = pres - pres.shift(12)
        dt2 = t - t.shift(2)
        anom = t - t.rolling(24 * 7, min_periods=24).mean().shift(24)
        sur = dirv.between(135, 225)
        norte = (dirv >= 280) | (dirv <= 30)
        noroeste = dirv.between(270, 360)
        mes = d["hora"].dt.month
        h = d["hora"].dt.hour
        suelo_hum = suelo >= (suelo.quantile(0.75) if suelo.notna().sum() > 100 else 0.35)
        s = pd.DataFrame({
            "parque": p, "hora": d["hora"].to_numpy(),
            "temp": t.to_numpy(), "humedad": hr.to_numpy(), "lluvia_1h": ll.to_numpy(),
            "lluvia_24h": ll24.to_numpy(), "lluvia_72h": ll72.to_numpy(), "viento_kmh": vel.to_numpy(),
            "racha_kmh": rac.to_numpy(), "dir_viento": dirv.to_numpy(), "factor_racha": factor_racha.round(2).to_numpy(),
            "presion": pres.to_numpy(), "dpresion_12h": dpres12.to_numpy(), "anomalia_temp": anom.to_numpy(),
            "dias_sin_lluvia": sin_lluvia, "ola_m": ola.to_numpy(),
        })
        s["SUR_RACHEADO"] = (sur & (rac >= 50) & (factor_racha >= 1.6) & (hr < 55)).to_numpy()
        s["NORTE_PERSISTENTE"] = (norte & (vel.rolling(6, min_periods=6).min() >= 25)).to_numpy()
        s["GALERNA"] = (mes.between(5, 10) & noroeste & (dt2 <= -5) & (rac >= 45)).to_numpy()
        s["BORRASCA"] = (dpres12 <= -6).to_numpy()
        s["VIENTO_FUERTE"] = (rac >= 70).to_numpy()
        s["LLUVIA_INTENSA"] = (ll >= 10).to_numpy()
        s["LLUVIA_PERSISTENTE"] = ((ll72 >= 60) | ((ll24 >= 30) & suelo_hum)).to_numpy()
        s["TORMENTA"] = ((cape >= 800) & (ll >= 3)).to_numpy()
        s["HELADA"] = (t <= 0.5).to_numpy()
        s["NIEVE"] = (_col(d, "snowfall").fillna(0) > 0).to_numpy()
        s["CALOR"] = ((t >= 30) | (((h >= 22) | (h <= 7)) & (t >= 20))).to_numpy()
        s["SECO_PROLONGADO"] = ((sin_lluvia >= 7) & (hr < 50)).to_numpy()
        s["MAR_GRUESO"] = ((ola >= 4) & (p in COSTA)).to_numpy()
        out.append(s)
    return pd.concat(out, ignore_index=True)


def activas(fila) -> list:
    return [k for k in SITUACIONES if bool(fila.get(k, False))]


def texto(sits, fila=None) -> str:
    if not sits:
        return ""
    partes = []
    for k in sits:
        ico, nom = SITUACIONES[k]
        extra = ""
        if fila is not None and k in ("SUR_RACHEADO", "VIENTO_FUERTE", "NORTE_PERSISTENTE", "GALERNA"):
            extra = f" {fila.get('racha_kmh', 0):.0f} km/h"
            if k == "SUR_RACHEADO":
                extra += f", HR {fila.get('humedad', 0):.0f} %"
        partes.append(f"{ico} {nom}{extra}")
    return " · ".join(partes)


def dias_por_mes(horaria: pd.DataFrame) -> pd.DataFrame:
    """Días de cada situación por parque, año y mes (día = ≥3 h, o ≥1-2 h en las breves)."""
    h = horaria.copy()
    h["fecha"] = pd.to_datetime(h["hora"]).dt.floor("D")
    g = h.groupby(["parque", "fecha"])[list(SITUACIONES)].sum()
    dias = pd.DataFrame({k: g[k] >= HORAS_DIA.get(k, 3) for k in SITUACIONES}).astype(int).reset_index()
    dias["anio"], dias["mes"] = dias["fecha"].dt.year, dias["fecha"].dt.month
    out = dias.groupby(["parque", "anio", "mes"])[list(SITUACIONES)].sum()
    out["dias_mes"] = dias.groupby(["parque", "anio", "mes"]).size()
    return out.reset_index()
