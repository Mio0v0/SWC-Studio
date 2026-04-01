# Tool Tutorials

This page walks through each top-level tool with practical workflows.

OS note: replace `./data/...` with `.\data\...` on Windows. If `swcstudio` is not on PATH, use module mode (`python -m swcstudio.cli.cli ...` on macOS/Linux, `py -m swcstudio.cli.cli ...` on Windows).

## Tool -> Feature map

## 0) Issue Check

- GUI-style issue list (`check`)

## 1) Batch Processing

- Batch Validation (`batch validate`)
- SWC Splitter (`batch split`)
- Auto Typing (`batch auto-typing`)
- Radii Cleaning (`batch radii-clean`)
- Simplification (`batch simplify`)
- Index Clean (`batch index-clean`)

## 2) Validation

- Rule Guide (`validation rule-guide`)
- Run Checks (`validation run`)
- Auto Fix (`validation auto-fix`)
- Radii Cleaning (`validation radii-clean`)
- Index Clean (`validation index-clean`)

## 3) Visualization

- Mesh Editing (`visualization mesh-editing`)

## 4) Morphology Editing

- Dendrogram Edit (`morphology dendrogram-edit`)
- Manual Radii (`morphology set-radius`)

## 5) Geometry Editing

- Simplification (`geometry simplify`)
- Move Node (`geometry move-node`)
- Move Subtree (`geometry move-subtree`)
- Connect (`geometry connect`)
- Disconnect (`geometry disconnect`)
- Delete Node / Subtree (`geometry delete-node`, `geometry delete-subtree`)
- Insert Node (`geometry insert`)

---

## Issue Check Tutorial

Print the same combined issue list the GUI builds when a file is opened:

```bash
swcstudio check ./data/single-soma.swc
```

What it includes:

- validation issues
- suspicious radii
- likely wrong labels
- simplification suggestion

## Batch Processing Tutorials

### A. Batch Validation on a folder

```bash
swcstudio batch validate ./data
```

What it does:

- runs full validation for each `.swc` in folder
- prints pre-check summary first
- prints per-file grouped results
- writes one batch report file

Show guide only:

```bash
swcstudio batch validate rule-guide
```

### B. Split all multi-tree SWC files

```bash
swcstudio batch split ./data
```

Output pattern (default):

- folder: `./data/data_split`
- files: `<original_stem>_tree1.swc`, `<original_stem>_tree2.swc`, ...
- report: `split_report.txt`

### C. Batch Auto Typing

```bash
swcstudio batch auto-typing ./data --soma --axon --basal
```

Behavior:

- prints auto-typing rule guide before run
- writes outputs into `<folder>/<folder>_auto_typing`
- writes `auto_typing_report.txt`

### D. Batch Radii Cleaning

```bash
swcstudio batch radii-clean ./data
```

Behavior:

- uses the shared path-aware radii-cleaning backend
- reads defaults from `swcstudio/tools/batch_processing/configs/radii_cleaning.json`
- supports temporary JSON overrides through `--config-json`

### E. Batch Simplification

```bash
swcstudio batch simplify ./data
```

### F. Batch Index Clean

```bash
swcstudio batch index-clean ./data
```

---

## Validation Tutorials

### A. Show Validation Rule Guide

```bash
swcstudio validation rule-guide
```

### B. Validate one SWC

```bash
swcstudio validation run ./data/single-soma.swc
```

### C. Auto-fix one SWC

```bash
swcstudio validation auto-fix ./data/single-soma.swc --write
```

Use custom output path:

```bash
swcstudio validation auto-fix ./data/single-soma.swc --write --out ./data/single-soma_fixed.swc
```

### D. Validation Radii Cleaning

```bash
swcstudio validation radii-clean ./data/single-soma.swc
```

### E. Validation Index Clean

```bash
swcstudio validation index-clean ./data/single-soma.swc --write
```

---

## Visualization Tutorial

Build mesh payload summary from one SWC:

```bash
swcstudio visualization mesh-editing ./data/single-soma.swc --include-edges
```

Used mainly as backend payload for GUI rendering workflows.

---

## Morphology Editing Tutorials

### A. Dendrogram subtree reassignment

```bash
swcstudio morphology dendrogram-edit ./data/single-soma.swc --node-id 42 --new-type 3 --write
```

### B. Manual Radius Edit

```bash
swcstudio morphology set-radius ./data/single-soma.swc --node-id 42 --radius 0.75 --write
```

---

## Geometry Editing Tutorials

### A. Simplification

```bash
swcstudio geometry simplify ./data/single-soma.swc --write
```

Prints the simplification rule guide before processing and writes a simplification log.

### B. Connect two nodes

```bash
swcstudio geometry connect ./data/single-soma.swc --start-id 10 --end-id 22 --write
```

### C. Disconnect a path

```bash
swcstudio geometry disconnect ./data/single-soma.swc --start-id 10 --end-id 22 --write
```

### D. Move a subtree

```bash
swcstudio geometry move-subtree ./data/single-soma.swc --root-id 40 --x 100 --y 120 --z 5 --write
```

## Config override pattern

Most commands support inline temporary overrides:

```bash
swcstudio validation run ./data/single-soma.swc --config-json '{"checks":{"has_soma":{"enabled":true,"severity":"warning","params":{}}}}'
```

Persistent defaults live in:

- `swcstudio/tools/<tool>/configs/*.json`
