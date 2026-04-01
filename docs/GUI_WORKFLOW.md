# GUI Workflow Guide

This page explains the current GUI structure and the intended issue-driven repair workflow.

## Layout model

The GUI uses a studio-style layout with shared backend logic:

- top in-app bar: file/edit/view/window/help menus + tool and feature selectors
- center canvas: active SWC visualization/editor tabs
- left panel: Issue Navigator / SWC File / Segment Info
- right panel: Inspector (issue detail on top, active tool controls below)
- bottom panel: log output/events

The center canvas is the dominant workspace and updates based on current tool/feature.

## Tool and feature switching

Top-level tools:

- Batch Processing
- Validation
- Visualization
- Morphology Editing
- Geometry Editing
- Atlas Registration
- Analysis

When a tool is active, feature buttons are shown for that tool.
The selected feature controls what appears in the lower Inspector area.

### Feature mapping in GUI

- Batch Processing: Split, Validation, Auto Label Editing, Radii Cleaning, Simplification, Index Clean
- Validation: Validation, Index Clean
- Visualization: View Controls
- Morphology Editing: Manual Label Editing, Auto Label Editing, Manual Radii Editing, Auto Radii Editing, Simplification
- Geometry Editing: Geometry Editing
- Atlas Registration: Registration (placeholder)
- Analysis: Summary (placeholder)

## Document/canvas behavior

- Multiple SWC files can be open in separate canvas tabs.
- Preview outputs (for some operations) open as temporary comparison tabs.
- Closing a changed tab triggers save/discard flow and session logging.

## Recommended GUI usage sequence

1. Open an SWC file from the File menu.
2. Run **Validation** and review the Issue Navigator on the left.
3. Click an issue to focus the affected nodes and jump to the matching repair feature.
4. Fix the issue in the suggested feature, such as **Index Clean**, **Manual Label Editing**, **Auto Label Editing**, **Manual Radii Editing**, **Auto Radii Editing**, or **Geometry Editing**.
5. Rerun validation and continue until the issue list is cleared or reduced to acceptable warnings.
6. Save the cleaned SWC for downstream analysis, batch processing, or further editing.

This is the intended desktop workflow:

- validation surfaces structural and annotation problems
- the Issue Navigator shows what needs attention
- the app directs you to the corresponding fix tool
- once the issues are resolved, the SWC is ready for downstream work

## Validation in GUI

Validation panel supports:

- Rule Guide button (manual display; no forced popup)
- Run Validation
- Index Clean as a separate Validation feature
- results table with status/label
- report export controls

Validation uses the same backend as CLI (`swctools.tools.validation` + core engine).

## Auto Typing in GUI

- Batch mode: folder-level auto label editing
- Validation mode: single-file auto label editing
- JSON editor for rule parameters
- shared backend logic (same as CLI/API)
- branch-consistent labeling from the soma boundary
- one primary axon winner and one primary apical winner when enabled
- primary subtree inheritance, so a labeled subtree keeps one neurite class downstream
- far-from-soma penalty against unlikely basal assignments

## Radii Editing in GUI

- shared backend for Batch + Validation + CLI
- `Manual Radii Editing` supports one-node edits with type-level statistics
- `Auto Radii Editing` supports distribution-based cleanup
- thresholds configurable via JSON
- histogram/statistics visualization for currently loaded file

## Simplification in GUI

- RDP-based Smart Decimation controls in Morphology Editing
- process creates a simplified preview/result path
- action bar supports apply/redo/cancel behavior
- outputs include simplification log with node reduction stats and parameters

## Logs and status

- transient status: status bar and bottom log
- persistent logs: text report files written by backend reporting layer

See [LOGS_AND_REPORTS](LOGS_AND_REPORTS.md) for full report naming conventions.
