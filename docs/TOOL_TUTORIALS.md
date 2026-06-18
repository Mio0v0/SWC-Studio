# CLI Task Guide

This page groups the current CLI command surface by task.

It is a quick practical companion to the full [CLI Reference](CLI_REFERENCE.md).

## Inspect one file

```bash
swcstudio check cell.swc
swcstudio validate cell.swc
swcstudio rule-guide
```

## Repair one file

Validation-oriented edits:

```bash
swcstudio auto-fix cell.swc
swcstudio auto-label cell.swc
swcstudio radii-clean cell.swc
swcstudio index-clean cell.swc
```

Morphology edits:

```bash
swcstudio set-type cell.swc --node-id 14169 --new-type 3
swcstudio dendrogram-edit cell.swc --node-id 42 --new-type 3
swcstudio set-radius cell.swc --node-id 42 --radius 0.75
```

Geometry edits:

```bash
swcstudio simplify cell.swc
swcstudio connect cell.swc --start-id 10 --end-id 22
swcstudio disconnect cell.swc --start-id 10 --end-id 22
swcstudio move-subtree cell.swc --root-id 40 --x 100 --y 120 --z 5
```

Current single-file edit behavior:

- auto-label always applies soma, axon, and basal labeling
- apical labeling is detected automatically when appropriate
- `--cell-type pyramidal` / `--cell-type interneuron` bypasses Stage 1 when the user already knows the cell type
- flag scoring is enabled by default; `--flag-strictness` tunes loose vs conservative flagging and `--no-flag` disables it
- the source SWC is updated automatically
- the operation is recorded in `<stem>_history.swcstudio`
- SWC/SWC+ comment headers are preserved while `# @PROV` pointers are updated

## Process a folder

```bash
swcstudio validate ./swc-folder
swcstudio split ./swc-folder
swcstudio auto-typing ./swc-folder
swcstudio radii-clean ./swc-folder
swcstudio simplify ./swc-folder
swcstudio index-clean ./swc-folder
```

## Use temporary config overrides

```bash
swcstudio validate cell.swc --config-json '{"checks":{"has_soma":{"enabled":true,"severity":"warning","params":{}}}}'
```

## Related pages

- [CLI Reference](CLI_REFERENCE.md)
- [CLI Tutorial](tutorials/cli-tutorial.md)
- [Logs And Reports](LOGS_AND_REPORTS.md)
