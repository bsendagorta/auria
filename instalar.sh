#!/bin/bash
# Instala AURIA en este Mac: entorno Python + recolector automático cada 5 minutos.
# Uso:  bash instalar.sh            (instala todo)
#       bash instalar.sh --sin-recolector
set -e
cd "$(dirname "$0")"
RAIZ="$(pwd)"

if ! command -v python3 >/dev/null; then
  echo "Falta python3. Instálalo con:  xcode-select --install   (o desde python.org)"; exit 1
fi

echo "==> Creando entorno virtual en .venv"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "    OK"

if [ "$1" != "--sin-recolector" ]; then
  PLIST="$HOME/Library/LaunchAgents/eus.auria.recolector.plist"
  mkdir -p "$HOME/Library/LaunchAgents" "$RAIZ/datos/online"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>eus.auria.recolector</string>
  <key>ProgramArguments</key><array>
    <string>$RAIZ/.venv/bin/python</string><string>-m</string><string>auria.recolector_online</string>
  </array>
  <key>WorkingDirectory</key><string>$RAIZ</string>
  <key>EnvironmentVariables</key><dict><key>AURIA_ORIGEN</key><string>mac</string></dict>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$RAIZ/datos/online/recolector.log</string>
  <key>StandardErrorPath</key><string>$RAIZ/datos/online/recolector.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/eus.auria.recolector" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "==> Recolector activado (cada 5 min). Log: datos/online/recolector.log"
  echo "    Para pararlo:  launchctl bootout gui/\$(id -u)/eus.auria.recolector"
fi

echo
echo "Siguiente paso:  ./auria.sh todo"
