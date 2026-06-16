"""Public entry points for the auto-typing engine.

The v12 QC-label-flag path drives every prediction:

* Stage 1: cell-type detector (sklearn ensemble, 49 whole-cell
  features) decides pyramidal vs interneuron with a soft handoff.
* Stage 2: per-subtree axon/basal/apical classifier (sklearn
  ensemble), propagated to all branches in the same primary subtree.
* Stage 2b: GraphSAGE GNN over the branch graph re-decides
  apical-vs-basal for pyramidal dendrite branches.
* Stage 3: topology refinement plus conservative Branch3 rescue.
* QC/flag: runtime QC metadata and learned per-cell bad-label flag.

The core model files are required. ``is_available`` returns False if any
of the Stage 1, Stage 2, GNN, Branch3, or QC-gate files are missing.

Public surface:

* ``run_file(path, opts, ...)`` returns ``FileResult``
* ``run_batch(folder, opts, ...)`` returns ``BatchResult``
* ``is_available()`` returns ``(bool, reason)``
* ``backend_status()`` returns a diagnostic dict
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Callable

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

    The engine requires the v12 model files (Stage 1 sklearn pickle,
    Stage 2 sklearn pickle, Stage 2b GNN checkpoint, Branch3 rescue
    checkpoint, and QC gate) plus torch and
    torch_geometric — they are required dependencies of the package, so
    a normal install satisfies them. When something is missing this
    returns ``(False, reason)`` with a search-path diagnostic so the
    GUI / CLI can fail fast with a clear message.
    """
    s1 = resolve_model_path("stage1", override=model_dir)
    s2 = resolve_model_path("stage2", override=model_dir)
    gnn = resolve_model_path("gnn", override=model_dir)
    branch3 = resolve_model_path("branch3", override=model_dir)
    qc_gate = resolve_model_path("qc_gate", override=model_dir)
    missing = []
    if s1 is None:
        missing.append("Stage 1 (cell_type_classifier.pkl)")
    if s2 is None:
        missing.append("Stage 2 (branch_classifier.pkl)")
    if gnn is None:
        missing.append("Stage 2b GNN (gnn_apical_basal.pt)")
    if branch3 is None:
        missing.append("Branch3 rescue head (gnn_branch3_rescue.pt)")
    if qc_gate is None:
        missing.append("QC gate (qc_gate.pkl)")
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
    branch3 = resolve_model_path("branch3", override=model_dir)
    qc_gate = resolve_model_path("qc_gate", override=model_dir)
    flag_pyr = resolve_model_path("flag_pyramidal", override=model_dir)
    flag_int = resolve_model_path("flag_interneuron", override=model_dir)
    flag_all = resolve_model_path("flag_all", override=model_dir)

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
        "branch3_path": str(branch3) if branch3 else None,
        "qc_gate_path": str(qc_gate) if qc_gate else None,
        "flag_pyramidal_path": str(flag_pyr) if flag_pyr else None,
        "flag_interneuron_path": str(flag_int) if flag_int else None,
        "flag_all_path": str(flag_all) if flag_all else None,
        "stage1_ok": s1 is not None,
        "stage2_ok": s2 is not None,
        "gnn_ok": gnn is not None and torch_ok,
        "branch3_ok": branch3 is not None and torch_ok,
        "qc_gate_ok": qc_gate is not None,
        "flag_pyramidal_ok": flag_pyr is not None,
        "flag_interneuron_ok": flag_int is not None,
        "flag_all_ok": flag_all is not None,
        "torch_ok": torch_ok,
        "torch_message": torch_msg,
        "search_diagnostic": diagnostic_search_report(override=model_dir),
    }


# ---------------------------------------------------------------------------
# Internal: load GNN once and reuse across files in a batch
# ---------------------------------------------------------------------------


_GNN_CACHE: dict[str, Any] = {"path": None, "state": None}
_BRANCH3_CACHE: dict[str, Any] = {"path": None, "state": None}
_QC_GATE_CACHE: dict[str, Any] = {"path": None, "state": None}


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


