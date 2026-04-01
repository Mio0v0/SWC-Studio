# Plugin Demonstration Guide

This is a step-by-step handoff guide for lab members to add a plugin to SWC-Studio and run it from the same app/CLI workflow.

## What This Demonstration Covers

1. Create a plugin file.
2. Load plugin into SWC-Studio.
3. Verify plugin is registered.
4. Run a built-in feature using plugin method selection.
5. Reuse the same plugin setup in future runs.

## Plugin Contract (Required)

Every plugin module needs:

1. `PLUGIN_MANIFEST` (or `get_plugin_manifest()`).
2. `register_plugin(registrar)`.

Inside `register_plugin`, bind your function to a feature key and method name:

```python
def register_plugin(registrar):
    registrar.register_method(
        "analysis.summary",                 # feature key in SWC-Studio
        "lab_summary",                      # method name users select
        my_callable,                        # Python callable
    )
```

## Minimal File Layout

Recommended starting point:

- Copy: `examples/plugins/summary_plugin_template.py`
- New file: `examples/plugins/my_lab_plugin.py`

The new file is your plugin module name (`my_lab_plugin`).

## End-to-End Demo Workflow

### 1) Open project and activate environment

macOS/Linux:

```bash
cd <repo-root>
source .venv/bin/activate
```

Windows PowerShell:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
```

Windows cmd:

```bat
cd <repo-root>
.venv\Scripts\activate.bat
```

### 2) Make plugin module importable

If your plugin file is under `examples/plugins`:

macOS/Linux:

```bash
export PYTHONPATH="$PWD/examples/plugins"
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD/examples/plugins"
```

Windows cmd:

```bat
set PYTHONPATH=%CD%\examples\plugins
```

### 3) Load plugin

```bash
swctools plugins load my_lab_plugin
```

### 4) Verify plugin manifest loaded

```bash
swctools plugins list-loaded
```

You should see your `plugin_id`.

### 5) Verify method registration under target feature

```bash
swctools plugins list --feature-key analysis.summary
```

You should see your method name in `plugin_methods`.

### 6) Run feature through plugin method

Example:

```bash
python - <<'PY'
from swctools.api import analysis_summary_file
print(analysis_summary_file("./data/single-soma.swc", config_overrides={"method": "lab_summary"}))
PY
```

The `method` value must exactly match the name used in `register_method(...)`.

## Persistent Plugin Loading (Recommended)

`swctools plugins load ...` is process-scoped. To auto-load every run:

macOS/Linux:

```bash
export SWCTOOLS_PLUGINS="my_lab_plugin"
```

Windows PowerShell:

```powershell
$env:SWCTOOLS_PLUGINS = "my_lab_plugin"
```

Windows cmd:

```bat
set SWCTOOLS_PLUGINS=my_lab_plugin
```

## Common Errors and Fixes

### Error: `No module named my_lab_plugin`

- Cause: module path not importable.
- Fix: set `PYTHONPATH` or install plugin as package.

### Plugin appears loaded but method is not used

- Cause: wrong method name or wrong feature key.
- Fix: compare:
  - `register_method(<feature_key>, <method_name>, ...)`
  - CLI `--config-json '{"method":"<method_name>"}'`

## Notes for GUI Users

Plugin methods are backend methods. If a GUI control calls the same feature key, it can use plugin-selected methods through the same config path. The plugin itself does not need GUI code for basic integration.

## Related Docs

- `docs/CLI_REFERENCE.md`
- `docs/API_DOCUMENTATION.md`
