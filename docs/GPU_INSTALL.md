# GPU Setup

SWC-Studio supports three installation styles:

- one-click executable from GitHub Releases
- `pip install swcstudio`
- source install from a cloned repository

The recommended one-click executable is the universal CPU build. It
bundles Python, the GUI stack, scientific packages, and the trained
models so it can run directly without asking users to manage CUDA.

GPU acceleration is intended for pip/source installs, where advanced
users can choose the PyTorch/CUDA stack that matches their own NVIDIA
driver and Python version.

## Check GPU Readiness

From the GUI:

1. Open SWC-Studio.
2. Choose Help -> GPU Readiness.

From the CLI:

```bash
swcstudio gpu-status
swcstudio gpu-status --json
```

The checker reports:

- whether PyTorch imports
- whether the installed PyTorch build includes CUDA
- whether `torch.cuda.is_available()` can see a CUDA device
- whether PyTorch Geometric imports
- whether `nvidia-smi` is available
- what is missing for GPU mode

CPU auto-labeling still works when GPU mode is not ready.

## Install GPU Dependencies

Use a pip or source environment for GPU mode:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -e .
```

Then install the CUDA-enabled PyTorch build recommended by the official
PyTorch selector:

<https://pytorch.org/get-started/locally/>

Install PyTorch Geometric for the same PyTorch/CUDA stack:

<https://pytorch-geometric.readthedocs.io/en/2.6.1/install/installation.html>

Finally verify:

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
python -c "import torch_geometric; print(torch_geometric.__version__)"
swcstudio gpu-status
```

## Why The Executable Is CPU By Default

A normal one-click executable uses its own bundled Python environment,
not the user's external Python environment. Even if a user has GPU
PyTorch installed elsewhere, the executable usually cannot see it.

To make a GPU executable work without extra setup, the build has to
bundle one compatible CUDA/PyTorch stack. That makes the file much
larger and still does not cover every driver/CUDA combination. Keeping
the executable CPU-only gives the most portable download, while pip and
source installs remain flexible for GPU users.
