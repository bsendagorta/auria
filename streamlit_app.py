"""AURIA — Panel de riesgo de emergencias en Bizkaia (Streamlit).

Local:   .venv/bin/streamlit run streamlit_app.py
Nube:    https://auria-bizkaia.streamlit.app (repo bsendagorta/auria)
Lee del repositorio público (raw.githubusercontent) lo que publican los procesos de GitHub:
    prediccion/ultima.json      predicción 6 h (cada 15 min)
    prediccion/directo.json     situación en directo (cada minuto)
    datos/modelo/*.json|csv     evaluación, patrones, modelos y tráfico (reentreno nocturno)
"""
import base64
import io
import json
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

st.set_page_config(page_title="AURIA · Emergencias Bizkaia", page_icon=str(Path(__file__).parent / "static" / "favicon-64.png"),
                   layout="wide")


def _icono_inicio():
    """Icono y nombre de AURIA al añadir el panel a la pantalla de inicio (iPhone/Android).
    Streamlit no deja tocar su <head>: un script (st.html con JavaScript) añade las etiquetas al
    documento de la app y al de la ventana principal de Streamlit Cloud (mismo origen). Iconos en static/ (servidos en /app/static/)."""
    v = "4"
    st.html(f"""<script>
    (function() {{
      // en Streamlit Cloud la app vive en /~/+/ : los estáticos están en /~/+/app/static/
      const base = new URL("app/static/", window.location.href.split("?")[0].replace(/[^/]*$/, "")).href;
      const docs = [document];
      try {{ if (window.top !== window) docs.push(window.top.document); }} catch (e) {{}}
      for (const d of docs) {{
        d.querySelectorAll('link[rel="apple-touch-icon"],link[rel="manifest"]').forEach(x => x.remove());
        const add = (rel, href, extra) => {{ const l = d.createElement("link"); l.rel = rel; l.href = href;
          Object.assign(l, extra || {{}}); d.head.appendChild(l); }};
        add("apple-touch-icon", base + "apple-touch-icon.png?v={v}", {{sizes: "180x180"}});
        add("icon", base + "icon-192.png?v={v}", {{sizes: "192x192", type: "image/png"}});
        add("manifest", base + "manifest.json?v={v}");
        const meta = (n, c) => {{ let m = d.querySelector('meta[name="' + n + '"]');
          if (!m) {{ m = d.createElement("meta"); m.name = n; d.head.appendChild(m); }} m.content = c; }};
        meta("apple-mobile-web-app-title", "AURIA");
        meta("application-name", "AURIA");
        meta("apple-mobile-web-app-capable", "yes");
        meta("mobile-web-app-capable", "yes");
        meta("apple-mobile-web-app-status-bar-style", "black-translucent");
        meta("theme-color", "#1f2e39");
        d.title = "AURIA";
      }}
    }})();
    </script>""", unsafe_allow_javascript=True, width="content")


_icono_inicio()

