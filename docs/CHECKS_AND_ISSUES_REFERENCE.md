# Checks And Issues Reference

This document describes the current SWC checking and issue-generation pipeline in `SWC-Studio`.

It answers four questions:

1. What checks can run on an SWC file?
2. What issues can the issue-driven workflow raise?
3. How is each check/issue computed?
4. What parameters currently control the behavior?

This document reflects the current code in:

- `swctools/core/validation_catalog.py`
- `swctools/core/validation_checks/native_checks.py`
- `swctools/core/validation_checks/neuron_morphology_checks.py`
- `swctools/core/issues.py`
- `swctools/core/radii_cleaning.py`
- `swctools/tools/validation/configs/default.json`
- `swctools/tools/batch_processing/configs/radii_cleaning.json`
- `swctools/tools/batch_processing/configs/auto_typing.json`

## Overview

The checking pipeline currently has three layers:

1. `Validation checks`
   - deterministic rule checks run through the shared validation engine
2. `Suspicious-item detectors`
   - aggregated heuristics for suspicious radii and suspicious labels
3. `Issue normalization`
   - validation rows and suspicious findings are converted into GUI issues

In the issue-driven workflow, a file can therefore raise:

- `validation issues`
- `blocked-check issues`
- `suspicious radii issues`
- `suspicious label issues`

## Core Issue Model

Current issue fields come from `swctools/core/issues.py`:

- `issue_id`
- `severity`
  - `critical`
  - `warning`
  - `info`
- `certainty`
  - `rule`
  - `suspicious`
  - future `ai`
- `domain`
  - `structure`
  - `radii`
  - `label`
  - `geometry`
  - future `ai`
- `title`
- `description`
- `node_ids`
- `section_ids`
- `tool_target`
- `suggested_fix`
- `confidence`
- `status`
  - `open`
  - `fixing`
  - `skipped`
  - `fixed`
- `source_key`
- `source_label`
- `source_category`
- `source_payload`

## Validation Checks

Validation checks are configured in:

- `swctools/tools/validation/configs/default.json`

User overrides are applied through that same JSON structure. If you change a check's
`params` block there, the validation runner passes those values through to the native
or NeuroM-backed check implementation.

Each entry has:

- `enabled`
- `severity`
- `params`

The following checks are currently registered.

### Structural Presence

#### `valid_soma_format`

- Label: `Soma format is simple`
- Source: native
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - finds all type `1` nodes
  - groups them by topological connectivity within the soma subgraph
  - detects whether any connected soma group has more than one node
- Failure condition:
  - one or more connected soma groups contain multiple soma nodes
- Parameters:
  - none
- Output details:
  - failing node IDs from complex soma groups
  - metrics:
    - `complex_soma_group_count`
    - `complex_soma_node_count`
    - `soma_count_before`
    - `soma_count_after`
    - `complex_groups`
- Notes:
  - this is the first validation-stage soma-format warning
  - if this warning is raised, later checks do not run until the soma-format problem is resolved
- Typical related issue tool:
  - `validation`

#### `multiple_somas`

- Label: `Only one connected soma group remains`
- Source: native
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - runs strictly after temporary soma consolidation
  - counts how many type `1` nodes remain in the consolidated working copy
- Failure condition:
  - more than one soma remains after consolidation
- Parameters:
  - none
- Output details:
  - failing node IDs = consolidated soma anchor IDs
  - metrics:
    - `multiple_soma_count`
    - `can_split_trees`
    - `soma_ids_after_consolidation`
- Notes:
  - this means disconnected cells remain in the file
  - if this error is raised, later checks do not run
- Typical related issue tool:
  - `validation`

#### `has_soma`

- Label: `Soma present`
- Source: native
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - checks whether any node has SWC type `1`
- Failure condition:
  - no soma node exists
- Parameters:
  - none
- Output details:
  - metric: `soma_count`
- Typical related issue tool:
  - `label_editing`

#### `has_axon`

- Label: `Axon present`
- Source: native
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - counts nodes with SWC type `2`
- Failure condition:
  - axon count is `0`
