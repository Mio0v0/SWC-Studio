"""swcstudio package entrypoint.

Layers:
- swcstudio.core: shared algorithm/data logic
- swcstudio.tools: tool + feature modules
- swcstudio.api: public Python API
- swcstudio.cli: terminal interface
- swcstudio.gui: desktop GUI interface
"""

import os as _os
import sys as _sys

# macOS ships xgboost and torch wheels that both dlopen libomp.dylib; once
# both are loaded into the same process, concurrent OpenMP regions segfault
# on arm64 (xgboost 3.2 + torch 2.12 reproduces with any OMP_NUM_THREADS>1).
# KMP_DUPLICATE_LIB_OK silences the duplicate-load fast-fail; pinning OpenMP
# to a single thread is what actually keeps auto-label inference alive.
# setdefault lets power users override either knob; revisit when xgboost or
# torch ships an arm64 OpenMP fix.
if _sys.platform == "darwin":
    _os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    _os.environ.setdefault("OMP_NUM_THREADS", "1")

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("swcstudio")
except PackageNotFoundError:
    # Local source checkout before installation.
    __version__ = "0.1.0"

__all__ = ["api", "core", "tools", "plugins", "cli", "gui", "__version__"]
