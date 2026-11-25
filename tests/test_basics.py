import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


def test_collector_samples():
    from sysmon.metrics import Collector
    c = Collector()
    cur = c.sample(with_procs=True)
    assert 0 <= cur["cpu"] <= 100
    assert cur["ram_total"] > 0
    assert len(c.h["cpu"]) == 60


def test_fmt():
    from sysmon.ui import br, fmt_bytes
    assert br(1.5) == "1,5"
    assert fmt_bytes(1500, True) == "1,5 KB/s"


def test_hotkey_parse():
    pytest.importorskip("PySide6")
    from sysmon.winhotkey import MOD_ALT, MOD_CONTROL, parse_hotkey
    assert parse_hotkey("ctrl+alt+m") == (MOD_CONTROL | MOD_ALT, ord("M"))
    assert parse_hotkey("Ctrl+PageUp") == (MOD_CONTROL, 0x21)
    assert parse_hotkey("ctrl+f9") == (MOD_CONTROL, 0x78)
    with pytest.raises(ValueError):
        parse_hotkey("m")
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+banana")


def test_render_both_modes():
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from sysmon.metrics import Collector
    from sysmon.ui import MonitorWindow
    app = QApplication.instance() or QApplication([])
    c = Collector()
    c.sample(with_procs=True)
    w = MonitorWindow(c)
    for adv in (False, True):
        w.advanced = adv
        size = w._measure()
        w.setFixedSize(*size)
        img = QImage(w.size(), QImage.Format.Format_ARGB32)
        w.render(img)
        assert not img.isNull()
    assert app is not None


class _FakeUser32:
    """Simula o user32 do Windows: entrega um WM_HOTKEY e depois encerra o laço."""

    def __init__(self, register_ok=True):
        self.register_ok, self.calls, self.unregistered = register_ok, 0, False

    def RegisterHotKey(self, *a):  # noqa: N802
        self.args = a
        return 1 if self.register_ok else 0

    def GetMessageW(self, ref, *a):  # noqa: N802
        self.calls += 1
        if self.calls == 1:
            from sysmon.winhotkey import HOTKEY_ID, WM_HOTKEY
            ref._obj.message, ref._obj.wParam = WM_HOTKEY, HOTKEY_ID
            return 1
        return 0

    def UnregisterHotKey(self, *a):  # noqa: N802
        self.unregistered = True


def _run_thread(fake, spec="ctrl+pageup"):
    from PySide6.QtWidgets import QApplication
    from sysmon.winhotkey import HotkeyThread

    class T(HotkeyThread):
        def _api(self):
            return fake, lambda: 1

    app = QApplication.instance() or QApplication([])
    t, got = T(spec), {"hits": 0, "errors": []}
    t.triggered.connect(lambda: got.__setitem__("hits", got["hits"] + 1))
    t.failed.connect(got["errors"].append)
    t.start()
    t.wait(3000)
    app.processEvents()
    return t, got


def test_hotkey_thread_triggers():
    fake = _FakeUser32()
    t, got = _run_thread(fake)
    assert got["hits"] == 1 and not got["errors"]
    assert fake.args[2] & 0x4000 and fake.args[3] == 0x21  # NOREPEAT + VK_PRIOR
    assert fake.unregistered


def test_hotkey_thread_reports_refusal():
    t, got = _run_thread(_FakeUser32(register_ok=False))
    assert got["hits"] == 0 and len(got["errors"]) == 1


def test_autostart_command_uses_appimage_path(monkeypatch):
    from sysmon import autostart
    monkeypatch.setenv("APPIMAGE", "/home/x/Apps/sysmon-x86_64.AppImage")
    assert autostart._command() == ["/home/x/Apps/sysmon-x86_64.AppImage"]
    monkeypatch.delenv("APPIMAGE")
    assert autostart._command()[-1].endswith("sysmon.py")
