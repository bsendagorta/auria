"""Diagnóstico de fuentes externas (no muestra claves)."""
import datetime as dt
import requests
from auria import euskalmet as E

def ver(nombre, url, headers=None, n=1500):
    try:
        r = requests.get(url, headers=headers or {"User-Agent": "AURIA"}, timeout=60, stream=True)
        txt = r.raw.read(n, decode_content=True).decode("utf-8", "replace")
        print(f"== {nombre} -> {r.status_code} {r.headers.get('content-type')} {r.headers.get('content-length')}\n{url}\n{txt}\n")
    except Exception as e:
        print(f"== {nombre} -> ERR {e}\n{url}\n")

hoy = dt.date.today() - dt.timedelta(days=1)
tok = E.token(900)
H = {"Authorization": "Bearer " + tok, "Accept": "application/json"}
for r in ["/euskalmet/stations", "/euskalmet/stations/C040", f"/euskalmet/readings/aggregated/byDay/forStation/C040/at/{hoy:%Y/%m/%d}",
          f"/euskalmet/readings/aggregated/byDay/forStation/C040/at/2021/03/10"]:
    ver("euskalmet " + r, E.BASE + r, H, 2500)
# MITMS movilidad
for u in ["https://movilidad-opendata.mitma.es/RSS.xml",
          "https://movilidad-opendata.mitma.es/estudios_basicos/por-distritos/viajes/ficheros-diarios/2025-05/",
          "https://movilidad-opendata.mitma.es/estudios_basicos/por-distritos/personas/ficheros-diarios/2025-05/",
          "https://movilidad-opendata.mitma.es/zonificacion/zonificacion_distritos/nombres_distritos.csv",
          "https://movilidad-opendata.mitma.es/zonificacion/relacion_ine_zonificacionMitma.csv"]:
    ver("mitms", u, n=1200)
# Kulturklik y calendario laboral
for u in ["https://api.euskadi.eus/culture/events/v1.0/events/upcoming?_elements=3&_page=1",
          "https://api.euskadi.eus/culture/events/v1.0/events/byMonth/2026/11?_elements=3&_page=1&provinceNoraCode=48",
          "https://api.euskadi.eus/culture/events/v1.0/eventType",
          "https://opendata.euskadi.eus/contenidos/ds_eventos/calendario_laboral_2026/opendata/calendario_laboral_2026.json",
          "https://opendata.euskadi.eus/contenidos/ds_eventos/calendario_laboral_2025/opendata/calendario_laboral_2025.json",
          "https://opendata.euskadi.eus/contenidos/ds_eventos/calendario_laboral_2024/opendata/calendario_laboral_2024.json"]:
    ver("eventos", u, n=1500)
