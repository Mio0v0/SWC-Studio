# CLI Reference

This is the current command reference for the SWC-Studio CLI (`swcstudio`).

## Install and Verify

```bash
pip install -e .
swcstudio --help
```

## Command Shape

```bash
swcstudio <tool> <feature> [args] [options]
```

Top-level tools:

- `check`
- `batch`
- `validation`
- `visualization`
- `morphology`
- `geometry`
- `plugins`

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

## `batch`

### `swcstudio batch validate <folder>`

- Purpose: run validation on all SWC files in a folder
- Special behavior: if `folder` is literal `rule-guide`, prints rules only

Options:

- `--config-json JSON`

Example:

```bash
swcstudio batch validate ./data
swcstudio batch validate rule-guide
```

### `swcstudio batch split <folder>`

- Purpose: split SWC files by soma-root trees

Options:

- `--config-json JSON`

Example:

```bash
swcstudio batch split ./data
```

### `swcstudio batch auto-typing <folder>`

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
swcstudio batch auto-typing ./data --soma --axon --basal
```

### `swcstudio batch radii-clean <target>`

- Purpose: clean abnormal radii on a file or folder

Arguments:

- `target`: file path or directory path

Options:

- soma radii are always preserved during radii cleaning
- `--config-json JSON`

Example:

```bash
swcstudio batch radii-clean ./data/single-soma.swc
```

### `swcstudio batch simplify <folder>`

- Purpose: run simplification on every SWC file in a folder

Options:

- `--config-json JSON`

Example:

```bash
swcstudio batch simplify ./data
```

### `swcstudio batch index-clean <folder>`

- Purpose: reorder and reindex every SWC file in a folder so parents come before children and IDs become continuous

Options:

- `--config-json JSON`

Example:

```bash
swcstudio batch index-clean ./data
```

## `validation`

### `swcstudio validation rule-guide`

- Purpose: print validation pre-check/rule guide only

Options:

- `--config-json JSON`

### `swcstudio validation run <file>`

- Purpose: run full structured validation for one file

Options:

- `--config-json JSON`

Example:

```bash
swcstudio validation run ./data/single-soma.swc
```

### `swcstudio validation auto-fix <file>`

- Purpose: sanitize + revalidate one file

Options:

- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio validation auto-fix ./data/single-soma.swc --write
```

### `swcstudio validation radii-clean <target>`

- Purpose: same shared radii-clean backend used by batch

Arguments:

- `target`: file path or directory path

Options:

- soma radii are always preserved during radii cleaning
- `--config-json JSON`

Notes:

- radii cleaning uses the same shared backend and JSON config as batch mode
- see [Radii Cleaning Tutorial](RADII_CLEANING_TUTORIAL.md) for the algorithm and config groups

### `swcstudio validation index-clean <file>`

- Purpose: reorder and reindex one SWC file

Options:

- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio validation index-clean ./data/single-soma.swc --write
```

## `visualization`

### `swcstudio visualization mesh-editing <file>`

- Purpose: build reusable mesh payload summary

Options:

- `--include-edges`
- `--config-json JSON`

## `morphology`

### `swcstudio morphology dendrogram-edit <file> --node-id N --new-type T`

- Purpose: reassign subtree node types

Options:

- `--node-id INT` (required)
- `--new-type INT` (required)
- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio morphology dendrogram-edit ./data/single-soma.swc --node-id 42 --new-type 3 --write
```

### `swcstudio morphology set-radius <file> --node-id N --radius R`

- Purpose: set one node radius directly

Options:

- `--node-id INT` (required)
- `--radius FLOAT` (required)
- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio morphology set-radius ./data/single-soma.swc --node-id 42 --radius 0.75 --write
```

## `geometry`

These commands expose the same geometry-editing backend used by the app.

### `swcstudio geometry simplify <file>`

- Purpose: run the current simplification workflow used by `Geometry Editing -> Simplification`
- CLI prints the simplification rule guide before running

Options:

- `--write`
- `--out PATH`
- `--config-json JSON`

Example:

```bash
swcstudio geometry simplify ./data/single-soma.swc --write
```

### `swcstudio geometry move-node <file> --node-id N --x X --y Y --z Z`

- Purpose: move one node to absolute coordinates

### `swcstudio geometry move-subtree <file> --root-id N --x X --y Y --z Z`

- Purpose: move a whole subtree by setting the subtree root to absolute coordinates

### `swcstudio geometry connect <file> --start-id A --end-id B`

- Purpose: connect nodes by setting `parent(end) = start`

### `swcstudio geometry disconnect <file> --start-id A --end-id B`

- Purpose: disconnect every parent-child edge along the path between start and end

### `swcstudio geometry delete-node <file> --node-id N`

- Purpose: delete one node

Options:

- `--reconnect-children`
- `--write`
- `--out PATH`

### `swcstudio geometry delete-subtree <file> --root-id N`

- Purpose: delete one subtree

### `swcstudio geometry insert <file> --start-id A [--end-id B] --x X --y Y --z Z`

- Purpose: insert a new node after start and optionally before end

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

Typical reports include:

- `*_validation_report.txt`
- `*_batch_validation_report.txt`
- `*_index_clean_report.txt`
- `split_report.txt`
- `*_radii_cleaning_report.txt`
- `*_auto_typing_report.txt`
- `*_simplification_log.txt`

## Exit Codes

- `0`: success
- `1`: usage error / parse error
- `2`: runtime error
