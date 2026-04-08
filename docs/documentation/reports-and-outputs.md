# Reports and Outputs

This page explains where `SWC-Studio` writes outputs and how logs are structured.

```{toctree}
:hidden:
:maxdepth: 1

Logs And Reports <../LOGS_AND_REPORTS>
```

## Shared reporting layer

The GUI and CLI use the same reporting helpers in `swcstudio.core.reporting`. That shared layer is responsible for:

- output directory naming
- operation report naming
- validation report formatting
- GUI session log formatting
- per-operation text logs for CLI edits

Because the report builders are shared, logs from different interfaces use the same conventions.

## Default single-file output directory

For a source file:

- `<parent>/<stem>.swc`

the default output directory is:

- `<parent>/<stem>_swc_studio_output/`

That directory is used for:

- validation reports
- single-file CLI edit results
- single-file CLI edit logs
- GUI session logs
- GUI saved copies

## Current CLI behavior for edit commands

Single-file edit commands write outputs automatically. You do not need a separate `--write` flag.

When you run single-file edit commands such as:

- `auto-fix`
- `auto-label`
- `radii-clean`
- `index-clean`
- `set-type`
- `dendrogram-edit`
- `set-radius`
- geometry commands such as `move-node`, `connect`, `disconnect`, `delete-node`, `insert`, or `simplify`

the CLI writes:

- an updated SWC file into the default output folder
- a matching text report into the same folder

## GUI session behavior

The GUI keeps a session-level log for a document.

Typical GUI outputs:

- session log
  - `<stem>_session_log_<timestamp>.txt`
- saved copy
  - `<stem>_closed_<timestamp>.swc`

Those files are also written into the default `*_swc_studio_output` directory for the source file.

## What the logs contain

Depending on the operation, reports can include:

- grouped validation summaries
- thresholds and metrics
- per-operation summaries
- node-level change tables
- software version information
- label legends, including saved custom type names, colors, and notes

That last point is important for custom labels: if you define custom type metadata in the GUI, the shared log builders can include those labels in generated reports.

## More detail

For the exact naming patterns and report helper list, use:

- [Logs And Reports](../LOGS_AND_REPORTS.md)
