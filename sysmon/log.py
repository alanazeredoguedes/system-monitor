"""Log simples em arquivo (o .exe do Windows não tem console, então erros ficariam invisíveis)."""

import os
import time

from . import paths


def log_file():
    return os.path.join(os.path.dirname(paths.config_file()), "sysmon.log")


def log(msg):
    try:
        os.makedirs(os.path.dirname(log_file()), exist_ok=True)
        with open(log_file(), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass
