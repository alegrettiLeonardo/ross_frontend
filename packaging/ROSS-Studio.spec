# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ENTRY = SRC / "ross_studio" / "frozen_entry.py"

# Keep ROSS as a complete runtime unit because several solver/result modules are
# imported lazily. ROSS imports ccp through its labyrinth-seal module during
# top-level initialization, but the Studio does not use ccp's optional Streamlit,
# AI or compressor-application modules. Let PyInstaller follow the ccp modules
# that are actually imported and add only ccp runtime data explicitly. This keeps
# required Pint definitions such as ccp/config/new_units.txt while avoiding a
# several-hundred-megabyte bundle of unrelated optional ccp applications.
ross_datas, ross_binaries, ross_hiddenimports = collect_all("ross")
ccp_datas = collect_data_files("ccp", include_py_files=False)

hiddenimports = list(dict.fromkeys([
    *ross_hiddenimports,
    # Loaded lazily by RossNativeRotorView; explicit inclusion is required so the
    # packaged executable preserves the native Plotly/Qt audit view.
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
]))

datas = [
    *ross_datas,
    *ccp_datas,
    (str(SRC / "ross_studio" / "resources"), "ross_studio/resources"),
]
binaries = [*ross_binaries]

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
