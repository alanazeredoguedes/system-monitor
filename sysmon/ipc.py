"""Controle da instância em execução (alternar, mostrar, esconder, sair).

Usa só a biblioteca padrão e um socket TCP local (127.0.0.1), então funciona igual no Linux e no
Windows e é rápido: o atalho do Linux chama `sysmon --toggle` sem precisar carregar o Qt.
"""

import os
import socket

HOST = "127.0.0.1"
PORT = int(os.environ.get("SYSMON_PORT", "47329"))
COMMANDS = ("toggle", "show", "hide", "advanced", "quit")


def send(cmd, timeout=0.4):
    """Envia um comando à instância em execução. True se havia alguém ouvindo."""
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout) as s:
            s.sendall(cmd.encode() + b"\n")
        return True
    except OSError:
        return False
