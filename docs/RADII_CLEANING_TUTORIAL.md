# Radii Cleaning Tutorial

Radii Cleaning fixes abnormal radius values while preserving branch continuity.

OS note: replace `./data/...` with `.\data\...` on Windows. If `swctools` is not on PATH, use module mode (`python -m swctools.cli.cli ...` on macOS/Linux, `py -m swctools.cli.cli ...` on Windows).

Shared backend module:

- `swctools.tools.batch_processing.features.radii_cleaning`

Validation tool reuses the same implementation through:

- `swctools.tools.validation.features.radii_cleaning`

So GUI Batch tab, GUI Validation tab, and CLI all use one core behavior.

## What counts as abnormal

The current cleaner treats the SWC as directed paths instead of a flat node list.

It looks for:

- non-positive radii (`<= 0`)
- non-finite radii (`NaN`, `inf`)
- local single-node spikes relative to a 5-node path window
- radii that violate configured sanity bounds
- branch points that become thicker distally than biologically expected

## Triple-pass refinement

The current cleaner follows a path-aware three-pass method:

1. `Local outlier repair`
   - uses a 5-node neighborhood (`2` upstream, `2` downstream)
   - computes the local median radius
   - flags a node when `|R_current - R_median| / R_median > 0.5`
   - immediately replaces the flagged radius with the local median or a topology-based fallback
2. `Global taper enforcement`
   - walks each branch segment from soma/proximal anchor toward the leaf
   - enforces `R_i <= R_(i-1) * (1 + slack)`
   - default taper slack is `0.05`
   - axons can also enforce a minimum floor radius
3. `Savitzky-Golay-style smoothing`
   - uses a local quadratic fit on each directed path
   - default window is `7` nodes
   - default polynomial order is `2`
   - smoothing runs after spike repair and taper enforcement, then taper is re-enforced once

## Key config file

- `swctools/tools/batch_processing/configs/radii_cleaning.json`

Validation radii cleaning is a thin wrapper over the same backend and can layer per-tool overrides through:

- `swctools/tools/validation/configs/radii_cleaning.json`

## Important config fields

Under `rules`:

- soma radii are always preserved during radii cleaning
- `small_radius_zero_only`: only treat very small values as abnormal if they are zero
- `sanity_bounds.global.lower_percentile`
- `sanity_bounds.global.upper_percentile`
- `sanity_bounds.global.lower_abs`
- `sanity_bounds.global.upper_abs`
- `sanity_bounds.per_type`: per-type overrides
  - `enabled`
  - `lower_percentile`
  - `upper_percentile`
  - `lower_abs`
  - `upper_abs`
- `local_outlier.enabled`
- `local_outlier.window_nodes`
  - default: `5`
- `local_outlier.max_percent_deviation`
  - default: `0.5`
- `taper.enabled`
- `taper.slack`
  - default: `0.05`
- `axon_floor.enabled`
- `axon_floor.min_radius`
  - default: `0.12`
- `savgol.enabled`
- `savgol.window_nodes`
  - default: `7`
- `savgol.polyorder`
  - default: `2`
- `savgol.gaussian_sigma_fraction`
  - default: `0.5`
- `fixed_point.enabled`
- `fixed_point.max_passes`
  - default: `32`
- `fixed_point.min_effective_delta`
  - default: `0.005`
- `replacement.clamp_min`, `replacement.clamp_max`

## CLI examples

Clean one file with the current JSON-configured three-pass method:

```bash
swctools batch radii-clean ./data/single-soma.swc
```

Clean one file while overriding rules for this run:

```bash
swctools batch radii-clean ./data/single-soma.swc --config-json '{"rules":{"local_outlier":{"max_percent_deviation":0.4}}}'
```

Validation command path (same backend):

```bash
swctools validation radii-clean ./data/single-soma.swc
```

## Outputs and logs

- file mode: writes `<stem>_radii_cleaned.swc` and `<stem>_radii_cleaning_report.txt`
- folder mode: writes `<folder>/<folder>_radii_cleaned/` plus folder report

Report includes:

- change counts
- per-file summary (folder mode)
- node-level change lines with old/new radii and reasons such as:
  - `local_outlier`
  - `non_positive`
  - `non_finite`
  - `taper_cap`
  - `post_smooth_taper_cap`
  - `axon_floor`
  - `savitzky_golay`
- config used

## GUI notes

- GUI panels expose JSON editor to adjust the three-pass behavior
- histogram/statistics view helps inspect the affected radius distribution
- run-on-loaded-file and run-on-folder are available in appropriate panels
- Auto Radii Editing runs to a fixed point so the cleaned file should reopen without the `Outlier radii detected` issue under the same rules
