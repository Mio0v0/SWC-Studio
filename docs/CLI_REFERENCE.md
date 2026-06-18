# CLI Reference

This page documents the current public CLI surface for `swcstudio`.

## Install and Verify

The CLI is available from any of the three install paths — see
[Getting Started](GETTING_STARTED.md) for the full options.

```bash
# pip install (researchers / Python users)
python -m pip install swcstudio

# OR source install (developers)
python -m pip install -e .

# Verify
swcstudio --help
swcstudio doctor
```

If the script entrypoint is not on your path, use module mode:

```bash
python -m swcstudio.cli.cli --help
```

## Command Shape

```bash
swcstudio <command> [args] [options]
```

Public direct commands:

- `check`
- `doctor`
- `validate`
- `rule-guide`
- `split`
- `auto-typing`
- `radii-clean`
- `simplify`
- `index-clean`
- `auto-fix`
- `auto-label`
- `mesh-editing`
- `dendrogram-edit`
- `set-type`
- `set-radius`
- `move-node`
- `move-subtree`
- `connect`
- `disconnect`
- `delete-node`
- `delete-subtree`
- `insert`
- `plugins`

`swcstudio doctor` imports every runtime dependency, checks all packaged
configuration files, deserializes every production model, and verifies
that the GUI module imports. Use `swcstudio doctor --json` in automated
setup checks or `swcstudio doctor --quick` to skip model deserialization.

The direct command form is the intended public interface. Internal grouped routes such as `validation`, `morphology`, or `geometry` still exist, but the direct form is the one to document and use.

## Common Option: `--config-json`

Most feature commands accept `--config-json` for one-run config overrides.

Example:

```bash
swcstudio radii-clean cell.swc --config-json '{"rules":{"max_passes":8}}'
```

This must be a JSON object and is merged into the feature config for that run.

## Output Behavior for Single-File Edits

Single-file edit commands now update the source SWC directly and record
the operation in the per-file history archive:

- source file: `<input_folder>/<stem>.swc`
- history archive: `<input_folder>/<stem>_history.swcstudio`

This applies to:

- `auto-fix`
- `auto-label`
- `radii-clean` when the target is one file
- `index-clean` when the target is one file
- `simplify` when the target is one file
- `dendrogram-edit`
- `set-type`
- `set-radius`
- all geometry edit commands

The source SWC receives compact `# @PROV` pointer lines, and existing
SWC/SWC+ comment headers are preserved. No extra `--write` flag is
needed. Text reports are still produced by report-only commands such as
validation runs, and explicit commands such as `split`, `history
checkout`, and `history checkpoint` intentionally materialize separate
files.

## `check`

### `swcstudio check <file>`

- Purpose: print the same combined issue list the GUI builds when an SWC is opened
- Includes:
  - validation issues
  - suspicious radii issues
  - likely wrong-label issues
  - a simplification suggestion when available

Example:

```bash
swcstudio check cell.swc
```

## Direct Commands

For commands like `validate`, `radii-clean`, `simplify`, and `index-clean`:

- if the target is an SWC file, SWC-Studio runs the single-file workflow
- if the target is a folder, SWC-Studio runs the batch workflow

### `swcstudio validate <target>`

- Purpose: run validation on one SWC file or all SWC files in a folder
- Special behavior: if `target` is the literal `rule-guide`, prints the validation guide only

Examples:

```bash
swcstudio validate ./swc-folder
swcstudio validate cell.swc
swcstudio validate rule-guide
```

### `swcstudio split <folder>`

- Purpose: split SWC files by disconnected soma-root trees

Example:

```bash
swcstudio split ./swc-folder
```

### `swcstudio auto-typing <folder>`

- Purpose: auto-labeling for every SWC in one folder.
- Engine: v12 QC-label-flag pipeline.
- Each passing source SWC is updated in place and gets its own history archive.
- QC-rejected or failed files are skipped and listed in the JSON summary.
- Prints a short engine summary before processing.
- Soma, axon, and basal labeling are always enabled
- The engine detects cell type automatically unless `--cell-type` is
  provided. Use `--cell-type pyramidal` or `--cell-type interneuron`
  when the user already knows the cell type.
- Flag scoring is enabled by default. `--flag-strictness` controls how
  strict the bad-label flagger is; higher values are stricter and may
  flag more cells. Use `--no-flag` to skip flag scoring.
- Optional `--model-dir` points at a v12-compatible model bundle. The
  core required files are Stage 1, Stage 2, Stage 2b GNN, Branch3 rescue,
  and QC gate; flag model files enable learned flag scoring.

Examples:

```bash
swcstudio auto-typing ./swc-folder
swcstudio auto-typing ./swc-folder --model-dir ~/swc-models
swcstudio auto-typing ./swc-folder --cell-type pyramidal --flag-strictness 0.8
swcstudio auto-typing ./swc-folder --no-flag
```

