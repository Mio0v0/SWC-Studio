# API Documentation (Library Reference)

This document covers Python-callable APIs in SWC-Studio (Python package: `swcstudio`).

## How To Read This Doc

- Use `swcstudio.api` for most integrations.
- Use feature modules directly only when you need tool-specific behavior.
- Use plugin registry APIs to override method implementations.

## API Layers

1. Stable convenience API: `swcstudio.api`
2. Tool feature modules: `swcstudio.tools.<tool>.features.<feature>`
3. Plugin registry: `swcstudio.plugins`

## Recommended Import

```python
import swcstudio.api as swc
```

## 1) Public Convenience API (`swcstudio.api`)

Source: `swcstudio/api.py`

### Data Type

#### `RuleBatchOptions`

Dataclass for auto-typing:

- `soma: bool`
- `axon: bool`
- `apic: bool`
- `basal: bool`

### Batch Processing

#### `batch_validate_folder(folder, *, config_overrides=None) -> dict`

Runs validation over all SWC files in a folder.

#### `batch_split_folder(folder, *, config_overrides=None) -> dict`

Splits each SWC by soma-root trees.

#### `batch_auto_typing(folder, *, options=None, config_overrides=None) -> RuleBatchResult`

Runs rule-based auto typing over a folder.

#### `batch_radii_cleaning(folder, *, config_overrides=None) -> dict`

Runs radii cleaning on a folder.

#### `batch_simplify_folder(folder, *, config_overrides=None) -> dict`

Runs simplification on all SWC files in a folder.

#### `batch_index_clean_folder(folder, *, config_overrides=None) -> dict`

Runs index clean on all SWC files in a folder.

#### `radii_clean_path(path, *, config_overrides=None) -> dict`

Runs radii cleaning on either one file or one folder.

### Validation

#### `validation_run_text(swc_text, *, config_overrides=None, feature_overrides=None) -> ValidationReport`

Runs structured validation from SWC text.

#### `validation_run_file(path, *, config_overrides=None, feature_overrides=None) -> ValidationReport`

Runs structured validation from file path.

#### `auto_fix_text(swc_text, *, config_overrides=None) -> dict`

Runs sanitize + validation from text.

#### `auto_fix_file(path, *, out_path=None, write_output=False, config_overrides=None) -> dict`

Runs sanitize + validation from file, optionally writes output.

#### `validation_auto_typing_file(file_path, *, options=None, config_overrides=None, output_path=None, write_output=True, write_log=True)`

Runs the shared auto-typing logic on a single file.

#### `validation_index_clean_text(swc_text, *, config_overrides=None) -> dict`

Runs validation index clean in memory.

#### `validation_index_clean_file(path, *, out_path=None, write_output=False, write_report=True, config_overrides=None) -> dict`

Runs validation index clean on one file.

### Visualization

#### `build_mesh_from_text(swc_text, *, config_overrides=None) -> dict`

Builds mesh summary payload from SWC text.

#### `build_mesh_from_file(path, *, config_overrides=None) -> dict`

Builds mesh summary payload from file.

### Morphology Editing

#### `reassign_subtree_types(swc_text, *, node_id, new_type, config_overrides=None) -> dict`

Reassigns subtree node types in memory.

#### `reassign_subtree_types_in_file(path, *, node_id, new_type, out_path=None, write_output=False, config_overrides=None) -> dict`

File wrapper for subtree type reassignment.

#### `morphology_set_node_radius_text(swc_text, *, node_id, radius, config_overrides=None) -> dict`

Sets one node radius in memory.

#### `morphology_set_node_radius_file(path, *, node_id, radius, out_path=None, write_output=False, config_overrides=None) -> dict`

File wrapper for single-node radius editing.

#### `morphology_smart_decimation_text(swc_text, *, config_overrides=None) -> dict`

Legacy compatibility name for the shared simplification backend.

#### `morphology_smart_decimation_file(path, *, out_path=None, write_output=False, config_overrides=None) -> dict`

Legacy compatibility name for the shared simplification backend used by `Geometry Editing -> Simplification`.

### Geometry Editing

These functions expose the shared geometry-editing core used by the app:

- `geometry_move_node_absolute(df, node_id, x, y, z)`
- `geometry_move_subtree_absolute(df, root_id, x, y, z)`
- `geometry_reconnect_branch(df, source_id, target_id)`
- `geometry_disconnect_branch(df, start_id, end_id)`
- `geometry_delete_node(df, node_id, reconnect_children=False)`
- `geometry_delete_subtree(df, root_id)`
- `geometry_insert_node_between(df, start_id, end_id, x, y, z, radius=None, type_id=None)`
- `geometry_reindex_dataframe_with_map(df)`

### Analysis

#### `analysis_summary_file(path, *, config_overrides=None) -> dict`

Basic morphology statistics.

This remains available as a library/plugin target even though `Analysis` is no longer a user-facing GUI or CLI tool.

### Plugins

#### `load_plugin_module(module_name, *, force_reload=False) -> dict`

Load one plugin module (manifest validation + method registration).
Note: registrations are process-local; use `autoload_plugins_from_environment`
for automatic loading in new CLI processes.

#### `load_plugins(modules) -> list[dict]`

Load multiple plugin modules and return per-module status.

#### `autoload_plugins_from_environment(env_var="SWCSTUDIO_PLUGINS") -> list[dict]`

Load comma-separated plugin module list from environment variable.

#### `register_plugin_manifest(manifest) -> PluginManifest`

Register validated plugin manifest metadata.

