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
    assert d["desde_8"] == 34 and d["anio"] == 5732 and len(d["activas"]) == 2
    assert d["activas"][1]["zona"] == "AV Algorta"
    with tempfile.TemporaryDirectory() as tmp:
        t0 = datetime(2026, 11, 15, 23, 50, tzinfo=R.TZ)
        for i, suma in enumerate([0, 3, 5, 9]):
            dd = {**d, "anio": d["anio"] + suma}
            R.guardar(dd, t0 + timedelta(minutes=10 * i), R.carpeta_origen(tmp))
        _, horario, acts = S.resumir(tmp, guardar=False)
        assert len(acts) == 2, "la misma actuación a caballo de medianoche no se duplica"
        assert set(acts["parque"]) == {"URIOSTE", "ARTAZA"}
        assert horario["salidas"].sum() == 9


def test_directo():
    assert directo.vehiculo("Bomba urbana pesada (Vehículo volviendo de un sin.)")["estado"] == "REGRESANDO"
    assert directo.vehiculo("Autoescala (Vehículo va a un siniestro)")["estado"] == "EN_RUTA"
    assert directo.vehiculo("Furgón utiles varios (Vehículo parado en siniestro)")["estado"] == "EN_SINIESTRO"
    d = directo.leer((FIX / "pagina_salidas.html").read_text(encoding="utf-8"))
    assert [a["parque"] for a in d["actuaciones"]] == ["URIOSTE", "ARTAZA"]
    assert d["por_parque"]["URIOSTE"]["en_siniestro"] == 1


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


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("OK", nombre)
