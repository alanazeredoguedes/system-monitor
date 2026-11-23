"""Card flutuante de monitoramento do sistema (GTK3 + Cairo, X11)."""

import ctypes
import json
import math
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402

import cairo  # noqa: E402

from .metrics import Collector  # noqa: E402

APP_ID = "io.github.vapo.sysmon"
CONFIG = os.path.join(GLib.get_user_config_dir(), "sysmon", "config.json")

# ------------------------------------------------------------------ visual
FONT = "Ubuntu Sans"
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
def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def panel(cr, x, y, w, h, r=12, fill=PANEL, border=BORDER):
    rrect(cr, x + 0.5, y + 0.5, w - 1, h - 1, r)
    cr.set_source_rgba(*fill)
    cr.fill_preserve()
    cr.set_source_rgba(*border)
    cr.set_line_width(1)
    cr.stroke()


def text(cr, s, x, y, size=12, color=TEXT, weight=400, align="l", width=None, spacing=0):
    """Desenha texto; retorna a largura em px. align: l/r/c (r e c usam `width`)."""
    layout = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription.from_string(FONT)
    fd.set_absolute_size(size * Pango.SCALE)
    fd.set_weight(weight)
    layout.set_font_description(fd)
    attrs = Pango.AttrList()
    attrs.insert(Pango.attr_font_features_new("tnum=1"))
    if spacing:
        attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
    layout.set_attributes(attrs)
    layout.set_text(s, -1)
    if width and align == "l":
        layout.set_width(int(width * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
    tw, _ = layout.get_pixel_size()
    if align == "r":
        x = x + (width or 0) - tw
    elif align == "c":
        x = x + ((width or 0) - tw) / 2
    cr.move_to(x, y)
    cr.set_source_rgba(*color, 1) if len(color) == 3 else cr.set_source_rgba(*color)
    PangoCairo.show_layout(cr, layout)
    return tw


def sparkline(cr, x, y, w, h, series, vmax):
    """series: [(valores, cor), ...]. Curvas suaves com preenchimento em gradiente."""
    cr.save()
    cr.set_source_rgba(1, 1, 1, 0.07)
    cr.set_line_width(1)
    cr.set_dash([3, 3])
    cr.move_to(x, round(y + h / 2) + 0.5)
    cr.line_to(x + w, round(y + h / 2) + 0.5)
    cr.stroke()
    cr.set_dash([])

    for data, color in series:
        data = list(data)
        n = len(data)
        if n < 2:
            continue
        step = w / (n - 1)
        pts = [(x + i * step, y + h - min(max(v / vmax, 0), 1) * (h - 2) - 1) for i, v in enumerate(data)]

        def path():
            cr.move_to(*pts[0])
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                dx = (x1 - x0) / 2
                cr.curve_to(x0 + dx, y0, x1 - dx, y1, x1, y1)

        path()
        cr.line_to(x + w, y + h)
        cr.line_to(x, y + h)
        cr.close_path()
        grad = cairo.LinearGradient(0, y, 0, y + h)
        grad.add_color_stop_rgba(0, *color, 0.30)
        grad.add_color_stop_rgba(1, *color, 0.0)
        cr.set_source(grad)
        cr.fill()

        path()
        cr.set_source_rgba(*color, 1)
        cr.set_line_width(1.6)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke()
    cr.restore()


def chevron(cr, cx, cy, up, color):
    cr.set_source_rgba(*color, 1)
    cr.set_line_width(1.6)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    d = -1 if up else 1
    cr.move_to(cx - 4, cy - 2 * d)
    cr.line_to(cx, cy + 2 * d)
    cr.line_to(cx + 4, cy - 2 * d)
    cr.stroke()


# ------------------------------------------------------------------ foco (X11)
def _drop_take_focus(gdk_win):
    """Remove WM_TAKE_FOCUS da janela X11.

    Só `accept_focus=False` não basta: com WM_TAKE_FOCUS o GNOME ainda considera a janela
    focável (ex.: ao trocar de área de trabalho) e o GTK aceita o foco quando o recebe.
    """
    try:
        gi.require_version("GdkX11", "3.0")
        from gi.repository import GdkX11
        if not isinstance(gdk_win, GdkX11.X11Window):
            return
        gdk = ctypes.CDLL("libgdk-3.so.0")
        x11 = ctypes.CDLL("libX11.so.6")
        gdk.gdk_x11_get_default_xdisplay.restype = ctypes.c_void_p
        x11.XInternAtom.restype = ctypes.c_ulong
        x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XSetWMProtocols.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_int]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        dpy = gdk.gdk_x11_get_default_xdisplay()
        names = (b"WM_DELETE_WINDOW", b"_NET_WM_PING", b"_NET_WM_SYNC_REQUEST")
        atoms = (ctypes.c_ulong * len(names))(*(x11.XInternAtom(dpy, n, 0) for n in names))
        x11.XSetWMProtocols(dpy, gdk_win.get_xid(), atoms, len(names))
        x11.XFlush(dpy)
    except (OSError, ValueError, ImportError):
        pass


# ------------------------------------------------------------------ janela
class MonitorWindow(Gtk.Window):
    def __init__(self, app, collector):
        super().__init__(application=app, title="Monitor do Sistema")
        self.c = collector
        self.cfg = self._load_cfg()
        self.advanced = bool(self.cfg.get("advanced", False))
        self.hits = []
        self.hover = None
        self._save_src = None
        self._compact_pos = self._expanded_pos = None

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        # O card nunca rouba o foco (nem ao trocar de área de trabalho, nem ao aparecer pelo atalho).
        # Cliques continuam funcionando; por isso não há atalhos de teclado dentro do card.
        self.set_accept_focus(False)
        self.connect("realize", lambda *_: _drop_take_focus(self.get_window()))
        self.stick()
        self.set_app_paintable(True)
        screen = self.get_screen()
        self.composited = screen.is_composited() and screen.get_rgba_visual() is not None
        if self.composited:
            self.set_visual(screen.get_rgba_visual())

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._on_draw)
        self.add(self.area)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("button-press-event", self._on_press)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("leave-notify-event", lambda *_: self._set_hover(None))
        self.connect("configure-event", self._on_configure)
        self.connect("delete-event", lambda *_: self.hide() or True)

        w, h = self._measure()
        self.area.set_size_request(w, h)
        # Ao iniciar o programa, o card sempre aparece no canto superior direito.
        # Durante a sessão, esconder/mostrar mantém onde você arrastou.
        x, y = self._corner_pos(w)
        self.cfg.update(x=x, y=y)
        self.move(x, y)

    def _corner_pos(self, w, margin=12):
        display = Gdk.Display.get_default()
        mon = display.get_primary_monitor() or display.get_monitor(0)
        wa, geo = mon.get_workarea(), mon.get_geometry()
        # No XWayland a área útil não desconta a barra superior do GNOME
        top_inset = 34 if (wa.y, wa.height) == (geo.y, geo.height) else 0
        return wa.x + wa.width - w + SHADOW - margin, wa.y + top_inset - SHADOW + margin

    # ----------------------------------------------------------- config
    def _load_cfg(self):
        try:
            with open(CONFIG) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_cfg(self):
        self._save_src = None
        x, y = self.get_position()
        w, _ = self.get_size()
        self.cfg.update(x=x, y=y, w=w, advanced=self.advanced)
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, "w") as f:
            json.dump(self.cfg, f)
        return False

    def _queue_save(self):
        if self._save_src:
            GLib.source_remove(self._save_src)
        self._save_src = GLib.timeout_add(600, self._save_cfg)

    def _on_configure(self, *_):
        if self.get_visible():
            self._queue_save()
        return False

    # ----------------------------------------------------------- geometria
    def _workarea_at(self, point):
        display = Gdk.Display.get_default()
        mon = display.get_monitor_at_point(*point) if point else (display.get_primary_monitor() or display.get_monitor(0))
        return mon.get_workarea()

    def _on_some_monitor(self, x, y):
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            g = display.get_monitor(i).get_geometry()
            if g.x <= x + 40 < g.x + g.width and g.y <= y + 40 < g.y + g.height:
                return True
        return False

    def _measure(self):
        hits, hover = self.hits, self.hover
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        size = self._layout(cairo.Context(surf), measure=True)
        self.hits, self.hover = hits, hover
        return size

    def _apply_size(self, target=None):
        """Redimensiona mantendo preso o canto mais próximo da tela (ou indo para `target`).

        Retorna a posição final (x, y).
        """
        old_w, old_h = self.get_size()
        w, h = self._measure()
        x, y = self.get_position()
        if target:
            x, y = target
        else:
            wa = self._workarea_at((x + old_w // 2, y + old_h // 2))
            if x + old_w / 2 > wa.x + wa.width / 2:
                x += old_w - w
            if y + old_h / 2 > wa.y + wa.height / 2:
                y += old_h - h
            x = max(wa.x - SHADOW, min(x, wa.x + wa.width - w + SHADOW))
            y = max(wa.y - SHADOW, min(y, wa.y + wa.height - h + SHADOW))
        if os.environ.get("SYSMON_DEBUG"):
            print(f"apply_size old={old_w}x{old_h} new={w}x{h} target={target} -> pos={x},{y}",
                  file=sys.stderr, flush=True)
        self.area.set_size_request(w, h)
        self.resize(w, h)
        # Move e redimensiona juntos: se movesse antes de encolher, a janela ainda larga
        # ficaria fora da tela e o GNOME a empurraria de volta (era o bug do "não volta pro canto").
        gdk_win = self.get_window()
        if gdk_win:
            gdk_win.move_resize(x, y, w, h)
        self.move(x, y)
        # Garantia: reaplica a posição depois que o gerenciador de janelas processar o resize
        GLib.timeout_add(120, lambda: self.move(x, y) and False)
        return x, y

    # ----------------------------------------------------------- visibilidade
    def toggle(self):
        if os.environ.get("SYSMON_DEBUG"):
            import time
            print(f"{time.strftime('%T')} toggle visible={self.get_visible()}", file=sys.stderr, flush=True)
        if self.get_visible():
            self.hide()
        else:
            self.reveal()

    def reveal(self):
        x, y = self.cfg.get("x"), self.cfg.get("y")
        self.show_all()
        if x is not None and self._on_some_monitor(x, y):
            self.move(x, y)
        self.set_keep_above(True)
        self.stick()
        if self.get_window():
            self.get_window().raise_()  # traz para cima de tudo sem pegar o foco
        self.area.queue_draw()

    def hide(self):
        if self.get_visible():
            self._save_cfg()
        super().hide()

    def toggle_advanced(self):
        self.advanced = not self.advanced
        self.c.sample(with_procs=self.advanced)
        if self.advanced:
            # Lembra onde o modo curto estava para voltar exatamente para lá ao recolher
            self._compact_pos = self.get_position()
            self._expanded_pos = self._apply_size()
        else:
            moved = self._expanded_pos is None or any(
                abs(a - b) > 4 for a, b in zip(self.get_position(), self._expanded_pos))
            # Se o usuário arrastou o card expandido, recolhe ancorado no canto mais próximo
            self._apply_size(None if moved else self._compact_pos)
            self._compact_pos = self._expanded_pos = None
        self._queue_save()
        self.area.queue_draw()

    # ----------------------------------------------------------- eventos
    def _hit(self, ex, ey):
        for x, y, w, h, action in self.hits:
            if x <= ex <= x + w and y <= ey <= y + h:
                return action
        return None

    def _on_press(self, _w, ev):
        if ev.button != 1 or ev.type != Gdk.EventType.BUTTON_PRESS:
            return False
        action = self._hit(ev.x, ev.y)
        if action == "close":
            self.hide()
        elif action == "advanced":
            self.toggle_advanced()
        else:
            self.begin_move_drag(ev.button, int(ev.x_root), int(ev.y_root), ev.time)
        return True

    def _set_hover(self, action):
        if action != self.hover:
            self.hover = action
            cursor = Gdk.Cursor.new_from_name(self.get_display(), "pointer" if action else "default")
            if self.get_window():
                self.get_window().set_cursor(cursor)
            self.area.queue_draw()
        return False

    def _on_motion(self, _w, ev):
        return self._set_hover(self._hit(ev.x, ev.y))

    def tick(self):
        if self.get_visible():
            self.area.queue_draw()

    # ----------------------------------------------------------- desenho
    def _on_draw(self, _area, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        self.hits = []
        self._layout(cr, measure=False)
        return False

    def _layout(self, cr, measure):
        """Desenha (ou só mede) o card inteiro. Retorna o tamanho da janela."""
        col_w = self.ts["col"]
        card_w = PAD * 2 + col_w + ((GAP + DET_W) if self.advanced else 0)
        win_w = card_w + SHADOW * 2

        if not measure:
            # O tamanho é determinístico: mede primeiro para desenhar fundo/sombra atrás do conteúdo
            _, win_h = self._measure()
            card_h = win_h - SHADOW * 2
            if self.composited:
                for i in range(SHADOW, 0, -2):
                    rrect(cr, SHADOW - i, SHADOW - i + 3, card_w + 2 * i, card_h + 2 * i, RADIUS + i)
                    cr.set_source_rgba(0, 0, 0, 0.035)
                    cr.fill()
            rrect(cr, SHADOW, SHADOW, card_w, card_h, RADIUS)
            cr.set_source_rgba(*BG) if self.composited else cr.set_source_rgb(*BG[:3])
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.09)
            cr.set_line_width(1)
            cr.stroke()

        x0, y0 = SHADOW + PAD, SHADOW + PAD
        # Cabeçalho (bolinha, "Sistema", modelos e ×) só no modo avançado; o curto começa direto na CPU
        y = self._header(cr, x0, y0, card_w - PAD * 2) if self.advanced else y0
        left = self._tiles(cr, x0, y, col_w)
        if self.advanced:
            left = self._temps(cr, x0, left + GAP, col_w)
            right = self._details(cr, x0 + col_w + GAP, y, DET_W)
            # Top processos ocupa a largura toda (a coluna da esquerda ficou estreita demais)
            y = self._procs(cr, x0, max(left, right) + GAP, card_w - PAD * 2)
        else:
            y = left
        y = self._footer(cr, x0, y + GAP, card_w - PAD * 2)
        return win_w, y + PAD + SHADOW

    # ----------------------------------------------------------- seções
    def _header(self, cr, x, y, w):
        cur = self.c.cur
        worst = max(cur.get("cpu", 0), (cur.get("gpu") or {}).get("util", 0), cur.get("ram", 0))
        cr.arc(x + 5, y + 9, 3.5, 0, 2 * math.pi)
        cr.set_source_rgba(*load_color(worst), 1)
        cr.fill()
        tw = text(cr, "Sistema", x + 14, y + 1, 13, TEXT, 600)
        if self.advanced:
            sub = self.c.cpu_model + (f"  ·  {self.c.gpu.name}" if self.c.gpu.ok else "")
            text(cr, sub, x + 14 + tw + 10, y + 2.5, 11, DIM, width=w - tw - 60)

        bx, by, bs = x + w - 20, y - 1, 20
        if self.hover == "close":
            rrect(cr, bx, by, bs, bs, 7)
            cr.set_source_rgba(1, 1, 1, 0.08)
            cr.fill()
        cr.set_source_rgba(*(TEXT if self.hover == "close" else MUTED), 1)
        cr.set_line_width(1.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cx, cy = bx + bs / 2, by + bs / 2
        for dx in (-4, 4):
            cr.move_to(cx - 4, cy - dx)
            cr.line_to(cx + 4, cy + dx)
        cr.stroke()
        self.hits.append((bx, by, bs, bs, "close"))
        return y + 26

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

    @property
    def ts(self):
        return self.TILE_STYLE[self.advanced]

    def _tile_frame(self, cr, x, y, w, label, detail="", big=False):
        """big=True: detalhe maior e mais claro (CPU, GPU e Memória, que têm espaço sobrando)."""
        t = self.ts
        panel(cr, x, y, w, t["h"], 10)
        lw = text(cr, label, x + t["pad"], y + t["label_y"], t["label"], MUTED, 600, spacing=0.6)
        if detail:
            k = "detail_big" if big else "detail"
            text(cr, detail, x + t["pad"], y + t[k + "_y"], t[k], t[k + "_color"],
                 align="r", width=w - 2 * t["pad"])
        return lw

    def _tile_spark(self, cr, x, y, w, series, vmax):
        t = self.ts
        top = y + t["spark_top"]
        sparkline(cr, x + t["spark_x"], top, w - t["spark_x"] - t["pad"],
                  t["h"] - t["spark_top"] - t["spark_bottom"], series, vmax)

    def _pct_tile(self, cr, x, y, w, label, pct, detail, hist, color):
        t = self.ts
        self._tile_frame(cr, x, y, w, label, detail, big=True)
        vc = load_color(pct)
        nw = text(cr, f"{pct:.0f}", x + t["pad"], y + t["value_y"], t["value"], vc, 700)
        text(cr, "%", x + t["pad"] + 1 + nw, y + t["value_y"] + t["unit_dy"], t["unit"], vc, 600)
        self._tile_spark(cr, x, y, w, [(hist, color)], 100)
        return y + t["h"]

    def _rate_tile(self, cr, x, y, w, label, detail, a, b, ha, hb, vmin):
        """Tile com duas taxas (ex.: ↓/↑ da rede, leitura/escrita do disco)."""
        t = self.ts
        self._tile_frame(cr, x, y, w, label, detail)
        tw = t["spark_x"] - t["pad"] - 2
        text(cr, a, x + t["pad"], y + t["rate_y"][0], t["rate"], C_RX, 600, width=tw)
        text(cr, b, x + t["pad"], y + t["rate_y"][1], t["rate"], C_TX, 600, width=tw)
        vmax = nice_max(max(max(ha), max(hb), vmin))
        self._tile_spark(cr, x, y, w, [(ha, C_RX), (hb, C_TX)], vmax)
        return y + t["h"]

    def _tiles(self, cr, x, y, w):
        cur, h = self.c.cur, self.c.h
        if not cur:
            return y
        temp = f" · {cur['cpu_temp']:.0f}°C" if cur.get("cpu_temp") else ""
        y = self._pct_tile(cr, x, y, w, "CPU", cur["cpu"], f"{br(cur['freq'] / 1000)} GHz{temp}",
                           h["cpu"], C_CPU) + self.ts["gap"]

        g = cur.get("gpu")
        if g:
            # No curto, o rótulo "GPU" já dá o contexto: mostra só os GB de VRAM
            vram = ("VRAM " if self.advanced else "") + f"{gb(g['mem_used'])}/{gb(g['mem_total'])} GB"
            y = self._pct_tile(cr, x, y, w, "GPU", g["util"], vram, h["gpu"], C_GPU) + self.ts["gap"]
        else:
            self._tile_frame(cr, x, y, w, "GPU")
            text(cr, "NVIDIA não detectada", x + self.ts["pad"], y + self.ts["value_y"] + 3, 12, DIM)
            y += self.ts["h"] + self.ts["gap"]

        y = self._pct_tile(cr, x, y, w, "MEMÓRIA", cur["ram"],
                           f"{gb(cur['ram_used'])}/{gb(cur['ram_total'])} GB", h["ram"], C_RAM) + self.ts["gap"]

        y = self._rate_tile(cr, x, y, w, "REDE", "",
                            "↓ " + fmt_bytes(cur["rx"], True), "↑ " + fmt_bytes(cur["tx"], True),
                            h["rx"], h["tx"], 50_000) + self.ts["gap"]

        usage = " · ".join(f"{d['mount']} {d['percent']:.0f}%" for d in cur["disks"])
        return self._rate_tile(cr, x, y, w, "DISCO", usage,
                               "L " + fmt_bytes(cur["rd"], True), "E " + fmt_bytes(cur["wr"], True),
                               h["rd"], h["wr"], 1_000_000)

    def _section(self, cr, x, y, title):
        text(cr, title, x + 2, y, 9.5, DIM, 600, spacing=1)
        return y + 16

    def _kv(self, cr, x, y, w, k, v, vcolor=TEXT):
        text(cr, k, x + 10, y, 12, MUTED)
        text(cr, v, x + 10, y, 12, vcolor, 500, align="r", width=w - 20)
        return y + 21

    def _temps(self, cr, x, y, w):
        cur = self.c.cur
        y = self._section(cr, x, y, "TEMPERATURAS")
        panel(cr, x, y, w, 50, 11)
        items = [("CPU", cur.get("cpu_temp")), ("GPU", (cur.get("gpu") or {}).get("temp"))]
        disk_t = next((d for d in cur["disks"] if d["temp"] is not None), None)
        if disk_t:
            items.append((disk_t["kind"], disk_t["temp"]))
        cw = w / len(items)
        for i, (lbl, t) in enumerate(items):
            cx = x + i * cw
            text(cr, lbl, cx, y + 7, 10, MUTED, 600, align="c", width=cw, spacing=0.8)
            val = f"{t:.0f}°C" if t is not None else "—"
            text(cr, val, cx, y + 21, 17, temp_color(t) if t else DIM, 700, align="c", width=cw)
        return y + 50

    def _procs(self, cr, x, y, w):
        y = self._section(cr, x, y, "TOP PROCESSOS")
        rows = self.c.procs
        ph = 10 + 17 + 21 * 3 + 4
        panel(cr, x, y, w, ph, 11)
        cy = y + 8
        cpu_x, ram_x = x + w - 98, x + w - 58
        text(cr, "processo", x + 10, cy, 10, DIM)
        text(cr, "CPU", cpu_x, cy, 10, DIM, align="r", width=38)
        text(cr, "RAM", ram_x, cy, 10, DIM, align="r", width=48)
        cy += 18
        for i in range(3):
            if i < len(rows):
                c, rss, name = rows[i]
                text(cr, name, x + 10, cy, 11.5, TEXT, width=cpu_x - x - 12)
                text(cr, f"{br(c)}%", cpu_x, cy, 11.5, load_color(c), 500, align="r", width=38)
                text(cr, fmt_bytes(rss), ram_x, cy, 11.5, MUTED, align="r", width=48)
            else:
                text(cr, "…", x + 10, cy, 12, DIM)
            cy += 21
        return y + ph

    def _details(self, cr, x, y, w):
        cur, h = self.c.cur, self.c.h
        if not cur:
            return y

        # Processador: frequência + barras por thread
        y = self._section(cr, x, y, f"PROCESSADOR · {self.c.threads} THREADS")
        ph = 82
        panel(cr, x, y, w, ph, 11)
        self._kv(cr, x, y + 8, w, "Frequência / carga", f"{br(cur['freq'] / 1000)} GHz · {br(cur['load'], 2)}")
        cores = cur["cores"]
        bx, bw, bh, by = x + 10, w - 20, 42, y + 32
        n = len(cores)
        gap = 2 if n <= 40 else 1
        cw = (bw - gap * (n - 1)) / n
        for i, c in enumerate(cores):
            cx = bx + i * (cw + gap)
            rrect(cr, cx, by, cw, bh, min(2, cw / 2))
            cr.set_source_rgba(1, 1, 1, 0.05)
            cr.fill()
            fh = max(bh * c / 100, 2)
            rrect(cr, cx, by + bh - fh, cw, fh, min(2, cw / 2))
            cr.set_source_rgba(*load_color(c), 0.9)
            cr.fill()
        y += ph + GAP

        g = cur.get("gpu")
        if g:
            y = self._section(cr, x, y, "PLACA DE VÍDEO")
            ph = 12 + 21 * 4 - 2
            panel(cr, x, y, w, ph, 11)
            cy = y + 8
            vram_pct = 100 * g["mem_used"] / max(g["mem_total"], 1)
            cy = self._kv(cr, x, cy, w, "VRAM", f"{gb(g['mem_used'])} / {gb(g['mem_total'])} GB · {vram_pct:.0f}%",
                          load_color(vram_pct))
            lim = self.c.gpu.power_limit
            power = f"{g['power']:.0f} / {lim:.0f} W" if lim else f"{g['power']:.0f} W"
            cy = self._kv(cr, x, cy, w, "Consumo", power, load_color(100 * g["power"] / lim) if lim else TEXT)
            cy = self._kv(cr, x, cy, w, "Clock", f"{g['clock']} MHz")
            self._kv(cr, x, cy, w, "Ventoinha", f"{g['fan']}%" if g["fan"] else "parada")
            y += ph + GAP

        y = self._section(cr, x, y, "MEMÓRIA")
        ph = 12 + 21 * 2 - 2
        panel(cr, x, y, w, ph, 11)
        cy = self._kv(cr, x, y + 8, w, "Cache / buffers", f"{gb(cur['ram_cache'])} GB")
        swap = f"{gb(cur['swap_used'])} / {gb(cur['swap_total'])} GB · {cur['swap']:.0f}%" if cur["swap_total"] else "sem swap"
        self._kv(cr, x, cy, w, "Swap", swap, load_color(cur["swap"]) if cur["swap_total"] else MUTED)
        y += ph + GAP

        y = self._section(cr, x, y, "DISCOS E REDE")
        disks = cur["disks"]
        ph = 8 + 41 * len(disks) + 21 + 6
        panel(cr, x, y, w, ph, 11)
        cy = y + 8
        for d in disks:
            # linha 1: ponto de montagem + tipo | uso
            mw = text(cr, d["mount"], x + 10, cy, 12, TEXT, 600)
            text(cr, d["kind"], x + 10 + mw + 6, cy + 1, 10.5, DIM)
            text(cr, f"{gb(d['used'])} / {gb(d['total'])} GB · {d['percent']:.0f}%", x + 10, cy, 12,
                 load_color(d["percent"], 75, 90), 500, align="r", width=w - 20)
            # linha 2: modelo | leitura e escrita desta partição
            text(cr, d["model"] or "", x + 10, cy + 19, 10.5, DIM, width=w / 2 - 14)
            rw = text(cr, "E " + fmt_bytes(d["wr"], True), x + 10, cy + 19, 10.5, C_TX, 500,
                      align="r", width=w - 20)
            text(cr, "L " + fmt_bytes(d["rd"], True) + "  ", x + 10, cy + 19, 10.5, C_RX, 500,
                 align="r", width=w - 20 - rw)
            cy += 41
        self._kv(cr, x, cy, w, "Rede desde o boot",
                 f"↓ {fmt_bytes(cur['rx_total'])}  ↑ {fmt_bytes(cur['tx_total'])}")
        return y + ph

    def _footer(self, cr, x, y, w):
        hov = self.hover == "advanced"
        panel(cr, x, y, w, 26, 8, (1, 1, 1, 0.07 if hov else 0.035))
        label = "Ver menos" if self.advanced else "Ver avançado"
        col = TEXT if hov else MUTED
        tw = text(cr, label, x, y + 5.5, 11.5, col, 500, align="c", width=w - 14)
        chevron(cr, x + (w - 14 + tw) / 2 + 10, y + 13, self.advanced, col)
        self.hits.append((x, y, w, 26, "advanced"))
        return y + 26


# ------------------------------------------------------------------ aplicação
class SysMonApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win = None
        self.collector = None
        self.add_main_option("hidden", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Inicia escondido (para o autostart)", None)
        self.add_main_option("quit", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Encerra o monitor", None)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()  # continua rodando mesmo com o card escondido
        for name, cb in (("toggle", lambda *_: self.win.toggle()),
                         ("show", lambda *_: self.win.reveal()),
                         ("hide", lambda *_: self.win.hide()),
                         ("advanced", lambda *_: self.win.toggle_advanced()),
                         ("quit", lambda *_: self.quit())):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)

    def _ensure_window(self):
        if self.win:
            return
        self.collector = Collector()
        self.collector.sample()
        self.win = MonitorWindow(self, self.collector)
        GLib.timeout_add(1000, self._tick)

    def _tick(self):
        visible = self.win.get_visible()
        self.collector.sample(with_procs=self.win.advanced and visible)
        self.win.tick()
        return True

    def do_command_line(self, cmdline):
        opts = cmdline.get_options_dict().end().unpack()
        first = self.win is None
        self._ensure_window()
        if opts.get("quit"):
            self.quit()
        elif first:
            if not opts.get("hidden"):
                self.win.reveal()
        else:
            self.win.toggle()  # segunda chamada (ex.: atalho) alterna
        return 0


def main():
    return SysMonApp().run(sys.argv)
