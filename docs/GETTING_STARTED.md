# Getting Started

This guide gets a new user to a working `SWC-Studio` install and a first successful run.

## Installation paths

There are two supported ways to start:

- use a packaged desktop release from GitHub Releases
- install from source if you want the Python package, CLI, or a development setup

## Supported Python versions

Source installs currently support:

- Python 3.10
- Python 3.11
- Python 3.12

Python 3.11 is the safest default for most users.

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
git clone <your-repo-url>
cd <repo-folder-name>
```

### Conda

```bash
conda create -n swc-studio python=3.11 -y
conda activate swc-studio
python -m pip install --upgrade pip
pip install -e ".[gui]"
```

### venv on macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[gui]"
```

### venv on Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[gui]"
```

### CLI-only install

```bash
python -m pip install -e .
```

## Verify installation

For a source install:

```bash
swcstudio --help
swcstudio-gui --help
```

If the console script is not on your path, use module mode:

```bash
python -m swcstudio.cli.cli --help
python -m swcstudio.gui.main
```

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

Single-file edit commands write both the updated SWC and the matching log into the source file's default output directory. No separate `--write` flag is required. Auto-label always applies soma/axon/basal labeling and automatically enables apical labeling only when an apical subtree is detected.

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
- [GUI Workflow Guide](GUI_WORKFLOW.md)
- [CLI Tutorial](tutorials/cli-tutorial.md)
- [Logs And Reports](LOGS_AND_REPORTS.md)
