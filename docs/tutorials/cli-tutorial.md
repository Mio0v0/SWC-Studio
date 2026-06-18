# CLI Tutorial

This tutorial walks through the current command-line workflow for inspecting a file, applying edits, and reviewing history/results.

## Before you start

```{note}
You need a working CLI install and one or more SWC files. If the command is not on your path, use module mode from [Getting Started](../GETTING_STARTED.md).
```

The examples below use macOS or Linux path style. On Windows, replace
`./swc-folder/...` with `.\swc-folder\...`.

## Step 1: Verify the CLI

```bash
swcstudio --help
```

Module-mode fallback:

```bash
python -m swcstudio.cli.cli --help
```

## Step 2: Inspect one file with `check`

Start with the combined issue view:

```bash
swcstudio check cell.swc
```

This command prints the same shared issue list logic used by the GUI. It is the fastest way to see:

- validation findings
- suspicious radii suggestions
- likely wrong-label suggestions
- simplification suggestions

## Step 3: Run grouped validation

```bash
swcstudio validate cell.swc
```

Use this when you want the full grouped validation report rather than the broader issue summary from `check`.

If you only want the validation guide:

```bash
swcstudio rule-guide
```

## Step 4: Apply a targeted edit

Choose the command that matches the issue you want to fix.

Examples:

```bash
swcstudio index-clean cell.swc
swcstudio auto-fix cell.swc
swcstudio auto-label cell.swc
swcstudio auto-label cell.swc --model-dir ~/my-models   # custom-trained models
swcstudio auto-label cell.swc --cell-type pyramidal --flag-strictness 0.8
swcstudio auto-label cell.swc --no-flag
swcstudio set-type cell.swc --node-id 14169 --new-type 3
swcstudio set-radius cell.swc --node-id 42 --radius 0.75
swcstudio connect cell.swc --start-id 10 --end-id 22
```

Single-file edit commands automatically write:

- the updated source SWC file
- an operation record in `<stem>_history.swcstudio`

The source SWC receives compact `# @PROV` pointer lines, and existing
SWC/SWC+ comment headers are preserved.
Auto-label uses the v12 QC-label-flag engine. Leave cell type as
unknown to run Stage 1, or pass `--cell-type pyramidal` /
`--cell-type interneuron` when the user already knows the type.

## Step 5: Use batch commands for folders

When you need the same operation across many files, use folder commands.

Examples:

```bash
swcstudio validate ./swc-folder
swcstudio split ./swc-folder
swcstudio auto-typing ./swc-folder
swcstudio auto-typing ./swc-folder --model-dir ~/my-models   # custom-trained models
swcstudio auto-typing ./swc-folder --cell-type unknown --flag-strictness 0.5
swcstudio radii-clean ./swc-folder
swcstudio simplify ./swc-folder
swcstudio index-clean ./swc-folder
```

Mutating batch commands update each processed source SWC in place and
record operation history for each file. `split` is the main exception
because it intentionally creates new derived SWC files.

## Step 5b: Train your own auto-typing models

If you have a labeled SWC corpus, you can train the three core custom
models tuned to your data: Stage 1, Stage 2, and the Stage 2b GNN.

```bash
swcstudio train auto-typing --data-dir ./labeled --output-dir ./my-models
# Inspect what landed:
swcstudio models status --model-dir ./my-models
# Use the new models for one run:
swcstudio auto-label cell.swc --model-dir ./my-models
```

The dataset layout must be:

```
labeled/
    pyramidal/   *.swc
    interneuron/ *.swc
```

The standard `python -m pip install -e .` already includes torch and
torch_geometric, so GNN training works out of the box. Use `--no-gnn`
only when you want to refresh Stages 1+2 against an existing
`gnn_apical_basal.pt` checkpoint that's already in `--output-dir`.

The bundled production auto-labeler also uses Branch3, QC, and flag
artifacts. The custom-training command currently trains the core
Stage 1 + Stage 2 + Stage 2b stack only.

To make your custom models the new default everywhere (no `--model-dir`
flag needed), copy them into your user data directory — see the
[Auto-Typing Engine](../documentation/auto-typing-backends.md#training-custom-models)
page for the per-platform path.

## Step 6: Use temporary config overrides

Most commands accept `--config-json` so you can override parameters for one run without editing the default config files.

Example:

```bash
swcstudio simplify cell.swc --config-json '{"thresholds":{"epsilon":1.2,"radius_tolerance":0.35}}'
```

## Step 7: Review history and outputs

For mutating edits, look next to the source SWC:

- `<stem>.swc`
- `<stem>_history.swcstudio`

Use history commands to inspect or materialize previous states:

```bash
swcstudio history log cell.swc
swcstudio history show cell.swc op-1
swcstudio history checkpoint cell.swc op-1 --label review
```

`history log` prints operation IDs such as `op-1`. Add
`--technical` if you need exact version/SHA details for debugging or
reproducibility.

Validation/report-only commands can still write text reports, and
`split` writes separate derived SWC files.

## Related pages

- [CLI Reference](../CLI_REFERENCE.md)
- [Logs And Reports](../LOGS_AND_REPORTS.md)
- [Checks And Issues Reference](../CHECKS_AND_ISSUES_REFERENCE.md)
