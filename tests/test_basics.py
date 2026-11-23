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
