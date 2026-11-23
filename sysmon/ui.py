"""Card flutuante de monitoramento (Qt / PySide6). Mesmo visual no Linux e no Windows."""

import ctypes
import json
import math
import os
import sys
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QWidget

from . import autostart, paths

# ------------------------------------------------------------------ visual
FONT_FAMILIES = ["Ubuntu Sans", "Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans"]
SHADOW = 12  # margem transparente para a sombra
PAD = 8
DET_W = 280  # coluna extra do modo avançado
GAP = 8
RADIUS = 14

BG = (0.071, 0.090, 0.133, 1.0)
PANEL = (1, 1, 1, 0.035)
BORDER = (1, 1, 1, 0.07)
TEXT = (0.93, 0.95, 0.98)
MUTED = (0.60, 0.65, 0.73)
DIM = (0.43, 0.47, 0.55)

OK = (0.29, 0.87, 0.50)
WARN = (0.98, 0.80, 0.08)
HOT = (0.97, 0.44, 0.44)

C_CPU = (0.51, 0.55, 0.97)
C_GPU = (0.20, 0.83, 0.60)
C_RAM = (0.75, 0.52, 0.99)
C_RX = (0.38, 0.65, 0.98)
C_TX = (0.98, 0.57, 0.24)

IS_LINUX = sys.platform.startswith("linux")
IS_WIN = sys.platform == "win32"


def load_color(pct, warn=60, hot=85):
    return OK if pct < warn else WARN if pct < hot else HOT


def temp_color(t):
    return load_color(t or 0, 70, 85)


def br(v, decimals=1):
    """Número no formato brasileiro (vírgula decimal)."""
    return f"{v:.{decimals}f}".replace(".", ",")


def fmt_bytes(n, rate=False):
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while n >= 1000 and i < len(units) - 1:
        n /= 1000
        i += 1
    s = f"{int(n)} {units[i]}" if i == 0 else f"{br(n, 0 if n >= 100 else 1)} {units[i]}"
    return s + ("/s" if rate else "")


def gb(n):
    return br(n / 1024**3)


def nice_max(v):
    if v <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 5, 10):
        if v <= m * exp:
            return m * exp
    return 10 * exp


# ------------------------------------------------------------------ primitivas de desenho
def qc(color, alpha=None):
    """Tupla (r,g,b[,a]) em 0..1 -> QColor."""
    a = alpha if alpha is not None else (color[3] if len(color) == 4 else 1.0)
    return QColor.fromRgbF(color[0], color[1], color[2], a)


def rpath(x, y, w, h, r):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


def fill_rr(p, x, y, w, h, r, color):
    p.fillPath(rpath(x, y, w, h, r), qc(color))


def panel(p, x, y, w, h, r=12, fill=PANEL, border=BORDER):
    p.setBrush(qc(fill))
    p.setPen(QPen(qc(border), 1))
    p.drawPath(rpath(x + 0.5, y + 0.5, w - 1, h - 1, r))


_WEIGHTS = {400: QFont.Weight.Normal, 500: QFont.Weight.Medium, 600: QFont.Weight.DemiBold, 700: QFont.Weight.Bold}


@lru_cache(maxsize=None)
def _font(size, weight, spacing):
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPointSizeF(size * 0.75)  # px -> pt a 96 dpi (a app fixa QT_FONT_DPI=96)
    f.setWeight(_WEIGHTS.get(weight, QFont.Weight.Normal))
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    try:  # algarismos de largura fixa (Qt >= 6.7)
        f.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError):
        pass
    return f, QFontMetricsF(f)


def text(p, s, x, y, size=12, color=TEXT, weight=400, align="l", width=None, spacing=0):
    """Desenha texto com o topo em `y`; retorna a largura em px. align: l/r/c (r e c usam `width`)."""
    font, fm = _font(size, weight, spacing)
    if width and align == "l":
        s = fm.elidedText(s, Qt.TextElideMode.ElideRight, width)
    tw = fm.horizontalAdvance(s)
    if align == "r":
        x = x + (width or 0) - tw
    elif align == "c":
        x = x + ((width or 0) - tw) / 2
    p.setFont(font)
    p.setPen(qc(color))
    p.drawText(QPointF(x, y + fm.ascent()), s)
    return tw


