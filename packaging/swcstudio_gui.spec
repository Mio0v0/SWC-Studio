# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT_DIR = Path.cwd()
ENTRYPOINT = ROOT_DIR / "run_gui.py"

datas = collect_data_files(
    "swcstudio",
    includes=[
        "tools/**/*.json",
    ],
)
datas += collect_data_files("vispy")
datas += copy_metadata("neurom")
datas += copy_metadata("morphio")
datas += copy_metadata("swcstudio")
datas += copy_metadata("vispy")

hiddenimports = (
    collect_submodules("swcstudio.gui")
    + collect_submodules("swcstudio.tools")
    + collect_submodules("vispy.app.backends")
    + [
        "PySide6.QtOpenGLWidgets",
        "pyqtgraph",
        "vispy",
        "vispy.app.backends._qt",
        "vispy.app.backends._pyside6",
    ]
)

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SWC-Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SWC-Studio",
)

ICON_PATH = ROOT_DIR / "packaging" / "icon.icns"

app = BUNDLE(
    coll,
    name="SWC-Studio.app",
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
    bundle_identifier="io.github.mio0v0.swcstudio",
)
