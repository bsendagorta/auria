"""Recolector de las salidas en directo de bizkaia.eus.

La web solo muestra las actuaciones ACTIVAS en ese momento (sin hora) y dos contadores:
  - "Salidas desde 08:00h"  (se reinicia cada día a las 08:00)
  - "Salidas este año"      (acumulado anual)
Capturando cada 5-10 minutos se obtiene:
  - la hora aproximada de aparición de cada actuación
  - el nº exacto de salidas por día y por hora (diferencias del contador anual)

Almacenamiento: CSV mensuales, solo se añaden filas (varios recolectores pueden escribir en
carpetas distintas y se combinan después sin conflictos):
  datos/online/<origen>/capturas_AAAA-MM.csv  ts, salidas_desde_8, salidas_anio, n_activas, ok, error
  datos/online/<origen>/activas_AAAA-MM.csv   ts, tipo, ubicacion, zona, vehiculos, n_vehiculos
<origen> = variable de entorno AURIA_ORIGEN (p.ej. 'github' o 'mac'); por defecto 'local'.

Uso:  python -m auria.recolector_online
      python -m auria.recolector_online --html pagina.html   (pruebas)
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo("Europe/Madrid")
CAMPOS_CAPTURA = ["ts", "salidas_desde_8", "salidas_anio", "n_activas", "ok", "error"]
CAMPOS_ACTIVA = ["ts", "tipo", "ubicacion", "zona", "vehiculos", "n_vehiculos"]


class _Parser(HTMLParser):
    """Extrae contadores y tarjetas de la lista #..._salidas sin dependencias externas."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.textos = []
        self.en_lista = 0
        self.tarjetas = []
        self._tarjeta = None
        self._etiqueta = None
        self._panel = 0
        self._li_panel = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "ul" and (a.get("id") or "").endswith("_salidas"):
            self.en_lista = 1
            return
        if self.en_lista:
            if tag == "ul":
                self.en_lista += 1
            if tag == "div" and "card-body" in (a.get("class") or ""):
                self._tarjeta = {"tipo": "", "ubicacion": "", "zona": "", "vehiculos": [], "panel": []}
                self.tarjetas.append(self._tarjeta)
                self._etiqueta = None
            if tag == "div":
                if self._panel:
                    self._panel += 1
                elif (a.get("id") or "").startswith("panel_vehiculos"):
                    self._panel = 1
            if self._panel and tag == "li":
                self._li_panel = True
                if self._tarjeta is not None:
                    self._tarjeta["panel"].append("")

    def handle_endtag(self, tag):
        if self.en_lista and tag == "ul":
            self.en_lista -= 1
        if self._panel and tag == "div":
            self._panel -= 1
        if tag == "li":
            self._li_panel = False

    def handle_data(self, data):
        t = " ".join(data.split())
        if not t:
            return
        self.textos.append(t)
        if not (self.en_lista and self._tarjeta is not None):
            return
        if self._panel:
            if self._li_panel and self._tarjeta["panel"]:
                self._tarjeta["panel"][-1] = (self._tarjeta["panel"][-1] + " " + t).strip()
            return
        low = t.lower()
        if low.startswith("conocer todos"):
            return
        if low.startswith("tipo de siniestro"):
            self._etiqueta = "tipo"
        elif low.startswith("ubicaci"):
            self._etiqueta = "ubicacion"
        elif low.startswith("tipo de veh"):
            self._etiqueta = "vehiculos"
        elif low.startswith("zona"):
            self._etiqueta = "zona"
        elif self._etiqueta == "vehiculos":
            self._tarjeta["vehiculos"].append(t)
        elif self._etiqueta and not self._tarjeta[self._etiqueta]:
            self._tarjeta[self._etiqueta] = t


def parsear(html: str) -> dict:
    p = _Parser()
    p.feed(html)
    texto = " ".join(p.textos)
    m8 = re.search(r"(\d+)\s+Salidas\s+desde\s+08:00", texto, re.I)
    ma = re.search(r"(\d+)\s+Salidas\s+este\s+a", texto, re.I)
    if not (m8 and ma):
        raise ValueError("No se encontraron los contadores: la web puede haber cambiado")
    tarjetas = [t for t in p.tarjetas if t["tipo"]]
    for t in tarjetas:
        panel = [v for v in t.pop("panel") if v]
        if panel:
            t["vehiculos"] = panel
        else:
            t["vehiculos"] = [v for v in t["vehiculos"] if not v.lower().startswith("varios veh")]
    return {"desde_8": int(m8.group(1)), "anio": int(ma.group(1)), "activas": tarjetas}


def carpeta_origen(raiz=None) -> Path:
    d = Path(raiz or config.DIR_ONLINE) / os.environ.get("AURIA_ORIGEN", "local")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append(ruta: Path, campos, filas):
    nuevo = not ruta.exists()
    with ruta.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        if nuevo:
            w.writeheader()
        w.writerows(filas)


