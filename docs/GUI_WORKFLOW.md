# GUI Workflow Guide

This page explains the current desktop workflow and layout.

## Layout model

The GUI uses a studio-style layout with shared backend logic:

- top bar
  - menus, tool buttons, and feature buttons
- center workspace
  - open SWC document tabs and the main visualization/editor area
- left panel
  - `Issues`
  - `SWC File`
- right inspector
  - issue details and active tool controls
- bottom area
  - transient status and event output

The center workspace stays focused on the active document. The side panels change as the selected issue or active tool changes.

## Tool and feature switching

Top-level tools:

- Batch Processing
- Validation
- Visualization
- Morphology Editing
- Geometry Editing

Current feature mapping:

- Batch Processing
  - Split
  - Validation
  - Auto Label Editing
  - Radii Cleaning
  - Simplification
  - Index Clean
- Validation
  - Validation
  - Index Clean
- Visualization
  - View Controls
- Morphology Editing
  - Manual Label Editing
  - Auto Label Editing
  - Manual Radii Editing
  - Auto Radii Editing
- Geometry Editing
  - Geometry Editing
  - Simplification

## What happens when a file is opened

When you open an SWC file:

1. the file is loaded into a document tab
2. the active tool panels are synchronized to that document
3. validation is run automatically for a normal editable document when no validation report exists yet
4. the resulting report is converted into the shared issue list

That automatic validation step is why the GUI can immediately present an issue-oriented workflow after a file is loaded.

## Issue-driven repair flow

The intended desktop loop is:

1. open an SWC file
2. review the `Issues` panel
3. click one issue
4. inspect the problem and suggested action in the right inspector
5. let the app route you to the matching repair tool
6. apply the repair
7. rerun validation
8. review the new per-file history operation and any requested reports

### What the issue list includes

The issue list can include:

- validation findings
- blocked prerequisite summaries
- suspicious radii suggestions
- likely wrong-label suggestions
- a simplification suggestion

### How issue routing behaves

Typical routing behavior:

- index issues
  - `Validation -> Index Clean`
- label issues
  - `Morphology Editing`
- radii issues
  - `Manual Radii Editing` or `Auto Radii Editing`
- topology and geometry issues
  - `Geometry Editing`

Some checks use popup-only actions. For example, if a file contains custom type IDs that are not yet defined, the GUI can open the custom type definition dialog rather than only switching tabs.

## Custom types in the GUI

Custom types are managed from dendrogram editing with `Add/Edit Types`.

Users can define:

- type ID
- name
- color
- notes

These definitions are written to the persistent custom type registry, so they remain available after closing and reopening the application.

See [Custom Types and Labels](documentation/custom-types-and-labels.md) for the exact storage behavior and log integration.

## Saving, history, and outputs

The GUI writes tracked morphology edits directly back to the source SWC
and records the operation history in the encrypted sidecar archive.

Important current behavior:

- the source SWC receives compact `# @PROV` pointer lines
- the history archive is stored as `<stem>_history.swcstudio` next to the SWC
- the History Browser opens on Operation History; each file numbers its operations independently as `op-1`, `op-2`, `op-3`, and so on
- operation rows have expandable node-level changes
- undoing an operation restores the state before it, removing that operation and all later operations from the current state
- the new restore operation records which operation/version it restored from
- interactive Undo/Redo keeps at most 20 in-memory steps and stores row-level deltas instead of retaining a full SWC dataframe for every edit
- advanced users can change the in-memory step limit with the `SWCSTUDIO_UNDO_LIMIT` environment variable before launching the GUI
- after applying Auto Label Editing, the next validation reuses that result instead of launching duplicate type-suspicion inference
- the Commit History tab keeps exact version IDs and SHA details for technical review
- mutating GUI batch tools process and record each source SWC independently
- validation and report-only exports can still create text reports when requested

See [Logs And Reports](LOGS_AND_REPORTS.md) for the naming conventions.
