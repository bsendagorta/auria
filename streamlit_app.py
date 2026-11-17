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

st.set_page_config(page_title="AURIA · Emergencias Bizkaia", page_icon="🚒", layout="wide")

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


def _bajar(ruta, cada):
    """Contenido de un fichero del repo: GitHub (al día) y, si falla, la copia local."""
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
    except Exception:
        p = RAIZ / ruta
        return (p.read_bytes(), "copia local") if p.exists() else (None, None)


@st.cache_data(ttl=120, show_spinner=False)
def leer_json(ruta, cada=120):
    b, origen = _bajar(ruta, cada)
    return (json.loads(b), origen) if b else (None, None)


@st.cache_data(ttl=900, show_spinner=False)
def leer_csv(ruta):
    b, _ = _bajar(ruta, 900)
    return pd.read_csv(io.BytesIO(b), dtype={"cod_ine": str}) if b else None


@st.cache_data(ttl=50, show_spinner=False)
def leer_directo():
    b, _ = _bajar("prediccion/directo.json", 50)
    if b:
        return json.loads(b), None
    try:   # en local se puede leer la web directamente
        from auria import directo, recolector_online
        import auria.config as cfg
        html = requests.get(cfg.URL_SALIDAS_ONLINE, timeout=6, headers={"User-Agent": cfg.USER_AGENT}).text
        return directo.enriquecer(recolector_online.parsear(html)), None
    except Exception as e:
        return None, str(e)


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
    if retraso > 10:
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
        dp = pd.DataFrame([{"lat": p["lat"], "lon": p["lon"], "color": NIVEL_RGB[p["nivel"]] + [170],
                            "radio": 2200 + 2600 * p["salidas_esperadas_6h"],
                            "txt": f"{p['nombre']}\n{EMOJI[p['nivel']]} {p['nivel']} · ×{p['ratio_max']} lo normal\n"
                                   f"esperadas 6 h: {p['salidas_esperadas_6h']}"} for p in parques])
        capas = [pdk.Layer("ScatterplotLayer", dp, get_position="[lon, lat]", get_fill_color="color",
                           get_radius="radio", pickable=True, stroked=True, get_line_color=[255, 255, 255],
                           line_width_min_pixels=2)]
        if pts:
            capas.append(pdk.Layer("ScatterplotLayer", pd.DataFrame(pts), get_position="[lon, lat]",
                                   get_fill_color=[20, 20, 20, 230], get_line_color=[255, 255, 255],
                                   stroked=True, line_width_min_pixels=2, get_radius=900,
                                   radius_min_pixels=6, pickable=True))
        st.pydeck_chart(pdk.Deck(map_style=None, tooltip={"text": "{txt}"}, layers=capas,
                                 initial_view_state=pdk.ViewState(latitude=43.24, longitude=-2.85, zoom=8.7)),
                        height=430)
        st.caption("Círculos de color: riesgo de cada parque (semáforo, tamaño = intervenciones esperadas). "
                   "Puntos negros: actuaciones en curso (situadas en su municipio).")
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
        cols[i % 4].markdown(f"""
<div class="parque" style="--c:{NIVEL_HEX[p['nivel']]}">
 <div class="t">{EMOJI[p['nivel']]} {p['nombre']}</div>
 <div><span class="r">×{p['ratio_max']}</span> <span class="s">lo normal · pico {p['hora_pico'][11:16]}</span></div>
 <div class="s">Esperadas <b>{p['salidas_esperadas_6h']}</b> (normal {p['normal_6h']}) · P(≥1) <b>{p['prob_6h']:.0%}</b></div>
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

    sel = st.selectbox("Detalle de un parque", [p["nombre"] for p in parques])
    p = next(x for x in parques if x["nombre"] == sel)
    st.dataframe(pd.DataFrame([{
        "hora": x["hora"][11:16], "nivel": f"{EMOJI[x['nivel']]} ×{x['ratio']}", "esperadas": x["lambda"],
        "normal": x["normal"], "P(≥1)": x["prob"],
        "tipos más probables": ", ".join(FAMILIA_TXT.get(f["familia"], f["familia"]) for f in x["familias_top"]),
        "racha km/h": x["meteo"]["racha_kmh"], "lluvia mm/h": x["meteo"]["lluvia_1h"], "T ºC": x["meteo"]["temp"],
        "factores": "; ".join(x["factores"]),
    } for x in p["horas"]]), hide_index=True, width="stretch",
        column_config={"P(≥1)": st.column_config.ProgressColumn(format="percent", min_value=0.0, max_value=1.0)})


# ------------------------------------------------------------------ CARRETERAS
with t_carr:
    tramos = [{"carretera": c["carretera"], "tramo": f"km {c['km_ini']}-{c['km_fin']}",
               "parque": p["nombre"].split(" (")[0], "P(≥1 accidente con víctimas, 6 h)": c["prob"],
               "accidentes/año": c["accidentes_anio"], "% graves": c["pct_graves"],
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
    st.caption("Fuente: microdatos de accidentes con víctimas de la DGT (vías interurbanas, sin Bilbao), "
               "calibrados con las salidas reales de tráfico de SPEIS. Falta la intensidad de tráfico de cada "
               "tramo (aforos): es la siguiente fuente a incorporar.")


# ------------------------------------------------------------------ APRENDIZAJE
with t_apr:
    ev, _ = leer_json("datos/modelo/evaluacion.json")
    mh, _ = leer_json("datos/modelo/modelo_horario.json")
    mm, _ = leer_json("datos/modelo/modelo_mensual_municipio.json")
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