Run `swcstudio models status` first if you want to confirm the engine
can resolve the model files on your machine.

### `swcstudio radii-clean <target>`

- Purpose: clean abnormal radii on a file or folder using the shared radii-clean backend
- File target: updates the source SWC and records operation history
- Folder target: records each processed SWC in place

Examples:

```bash
swcstudio radii-clean cell.swc
swcstudio radii-clean ./swc-folder
```

### `swcstudio simplify <target>`

- Purpose: run simplification on one SWC file or every SWC file in a folder
- File target: runs `geometry simplify`
- Folder target: runs batch simplification

Examples:

```bash
swcstudio simplify cell.swc
swcstudio simplify ./swc-folder
```

### `swcstudio index-clean <target>`

- Purpose: reorder and reindex one SWC file or every SWC file in a folder so parents come before children and IDs become continuous
- File target: runs the single-file index-clean workflow
- Folder target: runs batch index clean

Examples:

```bash
swcstudio index-clean cell.swc
swcstudio index-clean ./swc-folder
```

### `swcstudio rule-guide`

- Purpose: print the validation pre-check and rule guide only

## Single-File Repair Commands

### `swcstudio auto-fix <file>`

- Purpose: sanitize and revalidate one file

Example:

```bash
swcstudio auto-fix cell.swc
```

### `swcstudio auto-label <file>`

- Purpose: apply the same single-file auto-label workflow used by the
  GUI Auto Label Editing panel
- Engine: same v12 QC-label-flag pipeline used by `swcstudio auto-typing`
- Changes only node types; geometry, parent IDs, and radii are preserved
- Updates the source SWC in place and records operation history
- Soma, axon, and basal labeling are always enabled
- The engine detects cell type automatically unless `--cell-type` is
  provided. Use `--cell-type pyramidal` or `--cell-type interneuron`
  when the user already knows the cell type.
- Flag scoring is enabled by default. `--flag-strictness` controls how
  strict the bad-label flagger is; higher values are stricter and may
  flag more cells. Use `--no-flag` to skip flag scoring.
- Optional `--model-dir` points at a v12-compatible model bundle.

Examples:

```bash
swcstudio auto-label cell.swc
swcstudio auto-label cell.swc --model-dir ~/my-models
swcstudio auto-label cell.swc --cell-type interneuron --flag-strictness 0.3
swcstudio auto-label cell.swc --no-flag
```

To verify the engine can find its model files:

```bash
swcstudio models status
swcstudio models status --model-dir ~/my-models
```

### `swcstudio dendrogram-edit <file>`

- Purpose: reassign one subtree to a new node type

Flags:

- `--node-id`
- `--new-type`

Example:

```bash
swcstudio dendrogram-edit cell.swc --node-id 42 --new-type 3
```

### `swcstudio set-type <file>`

- Purpose: set one node type directly

Flags:

- `--node-id`
- `--new-type`

Example:

```bash
swcstudio set-type cell.swc --node-id 14169 --new-type 3
```

### `swcstudio set-radius <file>`

- Purpose: set one node radius directly

Flags:

- `--node-id`
- `--radius`

Example:

```bash
swcstudio set-radius cell.swc --node-id 42 --radius 0.75
```

## Geometry Commands

### `move-node`

Move one node to an absolute XYZ position.

```bash
swcstudio move-node cell.swc --node-id 42 --x 100 --y 120 --z 5
```

### `move-subtree`

Move a subtree by setting its root node to an absolute XYZ position.

```bash
swcstudio move-subtree cell.swc --root-id 40 --x 100 --y 120 --z 5
```

### `connect`

Set the end node parent to the start node.

```bash
swcstudio connect cell.swc --start-id 10 --end-id 22
```

### `disconnect`

Disconnect all parent-child edges along the path between two nodes.

```bash
swcstudio disconnect cell.swc --start-id 10 --end-id 22
```

### `delete-node`

Delete one node. Use `--reconnect-children` when the node has children and you want them reattached to the deleted node’s parent.

```bash
swcstudio delete-node cell.swc --node-id 1180
swcstudio delete-node cell.swc --node-id 13 --reconnect-children
```

### `delete-subtree`

Delete a full subtree rooted at one node.

```bash
swcstudio delete-subtree cell.swc --root-id 40
```

### `insert`

Insert one node after `start-id` and optionally before `end-id`.

```bash
swcstudio insert cell.swc --start-id 10 --end-id 22 --x 100 --y 120 --z 5
```

## History Commands

History commands inspect or materialize states from
`<stem>_history.swcstudio`.

```bash
swcstudio history log cell.swc
swcstudio history show cell.swc op-1
swcstudio history checkout cell.swc op-1 -o review_copy.swc
swcstudio history checkpoint cell.swc op-1 --label review
```

