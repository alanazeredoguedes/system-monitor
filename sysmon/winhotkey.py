"""Atalho global no Windows (RegisterHotKey). Só é importado no Windows."""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID = 0x5359  # "SY"

_MODS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT,
         "win": MOD_WIN, "super": MOD_WIN}
_NAMED = {"pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26,
          "right": 0x27, "down": 0x28, "insert": 0x2D, "delete": 0x2E, "space": 0x20, "tab": 0x09,
          "enter": 0x0D, "esc": 0x1B}


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


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, spec, callback):
        super().__init__()
        self.callback = callback
        mods, vk = parse_hotkey(spec)
        self.ok = bool(ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk))

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.callback()
                return True, 0
        return False, 0

    def unregister(self):
        ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
