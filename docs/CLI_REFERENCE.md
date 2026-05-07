# CLI Reference

This page documents the current public CLI surface for `swcstudio`.

## Install and Verify

The CLI is available from any of the three install paths — see
[Getting Started](GETTING_STARTED.md) for the full options.

```bash
# pip install (researchers / Python users)
pip install swcstudio

# OR source install (developers)
pip install -e .

# Verify
swcstudio --help
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

The direct command form is the intended public interface. Internal grouped routes such as `validation`, `morphology`, or `geometry` still exist, but the direct form is the one to document and use.

## Common Option: `--config-json`

Most feature commands accept `--config-json` for one-run config overrides.

Example:

```bash
swcstudio radii-clean ./data/single-soma.swc --config-json '{"rules":{"max_passes":8}}'
```

This must be a JSON object and is merged into the feature config for that run.

## Output Behavior for Single-File Edits

Single-file edit commands now always write both:

- a processed SWC copy
- an operation log

Default location:

- `<input_folder>/<stem>_swc_studio_output/`

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

No extra `--write` flag is needed.

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
swcstudio check ./data/single-soma.swc
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
swcstudio validate ./data
swcstudio validate ./data/single-soma.swc
swcstudio validate rule-guide
```

### `swcstudio split <folder>`

- Purpose: split SWC files by disconnected soma-root trees

Example:

```bash
swcstudio split ./data
```

### `swcstudio auto-typing <folder>`

- Purpose: auto-labeling for every SWC in one folder, using the v9 ML
  engine (Stage 1 cell-type detector + Stage 2 per-subtree classifier
  + Stage 2b GraphSAGE GNN + Stage 3 topology refinement). All four
  stages are required.
- Prints a short engine summary before processing
- Soma, axon, and basal labeling are always enabled
- The engine automatically switches between 3-class and 4-class
  labeling by detecting whether an apical subtree is present
- Optional `--model-dir` points at a directory of trained model files
  (Stage 1 + Stage 2 + Stage 2b GNN, all three required); falls back
  to user-data / bundled models if omitted

Examples:

```bash
swcstudio auto-typing ./data
swcstudio auto-typing ./data --model-dir ~/swc-models
```

Run `swcstudio models status` first if you want to confirm the engine
can resolve the model files on your machine.

### `swcstudio radii-clean <target>`

- Purpose: clean abnormal radii on a file or folder using the shared radii-clean backend
- File target: writes the cleaned SWC and one operation report
- Folder target: runs the batch radii-clean workflow

Examples:

```bash
swcstudio radii-clean ./data/single-soma.swc
swcstudio radii-clean ./data
```

### `swcstudio simplify <target>`

- Purpose: run simplification on one SWC file or every SWC file in a folder
- File target: runs `geometry simplify`
- Folder target: runs batch simplification

Examples:

```bash
swcstudio simplify ./data/single-soma.swc
swcstudio simplify ./data
```

### `swcstudio index-clean <target>`

- Purpose: reorder and reindex one SWC file or every SWC file in a folder so parents come before children and IDs become continuous
- File target: runs the single-file index-clean workflow
- Folder target: runs batch index clean

Examples:

```bash
swcstudio index-clean ./data/single-soma.swc
swcstudio index-clean ./data
```

### `swcstudio rule-guide`

- Purpose: print the validation pre-check and rule guide only

## Single-File Repair Commands

### `swcstudio auto-fix <file>`

- Purpose: sanitize and revalidate one file

Example:

```bash
swcstudio auto-fix ./data/single-soma.swc
```

### `swcstudio auto-label <file>`

- Purpose: apply the same single-file auto-label workflow used by the
  GUI Auto Label Editing panel
- Engine: v9 ML pipeline (same as `swcstudio auto-typing`)
- Changes only node types; geometry, parent IDs, and radii are preserved
- Soma, axon, and basal labeling are always enabled
- The engine automatically switches between 3-class and 4-class
  labeling by detecting whether an apical subtree is present
- Optional `--model-dir` points at a directory of trained model files

Examples:

```bash
swcstudio auto-label ./data/single-soma.swc
swcstudio auto-label ./data/single-soma.swc --model-dir ~/my-models
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
swcstudio dendrogram-edit ./data/single-soma.swc --node-id 42 --new-type 3
```

### `swcstudio set-type <file>`

- Purpose: set one node type directly

Flags:

- `--node-id`
- `--new-type`

Example:

```bash
swcstudio set-type ./data/single-soma.swc --node-id 14169 --new-type 3
```

### `swcstudio set-radius <file>`

- Purpose: set one node radius directly

Flags:

- `--node-id`
- `--radius`

Example:

```bash
swcstudio set-radius ./data/single-soma.swc --node-id 42 --radius 0.75
```

## Geometry Commands

### `move-node`

Move one node to an absolute XYZ position.

```bash
swcstudio move-node ./data/single-soma.swc --node-id 42 --x 100 --y 120 --z 5
```

### `move-subtree`

Move a subtree by setting its root node to an absolute XYZ position.

```bash
swcstudio move-subtree ./data/single-soma.swc --root-id 40 --x 100 --y 120 --z 5
```

### `connect`

Set the end node parent to the start node.

```bash
swcstudio connect ./data/single-soma.swc --start-id 10 --end-id 22
```

### `disconnect`

Disconnect all parent-child edges along the path between two nodes.

```bash
swcstudio disconnect ./data/single-soma.swc --start-id 10 --end-id 22
```

### `delete-node`

Delete one node. Use `--reconnect-children` when the node has children and you want them reattached to the deleted node’s parent.

```bash
swcstudio delete-node ./data/single-soma.swc --node-id 1180
swcstudio delete-node ./data/single-soma.swc --node-id 13 --reconnect-children
```

### `delete-subtree`

Delete a full subtree rooted at one node.

```bash
swcstudio delete-subtree ./data/single-soma.swc --root-id 40
```

### `insert`

Insert one node after `start-id` and optionally before `end-id`.

```bash
swcstudio insert ./data/single-soma.swc --start-id 10 --end-id 22 --x 100 --y 120 --z 5
```

## Train Custom Auto-Typing Models

### `swcstudio train auto-typing`

Train all three model files of the v9 ML pipeline — Stage 1
(cell-type classifier), Stage 2 (per-branch classifier), and Stage 2b
(GraphSAGE GNN apical-vs-basal head) — on your own labeled SWC corpus.
All three are required at inference time. Pass `--no-gnn` only when
you want to refresh Stages 1+2 against an existing GNN checkpoint.

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

Training writes three files into `--output-dir`:

- `cell_type_classifier.pkl`  Stage 1
- `branch_classifier.pkl`     Stage 2
- `gnn_apical_basal.pt`       Stage 2b GNN (only if not `--no-gnn`)

The standard `pip install -e .` already includes torch and
torch_geometric so GNN training works out of the box.

For the full retraining workflow (recommended ways to make custom
models the default, dataset layout, troubleshooting), see the
[Auto-Typing Engine](documentation/auto-typing-backends.md) page.

## Models

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

## Plugins

### `swcstudio plugins list`

List builtin and plugin-provided feature methods.

### `swcstudio plugins list-loaded`

List currently loaded plugin manifests.

### `swcstudio plugins load <module>`

Load one plugin module by import path.
