# SWC-Studio

`SWC-Studio` is a desktop, CLI, and Python toolkit for working with neuron morphology files in SWC format.

It is designed for inspecting reconstructions, finding structural or annotation problems, repairing them, and running repeatable morphology-processing workflows from one shared backend.

## Project Overview

`SWC-Studio` includes:

- a shared Python backend (`swcstudio`)
- a command-line interface (`swcstudio`)
- a desktop GUI (`swcstudio-gui`)

Both the CLI and GUI use the same core feature logic. Auto-labeling now always runs soma/axon/basal labeling and automatically switches between 3-class and 4-class output by detecting whether an apical subtree is present.

## Documentation

Project documentation lives on the docs website:

- Live docs: [https://mio0v0.github.io/SWC-Studio/](https://mio0v0.github.io/SWC-Studio/)
- All releases: [https://github.com/Mio0v0/SWC-Studio/releases](https://github.com/Mio0v0/SWC-Studio/releases)

Use the docs site for:

- installation and getting started
- GUI and CLI workflows
- validation, repair, and reporting behavior
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

Option 2: install from source.

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[gui]"
swcstudio-gui
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[gui]"
swcstudio-gui
```

Windows cmd:

```bat
py -m venv .venv
.venv\Scripts\activate.bat
pip install -e ".[gui]"
swcstudio-gui
```

CLI help:

macOS/Linux:

```bash
swcstudio --help
# fallback:
python -m swcstudio.cli.cli --help
```

Windows PowerShell or cmd:

```powershell
swcstudio --help
# fallback:
py -m swcstudio.cli.cli --help
```

## Core Capabilities

- issue-driven SWC validation and repair
- batch processing workflows
- rule-based auto typing with automatic apical detection
- radii cleaning
- manual morphology and geometry editing
- shared GUI, CLI, and Python integration surface

## Recommended Workflow

1. Open one SWC file in the GUI.
2. Run validation and review the issue list.
3. Apply the suggested repairs.
4. Rerun validation.
5. Save or export the cleaned result.

## License

Released under the MIT License. See `LICENSE`.
