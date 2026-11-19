"""Contexto histórico a partir de las memorias anuales del SPEIS (2000-2025).

Las memorias de la Diputación (carpeta memorias/, PDF) son informes anuales con ESTADÍSTICAS AGREGADAS,
no registros intervención a intervención. Por eso:
  * Lo que se extrae de forma fiable (del resumen de cada memoria) es el total de salidas por año y, en los
    años recientes, su reparto en incendios / salvamentos / asistencias técnicas → datos/memorias/series_anual.csv
  * El reparto por HORA del día y por DÍA de la semana aparece solo como gráficos de barras/reloj dentro de los
    PDF, no como números, así que no se puede leer de forma automática y fiable. La única serie por día de la
    semana que se ha podido reconstruir (2022) es prácticamente plana (datos/memorias/dia_semana_2022.csv),
    lo que coincide con lo que dicen las propias memorias: el día de la semana apenas influye.

Uso en AURIA:
  - serie_anual(): tendencia de largo plazo para el panel (contexto, no entra en el modelo horario).
  - No se usa como variable del modelo: son agregados anuales y, en los años antiguos, con otra clasificación
    de tipos y otros parques, así que mezclarlos con los datos recientes por mes/franja falsearía las tasas.
"""
import pandas as pd

from . import config

DIR = config.DATOS / "memorias"


def serie_anual() -> pd.DataFrame:
    p = DIR / "series_anual.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def dia_semana() -> pd.DataFrame:
    p = DIR / "dia_semana_2022.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p)
    d["relativo"] = (d["salidas"] / d["salidas"].mean()).round(3)
    return d


if __name__ == "__main__":
    print(serie_anual().to_string(index=False))
    print()
    print(dia_semana().to_string(index=False))
