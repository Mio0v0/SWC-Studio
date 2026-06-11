# Auto-Typing Engine

`SWC-Studio`'s auto-labeling is a single ML engine. It runs everywhere
— the CLI, both Auto Label Editing GUI panels, and the Python API call
into the same code. There is no backend switch; the engine is the engine.

## What the engine does

The v12 QC-label-flag pipeline runs in order on every SWC:

| Stage | Purpose | Implementation |
|---|---|---|
| Stage 1 | Cell-type detection (pyramidal vs interneuron) | sklearn ensemble over 49 whole-cell features. A soft handoff runs Stage 2+3 for both cell types when confidence is below threshold and picks the higher-confidence outcome. |
| Stage 2 | Per-subtree classification (axon / basal / apical) | sklearn ensemble. Labels are propagated to all branches in the same primary subtree — no mid-track type switches. |
| Stage 2b | Apical-vs-basal re-decision on pyramidal dendrites | GraphSAGE GNN over the branch graph. |
| Branch3 | Conservative rescue for difficult pyramidal apical/basal cases | Lightweight GraphSAGE rescue head (`gnn_branch3_rescue.pt`). |
| Stage 3 | Topology refinement | Smooths short islands, enforces hard constraints (one primary axon, one primary apical) at the soma boundary. |
| QC/flag | Per-cell quality and bad-label flag scoring | QC gate plus compact learned flag models when available. |

The core prediction stages, Branch3 rescue, and QC gate are required.
Learned flag models are optional but included in the bundled production
model set. The torch / torch_geometric runtime comes along through pip
in every install path. The trained model files reach the engine
differently depending on how it was installed:

| Install method | How the engine finds the model files |
|---|---|
| Bundled desktop app (`SWC-Studio.app` / `.zip`) | bundled inside the app under `Contents/Resources/models/` |
| `pip install swcstudio` from PyPI | downloaded from GitHub Releases on first auto-label call (~80 MB, one-time, cached locally) |
| Source install (`pip install -e .`) | bundled in the working tree under `swcstudio/data/models/` |

If any stage's model file is missing — or torch / torch_geometric
fails to import — the engine refuses to run and surfaces a clear
search-path diagnostic instead of silently degrading.

The engine always emits soma + axon + basal labels and detects apical
automatically. Users can leave cell type as `unknown` to run Stage 1, or
override it with `pyramidal` / `interneuron` when they already know what
they are labeling. Flag scoring is enabled by default; a strictness
slider/CLI value controls whether flags are loose or conservative.

## Setup

For the bundled desktop app and the source install, every dependency
*and* every model file is in place after install — no separate
download step needed. For `pip install swcstudio` from PyPI, models
download from GitHub Releases on the first auto-label call (~80 MB,
one-time, cached) — Python dependencies still come along through pip
itself.

The bundled defaults live in `swcstudio/data/models/` (source install)
or `Contents/Resources/models/` (bundled desktop app):

| Filename | Stage | Bundled? |
|---|---|---|
| `cell_type_classifier.pkl` | Stage 1 | yes (~15 MB) |
| `branch_classifier.pkl` | Stage 2 | yes (~45 MB) |
| `gnn_apical_basal.pt` | Stage 2b | yes (~0.3 MB) |
| `gnn_branch3_rescue.pt` | Branch3 | yes |
| `qc_gate.pkl` | QC gate | yes |
| `flag_model_pyramidal.joblib` | flag scoring | yes |
| `flag_model_interneuron.joblib` | flag scoring | yes |
| `flag_model_all.joblib` | flag scoring | yes |
| `flag_model_pyramidal_baseline.joblib` | optional baseline-assisted flag scoring | optional |
| `flag_model_all_baseline.joblib` | optional baseline-assisted flag scoring | optional |

The compact flagger is the default because it is fast and self-contained.
The optional baseline-assisted flagger adds disagreement features from
`neurom_rf.pkl`, `lmeasure_rf.pkl`, `sholl_rf.pkl`, and `sholl_mlp.pkl`.
Place those predictor files in `<model-dir>/baselines/` or set
`SWCSTUDIO_BASELINE_MODEL_DIR`; `swcstudio models status` reports whether
they are reachable. In source checkouts used for paper work, SWC-Studio
also detects a sibling `swc-autolabel-ml/paper/models/baselines/` folder.

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
swcstudio auto-label cell.swc --cell-type pyramidal --flag-strictness 0.8
swcstudio auto-label cell.swc --flag-feature-mode baseline
swcstudio auto-label cell.swc --no-flag
```

To use a custom model directory just for this run:

```bash
swcstudio auto-label cell.swc --model-dir /path/to/my-models
```

### CLI — folder

```bash
swcstudio auto-typing ./folder
swcstudio auto-typing ./folder --model-dir /path/to/my-models
swcstudio auto-typing ./folder --cell-type unknown --flag-strictness 0.5
swcstudio auto-typing ./folder --flag-feature-mode baseline
```

The folder command prints a short engine summary before processing,
then writes one output SWC per input plus a per-folder report.

### GUI

Both Auto Label Editing panels (Batch Processing → Auto Label Editing,
Validation → Auto Label Editing) show a single **Run** button. The
*Model dir* picker next to it is optional — leave it blank to use the
bundled / user-data defaults. A small green "models OK" / red "models
missing" indicator next to the field tells you in real time whether
the engine can run with the chosen settings. The same panels include a
cell-type selector (`unknown`, `pyramidal`, `interneuron`) and a flag
feature selector (`compact`, `baseline`, `auto`) plus a flag strictness
slider.

### Python

```python
from swcstudio.core.auto_typing import (
    BatchOptions, run_file, run_batch, is_available, backend_status,
)