def _load_branch3_state(model_dir: str | None) -> Any:
    branch3_path = resolve_model_path("branch3", override=model_dir)
    if branch3_path is None:
        raise FileNotFoundError(
            "Branch3 rescue checkpoint (gnn_branch3_rescue.pt) not found.\n"
            + diagnostic_search_report(override=model_dir)
        )
    cache_key = str(branch3_path.resolve())
    if _BRANCH3_CACHE.get("path") == cache_key and _BRANCH3_CACHE.get("state") is not None:
        return _BRANCH3_CACHE["state"]
    from .gnn_branch3_inference import load_branch3  # noqa: PLC0415
    state = load_branch3(branch3_path)
    _BRANCH3_CACHE["path"] = cache_key
    _BRANCH3_CACHE["state"] = state
    return state


def _load_qc_gate(model_dir: str | None) -> Any | None:
    qc_path = resolve_model_path("qc_gate", override=model_dir)
    if qc_path is None:
        return None
    cache_key = str(qc_path.resolve())
    if _QC_GATE_CACHE.get("path") == cache_key and _QC_GATE_CACHE.get("state") is not None:
        return _QC_GATE_CACHE["state"]
    from .qc_input import QCGate  # noqa: PLC0415
    gate = QCGate.load(qc_path)
    _QC_GATE_CACHE["path"] = cache_key
    _QC_GATE_CACHE["state"] = gate
    return gate


def _public_qc_result(raw: Any) -> dict[str, Any] | None:
    """Return the user-facing QC payload without bulky internals."""
    if raw is None:
        return None
    if hasattr(raw, "to_dict"):
        raw = raw.to_dict()
    if not isinstance(raw, dict):
        return {"passed": False, "reasons": [f"qc_error:unexpected_result:{type(raw).__name__}"]}
    out = dict(raw)
    out.pop("feature_vector", None)
    return out


def _qc_failure_reasons(qc_result: dict[str, Any] | None) -> list[str]:
    """Return non-empty QC reasons when a file should not be auto-labeled."""
    if not qc_result:
        return []
    passed = qc_result.get("passed")
    if passed is None or bool(passed):
        return []
    raw_reasons = qc_result.get("reasons") or []
    reasons = [str(reason) for reason in raw_reasons if str(reason).strip()]
    return reasons or ["qc_failed"]


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


def _check_auto_label_eligibility(rows: list[dict[str, Any]]) -> str | None:
    """Fast pre-flight check on parsed SWC rows.

    Auto-label assumes the file describes one cell. The only case
    that produces garbage labels and warrants a hard skip is
    *multi-soma* files (multiple disconnected type-1 components in a
    single SWC) — those need to be split into one cell per file
    first. Soma-less and soma-only files are accepted: the engine's
    proxy-root fallback picks the largest-radius root when there's
    no explicit soma, and a soma-only file simply produces an
    all-soma labeling, which is correct.

    Returns:
        ``None`` when the file is eligible, or a short
        human-readable reason when it is not.
    """
    if not rows:
        return "no valid SWC rows"

    soma_indices = [i for i, r in enumerate(rows) if int(r["type"]) == 1]
    if len(soma_indices) <= 1:
        return None  # 0 somas (proxy-root path) or 1 soma — both fine

    # Multi-soma detection. Two soma nodes are part of the same soma
    # only if they are directly connected (parent <-> child) or
    # transitively connected through soma-only edges. Build that
    # connectivity over soma nodes, count components.
    id_to_idx = {int(r["id"]): i for i, r in enumerate(rows)}
    soma_set = set(soma_indices)
    parent_idx_of = [id_to_idx.get(int(r["parent"])) for r in rows]

    # Adjacency restricted to soma-soma edges.
    soma_adj: dict[int, set[int]] = {i: set() for i in soma_indices}
    for child in soma_indices:
        p = parent_idx_of[child]
        if p in soma_set:
            soma_adj[child].add(p)
            soma_adj[p].add(child)

    seen: set[int] = set()
    components = 0
    for start in soma_indices:
        if start in seen:
            continue
        # BFS over soma-restricted adjacency.
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(n for n in soma_adj[cur] if n not in seen)
        components += 1
    if components > 1:
        return (
            f"multi-soma file ({components} disconnected soma groups); "
            "split with `batch split` before auto-labeling"
        )

    return None


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


