# Reproducible macOS Packaging

This page describes the tracked packaging setup for building a macOS GUI executable for `SWC-Studio`.

## Goal

Build a reproducible macOS `.app` bundle from the same source tree, with packaging inputs committed to git and generated artifacts ignored.

## Files In Git

These files are part of the reproducible build setup and should stay in git:

- `packaging/swctools_gui.spec`
- `packaging/build_macos.sh`
- `packaging/README.md`
- `pyproject.toml`

## Files Not In Git

Generated build outputs should not be tracked:

- `build/`
- `dist/`
- generated `.app`
- generated `.dmg`
- generated `.pkg`
- temporary release `.zip` files

## Build Dependency Source

Packaging dependencies are declared in `pyproject.toml`:

- `.[gui]` for runtime GUI dependencies
- `.[build]` for build tooling (`PyInstaller`)

Recommended install inside a clean macOS build environment:

```bash
python3.11 -m venv .venv-packaging-macos
source .venv-packaging-macos/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -e ".[gui,build]"
```

## Build Command

Preferred one-command entrypoint:

```bash
./packaging/build_macos.sh
```

This script:

1. creates or refreshes a dedicated macOS packaging virtual environment
2. installs the project with GUI and build extras
3. runs PyInstaller with the tracked spec file
4. writes the app bundle under `dist/`

## Output

Expected output:

- `dist/SWC-Studio.app`

Optional release zip:

```bash
cd dist
zip -r SWC-Studio-macos.zip SWC-Studio.app
```

## Notes

- Build on macOS for macOS.
- For best consistency, use Python 3.11.
- Unsigned macOS apps may require users to right-click and choose **Open** on first launch.
- If you later add code signing or notarization, keep those steps in `packaging/build_macos.sh` or a companion release script so the process remains reproducible.
