"""Public entry points for the auto-typing engine.

Four stages drive every prediction:

* Stage 1: cell-type detector (sklearn ensemble, 49 whole-cell
  features) decides pyramidal vs interneuron with a soft handoff.
* Stage 2: per-subtree axon/basal/apical classifier (sklearn
  ensemble), propagated to all branches in the same primary subtree.
* Stage 2b: GraphSAGE GNN over the branch graph re-decides
  apical-vs-basal for pyramidal dendrite branches.
* Stage 3: topology refinement.

All four stages are required. ``is_available`` returns False if any
of the three model files (Stage 1 pickle, Stage 2 pickle, GNN
checkpoint) or torch / torch_geometric are missing.

Public surface:

* ``run_file(path, opts, ...)`` returns ``FileResult``
* ``run_batch(folder, opts, ...)`` returns ``BatchResult``
* ``is_available()`` returns ``(bool, reason)``
* ``backend_status()`` returns a diagnostic dict
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from swcstudio.core.model_paths import (
    diagnostic_search_report,
    resolve_model_path,
)
from swcstudio.core.reporting import (
    auto_typing_log_path_for_file,
    format_auto_typing_report_text,
    operation_output_dir_for_folder,
    operation_output_path_for_file,
    operation_report_path_for_file,
    operation_report_path_for_folder,
    timestamp_slug,
    write_text_report,
)

from .types import BatchOptions, BatchResult, FileResult


# ---------------------------------------------------------------------------
# Availability / diagnostics
# ---------------------------------------------------------------------------


def is_available(*, model_dir: str | None = None) -> tuple[bool, str]:
    """Return ``(ok, reason)`` describing whether the auto-typing engine
    can run right now.

    The engine requires all three model files (Stage 1 sklearn pickle,
    Stage 2 sklearn pickle, Stage 2b GNN checkpoint) plus torch and
    torch_geometric — they are required dependencies of the package, so
    a normal install satisfies them. When something is missing this
    returns ``(False, reason)`` with a search-path diagnostic so the
    GUI / CLI can fail fast with a clear message.
    """
    s1 = resolve_model_path("stage1", override=model_dir)
    s2 = resolve_model_path("stage2", override=model_dir)
    gnn = resolve_model_path("gnn", override=model_dir)
    missing = []
    if s1 is None:
        missing.append("Stage 1 (cell_type_classifier.pkl)")
    if s2 is None:
        missing.append("Stage 2 (branch_classifier.pkl)")
    if gnn is None:
        missing.append("Stage 2b GNN (gnn_apical_basal.pt)")
    if missing:
        return False, (
            "Auto-typing is missing required model files: "
            + ", ".join(missing) + ".\n"
            + diagnostic_search_report(override=model_dir)
        )
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return False, (
            "Auto-typing requires torch and torch_geometric "
            f"(import failed: {exc.__class__.__name__}: {exc}). "
            "Reinstall the package: `pip install -e .`."
        )
    return True, "available"


def backend_status(*, model_dir: str | None = None) -> dict[str, Any]:
    """Structured status report. Used by the CLI ``models status`` command
    and the GUI to surface the resolved model paths and torch availability.
    """
    s1 = resolve_model_path("stage1", override=model_dir)
    s2 = resolve_model_path("stage2", override=model_dir)
    gnn = resolve_model_path("gnn", override=model_dir)

    torch_ok = True
    torch_msg = "torch + torch_geometric available"
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        torch_ok = False
        torch_msg = f"torch / torch_geometric unavailable: {exc.__class__.__name__}"

    return {
        "stage1_path": str(s1) if s1 else None,
        "stage2_path": str(s2) if s2 else None,
        "gnn_path": str(gnn) if gnn else None,
        "stage1_ok": s1 is not None,
        "stage2_ok": s2 is not None,
        "gnn_ok": gnn is not None and torch_ok,
        "torch_ok": torch_ok,
        "torch_message": torch_msg,
        "search_diagnostic": diagnostic_search_report(override=model_dir),
    }


# ---------------------------------------------------------------------------
# Internal: load GNN once and reuse across files in a batch
# ---------------------------------------------------------------------------


_GNN_CACHE: dict[str, Any] = {"path": None, "state": None}


def _load_gnn_state(model_dir: str | None) -> Any:
    """Load the Stage 2b GNN checkpoint. Raises if it cannot be loaded —
    the GNN is a required pipeline stage, not optional.
    """
    gnn_path = resolve_model_path("gnn", override=model_dir)
    if gnn_path is None:
        raise FileNotFoundError(
            "Stage 2b GNN checkpoint (gnn_apical_basal.pt) not found.\n"
            + diagnostic_search_report(override=model_dir)
        )
    cache_key = str(gnn_path.resolve())
    if _GNN_CACHE.get("path") == cache_key and _GNN_CACHE.get("state") is not None:
        return _GNN_CACHE["state"]
    from .gnn_inference import load_gnn  # noqa: PLC0415
    state = load_gnn(gnn_path)
    _GNN_CACHE["path"] = cache_key
    _GNN_CACHE["state"] = state
    return state


# ---------------------------------------------------------------------------
# SWC parse / write / diff helpers (shared with rest of swcstudio)
# ---------------------------------------------------------------------------


def _parse_swc(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    headers: list[str] = []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                headers.append(line.rstrip("\n"))
                continue

            parts = s.split()
            if len(parts) < 7:
                continue

            try:
                rid = int(float(parts[0]))
                rtype = int(float(parts[1]))
                x = float(parts[2])
                y = float(parts[3])
                z = float(parts[4])
                radius = float(parts[5])
                parent = int(float(parts[6]))
            except Exception:
                continue

            rows.append(
                {
                    "id": rid,
                    "type": rtype,
                    "x": x,
                    "y": y,
                    "z": z,
                    "radius": radius,
                    "parent": parent,
                }
            )
    return headers, rows


def _write_swc(
    path: Path,
    headers: list[str],
    rows: list[dict[str, Any]],
    types: list[int],
    radii: list[float],
) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for h in headers:
            fh.write(f"{h}\n")
        for i, row in enumerate(rows):
            fh.write(
                f"{int(row['id'])} {int(types[i])} "
                f"{float(row['x']):.10g} {float(row['y']):.10g} {float(row['z']):.10g} "
                f"{float(radii[i]):.10g} {int(row['parent'])}\n"
            )


def _build_change_details(
    file_name: str,
    rows: list[dict[str, Any]],
    orig_types: list[int],
    new_types: list[int],
    orig_radii: list[float],
    new_radii: list[float],
) -> list[str]:
    out: list[str] = []
    type_changes = sum(1 for old, new in zip(orig_types, new_types) if int(old) != int(new))
    radius_changes = sum(1 for old, new in zip(orig_radii, new_radii) if float(old) != float(new))
    if type_changes <= 0 and radius_changes <= 0:
        return out

    out.append(f"[{file_name}]")
    if type_changes > 0:
        out.append("type_changes:")
        for row, old_t, new_t in zip(rows, orig_types, new_types):
            if int(old_t) != int(new_t):
                out.append(
                    f"  node_id={int(row['id'])}: old_type={int(old_t)} -> new_type={int(new_t)}"
                )
    if radius_changes > 0:
        out.append("radius_changes:")
        for row, old_r, new_r in zip(rows, orig_radii, new_radii):
            if float(old_r) != float(new_r):
                out.append(
                    f"  node_id={int(row['id'])}: "
                    f"old_radius={float(old_r):.10g} -> new_radius={float(new_r):.10g}"
                )
    out.append("")
    return out


# ---------------------------------------------------------------------------
# Conversion: parsed SWC rows <-> pipeline SWCNode list
# ---------------------------------------------------------------------------


def _rows_to_swc_nodes(rows: list[dict[str, Any]]) -> list:
    from .features import SWCNode  # noqa: PLC0415

    return [
        SWCNode(
            id=int(row["id"]),
            type=int(row["type"]),
            x=float(row["x"]),
            y=float(row["y"]),
            z=float(row["z"]),
            radius=float(row["radius"]),
            parent=int(row["parent"]),
        )
        for row in rows
    ]


def _apply_pipeline_to_rows(
    rows: list[dict[str, Any]],
    *,
    opts: BatchOptions,
    stage1_path: Path,
    stage2_path: Path,
    gnn_state: Any | None,
    use_subtree_stage2: bool,
) -> tuple[list[int], list[float], int, int]:
    """Run the pipeline on parsed SWC rows. Returns
    ``(types, radii, type_changes, radius_changes)``.

    The ``opts`` flags map onto the pipeline like this:

        opts.soma   - soma is detected by Stage 1 and assigned via the
                      proxy-soma rule. The flag controls whether we
                      *write* the predicted soma label (default True).
        opts.axon, opts.basal, opts.apic
                    - per-cell-type label gates. When the pipeline
                      predicts an axon for an interneuron and the user
                      has disabled axon, the original label is kept.
        opts.rad    - radius cleanup. The pipeline does not modify radii
                      itself; we apply the simple "copy parent radius
                      if zero" rule when the flag is set.
    """
    from .pipeline import run_pipeline_on_nodes  # noqa: PLC0415

    nodes = _rows_to_swc_nodes(rows)
    if not nodes:
        return (
            [int(r["type"]) for r in rows],
            [float(r["radius"]) for r in rows],
            0,
            0,
        )

    result = run_pipeline_on_nodes(
        nodes,
        file_path="",
        stage1_model=stage1_path,
        stage2_model=stage2_path,
        gnn_state=gnn_state,
        use_subtree_stage2=use_subtree_stage2,
    )
    pipeline_types = list(result.node_labels)

    orig_types = [int(r["type"]) for r in rows]
    final_types: list[int] = []
    enabled_neurites: set[int] = set()
    if opts.axon:
        enabled_neurites.add(2)
    if opts.basal:
        enabled_neurites.add(3)
    if opts.apic:
        enabled_neurites.add(4)

    for old_t, new_t in zip(orig_types, pipeline_types):
        new_t = int(new_t)
        if new_t == 1:
            final_types.append(1 if opts.soma else int(old_t))
        elif new_t in {2, 3, 4}:
            if not enabled_neurites:
                final_types.append(int(old_t))
            elif new_t in enabled_neurites:
                final_types.append(new_t)
            else:
                final_types.append(int(old_t))
        else:
            final_types.append(int(old_t))

    radii_orig = [float(r["radius"]) for r in rows]
    radii = list(radii_orig)
    if opts.rad:
        id_to_idx = {int(r["id"]): i for i, r in enumerate(rows)}
        order: list[int] = []
        seen: set[int] = set()
        roots = [
            i for i, r in enumerate(rows)
            if int(r["parent"]) == -1 or int(r["parent"]) not in id_to_idx
        ]
        queue = list(roots)
        while queue:
            idx = queue.pop(0)
            if idx in seen:
                continue
            seen.add(idx)
            order.append(idx)
            for j, r in enumerate(rows):
                if id_to_idx.get(int(r["parent"])) == idx and j not in seen:
                    queue.append(j)
        for idx in order:
            pidx = id_to_idx.get(int(rows[idx]["parent"]))
            if pidx is None:
                continue
            if radii[idx] <= 0 and radii[pidx] > 0:
                radii[idx] = radii[pidx]

    type_changes = sum(
        1 for old, new in zip(orig_types, final_types) if int(old) != int(new)
    )
    radius_changes = sum(
        1 for old, new in zip(radii_orig, radii) if float(old) != float(new)
    )
    return final_types, radii, type_changes, radius_changes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_file(
    file_path: str,
    opts: BatchOptions,
    *,
    output_path: str | None = None,
    write_output: bool = True,
    write_log: bool = True,
    model_dir: str | None = None,
    use_subtree_stage2: bool = True,
) -> FileResult:
    """Run the auto-typing engine on one SWC file."""
    ok, reason = is_available(model_dir=model_dir)
    if not ok:
        raise FileNotFoundError(reason)

    stage1_path = resolve_model_path("stage1", override=model_dir)
    stage2_path = resolve_model_path("stage2", override=model_dir)
    gnn_state = _load_gnn_state(model_dir)

    in_path = Path(file_path)
    headers, rows = _parse_swc(in_path)
    if not rows:
        raise ValueError(f"{in_path.name}: no valid SWC rows")

    orig_types = [int(r["type"]) for r in rows]
    orig_radii = [float(r["radius"]) for r in rows]
    types, radii, type_changes, radius_changes = _apply_pipeline_to_rows(
        rows,
        opts=opts,
        stage1_path=stage1_path,
        stage2_path=stage2_path,
        gnn_state=gnn_state,
        use_subtree_stage2=use_subtree_stage2,
    )

    out_path: Path | None = None
    run_timestamp = timestamp_slug()
    if write_output:
        out_path = (
            Path(output_path)
            if output_path
            else operation_output_path_for_file(in_path, "auto_typing", timestamp=run_timestamp)
        )
        _write_swc(out_path, headers, rows, types, radii)

    out_counts = {
        1: sum(1 for t in types if int(t) == 1),
        2: sum(1 for t in types if int(t) == 2),
        3: sum(1 for t in types if int(t) == 3),
        4: sum(1 for t in types if int(t) == 4),
    }
    change_details = _build_change_details(
        in_path.name,
        rows,
        orig_types,
        types,
        orig_radii,
        radii,
    )

    log_path: str | None = None
    if write_log:
        log_target = (
            auto_typing_log_path_for_file(in_path)
            if output_path
            else operation_report_path_for_file(in_path, "auto_typing", timestamp=run_timestamp)
        )
        payload = {
            "folder": str(in_path.parent),
            "out_dir": str(out_path.parent if out_path is not None else in_path.parent),
            "zip_path": None,
            "files_total": 1,
            "files_processed": 1,
            "files_failed": 0,
            "total_nodes": len(rows),
            "total_type_changes": type_changes,
            "total_radius_changes": radius_changes,
            "failures": [],
            "per_file": [
                f"{in_path.name}: nodes={len(rows)}, type_changes={type_changes}, "
                f"radius_changes={radius_changes}, out_types(soma/axon/basal/apic)="
                f"{out_counts[1]}/{out_counts[2]}/{out_counts[3]}/{out_counts[4]}"
            ],
            "change_details": change_details,
        }
        log_path = write_text_report(log_target, format_auto_typing_report_text(payload))

    return FileResult(
        input_file=str(in_path),
        output_file=str(out_path) if out_path is not None else None,
        nodes_total=len(rows),
        type_changes=type_changes,
        radius_changes=radius_changes,
        out_type_counts=out_counts,
        failures=[],
        change_details=change_details,
        log_path=log_path,
        headers=headers,
        rows=rows,
        types=types,
        radii=radii,
    )


def run_batch(
    folder: str,
    opts: BatchOptions,
    *,
    model_dir: str | None = None,
    use_subtree_stage2: bool = True,
) -> BatchResult:
    """Run the auto-typing engine on every ``.swc`` file in ``folder``."""
    ok, reason = is_available(model_dir=model_dir)
    if not ok:
        raise FileNotFoundError(reason)

    stage1_path = resolve_model_path("stage1", override=model_dir)
    stage2_path = resolve_model_path("stage2", override=model_dir)
    gnn_state = _load_gnn_state(model_dir)

    in_dir = Path(folder)
    swc_files = sorted([
        p for p in in_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".swc"
    ])

    run_timestamp = timestamp_slug()
    out_dir = operation_output_dir_for_folder(
        in_dir, "batch_auto_typing", timestamp=run_timestamp,
    )

    failures: list[str] = []
    per_file: list[str] = []
    change_details: list[str] = []

    processed = 0
    total_nodes = 0
    total_type_changes = 0
    total_radius_changes = 0

    for swc_path in swc_files:
        try:
            headers, rows = _parse_swc(swc_path)
            if not rows:
                failures.append(f"{swc_path.name}: no valid SWC rows")
                continue

            orig_types = [int(r["type"]) for r in rows]
            orig_radii = [float(r["radius"]) for r in rows]
            types, radii, type_changes, radius_changes = _apply_pipeline_to_rows(
                rows,
                opts=opts,
                stage1_path=stage1_path,
                stage2_path=stage2_path,
                gnn_state=gnn_state,
                use_subtree_stage2=use_subtree_stage2,
            )
            out_path = operation_output_path_for_file(
                swc_path,
                "batch_auto_typing",
                output_dir=out_dir,
                timestamp=run_timestamp,
            )
            _write_swc(out_path, headers, rows, types, radii)

            processed += 1
            total_nodes += len(rows)
            total_type_changes += type_changes
            total_radius_changes += radius_changes
            out_counts = {
                1: sum(1 for t in types if int(t) == 1),
                2: sum(1 for t in types if int(t) == 2),
                3: sum(1 for t in types if int(t) == 3),
                4: sum(1 for t in types if int(t) == 4),
            }
            per_file.append(
                f"{swc_path.name}: nodes={len(rows)}, type_changes={type_changes}, "
                f"radius_changes={radius_changes}, out_types(soma/axon/basal/apic)="
                f"{out_counts[1]}/{out_counts[2]}/{out_counts[3]}/{out_counts[4]}"
            )

            change_details.extend(
                _build_change_details(
                    swc_path.name, rows, orig_types, types, orig_radii, radii,
                )
            )
        except Exception as e:  # noqa: BLE001
            failures.append(f"{swc_path.name}: {e}")

    zip_path: str | None = None
    if opts.zip_output and processed > 0:
        zip_target = in_dir / f"{out_dir.name}.zip"
        with zipfile.ZipFile(zip_target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(out_dir.glob("*.swc")):
                zf.write(f, arcname=f"{out_dir.name}/{f.name}")
        zip_path = str(zip_target)

    payload = {
        "folder": str(in_dir),
        "out_dir": str(out_dir),
        "zip_path": zip_path,
        "files_total": len(swc_files),
        "files_processed": processed,
        "files_failed": len(failures),
        "total_nodes": total_nodes,
        "total_type_changes": total_type_changes,
        "total_radius_changes": total_radius_changes,
        "failures": failures,
        "per_file": per_file,
        "change_details": change_details,
    }
    log_path = write_text_report(
        operation_report_path_for_folder(
            in_dir, "batch_auto_typing", output_dir=out_dir, timestamp=run_timestamp,
        ),
        format_auto_typing_report_text(payload),
    )

    return BatchResult(
        folder=str(in_dir),
        out_dir=str(out_dir),
        zip_path=zip_path,
        files_total=len(swc_files),
        files_processed=processed,
        files_failed=len(failures),
        total_nodes=total_nodes,
        total_type_changes=total_type_changes,
        total_radius_changes=total_radius_changes,
        failures=failures,
        per_file=per_file,
        log_path=log_path,
    )


__all__ = [
    "is_available",
    "backend_status",
    "run_file",
    "run_batch",
]
