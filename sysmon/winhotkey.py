"""Atalho global no Windows (RegisterHotKey), em uma thread própria com laço de mensagens.

Não depende do filtro de eventos do Qt: a thread registra o atalho, espera o WM_HOTKEY com
GetMessageW e avisa a interface por um sinal do Qt (entregue na thread principal).
"""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QThread, Signal

from .log import log

WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID = 0x5359  # "SY"
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_MODS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT,
         "win": MOD_WIN, "super": MOD_WIN}
_NAMED = {"pageup": 0x21, "pgup": 0x21, "page_up": 0x21, "pagedown": 0x22, "pgdn": 0x22, "page_down": 0x22,
          "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
          "insert": 0x2D, "delete": 0x2E, "space": 0x20, "tab": 0x09, "enter": 0x0D, "esc": 0x1B}


def parse_hotkey(spec):
    """'ctrl+alt+m' -> (modificadores, código de tecla virtual). Levanta ValueError se inválido."""
    mods, vk = 0, None
    for part in (s.strip().lower() for s in spec.split("+")):
        if part in _MODS:
            mods |= _MODS[part]
        elif part in _NAMED:
            vk = _NAMED[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())  # A-Z e 0-9 usam o próprio código ASCII
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            vk = 0x6F + int(part[1:])
        else:
            raise ValueError(f"tecla desconhecida: {part!r}")
    if vk is None or not mods:
        raise ValueError("o atalho precisa de pelo menos um modificador e uma tecla")
    return mods, vk


def _load_user32():
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    u.RegisterHotKey.restype = wintypes.BOOL
    u.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    u.GetMessageW.restype = ctypes.c_int
    u.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.PostThreadMessageW.restype = wintypes.BOOL
    return u


class HotkeyThread(QThread):
    triggered = Signal()
    failed = Signal(str)

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.mods, self.vk = parse_hotkey(spec)  # ValueError sobe para quem criou
        self._tid = 0

    def _api(self):
        """Separado para os testes poderem trocar por um falso."""
        return _load_user32(), ctypes.windll.kernel32.GetCurrentThreadId

    def run(self):
        try:
            user32, get_tid = self._api()
            self._tid = get_tid()
            if not user32.RegisterHotKey(None, HOTKEY_ID, self.mods | MOD_NOREPEAT, self.vk):
                err = ctypes.get_last_error()
                why = ("já está em uso por outro programa" if err == ERROR_HOTKEY_ALREADY_REGISTERED
                       else f"erro {err} do Windows")
                log(f"atalho {self.spec}: não registrado ({why})")
                self.failed.emit(f"Não foi possível registrar o atalho {self.spec}: {why}.")
                return
            log(f"atalho {self.spec}: registrado")
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    log("atalho acionado")
                    self.triggered.emit()
            user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception as e:  # noqa: BLE001 - qualquer falha deve ir para o log, não sumir
            log(f"atalho {self.spec}: exceção {e!r}")
            self.failed.emit(f"Erro no atalho global: {e}")

    def stop(self):
        if self._tid:
            try:
                _load_user32().PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            except Exception:  # noqa: BLE001
                pass
        self.wait(1000)
