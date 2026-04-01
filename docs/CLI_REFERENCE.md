# CLI Reference

This is the current command reference for the SWC-Studio CLI (`swcstudio`).

## Install and Verify

```bash
pip install -e .
swcstudio --help
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

The direct command form is the intended public interface.

Some `--help` usage lines still show the internal grouped route such as `validation`, `morphology`, or `geometry`. That is expected: the direct command is normalized into the shared backend parser before execution.

## OS Notes

- Command names and flags are the same on macOS/Linux/Windows.
- Path style differs: macOS/Linux `./data/file.swc`, Windows `.\data\file.swc`.
- If script entrypoints are not on PATH, use module mode:
  - macOS/Linux: `python -m swcstudio.cli.cli ...`
  - Windows: `py -m swcstudio.cli.cli ...`
- Shell line continuation differs:
  - macOS/Linux: `\`
  - PowerShell: `` ` ``
  - Windows cmd: `^`

## Common Option: `--config-json`

Most feature commands accept JSON, but quote style differs by shell:

macOS/Linux or PowerShell:

```bash
--config-json '{"some":"override"}'
```

Windows cmd:

```bat
--config-json "{\"some\":\"override\"}"
```

This must be a JSON object and is merged into feature config for that run.

## `check`

### `swcstudio check <file>`

- Purpose: print the same combined issue list the GUI builds when an SWC is opened
- Includes:
  - validation issues
  - suspicious radii issues
  - likely wrong labels
  - simplification suggestion

Options:

- `--config-json JSON`

Example:

```bash
swcstudio check ./data/single-soma.swc
```

## Direct Commands

The CLI accepts direct top-level commands.

For commands like `validate`, `radii-clean`, `simplify`, and `index-clean`:

- if the target is an SWC file, SWC-Studio runs the single-file workflow
- if the target is a folder, SWC-Studio runs the batch workflow

Legacy grouped forms such as `swcstudio validation run ...` still work, but the direct form is the preferred public interface.

### `swcstudio validate <target>`

- Purpose: run validation on one SWC file or all SWC files in a folder
- Special behavior: if `target` is literal `rule-guide`, prints rules only

Options:

- `--config-json JSON`

Example:

```bash
swcstudio validate ./data
swcstudio validate ./data/single-soma.swc
swcstudio validate rule-guide
```

### `swcstudio split <folder>`

- Purpose: split SWC files by soma-root trees

Options:

- `--config-json JSON`

Example:

```bash
swcstudio split ./data
```

### `swcstudio auto-typing <folder>`

- Purpose: rule-based auto-labeling for SWCs in folder
- CLI prints auto-typing rule guide before processing
- current method uses branch-consistent subtree inheritance with single-axon / single-apical primary selection rules

Flags:

- `--soma`
- `--axon`
- `--apic`
- `--basal`
- `--config-json JSON`

Example:

```bash
swcstudio auto-typing ./data --soma --axon --basal
```

### `swcstudio radii-clean <target>`

- Purpose: clean abnormal radii on a file or folder using the shared radii-clean backend
- For a file target, writes the cleaned SWC and one GUI-style operation report into the output folder
- For a folder target, runs the batch workflow

Arguments:

- `target`: file path or directory path

Options:

- soma radii are always preserved during radii cleaning
- `--config-json JSON`

Example:

```bash
swcstudio radii-clean ./data/single-soma.swc
swcstudio radii-clean ./data
```

### `swcstudio simplify <target>`

- Purpose: run simplification on one SWC file or every SWC file in a folder
- For a file target, use `--write` to save the simplified SWC and one GUI-style operation report
- For a folder target, runs the batch workflow

Options:

- file target only: `--write`
- file target only: `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio simplify ./data/single-soma.swc --write
swcstudio simplify ./data
```

### `swcstudio index-clean <target>`

- Purpose: reorder and reindex one SWC file or every SWC file in a folder so parents come before children and IDs become continuous
- For a file target, use `--write` to save the cleaned SWC and one GUI-style operation report
- For a folder target, runs the batch workflow

Options:

- file target only: `--write`
- file target only: `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio index-clean ./data/single-soma.swc --write
swcstudio index-clean ./data
```

### `swcstudio rule-guide`

- Purpose: print validation pre-check/rule guide only

Options:

- `--config-json JSON`

### `swcstudio auto-fix <file>`

- Purpose: sanitize + revalidate one file
- When `--write` is used, also writes a GUI-style operation report with a node-change table

Options:

- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio auto-fix ./data/single-soma.swc --write
```

### `swcstudio auto-label <file>`

- Purpose: apply the same single-file auto label workflow used by the GUI Auto Label Editing panel
- Changes only node types; geometry, parent IDs, and radii are preserved
- When `--write` is used, also writes a GUI-style operation report with a node-change table

Flags:

- `--soma`
- `--axon`
- `--apic`
- `--basal`
- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio auto-label ./data/single-soma.swc --write
```

### `swcstudio mesh-editing <file>`

- Purpose: build reusable mesh payload summary

Options:

- `--include-edges`
- `--config-json JSON`

### `swcstudio dendrogram-edit <file> --node-id N --new-type T`

- Purpose: reassign subtree node types
- This is a subtree edit, not a single-node type edit
- When `--write` is used, also writes a GUI-style operation report with a node-change table

Options:

