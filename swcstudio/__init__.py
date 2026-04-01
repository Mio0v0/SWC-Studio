"""swcstudio package entrypoint.

Layers:
- swcstudio.core: shared algorithm/data logic
- swcstudio.tools: tool + feature modules
- swcstudio.api: public Python API
- swcstudio.cli: terminal interface
- swcstudio.gui: desktop GUI interface
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("swcstudio")
except PackageNotFoundError:
    # Local source checkout before installation.
    __version__ = "0.1.0"

__all__ = ["api", "core", "tools", "plugins", "cli", "gui", "__version__"]
