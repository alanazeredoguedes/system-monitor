#!/bin/bash
# Gera o executável do Linux em dist/sysmon/ (e dist/sysmon-linux-x86_64.tar.gz).
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-.venv/bin/python}"
[[ -x "$PY" ]] || PY=python3
"$PY" -m PyInstaller --noconfirm --clean sysmon.spec
tar -C dist -czf "dist/sysmon-linux-$(uname -m).tar.gz" sysmon
echo "Pronto: dist/sysmon/sysmon  (pacote: dist/sysmon-linux-$(uname -m).tar.gz)"
