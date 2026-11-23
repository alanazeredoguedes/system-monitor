"""Linha de comando. Fala com a instância já aberta antes de carregar o Qt (resposta instantânea)."""

import argparse
import os
import sys

from . import ipc


def _parse(argv):
    ap = argparse.ArgumentParser(prog="sysmon", description="Monitor do sistema flutuante.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--toggle", action="store_true", help="mostra/esconde o card (padrão se já estiver rodando)")
    g.add_argument("--show", action="store_true", help="mostra o card")
    g.add_argument("--hide", action="store_true", help="esconde o card")
    g.add_argument("--advanced", action="store_true", help="alterna o modo avançado")
    g.add_argument("--quit", action="store_true", help="encerra o monitor")
    g.add_argument("--autostart", choices=("on", "off"), help="liga/desliga o início automático no login")
    ap.add_argument("--hidden", action="store_true", help="inicia escondido")
    ap.add_argument("--hotkey", metavar="ATALHO", help="Windows: atalho global, ex.: ctrl+alt+m")
    return ap.parse_args(argv)


def main(argv=None):
    args = _parse(sys.argv[1:] if argv is None else argv)

    if args.autostart:
        from . import autostart
        (autostart.enable if args.autostart == "on" else autostart.disable)()
        print("Início automático", "ligado." if args.autostart == "on" else "desligado.")
        return 0

    cmd = next((c for c in ipc.COMMANDS if getattr(args, c)), None)
    if cmd == "quit":
        ipc.send("quit")
        return 0
    if ipc.send(cmd or ("noop" if args.hidden else "toggle")):
        return 0  # já havia uma instância; ela tratou o comando
    if cmd == "hide":
        return 0

    # Nova instância. No Wayland o Qt nativo não permite "sempre no topo" nem posicionar a janela;
    # pelo XWayland (xcb) as duas coisas funcionam. Para forçar o nativo: SYSMON_NATIVE=1
    if (sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY")
            and not os.environ.get("SYSMON_NATIVE")):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("QT_FONT_DPI", "96")  # tamanhos de fonte em px reais, iguais nos dois sistemas

    from .app import run
    return run(start_hidden=args.hidden or cmd in ("hide", "advanced"), first_cmd=cmd, hotkey=args.hotkey)
