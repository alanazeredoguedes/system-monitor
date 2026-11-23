#!/bin/bash
# Instala o monitor: atalho global no GNOME, início automático no login e entrada no menu de apps.
# Uso: ./install.sh            (atalho padrão: Ctrl+Page Up)
#      SHORTCUT='<Super>m' ./install.sh
#      ./install.sh --uninstall
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SHORTCUT="${SHORTCUT:-<Primary>Page_Up}"
KB_SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
KB_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/sysmon/"
KB_ITEM="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$KB_PATH"
AUTOSTART="$HOME/.config/autostart/sysmon.desktop"
LAUNCHER="$HOME/.local/share/applications/sysmon.desktop"

current_list() { gsettings get "$KB_SCHEMA" custom-keybindings; }

if [[ "${1:-}" == "--uninstall" ]]; then
  python3 - "$KB_PATH" "$(current_list)" <<'EOF' | xargs -0 gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings
import ast, sys
path, raw = sys.argv[1], sys.argv[2].replace("@as ", "")
items = [p for p in ast.literal_eval(raw) if p != path]
print(str(items), end="")
EOF
  gsettings reset-recursively "$KB_ITEM" 2>/dev/null || true
  rm -f "$AUTOSTART" "$LAUNCHER"
  "$DIR/sysmon.py" --quit 2>/dev/null || true
  echo "Monitor desinstalado."
  exit 0
fi

python3 -c "import gi; gi.require_foreign('cairo')" 2>/dev/null || {
  echo "Falta o pacote python3-gi-cairo. Rode: sudo apt install python3-gi-cairo"; exit 1; }

# 1) Atalho global (adiciona à lista sem apagar os atalhos que já existem)
NEW_LIST="$(python3 - "$KB_PATH" "$(current_list)" <<'EOF'
import ast, sys
path, raw = sys.argv[1], sys.argv[2].replace("@as ", "")
items = ast.literal_eval(raw)
if path not in items:
    items.append(path)
print(str(items), end="")
EOF
)"
gsettings set "$KB_SCHEMA" custom-keybindings "$NEW_LIST"
gsettings set "$KB_ITEM" name "Monitor do Sistema"
gsettings set "$KB_ITEM" command "$DIR/sysmon-toggle"
gsettings set "$KB_ITEM" binding "$SHORTCUT"

# 2) Início automático (já abre o card visível)
mkdir -p "$(dirname "$AUTOSTART")" "$(dirname "$LAUNCHER")"
cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Monitor do Sistema
Exec=$DIR/sysmon.py
Icon=utilities-system-monitor
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF

# 3) Entrada no menu de aplicativos
cat > "$LAUNCHER" <<EOF
[Desktop Entry]
Type=Application
Name=Monitor do Sistema (card)
Comment=CPU, GPU, memória e rede em um card flutuante
Exec=$DIR/sysmon-toggle
Icon=utilities-system-monitor
Categories=System;Monitor;
EOF

echo "Instalado. Atalho: $SHORTCUT"
echo "Para iniciar agora em segundo plano: $DIR/sysmon.py --hidden &"
