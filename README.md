# SWC-Studio

`SWC-Studio` is a desktop and command-line workbench for working with neuron morphology files in SWC format. At a high level, it is meant to help researchers inspect reconstructions, find structural or annotation problems, repair them, and run repeatable morphology-processing workflows from the same shared backend.

`SWC-Studio` is a modular SWC morphology toolkit (Python package: `swcstudio`) with:

- a shared Python backend (`swcstudio/core` + `swcstudio/tools`)
- a CLI (`swcstudio`)
- a desktop GUI (`swcstudio-gui`)

CLI and GUI call the same feature backend functions.

There are two main ways to use `SWC-Studio`. If you want the full Python workflow, you can create a virtual environment and install it with `pip`, which gives you the shared library, CLI, and GUI together. If you just want to use it as desktop software, you can download a packaged executable `.zip` release, extract it, and run the desktop application directly without setting up a Python environment.

## Documentation

Short docs (Markdown):

- [Docs Overview](docs/README.md): reading order and page ownership
- [Getting Started](docs/GETTING_STARTED.md): install, run, first steps
- [GUI Workflow Guide](docs/GUI_WORKFLOW.md): current GUI layout and issue-driven flow
- [CLI Reference](docs/CLI_REFERENCE.md): current command surface
- [Checks And Issues Reference](docs/CHECKS_AND_ISSUES_REFERENCE.md): canonical checks, issues, and algorithms
- [Logs And Reports](docs/LOGS_AND_REPORTS.md): report names, session logs, and output folders
- [API / Library Documentation](docs/API_DOCUMENTATION.md): Python integration surface

Comprehensive docs site (Sphinx source):

- Live docs: `https://mio0v0.github.io/SWC-Studio/`
- includes tutorials, architecture, logs/reporting, plugin development, and auto-generated API/module references

## What This Project Does

Top-level tool areas:

1. Batch Processing
2. Validation
3. Visualization
4. Morphology Editing
5. Geometry Editing

Core workflows currently include:

- SWC split by soma-root trees
- Batch simplification
- Batch index clean
- Rule-based auto typing
- Single-file and batch validation
- Validation index clean
- Radius outlier cleaning
- Manual single-node radius editing
- Dendrogram subtree type reassignment
- Simplification (graph-aware RDP)
- Geometry editing operations for move/connect/disconnect/delete/insert

Current auto-labeling is directed-path and subtree-consistent:

- primary soma-child subtrees are scored as axon, basal, or apical
- one primary axon winner and one primary apical winner can be enforced
- labels inherit root-to-leaf within a classified primary subtree
- path persistence, terminal taper, branch structure, and +Z alignment are used in the scores
- distant branches are penalized as basal candidates

Current radii cleaning is three-pass and path-aware:

- pass 1: local median outlier repair on a 5-node neighborhood
- pass 2: monotonic taper enforcement away from the soma with a small slack
- pass 3: Savitzky-Golay-style local polynomial smoothing
- axons can keep a configurable biological minimum floor

## Recommended App Workflow

`SWC-Studio` is built around an issue-driven repair workflow for one SWC at a time:

1. Open an SWC file in the GUI.
2. Run Validation and review the Issue Navigator on the left.
3. Click an issue to focus the affected nodes and jump to the most relevant fix tool.
4. Fix the issue in the suggested feature, such as Validation, Index Clean, Manual Label Editing, Auto Label Editing, Manual Radii Editing, Auto Radii Editing, or Geometry Editing.
5. Rerun validation and continue until the important issues are resolved.
6. Save the cleaned SWC for batch processing, export, or further editing.

The intended app flow is:

- issues are surfaced in the navigator
- each issue directs you to the corresponding repair tool
- fixes are applied on the current SWC
- once the issue list is resolved or reduced to acceptable warnings, the SWC is ready for export or downstream workflows


## Install

## Prerequisites

- Python 3.10+ (Windows strongly recommended: Python 3.11)
- `pip` (bundled with modern Python)
- `git` (to clone the repository)
- Optional: `conda`/`mamba` if you prefer conda environments

## Install Method Notes

Using a virtual environment is highly recommended (venv or conda), but not required.
You can install into a base interpreter if needed.

- `pip install -e ".[gui]"`: editable install for local development/testing
- `pip install -e ".[gui,build]"`: editable install with macOS packaging tools
- `pip install -r requirements.txt`: full top-level setup (core + GUI + docs + build)

macOS/Linux (GUI + CLI):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[gui]"
```

Windows PowerShell (GUI + CLI, stricter setup):

```powershell
Requires Python 3.10 or newer.

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -e ".[gui]"
```

Windows cmd (GUI + CLI, stricter setup):

```bat
Requires Python 3.10 or newer.