def sparkline(p, x, y, w, h, series, vmax):
    """series: [(valores, cor), ...]. Curvas suaves com preenchimento em gradiente."""
    p.save()
    pen = QPen(qc((1, 1, 1), 0.07), 1)
    pen.setDashPattern([3, 3])
    p.setPen(pen)
    ly = round(y + h / 2) + 0.5
    p.drawLine(QPointF(x, ly), QPointF(x + w, ly))

    for data, color in series:
        data = list(data)
        n = len(data)
        if n < 2:
            continue
        step = w / (n - 1)
        pts = [(x + i * step, y + h - min(max(v / vmax, 0), 1) * (h - 2) - 1) for i, v in enumerate(data)]

        line = QPainterPath(QPointF(*pts[0]))
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx = (x1 - x0) / 2
            line.cubicTo(x0 + dx, y0, x1 - dx, y1, x1, y1)

        area = QPainterPath(line)
        area.lineTo(x + w, y + h)
        area.lineTo(x, y + h)
        area.closeSubpath()
        grad = QLinearGradient(0, y, 0, y + h)
        grad.setColorAt(0, qc(color, 0.30))
        grad.setColorAt(1, qc(color, 0.0))
        p.fillPath(area, grad)

        stroke = QPen(qc(color, 1), 1.6)
        stroke.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        stroke.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.strokePath(line, stroke)
    p.restore()


