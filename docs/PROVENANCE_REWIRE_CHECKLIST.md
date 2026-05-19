# Provenance rewire checklist

Tracking doc for the per-handler conversion work. Each item is a
discrete commit on `data-version-control`. Check off as we land them.

Conversion recipe lives in
[`PROVENANCE_CONVERSION_GUIDE.md`](PROVENANCE_CONVERSION_GUIDE.md).
Worked reference implementation lives in
[`swcstudio/cli/tracked_handlers_example.py`](../swcstudio/cli/tracked_handlers_example.py).

Legend: ⬜ todo · 🟦 in progress · ✅ done · ⏭ read-only, no conversion needed

---

## 1. CLI handlers (`swcstudio/cli/cli.py`)

### 1.1 Mutating — need `tracked_op` conversion

These each get one commit. Test each by running the command and
inspecting `.history/events.jsonl` + `current.swc` + the JSON output
your scripts depend on.

| # | Status | Command | cli.py line | Op kind | AI? | Notes |
|---|---|---|---|---|---|---|
| 1 | ✅ | `swcstudio morphology set-type` | 1104 | `SET_TYPE` | no | Done. Byte-identical to old path on a 28k-line real SWC; chain verified; original untouched. |
| 2 | ✅ | `swcstudio morphology set-radius` | 1076 | `SET_RADIUS` | no | Done. Byte-identical to bare feature on real SWC; node 1.radius: 2.5390625 → 9.9 round-trips; chain + verify clean. |
| 3 | ✅ | `swcstudio morphology dendrogram-edit` | 1051 | `DENDROGRAM_EDIT` | no | Done. Byte-identical on real SWC; 25,202-node subtree retype; changed_node_id_preview matches bare feature. |
| 4 | ✅ | `swcstudio validation auto-fix` | 905 | `AUTO_FIX` | no | Done. 1.3 MB byte-identical output on real SWC; 27 issues, validation results still printed to stdout; report_summary embedded in commit params. |
| 5 | 🟦 | `swcstudio validation auto-label` | 953 | `AUTO_LABEL` | **yes** | **Blocked**: pickle/numpy incompat in dev env (`MT19937 not a known BitGenerator`). Original handler also fails here — not a conversion regression. Resume on machine with working sklearn 1.5 + matching numpy. |
| 6 | ✅ | `swcstudio validation radii-clean` | 852 | `RADII_CLEAN` | no | Done (file mode only). Byte-identical 1.6 MB output on real SWC; 16 passes, 8,039 radius changes. Folder/batch mode still falls through to old path (item 1.2 #18). |
| 7 | ✅ | `swcstudio validation index-clean` | 1004 | `INDEX_CLEAN` | no | Done. Byte-identical reordering verified on a deliberately disordered 5-node SWC; remapped_id_count=2, id_map_size=5 preserved. |
| 8 | ✅ | `swcstudio geometry simplify` | 1131 | `SIMPLIFICATION` | no | Done. Byte-identical on real SWC; 28,075 → 9,164 nodes (67.36% reduction); params_used preserved. |
| 9 | ✅ | `swcstudio geometry move-node` | 1183 | `GEOMETRY_EDIT` | no | Done. Byte-identical; params {op:'move-node', node_id, x, y, z}. |
| 10 | ✅ | `swcstudio geometry move-subtree` | 1207 | `GEOMETRY_EDIT` | no | Done. Byte-identical; params {op:'move-subtree', root_id, x, y, z}. |
| 11 | ✅ | `swcstudio geometry connect` | 1231 | `GEOMETRY_EDIT` | no | Done. Byte-identical; params {op:'connect', start_id, end_id}. |
| 12 | ✅ | `swcstudio geometry disconnect` | 1265 | `GEOMETRY_EDIT` | no | Done. Byte-identical; path-existence sanity check preserved. |
| 13 | ✅ | `swcstudio geometry delete-node` | 1319 | `GEOMETRY_EDIT` | no | Done. Byte-identical; reconnect_children flag recorded in params. |
| 14 | ✅ | `swcstudio geometry delete-subtree` | 1353 | `GEOMETRY_EDIT` | no | Done. Byte-identical; params {op:'delete-subtree', root_id}. |
| 15 | ✅ | `swcstudio geometry insert` | 1383 | `GEOMETRY_EDIT` | no | Done. Byte-identical; params capture x/y/z and optional radius/type_id. |

### 1.2 Batch mutating — bulk variants

Batch handlers iterate over a folder. Each iteration should be its own
`tracked_op` commit on the **per-file** `.history/`. The batch-level
summary report should still print, but no batch-wide text report is
needed (each file's history covers it).

| # | Status | Command | cli.py line | Op kind | AI? |
|---|---|---|---|---|---|
| 16 | ✅ | `swcstudio batch split` | 764 | `SPLIT` (+ `derived_from` per child) | no | Done. multi-soma split into 4 trees, each output gets its own .history/ with derived_from pointing to source file. single-soma correctly skipped (no split needed). |
| 17 | ⬜ | `swcstudio batch auto-typing` | 774 | `AUTO_LABEL` | **yes** |
| 18 | ✅ | `swcstudio batch radii-clean` | 802 | `RADII_CLEAN` | no | Done. Folder mode uses _tracked_batch; file mode delegates to converted single-file path. multi-soma: 17 passes, 3,305 changes. |
| 19 | ✅ | `swcstudio batch simplify` | 812 | `SIMPLIFICATION` | no | Done. multi-soma: 6,155 → 1,356 nodes (77.97% reduction); per-file commit on each input. |
| 20 | ✅ | `swcstudio batch index-clean` | 822 | `INDEX_CLEAN` | no | Done. 4-file test (3 unique contents) succeeds; per-file .history/ created on each input; identical content produces identical commit SHA (content-addressing confirmed). |

### 1.3 Read-only — no conversion needed

| Status | Command | Why skipped |
|---|---|---|
| ⏭ | `swcstudio check` | Read-only validation |
| ⏭ | `swcstudio batch validate` | Read-only validation across folder |
| ⏭ | `swcstudio validation run` | Read-only check run |
| ⏭ | `swcstudio validation rule-guide` | Prints guide; no I/O |
| ⏭ | `swcstudio visualization mesh-editing` | Prepares mesh; no SWC mutation |
| ⏭ | `swcstudio train auto-typing` | Trains models; doesn't mutate SWCs |
| ⏭ | `swcstudio models status` | Informational |
| ⏭ | `swcstudio plugins {list,list-loaded,load}` | Informational |
| ⏭ | `swcstudio history *` | Already uses provenance APIs |

---

## 2. GUI handlers (`swcstudio/gui/main_window.py` slots)

All mutation goes through main_window slots that receive panel
signals. Converting these covers the entire GUI.

Each gets one commit. Test by clicking through the panel manually,
then check History → Open History Browser to confirm a commit landed
with the right op kind + params.

| # | Status | Slot method | line | Triggered by | Op kind | AI? |
|---|---|---|---|---|---|---|
| G1 | ⬜ | `_on_validation_auto_label_process_requested` | 1894 | validation_auto_label_panel | `AUTO_LABEL` | **yes** |
| G2 | ⬜ | `_on_manual_radii_apply_requested` | 2125 | manual_radii_panel | `MANUAL_RADII` | no |
| G3 | ⬜ | `_on_validation_radii_apply_requested` | 2159 | validation_tab radii fix | `RADII_CLEAN` | no |
| G4 | ⬜ | `_on_geometry_move_selection_requested` | 2245 | geometry_editing_panel | `GEOMETRY_EDIT` | no |
| G5 | ⬜ | `_on_geometry_reconnect_requested` | 2275 | geometry_editing_panel | `GEOMETRY_EDIT` | no |
| G6 | ⬜ | `_on_geometry_disconnect_requested` | 2308 | geometry_editing_panel | `GEOMETRY_EDIT` | no |
| G7 | ⬜ | `_on_geometry_delete_node_requested` | 2361 | geometry_editing_panel | `GEOMETRY_EDIT` | no |
| G8 | ⬜ | `_on_geometry_delete_subtree_requested` | 2392 | geometry_editing_panel | `GEOMETRY_EDIT` | no |
| G9 | ⬜ | `_on_geometry_insert_node_requested` | 2421 | geometry_editing_panel | `GEOMETRY_EDIT` | no |
| G10 | ⬜ | `_on_validation_index_clean_requested` | 3287 | validation_tab index-clean | `INDEX_CLEAN` | no |
| G11 | ⬜ | `_on_apply_suggested_fix_requested` | 4026 | issue_panel single-fix | `AUTO_FIX` | no |
| G12 | ⬜ | `_on_save` | 2707 | File → Save (Ctrl+S) | **session close** | no |
| G13 | ⬜ | `_on_save_as` | 2719 | File → Save As | **session close** | no |

### 2.1 Panel-side direct mutation paths (also need attention)

These panels write SWC files themselves rather than emitting a
signal to main_window. Each needs its own commit.

| # | Status | File | Method | Notes |
|---|---|---|---|---|
| G14 | ⬜ | `radii_cleaning_panel.py` | `_on_run_loaded` (line 326) | Wraps `clean_path`; convert to `tracked_op(kind=RADII_CLEAN)` |
| G15 | ⬜ | `radii_cleaning_panel.py` | `_on_run_folder` (line 379) | Folder batch — one commit per file |
| G16 | ⬜ | `simplification_panel.py` | `_on_process` (line 168) | Wraps `simplify_file`; `SIMPLIFICATION` |
| G17 | ⬜ | `simplification_panel.py` | `_on_save` (line 286) | Saves edited result |
| G18 | ⬜ | `validation_auto_label_panel.py` | `_on_save` (line 92) | Saves auto-label result |

### 2.2 Read-only / no conversion needed

| Status | File | Why skipped |
|---|---|---|
| ⏭ | `editor_tab.py` | In-memory dataframe edits; final save goes through `_on_save` (G12) |
| ⏭ | `validation_tab.py` (read paths) | Validation display only; mutation paths are G3/G10/G11 |
| ⏭ | `dendrogram_widget.py` | Display widget |
| ⏭ | `neuron_3d_widget.py` | 3D viewer |
| ⏭ | `swc_table_widget.py` | Display widget |
| ⏭ | `issue_panel.py` | Drives validation; mutation goes through G11 |
| ⏭ | `batch_tab.py` | Wraps batch CLI handlers (covered by 1.2) |
| ⏭ | `custom_type_dialog.py` | Edits custom-type definitions, not SWC |
| ⏭ | `context_inspector.py` | Display |
| ⏭ | `report_popup.py` | Display |
| ⏭ | `auto_typing_guide.py` | Display |
| ⏭ | `validation_auto_label_panel.py` (run path) | The actual run is G1 via signal |

---

## 3. Final deletion commit (after 1.1 + 1.2 + 2 are done)

| Status | Action |
|---|---|
| ⬜ | `git rm swcstudio/core/reporting.py` |
| ⬜ | Remove every `from swcstudio.core.reporting import ...` line across the tree |
| ⬜ | Update `docs/LOGS_AND_REPORTS.md` to point at `provenance.render` |

Files currently importing `swcstudio.core.reporting` (all 14 must be cleaned before deletion):

- `swcstudio/cli/cli.py`
- `swcstudio/gui/main_window.py`
- `swcstudio/gui/validation_tab.py`
- `swcstudio/tools/batch_processing/features/{radii_cleaning,index_clean,simplification,batch_validation,swc_splitter}.py`
- `swcstudio/tools/morphology_editing/features/{manual_radii,manual_label,dendrogram_editing,simplification}.py`
- `swcstudio/tools/validation/features/{auto_fix,auto_typing,index_clean}.py`

---

## Running totals

- **15** single-file CLI handlers to convert (1.1)
- **5** batch CLI handlers to convert (1.2)
- **13** GUI slot handlers in main_window to convert (2)
- **5** panel-side mutation methods to convert (2.1)
- **38** total mutation-path commits, plus the final deletion commit
- **0** total Python tests required to pre-exist (we'll test each by hand as we go)

---

## Working agreement

For each item:

1. I'll write the conversion as a small diff.
2. You'll run the matching CLI command or click through the matching
   GUI flow to confirm behavior.
3. We commit; check it off; move to the next.
4. Once 1.1, 1.2, and 2 are all ✅, we do the deletion commit (item 3)
   in one shot.

Suggested starting order (easiest → harder):

1. `morphology set-type` (#1) — simplest; copy of the worked example
2. `morphology set-radius` (#2) — identical shape to #1
3. `validation index-clean` (#7) — single-file, no AI
4. `validation auto-fix` (#4) — multi-rule, no AI
5. `validation auto-label` (#5) — first AI op
6. … continue with the remaining single-file CLI handlers
7. … then geometry handlers (#9–15)
8. … then batch handlers (#16–20) — these need the per-file/per-commit-per-file pattern
9. … then GUI slots (#G1–G13), starting with `_on_manual_radii_apply_requested` (G2 — simplest)
10. … then panel-side direct paths (G14–G18)
11. … finally the deletion commit (item 3)

Pick whichever you want to start with. I default to #1 if you don't specify.
