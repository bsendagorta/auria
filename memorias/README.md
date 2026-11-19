# Memorias del SPEIS de Bizkaia (2000-2025)

Informes anuales de actividad del Servicio de Prevención, Extinción de Incendios y Salvamento (SPEIS)
de la Diputación Foral de Bizkaia, publicados por la propia Diputación.

Contienen **estadísticas agregadas** (totales por año, tipo, parque, mes; y gráficos por hora y día de la
semana). No son registros intervención a intervención; esos están en Open Data Bizkaia (datos/historico).

## Qué se ha extraído
- `../datos/memorias/series_anual.csv` — total de salidas por año y, en los años recientes, su reparto en
  incendios / salvamentos / asistencias técnicas. Fuente indicada por fila.
- `../datos/memorias/dia_semana_2022.csv` — reparto por día de la semana (único año reconstruible de forma
  fiable; sale prácticamente plano).

## Qué NO se ha podido extraer de forma automática
El reparto por **hora del día** y por **día de la semana** aparece como gráficos (barras y relojes) dentro
de los PDF, no como tablas de números, así que no se puede leer con fiabilidad. Los años 2000-2018 son
además documentos escaneados o de gráficos, por lo que sus totales no se extraen con garantías.

## Ficheros
Un PDF por año (`memoria_AAAA.pdf`). 2006, 2008 y 2009 tienen dos versiones (actividades y estadística).
2016-2018 son "Evaluación del Plan Foral de Emergencias" (`plan-foral_AAAA.pdf`), un documento distinto.