def chevron(p, cx, cy, up, color):
    pen = QPen(qc(color, 1), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    d = -1 if up else 1
    p.setPen(pen)
    p.drawPolyline([QPointF(cx - 4, cy - 2 * d), QPointF(cx, cy + 2 * d), QPointF(cx + 4, cy - 2 * d)])


# ------------------------------------------------------------------ X11: aparecer em todas as áreas de trabalho
def _x11_tweak_window(win_id):
    """Ajustes que o Qt não expõe, direto na janela X11:

    - em todas as áreas de trabalho (_NET_WM_DESKTOP = 0xFFFFFFFF);
    - remove WM_TAKE_FOCUS: só "não aceitar foco" não basta, com WM_TAKE_FOCUS o GNOME ainda
      considera a janela focável (ex.: ao trocar de área de trabalho).
    """
    try:
        x11 = ctypes.CDLL("libX11.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XInternAtom.restype = ctypes.c_ulong
        x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        x11.XSetWMProtocols.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                        ctypes.c_int]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        dpy = x11.XOpenDisplay(None)
        if not dpy:
            return
        atom = x11.XInternAtom(dpy, b"_NET_WM_DESKTOP", 0)
        data = ctypes.c_ulong(0xFFFFFFFF)  # formato 32 bits = "long" no Xlib
        x11.XChangeProperty(dpy, win_id, atom, 6, 32, 0, ctypes.byref(data), 1)  # 6 = XA_CARDINAL
        names = (b"WM_DELETE_WINDOW", b"_NET_WM_PING", b"_NET_WM_SYNC_REQUEST")
        atoms = (ctypes.c_ulong * len(names))(*(x11.XInternAtom(dpy, n, 0) for n in names))
        x11.XSetWMProtocols(dpy, win_id, atoms, len(names))
        x11.XFlush(dpy)
        x11.XCloseDisplay(dpy)
    except (OSError, AttributeError):
        pass


# ------------------------------------------------------------------ janela
class MonitorWindow(QWidget):
    quit_requested = Signal()

    # Tile: linha 1 = rótulo (esq.) + detalhe (dir.); linha 2 = valor (esq.) + gráfico (dir.)
    # O modo curto é enxuto; no avançado há espaço, então tudo fica maior e mais legível.
    TILE_STYLE = {
        False: dict(col=148, h=52, gap=6, pad=8, spark_x=74, spark_top=24, spark_bottom=6,
                    label=9.5, detail=9.5, detail_color=DIM, label_y=7, detail_y=7.5,
                    detail_big=10.5, detail_big_color=MUTED, detail_big_y=6.5,
                    value=19, unit=11, value_y=21, unit_dy=7, rate=10.5, rate_y=(20, 34)),
        True: dict(col=228, h=66, gap=8, pad=11, spark_x=104, spark_top=30, spark_bottom=9,
                   label=11, detail=12, detail_color=MUTED, label_y=9, detail_y=9,
                   detail_big=12, detail_big_color=MUTED, detail_big_y=9,
                   value=25, unit=14, value_y=26, unit_dy=9, rate=14, rate_y=(26, 44)),
    }

    def __init__(self, collector):
        super().__init__()
        self.c = collector
        self.cfg = self._load_cfg()
        self.advanced = bool(self.cfg.get("advanced", False))
        self.hits = []
        self.hover = None
        self._compact_pos = self._expanded_pos = None
        self._size_cache = {}
        self.autostart_on = self._autostart_state()

        self.setWindowTitle("Monitor do Sistema")
        # Sem borda, sempre no topo, fora da barra de tarefas e sem roubar o foco
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)

        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self._save_cfg)

        w, h = self._measure()
        self.setFixedSize(w, h)
        # Ao iniciar o programa, o card sempre aparece no canto superior direito.
        # Durante a sessão, esconder/mostrar mantém onde você arrastou.
        x, y = self._corner_pos(w)
        self.cfg.update(x=x, y=y)
        self.move(x, y)

    # ----------------------------------------------------------- tela
    def _primary(self):
        return QGuiApplication.primaryScreen()

    def _corner_pos(self, w, margin=12):
        scr = self._primary()
        wa, geo = scr.availableGeometry(), scr.geometry()
        # No XWayland a área útil não desconta a barra superior do GNOME
        top_inset = 34 if (IS_LINUX and (wa.y(), wa.height()) == (geo.y(), geo.height())) else 0
        return wa.x() + wa.width() - w + SHADOW - margin, wa.y() + top_inset - SHADOW + margin

    def _workarea_at(self, point):
        scr = QGuiApplication.screenAt(point) if point else None
        return (scr or self._primary()).availableGeometry()

    def _on_some_monitor(self, x, y):
        return any(s.geometry().contains(int(x) + 40, int(y) + 40) for s in QGuiApplication.screens())

    # ----------------------------------------------------------- início automático
    @staticmethod
    def _autostart_state():
        try:
            return autostart.is_enabled()
        except OSError:
            return False

    def set_autostart(self, on):
        try:
            autostart.set_enabled(on)
        except OSError:
            pass
        self.autostart_on = self._autostart_state()
        self.update()

    # ----------------------------------------------------------- config
    def _load_cfg(self):
        try:
            with open(paths.config_file()) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_cfg(self):
        pos = self.pos()
        self.cfg.update(x=pos.x(), y=pos.y(), w=self.width(), advanced=self.advanced)
        try:
            os.makedirs(os.path.dirname(paths.config_file()), exist_ok=True)
            with open(paths.config_file(), "w") as f:
                json.dump(self.cfg, f)
        except OSError:
            pass

    def _queue_save(self):
        self._save_timer.start()

    def moveEvent(self, ev):
        if self.isVisible():
            self._queue_save()
        super().moveEvent(ev)

    def closeEvent(self, ev):
        ev.ignore()
        self.hide()

    # ----------------------------------------------------------- geometria
    def _measure(self):
        cur = self.c.cur
        key = (self.advanced, len(cur.get("disks", ())), bool(cur.get("gpu")), bool(cur))
        if key not in self._size_cache:
            hits, hover = self.hits, self.hover
            img = QImage(1, 1, QImage.Format.Format_ARGB32)
            p = QPainter(img)
            self._size_cache[key] = self._layout(p, measure=True)
            p.end()
            self.hits, self.hover = hits, hover
        return self._size_cache[key]

    def _apply_size(self, target=None):
        """Redimensiona mantendo preso o canto mais próximo da tela (ou indo para `target`).

        Retorna a posição final (x, y).
        """
        old_w, old_h = self.width(), self.height()
        w, h = self._measure()
        x, y = self.x(), self.y()
        if target:
            x, y = target
        else:
            wa = self._workarea_at(self.geometry().center())
            if x + old_w / 2 > wa.x() + wa.width() / 2:
                x += old_w - w
            if y + old_h / 2 > wa.y() + wa.height() / 2:
                y += old_h - h
            x = max(wa.x() - SHADOW, min(x, wa.x() + wa.width() - w + SHADOW))
            y = max(wa.y() - SHADOW, min(y, wa.y() + wa.height() - h + SHADOW))
        if os.environ.get("SYSMON_DEBUG"):
            print(f"apply_size old={old_w}x{old_h} new={w}x{h} target={target} -> pos={x},{y}",
                  file=sys.stderr, flush=True)
        self.setFixedSize(w, h)
        self.setGeometry(int(x), int(y), w, h)  # move e redimensiona juntos
        # Garantia: reaplica a posição depois que o gerenciador de janelas processar o resize
        QTimer.singleShot(120, lambda: self.move(int(x), int(y)))
        return int(x), int(y)

    # ----------------------------------------------------------- visibilidade
    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.reveal()

    def reveal(self):
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if IS_LINUX and QGuiApplication.platformName() == "xcb":
            _x11_tweak_window(int(self.winId()))
        self.show()
        if x is not None and self._on_some_monitor(x, y):
            self.move(int(x), int(y))
        self.raise_()  # traz para cima de tudo sem pegar o foco
        self.update()

    def hide(self):
        if self.isVisible():
            self._save_cfg()
        super().hide()

    def toggle_advanced(self):
        self.advanced = not self.advanced
        self.c.sample(with_procs=self.advanced)
        if self.advanced:
            # Lembra onde o modo curto estava para voltar exatamente para lá ao recolher
            self._compact_pos = (self.x(), self.y())
            self._expanded_pos = self._apply_size()
        else:
            moved = self._expanded_pos is None or any(
                abs(a - b) > 4 for a, b in zip((self.x(), self.y()), self._expanded_pos))
            # Se o usuário arrastou o card expandido, recolhe ancorado no canto mais próximo
            self._apply_size(None if moved else self._compact_pos)
            self._compact_pos = self._expanded_pos = None
        self._queue_save()
        self.update()

    # ----------------------------------------------------------- eventos
    def _hit(self, ex, ey):
        for x, y, w, h, action in self.hits:
            if x <= ex <= x + w and y <= ey <= y + h:
                return action
        return None

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position()
        action = self._hit(pos.x(), pos.y())
        if action == "close":
            self.hide()
        elif action == "advanced":
            self.toggle_advanced()
        elif action == "autostart":
            self.set_autostart(not self.autostart_on)
        elif action == "quit":
            self.quit_requested.emit()
        else:
            handle = self.windowHandle()
            if handle:
                handle.startSystemMove()

    def _set_hover(self, action):
        if action != self.hover:
            self.hover = action
            self.setCursor(Qt.CursorShape.PointingHandCursor if action else Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        self._set_hover(self._hit(pos.x(), pos.y()))

    def leaveEvent(self, ev):
        self._set_hover(None)

    def tick(self):
        if self.isVisible():
            self.update()

    # ----------------------------------------------------------- desenho
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                         | QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self.hits = []
        self._layout(p, measure=False)
        p.end()

    def _layout(self, p, measure):
        """Desenha (ou só mede) o card inteiro. Retorna o tamanho da janela."""
        col_w = self.ts["col"]
        card_w = PAD * 2 + col_w + ((GAP + DET_W) if self.advanced else 0)
        win_w = card_w + SHADOW * 2

        if not measure:
            # O tamanho é determinístico: mede primeiro para desenhar fundo/sombra atrás do conteúdo
            _, win_h = self._measure()
            card_h = win_h - SHADOW * 2
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(SHADOW, 0, -2):
                p.setBrush(QColor(0, 0, 0, 9))
                p.drawPath(rpath(SHADOW - i, SHADOW - i + 3, card_w + 2 * i, card_h + 2 * i, RADIUS + i))
            p.setBrush(qc(BG))
            p.setPen(QPen(qc((1, 1, 1), 0.09), 1))
            p.drawPath(rpath(SHADOW, SHADOW, card_w, card_h, RADIUS))

        x0, y0 = SHADOW + PAD, SHADOW + PAD
        # Cabeçalho (bolinha, "Sistema", modelos e ×) só no modo avançado; o curto começa direto na CPU
        y = self._header(p, x0, y0, card_w - PAD * 2) if self.advanced else y0
        left = self._tiles(p, x0, y, col_w)
        if self.advanced:
            left = self._temps(p, x0, left + GAP, col_w)
            right = self._details(p, x0 + col_w + GAP, y, DET_W)
            # Top processos ocupa a largura toda (a coluna da esquerda ficou estreita demais)
            y = self._procs(p, x0, max(left, right) + GAP, card_w - PAD * 2)
        else:
            y = left
        if self.advanced:
            y = self._actions(p, x0, y + GAP, card_w - PAD * 2)
        y = self._footer(p, x0, y + GAP, card_w - PAD * 2)
        return win_w, int(math.ceil(y + PAD + SHADOW))

    # ----------------------------------------------------------- seções
    def _header(self, p, x, y, w):
        cur = self.c.cur
        worst = max(cur.get("cpu", 0), (cur.get("gpu") or {}).get("util", 0), cur.get("ram", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(load_color(worst), 1))
        p.drawEllipse(QPointF(x + 5, y + 9), 3.5, 3.5)
        tw = text(p, "Sistema", x + 14, y + 1, 13, TEXT, 600)
        sub = self.c.cpu_model + (f"  ·  {self.c.gpu.name}" if self.c.gpu.ok else "")
        text(p, sub, x + 14 + tw + 10, y + 2.5, 11, DIM, width=w - tw - 60)

        bx, by, bs = x + w - 20, y - 1, 20
        if self.hover == "close":
            fill_rr(p, bx, by, bs, bs, 7, (1, 1, 1, 0.08))
        pen = QPen(qc(TEXT if self.hover == "close" else MUTED, 1), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        cx, cy = bx + bs / 2, by + bs / 2
        for dx in (-4, 4):
            p.drawLine(QPointF(cx - 4, cy - dx), QPointF(cx + 4, cy + dx))
        self.hits.append((bx, by, bs, bs, "close"))
        return y + 26

    @property
    def ts(self):
        return self.TILE_STYLE[self.advanced]

    def _tile_frame(self, p, x, y, w, label, detail="", big=False):
        """big=True: detalhe maior e mais claro (CPU, GPU e Memória, que têm espaço sobrando)."""
        t = self.ts
        panel(p, x, y, w, t["h"], 10)
        lw = text(p, label, x + t["pad"], y + t["label_y"], t["label"], MUTED, 600, spacing=0.6)
        if detail:
            k = "detail_big" if big else "detail"
            text(p, detail, x + t["pad"], y + t[k + "_y"], t[k], t[k + "_color"],
                 align="r", width=w - 2 * t["pad"])
        return lw

    def _tile_spark(self, p, x, y, w, series, vmax):
        t = self.ts
        top = y + t["spark_top"]
        sparkline(p, x + t["spark_x"], top, w - t["spark_x"] - t["pad"],
                  t["h"] - t["spark_top"] - t["spark_bottom"], series, vmax)

    def _pct_tile(self, p, x, y, w, label, pct, detail, hist, color):
        t = self.ts
        self._tile_frame(p, x, y, w, label, detail, big=True)
        vc = load_color(pct)
        nw = text(p, f"{pct:.0f}", x + t["pad"], y + t["value_y"], t["value"], vc, 700)
        text(p, "%", x + t["pad"] + 1 + nw, y + t["value_y"] + t["unit_dy"], t["unit"], vc, 600)
        self._tile_spark(p, x, y, w, [(hist, color)], 100)
        return y + t["h"]

    def _rate_tile(self, p, x, y, w, label, detail, a, b, ha, hb, vmin):
        """Tile com duas taxas (ex.: ↓/↑ da rede, leitura/escrita do disco)."""
        t = self.ts
        self._tile_frame(p, x, y, w, label, detail)
        tw = t["spark_x"] - t["pad"] - 2
        text(p, a, x + t["pad"], y + t["rate_y"][0], t["rate"], C_RX, 600, width=tw)
        text(p, b, x + t["pad"], y + t["rate_y"][1], t["rate"], C_TX, 600, width=tw)
        vmax = nice_max(max(max(ha), max(hb), vmin))
        self._tile_spark(p, x, y, w, [(ha, C_RX), (hb, C_TX)], vmax)
        return y + t["h"]

    def _tiles(self, p, x, y, w):
        cur, h = self.c.cur, self.c.h
        if not cur:
            return y
        temp = f" · {cur['cpu_temp']:.0f}°C" if cur.get("cpu_temp") else ""
        y = self._pct_tile(p, x, y, w, "CPU", cur["cpu"], f"{br(cur['freq'] / 1000)} GHz{temp}",
                           h["cpu"], C_CPU) + self.ts["gap"]

        g = cur.get("gpu")
        if g:
            # No curto, o rótulo "GPU" já dá o contexto: mostra só os GB de VRAM
            vram = ("VRAM " if self.advanced else "") + f"{gb(g['mem_used'])}/{gb(g['mem_total'])} GB"
            y = self._pct_tile(p, x, y, w, "GPU", g["util"], vram, h["gpu"], C_GPU) + self.ts["gap"]
        else:
            self._tile_frame(p, x, y, w, "GPU")
            text(p, "NVIDIA não detectada", x + self.ts["pad"], y + self.ts["value_y"] + 3, 12, DIM)
            y += self.ts["h"] + self.ts["gap"]

        y = self._pct_tile(p, x, y, w, "MEMÓRIA", cur["ram"],
                           f"{gb(cur['ram_used'])}/{gb(cur['ram_total'])} GB", h["ram"], C_RAM) + self.ts["gap"]

        y = self._rate_tile(p, x, y, w, "REDE", "",
                            "↓ " + fmt_bytes(cur["rx"], True), "↑ " + fmt_bytes(cur["tx"], True),
                            h["rx"], h["tx"], 50_000) + self.ts["gap"]

        usage = " · ".join(f"{_mount_label(d['mount'])} {d['percent']:.0f}%" for d in cur["disks"])
        return self._rate_tile(p, x, y, w, "DISCO", usage,
                               "L " + fmt_bytes(cur["rd"], True), "E " + fmt_bytes(cur["wr"], True),
                               h["rd"], h["wr"], 1_000_000)

    def _section(self, p, x, y, title):
        text(p, title, x + 2, y, 9.5, DIM, 600, spacing=1)
        return y + 16

    def _kv(self, p, x, y, w, k, v, vcolor=TEXT):
        text(p, k, x + 10, y, 12, MUTED)
        text(p, v, x + 10, y, 12, vcolor, 500, align="r", width=w - 20)
        return y + 21

    def _temps(self, p, x, y, w):
        cur = self.c.cur
        y = self._section(p, x, y, "TEMPERATURAS")
        panel(p, x, y, w, 50, 11)
        items = [("CPU", cur.get("cpu_temp")), ("GPU", (cur.get("gpu") or {}).get("temp"))]
        disk_t = next((d for d in cur["disks"] if d["temp"] is not None), None)
        if disk_t:
            items.append((disk_t["kind"] or "DISCO", disk_t["temp"]))
        cw = w / len(items)
        for i, (lbl, t) in enumerate(items):
            cx = x + i * cw
            text(p, lbl, cx, y + 7, 10, MUTED, 600, align="c", width=cw, spacing=0.8)
            val = f"{t:.0f}°C" if t is not None else "—"
            text(p, val, cx, y + 21, 17, temp_color(t) if t else DIM, 700, align="c", width=cw)
        return y + 50

    def _procs(self, p, x, y, w):
        y = self._section(p, x, y, "TOP PROCESSOS")
        rows = self.c.procs
        ph = 10 + 17 + 21 * 3 + 4
        panel(p, x, y, w, ph, 11)
        cy = y + 8
        cpu_x, ram_x = x + w - 98, x + w - 58
        text(p, "processo", x + 10, cy, 10, DIM)
        text(p, "CPU", cpu_x, cy, 10, DIM, align="r", width=38)
        text(p, "RAM", ram_x, cy, 10, DIM, align="r", width=48)
        cy += 18
        for i in range(3):
            if i < len(rows):
                c, rss, name = rows[i]
                text(p, name, x + 10, cy, 11.5, TEXT, width=cpu_x - x - 12)
                text(p, f"{br(c)}%", cpu_x, cy, 11.5, load_color(c), 500, align="r", width=38)
                text(p, fmt_bytes(rss), ram_x, cy, 11.5, MUTED, align="r", width=48)
            else:
                text(p, "…", x + 10, cy, 12, DIM)
            cy += 21
        return y + ph

    def _details(self, p, x, y, w):
        cur, h = self.c.cur, self.c.h
        if not cur:
            return y

        # Processador: frequência + barras por thread
        y = self._section(p, x, y, f"PROCESSADOR · {self.c.threads} THREADS")
        ph = 82
        panel(p, x, y, w, ph, 11)
        self._kv(p, x, y + 8, w, "Frequência / carga", f"{br(cur['freq'] / 1000)} GHz · {br(cur['load'], 2)}")
        cores = cur["cores"]
        bx, bw, bh, by = x + 10, w - 20, 42, y + 32
        n = len(cores)
        gap = 2 if n <= 40 else 1
        cw = (bw - gap * (n - 1)) / n
        for i, c in enumerate(cores):
            cx = bx + i * (cw + gap)
            fill_rr(p, cx, by, cw, bh, min(2, cw / 2), (1, 1, 1, 0.05))
            fh = max(bh * c / 100, 2)
            fill_rr(p, cx, by + bh - fh, cw, fh, min(2, cw / 2), (*load_color(c), 0.9))
        y += ph + GAP

        g = cur.get("gpu")
        if g:
            y = self._section(p, x, y, "PLACA DE VÍDEO")
            ph = 12 + 21 * 4 - 2
            panel(p, x, y, w, ph, 11)
            cy = y + 8
            vram_pct = 100 * g["mem_used"] / max(g["mem_total"], 1)
            cy = self._kv(p, x, cy, w, "VRAM", f"{gb(g['mem_used'])} / {gb(g['mem_total'])} GB · {vram_pct:.0f}%",
                          load_color(vram_pct))
            lim = self.c.gpu.power_limit
            power = f"{g['power']:.0f} / {lim:.0f} W" if lim else f"{g['power']:.0f} W"
            cy = self._kv(p, x, cy, w, "Consumo", power, load_color(100 * g["power"] / lim) if lim else TEXT)
            cy = self._kv(p, x, cy, w, "Clock", f"{g['clock']} MHz")
            self._kv(p, x, cy, w, "Ventoinha", f"{g['fan']}%" if g["fan"] else "parada")
            y += ph + GAP

        y = self._section(p, x, y, "MEMÓRIA")
        ph = 12 + 21 * 2 - 2
        panel(p, x, y, w, ph, 11)
        cy = self._kv(p, x, y + 8, w, "Cache / buffers", f"{gb(cur['ram_cache'])} GB" if cur["ram_cache"] else "—")
        swap = (f"{gb(cur['swap_used'])} / {gb(cur['swap_total'])} GB · {cur['swap']:.0f}%"
                if cur["swap_total"] else "sem swap")
        self._kv(p, x, cy, w, "Swap", swap, load_color(cur["swap"]) if cur["swap_total"] else MUTED)
        y += ph + GAP

        y = self._section(p, x, y, "DISCOS E REDE")
        disks = cur["disks"]
        ph = 8 + 41 * len(disks) + 21 + 6
        panel(p, x, y, w, ph, 11)
        cy = y + 8
        for d in disks:
            # linha 1: ponto de montagem + tipo | uso
            mw = text(p, _mount_label(d["mount"]), x + 10, cy, 12, TEXT, 600)
            text(p, d["kind"], x + 10 + mw + 6, cy + 1, 10.5, DIM)
            text(p, f"{gb(d['used'])} / {gb(d['total'])} GB · {d['percent']:.0f}%", x + 10, cy, 12,
                 load_color(d["percent"], 75, 90), 500, align="r", width=w - 20)
            # linha 2: modelo | leitura e escrita desta partição (no Windows só há o total, no tile DISCO)
            text(p, d["model"] or "", x + 10, cy + 19, 10.5, DIM, width=w / 2 - 14)
            if IS_LINUX:
                rw = text(p, "E " + fmt_bytes(d["wr"], True), x + 10, cy + 19, 10.5, C_TX, 500,
                          align="r", width=w - 20)
                text(p, "L " + fmt_bytes(d["rd"], True) + "  ", x + 10, cy + 19, 10.5, C_RX, 500,
                     align="r", width=w - 20 - rw)
            cy += 41
        self._kv(p, x, cy, w, "Rede desde o boot",
                 f"↓ {fmt_bytes(cur['rx_total'])}  ↑ {fmt_bytes(cur['tx_total'])}")
        return y + ph

    def _actions(self, p, x, y, w):
        """Só no modo avançado: caixinha "Iniciar com o sistema" e botão "Sair"."""
        h, qw, gap = 26, 70, 6
        aw = w - qw - gap
        for bx, bw, action in ((x, aw, "autostart"), (x + aw + gap, qw, "quit")):
            panel(p, bx, y, bw, h, 8, (1, 1, 1, 0.07 if self.hover == action else 0.035))
            self.hits.append((bx, y, bw, h, action))
        # caixinha
        bx, by = x + 10, y + 7
        if self.autostart_on:
            fill_rr(p, bx, by, 12, 12, 3, C_GPU)
            pen = QPen(qc(BG), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline([QPointF(bx + 3, by + 6.3), QPointF(bx + 5.3, by + 8.6), QPointF(bx + 9, by + 3.8)])
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(qc(MUTED, 0.9), 1.3))
            p.drawPath(rpath(bx + 0.5, by + 0.5, 11, 11, 3))
        text(p, "Iniciar com o sistema", x + 30, y + 5.5, 11.5,
             TEXT if self.hover == "autostart" else MUTED, 500)
        text(p, "Sair", x + aw + gap, y + 5.5, 11.5, HOT if self.hover == "quit" else MUTED, 500,
             align="c", width=qw)
        return y + h

    def _footer(self, p, x, y, w):
        hov = self.hover == "advanced"
        panel(p, x, y, w, 26, 8, (1, 1, 1, 0.07 if hov else 0.035))
        label = "Ver menos" if self.advanced else "Ver avançado"
        col = TEXT if hov else MUTED
        tw = text(p, label, x, y + 5.5, 11.5, col, 500, align="c", width=w - 14)
        chevron(p, x + (w - 14 + tw) / 2 + 10, y + 13, self.advanced, col)
        self.hits.append((x, y, w, 26, "advanced"))
        return y + 26


def _mount_label(mount):
    """No Windows 'C:\\' vira 'C:'."""
    return mount.rstrip("\\") if IS_WIN else mount
