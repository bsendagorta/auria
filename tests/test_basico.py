"""Pruebas rápidas sin red:  .venv/bin/python -m tests.test_basico"""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from auria import calendario, directo, historico, recolector_online as R, reglas, resumen_online as S, trafico
from auria.familias import familia
from auria.parques import PARQUES, parque_de_nombre

FIX = Path(__file__).parent / "fixtures"


def test_familias():
    casos = {
        "NIVEL 3.ACCESO A VIVIENDAS CERRADAS CON RIESGO DE INCENDIO": "RESCATE_SALVAMENTO",
        "INCENDIO FORESTAL NIVEL 2": "INCENDIO_FORESTAL_EXTERIOR",
        "INCENDIO URBANO DE VIVIENDA": "INCENDIO_URBANO",
        "Incendio industrial ": "INCENDIO_INDUSTRIAL",
        "ACCIDENTE DE TRÁFICO CON ATRAPADOS (I)": "TRAFICO",
        "FUGA GAS INFLAMADA": "GAS_MMPP",
        "SANEADO DE CONSTRUCCIONES": "METEO_ASISTENCIA",
        "SIMULACIÓN INFORMÁTICA": "NO_OPERATIVO",
        "RETÉN DE PREVENCIÓN (SPEIS)": "NO_OPERATIVO",
        "NEUTRALIZACIÓN DE ABEJAS Y AVISPAS": "ABEJAS_AVISPAS",
    }
    for tipo, esperado in casos.items():
        assert familia(tipo) == esperado, (tipo, familia(tipo))


def test_parques():
    assert sum(len(p["ine"]) for p in PARQUES.values()) == 112
    assert parque_de_nombre("BARAKALDO") == "URIOSTE"
    assert parque_de_nombre("Valle de Trápaga-Trapagaran") == "URIOSTE"
    assert parque_de_nombre("GÜEÑES") == "ZALLA"
    assert parque_de_nombre("BILBAO") == "SIN_PARQUE"


def test_historico():
    df = historico.procesar(sorted(FIX.glob("intervenciones_*.csv")))
    assert set(df["anio"]) == {2021, 2022, 2023, 2024, 2025}
    assert (df["anio"] == 2022).sum() == 6, "2022: solo la última extracción"
    bk = df[(df["cod_ine"] == "48013") & df["lat"].notna()].iloc[0]
    assert 43.25 < bk["lat"] < 43.33 and -3.05 < bk["lon"] < -2.95
    assert bk["parque"] == "URIOSTE"
    assert df.loc[(df["anio"] == 2022) & (df["origen"].str.contains("VESPA")), "familia"].iat[0] == "ABEJAS_AVISPAS"


def test_recolector_y_resumen():
    html = (FIX / "pagina_salidas.html").read_text(encoding="utf-8")
    d = R.parsear(html)
    assert d["desde_8"] == 34 and d["anio"] == 5732 and len(d["activas"]) == 3
    assert d["activas"][1]["zona"] == "AV Algorta"
    assert d["activas"][2]["vehiculos"] == ["Transporte Material y Personal (Vehículo propuesto)",
                                            "Auto escala articulada (Vehículo propuesto)"], d["activas"][2]
    assert d["activas"][2]["zona"] == "CL El Carmen"
    with tempfile.TemporaryDirectory() as tmp:
        t0 = datetime(2026, 11, 15, 23, 50, tzinfo=R.TZ)
        for i, suma in enumerate([0, 3, 5, 9]):       # el contador "desde las 08:00" es el que avanza
            dd = {**d, "desde_8": d["desde_8"] + suma}
            R.guardar(dd, t0 + timedelta(minutes=10 * i), R.carpeta_origen(tmp))
        _, horario, acts = S.resumir(tmp, guardar=False)
        assert len(acts) == 3, "la misma actuación a caballo de medianoche no se duplica"
        assert set(acts["parque"]) == {"URIOSTE", "ARTAZA"}
        assert horario["vehiculos"].sum() == 9


def test_directo():
    assert directo.vehiculo("Bomba urbana pesada (Vehículo volviendo de un sin.)")["estado"] == "REGRESANDO"
    assert directo.vehiculo("Autoescala (Vehículo va a un siniestro)")["estado"] == "EN_RUTA"
    assert directo.vehiculo("Furgón utiles varios (Vehículo parado en siniestro)")["estado"] == "EN_SINIESTRO"
    d = directo.leer((FIX / "pagina_salidas.html").read_text(encoding="utf-8"))
    assert [a["parque"] for a in d["actuaciones"]] == ["URIOSTE", "ARTAZA", "ARTAZA"]
    assert d["por_parque"]["URIOSTE"]["en_siniestro"] == 1
    assert d["por_parque"]["ARTAZA"]["propuesto"] == 2
    assert directo.vehiculo("Auto escala articulada (Vehículo propuesto)")["estado"] == "PROPUESTO"


