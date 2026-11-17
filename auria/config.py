"""Configuración central de AURIA."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
CRUDO = DATOS / "crudo"            # descargas (no se suben a git)
HISTORICO = DATOS / "historico"    # CSV de Open Data Bizkaia guardados en el repo (GitHub no llega al portal)
PROCESADO = DATOS / "procesado"    # tablas limpias
DIR_ONLINE = DATOS / "online"      # capturas en directo, una subcarpeta por recolector
DIR_MODELO = DATOS / "modelo"      # tasas base y modelo entrenado (se suben a git)
DIR_PREDICCION = RAIZ / "prediccion"
INFORMES = RAIZ / "informes"

for _d in (CRUDO, HISTORICO, PROCESADO, DIR_ONLINE, DIR_MODELO, DIR_PREDICCION, INFORMES):
    _d.mkdir(parents=True, exist_ok=True)

# --- Fuentes ---------------------------------------------------------------
URL_SALIDAS_ONLINE = "https://www.bizkaia.eus/es/bomberas-bomberos-bizkaia"

# Open Data Bizkaia: intervenciones SPEIS (actualización trimestral)
OPENDATA_BASE = "https://www.opendatabizkaia.eus/es/dump"
RECURSOS_HISTORICO = {
    "2023-2026": "1db8ab30-b367-4fb8-bc52-74b79910dc69/intervenciones-speis-2023-2026",
    "2022": "a13509ed-030b-4929-9aea-dc47cdb932b0/intervenciones-speis-2022",
    "2021": "bfd599e0-c380-4d8c-a1a0-8f2c128ae073/intervenciones-speis-2021",
}

# Open-Meteo (gratis, sin API key)
OPENMETEO_ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"
OPENMETEO_PREVISION = "https://api.open-meteo.com/v1/forecast"

# Open Data Euskadi: incidencias de tráfico (sin API key)
TRAFICO_INCIDENCIAS = "https://api.euskadi.eus/traffic/v1.0/incidences/byDate/{y}/{m:02d}/{d:02d}"

USER_AGENT = "AURIA/0.2 (proyecto personal de prediccion de emergencias)"
