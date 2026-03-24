# macOS Packaging

This folder contains the tracked files needed to build a reproducible macOS GUI executable for `SWC-Studio`.

## Files

- `swctools_gui.spec`: PyInstaller spec file for the GUI app bundle
- `build_macos.sh`: reproducible macOS build script

## Recommended Environment

- macOS host
- Python `3.11`

## Build

From the repository root:

```bash
./packaging/build_macos.sh
```

Expected output:

- `dist/SWC-Studio.app`

## Git Policy

Keep in git:

- files in `packaging/`
- `pyproject.toml`

Do not keep in git:

- `build/`
- `dist/`
- generated `.app`
- generated `.dmg`
- generated release `.zip`

## Future Extensions

If you later add an icon or signing/notarization:

- add the icon file under `packaging/`
- update `swctools_gui.spec`
- keep release steps scripted so the build stays reproducible
