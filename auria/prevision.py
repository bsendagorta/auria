"""Predicción horaria por parque para las próximas horas (por defecto 6).

  λ(parque, hora, familia) = tasa_base(parque, familia, mes, franja) × multiplicadores(meteo, calendario,
                             tráfico, eventos)           [o modelo LightGBM si ya está entrenado y validado]
  P(≥1 salida) = 1 - exp(-λ)       riesgo relativo = λ / λ_normal       nivel = semáforo por riesgo relativo

Uso: python -m auria.prevision [--horas 6]
Salida: prediccion/ultima.json  y  prediccion/historial/{prediccion,variables}_AAAA-MM.csv
"""
import argparse
import json
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from . import situaciones, base_horaria, calendario, config, eventos, reglas, riesgo_trafico, trafico
from .familias import FAMILIAS
from .parques import PARQUES

TZ = ZoneInfo("Europe/Madrid")
NIVELES = [(1.5, "verde"), (2.5, "amarillo"), (4.0, "naranja"), (float("inf"), "rojo")]
from .situaciones import VARS_PREVISION as VARS_HORA   # incluye viento medio, presión, suelo y CAPE


def nivel(ratio: float) -> str:
    return next(n for lim, n in NIVELES if ratio < lim)


# --------------------------------------------------------------------------- meteo
def meteo_parques(dias_pasados=14, dias_futuros=2) -> pd.DataFrame:
    ids = list(PARQUES)
    params = {
        "latitude": ",".join(str(PARQUES[p]["lat"]) for p in ids),
        "longitude": ",".join(str(PARQUES[p]["lon"]) for p in ids),
        "hourly": ",".join(VARS_HORA), "past_days": dias_pasados, "forecast_days": dias_futuros,
        "timezone": "Europe/Madrid", "wind_speed_unit": "kmh",
    }
    r = None
    for intento in range(3):
        try:
            r = requests.get(config.OPENMETEO_PREVISION, params=params, timeout=60,
                             headers={"User-Agent": config.USER_AGENT})
            if r.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(10 * (intento + 1))
    r.raise_for_status()
    res = r.json()
    res = res if isinstance(res, list) else [res]
    partes = []
    for p, bloque in zip(ids, res):
        d = pd.DataFrame(bloque["hourly"])
        d["parque"] = p
        partes.append(d)
    crudo = pd.concat(partes, ignore_index=True)
    # oleaje en los parques de costa (Open-Meteo Marine); si falla, se sigue sin él
    from .situaciones import COSTA, clasificar
    try:
        cos = [p for p in ids if p in COSTA]
        rm = requests.get("https://marine-api.open-meteo.com/v1/marine", timeout=30, params={
            "latitude": ",".join(str(PARQUES[p]["lat"] + 0.08) for p in cos),
            "longitude": ",".join(str(PARQUES[p]["lon"]) for p in cos), "hourly": "wave_height",
            "past_days": dias_pasados, "forecast_days": dias_futuros, "timezone": "Europe/Madrid"})
        rm.raise_for_status()
        jm = rm.json()
        jm = jm if isinstance(jm, list) else [jm]
        olas = pd.concat([pd.DataFrame(b["hourly"]).assign(parque=p) for p, b in zip(cos, jm)])
        crudo = crudo.merge(olas.rename(columns={"wave_height": "ola_m"}), on=["parque", "time"], how="left")
    except Exception as e:
        print(f"Aviso oleaje: {e}")
    return meteo_desde_crudo(crudo)


def meteo_desde_crudo(crudo):
    """Horas crudas de Open-Meteo (columna 'time') -> variables de riesgo + situaciones por parque y hora."""
    from .situaciones import clasificar
    base = preparar_meteo(crudo)
    sit = clasificar(crudo.rename(columns={"time": "hora"}))
    extra = [c for c in sit.columns if c not in base.columns or c in ("parque", "hora")]
    return base.merge(sit[extra], on=["parque", "hora"], how="left")