ok, reason = is_available()
print(backend_status())              # diagnostic dict

opts = BatchOptions(
    soma=True, axon=True, basal=True, apic=True, rad=False,
    zip_output=False, cell_type="unknown", flag_enabled=True,
    flag_strictness=0.5, flag_feature_mode="compact",
)
res = run_file("cell.swc", opts)     # single file
res = run_batch("./folder", opts)    # folder
```

If the engine cannot find the required v12 model files it raises
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

Training writes the three core custom-training files into `my_models/`:

- `cell_type_classifier.pkl` (Stage 1)
- `branch_classifier.pkl` (Stage 2)
- `gnn_apical_basal.pt` (Stage 2b)

The bundled production engine also expects `gnn_branch3_rescue.pt`,
`qc_gate.pkl`, and optional flag model files. The CLI custom-training
command currently trains only the core Stage 1 + Stage 2 + Stage 2b
stack.

Tunable flags:

| Flag | Default | Meaning |
|---|---|---|
| `--no-gnn` | (off) | skip Stage 2b GNN training (refresh Stages 1+2 only; the existing GNN checkpoint must already be in `--output-dir`) |
| `--seed` | 42 | random seed for splits and models |
| `--gnn-hidden` | 128 | GraphSAGE hidden dim |
| `--gnn-layers` | 3 | GraphSAGE depth |
| `--gnn-dropout` | 0.0 | dropout |
| `--gnn-epochs` | 200 | max epochs per fold |
| `--gnn-patience` | 25 | early-stopping patience |

Training runs Stage 1 (fast — seconds), then Stage 2 (minutes per ~1000
cells), then the Stage 2b GNN (a few minutes on CPU; faster with CUDA).
Memory and time scale with dataset size and morphology complexity.

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

The output shows the resolved path for each v12 model file, so you can
confirm whether the engine is hitting your custom models or the bundled
fallbacks.

## Troubleshooting

### "Auto-typing is missing required model files"

Means the resolver couldn't find one of the required core model files:
`cell_type_classifier.pkl` (Stage 1), `branch_classifier.pkl` (Stage 2),
`gnn_apical_basal.pt` (Stage 2b), `gnn_branch3_rescue.pt`, or
`qc_gate.pkl`. Run `swcstudio models status` to see the full search path.
The most common cause is a typo or non-existent path passed to
`--model-dir` or `SWCSTUDIO_MODEL_DIR`.

### "Auto-typing requires torch and torch_geometric"

torch and torch_geometric are required dependencies of the package.
Seeing this error means your install is broken — most often a venv
was created with a different Python version than the one currently
active. Reinstall:

```bash
pip install -e .
```

If that still fails, recreate the venv from scratch (see
[Getting Started](../GETTING_STARTED.md)).

### Pickle deserialization errors

Stage 1 and Stage 2 pickles are sensitive to the sklearn version they
were trained on. The bundled pickles are pinned to `scikit-learn>=1.5,<1.8`
in `pyproject.toml`. If you upgrade sklearn outside that range and see
deserialization errors, either re-pin sklearn or retrain your models
under the new version.

### Bundled models are out of date

To replace the bundled models with custom-trained ones, drop your
new files into the location that wins for your install:

| Install method | Where to put your custom models |
|---|---|
| Source install (`pip install -e .`) | `swcstudio/data/models/` — the model resolver finds them on every run |
| `pip install swcstudio` from PyPI | the user model dir (macOS: `~/Library/Application Support/swcstudio/models/`, Windows: `%APPDATA%\swcstudio\models\`, Linux: `~/.local/share/swcstudio/models/`) |
| Bundled desktop app | the user model dir above (overrides the bundled copy) |

Or pass `--model-dir /path/to/your/models` to `swcstudio auto-label`
for one-off use without modifying any directory permanently.

Note: the pip wheel intentionally does **not** ship model files
(see `pyproject.toml`'s `[tool.setuptools]` block). Model layers are
distributed as a separate `swcstudio-models-vX.Y.Z.zip` GitHub Release
asset and downloaded on first use.

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