def _normalize_cell_type(raw: str | None) -> str | None:
    value = str(raw or "").strip().lower()
    if value in {"", "unknown", "auto", "stage1", "none"}:
        return None
    if value in {"pyramidal", "interneuron"}:
        return value
    raise ValueError("cell_type must be one of: unknown, pyramidal, interneuron")


def _normalize_flag_feature_mode(raw: str | None) -> str:
    value = str(raw or "compact").strip().lower().replace("-", "_")
    if value in {"", "default", "compact", "simple", "auto", "baseline", "complex"}:
        return "compact"
    raise ValueError("flag_feature_mode must be compact/simple")


def _compact_flag_model_for_cell_type(model_dir: str | None, cell_type: str | None) -> Path | None:
    if cell_type == "pyramidal":
        return (
            resolve_model_path("flag_pyramidal", override=model_dir, auto_download=False)
            or resolve_model_path("flag_all", override=model_dir, auto_download=False)
        )
    if cell_type == "interneuron":
        return (
            resolve_model_path("flag_interneuron", override=model_dir, auto_download=False)
            or resolve_model_path("flag_all", override=model_dir, auto_download=False)
        )
    return resolve_model_path("flag_all", override=model_dir, auto_download=False)


def _flag_model_for_cell_type(
    model_dir: str | None,
    cell_type: str | None,
    feature_mode: str | None,
) -> tuple[Path | None, str]:
    _normalize_flag_feature_mode(feature_mode)
    return _compact_flag_model_for_cell_type(model_dir, cell_type), "compact"