#### `register_plugin_method(plugin_id, feature_key, method_name, func) -> None`

Register a plugin-owned method for one feature/method key.

#### `unregister_plugin(plugin_id) -> None`

Remove plugin manifest and methods owned by that plugin.

#### `register_method(feature_key, method_name, func) -> None`

Register plugin override method.

#### `unregister_method(feature_key, method_name) -> None`

Remove plugin override method.

#### `list_feature_methods(feature_key) -> dict`

List methods for a single feature key.

#### `list_all_feature_methods() -> dict`

List methods for all feature keys.

#### `list_plugins() -> list[dict]`

List loaded/registered plugin manifests.

#### `get_plugin(plugin_id) -> dict | None`

Get one plugin manifest by plugin id.

## 2) Tool Feature Module Entry Points

These are callable if you want per-feature direct imports.

## Batch Processing

- `swcstudio.tools.batch_processing.features.batch_validation`
  - `validate_swc_text(...)`
  - `validate_folder(...)`
- `swcstudio.tools.batch_processing.features.swc_splitter`
  - `split_swc_text(...)`
  - `split_folder(...)`
- `swcstudio.tools.batch_processing.features.auto_typing`
  - `run_folder(...)`
  - `options_to_dict(...)`
- `swcstudio.tools.batch_processing.features.radii_cleaning`
  - `clean_swc_text(...)`
  - `clean_file(...)`
  - `clean_folder(...)`
  - `clean_path(...)`
- `swcstudio.tools.batch_processing.features.simplification`
  - `run_folder(...)`
- `swcstudio.tools.batch_processing.features.index_clean`
  - `run_folder(...)`

## Validation

- `swcstudio.tools.validation.features.run_checks`
  - `validate_text(...)`
  - `validate_file(...)`
- `swcstudio.tools.validation.features.auto_fix`
  - `auto_fix_text(...)`
  - `auto_fix_file(...)`
- `swcstudio.tools.validation.features.auto_typing`
  - `run_file(...)`
- `swcstudio.tools.validation.features.radii_cleaning`
  - `clean_path(...)`
  - `clean_file(...)`
  - `clean_folder(...)`
- `swcstudio.tools.validation.features.index_clean`
  - `index_clean_text(...)`
  - `index_clean_file(...)`

## Visualization

- `swcstudio.tools.visualization.features.mesh_editing`
  - `build_mesh_from_text(...)`
  - `build_mesh_from_file(...)`

## Morphology Editing

- `swcstudio.tools.morphology_editing.features.dendrogram_editing`
  - `reassign_subtree_types(...)`
  - `reassign_subtree_types_in_file(...)`
- `swcstudio.tools.morphology_editing.features.manual_radii`
  - `set_node_radius_text(...)`
  - `set_node_radius_file(...)`
- `swcstudio.tools.morphology_editing.features.simplification`
  - `simplify_dataframe(...)`
  - `simplify_swc_text(...)`
  - `simplify_file(...)`
  - shared simplification backend used by the current Geometry Editing tool

## Analysis (Library / Plugin Only)

- `swcstudio.tools.analysis.features.summary`
  - `analyze_text(...)`
  - `analyze_file(...)`

## 3) Validation Engine and Models

Module: `swcstudio.tools.validation`

Exposed helpers:

- `load_validation_config(...)`
- `build_precheck_summary(...)`
- `run_validation_text(...)`
- `register_check(...)`
- `register_plugin_check(...)`
- `get_check(...)`
- `list_checks(...)`

Result models:

- `PreCheckItem`
- `CheckResult`
- `ValidationReport`

## Simplification (How It Works)

1. Build directed graph from SWC `id`/`parent`.
2. Protect structural nodes (roots, optional tips, optional bifurcations).
3. Extract anchor-to-anchor linear paths.
4. Apply RDP with `thresholds.epsilon`.
5. Protect radius-sensitive nodes where:
   - `abs(node_radius - path_mean_radius) / path_mean_radius > thresholds.radius_tolerance`
6. Rewire kept nodes to nearest kept ancestor.

Key parameters (`simplification.json`):

- `thresholds.epsilon`
- `thresholds.radius_tolerance`
- `flags.keep_tips`
- `flags.keep_bifurcations`
- `flags.keep_roots`

## Plugin Override Pattern

```python
from swcstudio.plugins import load_plugin_module, register_method

def my_method(*args, **kwargs):
    ...

register_method("batch_processing.auto_typing", "default", my_method)
load_plugin_module("my_lab_plugins.summary_plugin")
```

## Plugin Contract (Versioned)

External plugin modules should expose:

1. `PLUGIN_MANIFEST` dictionary (or `get_plugin_manifest()`)
2. one of:
   - `register_plugin(registrar)` function
   - `PLUGIN_METHODS` mapping/list

Minimal `PLUGIN_MANIFEST`:

```python
PLUGIN_MANIFEST = {
    "plugin_id": "my_lab.summary_plugin",
    "name": "Custom Summary Plugin",
    "version": "0.1.0",
    "api_version": "1",
    "capabilities": ["analysis", "custom_metrics"],
}
```

Starter template in this repo:

- `examples/plugins/summary_plugin_template.py`

## Config Files

Per-feature config path pattern:

- `swcstudio/tools/<tool>/configs/<feature>.json`

Examples:

- `swcstudio/tools/validation/configs/default.json`
- `swcstudio/tools/batch_processing/configs/radii_cleaning.json`
- `swcstudio/tools/morphology_editing/configs/simplification.json`
