"""Multiplicadores de riesgo por familia (versión inicial basada en conocimiento operativo).

Se aplican sobre la tasa base histórica del parque para esa hora. Son PROVISIONALES: cuando el
reentrenamiento nocturno tenga datos horarios suficientes, el modelo LightGBM aprende los pesos reales
y estas reglas solo se usan para explicar los factores.

Cada regla: (condición sobre las variables de la hora, {familia: factor}, texto para el panel)
"""

REGLAS = [
    # --- viento
    (lambda v: v["racha_kmh"] >= 100, {"METEO_ASISTENCIA": 8.0, "OTRAS_ASISTENCIAS": 2.0, "TRAFICO": 1.3},
     "Rachas muy fuertes (≥100 km/h)"),
    (lambda v: 80 <= v["racha_kmh"] < 100, {"METEO_ASISTENCIA": 5.0, "OTRAS_ASISTENCIAS": 1.6, "TRAFICO": 1.2},
     "Rachas fuertes (80-100 km/h)"),
    (lambda v: 60 <= v["racha_kmh"] < 80, {"METEO_ASISTENCIA": 2.5, "OTRAS_ASISTENCIAS": 1.3},
     "Rachas de 60-80 km/h"),
    # --- lluvia
    (lambda v: v["lluvia_1h"] >= 10, {"METEO_ASISTENCIA": 3.0, "TRAFICO": 1.4}, "Lluvia intensa (≥10 mm/h)"),
    (lambda v: 3 <= v["lluvia_1h"] < 10, {"METEO_ASISTENCIA": 1.5, "TRAFICO": 1.2}, "Lluvia moderada"),
    (lambda v: v["lluvia_12h"] >= 40, {"METEO_ASISTENCIA": 2.5}, "Lluvia acumulada alta (≥40 mm en 12 h)"),
    (lambda v: v["dias_sin_lluvia"] >= 5 and v["lluvia_1h"] >= 0.5, {"TRAFICO": 1.5},
     "Primeras lluvias tras días secos (asfalto deslizante)"),
    # --- incendio forestal
    (lambda v: v["viento_sur"] and v["humedad"] < 40 and v["temp"] > 18,
     {"INCENDIO_FORESTAL_EXTERIOR": 4.0}, "Viento sur seco y cálido (riesgo forestal)"),
    (lambda v: v["humedad"] < 45 and v["dias_sin_lluvia"] >= 7 and not v["viento_sur"],
     {"INCENDIO_FORESTAL_EXTERIOR": 2.0}, "Vegetación seca (≥7 días sin lluvia)"),
    (lambda v: v["temp"] >= 30, {"INCENDIO_FORESTAL_EXTERIOR": 1.5, "RESCATE_SALVAMENTO": 1.1}, "Calor (≥30 °C)"),
    # --- frío
    (lambda v: v["temp"] <= 3, {"INCENDIO_URBANO": 1.3}, "Frío (calefacciones, chimeneas)"),
    (lambda v: v["temp"] <= 1 and (v["lluvia_1h"] > 0 or v["nieve"] > 0), {"TRAFICO": 1.6},
     "Posible hielo o nieve en calzada"),
    # --- calendario y movilidad
    (lambda v: v["noche_finde"], {"TRAFICO": 1.3}, "Noche de fin de semana"),
    (lambda v: v["operacion_trafico"], {"TRAFICO": 1.3}, "Operación salida/retorno"),
    (lambda v: v["festivo"] and not v["noche_finde"], {"TRAFICO": 1.1}, "Festivo"),
    # --- tráfico en tiempo real (solo para la hora en curso y la siguiente)
    (lambda v: v.get("trafico_accidentes", 0) >= 1, {"TRAFICO": 1.3}, "Accidentes de tráfico activos en la zona"),
    (lambda v: v.get("trafico_seguridad", 0) >= 2, {"TRAFICO": 1.2, "OTRAS_ASISTENCIAS": 1.3},
     "Incidencias de seguridad vial (objetos, desprendimientos)"),
    # --- eventos
    (lambda v: v.get("evento_nivel", 0) == 2, {"TRAFICO": 1.35, "RESCATE_SALVAMENTO": 1.2}, "Evento masivo"),
    (lambda v: v.get("evento_nivel", 0) == 1, {"TRAFICO": 1.15}, "Evento"),
]


# reglas meteorológicas escritas a mano: se desactivan para los tipos de siniestro cuyo efecto ya está
# medido con datos reales (auria.efectos_meteo)
METEO = {"Rachas muy fuertes (≥100 km/h)", "Rachas fuertes (80-100 km/h)", "Rachas de 60-80 km/h",
         "Lluvia intensa (≥10 mm/h)", "Lluvia moderada", "Lluvia acumulada alta (≥40 mm en 12 h)",
         "Viento sur seco y cálido (riesgo forestal)", "Vegetación seca (≥7 días sin lluvia)", "Calor (≥30 °C)",
         "Frío (calefacciones, chimeneas)", "Primeras lluvias tras días secos (asfalto deslizante)",
         "Posible hielo o nieve en calzada"}
LLUVIA_TRAFICO = {"Lluvia intensa (≥10 mm/h)", "Lluvia moderada"}   # sustituidas por el riesgo medido (DGT)


def aplicar(v: dict, sin_meteo=frozenset()):
    """Devuelve ({familia: multiplicador}, [textos de los factores activos]).
    sin_meteo: tipos de siniestro con efecto meteorológico medido (no se les aplican las reglas a mano)."""
    from . import accidentes_hora, riesgo_trafico
    mult, textos = {}, []
    # 1.º efecto medido HORA A HORA (incidencias con hora exacta); si no hay modelo validado, el de la DGT
    hora = accidentes_hora.factor_hora(v)
    if hora is not None:
        sin_meteo = set(sin_meteo) | {"TRAFICO"}
    obst = accidentes_hora.factor_hora(v, "obstaculo")
    if obst is not None:
        sin_meteo = set(sin_meteo) | {"METEO_ASISTENCIA"}
    rr = None if hora is not None else riesgo_trafico.rr_lluvia(v.get("lluvia_1h", 0) or 0)
    for cond, efectos, texto in REGLAS:
        try:
            activa = cond(v)
        except (KeyError, TypeError):
            activa = False
        if activa:
            textos.append(texto)
            for f, k in efectos.items():
                if f in sin_meteo and texto in METEO:
                    continue
                if rr is not None and f == "TRAFICO" and texto in LLUVIA_TRAFICO:
                    continue
                mult[f] = mult.get(f, 1.0) * k
    if hora is not None:
        mult["TRAFICO"] = mult.get("TRAFICO", 1.0) * hora[0]
        textos += hora[1]
    if obst is not None:
        mult["METEO_ASISTENCIA"] = mult.get("METEO_ASISTENCIA", 1.0) * obst[0]
        textos += obst[1]
    if rr is not None:            # riesgo de accidente con lluvia medido con datos reales
        k = rr if rr != 1.0 else riesgo_trafico.factor_seco()
        mult["TRAFICO"] = mult.get("TRAFICO", 1.0) * k
        if rr > 1.05:
            textos.append(f"Lluvia: riesgo de accidente ×{rr:.1f} (datos DGT)")
    return mult, textos
