# Checks And Issues Reference

This is the canonical reference for:

- validation checks
- GUI issue types
- related tools
- parameter sources
- the current radii-cleaning and auto-labeling algorithms

Primary code sources:

- `swcstudio/core/validation_catalog.py`
- `swcstudio/core/validation_checks/native_checks.py`
- `swcstudio/core/validation_checks/neuron_morphology_checks.py`
- `swcstudio/core/issues.py`
- `swcstudio/core/radii_cleaning.py`
- `swcstudio/core/auto_typing/` (engine package)
- `swcstudio/tools/validation/configs/default.json`
- `swcstudio/tools/batch_processing/configs/radii_cleaning.json`
- `swcstudio/tools/batch_processing/configs/auto_typing.json`

## How To Read This Page

- `Source`
  - `native`: implemented directly in SWC-Studio
  - `NeuroM`: wrapped from NeuroM
- `Severity`
  - current default from `swcstudio/tools/validation/configs/default.json`
- `JSON`
  - `yes`: params are exposed in JSON
  - `enabled/severity only`: the check can be turned on/off and reclassified, but has no extra exposed params
- `Related tool`
  - the tool the GUI routes to for inspection or repair

## Pipeline Overview

The app raises issues from three layers:

1. `Validation checks`
   - deterministic checks run through the shared validation engine
2. `Suspicious-item detectors`
   - suspicious radii and suspicious labels
3. `Issue normalization`
   - validation rows and suspicious findings become GUI issues

So one SWC can raise:

- validation issues
- blocked-check issues
- suspicious radii issues
- suspicious label issues

## Validation Check Matrix

### Structural Presence

| Key | Issue title | Source | Severity | How checked | Params | JSON | Related tool |
|---|---|---|---|---|---|---|---|
| `valid_soma_format` | `Complex soma format found` | native | warning | Groups connected type-`1` nodes and fails if any soma group has more than one node. | none | enabled/severity only | `Consolidate Soma` action |
| `multiple_somas` | `Multiple somas found` | native | critical | Runs after temporary soma consolidation and fails if more than one soma anchor remains. | none | enabled/severity only | `Split` action |
| `has_soma` | `Soma missing` | native | critical | Fails if no node has type `1`. | none | enabled/severity only | Manual Label Editing / Auto Label Editing |
| `no_invalid_negative_types` | `Invalid negative types found` | native | critical | Fails if any node type is `< 0`. | none | enabled/severity only | Manual Label Editing |
| `custom_types_defined` | `Custom types need definitions` | native | warning | Requires every used custom type (`>= 5`) to have a saved name and color. | none | enabled/severity only | `Define Custom Types` dialog |
| `has_axon` | `Axon missing` | native | warning | Fails if no node has type `2`. | none | enabled/severity only | Manual Label Editing / Auto Label Editing |
| `has_basal_dendrite` | `Basal dendrite missing` | native | warning | Fails if no node has type `3`. | none | enabled/severity only | Manual Label Editing / Auto Label Editing |
| `has_apical_dendrite` | `Apical dendrite missing` | native | warning | Fails if no node has type `4`. | none | enabled/severity only | Manual Label Editing / Auto Label Editing |

### Radius And Size

| Key | Issue title | Source | Severity | How checked | Params | JSON | Related tool |
|---|---|---|---|---|---|---|---|
| `all_neurite_radii_nonzero` | `Invalid neurite radii found` | native | critical | Fails on non-soma nodes with non-finite or `<= 0` radius. | none | enabled/severity only | Manual Radii Editing |
| `soma_radius_nonzero` | `Invalid soma radius found` | NeuroM | critical | Calls NeuroM `has_nonzero_soma_radius`. | `threshold=0.0` | yes | Manual Radii Editing |
| `no_ultranarrow_sections` | `Ultranarrow sections found` | NeuroM | warning | Calls NeuroM `has_no_narrow_neurite_section`. | `radius_threshold=0.05`, `considered_section_min_length=50.0` | yes | Manual Radii Editing |
| `no_ultranarrow_starts` | `Ultranarrow branch starts found` | NeuroM | warning | Calls NeuroM `has_no_narrow_start`. | `frac=0.9` | yes | Manual Radii Editing |
| `no_fat_terminal_ends` | `Oversized terminal ends found` | NeuroM | warning | Calls NeuroM `has_no_fat_ends`. | `multiple_of_mean=2.0`, `final_point_count=5` | yes | Manual Radii Editing |
| `radius_upper_bound` | `Oversized radii found` | native | warning | Fails when any radius is above `max_radius`. | `max_radius=20.0` | yes | Auto Radii Editing |

### Length And Geometry

