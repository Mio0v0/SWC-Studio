# SWC-Studio

`SWC-Studio` is a desktop, CLI, and Python toolkit for working with neuron morphology files in SWC format.

It is designed for inspecting reconstructions, finding structural or annotation problems, repairing them, and running repeatable morphology-processing workflows from one shared backend.

## Project Overview

`SWC-Studio` includes:

- a shared Python backend (`swcstudio`)
- a command-line interface (`swcstudio`)
- a desktop GUI (`swcstudio-gui`)

Both the CLI and GUI use the same core feature logic.

## Documentation

Canonical project documentation lives on the docs website:

- Live docs: [https://mio0v0.github.io/SWC-Studio/](https://mio0v0.github.io/SWC-Studio/)
- All releases: [https://github.com/Mio0v0/SWC-Studio/releases](https://github.com/Mio0v0/SWC-Studio/releases)

Use the docs site for:

- installation and getting started
- GUI and CLI workflows
- validation, repair, and reporting behavior
- tutorials
- API and extension references

## Quick Start

Option 1: download a packaged executable from the GitHub Releases page and run the app directly.

- macOS: [SWC-Studio v0.1.0 for macOS](https://github.com/Mio0v0/SWC-Studio/releases/download/v0.1.0/SWC-Studio.v0.1.0.macOS.zip)
- Windows: [SWC-Studio v0.1.0 for Windows](https://github.com/Mio0v0/SWC-Studio/releases/download/v0.1.0/SWC-Studio.v0.1.0.Windows.zip)
- Download the zip for your platform, extract it, and launch the included application

Option 2: install from source:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[gui]"
swcstudio-gui
```

CLI help:

```bash
swcstudio --help
```

## Core Capabilities

- issue-driven SWC validation and repair
- batch processing workflows
- rule-based auto typing
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
