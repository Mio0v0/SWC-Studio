# -*- mode: python ; coding: utf-8 -*-
"""Modular PyInstaller spec — see packaging/MODULAR_BUILD.md.

Difference from swcstudio_gui.spec:

* Entrypoint is ``swcstudio_bootstrap.py``, not ``run_gui.py``.
* The ``swcstudio`` package is **not** baked into the PyInstaller bundle.
  Instead it's copied as plain ``.py`` files into
  ``Contents/Resources/app/swcstudio/`` by ``packaging/build_macos_modular.sh``
  AFTER PyInstaller runs.
* Models are also not baked in. They live alongside the app/ folder under
  ``Contents/Resources/models/`` and can be replaced by the auto-updater.

Result: code-only updates ship as ~5 MB zips that replace just the
``swcstudio/`` folder. Model-only updates ship as ~60 MB zips.
"""

from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT_DIR = Path.cwd()
ENTRYPOINT = ROOT_DIR / "swcstudio_bootstrap.py"
try:
    APP_VERSION = pkg_version("swcstudio")
except PackageNotFoundError:
    APP_VERSION = "0.1.0"

# --- Data ---
# The bootstrap doesn't import swcstudio at module level, so we have to
# tell PyInstaller about every heavy dependency that swcstudio.gui.main
# will need at runtime.
datas = []
datas += collect_data_files("vispy")
datas += collect_data_files("torch_geometric", include_py_files=True)
datas += collect_data_files("torch", include_py_files=True)
datas += copy_metadata("neurom")
datas += copy_metadata("morphio")
datas += copy_metadata("vispy")
datas += copy_metadata("scikit-learn")
datas += copy_metadata("torch")
datas += copy_metadata("torch_geometric")
# Note: swcstudio's data files (model pickles, tools/*.json) are NOT
# bundled here. They land in Contents/Resources/app/ via the post-build
# copy step.

# --- Hidden imports ---
# Without these, PyInstaller can't see what the late `__import__` of
# swcstudio.gui.main will need at runtime.
hiddenimports = (
    collect_submodules("vispy.app.backends")
    + collect_submodules("sklearn")
    + collect_submodules("scipy")
    + collect_submodules("torch_geometric")
    + [
        "PySide6.QtOpenGLWidgets",
        "pyqtgraph",
        "vispy",
        "vispy.app.backends._qt",
        "vispy.app.backends._pyside6",
        "torch",
        "numpy",
        "pandas",
        "scipy",
        "sklearn",
        "morphio",
        "neurom",
    ]
)

# torch / torch_geometric need the original .py files for TorchScript
# inspect.getsource() paths. Same fix as the monolithic spec.
module_collection_mode = {
    "torch_geometric": "pyz+py",
    "torch": "pyz+py",
}

# --- Excludes ---
# Belt-and-suspenders: explicitly tell PyInstaller never to bundle the
# swcstudio package even if some import path drags it in by accident.
excludes = [
    "swcstudio",
]

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    module_collection_mode=module_collection_mode,
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
    info_plist={
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundleDisplayName": "SWC-Studio",
        "CFBundleName": "SWC-Studio",
    },
)
