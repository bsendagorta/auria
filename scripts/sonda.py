"""Diagnóstico de fuentes externas (no muestra claves)."""
import datetime as dt, json, collections
import requests
from auria import euskalmet as E
tok = E.token(900)
H = {"Authorization": "Bearer " + tok, "Accept": "application/json"}
g = lambda r: requests.get(E.BASE + r, headers=H, timeout=60)
st = g("/euskalmet/stations").json()
ult = {}
for s in st:
    ult[s["stationId"]] = s["key"]
print("estaciones:", len(ult))
print("== detalle C040:", g("/" + ult["C040"]).text[:3000])
# medidas disponibles en un día
d = g("/euskalmet/readings/aggregated/byDay/forStation/C040/at/2026/11/16").json()
print("== medidas C040:", sorted({(i["measureType"], i["measureId"], i["sensorId"]) for i in d["items"]}))
it = d["items"][0]["readings"][0]
print("== ejemplo lectura:", json.dumps({k: it[k] for k in it if k != "slots"})[:600])
