# CLI Task Guide

This page groups the current CLI command surface by task.

It is a quick practical companion to the full [CLI Reference](CLI_REFERENCE.md).

## Inspect one file

```bash
swcstudio check ./data/single-soma.swc
swcstudio validate ./data/single-soma.swc
swcstudio rule-guide
```

## Repair one file

Validation-oriented edits:

```bash
swcstudio auto-fix ./data/single-soma.swc
swcstudio auto-label ./data/single-soma.swc
swcstudio radii-clean ./data/single-soma.swc
swcstudio index-clean ./data/single-soma.swc
```

Morphology edits:

```bash
swcstudio set-type ./data/single-soma.swc --node-id 14169 --new-type 3
swcstudio dendrogram-edit ./data/single-soma.swc --node-id 42 --new-type 3
swcstudio set-radius ./data/single-soma.swc --node-id 42 --radius 0.75
```

Geometry edits:

```bash
swcstudio simplify ./data/single-soma.swc
swcstudio connect ./data/single-soma.swc --start-id 10 --end-id 22
swcstudio disconnect ./data/single-soma.swc --start-id 10 --end-id 22
swcstudio move-subtree ./data/single-soma.swc --root-id 40 --x 100 --y 120 --z 5
```

Current single-file edit behavior:

- the updated SWC is written automatically
- the matching log is written automatically
- both go into the source file's `*_swc_studio_output` directory

## Process a folder

```bash
swcstudio validate ./data
swcstudio split ./data
swcstudio auto-typing ./data --soma --axon --basal
swcstudio radii-clean ./data
swcstudio simplify ./data
swcstudio index-clean ./data
```

## Use temporary config overrides

```bash
swcstudio validate ./data/single-soma.swc --config-json '{"checks":{"has_soma":{"enabled":true,"severity":"warning","params":{}}}}'
```

## Related pages

- [CLI Reference](CLI_REFERENCE.md)
- [CLI Tutorial](tutorials/cli-tutorial.md)
- [Logs And Reports](LOGS_AND_REPORTS.md)
