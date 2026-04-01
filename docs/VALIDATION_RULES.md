# Validation System And Rules

This page explains the validation backend at a high level.

For the full per-check matrix, issue titles, params, and related tools, use:

- [Checks And Issues Reference](CHECKS_AND_ISSUES_REFERENCE.md)

## Shared Backend

GUI and CLI both use the same validation stack:

- engine: `swcstudio.core.validation_engine`
- registry: `swcstudio.core.validation_registry`
- result models: `swcstudio.core.validation_results`
- labels and categories: `swcstudio.core.validation_catalog`
- feature wrapper: `swcstudio.tools.validation.features.run_checks`

Common flow:

1. load validation config
2. build the pre-check summary
3. run enabled checks
4. return a structured `ValidationReport`
5. render results in GUI, CLI, or reports

## Main Config

Validation config lives in:

- `swcstudio/tools/validation/configs/default.json`

Per-check shape:

```json
{
  "checks": {
    "has_soma": {
      "enabled": true,
      "severity": "error",
      "params": {}
    }
  }
}
```

Meaning:

- `enabled`
  - run or skip the check
- `severity`
  - how a failing check is classified in the report
- `params`
  - check-specific thresholds or options

## Output Model

Each check returns a `CheckResult` with fields such as:

- `key`
- `label`
- `status`
- `message`
- `failing_node_ids`
- `failing_section_ids`
- `metrics`
- `params_used`
- `thresholds_used`

A full run returns a `ValidationReport` with:

- `precheck`
- `results`
- `summary`

## GUI And CLI Consistency

Validation stays consistent across interfaces because both call the same backend and return the same result model.

Use the CLI when you want batchable text output.
Use the GUI when you want issue navigation, highlighting, and repair routing.
