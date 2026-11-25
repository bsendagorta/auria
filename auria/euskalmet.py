"""Cliente de la API de Euskalmet (Agencia Vasca de Meteorología).

Autenticación (https://opendata.euskadi.eus/api-euskalmet/-/how-to-use-meteo-rest-services/):
  JWT RS256 firmado con la clave privada del usuario; aud "met01.apikey", version "1.0.0", iss libre y
  loginId = huella (fingerprint) de la clave pública. Cabecera  Authorization: Bearer <JWT>.
La clave NUNCA va al repositorio (es público). Se lee, por este orden, de:
  1. variables de entorno EUSKALMET_PRIVATE_KEY (texto PEM) y EUSKALMET_FINGERPRINT (secretos de GitHub)
  2. ficheros secretos/euskalmet/privateKey.pem y secretos/euskalmet/fingerPrint.txt (solo en el Mac;
     la carpeta secretos/ está en .gitignore)
"""
import os
import time
import requests

from . import config

BASE = "https://api.euskadi.eus"
DIR_SECRETOS = config.RAIZ / "secretos" / "euskalmet"


def credenciales():
    clave = os.environ.get("EUSKALMET_PRIVATE_KEY")
    huella = os.environ.get("EUSKALMET_FINGERPRINT")
    if not clave and (DIR_SECRETOS / "privateKey.pem").exists():
        clave = (DIR_SECRETOS / "privateKey.pem").read_text()
    if not huella and (DIR_SECRETOS / "fingerPrint.txt").exists():
        huella = (DIR_SECRETOS / "fingerPrint.txt").read_text()
    return (_pem(clave), huella.strip()) if clave and huella else (None, None)


def _pem(txt):
    """Rehace el PEM si al pegarlo como secreto se perdieron los saltos de línea o llegó con \\n literales."""
    import re
    t = txt.replace("\\n", "\n").replace("\r", "").strip().strip('"').strip("'")
    m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", t, re.S)
    if not m:                       # solo el cuerpo en base64
        tipo, cuerpo = "PRIVATE KEY", t
    else:
        tipo, cuerpo = m.group(1), m.group(2)
    cuerpo = re.sub(r"[^A-Za-z0-9+/=]", "", cuerpo)
    lineas = "\n".join(cuerpo[i:i + 64] for i in range(0, len(cuerpo), 64))
    return f"-----BEGIN {tipo}-----\n{lineas}\n-----END {tipo}-----\n"


def disponible():
    return credenciales()[0] is not None


def token(validez_s=3600):
    import jwt
    clave, huella = credenciales()
    if not clave:
        raise RuntimeError("Sin clave de Euskalmet (EUSKALMET_PRIVATE_KEY / secretos/euskalmet)")
    ahora = int(time.time())
    return jwt.encode({"aud": "met01.apikey", "iss": "AURIA Bizkaia", "version": "1.0.0", "iat": ahora,
                       "exp": ahora + validez_s, "loginId": huella}, clave, algorithm="RS256")


_TOKEN = {"v": None, "t": 0}


def get(ruta, **params):
    if not _TOKEN["v"] or time.time() - _TOKEN["t"] > 3000:
        _TOKEN.update(v=token(), t=time.time())
    r = requests.get(BASE + ruta, params=params or None, timeout=30,
                     headers={"Authorization": f"Bearer {_TOKEN['v']}", "User-Agent": config.USER_AGENT,
                              "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ avisos (alertas) de Euskalmet
# zonas de Euskalmet que tocan Bizkaia y parques que cubren (comprobado con /euskalmet/geo/... en nov. 2026)
ZONAS_BIZKAIA = {
    "coast_zone": ["ARTAZA", "URIOSTE", "ARRATZU", "MARKINA"],
    "great_bilbao": ["BASAURI", "DERIO", "ARTAZA", "URIOSTE"],
    "cantabrian_valleys": ["IURRETA", "ZALLA", "ARRATZU", "MARKINA", "BASAURI", "DERIO"],
    "cantabrian_mountains": ["ZALLA", "IURRETA", "BASAURI"],
}


def zonas():
    """Zonas de aviso de Euskalmet que afectan a Bizkaia (las demás —Álava, Gipuzkoa— se ignoran)."""
    return list(ZONAS_BIZKAIA)


def _zonas_api():
    """Todas las zonas según la API Geo (por si Euskalmet cambia la lista)."""
    for ruta in ("/euskalmet/geo/regions/basque_country/zones", "/euskalmet/geo/regions/basque_country"):
        try:
            j = get(ruta)
        except Exception:
            continue
        items = j if isinstance(j, list) else (j.get("zones") or j.get("regionZones") or [])
        ids = [z.get("regionZoneId") or z.get("zoneId") or z.get("id") for z in items if isinstance(z, dict)]
        ids = [i for i in ids if i]
        if ids:
            return ids
    return []


def avisos(fecha=None):
    """Avisos previstos hoy por zona. Devuelve {zona: respuesta JSON} (vacío si no hay clave o falla)."""
    import datetime as _dt
    if not disponible():
        return {}
    f = fecha or _dt.date.today()
    out = {}
    for z in zonas():
        try:
            out[z] = get(f"/euskalmet/alerts/zones/{z}/forecast/at/{f:%Y/%m/%d}")
        except Exception as e:
            out[z] = {"error": str(e)[:200]}
    return out


def capturar(carpeta=None):
    """Guarda los avisos del día (JSON por línea) para aprender después su efecto sobre las salidas."""
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    a = avisos()
    if not a:
        return {}
    from .recolector_online import carpeta_origen
    d = carpeta or carpeta_origen()
    d.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    with open(d / f"euskalmet_{ahora:%Y-%m}.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"leido": ahora.isoformat(timespec="seconds"), "avisos": a}, ensure_ascii=False) + "\n")
    return a
