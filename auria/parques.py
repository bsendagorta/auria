"""Los 8 parques del SPEIS foral y los municipios de su zona (fuente: bizkaia.eus/es/bomberos, nov-2026).

Bilbao (48020) tiene servicio propio: queda fuera.
Ziortza-Bolibar no aparece en ninguna lista oficial; se asigna a Markina por cercanía (supuesto).
"""
from .familias import normaliza

PARQUES = {
    "URIOSTE": {"nombre": "Urioste (Ortuella)", "lat": 43.3075, "lon": -3.0510,
                "ine": ["48013", "48078", "48082", "48084", "48080", "48002", "48083", "48071", "48912", "48913"]},
    "ARTAZA": {"nombre": "Artaza (Leioa)", "lat": 43.3350, "lon": -2.9870,
               "ine": ["48044", "48054", "48902", "48085", "48016", "48043", "48077", "48089", "48014"]},
    "DERIO": {"nombre": "Derio", "lat": 43.2930, "lon": -2.8840,
              "ine": ["48069", "48901", "48904", "48905", "48903", "48081", "48012", "48040", "48038",
                      "48053", "48056", "48061", "48010", "48064", "48035"]},
    "BASAURI": {"nombre": "Basauri", "lat": 43.2370, "lon": -2.8850,
                "ine": ["48015", "48036", "48916", "48011", "48029", "48065", "48074", "48094", "48055",
                        "48075", "48097", "48052", "48024", "48026", "48093", "48025", "48092", "48009",
                        "48023", "48006", "48088", "48005"]},
    "IURRETA": {"nombre": "Iurreta", "lat": 43.1760, "lon": -2.6340,
                "ine": ["48027", "48034", "48003", "48032", "48001", "48019", "48910", "48095", "48091",
                        "48058", "48072", "48059", "48050", "48039"]},
    "ARRATZU": {"nombre": "Arratzu", "lat": 43.3090, "lon": -2.6400,
                "ine": ["48017", "48046", "48068", "48021", "48067", "48906", "48041", "48028", "48048",
                        "48079", "48031", "48911", "48066", "48907", "48914", "48062", "48076", "48033",
                        "48908", "48909"]},
    "MARKINA": {"nombre": "Markina-Xemein", "lat": 43.2680, "lon": -2.4970,
                "ine": ["48073", "48057", "48060", "48018", "48030", "48070", "48049", "48007", "48004",
                        "48063", "48047", "48915"]},
    "ZALLA": {"nombre": "Zalla", "lat": 43.2130, "lon": -3.1370,
              "ine": ["48096", "48090", "48045", "48022", "48086", "48042", "48037", "48008", "48087", "48051"]},
}
SIN_PARQUE = "SIN_PARQUE"

