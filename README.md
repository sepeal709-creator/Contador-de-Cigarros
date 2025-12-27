# Control de Cigarros — APK rápido

Este proyecto es una app Kivy para registrar cigarros fumados, antojos y ver estadísticas básicas. Sigue los pasos para generar un APK que puedas instalar en Android sin depender de la red durante el uso.

## Requisitos
- Linux/macOS con Python 3.10+.
- [Buildozer](https://github.com/kivy/buildozer) instalado (`pip install buildozer`).
- Dependencias de Android SDK/NDK y Java JDK (Buildozer las descarga al primer build).
- `adb` si quieres instalar el APK por USB/Wi‑Fi.

## Construir el APK
1. Clona el repo y entra a la carpeta:
   ```bash
   git clone <este-repo>
   cd Contador-de-Cigarros
   ```
2. Ejecuta el script de ayuda (usa Buildozer internamente):
   ```bash
   ./scripts/build_apk.sh
   ```
   - Esto genera un APK *debug* en `./bin/*-debug.apk`.
   - Si quieres un APK *release* (para publicar), firma el APK y ejecuta:
     ```bash
     buildozer android release
     ```
3. Instala el APK en un dispositivo con depuración USB/ADB habilitado:
   ```bash
   adb install -r bin/*-debug.apk
   ```

## Notas útiles
- El archivo `buildozer.spec` ya está configurado con:
  - `requirements = python3,kivy`
  - API mínima 26 (Android 8) y API objetivo 33.
- Si Buildozer pide aceptar licencias de Android, responde `y`.
- Para limpiar builds previos: `buildozer android clean`.
- La app guarda la base de datos localmente en `control_de_cigarros.db`; no requiere Internet.