| Key | Issue title | Source | Severity | How checked | Params | JSON | Related tool |
|---|---|---|---|---|---|---|---|
| `all_section_lengths_nonzero` | `Zero-length sections found` | native | critical | Uses segment-based section validity and fails on zero or invalid derived section length. | none | enabled/severity only | Geometry Editing |
| `all_segment_lengths_nonzero` | `Zero-length segments found` | native | critical | Computes Euclidean parent-child distance and fails on non-finite or `<= 0` length. | none | enabled/severity only | Geometry Editing |
| `no_back_tracking` | `Geometric backtracking found` | NeuroM | warning | Calls NeuroM `has_no_back_tracking`. | none | enabled/severity only | Geometry Editing |
| `no_flat_neurites` | `Flattened neurites found` | NeuroM | warning | Calls NeuroM `has_no_flat_neurites`. | `tol=0.1`, `method="ratio"` | yes | Geometry Editing |
| `no_duplicate_3d_points` | `Duplicated points found` | native | critical | Fails only when the full `x,y,z` triplet is duplicated. | none | enabled/severity only | Geometry Editing |
| `no_extreme_spatial_jump` | `Extreme spatial jumps found` | native | warning | Flags parent-child segments above a threshold derived from absolute, median-ratio, and MAD-based bounds. | `min_jump_um=200.0`, `median_ratio=10.0`, `mad_scale=12.0`, `mad_floor_um=1.0` | yes | Geometry Editing |

### Topology

| Key | Issue title | Source | Severity | How checked | Params | JSON | Related tool |
|---|---|---|---|---|---|---|---|
| `no_dangling_branches` | `Dangling branches found` | native | critical | Fails on non-soma nodes with `parent == -1`. | none | enabled/severity only | Geometry Editing |
| `no_self_loop` | `Self loops found` | native | critical | Fails when `parent == id`. | none | enabled/severity only | Geometry Editing |
| `no_single_child_chains` | `Single-child chains found` | NeuroM | warning | Calls NeuroM `has_no_single_children`. | none | enabled/severity only | Geometry Editing |
| `has_unifurcation` | `Unifurcation found` | NeuroM | warning | Calls NeuroM `has_unifurcation`. | none | enabled/severity only | Geometry Editing |
| `has_multifurcation` | `Multifurcation found` | NeuroM | warning | Calls NeuroM `has_multifurcation`. | none | enabled/severity only | Geometry Editing |

### Index Consistency

| Key | Issue title | Source | Severity | How checked | Params | JSON | Related tool |
|---|---|---|---|---|---|---|---|
| `no_section_index_jumps` | `Sections jump too far along Z` | NeuroM | critical | Calls NeuroM `has_no_jumps` and uses it as a Z-axis consistency check. | `max_distance=30.0`, `axis="z"` | yes | Geometry Editing |
| `no_root_index_jumps` | `Neurite roots too far from soma` | NeuroM | critical | Calls NeuroM `has_no_root_node_jumps`. | `radius_multiplier=2.0` | yes | Geometry Editing |
| `parent_id_less_than_child_id` | `Parent-child ID order violations found` | native | warning | Fails when a valid in-file parent ID is `>=` child ID. | none | enabled/severity only | Index Clean |
| `no_node_id_gaps` | `Node ID gaps found` | native | info | Fails when sorted unique node IDs skip integers. | none | enabled/severity only | Index Clean |

## GUI-Only Issue Generators

These are shown in the issue-driven workflow but are not entries in `default.json`.

| Source key | Title | How generated | Config source | Related tool |
|---|---|---|---|---|
| `blocked_validation_checks` | `Checks blocked by ...` | Grouped from validation rows that could not run because morphology building failed. | none | Validation or Manual Label Editing, depending on cause |
| `radii_outlier_batch` | `Outlier radii detected` | Runs the shared radii-cleaning engine and groups nodes the cleaner would change. | `swcstudio/tools/batch_processing/configs/radii_cleaning.json` | Auto Radii Editing |
| `type_suspicion_batch` | `Likely wrong labels` | Runs the shared auto-typing engine and groups nodes where current type differs from suggested type. | `swcstudio/tools/batch_processing/configs/auto_typing.json` | Auto Label Editing |

## Issue Model

Issues normalized in `swcstudio/core/issues.py` use these fields:

- `issue_id`
- `severity`
- `certainty`
- `domain`
- `title`
- `description`
- `node_ids`
- `section_ids`
- `tool_target`
- `suggested_fix`
- `status`
- `source_key`
- `source_label`
- `source_category`
- `source_payload`

## Radii Cleaning Algorithm

The suspicious radii issue and Auto Radii Editing use the same shared backend in `swcstudio/core/radii_cleaning.py`.

### Current method

The current cleaner is directed-path and fixed-point based:

1. build topology and directed branch paths
2. compute per-type sanity bounds
3. `Pass 1`: local outlier repair
4. `Pass 2`: taper enforcement
5. `Pass 3`: local polynomial smoothing
6. re-apply taper
7. repeat until no issue-visible changes remain

Soma radii are always preserved.

### Reasons recorded per changed node

- `non_finite`
- `non_positive`
- `below_type_min`
- `above_type_max`
- `local_outlier`
- `taper_cap`
- `post_smooth_taper_cap`
- `axon_floor`
- `savitzky_golay`

### Current radii-clean config keys

Main config file:

- `swcstudio/tools/batch_processing/configs/radii_cleaning.json`

Current top-level rule groups:

