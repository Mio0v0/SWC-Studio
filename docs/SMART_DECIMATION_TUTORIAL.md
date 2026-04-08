# Simplification Tutorial

Simplification reduces redundant SWC geometry while preserving the main tree structure.

This page keeps the older filename for compatibility, but the current feature name in the app is `Simplification`.

## Backend and config

Current implementation path:

- `swcstudio.tools.morphology_editing.features.simplification`

Current config file:

- `swcstudio/tools/morphology_editing/configs/simplification.json`

## Main parameters

- `thresholds.epsilon`
- `thresholds.radius_tolerance`
- `flags.keep_tips`
- `flags.keep_bifurcations`
- `flags.keep_roots`

## Parameter guidance

- lower `epsilon`
  - keeps more geometry detail
- higher `epsilon`
  - removes more intermediate points
- lower `radius_tolerance`
  - protects more radius-sensitive nodes
- higher `radius_tolerance`
  - allows stronger decimation around radius variation

## CLI usage

Run simplification on one file:

```bash
swcstudio simplify ./data/single-soma.swc
```

Use temporary overrides for one run:

```bash
swcstudio simplify ./data/single-soma.swc --config-json '{"thresholds":{"epsilon":1.2,"radius_tolerance":0.35},"flags":{"keep_tips":true,"keep_bifurcations":true}}'
```

Current single-file behavior:

- the simplified SWC is written automatically
- the matching simplification log is written automatically
- both go into the source file's `*_swc_studio_output` directory

## GUI usage

In `Geometry Editing -> Simplification`:

1. open the source SWC
2. adjust the JSON config if needed
3. run simplification
4. review the updated morphology
5. save or close the document to keep the session log and saved copy
