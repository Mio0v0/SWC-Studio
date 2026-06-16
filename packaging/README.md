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
- CPU-only PyTorch for the release executable build

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

The Windows build script fails fast if the active environment contains a
CUDA PyTorch build. That prevents accidentally bundling a very large
CUDA/PyTorch stack into the default one-click executable. If a maintainer
intentionally wants an experimental GPU bundle, run:

```powershell
.\packaging\build_windows.ps1 -AllowCudaTorchBundle
```

The recommended public release remains the CPU executable. GPU users
should use pip/source installation and follow `docs/GPU_INSTALL.md`.

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
