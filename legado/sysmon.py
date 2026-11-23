#!/usr/bin/env python3
"""Monitor do sistema flutuante. Sem argumentos: abre (ou alterna, se já estiver rodando)."""
import os
import sys

# No Wayland, apps comuns não podem ficar "sempre no topo" nem escolher a própria posição.
# Rodando pelo XWayland (backend X11) essas duas coisas funcionam. Para forçar o nativo: SYSMON_NATIVE=1
if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("SYSMON_NATIVE"):
    os.environ["GDK_BACKEND"] = "x11"

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from sysmon.app import main  # noqa: E402

sys.exit(main())