def preparar_meteo(m: pd.DataFrame) -> pd.DataFrame:
    """Columnas horarias crudas de Open-Meteo -> variables de riesgo (sin mirar al futuro)."""
    m = m.rename(columns={"time": "hora"}).copy()
    m["hora"] = pd.to_datetime(m["hora"])
    m = m.sort_values(["parque", "hora"])
    out = []
    for p, d in m.groupby("parque"):
        d = d.copy()
        lluvia = d["precipitation"].fillna(0)
        d["lluvia_12h"] = lluvia.shift(1).rolling(12, min_periods=1).sum().fillna(0)
        dia = d.set_index("hora")["precipitation"].fillna(0).resample("D").sum()
        seco = (dia < 1).astype(int)
        racha = seco.groupby((seco == 0).cumsum()).cumsum()           # días secos seguidos hasta ese día
        d["dias_sin_lluvia"] = d["hora"].dt.floor("D").map(racha.shift(1)).fillna(0)
        out.append(d)
    m = pd.concat(out)
    return pd.DataFrame({
        "parque": m["parque"], "hora": m["hora"],
        "temp": m["temperature_2m"], "humedad": m["relative_humidity_2m"],
        "lluvia_1h": m["precipitation"].fillna(0), "lluvia_12h": m["lluvia_12h"],
        "racha_kmh": m["wind_gusts_10m"].fillna(0),
        "viento_sur": m["wind_direction_10m"].between(135, 225) & (m["wind_gusts_10m"] >= 30),
        "nieve": m["snowfall"].fillna(0), "dias_sin_lluvia": m["dias_sin_lluvia"],
    })


# --------------------------------------------------------------------------- estado en directo
def estado_directo():
    """Últimas actuaciones activas por parque (de las capturas del recolector)."""
    try:
        from .resumen_online import actuaciones, cargar
        cap, act = cargar()
        if cap.empty or act.empty:
            return {}, [], None
        ult = act["t"].max()
        ahora = act[act["t"] == ult]
        acts = actuaciones(act)
        hace_1h = acts[acts["primera_vez"] >= ult - pd.Timedelta(hours=1)]
        from .parques import parque_de_nombre
        lista = [{"tipo": r.tipo, "ubicacion": r.ubicacion, "zona": r.zona, "vehiculos": r.vehiculos,
                  "parque": parque_de_nombre(r.ubicacion)} for r in ahora.itertuples()]
        por_parque = {p: {"activas": sum(1 for x in lista if x["parque"] == p),
                          "nuevas_1h": int((hace_1h["parque"] == p).sum())} for p in PARQUES}
        ok = cap[cap["ok"] == 1]
        contador = None
        if not ok.empty:
            u = ok.iloc[-1]
            contador = {"ts": u["ts"], "desde_8": int(u["salidas_desde_8"]), "anio": int(u["salidas_anio"])}
        return por_parque, lista, contador
    except Exception as e:
        print(f"Aviso estado en directo: {e}")
        return {}, [], None


