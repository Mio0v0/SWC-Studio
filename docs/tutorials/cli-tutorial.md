# CLI Tutorial

This tutorial walks through the current command-line workflow for inspecting a file, applying edits, and reviewing the generated outputs.

## Before you start

```{note}
You need a working CLI install and one or more SWC files. If the command is not on your path, use module mode from [Getting Started](../GETTING_STARTED.md).
```

The examples below use macOS or Linux path style. On Windows, replace `./data/...` with `.\data\...`.

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
swcstudio check ./data/single-soma.swc
```

This command prints the same shared issue list logic used by the GUI. It is the fastest way to see:

- validation findings
- suspicious radii suggestions
- likely wrong-label suggestions
- simplification suggestions

## Step 3: Run grouped validation

```bash
swcstudio validate ./data/single-soma.swc
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
swcstudio index-clean ./data/single-soma.swc
swcstudio auto-fix ./data/single-soma.swc
swcstudio auto-label ./data/single-soma.swc
swcstudio auto-label ./data/single-soma.swc --model-dir ~/my-models   # custom-trained models
swcstudio auto-label ./data/single-soma.swc --cell-type pyramidal --flag-strictness 0.8
swcstudio auto-label ./data/single-soma.swc --no-flag
swcstudio set-type ./data/single-soma.swc --node-id 14169 --new-type 3
swcstudio set-radius ./data/single-soma.swc --node-id 42 --radius 0.75
swcstudio connect ./data/single-soma.swc --start-id 10 --end-id 22
```

Single-file edit commands automatically write:

- the updated SWC file
- the matching operation log

to the default `*_swc_studio_output` directory for the source file.
Auto-label uses the v12 QC-label-flag engine. Leave cell type as
unknown to run Stage 1, or pass `--cell-type pyramidal` /
`--cell-type interneuron` when the user already knows the type.

## Step 5: Use batch commands for folders

When you need the same operation across many files, use folder commands.

Examples:

```bash
swcstudio validate ./data
swcstudio split ./data
swcstudio auto-typing ./data
swcstudio auto-typing ./data --model-dir ~/my-models   # custom-trained models
swcstudio auto-typing ./data --cell-type unknown --flag-strictness 0.5
swcstudio radii-clean ./data
swcstudio simplify ./data
swcstudio index-clean ./data
```

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

The standard `pip install -e .` already includes torch and
torch_geometric, so GNN training works out of the box. Use `--no-gnn`
only when you want to refresh Stages 1+2 against an existing
`gnn_apical_basal.pt` checkpoint that's already in `--output-dir`.

The bundled production auto-labeler also uses Branch3, QC, and flag
artifacts. The custom-training command currently trains the core
Stage 1 + Stage 2 + Stage 2b stack only.

To make your custom models the new default everywhere (no `--model-dir`
flag needed), copy them into your user data directory — see the
[Auto-Typing Engine](../documentation/auto-typing-backends.md#using-your-custom-models)
page for the per-platform path.

## Step 6: Use temporary config overrides

Most commands accept `--config-json` so you can override parameters for one run without editing the default config files.

Example:

```bash
swcstudio simplify ./data/single-soma.swc --config-json '{"thresholds":{"epsilon":1.2,"radius_tolerance":0.35}}'
```

## Step 7: Review outputs and logs

For single-file edits, open the source file's default output folder:

- `<stem>_swc_studio_output`

Typical files there include:

- edited SWC copies
- validation reports
- per-operation text logs

## Related pages

- [CLI Reference](../CLI_REFERENCE.md)
- [Logs And Reports](../LOGS_AND_REPORTS.md)
- [Checks And Issues Reference](../CHECKS_AND_ISSUES_REFERENCE.md)
