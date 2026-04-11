# CLI Reference

This page documents the current public CLI surface for `swcstudio`.

## Install and Verify

```bash
pip install -e .
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

- Purpose: rule-based auto-labeling for SWCs in one folder
- Prints the auto-typing guide before processing
- Soma, axon, and basal labeling are always enabled
- The algorithm automatically switches between 3-class and 4-class labeling by detecting whether an apical subtree is present

Example:

```bash
swcstudio auto-typing ./data
```

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

- Purpose: apply the same single-file auto-label workflow used by the GUI Auto Label Editing panel
- Changes only node types; geometry, parent IDs, and radii are preserved
- Soma, axon, and basal labeling are always enabled
- The algorithm automatically switches between 3-class and 4-class labeling by detecting whether an apical subtree is present

Example:

```bash
swcstudio auto-label ./data/single-soma.swc
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

## Plugins

### `swcstudio plugins list`

List builtin and plugin-provided feature methods.

### `swcstudio plugins list-loaded`

List currently loaded plugin manifests.

### `swcstudio plugins load <module>`

Load one plugin module by import path.
