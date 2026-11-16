"""AURIA — Panel de riesgo por parque (Streamlit).

Local:   .venv/bin/streamlit run streamlit_app.py
Nube:    Streamlit Community Cloud -> New app -> este repositorio -> streamlit_app.py
         Para leer siempre la última predicción sin esperar al redespliegue, añade en Secrets:
             GITHUB_TOKEN = "github_pat_..."   (permiso de solo lectura de contenidos del repo)
             GITHUB_REPO  = "usuario/auria"
"""
import base64
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

st.set_page_config(page_title="AURIA · Riesgo por parque", page_icon="🚒", layout="wide")

COLORES = {"verde": [46, 160, 67], "amarillo": [230, 180, 0], "naranja": [240, 120, 20], "rojo": [210, 40, 40]}
EMOJI = {"verde": "🟢", "amarillo": "🟡", "naranja": "🟠", "rojo": "🔴"}
FAMILIA_TXT = {
    "INCENDIO_URBANO": "Incendio urbano", "INCENDIO_FORESTAL_EXTERIOR": "Incendio forestal/exterior",
    "INCENDIO_INDUSTRIAL": "Incendio industrial", "TRAFICO": "Tráfico", "RESCATE_SALVAMENTO": "Rescate/salvamento",
    "METEO_ASISTENCIA": "Saneados, árboles, achiques", "ABEJAS_AVISPAS": "Avispas/abejas", "GAS_MMPP": "Gas/MMPP",
    "OTRAS_ASISTENCIAS": "Otras asistencias", "OTROS": "Otros",
}


@st.cache_data(ttl=300)
def cargar():
    try:
        tok, repo = st.secrets["GITHUB_TOKEN"], st.secrets["GITHUB_REPO"]
    except Exception:
        tok = repo = None
    if tok and repo:
        try:
            r = requests.get(f"https://api.github.com/repos/{repo}/contents/prediccion/ultima.json",
                             headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                             timeout=15)
            r.raise_for_status()
            return json.loads(base64.b64decode(r.json()["content"])), "GitHub (en vivo)"
        except Exception as e:
            st.warning(f"No se pudo leer de GitHub ({e}); uso la copia local.")
    p = Path(__file__).parent / "prediccion" / "ultima.json"
    if not p.exists():
        return None, None
    return json.loads(p.read_text(encoding="utf-8")), "copia del repositorio"


datos, origen = cargar()
st.title("AURIA · Riesgo de salidas por parque")
if datos is None:
    st.info("Aún no hay predicciones. Ejecuta `python -m auria.prevision` o espera a la tarea horaria.")
    st.stop()

gen = datetime.fromisoformat(datos["generado"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Actualizado", gen.strftime("%d/%m %H:%M"))
biz = datos["bizkaia"]
c2.metric("Salidas esperadas (6 h, Bizkaia)", biz["salidas_esperadas_6h"],
          f"{biz['salidas_esperadas_6h'] - biz['normal_6h']:+.1f} vs normal", delta_color="inverse")
if biz.get("contador"):
    c3.metric("Salidas hoy desde las 08:00", biz["contador"]["desde_8"])
    c4.metric("Salidas este año", f"{biz['contador']['anio']:,}".replace(",", "."))
avisos = [k for k, ok in datos.get("fuentes_ok", {}).items() if not ok]
st.caption(f"Modelo: **{datos['modelo']}** · fuente: {origen}"
           + (f" · ⚠️ sin datos de: {', '.join(avisos)}" if avisos else ""))

parques = datos["parques"]

# --- mapa
df_mapa = pd.DataFrame([{
    "nombre": p["nombre"], "lat": p["lat"], "lon": p["lon"], "nivel": p["nivel"], "ratio": p["ratio_max"],
    "esperadas": p["salidas_esperadas_6h"], "color": COLORES[p["nivel"]] + [200],
    "radio": 1500 + 2500 * p["salidas_esperadas_6h"], "factores": "; ".join(p["factores"][:3]) or "—",
} for p in parques])
st.pydeck_chart(pdk.Deck(
    map_style=None,
    initial_view_state=pdk.ViewState(latitude=43.25, longitude=-2.82, zoom=8.6),
    layers=[pdk.Layer("ScatterplotLayer", df_mapa, get_position="[lon, lat]", get_fill_color="color",
                      get_radius="radio", pickable=True, stroked=True, get_line_color=[255, 255, 255],
                      line_width_min_pixels=1)],
    tooltip={"text": "{nombre}\n{nivel} · ×{ratio} lo normal\nEsperadas 6 h: {esperadas}\n{factores}"},
), width="stretch")

# --- tarjetas
st.subheader("Semáforo de las próximas 6 horas")
cols = st.columns(4)
for i, p in enumerate(parques):
    with cols[i % 4].container(border=True):
        st.markdown(f"### {EMOJI[p['nivel']]} {p['nombre']}")
        st.markdown(f"**×{p['ratio_max']}** lo normal · pico {p['hora_pico'][11:16]} h")
        st.markdown(f"Esperadas: **{p['salidas_esperadas_6h']}** (normal {p['normal_6h']}) · "
                    f"P(≥1 salida): **{p['prob_6h']:.0%}**")
        if p["factores"]:
            st.markdown("\n".join(f"- {f}" for f in p["factores"][:4]))
        else:
            st.caption("Sin factores de riesgo activos")
        d = p.get("directo") or {}
        if d.get("activas"):
            st.caption(f"🚒 {d['activas']} actuación(es) activa(s) ahora")

# --- detalle horario
st.subheader("Detalle por hora")
sel = st.selectbox("Parque", [p["nombre"] for p in parques])
p = next(x for x in parques if x["nombre"] == sel)
h = pd.DataFrame([{
    "hora": x["hora"][11:16], "esperadas": x["lambda"], "normal": x["normal"], "×normal": x["ratio"],
    "nivel": f"{EMOJI[x['nivel']]} {x['nivel']}", "P(≥1)": f"{x['prob']:.0%}",
    "racha km/h": x["meteo"]["racha_kmh"], "lluvia mm/h": x["meteo"]["lluvia_1h"], "T ºC": x["meteo"]["temp"],
    "HR %": x["meteo"]["humedad"],
    "tipos más probables": ", ".join(FAMILIA_TXT.get(f["familia"], f["familia"]) for f in x["familias_top"]),
    "factores": "; ".join(x["factores"]),
} for x in p["horas"]])
st.line_chart(h.set_index("hora")[["esperadas", "normal"]])
st.dataframe(h, hide_index=True, width="stretch")

# --- en directo
st.subheader("Actuaciones activas ahora (bizkaia.eus)")
act = datos.get("activas_ahora") or []
if act:
    st.dataframe(pd.DataFrame(act), hide_index=True, width="stretch")
else:
    st.caption("Ninguna actuación activa en la última captura (o el recolector aún no tiene datos).")

with st.expander("Cómo se calcula"):
    st.markdown("""
- **Normal**: tasa histórica de salidas del parque para ese mes y franja horaria (Open Data Bizkaia 2023-hoy).
- **Esperadas**: la tasa normal multiplicada por factores de meteorología (Open-Meteo), calendario, tráfico
  (Open Data Euskadi) y eventos. Cuando hay datos horarios suficientes del recolector, un modelo LightGBM
  reentrenado cada noche sustituye a las reglas si demuestra predecir mejor.
- **Semáforo** según cuántas veces supera lo normal: 🟢 <1,5 · 🟡 1,5-2,5 · 🟠 2,5-4 · 🔴 ≥4.
- Herramienta experimental de apoyo. No sustituye a la información oficial del 112 ni de Bizkaia Prest.
""")
