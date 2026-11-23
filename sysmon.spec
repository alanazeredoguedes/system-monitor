# PyInstaller: Linux gera uma pasta (abre rápido, bom para o atalho); Windows gera um .exe único.
import sys

WIN = sys.platform == "win32"
EXCLUDES = ["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.QtSvg", "PySide6.QtOpenGL",
            "PySide6.QtDBus", "tkinter", "unittest", "pydoc", "test"]

a = Analysis(["sysmon.py"], excludes=EXCLUDES)
pyz = PYZ(a.pure)

if WIN:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="sysmon", console=False, upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="sysmon", console=True, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="sysmon", upx=False)
