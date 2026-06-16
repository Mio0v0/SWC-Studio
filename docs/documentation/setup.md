# Setup

Setup documentation covers installation, local startup, and first-run verification.

```{toctree}
:hidden:
:maxdepth: 1

Getting Started <../GETTING_STARTED>
```

## Installation

<a href="../GETTING_STARTED.html">Getting Started</a> covers all three install paths:

- **bundled desktop app** from GitHub Releases (double-click)
- **`pip install swcstudio`** from PyPI (Python users)
- **source install** from the cloned repository (developers)

The bundled desktop app is the portable CPU distribution. For GPU setup
with pip/source installs, see <a href="../GPU_INSTALL.html">GPU Setup</a>.

## First Run

- if using the bundled app, extract the release zip and open `SWC-Studio.app` / the `.exe`
- if using a pip install, run `swcstudio-gui` to launch the GUI or `swcstudio --help` for the CLI
- if using a source install, run the same commands inside your activated venv to verify
- run `swcstudio gpu-status` or use Help -> GPU Readiness when you want
  to check CUDA/PyTorch availability

## Updating

- bundled app: Help → Check for Updates (in-app updater handles modular updates)
- pip install: `pip install --upgrade swcstudio`
- source install: `git pull` and re-run `pip install -e .`

See <a href="../GETTING_STARTED.html#updating">Getting Started → Updating</a> for full details.
