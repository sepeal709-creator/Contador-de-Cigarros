#!/usr/bin/env bash
set -euo pipefail

# Construye un APK de Kivy usando Buildozer en modo debug.
# Requisitos previos: Python 3, buildozer instalado y las dependencias de Android SDK/NDK.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v buildozer >/dev/null 2>&1; then
  echo "Error: buildozer no está instalado. Instálalo con 'pip install buildozer'." >&2
  exit 1
fi

echo "Construyendo APK (debug)..."
buildozer android debug

APK_PATH="$(find "$ROOT_DIR/bin" -maxdepth 2 -type f -name "*-debug.apk" | head -n 1 || true)"

if [[ -z "$APK_PATH" ]]; then
  echo "No se encontró el APK en ./bin. Revisa la salida de buildozer para más detalles." >&2
  exit 1
fi

echo "APK generado: $APK_PATH"
echo "Para instalarlo en un dispositivo con ADB activado: adb install -r \"$APK_PATH\""
