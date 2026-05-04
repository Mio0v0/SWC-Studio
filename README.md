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

Auto-labeling uses a single ML pipeline: the **v9 engine**. It runs a four-stage process — cell-type detection, per-subtree axon/basal/apical classification, an optional GraphSAGE GNN apical-vs-basal re-decision, and topology refinement — and automatically chooses between 3-class (no apical) and 4-class output per file.

The toolkit ships with bundled trained models. After `pip install -e .` the engine works out of the box; users can also retrain on their own labeled SWC corpus via `swcstudio train auto-typing` and have the toolkit pick up the new models automatically.

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

Current GitHub Releases may include:

- macOS application bundle
- Windows executable package

## Quick Start

Option 1: download a packaged executable from the GitHub Releases page and run the app directly.

- macOS: [SWC-Studio v0.1.0 for macOS](https://github.com/Mio0v0/SWC-Studio/releases/download/v0.1.0/SWC-Studio.v0.1.0.macOS.zip)
- Windows: [SWC-Studio v0.1.0 for Windows](https://github.com/Mio0v0/SWC-Studio/releases/download/v0.1.0/SWC-Studio.v0.1.0.Windows.zip)
- Download the zip for your platform, extract it, and launch the included application

Option 2: install from source. Supported Python versions: 3.10, 3.11, 3.12, 3.13.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
swcstudio-gui
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
swcstudio-gui
```

A single `pip install -e .` pulls in everything: the CLI, the desktop GUI, the auto-typing engine (sklearn + torch + torch_geometric), and the bundled v9 model files. There are no extras to remember for normal use. Maintainers who need PyInstaller and Sphinx for release packaging and docs builds can use `pip install -e ".[all]"`.

CLI help:

```bash
swcstudio --help
swcstudio models status     # confirm the bundled auto-typing models are reachable
```

If the script entry point is not on your path, fall back to module mode:

```bash
python -m swcstudio.cli.cli --help
python -m swcstudio.gui.main
```

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