def _score_flag_for_pipeline_result(
    *,
    in_path: Path,
    rows: list[dict[str, Any]],
    opts: BatchOptions,
    model_dir: str | None,
    stage1_path: Path,
    stage2_path: Path,
    gnn_state: Any | None,
    pipeline_result: Any,
    cell_type: str | None,
    stage1_conf: float | None,
    use_subtree_stage2: bool,
) -> dict[str, Any] | None:
    if not bool(getattr(opts, "flag_enabled", True)) or pipeline_result is None:
        return None

    requested_mode = _normalize_flag_feature_mode(getattr(opts, "flag_feature_mode", "compact"))
    flag_path, actual_mode = _flag_model_for_cell_type(model_dir, cell_type, requested_mode)
    if flag_path is None:
        return None

    try:
        from .flagging import build_feature_row, score_flag  # noqa: PLC0415
        from .pipeline import run_pipeline_on_nodes  # noqa: PLC0415

        nodes_for_flag = _rows_to_swc_nodes(rows)
        base_result = None
        if cell_type == "pyramidal":
            base_result = run_pipeline_on_nodes(
                nodes_for_flag,
                file_path="",
                stage1_model=stage1_path,
                stage2_model=stage2_path,
                gnn_state=gnn_state,
                branch3_state=None,
                use_subtree_stage2=use_subtree_stage2,
                override_cell_type=_normalize_cell_type(getattr(opts, "cell_type", None)),
            )
        feature_row = build_feature_row(
            file_name=in_path.name,
            nodes=nodes_for_flag,
            labels=list(pipeline_result.node_labels),
            confidences=[float(c) for c in pipeline_result.node_confidences],
            stage1_cell_type=str(cell_type or ""),
            stage1_confidence=float(stage1_conf if stage1_conf is not None else 0.0),
            base_labels=list(base_result.node_labels) if base_result is not None else None,
            base_confidences=(
                [float(c) for c in base_result.node_confidences]
                if base_result is not None else None
            ),
        )
        out = score_flag(
            flag_model_path=flag_path,
            feature_row=feature_row,
            cell_type_for_filter=str(cell_type or ""),
            strictness=float(getattr(opts, "flag_strictness", 0.5)),
        )
        out["requested_feature_mode"] = requested_mode
        out["actual_feature_mode"] = actual_mode
        return out
    except Exception as exc:  # noqa: BLE001
        return {
            "enabled": True,
            "flagged": False,
            "requested_feature_mode": requested_mode,
            "actual_feature_mode": actual_mode,
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def _apply_pipeline_to_rows(
    rows: list[dict[str, Any]],
    *,
    opts: BatchOptions,
    stage1_path: Path,
    stage2_path: Path,
    gnn_state: Any | None,
    branch3_state: Any | None,
    use_subtree_stage2: bool,
) -> tuple[list[int], list[float], int, int, Any | None]:
    """Run the pipeline on parsed SWC rows. Returns
    ``(types, radii, type_changes, radius_changes, pipeline_result)``.

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
            None,
        )

    cell_type_override = _normalize_cell_type(getattr(opts, "cell_type", None))
    result = run_pipeline_on_nodes(
        nodes,
        file_path="",
        stage1_model=stage1_path,
        stage2_model=stage2_path,
        gnn_state=gnn_state,
        branch3_state=branch3_state,
        use_subtree_stage2=use_subtree_stage2,
        override_cell_type=cell_type_override,
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
    return final_types, radii, type_changes, radius_changes, result


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
    branch3_state = _load_branch3_state(model_dir)
    qc_gate = _load_qc_gate(model_dir)

    in_path = Path(file_path)
    headers, rows = _parse_swc(in_path)
    ineligible = _check_auto_label_eligibility(rows)
    if ineligible is not None:
        raise ValueError(f"{in_path.name}: {ineligible}")
    qc_result = None
    if qc_gate is not None:
        try:
            qc_result = _public_qc_result(qc_gate.evaluate(in_path))
        except Exception as exc:  # noqa: BLE001
            qc_result = {"passed": False, "reasons": [f"qc_error:{exc}"], "path": str(in_path)}
    qc_reasons = _qc_failure_reasons(qc_result)
    if qc_reasons:
        raise ValueError(f"{in_path.name}: QC rejected; " + "; ".join(qc_reasons))

    orig_types = [int(r["type"]) for r in rows]
    orig_radii = [float(r["radius"]) for r in rows]
    types, radii, type_changes, radius_changes, pipeline_result = _apply_pipeline_to_rows(
        rows,
        opts=opts,
        stage1_path=stage1_path,
        stage2_path=stage2_path,
        gnn_state=gnn_state,
        branch3_state=branch3_state,
        use_subtree_stage2=use_subtree_stage2,
    )
    cell_type = getattr(getattr(pipeline_result, "stage1", None), "cell_type", None)
    stage1_conf = getattr(getattr(pipeline_result, "stage1", None), "confidence", None)
    cell_type_source = "user" if _normalize_cell_type(getattr(opts, "cell_type", None)) else "stage1"

    flag_result = _score_flag_for_pipeline_result(
        in_path=in_path,
        rows=rows,
        opts=opts,
        model_dir=model_dir,
        stage1_path=stage1_path,
        stage2_path=stage2_path,
        gnn_state=gnn_state,
        pipeline_result=pipeline_result,
        cell_type=cell_type,
        stage1_conf=stage1_conf,
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
            "files_qc_failed": 0,
            "total_nodes": len(rows),
            "total_type_changes": type_changes,
            "total_radius_changes": radius_changes,
            "files_flagged": int(bool(flag_result and flag_result.get("flagged"))),
            "failures": [],
            "per_file": [
                f"{in_path.name}: nodes={len(rows)}, type_changes={type_changes}, "
                f"radius_changes={radius_changes}, cell_type={cell_type or 'unknown'} "
                f"({cell_type_source}), flag={bool(flag_result and flag_result.get('flagged'))}, "
                f"out_types(soma/axon/basal/apic)={out_counts[1]}/{out_counts[2]}/"
                f"{out_counts[3]}/{out_counts[4]}"
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
        cell_type=cell_type,
        cell_type_source=cell_type_source,
        stage1_confidence=float(stage1_conf) if stage1_conf is not None else None,
        qc_result=qc_result,
        flag_result=flag_result,
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
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> BatchResult:
    """Run the auto-typing engine on every ``.swc`` file in ``folder``.

    ``progress_callback`` is invoked once per file *before* processing
    that file: ``progress_callback(index, total, current_filename)``.
    Use it to drive a GUI progress bar without blocking the engine.
    Exceptions raised inside the callback are propagated to the caller.
    """
    ok, reason = is_available(model_dir=model_dir)
    if not ok:
        raise FileNotFoundError(reason)

    stage1_path = resolve_model_path("stage1", override=model_dir)
    stage2_path = resolve_model_path("stage2", override=model_dir)
    gnn_state = _load_gnn_state(model_dir)
    branch3_state = _load_branch3_state(model_dir)
    qc_gate = _load_qc_gate(model_dir)

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
    total_files = len(swc_files)
    files_flagged = 0
    files_qc_failed = 0

    for idx, swc_path in enumerate(swc_files):
        if progress_callback is not None:
            progress_callback(idx, total_files, swc_path.name)
        try:
            headers, rows = _parse_swc(swc_path)
            ineligible = _check_auto_label_eligibility(rows)
            if ineligible is not None:
                failures.append(f"{swc_path.name}: skipped — {ineligible}")
                continue
            qc_result = None
            if qc_gate is not None:
                try:
                    qc_result = _public_qc_result(qc_gate.evaluate(swc_path))
                except Exception as exc:  # noqa: BLE001
                    qc_result = {"passed": False, "reasons": [f"qc_error:{exc}"], "path": str(swc_path)}
            qc_reasons = _qc_failure_reasons(qc_result)
            if qc_reasons:
                files_qc_failed += 1
                per_file.append(
                    f"{swc_path.name}: QC rejected; skipped auto-labeling; "
                    f"reasons={'; '.join(qc_reasons)}"
                )
                continue

            orig_types = [int(r["type"]) for r in rows]
            orig_radii = [float(r["radius"]) for r in rows]
            types, radii, type_changes, radius_changes, pipeline_result = _apply_pipeline_to_rows(
                rows,
                opts=opts,
                stage1_path=stage1_path,
                stage2_path=stage2_path,
                gnn_state=gnn_state,
                branch3_state=branch3_state,
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
            cell_type = getattr(getattr(pipeline_result, "stage1", None), "cell_type", None)
            stage1_conf = getattr(getattr(pipeline_result, "stage1", None), "confidence", None)
            cell_type_source = "user" if _normalize_cell_type(getattr(opts, "cell_type", None)) else "stage1"
            flag_result = _score_flag_for_pipeline_result(
                in_path=swc_path,
                rows=rows,
                opts=opts,
                model_dir=model_dir,
                stage1_path=stage1_path,
                stage2_path=stage2_path,
                gnn_state=gnn_state,
                pipeline_result=pipeline_result,
                cell_type=cell_type,
                stage1_conf=stage1_conf,
                use_subtree_stage2=use_subtree_stage2,
            )
            if bool(flag_result and flag_result.get("flagged")):
                files_flagged += 1
            out_counts = {
                1: sum(1 for t in types if int(t) == 1),
                2: sum(1 for t in types if int(t) == 2),
                3: sum(1 for t in types if int(t) == 3),
                4: sum(1 for t in types if int(t) == 4),
            }
            per_file.append(
                f"{swc_path.name}: nodes={len(rows)}, type_changes={type_changes}, "
                f"radius_changes={radius_changes}, cell_type={cell_type or 'unknown'} "
                f"({cell_type_source}), qc_pass={None if qc_result is None else qc_result.get('passed')}, "
                f"flag={bool(flag_result and flag_result.get('flagged'))}, "
                f"out_types(soma/axon/basal/apic)={out_counts[1]}/{out_counts[2]}/"
                f"{out_counts[3]}/{out_counts[4]}"
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
        "files_qc_failed": files_qc_failed,
        "total_nodes": total_nodes,
        "total_type_changes": total_type_changes,
        "total_radius_changes": total_radius_changes,
        "files_flagged": files_flagged,
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
        files_qc_failed=files_qc_failed,
        total_nodes=total_nodes,
        total_type_changes=total_type_changes,
        total_radius_changes=total_radius_changes,
        files_flagged=files_flagged,
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