# --------------------------------------------------------------------------- predicción
def predecir(horas=6, meteo=None, traf=None, ahora=None, guardar=True):
    ahora = ahora or datetime.now(TZ)
    h0 = pd.Timestamp(ahora.replace(tzinfo=None)).floor("h")
    franjas = [h0 + pd.Timedelta(hours=i) for i in range(horas)]
    if not (config.DIR_MODELO / "base_horaria.csv").exists():
        raise SystemExit("Falta datos/modelo/base_horaria.csv: ejecuta antes `python -m auria.historico` "
                         "(o la tarea de reentreno con 'historico' activado).")
    base = base_horaria.cargar().set_index(["parque", "familia", "mes", "franja"])["tasa_hora"]
    fuentes = {"meteo": True, "trafico": True}
    if meteo is None:
        try:
            meteo = meteo_parques()
        except Exception as e:
            print(f"Aviso meteo: {e}")
            meteo, fuentes["meteo"] = pd.DataFrame(), False
    if traf is None:
        traf = trafico.resumen_hoy()
    if traf is None:
        fuentes["trafico"] = False
    evs = eventos.cargar()
    directo, activas, contador = estado_directo()
    modelo = cargar_modelo()
    efectos_sit = cargar_efectos()

    parques_out, filas_hist, filas_vars = [], [], []
    for p, info in PARQUES.items():
        horas_out = []
        lluvias = []
        for i, hora in enumerate(franjas):
            fr = base_horaria.franja_de_hora(hora.hour)
            normal = {f: float(base.get((p, f, hora.month, fr), 0.0)) for f in FAMILIAS}
            # tráfico: forma horaria y por tipo de día de los accidentes reales (DGT), sin cambiar el nivel SPEIS
            normal["TRAFICO"] *= riesgo_trafico.factor(p, hora)[0]
            v = {"temp": 15.0, "humedad": 70.0, "lluvia_1h": 0.0, "lluvia_12h": 0.0, "racha_kmh": 0.0,
                 "viento_sur": False, "nieve": 0.0, "dias_sin_lluvia": 0, "dir_viento": float("nan"),
                 "viento_kmh": 0.0}
            if not meteo.empty:
                fila = meteo[(meteo["parque"] == p) & (meteo["hora"] == hora)]
                if len(fila):
                    v.update({k: (bool(x) if (k == "viento_sur" or k in situaciones.SITUACIONES) else float(x))
                              for k, x in fila.iloc[0].drop(["parque", "hora"]).items() if pd.notna(x)})
            v.update(calendario.variables_hora(hora))
            if traf is not None and i <= 1:
                v["trafico_accidentes"] = int(traf.loc[p, "accidentes"])
                v["trafico_seguridad"] = int(traf.loc[p, "seguridad_vial"])
                v["trafico_obras"] = int(traf.loc[p, "obras"])
            nv, horas_evento, nombre_ev = eventos.en_hora(evs, p, hora)
            v["evento_nivel"], v["horas_para_evento"] = nv, horas_evento
            v["activas_parque"] = directo.get(p, {}).get("activas", 0) if i == 0 else 0
            v["nuevas_parque_1h"] = directo.get(p, {}).get("nuevas_1h", 0)

            lluvias.append(v["lluvia_1h"])
            sits = situaciones.activas(v)
            ef = efectos_sit.get("activo", {})
            mult, factores = reglas.aplicar(v, sin_meteo={f for f, ok in ef.items() if ok})
            if sits:
                mult, txt_sit = aplicar_situaciones(p, sits, v, mult, efectos_sit)
                factores = txt_sit + factores
            if nombre_ev:
                factores = [f if f not in ("Evento masivo", "Evento") else f"{f}: {nombre_ev}" for f in factores]
            lam_f = {f: normal[f] * mult.get(f, 1.0) for f in FAMILIAS}
            lam_normal = sum(normal.values())
            lam = sum(lam_f.values())
            fuente = "base+reglas"
            if modelo is not None:
                lam_ml = modelo.predecir(p, hora, v, lam_normal, lam)
                if lam_ml is not None:
                    reparto = {f: lam_f[f] / lam for f in FAMILIAS} if lam > 0 else {}
                    lam, fuente = lam_ml, "lightgbm"
                    lam_f = {f: lam * reparto.get(f, 0) for f in FAMILIAS}
            ratio = lam / lam_normal if lam_normal > 0 else 1.0
            top = sorted(((f, x) for f, x in lam_f.items() if x > 0), key=lambda t: -t[1])[:3]
            horas_out.append({
                "hora": hora.isoformat(), "lambda": round(lam, 4), "prob": round(1 - math.exp(-lam), 3),
                "normal": round(lam_normal, 4), "ratio": round(ratio, 2), "nivel": nivel(ratio),
                "familias_top": [{"familia": f, "lambda": round(x, 4), "mult": round(mult.get(f, 1.0), 2)}
                                 for f, x in top],
                "factores": factores,
                "situaciones": sits, "situacion_txt": situaciones.texto(sits, v),
                "meteo": {k: (round(v[k], 1) if isinstance(v.get(k), float) else v.get(k))
                          for k in ("temp", "humedad", "lluvia_1h", "lluvia_12h", "racha_kmh", "viento_sur",
                                    "dias_sin_lluvia", "viento_kmh", "dir_viento", "factor_racha",
                                    "dpresion_12h", "lluvia_72h", "ola_m")},
            })
            filas_hist.append({"generado": ahora.isoformat(timespec="minutes"), "parque": p, "hora": hora,
                               "horizonte": i, "lambda": lam, "normal": lam_normal, "ratio": ratio,
                               "nivel": nivel(ratio), "modelo": fuente})
            if i == 0:
                filas_vars.append({"parque": p, "hora": hora, "lambda_base": lam_normal, "lambda_reglas":
                                   sum(normal[f] * mult.get(f, 1.0) for f in FAMILIAS),
                                   **{k: (int(x) if isinstance(x, bool) else x) for k, x in v.items()}})
        lam6 = sum(h["lambda"] for h in horas_out)
        norm6 = sum(h["normal"] for h in horas_out)
        peor = max(horas_out, key=lambda h: h["ratio"])
        factores6 = list(dict.fromkeys(f for h in horas_out for f in h["factores"]))
        parques_out.append({
            "id": p, "nombre": info["nombre"], "lat": info["lat"], "lon": info["lon"],
            "salidas_esperadas_6h": round(lam6, 2), "normal_6h": round(norm6, 2),
            "prob_6h": round(1 - math.exp(-lam6), 3), "ratio_max": peor["ratio"], "nivel": peor["nivel"],
            "hora_pico": peor["hora"], "factores": factores6,
            "situacion_ahora": horas_out[0]["situacion_txt"],
            "situaciones_6h": list(dict.fromkeys(x for h in horas_out for x in h["situaciones"])), "directo": directo.get(p, {}), "horas": horas_out,
            "carreteras": riesgo_trafico.carreteras(p, franjas, lluvias),
        })

    salida = {
        "generado": ahora.isoformat(timespec="minutes"), "horizonte_h": horas,
        "modelo": "lightgbm" if modelo is not None else "base+reglas", "fuentes_ok": fuentes,
        "bizkaia": {"salidas_esperadas_6h": round(sum(x["salidas_esperadas_6h"] for x in parques_out), 1),
                    "normal_6h": round(sum(x["normal_6h"] for x in parques_out), 1), "contador": contador},
        "parques": sorted(parques_out, key=lambda x: -x["ratio_max"]),
        "activas_ahora": activas,
        "niveles": {n: lim for lim, n in NIVELES},
        "trafico_dgt": riesgo_trafico.resumen(),
    }
    if guardar:
        (config.DIR_PREDICCION / "ultima.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
        hist = config.DIR_PREDICCION / "historial"
        hist.mkdir(exist_ok=True)
        mes = ahora.strftime("%Y-%m")
        for nombre, filas in (("prediccion", filas_hist), ("variables", filas_vars)):
            ruta = hist / f"{nombre}_{mes}.csv"
            nuevo = pd.DataFrame(filas)
            if ruta.exists():
                cab = pd.read_csv(ruta, nrows=0).columns.tolist()
                if cab != nuevo.columns.tolist():      # columnas nuevas: se reescribe con la unión
                    pd.concat([pd.read_csv(ruta), nuevo], ignore_index=True).to_csv(ruta, index=False)
                    continue
            nuevo.to_csv(ruta, mode="a", header=not ruta.exists(), index=False)
    return salida


def cargar_efectos():
    p = config.DIR_MODELO / "situaciones_efectos.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def aplicar_situaciones(parque, sits, v, mult, ef):
    """Multiplica cada tipo de siniestro por el efecto MEDIDO de las situaciones activas en ese parque
    (solo los tipos cuyo efecto mejoró la predicción en la validación). Tope ×6 / ×0,3 por hora."""
    from .patrones import ETIQ
    mult = dict(mult)
    textos = []
    bizkaia = ef.get("efectos", {})

    def claro(fam, s_):     # solo efectos cuyo intervalo del 95 % (toda Bizkaia) no incluye 1
        e = bizkaia.get(fam, {}).get(s_)
        return bool(e) and (e["lo"] > 1 or e["hi"] < 1)

    por_p = {f: {s_: min(max(m, 0.5), 4.0) for s_, m in d.items() if claro(f, s_)}
             for f, d in ef.get("por_parque", {}).get(parque, {}).items()}
    for fam, ok in ef.get("activo", {}).items():
        if not ok:
            continue
        k = 1.0
        for s_ in sits:
            k *= por_p.get(fam, {}).get(s_, 1.0)
        mult[fam] = mult.get(fam, 1.0) * min(max(k, 0.3), 6.0)
    for s_ in sits:
        cands = [(fam, por_p.get(fam, {}).get(s_)) for fam, ok in ef.get("activo", {}).items() if ok]
        cands = [(f, m) for f, m in cands if m and m >= 1.15]
        base = situaciones.texto([s_], v)
        if cands:
            f, m = max(cands, key=lambda t: t[1])
            textos.append(f"{base} → {ETIQ.get(f, f).lower()} ×{m:.1f} (medido {ef.get('anios', ['?'])[0]}-"
                          f"{ef.get('anios', ['?'])[-1]})")
        else:
            textos.append(base)
    return mult, textos


def cargar_modelo():
    try:
        from .horario import ModeloHorario
        return ModeloHorario.cargar()
    except Exception as e:
        print(f"Aviso modelo horario: {e}")
        return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=int, default=6)
    a = ap.parse_args(argv)
    s = predecir(a.horas)
    print(f"{s['generado']} · modelo {s['modelo']} · esperadas 6h Bizkaia: {s['bizkaia']['salidas_esperadas_6h']} "
          f"(normal {s['bizkaia']['normal_6h']})")
    for p in s["parques"]:
        print(f"  {p['nombre']:<20} {p['nivel']:<9} x{p['ratio_max']:<5} esperadas {p['salidas_esperadas_6h']:<5} "
              f"{'; '.join(p['factores'][:3])}")


if __name__ == "__main__":
    main()
