# SWC-Studio

`SWC-Studio` is a desktop, CLI, and Python toolkit for working with neuron morphology files in SWC format.

It is designed for inspecting reconstructions, finding structural or annotation problems, repairing them, and running repeatable morphology-processing workflows from one shared backend.

## Project Overview

`SWC-Studio` includes:

- a shared Python backend (`swcstudio`)
- a command-line interface (`swcstudio`)
- a desktop GUI (`swcstudio-gui`)

Both the CLI and GUI use the same core feature logic.

### Auto-labeling engine

Auto-labeling uses a single ML pipeline: the **v9 engine**. It runs a four-stage process — cell-type detection, per-subtree axon/basal/apical classification, a GraphSAGE GNN apical-vs-basal re-decision, and topology refinement — and automatically chooses between 3-class (no apical) and 4-class output per file. All four stages are required and ship trained out of the box.

The auto-typing models ship inside the bundled desktop app and the source checkout, and are auto-downloaded on first use for `pip install swcstudio`. In all three cases the engine works without any manual model setup. Users can also retrain on their own labeled SWC corpus via `swcstudio train auto-typing` and have the toolkit pick up the new models automatically.

## Documentation

Project documentation lives on the docs website:

- Live docs: [https://mio0v0.github.io/SWC-Studio/](https://mio0v0.github.io/SWC-Studio/)
- All releases: [https://github.com/Mio0v0/SWC-Studio/releases](https://github.com/Mio0v0/SWC-Studio/releases)

Use the docs site for:

- installation and getting started
- GUI and CLI workflows
- validation, repair, and reporting behavior
- the auto-typing engine and retraining workflow
- tutorials
- API and extension references

### Release Assets

Each GitHub Release attaches three sets of assets:

- **Bundled apps** — `SWC-Studio-vX.Y.Z-macOS.zip`, `SWC-Studio-vX.Y.Z-Windows.zip` (double-click installers)
- **Pip packages** — `swcstudio-X.Y.Z-py3-none-any.whl` and `swcstudio-X.Y.Z.tar.gz` (also published to PyPI)
- **Modular update layers** — `swcstudio-code-vX.Y.Z.zip`, `swcstudio-models-vX.Y.Z.zip`, and `update_manifest.json` (consumed by the in-app updater; end users never download these manually)

## Quick Start

Three supported install paths, depending on what you need.

### Option 1 — End user, double-click the desktop app

Use this path if you only need the desktop application and don't want to deal with Python.

1. Open <https://github.com/Mio0v0/SWC-Studio/releases/latest>
2. Download `SWC-Studio-v0.2.0-macOS.zip` or `SWC-Studio-v0.2.0-Windows.zip`
3. Extract and launch:
   - **macOS** — drag `SWC-Studio.app` into `/Applications`, then double-click. First launch needs `xattr -cr /Applications/SWC-Studio.app` or right-click → Open (the bundle is not yet code-signed).
   - **Windows** — extract anywhere and run the `.exe` inside.

Models are bundled inside the app — no separate download.

### Option 2 — Researcher, `pip install` (recommended for scripted workflows)

The Python package is published on PyPI:

```bash
pip install swcstudio
swcstudio-gui          # launch the desktop GUI
swcstudio --help       # CLI
```

Requires Python 3.10+ already installed on your system. The wheel itself is small (~300 KB); the heavy dependencies (PyTorch, PySide6, vispy, etc.) come along automatically. Models are downloaded on the first auto-label call (~21 MB, one-time, cached locally).

For a clean isolated install:

```bash
python3 -m venv ~/swcstudio-env
source ~/swcstudio-env/bin/activate     # Windows: ~\swcstudio-env\Scripts\Activate.ps1
pip install swcstudio
swcstudio-gui
```

To upgrade later: `pip install --upgrade swcstudio`.

### Option 3 — Developer, install from source

Use this path if you want to modify the swcstudio code itself. Supported Python versions: 3.10, 3.11, 3.12, 3.13.

```bash
git clone https://github.com/Mio0v0/SWC-Studio.git
cd SWC-Studio
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
swcstudio-gui
```

**Windows PowerShell:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
swcstudio-gui
```

`pip install -e .` pulls in everything (CLI + GUI + auto-typing engine). The `-e` ("editable") flag means edits to your local `.py` files take effect on the next `python` run — useful for development. Maintainers who also need PyInstaller (release packaging) and Sphinx (docs build) can use `pip install -e ".[all]"`.

### Verifying the install

```bash
swcstudio --help
swcstudio models status     # confirm the auto-typing models are reachable
```

If the console scripts aren't on your path, fall back to module mode:

```bash
python -m swcstudio.cli.cli --help
python -m swcstudio.gui.main
```

## Updates

How you update depends on how you installed:

| Install method | How to update |
|---|---|
| **Option 1** (bundled app) | Help → **Check for Updates** in the GUI. The in-app updater downloads only the changed layer (~5 MB code or ~21 MB models), no full re-download required. |
| **Option 2** (pip) | `pip install --upgrade swcstudio` — pip downloads only what changed. Models auto-refresh on next auto-label call if a new version is available. |
| **Option 3** (source) | `git pull` followed by `pip install -e .` to pick up any new dependencies. |

Under the hood, releases are split into three independently-updatable layers — runtime (heavy libraries), code (`swcstudio/` package), and models — so most updates touch only the small layers. See [`packaging/MODULAR_BUILD.md`](packaging/MODULAR_BUILD.md) for the architecture and [`RELEASE.md`](RELEASE.md) for the release pipeline.

## Core Capabilities

- issue-driven SWC validation and repair
- batch processing workflows
- v9 ML auto-typing engine: Stage 1 cell-type detector + Stage 2 per-subtree classifier + Stage 2b GraphSAGE GNN apical-vs-basal head + Stage 3 topology refinement, with bundled trained models
- automatic apical detection (3-class vs 4-class output chosen per file)
- one-command retraining of the engine on user data (`swcstudio train auto-typing`)
- radii cleaning
- manual morphology and geometry editing
- shared GUI, CLI, and Python integration surface

## Train your own auto-typing models

If you want models tuned to your own SWCs, the toolkit ships a one-command trainer:

```bash
swcstudio train auto-typing \
    --data-dir path/to/labeled/dataset \
    --output-dir path/to/save/models
```

The dataset directory must have `pyramidal/` and `interneuron/` subfolders of labeled `.swc` files (each SWC's `type` column is the per-node ground truth).

To use the trained models afterwards:

```bash
# One-off: pass --model-dir per call
swcstudio auto-label cell.swc --model-dir path/to/save/models

# Or set the env var for the whole shell
export SWCSTUDIO_MODEL_DIR=path/to/save/models      # macOS/Linux
$env:SWCSTUDIO_MODEL_DIR = "path\to\save\models"    # Windows PowerShell

# Or make them the persistent default by copying into the user data dir;
# see the docs site for the per-platform path.
```

See the [Auto-Typing Engine](https://mio0v0.github.io/SWC-Studio/documentation/auto-typing-backends.html) page in the docs for the full retraining workflow, hyperparameter flags, and model resolution rules.

## Recommended Workflow

1. Open one SWC file in the GUI.
2. Run validation and review the issue list.
3. Apply the suggested repairs.
4. Rerun validation.
5. Save or export the cleaned result.

## License

Released under the MIT License. See `LICENSE`.