- `history log` shows user-facing operation IDs by default.
- `history show <op-id>` shows operation details and node-level old/new values.
- `checkout`, `checkpoint`, `tag`, `branch --from`, and `reproduce`
  accept either an operation ID such as `op-1` or a technical SHA.
- Add `--technical` to `history log` or `history show` when you need
  exact internal version/SHA details.

## Train Custom Auto-Typing Models

### `swcstudio train auto-typing`

Train the three core custom-training files of the auto-typing pipeline:
Stage 1 (cell-type classifier), Stage 2 (per-branch classifier), and
Stage 2b (GraphSAGE GNN apical-vs-basal head) on your own labeled SWC
corpus.
Pass `--no-gnn` only when you want to refresh Stages 1+2 against an
existing GNN checkpoint.

Note: the bundled production engine is now the v12 QC-label-flag
pipeline. Full v12 deployment also uses a Branch3 rescue checkpoint, QC
gate, and optional learned flag models. This training command currently
trains only the core Stage 1 + Stage 2 + Stage 2b stack.

Required dataset layout:

```
<data-dir>/
    pyramidal/
        <files>.swc
    interneuron/
        <files>.swc
```

Each SWC's type column (1=soma, 2=axon, 3=basal, 4=apical) is the per-node
ground truth. Subfolder names are the cell-type labels.

Required flags:

- `--data-dir <dir>`   labeled-dataset root (must contain `pyramidal/` subfolder)
- `--output-dir <dir>` directory to write trained models into

Optional flags:

- `--no-gnn`           skip Stage 2b GNN training (Stage 1 + Stage 2 only)
- `--seed <int>`       random seed (default 42)
- `--gnn-hidden <int>` GraphSAGE hidden dim (default 128)
- `--gnn-layers <int>` GraphSAGE depth (default 3)
- `--gnn-dropout <f>`  dropout (default 0.0)
- `--gnn-epochs <int>` max epochs per fold (default 200)
- `--gnn-patience <int>` early-stopping patience (default 25)

Example:

```bash
swcstudio train auto-typing --data-dir ./labeled-dataset --output-dir ./my-models
# Then point auto-labeling at the trained models:
swcstudio auto-label cell.swc --model-dir ./my-models
# Or set the env var so all runs use them:
export SWCSTUDIO_MODEL_DIR=./my-models
```

Training writes three core files into `--output-dir`:

- `cell_type_classifier.pkl`  Stage 1
- `branch_classifier.pkl`     Stage 2
- `gnn_apical_basal.pt`       Stage 2b GNN (only if not `--no-gnn`)

The standard `python -m pip install -e .` already includes torch and
torch_geometric so GNN training works out of the box.

For the full retraining workflow (recommended ways to make custom
models the default, dataset layout, troubleshooting), see the
[Auto-Typing Engine](documentation/auto-typing-backends.md) page.

## Models

### `swcstudio gpu-status`

Check whether the active Python environment can run SWC-Studio with CUDA.
This is mainly useful for pip/source installs; the one-click executable is
intended to be the portable CPU build.

```bash
swcstudio gpu-status
swcstudio gpu-status --json
```

The report shows PyTorch, PyTorch CUDA build, CUDA visibility,
PyTorch Geometric, `nvidia-smi`, and recommended next steps. The GUI
exposes the same check under Help -> GPU Readiness.

### `swcstudio models status`

Print which model files the auto-typing engine can find and where it
looked. Run this once after install to confirm the bundled models are
reachable, or any time the engine reports models missing.

```bash
swcstudio models status
swcstudio models status --model-dir ~/my-models
```

Output is a search-path diagnostic plus a JSON summary of which model
files were found and whether torch is available for the Stage 2b GNN.

### Current Auto-Label Model Bundle

The current production auto-label path is the v12 QC-label-flag pipeline:

- Stage 1 cell type: `cell_type_classifier.pkl`
- Stage 2 subtree labeler: `branch_classifier.pkl`
- Stage 2b apical/basal GNN: `gnn_apical_basal.pt`
- Branch3 rescue: `gnn_branch3_rescue.pt`
- QC gate: `qc_gate.pkl`
- Compact learned flags: `flag_model_pyramidal.joblib`,
  `flag_model_interneuron.joblib`, `flag_model_all.joblib`

`--flag-feature-mode compact` and `--flag-feature-mode simple` both use
the bundled compact flagger. Older `baseline`, `auto`, and `complex`
config values are treated as compact for backward compatibility; the
slower research-only disagreement flag mode is not deployed in SWC-Studio.

## Plugins

### `swcstudio plugins list`

List builtin and plugin-provided feature methods.

### `swcstudio plugins list-loaded`

List currently loaded plugin manifests.

### `swcstudio plugins load <module>`

Load one plugin module by import path.
