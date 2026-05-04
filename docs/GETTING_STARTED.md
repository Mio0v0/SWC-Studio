# Getting Started

This guide gets a new user to a working `SWC-Studio` install and a first successful run.

## Installation paths

There are two supported ways to start:

- use a packaged desktop release from GitHub Releases
- install from source if you want the Python package, CLI, or a development setup

## Supported Python versions

Source installs support **Python 3.10, 3.11, 3.12, and 3.13**.

Python 3.11 or 3.12 is the safest default. PyTorch occasionally lags
on the newest Python release, so if you hit a wheel resolution problem
on 3.13 fall back to 3.12.

## Packaged desktop release

Use this path if you only need the desktop application:

1. download the release archive for your platform
2. extract it
3. launch the included application

Release page:

- <https://github.com/Mio0v0/SWC-Studio/releases>

## Source install

Clone the repository:

```bash
git clone https://github.com/Mio0v0/SWC-Studio.git
cd SWC-Studio
```

One command installs everything — the CLI, the desktop GUI, the
auto-typing engine (sklearn + torch), and the bundled v9 model files:

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
three bundled model files are reachable. You should see all three of
`cell_type_classifier.pkl`, `branch_classifier.pkl`, and
`gnn_apical_basal.pt` listed as `[FOUND]`.

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

`auto-label` always applies soma / axon / basal labeling and
automatically enables apical labeling only when an apical subtree is
detected.

## Train your own auto-typing models (optional)

The bundled models work out of the box, but if you want models tuned
to your own labeled SWC corpus:

```bash
swcstudio train auto-typing --data-dir ./labeled-dataset --output-dir ./my-models
```

The dataset must have `pyramidal/` and `interneuron/` subfolders of
labeled `.swc` files. To make your trained models the new default,
copy them into your user data dir (Windows: `%APPDATA%\swcstudio\models`,
macOS: `~/Library/Application Support/swcstudio/models`, Linux:
`~/.local/share/swcstudio/models`) — every CLI/GUI call will use them
automatically.

See the [Auto-Typing Engine](documentation/auto-typing-backends.md) page
for the full retraining workflow, hyperparameter flags, and model
resolution rules.

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