- Parameters:
  - none
- Output details:
  - metric: `axon_node_count`
- Typical related issue tool:
  - `auto_label`

#### `has_basal_dendrite`

- Label: `Basal dendrite present`
- Source: native
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - counts nodes with SWC type `3`
- Failure condition:
  - basal dendrite count is `0`
- Parameters:
  - none
- Output details:
  - metric: `basal_node_count`
- Typical related issue tool:
  - `auto_label`

#### `has_apical_dendrite`

- Label: `Apical dendrite present`
- Source: native
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - counts nodes with SWC type `4`
- Failure condition:
  - apical dendrite count is `0`
- Parameters:
  - none
- Output details:
  - metric: `apical_node_count`
- Typical related issue tool:
  - `auto_label`

### Radius And Size

#### `all_neurite_radii_nonzero`

- Label: `All neurite radii are positive`
- Source: native
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - scans all non-soma nodes
  - flags radius values that are `NaN`, non-finite, or `<= 0`
- Failure condition:
  - any non-soma node has invalid radius
- Parameters:
  - none
- Output details:
  - failing node IDs
  - metric: `invalid_radius_count`
- Typical related issue tool:
  - `radii_cleaning`

#### `soma_radius_nonzero`

- Label: `Soma radius is positive`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_nonzero_soma_radius`
- Failure condition:
  - NeuroM returns false
  - or the morphology cannot be built for the NeuroM check
- Parameters:
  - `threshold`
    - default in config: `0.0`
- Notes:
  - can be blocked by unsupported or incompatible morphology structure
- Typical related issue tool:
  - `radii_cleaning`

#### `no_ultranarrow_sections`

- Label: `No extremely narrow sections`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_no_narrow_neurite_section`
- Failure condition:
  - NeuroM reports narrow section(s)
  - or the morphology cannot be built
- Parameters:
  - `radius_threshold`
    - default in config: `0.05`
  - `considered_section_min_length`
    - default in config: `50.0`
- Typical related issue tool:
  - `radii_cleaning`

#### `no_ultranarrow_starts`

- Label: `No extremely narrow branch starts`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_no_narrow_start`
- Failure condition:
  - NeuroM reports narrow branch starts
  - or the morphology cannot be built
- Parameters:
  - `frac`
    - default in config: `0.9`
- Typical related issue tool:
  - `radii_cleaning`

#### `no_fat_terminal_ends`

- Label: `No oversized terminal ends`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_no_fat_ends`
- Failure condition:
  - NeuroM reports oversized terminal ends
  - or the morphology cannot be built
- Parameters:
  - `multiple_of_mean`
    - default in config: `2.0`
  - `final_point_count`
    - default in config: `5`
- Typical related issue tool:
  - `radii_cleaning`

#### `radius_upper_bound`

- Label: `Radius upper bound`
- Source: native
- Default enabled: no
- Default severity: `warning`
- Algorithm:
  - scans all radii
  - flags nodes whose radius is greater than a configured maximum
- Failure condition:
  - any node has `radius > max_radius`
- Parameters:
  - `max_radius`
    - default in config: `20.0`
- Output details:
  - failing node IDs
  - `params_used.max_radius`
  - metric: `max_radius_observed`
- Notes:
  - this check is registered but is not currently listed in `validation_catalog.py`

### Length And Geometry

#### `all_section_lengths_nonzero`

- Label: `All section lengths are positive`
- Source: native
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - computes parent-child segment lengths in 3D
  - uses segment-based approximation for section validity
- Failure condition:
  - one or more derived section segments have zero or invalid length
- Parameters:
  - none
- Output details:
  - failing node IDs
  - failing section IDs
  - metric: `invalid_section_count`
- Typical related issue tool:
  - `simplification`

#### `all_segment_lengths_nonzero`

- Label: `All segment lengths are positive`
- Source: native
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - computes Euclidean distance between each child and its parent
- Failure condition:
  - any segment has non-finite or `<= 0` length
- Parameters:
  - none
