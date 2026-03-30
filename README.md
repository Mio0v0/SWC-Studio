# SWC-Studio

`SWC-Studio` is a desktop and command-line workbench for working with neuron morphology files in SWC format. At a high level, it is meant to help researchers inspect reconstructions, find structural or annotation problems, repair them, and run repeatable morphology-processing workflows from the same shared backend.

`SWC-Studio` is a modular SWC morphology toolkit (Python package: `swctools`) with:

- a shared Python backend (`swctools/core` + `swctools/tools`)
- a CLI (`swctools`)
- a desktop GUI (`swctools-gui`)

CLI and GUI call the same feature backend functions.

There are two main ways to use `SWC-Studio`. If you want the full Python workflow, you can create a virtual environment and install it with `pip`, which gives you the shared library, CLI, and GUI together. If you just want to use it as desktop software, you can download a packaged executable `.zip` release, extract it, and run the desktop application directly without setting up a Python environment.

## What This Project Does

Top-level tool areas:

1. Batch Processing
2. Validation
3. Visualization
4. Morphology Editing
5. Geometry Editing
6. Atlas Registration (placeholder)
7. Analysis (placeholder)

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

## Recommended App Workflow

`SWC-Studio` is built around an issue-driven repair workflow for one SWC at a time:

1. Open an SWC file in the GUI.
2. Run Validation and review the Issue Navigator on the left.
3. Click an issue to focus the affected nodes and jump to the most relevant fix tool.
4. Fix the issue in the suggested feature, such as Validation, Index Clean, Manual Label Editing, Auto Label Editing, Manual Radii Editing, Auto Radii Editing, or Geometry Editing.
5. Rerun validation and continue until the important issues are resolved.
6. Save the cleaned SWC for downstream analysis, batch processing, or further editing.

The intended app flow is:

- issues are surfaced in the navigator
- each issue directs you to the corresponding repair tool
- fixes are applied on the current SWC
- once the issue list is resolved or reduced to acceptable warnings, the SWC is ready for downstream analysis and editing

## Documentation

Short docs (Markdown):

- [CLI Reference](docs/CLI_REFERENCE.md): command reference and options
- [GUI Workflow Guide](docs/GUI_WORKFLOW.md): current GUI layout, tool/feature structure, and issue-driven usage flow
- [API / Library Documentation](docs/API_DOCUMENTATION.md): Python API surface
- [Plugin Demonstration](docs/PLUGIN_DEMONSTRATION.md): lab handoff plugin workflow
- [Checks And Issues Reference](docs/CHECKS_AND_ISSUES_REFERENCE.md): validation checks, issue types, algorithms, and parameters

Comprehensive docs site (Sphinx source):

- Live docs: `https://mio0v0.github.io/SWC-Studio/`
- includes tutorials, architecture, logs/reporting, plugin development, and auto-generated API/module references

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
swctools --help
```

If `swctools` is not on PATH, use module mode:

macOS/Linux:

```bash
python -m swctools.cli.cli --help
```

Windows (PowerShell/cmd):

```powershell
py -m swctools.cli.cli --help
```

GUI (all OS):

```bash
swctools-gui
```

Fallback module mode:

macOS/Linux:

```bash
python -m swctools.gui.main
```

Windows (PowerShell/cmd):

```powershell
py -m swctools.gui.main
```

## Quick CLI Examples

macOS/Linux:

```bash
swctools batch split ./data
swctools batch validate ./data
swctools batch auto-typing ./data --soma --axon --basal
swctools batch radii-clean ./data
swctools batch simplify ./data
swctools batch index-clean ./data

swctools validation rule-guide
swctools validation run ./data/single-soma.swc
swctools validation auto-fix ./data/single-soma.swc --write
swctools validation index-clean ./data/single-soma.swc --write

swctools morphology simplify ./data/single-soma.swc --write
swctools morphology set-radius ./data/single-soma.swc --node-id 42 --radius 0.75 --write
swctools geometry connect ./data/single-soma.swc --start-id 10 --end-id 22 --write

swctools plugins load my_lab_plugins.brainglobe_adapter
swctools plugins list-loaded
```

Windows (PowerShell/cmd):

```powershell
swctools batch split .\data
swctools batch validate .\data
swctools batch auto-typing .\data --soma --axon --basal
swctools batch radii-clean .\data
swctools batch simplify .\data
swctools batch index-clean .\data

swctools validation rule-guide
swctools validation run .\data\single-soma.swc
swctools validation auto-fix .\data\single-soma.swc --write
swctools validation index-clean .\data\single-soma.swc --write

swctools morphology simplify .\data\single-soma.swc --write
swctools morphology set-radius .\data\single-soma.swc --node-id 42 --radius 0.75 --write
swctools geometry connect .\data\single-soma.swc --start-id 10 --end-id 22 --write

swctools plugins load my_lab_plugins.brainglobe_adapter
swctools plugins list-loaded
```

## macOS Packaging

Reproducible macOS GUI packaging files are tracked in:

- `packaging/swctools_gui.spec`
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

- `swctools/core`: shared data models, IO, validation/rules, reporting
- `swctools/tools`: tool/feature backends (actual behavior)
- `swctools/plugins`: registry for builtin + user override methods
- `swctools/cli`: terminal interface layer
- `swctools/gui`: Qt interface layer

## Config

Feature config JSON lives at:

- `swctools/tools/<tool>/configs/<feature>.json`

Examples:

- `swctools/tools/validation/configs/default.json`
- `swctools/tools/batch_processing/configs/radii_cleaning.json`
- `swctools/tools/morphology_editing/configs/simplification.json`

## Notes

- JSON controls parameters and method selection.
- Algorithm/data transformation logic stays in Python.
- No web/server/API service layer is included.

## License

This project is released under the MIT License. See `LICENSE`.

## Plugin Contract (For Many External Plugins)

`swctools` supports plugin modules through a small versioned contract:

1. `PLUGIN_MANIFEST` (or `get_plugin_manifest()`) must provide:
   - `plugin_id`, `name`, `version`, `api_version`
   - optional `description`, `author`, `capabilities`
2. Plugin module must provide either:
   - `register_plugin(registrar)` function, or
   - `PLUGIN_METHODS` dictionary/list
3. Plugin methods register against existing feature keys, e.g.:
   - `batch_processing.auto_typing`
   - `atlas_registration.registration`

This lets you integrate external libraries (like BrainGlobe adapters) without
rewriting their internal algorithms.

For automatic plugin loading in CLI sessions:

macOS/Linux:

```bash
export SWCTOOLS_PLUGINS="my_lab_plugins.brainglobe_adapter,my_lab_plugins.custom_methods"
```

Windows PowerShell:

```powershell
$env:SWCTOOLS_PLUGINS = "my_lab_plugins.brainglobe_adapter,my_lab_plugins.custom_methods"
```

Windows cmd:

```bat
set SWCTOOLS_PLUGINS=my_lab_plugins.brainglobe_adapter,my_lab_plugins.custom_methods
```

Starter template:

- `examples/plugins/brainglobe_adapter_template.py`
