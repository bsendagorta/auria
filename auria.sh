#!/bin/bash
# Atajos de AURIA.  Uso: ./auria.sh <orden>
#   historico   descarga y limpia el histórico de Open Data Bizkaia (2021-hoy)
#   meteo       descarga la meteorología diaria por municipio (Open-Meteo)
#   modelo      entrena y valida los modelos (nivel Bizkaia y municipio)
#   todo        las tres anteriores en orden
#   captura     hace una captura de las salidas en directo ahora
#   resumen     resume lo capturado en directo (series diarias/horarias)
#   estado      ¿está funcionando el recolector?
#   prevision   predicción de las próximas 6 horas por parque (prediccion/ultima.json)
#   entrenar    reentrena el modelo horario (si hay datos suficientes)
#   panel       abre el panel web en el navegador (Streamlit)
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python
[ -x "$PY" ] || { echo "Primero: bash instalar.sh"; exit 1; }

case "$1" in
  historico) $PY -m auria.historico ;;
  meteo)     $PY -m auria.meteo ;;
  modelo)    $PY -m auria.modelo --nivel municipio && $PY -m auria.modelo --nivel bizkaia ;;
  todo)      $PY -m auria.historico && $PY -m auria.meteo \
             && $PY -m auria.modelo --nivel municipio && $PY -m auria.modelo --nivel bizkaia \
             && $PY -m auria.prevision ;;
  captura)   AURIA_ORIGEN=mac $PY -m auria.recolector_online ;;
  resumen)   $PY -m auria.resumen_online ;;
  prevision) $PY -m auria.prevision ;;
  entrenar)  $PY -m auria.horario ;;
  panel)     .venv/bin/streamlit run streamlit_app.py ;;
  estado)    launchctl print "gui/$(id -u)/eus.auria.recolector" 2>/dev/null | grep -E "state|last exit" || echo "Recolector no instalado"
             echo "--- últimas líneas del log ---"; tail -n 5 datos/online/recolector.log 2>/dev/null || true ;;
  *)         sed -n '2,13p' "$0" ;;
esac
