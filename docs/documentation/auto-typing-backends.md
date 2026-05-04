# Auto-Typing Engine

`SWC-Studio`'s auto-labeling is a single ML engine: the **v9 hybrid
pipeline**. It runs everywhere — the CLI, both Auto Label Editing GUI
panels, and the Python API call into the same code. There is no
backend switch; the engine is the engine.

## What the engine does

Four stages run in order on every SWC:

| Stage | Purpose | Implementation |
|---|---|---|
| Stage 1 | Cell-type detection (pyramidal vs interneuron) | sklearn ensemble over 49 whole-cell features. A soft handoff runs Stage 2+3 for both cell types when confidence is below threshold and picks the higher-confidence outcome. |
| Stage 2 | Per-subtree classification (axon / basal / apical) | sklearn ensemble. Labels are propagated to all branches in the same primary subtree — no mid-track type switches. |
| Stage 2b | Apical-vs-basal re-decision on pyramidal dendrites | GraphSAGE GNN over the branch graph. Optional. Skipped automatically if torch / torch_geometric / the GNN checkpoint are missing. |
| Stage 3 | Topology refinement | Smooths short islands, enforces hard constraints (one primary axon, one primary apical) at the soma boundary. |

The engine always emits soma + axon + basal labels and detects apical
automatically — no class-selection flags. Apical detection requires
both a learned per-subtree apical score and a minimum root radius;
files without an apical subtree get 3-class output.

## Setup

`SWC-Studio` ships fully self-contained. `pip install -e .` puts every
dependency *and* every model file in place — there is no separate
download step.

The bundled defaults live in `swcstudio/data/models/`:

| Filename | Stage | Bundled? |
|---|---|---|
| `cell_type_classifier.pkl` | Stage 1 | yes (~15 MB) |
| `branch_classifier.pkl` | Stage 2 | yes (~45 MB) |
| `gnn_apical_basal.pt` | Stage 2b | yes (~0.3 MB) |

To verify the engine is ready on your machine:

```bash
swcstudio models status
```

You'll see a search-path diagnostic and a JSON summary indicating which
model files were resolved and whether torch is available for the GNN.

### Model resolution order

When the engine looks up a model file, it checks paths in this order
and uses the first match:

1. Explicit override (`--model-dir` on the CLI, the GUI's *Model dir*
   field, or the `model_dir` argument in Python)
2. The `SWCSTUDIO_MODEL_DIR` environment variable
3. The user data directory:
   - Windows: `%APPDATA%\swcstudio\models`
   - macOS: `~/Library/Application Support/swcstudio/models`
   - Linux: `~/.local/share/swcstudio/models`
4. The bundled `swcstudio/data/models/` directory inside the installed
   package

Because **first hit wins**, dropping custom-trained models into the
user data directory makes them the default with no extra flags. The
bundled models are a fallback, not a lock-in.

## Running auto-labeling

### CLI — single file

```bash
swcstudio auto-label cell.swc
```

To use a custom model directory just for this run:

```bash
swcstudio auto-label cell.swc --model-dir /path/to/my-models
```

### CLI — folder

```bash
swcstudio auto-typing ./folder
swcstudio auto-typing ./folder --model-dir /path/to/my-models
```

The folder command prints a short engine summary before processing,
then writes one output SWC per input plus a per-folder report.

### GUI

Both Auto Label Editing panels (Batch Processing → Auto Label Editing,
Validation → Auto Label Editing) show a single **Run** button. The
*Model dir* picker next to it is optional — leave it blank to use the
bundled / user-data defaults. A small green "models OK" / red "models
missing" indicator next to the field tells you in real time whether
the engine can run with the chosen settings.

### Python

```python
from swcstudio.core.auto_typing import (
    BatchOptions, run_file, run_batch, is_available, backend_status,
)

ok, reason = is_available()
print(backend_status())              # diagnostic dict

opts = BatchOptions(soma=True, axon=True, basal=True, apic=False, rad=False, zip_output=False)
res = run_file("cell.swc", opts)     # single file
res = run_batch("./folder", opts)    # folder
```

If the engine cannot find the Stage 1 / Stage 2 pickles it raises
`FileNotFoundError` with the search-path diagnostic — the GUI surfaces
the same message so you don't need to read the traceback.

## Training your own models

The engine is fully retrainable on user data; you do not have to live
with the bundled defaults.

### Required dataset layout

```
my_dataset/
├── pyramidal/
│   ├── cell_001.swc
│   ├── cell_002.swc
│   └── ...
└── interneuron/
    ├── cell_a.swc
    └── ...
```

Subfolder names are the cell-type labels. Filenames don't matter. The
SWC `type` column (1=soma, 2=axon, 3=basal, 4=apical) is the per-node
ground truth — make sure the labels in your training files are
correct.