- Output details:
  - failing node IDs
  - failing section IDs
  - metric: `invalid_segment_count`
- Typical related issue tool:
  - `simplification`

#### `no_back_tracking`

- Label: `No geometric backtracking`
- Source: NeuroM / `neuron_morphology`
- Default enabled: no
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_no_back_tracking`
- Failure condition:
  - NeuroM reports backtracking
  - or the morphology cannot be built
- Parameters:
  - none
- Typical related issue tool:
  - `label_editing`

#### `no_flat_neurites`

- Label: `No flattened neurites`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_no_flat_neurites`
- Failure condition:
  - NeuroM reports flattened neurites
  - or the morphology cannot be built
- Parameters:
  - `tol`
    - default in config: `0.1`
  - `method`
    - default in config: `"ratio"`
- Typical related issue tool:
  - `label_editing`

#### `no_duplicate_3d_points`

- Label: `No duplicate 3D points`
- Source: native
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - compares full XYZ triplets
  - groups identical coordinates using a NumPy uniqueness pass on row-wise byte views
- Failure condition:
  - two or more nodes share identical XYZ coordinates
- Parameters:
  - none
- Output details:
  - failing node IDs
  - metrics:
    - `duplicate_point_count`
    - `duplicate_group_count`
    - `duplicate_groups_sample`
- Typical related issue tool:
  - `simplification`

#### `no_extreme_spatial_jump`

- Label: `No extreme spatial jumps`
- Source: native
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - computes Euclidean parent-child segment lengths for all valid parent-child pairs
  - computes a conservative outlier threshold from:
    - `min_jump_um`
    - `median_segment_length * median_ratio`
    - `median_segment_length + mad_scale * max(MAD, mad_floor_um)`
  - flags segments longer than the maximum of those thresholds
- Failure condition:
  - one or more valid parent-child segments are extreme geometric outliers
- Parameters:
  - `min_jump_um`
    - default in config: `200.0`
  - `median_ratio`
    - default in config: `10.0`
  - `mad_scale`
    - default in config: `12.0`
  - `mad_floor_um`
    - default in config: `1.0`
- Output details:
  - failing node IDs
  - failing section IDs
  - metrics:
    - `extreme_jump_count`
    - `median_segment_length_um`
    - `mad_segment_length_um`
    - `jump_threshold_um`
    - `max_segment_length_um`
    - `sample_segments`
- Typical related issue tool:
  - `label_editing`

### Topology

#### `no_dangling_branches`

- Label: `No dangling branches`
- Source: native
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - scans all non-soma nodes
  - flags any non-soma node whose parent is `-1`
- Failure condition:
  - any non-soma node has parent `-1`
- Parameters:
  - none
- Output details:
  - failing node IDs = dangling non-soma node IDs
  - metric: `dangling_branch_count`
- Typical related issue tool:
  - `label_editing`

#### `no_self_loop`

- Label: `No self loops`
- Source: native
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - scans all nodes
  - flags any node whose `parent` is equal to its own `id`
- Failure condition:
  - one or more nodes directly self-reference as their own parent
- Parameters:
  - none
- Output details:
  - failing node IDs
  - metric: `self_loop_count`
- Typical related issue tool:
  - `label_editing`

#### `no_single_child_chains`

- Label: `No single-child chains`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_no_single_children`
- Failure condition:
  - NeuroM reports single-child chains
  - or the morphology cannot be built
- Parameters:
  - none
- Typical related issue tool:
  - `simplification`

#### `has_unifurcation`

- Label: `Contains unifurcation`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_unifurcation`
- Failure condition:
  - the morphology contains a unifurcation pattern
  - or the morphology cannot be built
- Parameters:
  - none
- Typical related issue tool:
  - `label_editing`

#### `has_multifurcation`

- Label: `Contains multifurcation`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - calls NeuroM `has_multifurcation`
- Failure condition:
  - the morphology contains a multifurcation
  - or the morphology cannot be built
- Parameters:
  - none
- Typical related issue tool:
  - `label_editing`

### Index Consistency

