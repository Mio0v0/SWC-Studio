# Logs and Reports

`SWC-Studio` uses a shared reporting layer so GUI and CLI logs follow the same conventions.

Core module:

- `swcstudio.core.reporting`

## Why this matters

- one report style across interfaces
- predictable output folders
- easier audit trails for lab workflows

## Main report helpers

Examples of the shared builders:

- `format_validation_report_text`
- `format_batch_validation_report_text`
- `format_split_report_text`
- `format_auto_typing_report_text`
- `format_radii_cleaning_report_text`
- `format_simplification_report_text`
- `format_morphology_session_log_text`
- `format_operation_report_text`
- `write_text_report`

## Default naming

Single-file outputs use:

- output folder
  - `<input_folder>/<stem>_swc_studio_output/`
- output or report file
  - `<stem>_<operation_name>_<timestamp>.<ext>`

Batch outputs use:

- output folder
  - `<input_folder>/<input_folder>_<operation_name>_<timestamp>/`
- batch report
  - `<input_folder>_<operation_name>_<timestamp>.txt`

## Current single-file CLI behavior

Single-file edit commands automatically write both:

- an updated SWC file
- a matching text report

into the source file's default `*_swc_studio_output` directory.

This applies to commands such as:

- `auto-fix`
- `auto-label`
- `radii-clean`
- `index-clean`
- `set-type`
- `dendrogram-edit`
- `set-radius`
- geometry edit commands

## GUI session outputs

The GUI writes:

- session log
  - `<stem>_session_log_<timestamp>.txt`
- saved copy
  - `<stem>_closed_<timestamp>.swc`

into the same default single-file output directory.

## Typical report contents

Validation reports can include:

- grouped pass, warning, and fail rows
- thresholds and metrics
- failing node IDs and section IDs

Operation reports and GUI session logs can include:

- operation summary
- node-level change tables
- software version information
- label type legend

When custom type definitions exist, the label legend can include:

- custom type ID
- saved custom label name
- saved color
- saved notes

That is why custom labels defined in the GUI can show up later in generated logs.

## Programmatic use

Plugins and custom features should use the shared reporting helpers rather than writing ad hoc text files so logs stay aligned with the rest of the application.
