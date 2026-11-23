"""Aplicação: janela, coleta a cada 1 s, controle por socket local, bandeja e atalho global (Windows)."""

import os
import sys

from PySide6.QtCore import QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtNetwork import QHostAddress, QTcpServer
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import ipc
from .log import log
from .metrics import Collector
from .ui import MonitorWindow

IS_WIN = sys.platform == "win32"


def make_icon():
    """Ícone desenhado em código (cartão escuro com uma curva verde), sem arquivos externos."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QPainterPath()
        card.addRoundedRect(QRectF(size * .04, size * .04, size * .92, size * .92), size * .22, size * .22)
        p.fillPath(card, QColor(18, 23, 34))
        pen = QPen(QColor(52, 211, 153), max(size * .09, 1.5))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        line = QPainterPath()
        pts = [(.18, .66), (.34, .66), (.45, .30), (.58, .74), (.68, .46), (.82, .46)]
        line.moveTo(size * pts[0][0], size * pts[0][1])
        for x, y in pts[1:]:
            line.lineTo(size * x, size * y)
        p.strokePath(line, pen)
        p.end()
        icon.addPixmap(pm)
    return icon


class Controller(QObject):
    def __init__(self, app, server):
        super().__init__()
        self.app = app
        self.server = server
        self.collector = Collector()
        self.collector.sample()
        self.win = MonitorWindow(self.collector)
        self.win.setWindowIcon(app.windowIcon())
        self.win.quit_requested.connect(app.quit)

        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        server.newConnection.connect(self._on_connection)

        self.tray = None
        if not os.environ.get("SYSMON_NO_TRAY"):
            self._setup_tray()
        self.hotkey = None

    # ----------------------------------------------------------- bandeja
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.app.windowIcon(), self)
        self.tray.setToolTip("Monitor do Sistema")
        menu = QMenu()
        for label, slot in (("Mostrar / ocultar", self.win.toggle), ("Ver avançado", self.win.toggle_advanced)):
            act = QAction(label, menu)
            act.triggered.connect(slot)
            menu.addAction(act)
        auto = QAction("Iniciar com o sistema", menu, checkable=True)
        auto.toggled.connect(lambda on: self.win.set_autostart(on) if on != self.win.autostart_on else None)
        menu.aboutToShow.connect(lambda: auto.setChecked(self.win._autostart_state()))
        menu.addAction(auto)
        menu.addSeparator()
        quit_act = QAction("Sair", menu)
        quit_act.triggered.connect(self.app.quit)
        menu.addAction(quit_act)
        self._tray_menu = menu  # mantém a referência viva
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.win.toggle() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    # ----------------------------------------------------------- atalho global (Windows)
    def setup_hotkey(self, spec):
        if not IS_WIN:
            return
        from .winhotkey import HotkeyThread
        try:
            self.hotkey = HotkeyThread(spec, self)
        except ValueError as e:
            self._hotkey_problem(f"Atalho inválido ({e}).")
            return
        self.hotkey.triggered.connect(self.win.toggle)
        self.hotkey.failed.connect(self._hotkey_problem)
        self.hotkey.start()

    def _hotkey_problem(self, text):
        log(text)
        if self.tray:
            self.tray.showMessage("Monitor do Sistema", text, QSystemTrayIcon.MessageIcon.Warning, 8000)

    # ----------------------------------------------------------- comandos
    def handle(self, cmd):
        w = self.win
        if cmd == "toggle":
            w.toggle()
        elif cmd == "show":
            w.reveal()
        elif cmd == "hide":
            w.hide()
        elif cmd == "advanced":
            w.toggle_advanced()
        elif cmd == "quit":
            self.app.quit()

    def _on_connection(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.setParent(self)
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(sock.deleteLater)
            QTimer.singleShot(1000, sock.deleteLater)

    def _read(self, sock):
        for line in bytes(sock.readAll()).decode(errors="ignore").split():
            self.handle(line)

    def _tick(self):
        visible = self.win.isVisible()
        self.collector.sample(with_procs=self.win.advanced and visible)
        self.win.tick()

    def shutdown(self):
        if self.hotkey:
            self.hotkey.stop()
        self.win._save_cfg()


def run(start_hidden=False, first_cmd=None, hotkey=None):
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Monitor do Sistema")
    app.setQuitOnLastWindowClosed(False)  # continua rodando mesmo com o card escondido
    app.setWindowIcon(make_icon())

    server = QTcpServer()
    if not server.listen(QHostAddress(ipc.HOST), ipc.PORT):
        # Corrida: outra instância subiu agora há pouco. Entrega o comando a ela e sai.
        ipc.send(first_cmd or "toggle")
        return 0

    ctl = Controller(app, server)
    if IS_WIN:
        ctl.setup_hotkey(hotkey or ctl.win.cfg.get("hotkey", "ctrl+pageup"))
    if not start_hidden:
        ctl.win.reveal()
    if first_cmd == "advanced":
        ctl.win.toggle_advanced()
    app.aboutToQuit.connect(ctl.shutdown)
    return app.exec()
