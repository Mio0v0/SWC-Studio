# Tool Tutorials

This page walks through each top-level tool with practical workflows.

OS note: replace `./data/...` with `.\data\...` on Windows. If `swctools` is not on PATH, use module mode (`python -m swctools.cli.cli ...` on macOS/Linux, `py -m swctools.cli.cli ...` on Windows).

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
swctools check ./data/single-soma.swc
```

What it includes:

- validation issues
- suspicious radii
- likely wrong labels
- simplification suggestion

## Batch Processing Tutorials

### A. Batch Validation on a folder

```bash
swctools batch validate ./data
```

What it does:

- runs full validation for each `.swc` in folder
- prints pre-check summary first
- prints per-file grouped results
- writes one batch report file

Show guide only:

```bash
swctools batch validate rule-guide
```

### B. Split all multi-tree SWC files

```bash
swctools batch split ./data
```

Output pattern (default):

- folder: `./data/data_split`
- files: `<original_stem>_tree1.swc`, `<original_stem>_tree2.swc`, ...
- report: `split_report.txt`

### C. Batch Auto Typing

```bash
swctools batch auto-typing ./data --soma --axon --basal
```

Behavior:

- prints auto-typing rule guide before run
- writes outputs into `<folder>/<folder>_auto_typing`
- writes `auto_typing_report.txt`

### D. Batch Radii Cleaning

```bash
swctools batch radii-clean ./data
```

Behavior:

- uses the shared path-aware radii-cleaning backend
- reads defaults from `swctools/tools/batch_processing/configs/radii_cleaning.json`
- supports temporary JSON overrides through `--config-json`

### E. Batch Simplification

```bash
swctools batch simplify ./data
```

### F. Batch Index Clean

```bash
swctools batch index-clean ./data
```

---

## Validation Tutorials

### A. Show Validation Rule Guide

```bash
swctools validation rule-guide
```

### B. Validate one SWC

```bash
swctools validation run ./data/single-soma.swc
```

### C. Auto-fix one SWC

```bash
swctools validation auto-fix ./data/single-soma.swc --write
```

Use custom output path:

```bash
swctools validation auto-fix ./data/single-soma.swc --write --out ./data/single-soma_fixed.swc
```

### D. Validation Radii Cleaning

```bash
swctools validation radii-clean ./data/single-soma.swc
```

### E. Validation Index Clean

```bash
swctools validation index-clean ./data/single-soma.swc --write
```

---

## Visualization Tutorial

Build mesh payload summary from one SWC:

```bash
swctools visualization mesh-editing ./data/single-soma.swc --include-edges
```

Used mainly as backend payload for GUI rendering workflows.

---

## Morphology Editing Tutorials

### A. Dendrogram subtree reassignment

```bash
swctools morphology dendrogram-edit ./data/single-soma.swc --node-id 42 --new-type 3 --write
```

### B. Manual Radius Edit

```bash
swctools morphology set-radius ./data/single-soma.swc --node-id 42 --radius 0.75 --write
```

---

## Geometry Editing Tutorials

### A. Simplification

```bash
swctools geometry simplify ./data/single-soma.swc --write
```

Prints rule guide before processing and writes simplification log.

### B. Connect two nodes

```bash
swctools geometry connect ./data/single-soma.swc --start-id 10 --end-id 22 --write
```

### C. Disconnect a path

```bash
swctools geometry disconnect ./data/single-soma.swc --start-id 10 --end-id 22 --write
```

### D. Move a subtree

```bash
swctools geometry move-subtree ./data/single-soma.swc --root-id 40 --x 100 --y 120 --z 5 --write
```

## Config override pattern

Most commands support inline temporary overrides:

```bash
swctools validation run ./data/single-soma.swc --config-json '{"checks":{"has_soma":{"enabled":true,"severity":"warning","params":{}}}}'
```

Persistent defaults live in:

- `swctools/tools/<tool>/configs/*.json`