REPO_POR_DEFECTO = "bsendagorta/auria"
RAIZ = Path(__file__).parent
# estado (semáforo): colores reservados, siempre acompañados de icono y texto
NIVEL_HEX = {"verde": "#0ca30c", "amarillo": "#fab219", "naranja": "#ec835a", "rojo": "#d03b3b"}
NIVEL_RGB = {k: [int(v[i:i + 2], 16) for i in (1, 3, 5)] for k, v in NIVEL_HEX.items()}
EMOJI = {"verde": "🟢", "amarillo": "🟡", "naranja": "🟠", "rojo": "🔴"}
AZUL, NARANJA, GRIS = "#2a78d6", "#eb6834", "#8a8984"
FAMILIA_TXT = {
    "INCENDIO_URBANO": "Incendio urbano", "INCENDIO_FORESTAL_EXTERIOR": "Incendio forestal/exterior",
    "INCENDIO_INDUSTRIAL": "Incendio industrial", "TRAFICO": "Tráfico", "RESCATE_SALVAMENTO": "Rescate/salvamento",
    "METEO_ASISTENCIA": "Saneados, árboles, achiques", "ABEJAS_AVISPAS": "Avispas/abejas", "GAS_MMPP": "Gas/MMPP",
    "OTRAS_ASISTENCIAS": "Otras asistencias", "OTROS": "Otros",
}
FAMILIA_ICONO = {"INCENDIO_URBANO": "🔥", "INCENDIO_FORESTAL_EXTERIOR": "🌲", "INCENDIO_INDUSTRIAL": "🏭",
                 "TRAFICO": "🚗", "RESCATE_SALVAMENTO": "🆘", "METEO_ASISTENCIA": "🌬️", "ABEJAS_AVISPAS": "🐝",
                 "GAS_MMPP": "☣️", "OTRAS_ASISTENCIAS": "🛠️", "OTROS": "•"}

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px;}
.auria-hero {display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;
  padding:.9rem 1.2rem; border-radius:14px; background:linear-gradient(100deg,#1d1d1b 0%,#3a1f17 100%);
  color:#f0efec; margin-bottom:.8rem;}
.auria-hero h1 {font-size:1.55rem; margin:0; color:#f0efec; letter-spacing:.02em;}
.auria-hero .sub {color:#c3c2b7; font-size:.85rem;}
.auria-pill {display:inline-block; padding:.15rem .55rem; border-radius:99px; font-size:.78rem;
  background:#ffffff1a; color:#f0efec; margin-left:.3rem;}
.kpi {border:1px solid #8a898433; border-radius:12px; padding:.6rem .8rem; height:100%;}
.kpi .v {font-size:1.6rem; font-weight:700; line-height:1.1;}
.kpi .l {font-size:.78rem; opacity:.75;}
.kpi .d {font-size:.78rem; opacity:.85;}
.parque {border:1px solid #8a898433; border-left:6px solid var(--c); border-radius:12px;
  padding:.55rem .75rem; margin-bottom:.6rem; min-height:132px;}
.parque .t {font-weight:700; font-size:1rem;}
.parque .r {font-size:1.25rem; font-weight:700;}
.parque .s {font-size:.8rem; opacity:.8; line-height:1.35;}
div[data-testid="stTabs"] button p {font-size:.98rem;}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ carga de datos
def _repo():
    try:
        return st.secrets.get("GITHUB_REPO", REPO_POR_DEFECTO), st.secrets.get("GITHUB_TOKEN")
    except Exception:
        return REPO_POR_DEFECTO, None


ERRORES = {}


def _bajar(ruta, cada, local=True):
    """Contenido de un fichero del repo: GitHub (al día) y, si falla, la API de GitHub o la copia local."""
    repo, tok = _repo()
    try:
        if tok:
            r = requests.get(f"https://api.github.com/repos/{repo}/contents/{ruta}",
                             headers={"Authorization": f"Bearer {tok}"}, timeout=15)
            r.raise_for_status()
            return base64.b64decode(r.json()["content"]), "GitHub"
        r = requests.get(f"https://raw.githubusercontent.com/{repo}/main/{ruta}",
                         params={"t": int(datetime.now().timestamp() // cada)}, timeout=15)
        r.raise_for_status()
        return r.content, "GitHub"
    except Exception as e:
        ERRORES[ruta] = f"raw: {e}"
    try:   # segunda vía: API de contenidos (otro servidor y otro límite)
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/{ruta}",
                         headers={"Accept": "application/vnd.github.raw+json",
                                  **({"Authorization": f"Bearer {tok}"} if tok else {})}, timeout=15)
        r.raise_for_status()
        return r.content, "GitHub API"
    except Exception as e:
        ERRORES[ruta] = ERRORES.get(ruta, "") + f" · api: {e}"
    p = RAIZ / ruta
    return (p.read_bytes(), "copia local (desactualizada)") if local and p.exists() else (None, None)


@st.cache_data(ttl=120, show_spinner=False)
def leer_json(ruta, cada=120):
    b, origen = _bajar(ruta, cada)
    return (json.loads(b), origen) if b else (None, None)


@st.cache_data(ttl=900, show_spinner=False)
def leer_csv(ruta):
    b, _ = _bajar(ruta, 900)
    return pd.read_csv(io.BytesIO(b), dtype={"cod_ine": str}) if b else None


def _directo_api():
    """La API de GitHub da el fichero recién subido (raw.githubusercontent tiene ~5 min de caché).
    Sin token permite 60 peticiones/hora por IP: la caché compartida de 75 s se queda en ~48/hora."""
    repo, tok = _repo()
    r = requests.get(f"https://api.github.com/repos/{repo}/contents/prediccion/directo.json",
                     headers={"Accept": "application/vnd.github.raw+json",
                              **({"Authorization": f"Bearer {tok}"} if tok else {})}, timeout=10)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=75, show_spinner=False)
def leer_directo():
    try:
        return _directo_api(), None
    except Exception as e:
        ERRORES["api_directo"] = str(e)
    b, _ = _bajar("prediccion/directo.json", 30, local=False)
    if b:
        return json.loads(b), None
    try:   # en local se puede leer la web directamente
        from auria import directo, recolector_online
        import auria.config as cfg
        html = requests.get(cfg.URL_SALIDAS_ONLINE, timeout=6, headers={"User-Agent": cfg.USER_AGENT}).text
        return directo.enriquecer(recolector_online.parsear(html)), None
    except Exception as e:
        return None, (ERRORES.get("prediccion/directo.json", "") + f" · web: {e}")


@st.cache_data(ttl=86400, show_spinner=False)
def _geo(ruta):
    b, _ = _bajar(ruta, 3600)
    if not b:
        raise RuntimeError(f"sin {ruta}")      # una excepción no queda en caché: se reintenta
    return json.loads(b)


def geo(ruta):
    try:
        return _geo(ruta)
    except Exception:
        return None


def capas_zonas(parques, por_municipio=False):
    """Zona de actuación de cada parque (silueta de sus municipios) coloreada por el semáforo."""
    idx = {p["id"]: p for p in parques}
    capas = []
    if por_municipio:
        g = geo("datos/geo/municipios_bizkaia.geojson")
        if g:
            mx = max(f["properties"]["salidas_anio"] for f in g["features"] if f["properties"]["parque"] != "BILBAO")
            for f in g["features"]:
                pr = f["properties"]
                if pr["parque"] == "BILBAO":
                    pr["color"] = [150, 150, 150, 90]
                else:   # secuencial azul: más salidas, más oscuro
                    t = (pr["salidas_anio"] / max(mx, 1)) ** 0.5
                    pr["color"] = [int(205 - 192 * t), int(226 - 172 * t), int(251 - 144 * t), 190]
                pr["txt"] = f"{pr['nombre']}\nParque: {pr['parque_nombre']}\n{pr['salidas_anio']:.0f} salidas/año (2023-25)"
            capas.append(pdk.Layer("GeoJsonLayer", g, get_fill_color="properties.color", get_line_color=[255, 255, 255],
                                   line_width_min_pixels=1, pickable=True, stroked=True, filled=True))
    g = geo("datos/geo/zonas_parques.geojson")
    if g:
        for f in g["features"]:
            pr = f["properties"]
            p = idx.get(pr["parque"])
            if p is None:
                pr["color"], pr["borde"] = [150, 150, 150, 70], [120, 120, 120, 200]
                pr["txt"] = f"{pr['nombre']}"
            else:
                c = NIVEL_RGB[p["nivel"]]
                pr["color"] = [0, 0, 0, 0] if por_municipio else c + [95]
                pr["borde"] = c + [255]
                sit = p.get("situacion_ahora") or "sin situación meteorológica destacable"
                pr["txt"] = (f"{p['nombre']} · {EMOJI[p['nivel']]} {p['nivel']} (×{p['ratio_max']} lo normal)\n"
                             f"Esperadas 6 h: {p['salidas_esperadas_6h']} (normal {p['normal_6h']})\n"
                             f"Ahora: {sit}\n{pr['n_municipios']} municipios: {pr['municipios']}")
        capas.append(pdk.Layer("GeoJsonLayer", g, get_fill_color="properties.color", get_line_color="properties.borde",
                               line_width_min_pixels=2, line_width_max_pixels=3, pickable=not por_municipio, stroked=True, filled=True))
    # el parque (cuartel) como punto
    capas.append(pdk.Layer("ScatterplotLayer", pd.DataFrame([{"lat": p["lat"], "lon": p["lon"],
                                                              "txt": p["nombre"]} for p in parques]),
                           get_position="[lon, lat]", get_fill_color=[255, 255, 255, 255], get_line_color=[29, 29, 27],
                           stroked=True, line_width_min_pixels=2, get_radius=150, radius_min_pixels=4, radius_max_pixels=7, pickable=True))
    return capas


def rumbo(g):
    try:
        return ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][int(((float(g) + 22.5) % 360) // 45)]
    except (TypeError, ValueError):
        return "—"


def kpi(col, valor, etiqueta, detalle=""):
    col.markdown(f'<div class="kpi"><div class="l">{etiqueta}</div><div class="v">{valor}</div>'
                 f'<div class="d">{detalle}</div></div>', unsafe_allow_html=True)


def coords_municipio():
    m = leer_csv("datos/municipios.csv")
    return {} if m is None else {r.cod_ine: (r.lat, r.lon) for r in m.dropna(subset=["lat"]).itertuples()}


datos, origen = leer_json("prediccion/ultima.json")
if datos is None:
    st.info("Aún no hay predicciones publicadas.")
    st.stop()
parques = datos["parques"]
biz = datos["bizkaia"]
gen = datetime.fromisoformat(datos["generado"])
peor = max(parques, key=lambda p: p["ratio_max"])
avisos = [k for k, ok in datos.get("fuentes_ok", {}).items() if not ok]

st.markdown(f"""
<div class="auria-hero">
  <div><h1>🚒 AURIA</h1><div class="sub">Predicción de salidas de Bomberos de Bizkaia · 8 parques forales</div></div>
  <div class="sub">Predicción {gen:%d/%m %H:%M}<span class="auria-pill">modelo: {datos['modelo']}</span>
  <span class="auria-pill">{'⚠️ sin ' + ', '.join(avisos) if avisos else 'fuentes OK'}</span></div>
</div>""", unsafe_allow_html=True)

t_ahora, t_6h, t_carr, t_apr, t_pat = st.tabs(
    ["🔴 Ahora", "⏱️ Próximas 6 h", "🛣️ Carreteras", "📈 Aprendizaje", "🔎 Patrones"])


# ------------------------------------------------------------------ AHORA
@st.fragment(run_every=60)
def seccion_ahora():
    from auria import directo, parques as P
    vivo, err = leer_directo()
    k = st.columns(5)
    if vivo is None:
        st.warning(f"No hay lectura en directo ({err}).")
        return
    ts = datetime.fromisoformat(vivo["ts"])
    retraso = (datetime.now(ts.tzinfo) - ts).total_seconds() / 60
    act = vivo["actuaciones"]
    kpi(k[0], len(act), "Actuaciones en curso")
    kpi(k[1], sum(x["n_vehiculos"] for x in act), "Vehículos fuera",
        f"{sum(1 for x in act for v in x['vehiculos'] if v['estado'] == 'EN_SINIESTRO')} en siniestro")
    kpi(k[2], vivo["salidas_desde_8"], "Salidas desde las 08:00", "vehículos movilizados")
    kpi(k[3], f"{biz['salidas_esperadas_6h']:.1f}", "Intervenciones esperadas 6 h",
        f"normal {biz['normal_6h']:.1f}")
    kpi(k[4], f"{EMOJI[peor['nivel']]} {peor['nombre'].split(' (')[0]}", "Parque con más riesgo",
        f"×{peor['ratio_max']} lo normal")
    if retraso > 12:
        st.warning(f"Última lectura en directo hace {retraso:.0f} min: el recolector puede estar parado.")

    izq, der = st.columns([3, 2])
    with izq:
        cm = coords_municipio()
        pts = []
        for i, x in enumerate(act):
            ll = cm.get(P.ine_de_nombre(x["ubicacion"]))
            if ll:
                pts.append({"lat": ll[0] + 0.004 * (i % 3), "lon": ll[1] + 0.004 * (i // 3 % 3),
                            "txt": f"{FAMILIA_ICONO.get(x['familia'], '•')} {x['tipo']}\n{x['ubicacion']} · "
                                   f"{x['n_vehiculos']} veh."})
        capas = capas_zonas(parques, por_municipio=st.session_state.get("ver_municipios", False))
        if pts:
            capas.append(pdk.Layer("ScatterplotLayer", pd.DataFrame(pts), get_position="[lon, lat]",
                                   get_fill_color=[20, 20, 20, 230], get_line_color=[255, 255, 255],
                                   stroked=True, line_width_min_pixels=2, get_radius=200, radius_min_pixels=5,
                                   radius_max_pixels=9, pickable=True))
        st.pydeck_chart(pdk.Deck(map_style=None, tooltip={"text": "{txt}"}, layers=capas,
                                 initial_view_state=pdk.ViewState(latitude=43.24, longitude=-2.85, zoom=8.7)),
                        height=430)
        st.toggle("Ver municipios (color = salidas al año)", key="ver_municipios")
        st.caption("Cada zona es el conjunto de municipios que cubre el parque, con el color de su semáforo. "
                   "Puntos negros: actuaciones en curso. Bilbao (gris) tiene servicio municipal. "
                   "Límites municipales 1:5.000: Eusko Jaurlaritza / Gobierno Vasco (CC BY 4.0).")
    with der:
        st.markdown(f"**Actuaciones en curso** · leído {ts:%H:%M:%S}")
        if not act:
            st.success("Sin actuaciones en curso.")
        for x in act:
            with st.container(border=True):
                st.markdown(f"{FAMILIA_ICONO.get(x['familia'], '•')} **{x['tipo'].capitalize()}**  \n"
                            f"{x['ubicacion']} · {x['zona'] or ''}  \n"
                            f"<span style='opacity:.7'>zona de parque: {x['parque_nombre']}</span>",
                            unsafe_allow_html=True)
                st.caption(" · ".join(f"{v['tipo']}: {directo.ESTADO_TXT[v['estado']].lower()}"
                                      for v in x["vehiculos"]))


with t_ahora:
    seccion_ahora()


# ------------------------------------------------------------------ PRÓXIMAS 6 H
with t_6h:
    cols = st.columns(4)
    for i, p in enumerate(sorted(parques, key=lambda p: -p["ratio_max"])):
        fac = "<br>".join("· " + f for f in p["factores"][:3]) or "sin factores de riesgo activos"
        sit = p.get("situacion_ahora") or "sin situación meteorológica destacable"
        cols[i % 4].markdown(f"""
<div class="parque" style="--c:{NIVEL_HEX[p['nivel']]}">
 <div class="t">{EMOJI[p['nivel']]} {p['nombre']}</div>
 <div><span class="r">×{p['ratio_max']}</span> <span class="s">lo normal · pico {p['hora_pico'][11:16]}</span></div>
 <div class="s">Esperadas <b>{p['salidas_esperadas_6h']}</b> (normal {p['normal_6h']}) · P(≥1) <b>{p['prob_6h']:.0%}</b></div>
 <div class="s" style="margin-top:.2rem"><b>Ahora:</b> {sit}</div>
 <div class="s" style="margin-top:.25rem">{fac}</div>
</div>""", unsafe_allow_html=True)
    st.caption("Semáforo según cuántas veces supera lo normal: 🟢 <1,5 · 🟡 1,5-2,5 · 🟠 2,5-4 · 🔴 ≥4.")

    filas = [{"hora": pd.Timestamp(x["hora"]), "parque": p["nombre"].split(" (")[0], "esperadas": x["lambda"],
              "normal": x["normal"]} for p in parques for x in p["horas"]]
    h = pd.DataFrame(filas)
    tot = h.groupby("hora")[["esperadas", "normal"]].sum().reset_index().melt("hora", var_name="serie")
    tot["serie"] = tot["serie"].map({"esperadas": "Esperadas", "normal": "Normal (histórico)"})
    st.markdown("**Bizkaia: intervenciones esperadas por hora**")
    st.altair_chart(alt.Chart(tot).mark_line(point=alt.OverlayMarkDef(size=60), strokeWidth=2).encode(
        x=alt.X("hora:T", title=None, axis=alt.Axis(format="%H:%M")),
        y=alt.Y("value:Q", title="intervenciones/hora"),
        color=alt.Color("serie:N", scale=alt.Scale(range=[AZUL, GRIS]), legend=alt.Legend(orient="top", title=None)),
        strokeDash=alt.condition("datum.serie != 'Esperadas'", alt.value([4, 3]), alt.value([1, 0])),
        tooltip=[alt.Tooltip("hora:T", format="%H:%M"), "serie", alt.Tooltip("value:Q", format=".2f")],
    ).properties(height=230), width="stretch")

    ev = leer_csv("datos/eventos_auto.csv")
    if ev is not None and len(ev):
        ev["inicio"] = pd.to_datetime(ev["inicio"])
        prox = ev[(ev["inicio"] >= pd.Timestamp.now().normalize()) &
                  (ev["inicio"] <= pd.Timestamp.now().normalize() + pd.Timedelta(days=3))].sort_values("inicio")
        with st.expander(f"📅 Fiestas y eventos con público en los próximos 3 días ({len(prox)})", expanded=False):
            nom = {k: v["nombre"] for k, v in ((p["id"], p) for p in parques)}
            prox = prox.assign(parque=prox["parques"].map(lambda x: ", ".join(nom.get(i, i) for i in str(x).split(";"))),
                               cuando=prox["inicio"].dt.strftime("%a %d %H:%M"),
                               nivel=prox["nivel"].map({1: "con público", 2: "masivo"}))
            st.dataframe(prox[["cuando", "nombre", "nivel", "parque"]], hide_index=True, width="stretch")
            st.caption("Fiestas locales: calendario laboral de Euskadi. Eventos: agenda cultural Kulturklik "
                       "(Open Data Euskadi), asignados al parque por su municipio.")

    sel = st.selectbox("Detalle de un parque", [p["nombre"] for p in parques])
    p = next(x for x in parques if x["nombre"] == sel)
    st.dataframe(pd.DataFrame([{
        "hora": x["hora"][11:16], "nivel": f"{EMOJI[x['nivel']]} ×{x['ratio']}", "esperadas": x["lambda"],
        "normal": x["normal"], "P(≥1)": x["prob"],
        "tipos más probables": ", ".join(FAMILIA_TXT.get(f["familia"], f["familia"]) for f in x["familias_top"]),
        "situación": x.get("situacion_txt", ""),
        "viento": (f"{x['meteo'].get('viento_kmh') or 0:.0f} km/h de {rumbo(x['meteo'].get('dir_viento'))}, "
                   f"racha {x['meteo']['racha_kmh']:.0f}"),
        "lluvia mm/h": x["meteo"]["lluvia_1h"], "T ºC": x["meteo"]["temp"],
        "factores": "; ".join(x["factores"]),
    } for x in p["horas"]]), hide_index=True, width="stretch",
        column_config={"P(≥1)": st.column_config.ProgressColumn(format="percent", min_value=0.0, max_value=1.0)})


# ------------------------------------------------------------------ CARRETERAS
with t_carr:
    tramos = [{"carretera": c["carretera"], "tramo": f"km {c['km_ini']}-{c['km_fin']}",
               "parque": p["nombre"].split(" (")[0], "P(≥1 accidente con víctimas, 6 h)": c["prob"],
               "accidentes/año": c["accidentes_anio"], "% graves": c["pct_graves"],
               "IMD (veh/día)": c.get("imd"), "peligrosidad": c.get("ip"),
               "hora habitual": f"{c['hora_pico']:02d}:00"} for p in parques for c in p.get("carreteras", [])]
    dgt = datos.get("trafico_dgt") or {}
    ll = dgt.get("lluvia", {})
    k = st.columns(3)
    kpi(k[0], f"×{ll['rr_lluvia']:.2f}" if ll.get("rr_lluvia") else "—", "Riesgo de accidente con lluvia",
        "frente a seco, misma hora (DGT + Open-Meteo)")
    kpi(k[1], f"×{ll['rr_lluvia_fuerte']:.1f}" if ll.get("rr_lluvia_fuerte") else "—", "Con lluvia fuerte")
    kpi(k[2], dgt.get("accidentes", "—"), "Accidentes con víctimas analizados",
        f"{dgt['anios'][0]}-{dgt['anios'][-1]}" if dgt.get("anios") else "")
    if tramos:
        t6 = pd.DataFrame(tramos).sort_values("P(≥1 accidente con víctimas, 6 h)", ascending=False)
        st.markdown("**Tramos con más riesgo en las próximas 6 horas**")
        st.dataframe(t6, hide_index=True, width="stretch", column_config={
            "P(≥1 accidente con víctimas, 6 h)": st.column_config.ProgressColumn(
                format="percent", min_value=0.0, max_value=float(max(0.05, t6.iloc[:, 3].max())))})
    perfil = leer_csv("datos/modelo/trafico_perfil_horario.csv")
    if perfil is not None:
        pb = perfil.groupby(["tipo_dia", "hora"])["factor_dia"].mean().reset_index()
        pb["día"] = pb["tipo_dia"].map({"LJ": "Lunes-jueves", "V": "Viernes", "S": "Sábado", "D": "Domingo/festivo"})
        st.markdown("**A qué hora hay accidentes (Bizkaia, 1 = hora media)**")
        st.altair_chart(alt.Chart(pb).mark_line(strokeWidth=2).encode(
            x=alt.X("hora:O", title="hora"), y=alt.Y("factor_dia:Q", title="riesgo relativo"),
            color=alt.Color("día:N", scale=alt.Scale(domain=["Lunes-jueves", "Viernes", "Sábado", "Domingo/festivo"],
                                                    range=[AZUL, NARANJA, "#1baf7a", "#6250d6"]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["día", "hora", alt.Tooltip("factor_dia:Q", format=".2f")],
        ).properties(height=260), width="stretch")
    est = leer_csv("datos/modelo/aforos_estaciones.csv")
    rv = leer_csv("datos/modelo/trafico_riesgo_vehiculo.csv")
    if est is not None and len(est):
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("**Intensidad de tráfico por estación de aforo** (IMD, vehículos/día)")
            st.dataframe(est[["carretera", "pk", "estacion", "imd", "pct_pesados", "vel_media", "hora_punta",
                              "dias_medidos"]].rename(columns={"pct_pesados": "% pesados", "vel_media": "vel. media",
                                                               "hora_punta": "hora punta", "dias_medidos": "días"}),
                         hide_index=True, width="stretch", height=320,
                         column_config={"imd": st.column_config.ProgressColumn(
                             "IMD", format="%d", min_value=0, max_value=float(est["imd"].max()))})
        with c2:
            st.markdown("**Mapa de aforos** (tamaño = IMD)")
            em = est.dropna(subset=["lat"]).assign(r=lambda x: 300 + 2500 * (x["imd"] / x["imd"].max()) ** .5,
                                                    txt=lambda x: x["carretera"] + " pk " + x["pk"].astype(str)
                                                    + "\n" + x["imd"].astype(int).astype(str) + " veh/día")
            st.pydeck_chart(pdk.Deck(map_style=None, tooltip={"text": "{txt}"},
                                     initial_view_state=pdk.ViewState(latitude=43.24, longitude=-2.85, zoom=8.6),
                                     layers=[pdk.Layer("ScatterplotLayer", em, get_position="[lon, lat]",
                                                       get_radius="r", get_fill_color=[42, 120, 214, 170],
                                                       stroked=True, get_line_color=[255, 255, 255],
                                                       line_width_min_pixels=1, pickable=True)]), height=320)
    if rv is not None and len(rv):
        rv["día"] = rv["tipo_dia"].map({"LJ": "Lunes-jueves", "V": "Viernes", "S": "Sábado", "D": "Domingo/festivo"})
        st.markdown("**Riesgo por vehículo según la hora** (accidentes ÷ tráfico; 1 = media del día)")
        st.altair_chart(alt.Chart(rv).mark_line(strokeWidth=2).encode(
            x=alt.X("hora:O"), y=alt.Y("riesgo_por_vehiculo:Q", title="riesgo por vehículo"),
            color=alt.Color("día:N", scale=alt.Scale(domain=["Lunes-jueves", "Viernes", "Sábado", "Domingo/festivo"],
                                                    range=[AZUL, NARANJA, "#1baf7a", "#6250d6"]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["día", "hora", alt.Tooltip("riesgo_por_vehiculo:Q", format=".2f")],
        ).properties(height=240), width="stretch")
        st.caption("Pocas personas conducen de madrugada, pero cada vehículo tiene más riesgo: por eso el "
                   "número de accidentes y el riesgo individual no coinciden.")
    ah, _ = leer_json("datos/modelo/accidentes_hora.json", 900)
    if ah and ah.get("accidente", {}).get("variables"):
        from auria.accidentes_hora import VARIABLES as VAH
        st.markdown("**Meteo de la hora y lo que pasa en la carretera** (incidencias de tráfico con hora exacta, "
                    "Bizkaia sin Bilbao ciudad, 2021-2026 · riesgo frente a una hora parecida sin esa situación)")
        cols = st.columns(2)
        for col, clase, tit in ((cols[0], "accidente", "Accidentes"), (cols[1], "obstaculo",
                                                                       "Obstáculos: objetos, árboles, desprendimientos (se aplica a saneados y árboles)")):
            r = ah.get(clase, {})
            if not r.get("variables"):
                continue
            with col:
                v = r.get("validacion") or {}
                st.caption(f"{tit}: {r['eventos']:,} casos en {r['meses']} meses completos · validación "
                           f"2025-26: {v.get('mejora_pct', 0):+.2f} % · en directo: {'sí' if r.get('activo') else 'no'}")
                t = pd.DataFrame([{"situación en esa hora": VAH[k], "×": e["rr"], "IC 95 %": f"{e['lo']}-{e['hi']}",
                                   "claro": "✓" if (e["lo"] > 1 or e["hi"] < 1) else "", "casos": e["eventos"]}
                                  for k, e in r["variables"].items()]).sort_values("×", ascending=False)
                st.dataframe(t, hide_index=True, width="stretch",
                             column_config={"×": st.column_config.NumberColumn(format="×%.2f")})
    st.caption("Fuentes: accidentes con víctimas DGT (vías interurbanas, sin Bilbao) calibrados con las salidas "
               "reales de SPEIS; intensidad de tráfico de los aforadores del Gobierno Vasco (Open Data Euskadi, "
               "2022-2024). Peligrosidad = accidentes con víctimas por 100 millones de veh·km.")


# ------------------------------------------------------------------ APRENDIZAJE
with t_apr:
    ev, _ = leer_json("datos/modelo/evaluacion.json", 600)
    mh, _ = leer_json("datos/modelo/modelo_horario.json", 600)
    mm, _ = leer_json("datos/modelo/modelo_mensual_municipio.json", 600)
    st.markdown("**¿Acierta AURIA?** Cada hora se compara lo que se predijo con lo que pasó "
                "(contador de salidas de bizkaia.eus).")
    if ev and ev.get("estado") == "ok":
        t, u = ev["total"], ev["ultimos_7_dias"]
        k = st.columns(4)
        kpi(k[0], u["horas"], "Horas evaluadas (7 días)", f"desde {ev['desde'][:10]}")
        kpi(k[1], f"{u['salidas_predichas']:.0f} / {u['salidas_reales']:.0f}", "Predichas / reales (7 días)",
            f"sesgo {u['sesgo_pct']:+.0f} %")
        kpi(k[2], f"{u['mae_hora']:.2f}", "Error medio por hora", "intervenciones")
        kpi(k[3], f"{u['skill_vs_normal']:+.0%}", "Mejora frente a la tasa normal",
            "> 0 = las variables aportan")
        pdia = pd.DataFrame(ev.get("por_dia", []))
        if len(pdia):
            m = pdia.melt("dia", ["real", "predicho", "normal"], var_name="serie")
            st.altair_chart(alt.Chart(m).mark_line(point=True, strokeWidth=2).encode(
                x=alt.X("dia:T", title=None), y=alt.Y("value:Q", title="intervenciones/día"),
                color=alt.Color("serie:N", scale=alt.Scale(domain=["real", "predicho", "normal"],
                                                           range=[NARANJA, AZUL, GRIS]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=["dia:T", "serie", alt.Tooltip("value:Q", format=".1f")],
            ).properties(height=240), width="stretch")
        eh = leer_csv("datos/modelo/evaluacion_horaria.csv")
        if eh is not None and len(eh):
            with st.expander("Detalle hora a hora"):
                st.dataframe(eh.rename(columns={"Unnamed: 0": "hora"}), hide_index=True, width="stretch")
    else:
        st.info("La evaluación empieza en cuanto hay horas completas con predicción y contador "
                f"({(ev or {}).get('estado', 'sin datos')}).")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Modelo horario (LightGBM)**")
        if mh and mh.get("activo"):
            st.success(f"Activo desde {mh['fecha'][:10]}: bate a la base y a las reglas en la última semana.")
        else:
            st.markdown(f"En espera: {(mh or {}).get('motivo', 'sin entrenar')}. Se entrena cada noche con las "
                        "capturas por minuto y solo se activa si predice mejor (≥21 días y ≥300 intervenciones).")
        st.json(mh or {}, expanded=False)
    with c2, st.container(border=True):
        st.markdown("**Modelo mensual por municipio** (validación en el último año completo)")
        if mm:
            st.dataframe(pd.DataFrame(mm["metricas"]).rename(columns={"modelo": "modelo", "desv_poisson": "desv. Poisson"}),
                         hide_index=True, width="stretch")
            st.caption(f"Año de prueba {mm['anio_test']} · mejor: **{mm['mejor']}** · ref = media del mismo mes en "
                       "años anteriores (lo que hay que batir).")


# ------------------------------------------------------------------ PATRONES
with t_pat:
    pt, _ = leer_json("datos/modelo/patrones.json", 900)
    if not pt:
        st.info("Patrones pendientes del próximo reentreno.")
    else:
        et = pt["etiquetas"]
        st.markdown(f"Patrones de **{pt['intervenciones']:,} intervenciones reales** "
                    f"({pt['anios'][0]}-{pt['anios'][-1]}, Open Data Bizkaia, sin Bilbao).".replace(",", "."))
        meses = "Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic".split()
        e = pd.DataFrame(pt["estacionalidad"]).T.rename(index=et)
        e.columns = meses
        em = e.reset_index(names="familia").melt("familia", var_name="mes", value_name="índice")
        st.markdown("**Estacionalidad** (1 = mes medio de esa familia)")
        st.altair_chart(alt.Chart(em).mark_rect(stroke="#fcfcfb", strokeWidth=2, cornerRadius=3).encode(
            x=alt.X("mes:N", sort=meses, title=None), y=alt.Y("familia:N", title=None),
            color=alt.Color("índice:Q", scale=alt.Scale(range=["#cde2fb", "#2a78d6", "#0d366b"], domainMid=1),
                            legend=alt.Legend(title="índice")),
            tooltip=["familia", "mes", alt.Tooltip("índice:Q", format=".2f")],
        ).properties(height=300), width="stretch")
        c1, c2 = st.columns(2)
        with c1:
            fr = pd.DataFrame(pt["franja"]).T.rename(index=et).rename(
                columns={"M": "Mañana 08-14", "T": "Tarde 14-20", "N": "Noche 20-08"})
            st.markdown("**Por franja** (intervenciones/hora, 1 = media)")
            st.dataframe(fr.style.background_gradient(cmap="Blues", axis=None).format("{:.2f}"), width="stretch")
        with c2:
            tn = pd.DataFrame(pt["tendencia"]).T.rename(index=et)
            st.markdown("**Total anual por familia**")
            st.dataframe(tn.astype(int), width="stretch")
            st.caption("En 2023 cambió la clasificación de tipos (p.ej. muchos incendios pasan de urbano a "
                       "exterior): compara 2021-22 con cautela.")
        if pt.get("meteo"):
            mt = pd.DataFrame(pt["meteo"]).rename(index=et, columns=pt["meteo_etiquetas"])
            st.markdown("**Meteorología del mes**: meses con más (tercil alto) ÷ meses con menos (tercil bajo), "
                        "misma estación")
            st.dataframe(mt.style.background_gradient(cmap="RdBu_r", vmin=0.5, vmax=1.5, axis=None)
                         .format("×{:.2f}", na_rep="—"), width="stretch")
        st.caption(pt["nota"])
    es, _ = leer_json("datos/modelo/situaciones_efectos.json", 900)
    if es and es.get("efectos"):
        from auria.situaciones import SITUACIONES
        st.markdown("---")
        st.markdown(f"### Situaciones meteorológicas: efecto medido ({es['anios'][0]}-{es['anios'][-1]})")
        st.caption("Multiplicador de salidas en un día con esa situación frente a un día normal del mismo mes y "
                   "parque (meteo horaria ERA5 de cada parque × salidas SPEIS). ✓ = intervalo del 95 % no "
                   "incluye 1. Solo se aplican en directo los tipos que mejoran la predicción del año de prueba.")
        filas = []
        for fam, ef in es["efectos"].items():
            for s_, e in ef.items():
                filas.append({"tipo": pt["etiquetas"].get(fam, fam) if pt else fam,
                              "situación": " ".join(SITUACIONES[s_]), "×": e["m"],
                              "IC 95 %": f"{e['lo']}-{e['hi']}", "claro": "✓" if (e["lo"] > 1 or e["hi"] < 1) else "",
                              "días": e["dias"], "en directo": "sí" if es.get("activo", {}).get(fam) else "no"})
        tabla = pd.DataFrame(filas)
        solo = st.toggle("Solo efectos claros", value=True)
        if solo:
            tabla = tabla[tabla["claro"] == "✓"]
        st.dataframe(tabla.sort_values("×", ascending=False), hide_index=True, width="stretch",
                     column_config={"×": st.column_config.NumberColumn(format="×%.2f")})
        val = pd.DataFrame(es.get("validacion", {})).T
        if len(val):
            val.index = [pt["etiquetas"].get(i, i) if pt else i for i in val.index]
            st.markdown(f"**Validación en {es['anio_test']}** (desviación de Poisson; mejora > 0 = las "
                        "situaciones predicen mejor que solo la referencia)")
            st.dataframe(val[["dev_ref", "dev_situaciones", "mejora_pct", "salidas_test"]].rename(columns={
                "dev_ref": "referencia", "dev_situaciones": "con situaciones", "mejora_pct": "mejora %",
                "salidas_test": "salidas"}), width="stretch")

    mv, _ = leer_json("datos/modelo/movilidad.json", 900)
    if mv:
        st.markdown("---")
        st.markdown(f"### Presencia de gente (datos anónimos de móviles, MITMS) · {mv['dias']} días "
                    f"({mv['desde']} → {mv['hasta']})")
        perf = leer_csv("datos/modelo/movilidad_perfil.csv")
        if perf is not None and len(perf):
            nom = {p["id"]: p["nombre"].split(" (")[0] for p in parques}
            pp = perf[perf["parque"] != "BILBAO"].assign(parque=lambda x: x["parque"].map(nom))
            td = st.radio("Tipo de día", ["LJ", "V", "S", "D"], horizontal=True,
                          format_func={"LJ": "Lunes-jueves", "V": "Viernes", "S": "Sábado", "D": "Domingo/festivo"}.get)
            st.altair_chart(alt.Chart(pp[pp["tipo_dia"] == td]).mark_line(strokeWidth=2).encode(
                x=alt.X("hora:O"), y=alt.Y("relativo:Q", title="presencia (1 = hora media del parque)"),
                color=alt.Color("parque:N", legend=alt.Legend(orient="top", title=None)),
                tooltip=["parque", "hora", alt.Tooltip("relativo:Q", format=".2f"),
                         alt.Tooltip("frac_visitantes:Q", format=".0%", title="de fuera de Bizkaia")],
            ).properties(height=260), width="stretch")
        ta = pd.DataFrame(mv.get("top_aglomeraciones", []))
        if len(ta):
            st.markdown("**Días con más visitantes de lo normal** (índice 2 = el doble que un día parecido)")
            st.dataframe(ta.assign(parque=ta["parque"].map({p["id"]: p["nombre"] for p in parques}).fillna(ta["parque"])),
                         hide_index=True, width="stretch")
        st.caption(mv.get("nota", ""))

with st.expander("Cómo funciona AURIA"):
    st.markdown("""
- **Normal**: tasa histórica real de cada parque por mes y franja (SPEIS 2023-hoy). En tráfico, la forma por
  hora y tipo de día viene de los accidentes con víctimas de la DGT.
- **Esperadas**: lo normal × factores de meteorología (Open-Meteo), calendario, tráfico (Open Data Euskadi) y
  eventos. Cada noche AURIA se reentrena con los datos reales y un modelo LightGBM sustituye a las reglas
  cuando demuestra predecir mejor en la última semana.
- **Aprendizaje**: se mide cada hora lo predicho frente a lo ocurrido; nada se da por bueno sin comprobarlo.
- Herramienta experimental de apoyo: no sustituye a la información oficial del 112 ni de Bizkaia Prest.
""")
st.caption(f"Datos: {origen} · repositorio github.com/{_repo()[0]}")
