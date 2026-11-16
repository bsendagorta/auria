#!/bin/bash
# Añade al repositorio los datos generados por las tareas automáticas y los sube (con reintentos).
set -e
git config user.name  "auria-bot"
git config user.email "auria-bot@users.noreply.github.com"
git add datos/online datos/modelo prediccion informes datos/eventos.csv datos/festivos_locales.csv 2>/dev/null || true
if git diff --cached --quiet; then echo "Sin cambios"; exit 0; fi
git commit -q -m "${1:-datos: actualización automática}"
git config pull.rebase true
for i in 1 2 3 4 5; do
  git pull -q --rebase origin "${GITHUB_REF_NAME:-main}" && git push -q origin HEAD:"${GITHUB_REF_NAME:-main}" && exit 0
  sleep $((i * 5))
done
echo "No se pudo subir tras 5 intentos"; exit 1
