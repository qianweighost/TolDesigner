# -*- mode: python ; coding: utf-8 -*-
# 成品文件名自动带版本号：从 app.py 读 APP_VERSION（如 1.2），
# 产出 dist/尺寸链公差分析计算器-v<版本>.exe —— 升版本只改 app.py 一处。
import os
import re

with open(os.path.join(SPECPATH, 'app.py'), encoding='utf-8') as _f:
    _ver = re.search(r'APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]', _f.read()).group(1)
EXE_NAME = f'尺寸链公差分析计算器-v{_ver}'


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2', 'PySide6.QtNetwork', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtDBus', 'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtUiTools', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtSpatialAudio', 'PySide6.QtSerialPort', 'PySide6.QtStateMachine', 'PySide6.QtXml', 'PySide6.QtConcurrent', 'PySide6.QtPrintSupport', 'PySide6.QtSvgWidgets', 'PySide6.QtWebSockets', 'tkinter', 'unittest', 'pydoc'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)
