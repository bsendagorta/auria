"""Límites municipales oficiales de Bizkaia y zona de actuación de cada parque.

Fuente: Límites Administrativos del País Vasco, municipios a escala 1:5.000 (Gobierno Vasco, CC BY 4.0,
"Eusko Jaurlaritza / Gobierno Vasco"), ETRS89 UTM 30N:
    https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/MUNICIPIOS_5000_ETRS89.zip
Salida (WGS84, simplificado a ~10 m para que el mapa cargue rápido):
    datos/geo/municipios_bizkaia.geojson   un polígono por municipio, con su parque y salidas al año
    datos/geo/zonas_parques.geojson        unión de los municipios de cada parque
Uso: python -m auria.mapas   (workflow "Mapas", a mano: los límites casi no cambian)
"""
import io
import json
import re
import zipfile

import pandas as pd
import requests

from . import config
from .parques import INE_A_PARQUE, PARQUES


def _nombre_parque(p):
    return PARQUES[p]["nombre"] if p in PARQUES else ("Bilbao (servicio municipal)" if p == "BILBAO" else "Sin parque asignado")

URL = "https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/MUNICIPIOS_5000_ETRS89.zip"
DIR = config.DATOS / "geo"
TOL = 0.0001          # grados (~8-11 m)
FUENTE = "Límites municipales 1:5.000 · Eusko Jaurlaritza / Gobierno Vasco (CC BY 4.0)"


def _leer_shp(zbytes):
    import shapefile                      # pyshp
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    base = next(n[:-4] for n in z.namelist() if n.lower().endswith(".shp"))
    ext = {e: z.read(next(n for n in z.namelist() if n.lower() == (base + e).lower()))
           for e in (".shp", ".shx", ".dbf")}
    r = shapefile.Reader(shp=io.BytesIO(ext[".shp"]), shx=io.BytesIO(ext[".shx"]), dbf=io.BytesIO(ext[".dbf"]),
                         encoding="utf-8", encodingErrors="replace")
    campos = [f[0] for f in r.fields[1:]]
    return r, campos


def _codigo_ine(reg, campos):
    """Código INE de 5 cifras (48xxx) a partir de los atributos, sea cual sea el nombre del campo."""
    if "MUN_PROV" in campos and "MUN_MUNI" in campos:       # esquema del Gobierno Vasco
        prov, muni = str(reg["MUN_PROV"]).strip().zfill(2), str(reg["MUN_MUNI"]).strip().zfill(3)
        return f"{prov}{muni}" if prov == "48" and muni.isdigit() else None
    for c in campos:
        v = str(reg[c]).strip()
        if re.fullmatch(r"48\d{3}", v):
            return v
    prov = next((str(reg[c]).zfill(2) for c in campos if re.search(r"prov|lurral|ter", c, re.I)), None)
    mun = next((str(reg[c]).zfill(3) for c in campos if re.search(r"cod.*mun|mun.*cod|udal.*kod|ine", c, re.I)), None)
    if prov == "48" and mun and mun.isdigit():
        return "48" + mun[-3:]
    return None


def construir(zbytes=None):
    from pyproj import Transformer
    from shapely.geometry import mapping, shape
    from shapely.ops import transform, unary_union
    zbytes = zbytes or requests.get(URL, timeout=120, headers={"User-Agent": config.USER_AGENT}).content
    r, campos = _leer_shp(zbytes)
    print("Campos:", campos)
    a_wgs = Transformer.from_crs(25830, 4326, always_xy=True).transform
    try:
        d = pd.read_csv(config.PROCESADO / "intervenciones.csv", dtype={"cod_ine": str}, low_memory=False)
        d = d[(d["operativa"].astype(str) == "True") & d["anio"].between(2023, 2025)]
        sal = (d.groupby("cod_ine").size() / 3).round(1).to_dict()
    except FileNotFoundError:
        sal = {}
    nombre_campo = "NOMBRE_TOP" if "NOMBRE_TOP" in campos else next(
        (c for c in campos if re.search(r"nombre|izena", c, re.I)), campos[0])
    mun, por = [], {}
    for sr in r.iterShapeRecords():
        ine = _codigo_ine(sr.record, campos)
        if not ine:
            continue
        g = transform(a_wgs, shape(sr.shape.__geo_interface__)).buffer(0)
        p = INE_A_PARQUE.get(ine, "BILBAO" if ine == "48020" else "SIN_PARQUE")
        nom = str(sr.record[nombre_campo]).strip()
        mun.append({"type": "Feature", "geometry": mapping(g.simplify(TOL, preserve_topology=True)),
                    "properties": {"ine": ine, "nombre": nom, "parque": p, "salidas_anio": sal.get(ine, 0.0),
                                   "parque_nombre": _nombre_parque(p)}})
        por.setdefault(p, []).append(g)
    if len(mun) < 100:
        raise RuntimeError(f"Solo {len(mun)} municipios de Bizkaia: revisar los campos {campos}")
    zon = []
    for p, gs in por.items():
        u = unary_union(gs).simplify(TOL, preserve_topology=True)
        ms = sorted(f["properties"]["nombre"] for f in mun if f["properties"]["parque"] == p)
        zon.append({"type": "Feature", "geometry": mapping(u), "properties": {
            "parque": p, "nombre": _nombre_parque(p), "n_municipios": len(ms),
            "municipios": ", ".join(ms),
            "salidas_anio": round(sum(f["properties"]["salidas_anio"] for f in mun if f["properties"]["parque"] == p), 1)}})
    DIR.mkdir(parents=True, exist_ok=True)

    def guardar(nombre, feats):
        txt = json.dumps({"type": "FeatureCollection", "fuente": FUENTE, "features": feats},
                         ensure_ascii=False, separators=(",", ":"))
        txt = re.sub(r"(\d+\.\d{5})\d+", r"\1", txt)          # 5 decimales ≈ 1 m
        (DIR / nombre).write_text(txt, encoding="utf-8")
        print(f"{nombre}: {len(feats)} polígonos, {len(txt) / 1e6:.2f} MB")

    guardar("municipios_bizkaia.geojson", mun)
    guardar("zonas_parques.geojson", zon)
    return mun, zon


if __name__ == "__main__":
    construir()