- `small_radius_zero_only`
- `sanity_bounds.global`
- `sanity_bounds.per_type`
- `local_outlier`
- `taper`
- `axon_floor`
- `savgol`
- `fixed_point`
- `replacement`

Important defaults:

- `local_outlier.window_nodes = 5`
- `local_outlier.max_percent_deviation = 0.5`
- `taper.slack = 0.05`
- `axon_floor.min_radius = 0.12`
- `savgol.window_nodes = 7`
- `savgol.polyorder = 2`
- `fixed_point.max_passes = 32`
- `fixed_point.min_effective_delta = 0.005`

## Auto Labeling Algorithm

The suspicious label issue and Auto Label Editing run the same
auto-typing engine, implemented in:

- `swcstudio/core/auto_typing/` (engine package)
- `swcstudio/tools/batch_processing/configs/auto_typing.json` (user-editable runtime knobs)

### Pipeline architecture

Auto-labeling runs three groups of work in sequence: a **QC gate**
that decides whether to label at all, a **labeling model** that
assigns the per-node types, and **flag scoring** that highlights low-
confidence labels for review.

| Step | Files | What it produces |
|---|---|---|
| **QC gate** | `qc_gate.pkl` | Pass / reject decision plus a specific reason. Rejects malformed, disconnected, or out-of-distribution files before any labeling runs. Unlabeled type-0 inputs are allowed through. |
| **Cell typing** | `cell_type_classifier.pkl` | Pyramidal vs interneuron. Uses a soft handoff: when confidence is low it runs subtree labeling for both cell types and picks the higher-confidence outcome. |
| **Subtree labeling** | `branch_classifier.pkl` | Per-primary-subtree assignment as axon / basal / apical. |
| **Apical/basal GNN** | `gnn_apical_basal.pt` | GraphSAGE re-decision over the branch graph for pyramidal dendrites. |
| **Apical/basal rescue** | `gnn_branch3_rescue.pt` | Conservative GraphSAGE rescue head for the hardest pyramidal apical/basal cases. |
| **Topology refinement** | — | Soma-boundary constraints applied (one primary axon, one primary apical), short islands flipped. |
| **Flag scoring** | `flag_model_pyramidal.joblib`, `flag_model_interneuron.joblib`, `flag_model_all.joblib` | Per-node score of how likely each predicted label is wrong. Surface in the GUI issue panel and in the CLI JSON output. |

`flag_feature_mode` controls flag-score features; both `compact` and
`simple` map to the bundled fast flagger.

### Apical detection

Apical labeling requires both a learned per-subtree score and a
minimum subtree-root radius. Files without a qualifying apical
subtree get 3-class output (soma / axon / basal); files with one get
4-class output (soma / axon / basal / apical). There are no
class-selection flags exposed to the user.

### Config keys

The user-editable JSON at
`swcstudio/tools/batch_processing/configs/auto_typing.json` is small —
the engine's behavior is set by the trained model files, not by
hand-tuned weights. Current keys:

- `model_dir` — override the model search path (empty string means use
  the default search order: env var → user data dir → bundled)
- `use_subtree_stage2` — whether Stage 2 operates on full primary
  subtrees (default `true`)
- `cell_type` - `unknown` runs Stage 1; `pyramidal` or `interneuron`
  bypasses Stage 1 with the user-provided type
- `flag_enabled` - enable learned per-cell bad-label flag scoring
- `flag_strictness` - tune flagging from loose to conservative
- `flag_feature_mode` - compatibility field; compact scoring is always
  used in SWC-Studio
- `enabled` — feature gate (default `true`)
- `notes` — free-form description; not consumed by the engine

To swap in your own trained models without editing this file, copy them
into the user data directory (`%APPDATA%\swcstudio\models\` on Windows,
`~/Library/Application Support/swcstudio/models/` on macOS, or
`~/.local/share/swcstudio/models/` on Linux) and they take precedence
over the bundled defaults.

`flag_feature_mode` behavior:

- `compact` is the bundled fast flagger and uses features the labeling
  stage already computed.
- `simple` is accepted as an alias for compact.

## How Checks Become GUI Issues

Current conversion rules:

- validation `pass`
  - no issue
- validation `warning`
  - `warning` issue
- validation `fail`
  - `critical` issue
- blocked or dependency-failed checks
  - collapsed into grouped blocked-check issues
- suspicious radii changes
  - one aggregated `Outlier radii detected` issue
- suspicious label changes
  - one aggregated `Likely wrong labels` issue

## Where To Edit Behavior

- validation check enable/severity/params
  - `swcstudio/tools/validation/configs/default.json`
- radii cleaning behavior
  - `swcstudio/tools/batch_processing/configs/radii_cleaning.json`
- auto labeling behavior
  - `swcstudio/tools/batch_processing/configs/auto_typing.json`

## Related Docs

- [Validation Rules](VALIDATION_RULES.md)
- [Radii Cleaning Tutorial](RADII_CLEANING_TUTORIAL.md)
- [GUI Workflow Guide](GUI_WORKFLOW.md)
- [CLI Reference](CLI_REFERENCE.md)
