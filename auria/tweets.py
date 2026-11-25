"""Lectura de actuaciones desde la cuenta pública @BomberosBizkaia (X/Twitter), capturadas por el usuario.

Mientras la web de Bomberos bloquea la lectura automática, esta cuenta publica cada actuación "en camino"
con tipo, ubicación y municipio. La hora exacta va codificada en el identificador del tuit (Snowflake),
así que cada tuit es una actuación con su hora: justo lo que se perdía del directo.

IMPORTANTE — cómo se obtiene: X no permite la lectura automática fuera de su API (de pago para leer) y
bloquea a los lectores automáticos. Por eso AURIA NO rastrea X desde la nube. Las capturas las hace el
propio usuario desde su sesión, con el botón `scripts/marcador_tweets.js` (un marcador de navegador):
al pulsarlo en la página de la cuenta, copia al portapapeles las actuaciones que se ven. El usuario las
pega y este módulo las integra.

Formato de entrada (una actuación por línea):  <id>\\t<iso_ts>\\t<texto del tuit>
(el id o el ts bastan para la hora; si falta el ts se calcula del id).

Salida: datos/online/tweets/tweets_AAAA-MM.csv  (ts, id, tipo, familia, ubicacion, municipio, parque, operativa)
  y se usa igual que las capturas por minuto para aprender el perfil por hora y día.
Uso:  python -m auria.tweets < lote.txt     (o  auria.tweets.ingerir(texto))
"""
import re
import sys
from datetime import datetime, timezone

import pandas as pd

from . import config
from .familias import familia
from .parques import PARQUES, parque_de_nombre

DIR = config.DATOS / "online" / "tweets"
EPOCA_TW = 1288834974657          # época Snowflake de Twitter (ms)
CAMPOS = ["ts", "id", "tipo", "ubicacion", "municipio", "familia", "parque", "operativa"]
# estados de un tuit que NO son una salida nueva (actualizaciones, agradecimientos…)
NO_SALIDA = re.compile(r"\b(resuelto|finalizado|controlado|extinguido|sofocado|gracias|eskerrik|"
                       r"amaitu|kontrolatu|itzali)\b", re.I)
HASHTAG_NO_MUNI = {"bomberos", "suhiltzaileak", "bizkaia", "112", "sosdeiak", "emergencias", "larrialdiak"}


def _ts_de_id(id_):
    try:
        return datetime.fromtimestamp(((int(id_) >> 22) + EPOCA_TW) / 1000, timezone.utc)
    except (ValueError, TypeError):
        return None


def parsear_tuit(texto: str) -> dict | None:
    """Del texto de un tuit saca tipo, ubicación y municipio. None si no es una actuación."""
    t = texto.replace("¶", "\n")
    # línea de contenido en castellano: la que lleva #Bomberos / 'en camino'
    linea = None
    for ln in t.split("\n"):
        if "#Bomberos" in ln or re.search(r"en camino$", ln.strip(), re.I):
            linea = ln.strip()
            break
    if not linea:
        # a veces solo está la euskera (#Suhiltzaileak); se intenta igual con la primera línea con hashtag
        for ln in t.split("\n"):
            if "#" in ln and "@" not in ln and len(ln) > 15:
                linea = ln.strip()
                break
    if not linea or NO_SALIDA.search(linea):
        return None
    hashtags = re.findall(r"#(\w+)", linea)
    municipio = next((h for h in hashtags if h.lower() not in HASHTAG_NO_MUNI), "")
    sin_tags = re.sub(r"#\w+", "", linea)
    sin_tags = re.sub(r"\b(en camino|bidean)\b.*$", "", sin_tags, flags=re.I).strip(" ,;·-")
    tipo, ubic = (sin_tags.split(",", 1) + [""])[:2] if "," in sin_tags else (sin_tags, "")
    tipo = tipo.strip()
    if not tipo:
        return None
    return {"tipo": tipo, "ubicacion": ubic.strip(), "municipio": municipio}


def parsear_lote(texto: str) -> pd.DataFrame:
    filas = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        partes = linea.split("\t")
        id_ = ts = None
        cuerpo = linea
        if len(partes) >= 3:                      # id \t ts \t texto
            id_, ts, cuerpo = partes[0], partes[1], "\t".join(partes[2:])
        elif len(partes) == 2:
            id_, cuerpo = partes
        m = re.match(r"\s*(\d{15,21})\b", id_ or "")
        id_ = m.group(1) if m else None
        t = None
        if ts:
            try:
                t = pd.to_datetime(ts, utc=True).to_pydatetime()
            except (ValueError, TypeError):
                t = None
        t = t or _ts_de_id(id_)
        info = parsear_tuit(cuerpo)
        if not info or t is None:
            continue
        p = parque_de_nombre(info["municipio"]) if info["municipio"] else None
        filas.append({"ts": t.astimezone().isoformat(timespec="seconds"), "id": id_ or "",
                      "tipo": info["tipo"], "ubicacion": info["ubicacion"], "municipio": info["municipio"],
                      "familia": familia(info["tipo"]), "parque": p if p in PARQUES else "", "operativa": True})
    return pd.DataFrame(filas, columns=CAMPOS)


def ingerir(texto: str) -> pd.DataFrame:
    """Integra un lote pegado por el usuario. Devuelve las actuaciones nuevas añadidas."""
    nuevas = parsear_lote(texto)
    if nuevas.empty:
        return nuevas
    DIR.mkdir(parents=True, exist_ok=True)
    nuevas["_mes"] = pd.to_datetime(nuevas["ts"]).dt.strftime("%Y-%m")
    total = 0
    añadidas = []
    for mes, g in nuevas.groupby("_mes"):
        ruta = DIR / f"tweets_{mes}.csv"
        previo = pd.read_csv(ruta, dtype=str) if ruta.exists() else pd.DataFrame(columns=CAMPOS)
        ids = set(previo["id"]) if len(previo) else set()
        g2 = g[~g["id"].isin(ids) | (g["id"] == "")].drop(columns="_mes")
        if len(g2):
            pd.concat([previo, g2], ignore_index=True).drop_duplicates("id", keep="first").to_csv(ruta, index=False)
            total += len(g2)
            añadidas.append(g2)
    print(f"Tweets integrados: {total} actuaciones nuevas", flush=True)
    return pd.concat(añadidas, ignore_index=True) if añadidas else nuevas.iloc[0:0]


def cargar() -> pd.DataFrame:
    import glob
    rutas = glob.glob(str(DIR / "tweets_*.csv"))
    if not rutas:
        return pd.DataFrame(columns=CAMPOS)
    d = pd.concat([pd.read_csv(r, dtype=str) for r in rutas], ignore_index=True).drop_duplicates("id")
    d["ts"] = pd.to_datetime(d["ts"])
    return d


if __name__ == "__main__":
    texto = sys.stdin.read()
    out = ingerir(texto)
    if len(out):
        print(out[["ts", "tipo", "familia", "municipio", "parque"]].to_string(index=False))
