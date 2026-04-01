# Packaging

This folder contains the tracked files needed to build reproducible GUI executables for `SWC-Studio`.

## Files

- `swcstudio_gui.spec`: PyInstaller spec file for the macOS app bundle
- `swcstudio_gui_windows.spec`: PyInstaller spec file for the Windows executable folder
- `build_macos.sh`: reproducible macOS build script
- `build_windows.ps1`: reproducible Windows build script
- `make_windows_icon.py`: converts `packaging/icon.png` into a Windows `.ico` file

## Recommended Environment

- macOS host
- Python `3.11`

For Windows packaging:

- Windows host
- Python environment with GUI + build dependencies installed

## Build

From the repository root:

```bash
./packaging/build_macos.sh
```

Expected output:

- `dist/SWC-Studio.app`

On Windows, from the repository root:

```powershell
.\packaging\build_windows.ps1
```

Expected output:

- `dist/SWC-Studio\`
- `dist/SWC-Studio-windows.zip`

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

If you later add signing/notarization or new platform assets:

- add the icon file under `packaging/`
- update the relevant `*.spec`
- keep release steps scripted so the build stays reproducible