def test_accidentes():
    import numpy as np
    from auria import accidentes as A
    filas = []
    for i in range(400):   # Barakaldo (municipio) y un tramo de la N-634 sin municipio junto a Durango
        m, car, km = ("48013", "A-8", 125.0) if i % 2 else ("48027", "N-634", 30.0)
        filas.append({"ANYO": 2025, "MES": 1 + i % 12, "DIA_SEMANA": 1 + i % 7, "HORA": (7 + i) % 24,
                      "COD_PROVINCIA": 48, "COD_MUNICIPIO": m, "ZONA_AGRUPADA": 1, "CARRETERA": car,
                      "KM": km + (i % 3), "CONDICION_METEO": 3 if i % 4 == 0 else 1, "TOTAL_MU30DF": 0,
                      "TOTAL_HG30DF": i % 10 == 0, "TOTAL_VICTIMAS_30DF": 1})
    filas.append({**filas[0], "COD_MUNICIPIO": "00000", "CARRETERA": "N-634", "KM": 31.0})
    filas.append({**filas[0], "COD_MUNICIPIO": "48020", "CARRETERA": "", "KM": None})
    d = A.preparar(pd.DataFrame(filas))
    assert d.iloc[-2]["parque"] == "IURRETA" and d.iloc[-2]["parque_por"] == "carretera_km"
    assert d.iloc[-1]["parque"] == "BILBAO"
    p = A.perfil_horario(d)
    w = p["tipo_dia"].map(A.DIAS_TIPO)
    for (_, _), g in p.groupby(["parque", "franja"]):
        assert abs(np.average(g["factor"], weights=w[g.index]) - 1) < 1e-3, "el perfil no debe cambiar el nivel"
    t = A.tramos(d[d["parque"] != "BILBAO"])
    assert set(t["CARRETERA"]) == {"A-8", "N-634"}
    ll = A.riesgo_lluvia(d, pd.Series([1.0] * 10 + [0.0] * 30, index=pd.date_range("2025-01-01", periods=40, freq="h")))
    assert ll["rr_lluvia"] > 0


def test_reglas_y_calendario():
    v = {"racha_kmh": 85, "lluvia_1h": 0, "lluvia_12h": 0, "dias_sin_lluvia": 0, "viento_sur": False,
         "humedad": 80, "temp": 12, "nieve": 0, "noche_finde": False, "operacion_trafico": False, "festivo": False}
    mult, textos = reglas.aplicar(v)
    assert mult["METEO_ASISTENCIA"] == 5.0 and textos
    assert calendario.variables_hora(pd.Timestamp("2026-11-20 23:00"))["noche_finde"]


def test_trafico():
    df = pd.DataFrame([
        {"province": "Bizkaia", "incidenceType": "Accidente", "cause": "Alcance", "latitude": "43.30",
         "longitude": "-3.04", "incidenceLevel": ""},
        {"province": "Gipuzkoa", "incidenceType": "Accidente", "cause": "Alcance", "latitude": "43.30",
         "longitude": "-2.00", "incidenceLevel": ""},
        {"province": "BIZKAIA", "incidenceType": "Obra", "cause": "Obra", "latitude": "0.0", "longitude": "0.0"},
        {"province": "Bizkaia", "incidenceType": "Obra", "cause": "Obra", "latitude": "43.258",
         "longitude": "-2.941"},  # Bilbao: excluido
    ])
    t = trafico.por_parque(df)
    assert t.loc["URIOSTE", "accidentes"] == 1 and t["accidentes"].sum() == 1
    assert t["obras"].sum() == 0


def test_situaciones_y_prevision():
    import json
    import numpy as np
    import pandas as pd
    from auria import config, prevision, situaciones
    from auria.parques import PARQUES
    horas = pd.date_range(pd.Timestamp.now().floor("h") - pd.Timedelta(days=3), periods=24 * 5, freq="h")
    partes = []
    for p in PARQUES:
        n = len(horas)
        d = pd.DataFrame({"time": horas.strftime("%Y-%m-%dT%H:%M"), "parque": p, "temperature_2m": 22.0,
                          "relative_humidity_2m": 35.0, "precipitation": 0.0, "snowfall": 0.0,
                          "wind_speed_10m": 20.0, "wind_gusts_10m": 75.0, "wind_direction_10m": 180.0,
                          "pressure_msl": np.linspace(1015, 1000, n), "soil_moisture_0_to_1cm": 0.2, "cape": 0.0})
        partes.append(d)
    m = prevision.meteo_desde_crudo(pd.concat(partes))
    assert m["SUR_RACHEADO"].all() and m["VIENTO_FUERTE"].all() and not m["NORTE_PERSISTENTE"].any()
    ef = {"anios": [2021, 2025], "activo": {"INCENDIO_FORESTAL_EXTERIOR": True, "METEO_ASISTENCIA": False},
          "efectos": {"INCENDIO_FORESTAL_EXTERIOR": {"SUR_RACHEADO": {"m": 2.0, "lo": 1.4, "hi": 2.6},
                                                     "VIENTO_FUERTE": {"m": 1.2, "lo": 0.9, "hi": 1.5}}},
          "por_parque": {p: {"INCENDIO_FORESTAL_EXTERIOR": {"SUR_RACHEADO": 2.0, "VIENTO_FUERTE": 1.2}}
                         for p in PARQUES}}
    ruta = config.DIR_MODELO / "situaciones_efectos.json"
    previo = ruta.read_text() if ruta.exists() else None
    ruta.write_text(json.dumps(ef))
    try:
        traf = pd.DataFrame(0, index=list(PARQUES), columns=["accidentes", "seguridad_vial", "obras"])
        out = prevision.predecir(3, meteo=m, traf=traf, guardar=False)
        h = out["parques"][0]["horas"][0]
        assert "SUR_RACHEADO" in h["situaciones"] and "Sur racheado" in out["parques"][0]["situacion_ahora"]
        assert any("×2.0" in f for f in h["factores"]), h["factores"]
    finally:
        if previo is None:
            ruta.unlink()
        else:
            ruta.write_text(previo)


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("OK", nombre)