- `--node-id INT` (required)
- `--new-type INT` (required)
- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio dendrogram-edit ./data/single-soma.swc --node-id 42 --new-type 3 --write
```

### `swcstudio set-type <file> --node-id N --new-type T`

- Purpose: change one node type only
- Uses the same single-node type edit behavior as GUI Manual Label Editing
- When `--write` is used, also writes a GUI-style operation report with a node-change table

Options:

- `--node-id INT` (required)
- `--new-type INT` (required)
- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio set-type ./data/single-soma.swc --node-id 14169 --new-type 3 --write
```

### `swcstudio set-radius <file> --node-id N --radius R`

- Purpose: set one node radius directly
- Uses the same single-node radius edit behavior as GUI Manual Radii Editing
- When `--write` is used, also writes a GUI-style operation report with a node-change table

Options:

- `--node-id INT` (required)
- `--radius FLOAT` (required)
- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio set-radius ./data/single-soma.swc --node-id 42 --radius 0.75 --write
```

### `swcstudio move-node <file> --node-id N --x X --y Y --z Z`

- Purpose: move one node to absolute coordinates
- When `--write` is used, also writes a GUI-style operation report with a node-change table

### `swcstudio move-subtree <file> --root-id N --x X --y Y --z Z`

- Purpose: move a whole subtree by setting the subtree root to absolute coordinates
- When `--write` is used, also writes a GUI-style operation report with a node-change table

### `swcstudio connect <file> --start-id A --end-id B`

- Purpose: connect nodes by setting `parent(end) = start`
- When `--write` is used, also writes a GUI-style operation report with a node-change table

### `swcstudio disconnect <file> --start-id A --end-id B`

- Purpose: disconnect every parent-child edge along the path between start and end
- When `--write` is used, also writes a GUI-style operation report with a node-change table

### `swcstudio delete-node <file> --node-id N`

- Purpose: delete one node
- When `--write` is used, also writes a GUI-style operation report with a node-change table

Options:

- `--reconnect-children`
- `--write`
- `--out PATH`

### `swcstudio delete-subtree <file> --root-id N`

- Purpose: delete one subtree
- When `--write` is used, also writes a GUI-style operation report with a node-change table

### `swcstudio insert <file> --start-id A [--end-id B] --x X --y Y --z Z`

- Purpose: insert a new node after start and optionally before end
- When `--write` is used, also writes a GUI-style operation report with a node-change table

Options:

- `--radius FLOAT`
- `--type-id INT`
- `--write`
- `--out PATH`

## `plugins`

### `swcstudio plugins list`

- Purpose: list builtin/plugin methods in registry

Options:

- `--feature-key TOOL.FEATURE`

Example:

```bash
swcstudio plugins list
swcstudio plugins list --feature-key batch_processing.auto_typing
```

### `swcstudio plugins load <module>`

- Purpose: load an external plugin module by Python import path
- Contract expected:
  - `PLUGIN_MANIFEST` dict (or `get_plugin_manifest()`)
  - `register_plugin(registrar)` OR `PLUGIN_METHODS`
- Scope: current CLI process only (use `SWCSTUDIO_PLUGINS` for autoload in each run)

Example:

```bash
swcstudio plugins load my_lab_plugins.summary_plugin
```

### `swcstudio plugins list-loaded`

- Purpose: list loaded plugin manifests (`plugin_id`, version, capabilities, API version)

Example:

```bash
swcstudio plugins list-loaded
```

### Environment Autoload

Plugins can autoload on every CLI run via `SWCSTUDIO_PLUGINS`:

macOS/Linux:

```bash
export SWCSTUDIO_PLUGINS="my_lab_plugins.summary_plugin,my_lab_plugins.custom_auto_typing"
```

Windows PowerShell:

```powershell
$env:SWCSTUDIO_PLUGINS = "my_lab_plugins.summary_plugin,my_lab_plugins.custom_auto_typing"
```

Windows cmd:

```bat
set SWCSTUDIO_PLUGINS=my_lab_plugins.summary_plugin,my_lab_plugins.custom_auto_typing
```

## Output and Reports

Most commands print terminal output and, where applicable, also write report files.

Default generated names use the same structure:

- single-file output/report folder: `<input_folder>/<original_stem>_swc_studio_output/`
- single-file output/report name: `<original_stem>_<full_operation_name>_<timestamp>.<ext>`
- batch output folder: `<input_folder>/<input_folder>_<full_operation_name>_<timestamp>/`
- batch report: `<input_folder>_<full_operation_name>_<timestamp>.txt`

Examples:

- `data/single-soma_swc_studio_output/single-soma_validation_run_20260401_132905.txt`
- `data/single-soma_swc_studio_output/single-soma_validation_index_clean_20260401_132905.swc`
- `data/single-soma_swc_studio_output/single-soma_geometry_simplify_20260401_132905.swc`
- `data_batch_split_20260401_132905/`

Current report behavior:

- `check` prints to the terminal and does not write a report file
- `validate <file>` writes one validation report
- single-file editing commands such as `auto-fix`, `auto-label`, `radii-clean`, `index-clean`, `simplify`, `set-type`, `set-radius`, `dendrogram-edit`, and geometry edits write one GUI-style operation report per run
- batch commands write one batch report and, where applicable, a batch output folder

Single-file edit commands no longer write duplicate legacy text reports alongside the operation report.

## Exit Codes

- `0`: success
- `1`: usage error / parse error
- `2`: runtime error