#### `no_section_index_jumps`

- Label: `No section index gaps`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - calls NeuroM `has_no_jumps`
- Failure condition:
  - NeuroM reports section index jumps
  - or the morphology cannot be built
- Parameters:
  - `max_distance`
    - default in config: `30.0`
  - `axis`
    - default in config: `"z"`
- Typical related issue tool:
  - `label_editing`

#### `no_root_index_jumps`

- Label: `Neurite roots too far from soma`
- Source: NeuroM / `neuron_morphology`
- Default enabled: yes
- Default severity: `error`
- Algorithm:
  - calls NeuroM `has_no_root_node_jumps`
- Failure condition:
  - NeuroM reports neurite root points that are too far from the soma
  - or the morphology cannot be built
- Parameters:
  - `radius_multiplier`
    - default in config: `2.0`
- Typical related issue tool:
  - `label_editing`

#### `parent_id_less_than_child_id`

- Label: `Parent ID is less than child ID`
- Source: native
- Default enabled: yes
- Default severity: `warning`
- Algorithm:
  - scans nodes with valid in-file parent IDs
  - flags nodes whose parent ID is greater than or equal to the child ID
- Failure condition:
  - one or more nodes violate the usual SWC parent-before-child ordering convention
- Parameters:
  - none
- Output details:
  - failing node IDs
  - metric: `id_order_violation_count`
- Typical related issue tool:
  - `label_editing`

## Issues Raised In The GUI Workflow

The issue-driven workflow can currently raise the following issue classes.

### 1. Validation Issues

These come from `issues_from_validation_report(...)`.

Behavior:

- every validation row with status `fail` becomes a `critical` issue
- every validation row with status `warning` becomes a `warning` issue
- passing rows are not shown as issues
- the displayed issue title uses finding-style wording on failure, for example:
  - `Duplicated points found`
  - `Multiple somas found`
- each issue inherits:
  - `source_key`
  - `source_label`
  - `source_category`
  - failing nodes / sections when available

Routing logic currently maps checks to tools like this:

- `radii_cleaning`
  - `all_neurite_radii_nonzero`
  - `soma_radius_nonzero`
  - `no_ultranarrow_sections`
  - `no_ultranarrow_starts`
  - `no_fat_terminal_ends`
- `auto_label`
  - `has_axon`
  - `has_basal_dendrite`
  - `has_apical_dendrite`
- `simplification`
  - `all_section_lengths_nonzero`
  - `all_segment_lengths_nonzero`
  - `no_duplicate_3d_points`
  - `no_single_child_chains`
- `label_editing`
  - `has_soma`
  - `no_back_tracking`
  - `no_flat_neurites`
  - `no_dangling_branches`
  - `no_self_loop`
  - `no_extreme_spatial_jump`
  - `has_unifurcation`
  - `has_multifurcation`
  - `no_section_index_jumps`
  - `no_root_index_jumps`
  - `parent_id_less_than_child_id`
- fallback
  - `validation`

### 2. Blocked Validation Issues

These come from `_blocked_reason_from_validation_row(...)` and grouped handling in `issues_from_validation_report(...)`.

Current blocked issue types:

#### `blocked_validation_checks`

- Certainty: `rule`
- Severity: `info`
- Raised when:
  - dependent NeuroM checks cannot run because the morphology cannot be built
  - example cause: `Unsupported section type: 0`
- Current user-facing titles:
  - `Checks blocked by unsupported node labels`
  - `Checks blocked by incompatible morphology`
- Behavior:
  - multiple blocked validation rows are collapsed into one aggregate issue
  - the issue payload stores a list of blocked checks
- Suggested fix:
  - fix the prerequisite morphology problem first

This is used specifically to avoid flooding the issue list with misleading downstream failures.

### 3. Suspicious Radii Issue

This comes from `issues_from_radii_suspicion(...)`.

#### `radii_outlier_batch`

- Title: `Outlier radii detected`
- Certainty: `suspicious`
- Severity: `warning`
- Domain: `radii`
- Tool target: `radii_cleaning`
- Aggregation:
  - one batch issue can contain many nodes
