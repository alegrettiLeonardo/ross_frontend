# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent.parent
SRC = ROOT / "src"
ENTRY = SRC / "ross_studio" / "frozen_entry.py"

ross_datas, ross_binaries, ross_hiddenimports = collect_all("ross")

hiddenimports = list(ross_hiddenimports) + [
    # Loaded lazily by RossNativeRotorView; explicit inclusion is required so the
    # packaged executable preserves the native Plotly/Qt audit view.
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
]

datas = list(ross_datas) + [
    (str(SRC / "ross_studio" / "resources"), "ross_studio/resources"),
]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=list(ross_binaries),
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ROSS-Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ROSS-Studio",
)