# Nombres de municipio tal y como los escribe la Diputación (Open Data y web en directo)
NOMBRES = {
    "48001": "ABADIÑO", "48002": "ABANTO Y CIERVANA-ABANTO ZIERBENA", "48003": "AMOREBIETA-ETXANO",
    "48004": "AMOROTO", "48005": "ARAKALDO", "48006": "ARANTZAZU", "48007": "MUNITIBAR-ARBATZEGI GERRIKAITZ",
    "48008": "ARTZENTALES", "48009": "ARRANKUDIAGA-ZOLLO", "48010": "ARRIETA", "48011": "ARRIGORRIAGA",
    "48012": "BAKIO", "48013": "BARAKALDO", "48014": "BARRIKA", "48015": "BASAURI", "48016": "BERANGO",
    "48017": "BERMEO", "48018": "BERRIATUA", "48019": "BERRIZ", "48020": "BILBAO", "48021": "BUSTURIA",
    "48022": "KARRANTZA HARANA/VALLE DE CARRANZA", "48023": "ARTEA", "48024": "ZEANURI", "48025": "ZEBERIO",
    "48026": "DIMA", "48027": "DURANGO", "48028": "EA", "48029": "ETXEBARRI", "48030": "ETXEBARRIA",
    "48031": "ELANTXOBE", "48032": "ELORRIO", "48033": "EREÑO", "48034": "ERMUA", "48035": "FRUIZ",
    "48036": "GALDAKAO", "48037": "GALDAMES", "48038": "GAMIZ-FIKA", "48039": "GARAI", "48040": "GATIKA",
    "48041": "GAUTEGIZ ARTEAGA", "48042": "GORDEXOLA", "48043": "GORLIZ", "48044": "GETXO", "48045": "GUEÑES",
    "48046": "GERNIKA-LUMO", "48047": "GIZABURUAGA", "48048": "IBARRANGELU", "48049": "ISPASTER",
    "48050": "IZURTZA", "48051": "LANESTOSA", "48052": "LARRABETZU", "48053": "LAUKIZ", "48054": "LEIOA",
    "48055": "LEMOA", "48056": "LEMOIZ", "48057": "LEKEITIO", "48058": "MALLABIA", "48059": "MAÑARIA",
    "48060": "MARKINA-XEMEIN", "48061": "MARURI-JATABE", "48062": "MENDATA", "48063": "MENDEXA",
    "48064": "MEÑAKA", "48065": "UGAO-MIRABALLES", "48066": "MORGA", "48067": "MUXIKA", "48068": "MUNDAKA",
    "48069": "MUNGIA", "48070": "AULESTI", "48071": "MUSKIZ", "48072": "OTXANDIO", "48073": "ONDARROA",
    "48074": "URDUÑA/ORDUÑA", "48075": "OROZKO", "48076": "SUKARRIETA", "48077": "PLENTZIA",
    "48078": "PORTUGALETE", "48079": "ERRIGOITI", "48080": "VALLE DE TRAPAGA-TRAPAGARAN", "48081": "LEZAMA",
    "48082": "SANTURTZI", "48083": "ORTUELLA", "48084": "SESTAO", "48085": "SOPELA", "48086": "SOPUERTA",
    "48087": "TRUCIOS-TURTZIOZ", "48088": "UBIDE", "48089": "URDULIZ", "48090": "BALMASEDA",
    "48091": "ATXONDO", "48092": "BEDIA", "48093": "AREATZA", "48094": "IGORRE", "48095": "ZALDIBAR",
    "48096": "ZALLA", "48097": "ZARATAMO", "48901": "DERIO", "48902": "ERANDIO", "48903": "LOIU",
    "48904": "SONDIKA", "48905": "ZAMUDIO", "48906": "FORUA", "48907": "KORTEZUBI", "48908": "MURUETA",
    "48909": "NABARNIZ", "48910": "IURRETA", "48911": "AJANGIZ", "48912": "ALONSOTEGI", "48913": "ZIERBENA",
    "48914": "ARRATZU", "48915": "ZIORTZA-BOLIBAR", "48916": "USANSOLO",
}

INE_A_PARQUE = {ine: p for p, d in PARQUES.items() for ine in d["ine"]}


def _variantes(nombre):
    """'KARRANTZA HARANA/VALLE DE CARRANZA' -> {completo, cada parte}; 'ABANTO Y CIERVANA-ABANTO ZIERBENA' -> partes."""
    n = normaliza(nombre)
    out = {n}
    for sep in ("/", "-", " Y "):
        for parte in n.split(sep):
            if len(parte.strip()) > 3:
                out.add(parte.strip())
    return out


NOMBRE_A_INE = {}
for _ine, _nom in NOMBRES.items():
    for _v in _variantes(_nom):
        NOMBRE_A_INE.setdefault(_v, _ine)
# Grafías alternativas habituales
for _alias, _ine in {"TRAPAGARAN": "48080", "VALLE DE TRAPAGA": "48080", "GUENES": "48045", "GERNIKA": "48046",
                     "MARKINA": "48060", "AMOREBIETA": "48003", "ORDUÑA": "48074", "ORDUNA": "48074",
                     "CARRANZA": "48022", "ARCENTALES": "48008", "IBARRENGELU": "48048", "IZURZA": "48050",
                     "MUNITIBAR": "48007", "ABANTO": "48002", "ZIERBENA": "48913"}.items():
    NOMBRE_A_INE[normaliza(_alias)] = _ine


def parque_de_ine(ine) -> str:
    return INE_A_PARQUE.get(str(ine or "").strip(), SIN_PARQUE)


def ine_de_nombre(nombre) -> str:
    n = normaliza(nombre)
    if n in NOMBRE_A_INE:
        return NOMBRE_A_INE[n]
    for v in _variantes(n):
        if v in NOMBRE_A_INE:
            return NOMBRE_A_INE[v]
    return ""


def parque_de_nombre(nombre) -> str:
    return parque_de_ine(ine_de_nombre(nombre))


def parque_mas_cercano(lat, lon) -> str:
    return min(PARQUES, key=lambda p: (PARQUES[p]["lat"] - lat) ** 2 + (PARQUES[p]["lon"] - lon) ** 2)
