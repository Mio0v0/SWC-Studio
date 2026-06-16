# Modular updates — design and operations

The **monolithic** build (`packaging/swcstudio_gui.spec` + `build_macos.sh`)
welds Python, all libraries, the swcstudio code, and the model files into one
PyInstaller bundle. Updating any one line of code requires the user to
re-download the whole thing. Release executables should be built from a
CPU-only PyTorch environment; building from a CUDA PyTorch environment can
pull in a much larger CUDA runtime stack.

The **modular** build (`packaging/swcstudio_gui_modular.spec` +
`build_macos_modular.sh`) splits the bundle into three layers that update
independently:

| Layer       | Lives in                                     | Typical size | Updates when                          |
|-------------|----------------------------------------------|--------------|----------------------------------------|
| Runtime     | `Contents/Frameworks/` (PyInstaller bundle)   | largest layer | PyTorch / Qt / Python pin changes      |
| Code        | `Contents/Resources/app/swcstudio/`           | ~5 MB        | Most releases (bug fixes, features)    |
| Models      | `Contents/Resources/models/`                  | ~75-80 MB    | When the auto-labeling model bundle changes |

End users fetch fresh **code** or **model** layers without re-downloading the
heavy runtime. They only pay the ~700 MB cost when the runtime itself bumps
(rare — once a year for a Torch upgrade, etc.).

## How the bootstrap finds the code

When you double-click the bundled .app, the entry point is
`swcstudio_bootstrap.py`. It searches three locations *in order* and uses
the first one that has a usable `swcstudio/` package inside it:

1. **User override**:
   * macOS:    `~/Library/Application Support/SWC-Studio/app/swcstudio/`
   * Windows:  `%APPDATA%\SWC-Studio\app\swcstudio\`
   * Linux:    `~/.local/share/swcstudio/app/swcstudio/`
   The auto-updater downloads here. This wins over the bundled copy.
2. **Bundled** (what shipped with the .app):
   `<bundle>/Contents/Resources/app/swcstudio/`
3. **Source repo** (only when running from a checkout):
   `<repo>/swcstudio/`

Models follow the same pattern but rooted at `.../SWC-Studio/models/`.

## Building the modular bundle (macOS)

```bash
PYTHON_BIN=python3.12 ./packaging/build_macos_modular.sh
```

Produces `dist/SWC-Studio.app` with:

```
SWC-Studio.app/
├── Contents/
│   ├── MacOS/SWC-Studio                    # bootstrap exe
│   ├── Frameworks/                         # heavy runtime libs
│   └── Resources/
│       ├── app/
│       │   └── swcstudio/                  # plain .py files — swappable
│       │       ├── VERSION                 # "0.1.0\n"
│       │       └── ...
│       └── models/
│           ├── VERSION
│           ├── cell_type_classifier.pkl
│           ├── branch_classifier.pkl
│           ├── gnn_apical_basal.pt
│           ├── gnn_branch3_rescue.pt
│           ├── qc_gate.pkl
│           ├── flag_model_pyramidal.joblib
│           ├── flag_model_interneuron.joblib
│           └── flag_model_all.joblib
```

## How updates flow at runtime

The app calls `swcstudio.core.updater.fetch_manifest()` either at startup
or on a user-triggered "Check for updates" action. The manifest is a JSON
asset attached to each GitHub Release that looks like:

```json
{
  "release_version": "0.2.0",
  "released_utc":    "2026-06-01T12:00:00Z",
  "app": {
    "version": "0.2.0",
    "url":     "https://github.com/Mio0v0/SWC-Studio/releases/download/v0.2.0/swcstudio-code-v0.2.0.zip",
    "size":    5242880,
    "sha256":  "abc..."
  },
  "models": {
    "version": "0.1.0",
    "url":     "https://github.com/Mio0v0/SWC-Studio/releases/download/v0.2.0/swcstudio-models-v0.1.0.zip",
    "size":    78643200,
    "sha256":  "def..."
  },
  "runtime": {
    "min_version": "0.1.0",
    "url_macos":   "https://github.com/.../v0.2.0/SWC-Studio-v0.2.0-macOS.zip",
    "url_windows": "https://github.com/.../v0.2.0/SWC-Studio-v0.2.0-Windows.zip"
  }
}
```

When `available_updates()` reports a newer `app` version, the GUI offers
to apply it. `apply_update("app", manifest.app)`:

1. Downloads the zip into a temp dir
2. Verifies SHA-256 (if provided)
3. Extracts to a staging dir
4. Atomically moves into the user override directory
5. Stamps a `VERSION` file so subsequent launches know what's installed

The next time the user launches the app, the bootstrap finds the override
and uses it. The bundled `Contents/Resources/app/` is left untouched —
which means the update can be **rolled back by deleting the override
directory**.

The same mechanism works for `apply_update("models", manifest.models)` —
no app restart required because models are loaded fresh on each
auto-label call.

## CPU Runtime And GPU Installs

The public one-click executable should use a CPU PyTorch runtime. This
keeps the download portable and avoids tying the release to one CUDA
stack. GPU acceleration is supported through pip/source installs where
the user can install the PyTorch/CUDA and PyTorch Geometric builds that
match their machine. See `docs/GPU_INSTALL.md`.

## What pip users get

Pip users install via:

```bash
pip install swcstudio
```

For pip distribution, the wheel is small (just code; models are downloaded
on first auto-label use, into the same `~/Library/Application Support/SWC-Studio/models/`
location). To upgrade:

```bash
pip install --upgrade swcstudio
```

Pip handles the differential download natively. The model resolver in
`swcstudio.core.model_paths` falls back to `swcstudio.core.updater` to
pull models from GitHub Releases on demand, so pip-installed users never
need to bundle models in their wheel.

## Publishing a release that supports modular updates

A future release tag (`v0.2.0`) would attach these assets to the GitHub
Release page:

| Asset                              | What it is                              |
|------------------------------------|-----------------------------------------|
| `SWC-Studio-v0.2.0-macOS.zip`      | Full .app for new users (or runtime upgrade) |
| `SWC-Studio-v0.2.0-Windows.zip`    | Full Windows package                    |
| `swcstudio-code-v0.2.0.zip`        | Code-only update (~5 MB)                |
| `swcstudio-models-v0.2.0.zip`      | Models-only update (~75-80 MB raw model files) |
| `swcstudio-0.2.0-py3-none-any.whl` | pip wheel                               |
| `update_manifest.json`             | the JSON manifest above                 |

Existing users on v0.1.x get a notification that v0.2.0 is available and
choose between *Code only*, *Models only*, or *Full update*. Most updates
will be code-only.

## Side-by-side with the monolithic build

You can keep both builds. Run `build_macos.sh` for the legacy monolithic
build, `build_macos_modular.sh` for the modular one. The two specs and
build scripts are independent.

For the migration, ship the modular build once it's proven and let users
auto-update from there.
