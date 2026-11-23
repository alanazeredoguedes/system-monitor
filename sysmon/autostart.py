"""Início automático no login (Linux: ~/.config/autostart; Windows: chave Run do registro)."""

import os
import sys

NAME = "SystemMonitor"


def _command():
    """Comando que inicia o monitor (executável empacotado ou `python sysmon.py`)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sysmon.py"))
    py = sys.executable
    if sys.platform == "win32" and py.lower().endswith("python.exe"):
        pyw = py[:-10] + "pythonw.exe"  # sem janela de console
        py = pyw if os.path.exists(pyw) else py
    return [py, script]


def _quote(parts):
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


def is_enabled():
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, NAME)
            return True
        except OSError:
            return False
    return os.path.exists(os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                                       "autostart", "sysmon.desktop"))


def set_enabled(on):
    (enable if on else disable)()


def enable():
    cmd = _quote(_command())
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, cmd)
    else:
        d = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "autostart")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sysmon.desktop"), "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Monitor do Sistema\n"
                    f"Exec={cmd}\nIcon=utilities-system-monitor\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n")


def disable():
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, NAME)
        except OSError:
            pass
    else:
        path = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                            "autostart", "sysmon.desktop")
        try:
            os.remove(path)
        except OSError:
            pass