def guardar(datos, ahora: datetime, carpeta: Path, error=None):
    ts = ahora.isoformat(timespec="seconds")
    mes = ahora.strftime("%Y-%m")
    if datos is None:
        fila = {"ts": ts, "salidas_desde_8": "", "salidas_anio": "", "n_activas": "", "ok": 0,
                "error": str(error)[:300]}
        _append(carpeta / f"capturas_{mes}.csv", CAMPOS_CAPTURA, [fila])
        return
    _append(carpeta / f"capturas_{mes}.csv", CAMPOS_CAPTURA, [{
        "ts": ts, "salidas_desde_8": datos["desde_8"], "salidas_anio": datos["anio"],
        "n_activas": len(datos["activas"]), "ok": 1, "error": ""}])
    _append(carpeta / f"activas_{mes}.csv", CAMPOS_ACTIVA, [{
        "ts": ts, "tipo": t["tipo"], "ubicacion": t["ubicacion"], "zona": t["zona"],
        "vehiculos": " | ".join(t["vehiculos"]), "n_vehiculos": len(t["vehiculos"])}
        for t in datos["activas"]])


class Bloqueado(Exception):
    """La web devuelve la página de verificación antibots (F5/TSPD) en vez del contenido."""


PAUSA_BLOQUEO = 1800


def publicar_directo(datos):
    """Deja la situación en directo en prediccion/directo.json (lo lee el panel)."""
    from .directo import enriquecer

    d = enriquecer(datos)
    d.pop("bloqueado", None)
    (config.DIR_PREDICCION / "directo.json").write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")


def publicar_estado_bloqueo(ahora):
    """Marca en directo.json que la lectura está bloqueada por la web (el panel lo explica)."""
    ruta = config.DIR_PREDICCION / "directo.json"
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {"actuaciones": [], "por_parque": {}}
    previo = (d.get("bloqueado") or {}).get("desde")
    d["bloqueado"] = {"desde": previo or ahora.isoformat(timespec="minutes"),
                      "motivo": "bizkaia.eus responde con una verificación antibots a las lecturas automáticas",
                      "comprobado": ahora.isoformat(timespec="seconds")}
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def bloqueo_pendiente(ahora):
    ruta = config.DIR_PREDICCION / "directo.json"
    try:
        estado = json.loads(ruta.read_text(encoding="utf-8")).get("bloqueado")
        if estado:
            comprobado = datetime.fromisoformat(estado["comprobado"])
            return max(0, PAUSA_BLOQUEO - (ahora - comprobado).total_seconds())
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return 0


def descargar_html() -> str:
    from playwright.sync_api import sync_playwright
    from playwright_stealth import stealth_sync
    
    with sync_playwright() as p:
        # Lanzar con argumentos que ocultan que es un bot
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security'
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="es-ES",
            timezone_id="Europe/Madrid"
        )
        
        # Aplicar el parche stealth para eliminar huellas de automatización
        stealth_sync(context)
        
        page = context.new_page()
        
        try:
            page.goto(config.URL_SALIDAS_ONLINE, timeout=60000, wait_until="domcontentloaded")
            
            # Esperar a que el JS de la web renderice los contadores
            page.wait_for_timeout(5000)
            
            html = page.content()
            
            # Comprobación robusta del bloqueo
            if "desde 08:00" not in html and ("TSPD" in html or "bobcmn" in html or "Checking your browser" in html or "ray" in html):
                raise Bloqueado("bizkaia.eus pide verificación antibots (lectura automática bloqueada)")
            
            if "desde 08:00" not in html:
                raise ValueError("La página no contiene los contadores esperados")
            
            return html
        finally:
            browser.close()


def capturar(html=None, raiz=None, ahora=None):
    ahora = ahora or datetime.now(TZ)
    carpeta = carpeta_origen(raiz)
    try:
        datos = parsear(html if html is not None else descargar_html())
    except Exception as e:
        guardar(None, ahora, carpeta, e)
        print(f"ERROR: {e}", file=sys.stderr)
        raise
    guardar(datos, ahora, carpeta)
    print(f"{ahora:%Y-%m-%d %H:%M} | hoy desde 8h: {datos['desde_8']} | año: {datos['anio']} "
          f"| activas: {len(datos['activas'])}")
    return datos


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="parsear un fichero HTML local en vez de descargar")
    a = ap.parse_args(argv)
    html = Path(a.html).read_text(encoding="utf-8") if a.html else None
    respaldo_github = html is None and os.environ.get("AURIA_ORIGEN") == "github"
    if respaldo_github and bloqueo_pendiente(datetime.now(TZ)):
        print("Captura de respaldo aplazada por el bloqueo de Bizkaia")
        return
    try:
        datos = capturar(html)
        if respaldo_github:
            publicar_directo(datos)
    except Bloqueado:
        if respaldo_github:
            publicar_estado_bloqueo(datetime.now(TZ))
        sys.exit(1)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
