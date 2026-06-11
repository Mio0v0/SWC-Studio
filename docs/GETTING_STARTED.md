# Getting Started

This guide gets a new user to a working `SWC-Studio` install and a first successful run.

## Installation paths

There are three supported ways to install:

| Method | Best for | Models bundled? |
|---|---|---|
| **Option 1 — bundled desktop app** | end users who want a double-clickable application | yes, inside the app |
| **Option 2 — `pip install swcstudio`** | researchers using SWC-Studio in scripts / Python | no, downloaded on first auto-label call |
| **Option 3 — install from source** | developers who want to modify the code itself | yes, in the local checkout |

## Supported Python versions

Options 2 and 3 require **Python 3.10, 3.11, 3.12, or 3.13** already installed on your system.

Python 3.11 or 3.12 is the safest default. PyTorch occasionally lags
on the newest Python release, so if you hit a wheel resolution problem
on 3.13 fall back to 3.12.

Option 1 (the bundled app) ships its own Python runtime — no separate Python install needed.

## Option 1 — Bundled desktop app

Use this path if you only need the desktop application and don't want to deal with Python.

1. open <https://github.com/Mio0v0/SWC-Studio/releases/latest>
2. download `SWC-Studio-vX.Y.Z-macOS.zip` (Mac) or `SWC-Studio-vX.Y.Z-Windows.zip` (Windows)
3. extract and launch:
   - **macOS** — drag `SWC-Studio.app` into `/Applications`, then double-click. First launch may need `xattr -cr /Applications/SWC-Studio.app` (or right-click → Open) because the bundle is not yet code-signed.
   - **Windows** — extract anywhere, run the `.exe` inside.

The auto-typing models are bundled inside the app, so the first auto-label
call works without any download.

## Option 2 — `pip install` from PyPI

Use this path for scripts, Jupyter notebooks, batch processing, or any Python
workflow. The Python package is published on PyPI:

```bash
pip install swcstudio
```

The wheel itself is tiny (~300 KB code only); the heavy dependencies
(PyTorch, PySide6, vispy, sklearn, etc.) are pulled in by pip. The
auto-typing models are **downloaded on first use** (~80 MB, one-time)
and cached at:

- macOS: `~/Library/Application Support/swcstudio/models/`
- Windows: `%APPDATA%\swcstudio\models\`
- Linux: `~/.local/share/swcstudio/models/`

A clean isolated install (recommended over polluting system Python):

```bash
python3 -m venv ~/swcstudio-env
source ~/swcstudio-env/bin/activate           # Windows: ~\swcstudio-env\Scripts\Activate.ps1
pip install swcstudio

swcstudio-gui                                 # launch the GUI
swcstudio --help                              # CLI
```

To upgrade later: `pip install --upgrade swcstudio`. Pip downloads only
what changed; models refresh automatically on the next auto-label call
if their version bumped.

## Option 3 — Source install (development)

Use this path if you want to modify the swcstudio code itself. The `-e`
flag installs in **editable** mode, meaning edits to local `.py` files
take effect on the next `python` run — no reinstall needed.

Clone the repository:

```bash
git clone https://github.com/Mio0v0/SWC-Studio.git
cd SWC-Studio
```

One command installs everything — the CLI, the desktop GUI, the
auto-typing engine (sklearn + torch + torch_geometric), and the
bundled model files:

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

### Conda

```bash
conda create -n swc-studio python=3.12 -y
conda activate swc-studio
python -m pip install --upgrade pip
pip install -e .
```

### Optional developer extras

For maintainers who need PyInstaller (release packaging) and Sphinx
(docs build):

```bash
pip install -e ".[all]"
```

End users do not need this.

## Updating

How you update depends on how you installed:

| Install method | How to update |
|---|---|
| Option 1 (bundled app) | Help → **Check for Updates** in the GUI. The in-app updater downloads only the changed layer (~5 MB code or ~80 MB models), no full re-download. |
| Option 2 (pip) | `pip install --upgrade swcstudio`. Pip downloads only what changed; models refresh on next auto-label call if a new version is available. |
| Option 3 (source) | `git pull` followed by `pip install -e .` to pick up any new dependencies. |

Internally, each release is split into three independent layers — runtime,
code, and models — so most updates only re-fetch the small ones. See
[`packaging/MODULAR_BUILD.md`](https://github.com/Mio0v0/SWC-Studio/blob/main/packaging/MODULAR_BUILD.md)
for the architecture details.

## Verify installation

```bash
swcstudio --help
swcstudio models status
swcstudio-gui --help
```

If a console script is not on your path, fall back to module mode:

```bash
python -m swcstudio.cli.cli --help
python -m swcstudio.gui.main
```

`swcstudio models status` is worth running once after install: it
prints the auto-typing engine's model search path and confirms the
bundled v12 model files are reachable. You should see the core files
`cell_type_classifier.pkl`, `branch_classifier.pkl`,
`gnn_apical_basal.pt`, `gnn_branch3_rescue.pt`, and `qc_gate.pkl`
listed as `[FOUND]`, plus flag model paths when flag scoring is bundled.

## First CLI checks

Start with a read-only inspection command:

```bash
swcstudio check ./data/single-soma.swc
swcstudio validate ./data/single-soma.swc
```

Then try an edit command:

```bash
swcstudio auto-label ./data/single-soma.swc
swcstudio set-type ./data/single-soma.swc --node-id 14169 --new-type 3
swcstudio simplify ./data/single-soma.swc
swcstudio connect ./data/single-soma.swc --start-id 10 --end-id 22
```

Single-file edit commands write both the updated SWC and the matching
log into the source file's default output directory. No separate
`--write` flag is required.

`auto-label` always applies soma / axon / basal labeling, detects apical
labels when appropriate, and can flag cells whose predicted labels look
unreliable. Use `--cell-type pyramidal` or `--cell-type interneuron`
when you already know the cell type; leave it unknown to run Stage 1.

## First GUI checks

Launch the GUI:

```bash
swcstudio-gui
```

Then:

1. open an SWC file
2. review the automatically generated issue list
3. select an issue and let the app route you to the matching repair tool
4. save or close the file to write the session log and saved copy

## Default outputs

For a source file:

- `<folder>/<stem>.swc`

the default single-file output directory is:

- `<folder>/<stem>_swc_studio_output/`

Typical files written there include:

- validation reports
- edited SWC copies
- per-operation logs
- GUI session logs
- GUI saved copies

## Recommended next pages

- [User Guide](documentation/index.md)
- [Auto-Typing Engine](documentation/auto-typing-backends.md)
- [GUI Workflow Guide](GUI_WORKFLOW.md)
- [CLI Tutorial](tutorials/cli-tutorial.md)
- [Logs And Reports](LOGS_AND_REPORTS.md)
