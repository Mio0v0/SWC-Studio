# Modular desktop architecture

macOS and Windows use the same three-layer desktop design:

| Layer | Contents | Update method |
|---|---|---|
| Runtime | Python, Qt, PyTorch, scientific libraries | Replace the full desktop bundle |
| Application | Plain `swcstudio/` Python source | Download a small code layer and restart |
| Models | Auto-label model files | Download the model layer |

## Runtime layout

The platform-specific runtime root contains:

```text
app/
  VERSION
  swcstudio/
models/
  VERSION
  cell_type_classifier.pkl
  branch_classifier.pkl
  gnn_apical_basal.pt
  gnn_branch3_rescue.pt
  qc_gate.pkl
  flag_model_*.joblib
```

The runtime root is `Contents/Resources` on macOS and `_internal` in the
Windows one-folder distribution.

## Bootstrap behavior

`packaging/swcstudio_bootstrap.py` searches for application code in this
order:

1. user code override:
   - macOS: `~/Library/Application Support/SWC-Studio/app`
   - Windows: `%APPDATA%\SWC-Studio\app`
   - Linux: `$XDG_DATA_HOME/SWC-Studio/app`
2. bundled `runtime-root/app`
3. source checkout, for direct development execution

It adds the selected code root to `sys.path`, exposes the bundled model
directory through `SWCSTUDIO_BUNDLED_MODEL_DIR`, and then imports
`swcstudio.gui.main`.

Models are resolved in this order:

1. explicit `--model-dir`
2. `SWCSTUDIO_MODEL_DIR`
3. user model directory (`.../swcstudio/models`)
4. bundled runtime model directory supplied by the bootstrap
5. package-local `swcstudio/data/models`

## Building

```bash
# macOS
PYTHON_BIN=python3.12 ./packaging/build_macos.sh

# Windows PowerShell
py -3.12 -m venv .venv-packaging-windows
.\.venv-packaging-windows\Scripts\python.exe -m pip install -e ".[build]" pillow
.\packaging\build_windows.ps1
```

Both scripts:

1. build the dependency runtime with a platform spec
2. call `stage_modular_payload.py`
3. stage code under `app/swcstudio`
4. stage models under `models`

The platform specs share dependency collection through
`pyinstaller_common.py`.

## Updates

The release manifest describes separate application and model archives.
The updater extracts them into user-writable override directories.
Application-layer updates are offered only when the modular bootstrap
has marked the current process as a modular desktop bundle. Pip/source
users update the complete package with `pip`; published wheels already
contain the matching production models. The model download path remains
available as a repair/update fallback.

Deleting an override restores the code or models bundled with the
desktop runtime.
