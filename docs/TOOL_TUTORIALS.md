# Tool Tutorials

This page walks through the current public CLI workflows with practical examples.

OS note: replace `./data/...` with `.\data\...` on Windows. If `swcstudio` is not on PATH, use module mode (`python -m swcstudio.cli.cli ...` on macOS/Linux, `py -m swcstudio.cli.cli ...` on Windows).

## Direct Command Map

## 0) Issue Check

- GUI-style issue list (`check`)

## 1) Folder Workflows

- Batch Validation (`validate <folder>`)
- SWC Splitter (`split <folder>`)
- Auto Typing (`auto-typing <folder>`)
- Radii Cleaning (`radii-clean <folder>`)
- Simplification (`simplify <folder>`)
- Index Clean (`index-clean <folder>`)

## 2) Single-File Validation and Cleanup

- Rule Guide (`rule-guide`)
- Run Validation (`validate <file>`)
- Auto Fix (`auto-fix <file>`)
- Auto Label (`auto-label <file>`)
- Radii Cleaning (`radii-clean <file>`)
- Index Clean (`index-clean <file>`)

## 3) Visualization

- Mesh Editing (`mesh-editing`)

## 4) Morphology Editing

- Manual Label (`set-type`)
- Dendrogram Edit (`dendrogram-edit`)
- Manual Radii (`set-radius`)

## 5) Geometry Editing

- Simplification (`simplify <file>`)
- Move Node (`move-node`)
- Move Subtree (`move-subtree`)
- Connect (`connect`)
- Disconnect (`disconnect`)
- Delete Node / Subtree (`delete-node`, `delete-subtree`)
- Insert Node (`insert`)

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

## Folder Workflow Tutorials

### A. Batch Validation on a folder

```bash
swcstudio validate ./data
```

What it does:

- runs full validation for each `.swc` in folder
- prints pre-check summary first
- prints per-file grouped results
- writes one batch report file

Show guide only:

```bash
swcstudio validate rule-guide
```

### B. Split all multi-tree SWC files

```bash
swcstudio split ./data
```

Output pattern (default):

- folder: `./data/data_batch_split_<timestamp>`
- files: `<original_stem>_batch_split_tree_<index>_<timestamp>.swc`
- report: `data_batch_split_<timestamp>.txt`

### C. Batch Auto Typing

```bash
swcstudio auto-typing ./data --soma --axon --basal
```

Behavior:

- prints auto-typing rule guide before run
- writes outputs into `<folder>/<folder>_batch_auto_typing_<timestamp>`
- writes `<folder>_batch_auto_typing_<timestamp>.txt`

### D. Batch Radii Cleaning

```bash
swcstudio radii-clean ./data
```

Behavior:

- uses the shared path-aware radii-cleaning backend
- reads defaults from `swcstudio/tools/batch_processing/configs/radii_cleaning.json`
- supports temporary JSON overrides through `--config-json`

### E. Batch Simplification

```bash
swcstudio simplify ./data
```

### F. Batch Index Clean

```bash
swcstudio index-clean ./data
```

---

## Single-File Validation and Cleanup Tutorials

### A. Show Validation Rule Guide

```bash
swcstudio rule-guide
```

### B. Validate one SWC

```bash
swcstudio validate ./data/single-soma.swc
```

### C. Auto-fix one SWC

```bash
swcstudio auto-fix ./data/single-soma.swc --write
```

Use custom output path:

```bash
swcstudio auto-fix ./data/single-soma.swc --write --out ./data/single-soma_fixed.swc
```

### D. Validation Radii Cleaning

```bash
swcstudio radii-clean ./data/single-soma.swc
```

### E. Validation Auto Label

```bash
swcstudio auto-label ./data/single-soma.swc --write
```

Behavior:

- uses the same single-file auto label logic as the GUI Auto Label Editing panel
- changes only node types
- writes a GUI-style operation report with a node-change table

### F. Validation Index Clean

```bash
swcstudio index-clean ./data/single-soma.swc --write
```

---

## Visualization Tutorial

Build mesh payload summary from one SWC:

```bash
swcstudio mesh-editing ./data/single-soma.swc --include-edges
```

Used mainly as backend payload for GUI rendering workflows.

---

## Morphology Editing Tutorials

### A. Manual single-node label edit

```bash
swcstudio set-type ./data/single-soma.swc --node-id 14169 --new-type 3 --write
```

### B. Dendrogram subtree reassignment

```bash
swcstudio dendrogram-edit ./data/single-soma.swc --node-id 42 --new-type 3 --write
```

### C. Manual Radius Edit

```bash
swcstudio set-radius ./data/single-soma.swc --node-id 42 --radius 0.75 --write
```

---

## Geometry Editing Tutorials

### A. Simplification

```bash
swcstudio simplify ./data/single-soma.swc --write
```

Prints the simplification rule guide before processing and writes one GUI-style operation report.

### B. Connect two nodes

```bash
swcstudio connect ./data/single-soma.swc --start-id 10 --end-id 22 --write
```

### C. Disconnect a path

```bash
swcstudio disconnect ./data/single-soma.swc --start-id 10 --end-id 22 --write
```

### D. Move a subtree

```bash
swcstudio move-subtree ./data/single-soma.swc --root-id 40 --x 100 --y 120 --z 5 --write
```

## Config override pattern

Most commands support inline temporary overrides:

```bash
swcstudio validate ./data/single-soma.swc --config-json '{"checks":{"has_soma":{"enabled":true,"severity":"warning","params":{}}}}'
```

Persistent defaults live in:

- `swcstudio/tools/<tool>/configs/*.json`
