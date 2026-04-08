# GUI Tutorial

This tutorial walks through the main desktop workflow for reviewing one SWC file, letting issues guide the repair process, and saving the result.

## Before you start

```{note}
You need a working GUI install and at least one SWC file. If needed, start with [Getting Started](../GETTING_STARTED.md).
```

Start the application:

```bash
swcstudio-gui
```

## Step 1: Open a file

Open an SWC file from the `File` menu.

After loading:

- the file appears in the central workspace
- the left-side `Issues` and `SWC File` panels are populated for the active document
- validation is triggered automatically for a normal editable document when no prior validation report exists

## Step 2: Review the issue list

The `Issues` panel is the center of the desktop workflow.

It can include:

- validation findings
- blocked prerequisite summaries
- suspicious radii suggestions
- likely wrong-label suggestions
- a simplification suggestion

This means the panel acts as a guided repair queue, not only as a validation dump.

## Step 3: Select one issue

When you click an issue, the GUI:

1. focuses the relevant nodes in the active document
2. updates the inspector with the issue description and suggested solution
3. routes the right-side controls to the matching repair tool when appropriate

Examples:

- index issues route to `Validation -> Index Clean`
- label issues route to `Morphology Editing`
- radii issues route to radii editing controls
- topology issues route to geometry editing

## Step 4: Apply a repair

Use the routed tool to apply the fix.

Common repair paths:

- `Index Clean`
- `Manual Label Editing`
- `Auto Label Editing`
- `Manual Radii Editing`
- `Auto Radii Editing`
- `Geometry Editing`
- `Simplification`

## Step 5: Define custom types when needed

If your file uses custom SWC type IDs, define them from the dendrogram editing controls with `Add/Edit Types`.

Each custom type can store:

- type ID
- name
- color
- notes

These definitions persist across restarts, so once they are saved they remain available the next time you open the app.

## Step 6: Rerun validation

After a repair, rerun validation and review the refreshed issue list.

This is the main loop:

1. inspect
2. route
3. repair
4. validate again

Continue until the important issues are resolved or reduced to acceptable warnings for your workflow.

## Step 7: Save and review outputs

Save the document or close the tab.

The GUI writes:

- a saved SWC copy
- a session log

Both are written into the source file's `*_swc_studio_output` directory.

The shared report layer can include custom label legends in those logs when custom type definitions exist.

## Related pages

- [GUI Workflow Guide](../GUI_WORKFLOW.md)
- [Custom Types and Labels](../documentation/custom-types-and-labels.md)
- [Checks And Issues Reference](../CHECKS_AND_ISSUES_REFERENCE.md)
- [Logs And Reports](../LOGS_AND_REPORTS.md)
