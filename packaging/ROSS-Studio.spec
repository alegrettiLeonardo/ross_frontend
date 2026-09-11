# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ENTRY = SRC / "ross_studio" / "frozen_entry.py"

# ROSS imports ccp through its labyrinth-seal module during top-level package
# initialization. ccp loads Pint unit-definition/data files at runtime, so collecting
# only Python modules is insufficient for a frozen executable. Keep both packages as
# complete runtime units instead of chasing individual resource files one by one.
ross_datas, ross_binaries, ross_hiddenimports = collect_all("ross")
ccp_datas, ccp_binaries, ccp_hiddenimports = collect_all("ccp")

# Engineering Outputs 0.18 writes XLSX/PDF and static PNGs from the exact native
# Plotly figures returned by ROSS. Kaleido carries an external renderer binary/data;
# reportlab/openpyxl also have runtime resources and lazy imports. Collect each
# package as a complete unit so the same export gates hold in the frozen app.
kaleido_datas, kaleido_binaries, kaleido_hiddenimports = collect_all("kaleido")
reportlab_datas, reportlab_binaries, reportlab_hiddenimports = collect_all("reportlab")
openpyxl_datas, openpyxl_binaries, openpyxl_hiddenimports = collect_all("openpyxl")

hiddenimports = list(dict.fromkeys([
    *ross_hiddenimports,
    *ccp_hiddenimports,
    *kaleido_hiddenimports,
    *reportlab_hiddenimports,
    *openpyxl_hiddenimports,
    # Loaded lazily by NativeRossFigureView; explicit inclusion is required so the
    # packaged executable preserves the native Plotly/Qt audit view.
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
]))

datas = [
    *ross_datas,
    *ccp_datas,
    *kaleido_datas,
    *reportlab_datas,
    *openpyxl_datas,
    (str(SRC / "ross_studio" / "resources"), "ross_studio/resources"),
]
binaries = [
    *ross_binaries,
    *ccp_binaries,
    *kaleido_binaries,
    *reportlab_binaries,
    *openpyxl_binaries,
]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=binaries,
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
