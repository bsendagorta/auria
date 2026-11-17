#!/bin/bash
# Añade al repositorio los datos generados por las tareas automáticas y los sube (con reintentos).
# Cada ruta se añade por separado: si una no existe, no impide subir las demás.
git config user.name  "auria-bot"
git config user.email "auria-bot@users.noreply.github.com"
# si quedó un rebase a medias de un intento anterior, se descarta
git rebase --abort 2>/dev/null || true
for r in datos/online datos/modelo datos/aforos prediccion informes datos/eventos.csv datos/festivos_locales.csv; do
  [ -e "$r" ] && git add "$r" 2>/dev/null
done
if git diff --cached --quiet; then echo "Sin cambios"; exit 0; fi
git commit -q -m "${1:-datos: actualización automática}"
RAMA="${GITHUB_REF_NAME:-main}"
for i in 1 2 3 4 5; do
  # en un conflicto gana la versión local (lo que acaba de calcular esta tarea)
  if git pull -q --rebase -X theirs origin "$RAMA"; then
    git push -q origin HEAD:"$RAMA" && exit 0
  else
    git rebase --abort 2>/dev/null || true
  fi
  sleep $((i * 5))
done
echo "No se pudo subir tras 5 intentos"; exit 1
