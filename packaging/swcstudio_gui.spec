# -*- mode: python ; coding: utf-8 -*-

from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

ROOT_DIR = Path.cwd()
ENTRYPOINT = ROOT_DIR / "run_gui.py"
try:
    APP_VERSION = pkg_version("swcstudio")
except PackageNotFoundError:
    APP_VERSION = "0.1.0"


def _exclude_xgboost_tests(name):
    return not name.startswith("xgboost.testing")


datas = collect_data_files(
    "swcstudio",
    includes=[
        "tools/**/*.json",
        # Auto-typing model files — without these the bundled engine
        # fails to load Stage 1, Stage 2, Stage 2b, Branch3, QC, or
        # compact flag scoring at runtime. Mirrors the Windows spec.
        "data/models/*.pkl",
        "data/models/*.pt",
        "data/models/*.joblib",
    ],
)
datas += collect_data_files("vispy")
# torch_geometric uses TorchScript, which calls inspect.getsource() at
# import time on classes like SelectOutput. PyInstaller bundles
# ``.pyc`` only by default, so the resulting frozen build crashes with
# ``OSError: Can't get source for <class 'torch_geometric.nn.pool.select.base.SelectOutput'>``.
# include_py_files=True copies the original .py alongside the .pyc so
# inspect.getsource works at runtime. Same trick for torch's
# JIT-compiled paths.
datas += collect_data_files("torch_geometric", include_py_files=True)
datas += collect_data_files("torch", include_py_files=True)
datas += collect_data_files("xgboost", includes=["VERSION"])
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
datas += copy_metadata("xgboost")
datas += copy_metadata("zstandard")
datas += copy_metadata("pyzipper")

binaries = collect_dynamic_libs("xgboost")

hiddenimports = (
    collect_submodules("swcstudio.gui")
    + collect_submodules("swcstudio.tools")
    + collect_submodules("swcstudio.core")
    + collect_submodules("vispy.app.backends")
    + collect_submodules("sklearn")
    + collect_submodules("scipy")
    + collect_submodules("xgboost", filter=_exclude_xgboost_tests)
    # torch_geometric loads many submodules lazily through registered
    # operator decorators; explicit submodule listing wasn't enough on
    # 2.7.x. Use collect_submodules to force the entire tree into the
    # bundle so ``import torch_geometric`` resolves on first call.
    + collect_submodules("torch_geometric")
    + [
        "PySide6.QtOpenGLWidgets",
        "pyqtgraph",
        "vispy",
        "vispy.app.backends._qt",
        "vispy.app.backends._pyside6",
        "torch",
        "xgboost",
        "zstandard",
        "pyzipper",
        "pyzipper.zipfile",
        "pyzipper.zipfile_aes",
    ]
)

# Tell PyInstaller to keep the original .py files (not just compiled
# .pyc) for torch_geometric and the parts of torch that hit
# inspect.getsource(). Without this the bundled engine crashes on
# the first auto-label run with a TorchScript source-access error.
module_collection_mode = {
    "torch_geometric": "pyz+py",
    "torch": "pyz+py",
}

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["xgboost.testing", "hypothesis"],
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