py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -e ".[gui]"
```

Conda (all OS, GUI + CLI):

```bash
conda create -n swc-studio python=3.11 -y
conda activate swc-studio
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -e ".[gui]"
```

CLI-only install (all OS, with venv active):

```bash
python -m pip install -e .
```

Build dependencies for packaging are defined in `pyproject.toml` under the `build` extra.

## Run

CLI (all OS):

```bash
swcstudio --help
```

If `swcstudio` is not on PATH, use module mode:

macOS/Linux:

```bash
python -m swcstudio.cli.cli --help
```

Windows (PowerShell/cmd):

```powershell
py -m swcstudio.cli.cli --help
```

GUI (all OS):

```bash
swcstudio-gui
```

Fallback module mode:

macOS/Linux:

```bash
python -m swcstudio.gui.main
```

Windows (PowerShell/cmd):

```powershell
py -m swcstudio.gui.main
```

## Quick CLI Examples

macOS/Linux:

```bash
swcstudio batch split ./data
swcstudio batch validate ./data
swcstudio batch auto-typing ./data --soma --axon --basal
swcstudio batch radii-clean ./data
swcstudio batch simplify ./data
swcstudio batch index-clean ./data

swcstudio check ./data/single-soma.swc
swcstudio validation rule-guide
swcstudio validation run ./data/single-soma.swc
swcstudio validation auto-fix ./data/single-soma.swc --write
swcstudio validation index-clean ./data/single-soma.swc --write

swcstudio morphology set-radius ./data/single-soma.swc --node-id 42 --radius 0.75 --write
swcstudio geometry simplify ./data/single-soma.swc --write
swcstudio geometry connect ./data/single-soma.swc --start-id 10 --end-id 22 --write

swcstudio plugins load my_lab_plugins.summary_plugin
swcstudio plugins list-loaded
```

Windows (PowerShell/cmd):

```powershell
swcstudio batch split .\data
swcstudio batch validate .\data
swcstudio batch auto-typing .\data --soma --axon --basal
swcstudio batch radii-clean .\data
swcstudio batch simplify .\data
swcstudio batch index-clean .\data

swcstudio check .\data\single-soma.swc
swcstudio validation rule-guide
swcstudio validation run .\data\single-soma.swc
swcstudio validation auto-fix .\data\single-soma.swc --write
swcstudio validation index-clean .\data\single-soma.swc --write

swcstudio morphology set-radius .\data\single-soma.swc --node-id 42 --radius 0.75 --write
swcstudio geometry simplify .\data\single-soma.swc --write
swcstudio geometry connect .\data\single-soma.swc --start-id 10 --end-id 22 --write

swcstudio plugins load my_lab_plugins.summary_plugin
swcstudio plugins list-loaded
```

## macOS Packaging

Reproducible macOS GUI packaging files are tracked in:

- `packaging/swcstudio_gui.spec`
- `packaging/build_macos.sh`
- `packaging/README.md`

Build from a clean macOS environment with:

```bash
./packaging/build_macos.sh
```

This uses the `build` extra from `pyproject.toml` and outputs:

- `dist/SWC-Studio.app`

Keep in git:

- packaging scripts
- packaging docs
- `*.spec` files

Do not keep in git:

- `build/`
- `dist/`
- generated `.app`, `.dmg`, `.pkg`, and `.zip` artifacts

See also:

- `packaging/README.md`
- `docs/MACOS_PACKAGING.md`


## Architecture (High-Level)

- `swcstudio/core`: shared data models, IO, validation/rules, reporting
- `swcstudio/tools`: tool/feature backends (actual behavior)
- `swcstudio/plugins`: registry for builtin + user override methods
- `swcstudio/cli`: terminal interface layer
- `swcstudio/gui`: Qt interface layer

## Config

Feature config JSON lives at:

- `swcstudio/tools/<tool>/configs/<feature>.json`

Examples:

- `swcstudio/tools/validation/configs/default.json`
- `swcstudio/tools/batch_processing/configs/radii_cleaning.json`
- `swcstudio/tools/morphology_editing/configs/simplification.json`

## Notes

- JSON controls parameters and method selection.
- Algorithm/data transformation logic stays in Python.
- No web/server/API service layer is included.

## License

This project is released under the MIT License. See `LICENSE`.

## Plugin Contract (For Many External Plugins)

`swcstudio` supports plugin modules through a small versioned contract:

1. `PLUGIN_MANIFEST` (or `get_plugin_manifest()`) must provide:
   - `plugin_id`, `name`, `version`, `api_version`
   - optional `description`, `author`, `capabilities`
2. Plugin module must provide either:
   - `register_plugin(registrar)` function, or
   - `PLUGIN_METHODS` dictionary/list
3. Plugin methods register against existing feature keys, e.g.:
   - `batch_processing.auto_typing`
   - `analysis.summary`

This lets you integrate external libraries or lab-specific methods without
rewriting the app’s interface layer.

For automatic plugin loading in CLI sessions:

macOS/Linux:

```bash
export SWCSTUDIO_PLUGINS="my_lab_plugins.summary_plugin,my_lab_plugins.custom_methods"
```

Windows PowerShell:

```powershell
$env:SWCSTUDIO_PLUGINS = "my_lab_plugins.summary_plugin,my_lab_plugins.custom_methods"
```

Windows cmd:

```bat
set SWCSTUDIO_PLUGINS=my_lab_plugins.summary_plugin,my_lab_plugins.custom_methods
```

Starter template:

- `examples/plugins/summary_plugin_template.py`