### One-command training

```bash
swcstudio train auto-typing --data-dir my_dataset --output-dir my_models
```

Training writes three files into `my_models/`:

- `cell_type_classifier.pkl` (Stage 1)
- `branch_classifier.pkl` (Stage 2)
- `gnn_apical_basal.pt` (Stage 2b — skipped if `--no-gnn` is set or
  torch is unavailable)

Tunable flags (all optional):

| Flag | Default | Meaning |
|---|---|---|
| `--no-gnn` | (off) | skip Stage 2b GNN training |
| `--seed` | 42 | random seed for splits and models |
| `--gnn-hidden` | 128 | GraphSAGE hidden dim |
| `--gnn-layers` | 3 | GraphSAGE depth |
| `--gnn-dropout` | 0.0 | dropout |
| `--gnn-epochs` | 200 | max epochs per fold |
| `--gnn-patience` | 25 | early-stopping patience |

Training runs Stage 1 (fast — seconds), then Stage 2 (minutes per ~1000
cells), then optionally the GNN (a few minutes on CPU; faster with
CUDA). Memory and time scale with dataset size and morphology
complexity.

### Using your custom models

There are three ways to swap your trained models in for the bundled
defaults; pick whichever fits your workflow.

**Make them the default (recommended for everyday use):**

Drop them into the user data directory. Because the resolver checks
that directory before the bundled defaults, every CLI / GUI / Python
call uses your models from then on, with no flags.

```powershell
# Windows
$dst = "$env:APPDATA\swcstudio\models"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item my_models\*.pkl $dst\
Copy-Item my_models\*.pt  $dst\
```

```bash
# macOS
mkdir -p ~/Library/Application\ Support/swcstudio/models
cp my_models/*.pkl my_models/*.pt ~/Library/Application\ Support/swcstudio/models/

# Linux
mkdir -p ~/.local/share/swcstudio/models
cp my_models/*.pkl my_models/*.pt ~/.local/share/swcstudio/models/
```

**Set per-shell:**

```bash
export SWCSTUDIO_MODEL_DIR=/path/to/my_models
swcstudio auto-label cell.swc
```

```powershell
$env:SWCSTUDIO_MODEL_DIR = "C:\path\to\my_models"
swcstudio auto-label cell.swc
```

**One-off override:**

```bash
swcstudio auto-label cell.swc --model-dir /path/to/my_models
```

The GUI panels' *Model dir* picker behaves the same as `--model-dir`
for that session.

### Verifying which models are in use

```bash
swcstudio models status
swcstudio models status --model-dir /path/to/my_models
```

The output shows the resolved path for each of the three model files,
so you can confirm whether the engine is hitting your custom models or
the bundled fallbacks.

## Troubleshooting

### "Auto-typing needs the Stage 1 and Stage 2 model files."

Means the resolver couldn't find `cell_type_classifier.pkl` or
`branch_classifier.pkl`. Run `swcstudio models status` to see the full
search path. The most common cause is a typo or non-existent path
passed to `--model-dir` or `SWCSTUDIO_MODEL_DIR`.

### GNN says "torch / torch_geometric unavailable"

You probably installed without torch. The GNN is the only optional
component — install it with:

```bash
pip install torch torch-geometric
```

(They're already in the standard `pip install -e .` since the [recent
install simplification](#setup); this only matters for stripped-down
environments.)

### Pickle deserialization errors

Stage 1 and Stage 2 pickles are sensitive to the sklearn version they
were trained on. The bundled pickles are pinned to `scikit-learn>=1.5,<1.8`
in `pyproject.toml`. If you upgrade sklearn outside that range and see
deserialization errors, either re-pin sklearn or retrain your models
under the new version.

### Bundled models are out of date

If you train your own models you can re-bundle them into your local
clone by copying them into `swcstudio/data/models/`. The package-data
manifest in `pyproject.toml` already includes `*.pkl` and `*.pt`, so
they'll be picked up by the next `pip install -e .`.

## Reference

| Public symbol | Lives in |
|---|---|
| `BatchOptions`, `BatchResult`, `FileResult` | `swcstudio.core.auto_typing` |
| `run_file`, `run_batch`, `run_folder` | `swcstudio.core.auto_typing` |
| `is_available`, `backend_status` | `swcstudio.core.auto_typing` |
| `train_user_models` | `swcstudio.core.auto_typing_train` |
| Pipeline internals (`run_pipeline_on_nodes`, `SWCNode`, etc.) | `swcstudio.core.auto_typing` (re-exported from submodules) |

CLI reference: see [CLI Reference](../CLI_REFERENCE.md) for the full
flag list on `swcstudio auto-label`, `swcstudio auto-typing`, and
`swcstudio train auto-typing`.
