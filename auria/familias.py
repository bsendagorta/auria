"""Agrupa las ~130 tipologías del SPEIS (que cambiaron en 2023) en familias estables.

Las reglas se evalúan en orden: la primera que encaja gana.
"""
import re
import unicodedata

NO_OPERATIVO = "NO_OPERATIVO"

# (familia, patrón regex sobre el texto normalizado en MAYÚSCULAS sin tildes)
REGLAS = [
    (NO_OPERATIVO, r"SIMULAC|SIMULACRO|MANIOBRA|RETEN|VISITA|PREVENCION|INVESTIGACION|ALERTA|"
                   r"ACTIVACION DEL|CODIGO 10|NIVEL DE RIESGO FORESTAL|ESPACIOS NATURALES|"
                   r"DANOS DE FAUNA|ASISTENCIAS MEDIO NATURAL|^NULL$|^$"),
    # antes que INCENDIO: "ACCESO A VIVIENDAS CERRADAS CON RIESGO DE INCENDIO" es un rescate
    ("RESCATE_SALVAMENTO", r"APERTURA|ACCESO A VIVIENDAS"),
    ("INCENDIO_INDUSTRIAL", r"INCENDIO INDUSTRIAL"),
    ("INCENDIO_FORESTAL_EXTERIOR", r"INCENDIO FORESTAL|INCENDIO RURAL|INCENDIOS RURALES|INCENDIO EXTERIOR|"
                                   r"MATORRAL|VEGETACION|PASTO|MONTE|ARBOLADO|BROZA|RASTROJO|HELECHO|ARGOMA|"
                                   r"QUEMA|HERBACEO|FORESTAL"),
    ("INCENDIO_URBANO", r"INCENDIO|INCENDIOS URBANOS"),
    ("TRAFICO", r"ACCIDENTE DE TRAFICO|GRAN ACCIDENTE|ACCIDENTE DE AVIACION"),
    ("GAS_MMPP", r"GAS|MMPP|MM\.PP|VERTIDO|EXPLOSIVO|OBJETOS ESPECIALES"),
    ("ABEJAS_AVISPAS", r"ABEJAS|AVISPAS"),
    ("METEO_ASISTENCIA", r"SANEADO|ARBOL|ACHIQUE|AUXILIARES|COLAPSO"),
    ("RESCATE_SALVAMENTO", r"APERTURA|ACCESO A VIVIENDAS|RESCATE|RECATE|SALVAMENTO|SUICIDIO|RAS\b|"
                           r"BREC|SOS|BOTON NARANJA|ASCENSOR|BUSQUEDA"),
    ("OTRAS_ASISTENCIAS", r"LIMPIEZA DE CALZADA|ASISTENCIA|SUMINISTRO DE AGUA|FAUNA|SERVICIOS"),
]
_COMPILADAS = [(f, re.compile(p)) for f, p in REGLAS]

FAMILIAS = list(dict.fromkeys(f for f, _ in REGLAS if f != NO_OPERATIVO)) + ["OTROS"]

ESTADOS_NO_OPERATIVOS = {"SIMULACIONES", "SERVICIOS DE COORDINACION"}


def normaliza(texto) -> str:
    if texto is None:
        return ""
    t = str(texto).strip().upper()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t)


def familia(tipo) -> str:
    t = normaliza(tipo)
    for fam, rx in _COMPILADAS:
        if rx.search(t):
            return fam
    return "OTROS"
