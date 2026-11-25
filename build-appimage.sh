#!/bin/bash
# Gera dist/sysmon-x86_64.AppImage a partir de dist/sysmon (rode ./build.sh antes).
set -euo pipefail
cd "$(dirname "$0")"

ARCH="${ARCH:-$(uname -m)}"
TOOL_VERSION="1.9.1"
TOOL="build/appimagetool-$ARCH.AppImage"
[[ -x dist/sysmon/sysmon ]] || { echo "Falta dist/sysmon. Rode ./build.sh primeiro."; exit 1; }

mkdir -p build
if [[ ! -x "$TOOL" ]]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/$TOOL_VERSION/appimagetool-$ARCH.AppImage"
  chmod +x "$TOOL"
fi

APPDIR="build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a dist/sysmon "$APPDIR/usr/lib/sysmon"
cp packaging/sysmon.desktop "$APPDIR/sysmon.desktop"
cp packaging/sysmon.png "$APPDIR/sysmon.png"
cp packaging/sysmon.png "$APPDIR/.DirIcon"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/sysmon/sysmon" "$@"
RUN
chmod +x "$APPDIR/AppRun"

# APPIMAGE_EXTRACT_AND_RUN: a própria ferramenta roda sem precisar de FUSE (útil no CI)
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "dist/sysmon-$ARCH.AppImage"
echo "Pronto: dist/sysmon-$ARCH.AppImage"
