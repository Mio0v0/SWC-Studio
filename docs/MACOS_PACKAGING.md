# Reproducible macOS Packaging

The macOS release is a modular PyInstaller app. Its heavy runtime,
replaceable Python application layer, and model layer are stored
separately.

## Inputs

- `packaging/swcstudio_gui_macos.spec`
- `packaging/pyinstaller_common.py`
- `packaging/swcstudio_bootstrap.py`
- `packaging/stage_modular_payload.py`
- `packaging/build_macos.sh`
- `pyproject.toml`

## Build environment

```bash
python3.12 -m venv .venv-packaging-macos
source .venv-packaging-macos/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -e ".[build]"
```

## Build command

```bash
PYTHON_BIN=python3.12 ./packaging/build_macos.sh
```

The result is `dist/SWC-Studio.app`. Application code is staged under
`Contents/Resources/app/swcstudio`, and models are staged under
`Contents/Resources/models`.

Build on macOS for macOS. The current bundle is unsigned, so first launch
may require right-clicking the app and choosing **Open**.
