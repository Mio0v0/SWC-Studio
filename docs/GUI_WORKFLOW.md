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
8. save or close the document to write logs and outputs

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

## Saving, logs, and outputs

The GUI writes outputs through the shared reporting layer.

Important current behavior:

- saved copies and session logs go into the source file's `*_swc_studio_output` directory
- logs use the same shared formatting conventions as CLI operation reports
- custom type legends can appear in generated logs when custom definitions exist

See [Logs And Reports](LOGS_AND_REPORTS.md) for the naming conventions.