- Gating:
  - this issue is not generated when soma-stage validation gates fail
- How it is computed:
  - runs `clean_radii_dataframe(df)`
  - uses the same shared radii-cleaning engine as the CLI / GUI radii-clean tool
  - every node that the cleaner would modify becomes part of the suspicious batch
- Ignored nodes:
  - nodes already covered by critical radii validation issues can be excluded by the caller
- Payload:
  - `changes`
    - `node_id`
    - `old_radius`
    - `new_radius`
    - `reasons`

### 4. Suspicious Label Issue

This comes from `issues_from_type_suspicion(...)`.

#### `type_suspicion_batch`

- Title: `Likely wrong labels`
- Certainty: `suspicious`
- Severity: `warning`
- Domain: `label`
- Tool target: `label_editing`
- Aggregation:
  - one batch issue can contain many nodes
- Gating:
  - this issue is not generated when soma-stage validation gates fail
- How it is computed:
  - runs the rule-based auto-typing pipeline
  - compares current node type against suggested node type
  - every node where `old_type != new_type` becomes part of the suspicious batch
- Payload:
  - `changes`
    - `node_id`
    - `old_type`
    - `new_type`

## Radii Suspicion / Repair Algorithm

The radii suspicion issue and the Radii Cleaning tool both use `swctools/core/radii_cleaning.py`.

### Main logic

The current radii cleaner:

1. loads configured rules
2. computes per-type radius statistics
3. computes allowable lower/upper bounds per type
4. marks abnormal nodes using several detectors
5. proposes replacement radii using nearby valid topology context
6. iterates several times
7. performs final enforcement so no abnormal non-soma nodes remain
8. optionally preserves soma radii exactly

### Detectors used

The cleaner can mark a node abnormal for these reasons:

- `non_finite`
- `non_positive`
- `below_type_min`
- `above_type_max`
- `local_spike`
- `local_dip`
- `final_enforce`

### Replacement strategy

For an abnormal node, the replacement value is estimated from:

- nearest valid ancestor radius
- nearest valid descendant radius or descendant mean
- otherwise per-type median
- otherwise global median

Then the replacement is clamped to configured bounds.

### Radii-clean parameters

Current parameters from `swctools/tools/batch_processing/configs/radii_cleaning.json`:

- `preserve_soma`
  - default: `true`
  - soma radii are restored after cleaning
- `small_radius_zero_only`
  - default: `true`
  - lower-bound failures are only treated as abnormal when the value is `<= 0`
- `threshold_mode`
  - `percentile` or `absolute`
- `global_percentile_bounds.min`
  - default: `1.0`
- `global_percentile_bounds.max`
  - default: `99.5`
- `global_absolute_bounds.min`
  - default: `0.05`
- `global_absolute_bounds.max`
  - default: `30.0`
- `type_thresholds`
  - per-type overrides for:
    - `enabled`
    - `min_percentile`
    - `max_percentile`
    - `min_abs`
    - `max_abs`
- `replace_non_positive`
  - default: `true`
- `replace_non_finite`
  - default: `true`
- `detect_spikes`
  - default: `true`
- `detect_dips`
  - default: `true`
- `spike_ratio_threshold`
  - default: `2.8`
- `dip_ratio_threshold`
  - default: `0.35`
- `min_neighbor_count`
  - default: `1`
- `iterations`
  - default: `4`
- `max_descendant_search_depth`
  - default: `32`
- `replacement.clamp_min`
  - default: `0.05`
- `replacement.clamp_max`
  - default: `30.0`

## Label Suspicion / Auto-Typing Algorithm

The suspicious label issue currently relies on the shared rule-based auto-typing engine.

References:

- `swctools/core/auto_typing_impl.py`
- `swctools/core/auto_typing_catalog.py`
- `swctools/tools/batch_processing/configs/auto_typing.json`

### High-level algorithm

The current guide text describes the pipeline like this:

