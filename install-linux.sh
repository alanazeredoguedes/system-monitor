#!/bin/bash
# Instala no GNOME: atalho global, início automático no login e entrada no menu de apps.
# Uso: ./install-linux.sh                       (atalho padrão: Ctrl+Page Up)
#      SHORTCUT='<Super>m' ./install-linux.sh
#      ./install-linux.sh /caminho/do/executavel  (padrão: dist/sysmon/sysmon, senão .venv + sysmon.py)
#      ./install-linux.sh --uninstall
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SHORTCUT="${SHORTCUT:-<Primary>Page_Up}"
KB_SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
KB_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/sysmon/"
KB_ITEM="$KB_SCHEMA.custom-keybinding:$KB_PATH"
AUTOSTART="$HOME/.config/autostart/sysmon.desktop"
LAUNCHER="$HOME/.local/share/applications/sysmon.desktop"

if [[ -n "${1:-}" && "$1" != "--uninstall" ]]; then
  EXE="$(readlink -f "$1")"
elif [[ -x "$DIR/dist/sysmon/sysmon" ]]; then
  EXE="$DIR/dist/sysmon/sysmon"
elif [[ -x "$DIR/.venv/bin/python" ]]; then
  EXE="$DIR/.venv/bin/python $DIR/sysmon.py"
else
  EXE="python3 $DIR/sysmon.py"
fi

current_list() { gsettings get "$KB_SCHEMA" custom-keybindings; }

if [[ "${1:-}" == "--uninstall" ]]; then
  python3 - "$KB_PATH" "$(current_list)" <<'PY' | xargs -0 gsettings set "$KB_SCHEMA" custom-keybindings
import ast, sys
path, raw = sys.argv[1], sys.argv[2].replace("@as ", "")
print(str([p for p in ast.literal_eval(raw) if p != path]), end="")
PY
  gsettings reset-recursively "$KB_ITEM" 2>/dev/null || true
  rm -f "$AUTOSTART" "$LAUNCHER"
  $EXE --quit 2>/dev/null || true
  echo "Monitor desinstalado."
  exit 0
fi

# 1) Atalho global (adiciona à lista sem apagar os atalhos que já existem)
NEW_LIST="$(python3 - "$KB_PATH" "$(current_list)" <<'PY'
import ast, sys
path, raw = sys.argv[1], sys.argv[2].replace("@as ", "")
items = ast.literal_eval(raw)
if path not in items:
    items.append(path)
print(str(items), end="")
PY
)"
gsettings set "$KB_SCHEMA" custom-keybindings "$NEW_LIST"
gsettings set "$KB_ITEM" name "Monitor do Sistema"
gsettings set "$KB_ITEM" command "$EXE --toggle"
gsettings set "$KB_ITEM" binding "$SHORTCUT"

# 2) Início automático (já abre o card visível)
mkdir -p "$(dirname "$AUTOSTART")" "$(dirname "$LAUNCHER")"
cat > "$AUTOSTART" <<DESK
[Desktop Entry]
Type=Application
Name=Monitor do Sistema
Exec=$EXE
Icon=utilities-system-monitor
X-GNOME-Autostart-enabled=true
NoDisplay=true
DESK

# 3) Entrada no menu de aplicativos
cat > "$LAUNCHER" <<DESK
[Desktop Entry]
Type=Application
Name=Monitor do Sistema (card)
Comment=CPU, GPU, memória e rede em um card flutuante
Exec=$EXE --toggle
Icon=utilities-system-monitor
Categories=System;Monitor;
DESK

echo "Instalado. Atalho: $SHORTCUT  ->  $EXE --toggle"
