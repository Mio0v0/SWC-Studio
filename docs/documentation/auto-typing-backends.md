# Auto-Typing Engine

`SWC-Studio` uses one auto-labeling engine across the CLI, GUI, and
Python API. There is no backend switch in the deployed app.

## What The Engine Does

The current engine is a QC-label-flag pipeline:

| Step | Purpose | Main model or code |
|---|---|---|
| QC gate | Reject malformed, disconnected, or out-of-distribution files before prediction starts. The structural checks are type-agnostic and do not require existing soma or neurite labels. | `qc_gate.pkl` plus structural checks in `qc_input.py` |
| Stage 1 | Detect cell type as pyramidal or interneuron, unless the user provides the type. | `cell_type_classifier.pkl` |
| Stage 2 | Label primary subtrees as axon, basal, or apical. | `branch_classifier.pkl` |
| Stage 2b | Re-decide apical vs basal on pyramidal dendrite branches using branch-graph context. | `gnn_apical_basal.pt` |
| Branch3 | Conservatively rescue difficult pyramidal apical/basal cases. | `gnn_branch3_rescue.pt` |
| Stage 3 | Apply topology cleanup and soma-boundary constraints. | code in `pipeline.py` |
| Flag scoring | Estimate whether the final cell-level labels look unreliable. | compact `flag_model_*.joblib` files |

Stage 1 has a soft handoff path: when its confidence is low, the engine
runs the downstream labeling path for both cell types and picks the more
confident result. If the user selects `pyramidal` or `interneuron`, Stage
1 is skipped and that cell type is used directly.

The compact flagger is the deployed flagger. It uses features already
available from the auto-labeling inference pass, including Branch3
disagreement features. Research-only flag bundles that require
unsupported `baseline_` or `xmodel_` disagreement features are rejected by
the runtime and are not shipped in SWC-Studio.

## Required Model Files

The production bundle in `swcstudio/data/models/` contains:

| Filename | Role | Current raw size |
|---|---|---|
| `cell_type_classifier.pkl` | Stage 1 cell-type classifier | about 1.1 MB |
| `branch_classifier.pkl` | Stage 2 subtree labeler | about 73.4 MB |
| `gnn_apical_basal.pt` | Stage 2b GraphSAGE apical/basal head | about 0.1 MB |
| `gnn_branch3_rescue.pt` | Branch3 rescue head | about 0.1 MB |
| `qc_gate.pkl` | QC gate | tiny |
| `flag_model_pyramidal.joblib` | compact pyramidal flagger | about 0.3 MB |
| `flag_model_interneuron.joblib` | compact interneuron flagger | about 0.1 MB |
| `flag_model_all.joblib` | compact fallback flagger | about 0.1 MB |

The core prediction stages, Branch3 rescue, QC gate, torch, and
torch_geometric are required for auto-labeling. The learned flag models
are optional at runtime: if the required prediction stack is present but a
flag model is missing, labeling can still run without a flag result.

## Model Resolution

When the engine looks up a model file, it checks paths in this order and
uses the first match:

1. `--model-dir`, the GUI model directory control, or the Python
   `model_dir` argument
2. `SWCSTUDIO_MODEL_DIR`
3. the user model directory:
   - Windows: `%APPDATA%\swcstudio\models`
   - macOS: `~/Library/Application Support/swcstudio/models`
   - Linux: `~/.local/share/swcstudio/models`
4. the bundled package directory: `swcstudio/data/models/`

For pip installs, the resolver can download the models package from
GitHub Releases on first use and cache it in the user model directory.
Source installs and bundled desktop apps already include the model files.

Check the current resolution status with:

```bash
swcstudio models status
swcstudio models status --model-dir /path/to/models
swcstudio gpu-status
```

## Running Auto-Labeling

Single file:

```bash
swcstudio auto-label cell.swc
swcstudio auto-label cell.swc --cell-type pyramidal --flag-strictness 0.8
swcstudio auto-label cell.swc --no-flag
swcstudio auto-label cell.swc --model-dir /path/to/models
```

Folder:

```bash
swcstudio auto-typing ./swc-folder
swcstudio auto-typing ./swc-folder --cell-type unknown --flag-strictness 0.5
swcstudio auto-typing ./swc-folder --model-dir /path/to/models
```

The GUI Auto Label Editing panels expose the same controls: input
selection, optional model directory, cell type (`unknown`, `pyramidal`,
`interneuron`), flag enable/disable, and a loose-to-strict flag
strictness control.

## Python API

```python
from swcstudio.core.auto_typing import (
    BatchOptions,
    backend_status,
    is_available,
    run_batch,
    run_file,
)

ok, reason = is_available()
print(backend_status())

opts = BatchOptions(
    soma=True,
    axon=True,
    basal=True,
    apic=True,
    rad=False,
    zip_output=False,
    cell_type="unknown",
    flag_enabled=True,
    flag_strictness=0.5,
    flag_feature_mode="compact",
)

single = run_file("cell.swc", opts)
folder = run_batch("./swc-folder", opts)
```

`flag_feature_mode` is kept for compatibility. `compact`, `simple`,
`auto`, `baseline`, and `complex` all resolve to compact scoring in the
current runtime.

## Training Custom Models

The public training command trains the core custom-training stack:

```bash
swcstudio train auto-typing --data-dir my_dataset --output-dir my_models
```

Expected dataset layout:

```text
my_dataset/
  pyramidal/
    cell_001.swc
    cell_002.swc
  interneuron/
    cell_a.swc
```

The command writes:

- `cell_type_classifier.pkl`
- `branch_classifier.pkl`
- `gnn_apical_basal.pt`

The deployed production engine also expects `gnn_branch3_rescue.pt` and
`qc_gate.pkl`, and can use the compact `flag_model_*.joblib` files when
available. The current public training command does not train Branch3,
QC, or flag models.

## Troubleshooting

`Auto-typing is missing required model files`

Run `swcstudio models status` and check the search paths. The required
core files are Stage 1, Stage 2, Stage 2b, Branch3, and the QC gate.

`Auto-typing requires torch and torch_geometric`

The installed Python environment is missing required dependencies for
the GNN stages. Reinstall the package in the active environment. For GPU
installs, run `swcstudio gpu-status` and follow
[GPU Setup](../GPU_INSTALL.md).

`Pickle deserialization errors`

Stage 1 and Stage 2 are sklearn pickles. Use the dependency range pinned
in `pyproject.toml`, or retrain the models under the sklearn version in
your environment.

## Reference

| Public symbol | Module |
|---|---|
| `BatchOptions`, `BatchResult`, `FileResult` | `swcstudio.core.auto_typing` |
| `run_file`, `run_batch`, `run_folder` | `swcstudio.core.auto_typing` |
| `is_available`, `backend_status` | `swcstudio.core.auto_typing` |
| `train_user_models` | `swcstudio.core.auto_typing_train` |
