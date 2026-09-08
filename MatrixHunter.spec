# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['pymem']
tmp_ret = collect_all('pymem')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D',
        'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtBluetooth',
        'PySide6.QtNfc', 'PySide6.QtPositioning', 'PySide6.QtSensors',
        'PySide6.QtWebChannel', 'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets', 'PySide6.QtXml',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtSpatialAudio', 'PySide6.QtHelp',
        'PySide6.QtDesigner', 'PySide6.QtRemoteObjects',
        'PySide6.QtScxml', 'PySide6.QtStateMachine',
        'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
        'PySide6.QtCharts', 'PySide6.QtSerialPort',
        'PySide6.QtSerialBus', 'PySide6.QtHttpServer',
        'PySide6.QtTextToSpeech', 'PySide6.QtOpenGLWidgets',
        'PySide6.QtOpenGL',
    ],
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
    name='MatrixHunter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