1. partition morphology into branch segments at soma/roots and bifurcations
2. compute branch features
   - path length
   - radial extent
   - mean radius
   - branchiness
   - z-mean
3. score each branch for axon / apical / basal using weighted features and priors
4. optionally refine with a nearest-centroid ML-like step seeded by confident branches
5. assign branch-level classes, smooth locally, then propagate labels back to nodes
6. optionally copy parent radius into zero/invalid radii

### Auto-typing parameters

Current parameters from `swctools/tools/batch_processing/configs/auto_typing.json`:

#### Output class options

- `options.soma`
- `options.axon`
- `options.basal`
- `options.apic`

These control which classes the auto-typing run is allowed to assign.

#### Missing-class assignment

- `rules.assign_missing.min_gain`
  - default: `-0.06`
- `rules.assign_missing.min_score`
  - default: `0.58`

#### Branch score weights

Per-class weighted feature scoring:

- `rules.branch_score_weights.axon`
  - `branch`
  - `path`
  - `prior`
  - `radial`
  - `radius`
  - `root_path`
  - `root_radial`
- `rules.branch_score_weights.basal`
  - `branch`
  - `path`
  - `prior`
  - `radius`
  - `root_path`
  - `root_radial`
  - `z`
- `rules.branch_score_weights.apical`
  - `branch`
  - `path`
  - `prior`
  - `radius`
  - `root_path`
  - `z`

#### ML / centroid blend

- `rules.ml_base_weight`
  - default: `0.72`
- `rules.ml_blend`
  - default: `0.28`

#### Propagation

- `rules.propagation_weights.branch_prior`
  - default: `0.30`
- `rules.propagation_weights.children`
  - default: `0.20`
- `rules.propagation_weights.iterations`
  - default: `4`
- `rules.propagation_weights.parent`
  - default: `0.35`
- `rules.propagation_weights.self`
  - default: `0.35`

#### Seeding and chunking

- `rules.seed_prior_threshold`
  - default: `0.55`
- `rules.segmenting.max_chunk_path`
  - default: `180.0`

#### Refinement

- `rules.refinement.child_weight`
  - default: `0.18`
- `rules.refinement.island_flip_margin`
  - default: `0.14`
- `rules.refinement.island_max_path`
  - default: `36.0`
- `rules.refinement.island_relative_max`
  - default: `0.35`
- `rules.refinement.iterations`
  - default: `2`
- `rules.refinement.parent_weight`
  - default: `0.14`

#### Smoothing

- `rules.smoothing.continuity_margin`
  - default: `0.02`
- `rules.smoothing.flip_margin`
  - default: `0.10`
- `rules.smoothing.maj_fraction`
  - default: `0.67`

#### Soma-child prior

- `rules.soma_child_prior.branch_boost`
  - default: `0.16`
- `rules.soma_child_prior.branch_weight`
  - default: `0.38`
- `rules.soma_child_prior.propagation_weight`
  - default: `0.30`
- `rules.soma_child_prior.score_weights.axon`
- `rules.soma_child_prior.score_weights.basal`
- `rules.soma_child_prior.score_weights.apical`

#### Radius handling

- `rules.radius.copy_parent_if_zero`
  - default: `true`

## How Checks Become Issues

Current conversion rules are:

- validation `pass`
  - no issue
- validation `warning`
  - `warning` issue
- validation `fail`
  - `critical` issue
- if `valid_soma_format` fails
  - validation stops immediately
- if `multiple_somas` fails
  - validation stops immediately after that check
- validation dependency/build errors
  - collapsed into one `blocked_validation_checks` issue instead of many downstream false failures
- suspicious radii changes
  - one aggregated `radii_outlier_batch` issue
- suspicious relabel suggestions
  - one aggregated `type_suspicion_batch` issue

## Existing Docs

There is already a validation-only overview here:

- `docs/VALIDATION_RULES.md`

That older document explains the shared validation backend, but it does not fully describe:

- blocked-check aggregation
- suspicious radii issues
- suspicious label issues
- issue model fields
- current issue-to-tool routing

This file is the more complete reference for the issue-driven workflow.
