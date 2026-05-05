# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT_DIR = Path.cwd()
ENTRYPOINT = ROOT_DIR / "run_gui.py"
ICON_PATH = ROOT_DIR / "packaging" / "icon.ico"

datas = collect_data_files(
    "swcstudio",
    includes=[
        "tools/**/*.json",
        # v9 auto-typing model files — without these the bundled engine
        # fails to load Stages 1 / 2 / 2b at startup.
        "data/models/*.pkl",
        "data/models/*.pt",
    ],
)
datas += collect_data_files("vispy")
datas += copy_metadata("neurom")
datas += copy_metadata("morphio")
datas += copy_metadata("swcstudio")
datas += copy_metadata("vispy")
# torch_geometric ships its version metadata in a .txt — copy_metadata
# also catches it. sklearn just needs its package data for some
# deserialization paths.
datas += copy_metadata("scikit-learn")
datas += copy_metadata("torch")
datas += copy_metadata("torch_geometric")

hiddenimports = (
    collect_submodules("swcstudio.gui")
    + collect_submodules("swcstudio.tools")
    + collect_submodules("swcstudio.core")
    + collect_submodules("vispy.app.backends")
    + collect_submodules("sklearn")
    + collect_submodules("scipy")
    + [
        "PySide6.QtOpenGLWidgets",
        "pyqtgraph",
        "vispy",
        "vispy.app.backends._qt",
        "vispy.app.backends._pyside6",
        # Stage 2b GraphSAGE GNN runtime — torch + torch_geometric are
        # required deps now, so make sure PyInstaller bundles their
        # full submodule tree. Some torch_geometric paths import lazily
        # and would otherwise be missed.
        "torch",
        "torch_geometric",
        "torch_geometric.nn",
        "torch_geometric.nn.conv",
        "torch_geometric.data",
        "torch_geometric.utils",
        "torch_geometric.loader",
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
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
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
