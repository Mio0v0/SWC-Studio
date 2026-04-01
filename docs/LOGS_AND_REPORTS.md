# Logs and Reports

The project has a shared report layer so CLI and GUI produce consistent text logs.

Core module:

- `swcstudio.core.reporting`

## Why this matters

- one report format per feature
- same content in CLI and GUI runs
- easier audit trail for lab workflows

## Report builders

Main helper functions:

- `format_validation_report_text`
- `format_batch_validation_report_text`
- `format_split_report_text`
- `format_auto_typing_report_text`
- `format_radii_cleaning_report_text`
- `format_simplification_report_text`
- `format_morphology_session_log_text`
- `format_operation_report_text`
- `write_text_report`

## Default report naming

CLI default naming uses one pattern:

- single-file output/report folder: `<input_folder>/<original_stem>_swc_studio_output/`
- single-file output or report name: `<original_stem>_<full_operation_name>_<timestamp>.<ext>`
- batch output folder: `<input_folder>/<input_folder>_<full_operation_name>_<timestamp>/`
- batch report: `<input_folder>_<full_operation_name>_<timestamp>.txt`

Examples:

- validation report: `<input_folder>/<stem>_swc_studio_output/<stem>_validation_run_<timestamp>.txt`
- validation index clean output: `<input_folder>/<stem>_swc_studio_output/<stem>_validation_index_clean_<timestamp>.swc`
- geometry simplify output: `<input_folder>/<stem>_swc_studio_output/<stem>_geometry_simplify_<timestamp>.swc`
- geometry simplify report: `<input_folder>/<stem>_swc_studio_output/<stem>_geometry_simplify_<timestamp>.txt`
- manual label operation report: `<input_folder>/<stem>_swc_studio_output/<stem>_morphology_set_type_<timestamp>.txt`
- auto label operation report: `<input_folder>/<stem>_swc_studio_output/<stem>_validation_auto_label_<timestamp>.txt`
- batch split folder: `<folder>/<folder>_batch_split_<timestamp>/`
- batch split files: `<stem>_batch_split_tree_<index>_<timestamp>.swc`
- batch auto typing folder report: `<folder>_batch_auto_typing_<timestamp>.txt`

### GUI Edit Session

- output folder: `<input_folder>/<stem>_swc_studio_output/`
- session log: `<stem>_session_log_<timestamp>.txt`
- saved copy: `<stem>_closed_<timestamp>.swc`
- records all edits in one GUI session for that SWC

## Typical report contents

Validation reports:

- pre-check rule summary
- grouped pass/warn/fail results
- detailed findings (node IDs, section IDs, thresholds, metrics)

Batch reports:

- files processed/failed
- per-file outputs
- run-level summary counts

GUI session logs:

- one header per open-to-close session
- one operation block per applied change
- operation-specific node-change tables with only the columns that changed

CLI single-file operation reports:

- one report per edit run
- same summary/details + node-change table format used by GUI session logs
- currently written for single-file edit commands such as auto-fix, auto-label, radii-clean, index-clean, simplify, set-type, set-radius, dendrogram-edit, and geometry edits

Single-file CLI edit commands are intended to keep one operation report, not an extra legacy feature log.

## Programmatic use

Use `write_text_report(path, text)` in custom features/plugins to produce logs in the same style as built-in tools.
