# User Guide

This section explains how to use `SWC-Studio` as it behaves today in the GUI, CLI, and shared backend.

```{toctree}
:hidden:
:maxdepth: 2

setup
workflows
validation-and-repair
custom-types-and-labels
reports-and-outputs
```

## Start Here

If you are new to the project, read these pages first:

- [Setup](setup.md)
- [Workflows](workflows.md)
- [Validation and Repair](validation-and-repair.md)

## What the User Guide Covers

The guide is organized around the main user-facing behavior of the application:

- how files are loaded and inspected
- how the issue-driven workflow works
- how validation findings become repair suggestions
- how custom labels persist across sessions
- where outputs, saved copies, and logs are written

## Current Workflow Model

`SWC-Studio` is not organized as separate GUI-only and CLI-only feature sets. The GUI and CLI call the same tool and core code paths, so the same validation logic, repair logic, and report builders are reused across interfaces.

Use this section when you want to understand:

- what happens when a file is opened in the GUI
- how the issue list is built
- which repair tools correspond to which issue categories
- how CLI edit commands write outputs and logs
