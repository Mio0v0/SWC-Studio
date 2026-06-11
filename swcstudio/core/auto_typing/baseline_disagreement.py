"""Optional baseline-disagreement features for the flag scorer.

These features compare the deployed v12 labels against classical baseline
predictors (NeuroM-style RF, L-Measure-style RF, Sholl RF, Sholl MLP). The
predictor artifacts are intentionally optional because the NeuroM RF artifact
is very large. Compact flag scoring remains available without them.
"""
from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import joblib
import numpy as np

from swcstudio.core.model_paths import search_dirs

from .cell_type_detector import CELL_TYPE_LABEL_SETS
from .features import SWCNode

BASELINE_ENV_VAR = "SWCSTUDIO_BASELINE_MODEL_DIR"
BASELINE_METHODS = ("neurom_rf", "lmeasure_rf", "sholl_rf", "sholl_mlp")
BASELINE_MODES = ("s1", "pyr")
SHOLL_RADII_UM = (10.0, 25.0, 50.0, 100.0, 200.0, 400.0, 800.0)

_MODEL_CACHE: dict[str, object] = {}


@dataclass
class _Topo:
    nodes: list[SWCNode]
    id_to_idx: dict[int, int]
    parent_idx: list[int | None]
    children: list[list[int]]
    roots: list[int]


def _dedupe(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def baseline_search_dirs(override: str | os.PathLike | None = None) -> list[Path]:
    """Return directories searched for optional baseline predictor pickles."""
    out: list[Path] = []
    env_dir = os.environ.get(BASELINE_ENV_VAR)
    if env_dir:
        out.append(Path(env_dir))
    for d in search_dirs(override):
        out.extend([d / "baselines", d])

    # Developer convenience: SWC-Studio and swc-autolabel-ml often live as
    # siblings on the Desktop during paper work. This keeps local experiments
    # usable without copying the 8 GB NeuroM RF artifact into SWC-Studio.
    here = Path(__file__).resolve()
    for parent in here.parents:
        out.append(parent / "swc-autolabel-ml" / "paper" / "models" / "baselines")
        out.append(parent.parent / "swc-autolabel-ml" / "paper" / "models" / "baselines")
    return _dedupe(out)


def resolve_baseline_model_path(
    method: str,
    *,
    override: str | os.PathLike | None = None,
) -> Path | None:
    fname = f"{method}.pkl"
    for d in baseline_search_dirs(override):
        candidate = d / fname
        if candidate.is_file():
            return candidate
    return None


def baseline_model_status(
    *,
    override: str | os.PathLike | None = None,
) -> dict[str, object]:
    paths = {
        method: resolve_baseline_model_path(method, override=override)
        for method in BASELINE_METHODS
    }
    return {
        "available": all(p is not None for p in paths.values()),
        "paths": {k: str(v) if v is not None else None for k, v in paths.items()},
        "search_dirs": [str(p) for p in baseline_search_dirs(override)],
    }


def _load_model(method: str, override: str | os.PathLike | None = None) -> object:
    path = resolve_baseline_model_path(method, override=override)
    if path is None:
        raise FileNotFoundError(
            f"Missing baseline predictor {method}.pkl. Set {BASELINE_ENV_VAR} "
            "or place baseline pickles in <model-dir>/baselines/."
        )
    key = str(path.resolve())
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = joblib.load(path)
    return _MODEL_CACHE[key]


def _build_topo(nodes: list[SWCNode]) -> _Topo:
    id_to_idx = {int(n.id): i for i, n in enumerate(nodes)}
    parent_idx: list[int | None] = [None] * len(nodes)
    children: list[list[int]] = [[] for _ in nodes]
    roots: list[int] = []
    for i, nd in enumerate(nodes):
        pidx = id_to_idx.get(int(nd.parent))
        parent_idx[i] = pidx
        if pidx is not None:
            children[pidx].append(i)
        if int(nd.parent) == -1 or pidx is None:
            roots.append(i)
    return _Topo(nodes, id_to_idx, parent_idx, children, roots)


def _select_proxy_root(topo: _Topo) -> int:
    if not topo.nodes:
        return 0
    candidate_roots = topo.roots or [0]
    return max(
        candidate_roots,
        key=lambda idx: (float(topo.nodes[idx].radius), len(topo.children[idx]), -idx),
    )


def _subtree_indices(topo: _Topo, root_idx: int) -> list[int]:
    out: list[int] = []
    stack = [root_idx]
    seen: set[int] = set()
    while stack:
        idx = stack.pop()
        if idx in seen:
            continue
        seen.add(idx)
        out.append(idx)
        stack.extend(topo.children[idx])
    return out


def _euclid(a: SWCNode, b: SWCNode) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _branch_segments(topo: _Topo, proxy: int) -> list[list[int]]:
    segments: list[list[int]] = []
    visited: set[int] = {proxy}
    queue: list[int] = list(topo.children[proxy])
    while queue:
        start = queue.pop(0)
        if start in visited:
            continue
        seg: list[int] = []
        cur: int | None = start
        while cur is not None and cur not in visited:
            visited.add(cur)
            seg.append(cur)
            kids = topo.children[cur]
            if len(kids) != 1:
                queue.extend(kids)
                break
            cur = kids[0]
        if seg:
            segments.append(seg)
    return segments


def _sanitize_features(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=1e30, neginf=-1e30)
    return np.clip(X, -1e30, 1e30).astype(np.float32)


def _valid_labels(cell_type: str) -> set[int]:
    return set(CELL_TYPE_LABEL_SETS.get(cell_type, {1, 2, 3}))


def _fallback_label(valid: set[int]) -> int:
    if 3 in valid:
        return 3
    return next(iter(valid - {1}), 3)


def _branch_neurom_features(topo: _Topo, proxy: int, seg: list[int], cell_type: str) -> np.ndarray:
    nodes = topo.nodes
    soma = nodes[proxy]
    head = nodes[seg[0]]
    tail = nodes[seg[-1]]
    path_len = 0.0
    for a, b in zip(seg[:-1], seg[1:]):
        path_len += _euclid(nodes[a], nodes[b])
    parent_idx = topo.parent_idx[seg[0]]
    if parent_idx is not None:
        path_len += _euclid(nodes[parent_idx], nodes[seg[0]])

    radii = np.asarray([nodes[i].radius for i in seg], dtype=np.float64)
    head_r = float(nodes[seg[0]].radius)
    tail_r = float(nodes[seg[-1]].radius)
    sub = _subtree_indices(topo, seg[-1])
    kids = topo.children[seg[-1]]
    if len(kids) >= 2:
        sizes = sorted((len(_subtree_indices(topo, k)) for k in kids), reverse=True)
        partition_asym = abs(sizes[0] - sizes[1]) / max(1, sizes[0] + sizes[1])
    else:
        partition_asym = 0.0
    sub_path = 0.0
    for i in sub:
        pi = topo.parent_idx[i]
        if pi is not None:
            sub_path += _euclid(nodes[pi], nodes[i])
    return np.array(
        [
            path_len,
            _euclid(head, soma),
            _euclid(tail, soma),
            max(_euclid(head, soma), _euclid(tail, soma)),
            tail.z - soma.z,
            float(radii.mean()),
            float(radii.min()),
            float(radii.max()),
            head_r,
            tail_r,
            (head_r - tail_r) / max(1e-6, head_r),
            float(len(sub)),
            float(sum(1 for i in sub if len(topo.children[i]) >= 2)),
            sub_path,
            float(partition_asym),
            1.0 if cell_type == "pyramidal" else 0.0,
            1.0 if cell_type == "interneuron" else 0.0,
        ],
        dtype=np.float64,
    )


def _sholl_subtree_features(topo: _Topo, proxy: int, sub_root: int, cell_type: str) -> np.ndarray:
    nodes = topo.nodes
    soma = nodes[proxy]
    sub = _subtree_indices(topo, sub_root)
    if not sub:
        return np.zeros(len(SHOLL_RADII_UM) + 14, dtype=np.float64)

    distances = np.asarray([_euclid(nodes[i], soma) for i in sub], dtype=np.float64)
    intersections: list[int] = []
    for radius in SHOLL_RADII_UM:
        n_cross = 0
        for i in sub:
            pi = topo.parent_idx[i]
            if pi is None:
                continue
            d_parent = _euclid(nodes[pi], soma)
            d_child = _euclid(nodes[i], soma)
            if (d_parent < radius <= d_child) or (d_child < radius <= d_parent):
                n_cross += 1
        intersections.append(n_cross)

    total_len = 0.0
    for i in sub:
        pi = topo.parent_idx[i]
        if pi is not None:
            total_len += _euclid(nodes[pi], nodes[i])

    dist_along: dict[int, float] = {sub_root: 0.0}
    stack = [sub_root]
    seen: set[int] = set()
    while stack:
        idx = stack.pop()
        if idx in seen:
            continue
        seen.add(idx)
        d_here = dist_along.get(idx, 0.0)
        for child in topo.children[idx]:
            dist_along[child] = d_here + _euclid(nodes[idx], nodes[child])
            stack.append(child)

    coords = np.asarray([(nodes[i].x, nodes[i].y, nodes[i].z) for i in sub], dtype=np.float64)
    if coords.shape[0] >= 2:
        centered = coords - coords.mean(axis=0)
        try:
            _, _, vt = np.linalg.svd(centered, full_matrices=False)
            axis = vt[0]
        except np.linalg.LinAlgError:
            axis = np.array([0.0, 0.0, 1.0])
    else:
        axis = np.array([0.0, 0.0, 1.0])
    pa_x, pa_y, pa_z = axis.tolist()

    return np.array(
        [
            *intersections,
            float(max(intersections)) if intersections else 0.0,
            float(SHOLL_RADII_UM[int(np.argmax(intersections))]) if intersections else 10.0,
            float(len(sub)),
            float(sum(1 for i in sub if len(topo.children[i]) >= 2)),
            float(distances.max()) if distances.size else 0.0,
            float(np.mean([nodes[i].radius for i in sub])),
            total_len,
            float(max(dist_along.values())) if dist_along else 0.0,
            abs(float(pa_x)),
            abs(float(pa_y)),
            abs(float(pa_z)),
            float(max(nodes[i].z - soma.z for i in sub)),
            float(min(nodes[i].z - soma.z for i in sub)),
            1.0 if cell_type == "pyramidal" else 0.0,
        ],
        dtype=np.float64,
    )


def _lmeasure_subtree_features(topo: _Topo, _proxy: int, sub_root: int, cell_type: str) -> np.ndarray:
    nodes = topo.nodes
    sub = _subtree_indices(topo, sub_root)
    if not sub:
        return np.zeros(23, dtype=np.float64)

    n_bifs = sum(1 for i in sub if len(topo.children[i]) >= 2)
    n_tips = sum(1 for i in sub if len(topo.children[i]) == 0)
    total_length = 0.0
    total_surface = 0.0
    total_volume = 0.0
    for i in sub:
        pi = topo.parent_idx[i]
        if pi is None:
            continue
        seg_len = _euclid(nodes[pi], nodes[i])
        seg_radius = 0.5 * (nodes[pi].radius + nodes[i].radius)
        total_length += seg_len
        total_surface += 2.0 * math.pi * seg_radius * seg_len
        total_volume += math.pi * (seg_radius ** 2) * seg_len

    radii = np.asarray([nodes[i].radius for i in sub], dtype=np.float64)
    coords = np.asarray([(nodes[i].x, nodes[i].y, nodes[i].z) for i in sub], dtype=np.float64)
    span = coords.max(axis=0) - coords.min(axis=0)
    euc_max = float(np.max(np.linalg.norm(coords - coords[0], axis=1))) if coords.shape[0] >= 2 else 0.0

    dist_along: dict[int, float] = {sub_root: 0.0}
    stack = [sub_root]
    seen: set[int] = set()
    while stack:
        idx = stack.pop()
        if idx in seen:
            continue
        seen.add(idx)
        d_here = dist_along.get(idx, 0.0)
        for child in topo.children[idx]:
            dist_along[child] = d_here + _euclid(nodes[idx], nodes[child])
            stack.append(child)

    order_at: dict[int, int] = {sub_root: 0}
    stack2 = [sub_root]
    seen2: set[int] = set()
    while stack2:
        idx = stack2.pop()
        if idx in seen2:
            continue
        seen2.add(idx)
        order = order_at.get(idx, 0)
        for child in topo.children[idx]:
            order_at[child] = order + (1 if len(topo.children[idx]) >= 2 else 0)
            stack2.append(child)

    pa_vals: list[float] = []
    for i in sub:
        kids = topo.children[i]
        if len(kids) < 2:
            continue
        sizes = sorted((len(_subtree_indices(topo, k)) for k in kids), reverse=True)
        pa_vals.append(abs(sizes[0] - sizes[1]) / max(1, sizes[0] + sizes[1]))

    contractions: list[float] = []
    for i in sub:
        if len(topo.children[i]) != 1:
            continue
        path = 0.0
        cur = i
        while len(topo.children[cur]) == 1:
            nxt = topo.children[cur][0]
            path += _euclid(nodes[cur], nodes[nxt])
            cur = nxt
        if path > 0:
            contractions.append(_euclid(nodes[i], nodes[cur]) / path)

    tapers: list[float] = []
    for i in sub:
        pi = topo.parent_idx[i]
        if pi is None or len(topo.children[i]) > 1:
            continue
        rp = float(nodes[pi].radius)
        if rp > 1e-6:
            tapers.append((rp - float(nodes[i].radius)) / rp)

    parent_idx = topo.parent_idx[sub_root]
    parent_rad = float(nodes[parent_idx].radius) if parent_idx is not None else float(nodes[sub_root].radius)
    return np.array(
        [
            float(len(sub)),
            float(n_bifs),
            float(n_tips),
            float(max(1, n_bifs * 2 + 1)),
            total_length,
            total_surface,
            total_volume,
            float(2.0 * radii.mean()),
            float(2.0 * radii.min()),
            float(2.0 * radii.max()),
            float(span[0]),
            float(span[1]),
            float(span[2]),
            euc_max,
            float(max(dist_along.values())) if dist_along else 0.0,
            float(max(order_at.values())) if order_at else 0.0,
            float(np.mean(pa_vals)) if pa_vals else 0.0,
            float(np.max(pa_vals)) if pa_vals else 0.0,
            float(np.mean(contractions)) if contractions else 1.0,
            float(np.mean(tapers)) if tapers else 0.0,
            parent_rad,
            float(nodes[sub_root].radius),
            1.0 if cell_type == "pyramidal" else 0.0,
        ],
        dtype=np.float64,
    )


def _predict_neurom(clf: object, nodes: list[SWCNode], cell_type: str) -> list[int]:
    if not nodes:
        return []
    topo = _build_topo(nodes)
    proxy = _select_proxy_root(topo)
    out = [int(n.type) for n in nodes]
    for i, nd in enumerate(nodes):
        if int(nd.type) == 1:
            out[i] = 1
    out[proxy] = 1
    valid = _valid_labels(cell_type)
    segs = [seg for seg in _branch_segments(topo, proxy) if seg]
    if not segs:
        return out
    X = _sanitize_features(np.vstack([_branch_neurom_features(topo, proxy, seg, cell_type) for seg in segs]))
    preds = clf.predict(X).astype(int).tolist()
    fallback = _fallback_label(valid)
    for seg, pred in zip(segs, preds):
        if pred not in valid:
            pred = fallback
        for i in seg:
            if int(topo.nodes[i].type) != 1:
                out[i] = int(pred)
    return out


def _predict_subtree_clf(
    clf: object,
    nodes: list[SWCNode],
    cell_type: str,
    feature_fn: Callable[[_Topo, int, int, str], np.ndarray],
) -> list[int]:
    if not nodes:
        return []
    topo = _build_topo(nodes)
    proxy = _select_proxy_root(topo)
    out = [int(n.type) for n in nodes]
    for i, nd in enumerate(nodes):
        if int(nd.type) == 1:
            out[i] = 1
    out[proxy] = 1
    sub_roots = list(topo.children[proxy])
    if not sub_roots:
        return out
    valid = _valid_labels(cell_type)
    X = _sanitize_features(np.vstack([feature_fn(topo, proxy, sub_root, cell_type) for sub_root in sub_roots]))
    preds = clf.predict(X).astype(int).tolist()
    fallback = _fallback_label(valid)
    for sub_root, pred in zip(sub_roots, preds):
        if pred not in valid:
            pred = fallback
        for i in _subtree_indices(topo, sub_root):
            if int(topo.nodes[i].type) != 1:
                out[i] = int(pred)
    return out


def _predict_baseline(
    method: str,
    nodes: list[SWCNode],
    cell_type: str,
    *,
    override: str | os.PathLike | None = None,
) -> list[int]:
    clf = _load_model(method, override=override)
    if method == "neurom_rf":
        return _predict_neurom(clf, nodes, cell_type)
    if method == "lmeasure_rf":
        return _predict_subtree_clf(clf, nodes, cell_type, _lmeasure_subtree_features)
    if method in {"sholl_rf", "sholl_mlp"}:
        return _predict_subtree_clf(clf, nodes, cell_type, _sholl_subtree_features)
    raise KeyError(method)


def _frac_counts(labels: list[int], n_nodes: int) -> dict[str, float]:
    denom = max(1.0, float(n_nodes - 1))
    counts = Counter(int(x) for x in labels)
    return {
        "axon": counts.get(2, 0) / denom,
        "basal": counts.get(3, 0) / denom,
        "apical": counts.get(4, 0) / denom,
    }


def _mode_cell_type(stage1_pred: str, mode: str) -> str:
    if mode == "pyr":
        return "pyramidal"
    return stage1_pred if stage1_pred in {"pyramidal", "interneuron"} else "pyramidal"


def _empty_agg() -> dict[str, dict[str, list[float]]]:
    return {
        mode: {
            "l1": [],
            "apical_delta": [],
            "axon_delta": [],
            "apical_present": [],
            "axon_present": [],
            "class_count": [],
        }
        for mode in BASELINE_MODES
    }


def build_baseline_disagreement_features(
    *,
    nodes: list[SWCNode],
    labels: list[int],
    stage1_cell_type: str,
    model_dir: str | os.PathLike | None = None,
) -> dict[str, float]:
    """Build the ``baseline_oof_*`` columns expected by the heavy flagger."""
    n_nodes = len(nodes)
    v12 = _frac_counts(labels, n_nodes)
    out: dict[str, float] = {}
    agg = _empty_agg()

    for method in BASELINE_METHODS:
        for mode in BASELINE_MODES:
            cell_type = _mode_cell_type(stage1_cell_type, mode)
            pred = _predict_baseline(method, nodes, cell_type, override=model_dir)
            if len(pred) != len(nodes):
                raise RuntimeError(f"{method}:{mode} returned {len(pred)} labels for {len(nodes)} nodes")
            frac = _frac_counts(pred, n_nodes)
            prefix = f"baseline_oof_{method}_{mode}"
            class_count = float(sum(1 for cls in ("axon", "basal", "apical") if frac[cls] > 0.0))
            l1 = float(sum(abs(frac[cls] - v12[cls]) for cls in ("axon", "basal", "apical")))
            ap_delta = float(abs(frac["apical"] - v12["apical"]))
            ax_delta = float(abs(frac["axon"] - v12["axon"]))

            out[f"{prefix}_axon_frac"] = frac["axon"]
            out[f"{prefix}_basal_frac"] = frac["basal"]
            out[f"{prefix}_apical_frac"] = frac["apical"]
            out[f"{prefix}_class_count"] = class_count
            out[f"{prefix}_v12_l1_frac_delta"] = l1
            out[f"{prefix}_v12_apical_frac_delta"] = ap_delta
            out[f"{prefix}_v12_axon_frac_delta"] = ax_delta
            out[f"{prefix}_v12_apical_zero_mismatch"] = float((frac["apical"] == 0.0) != (v12["apical"] == 0.0))
            out[f"{prefix}_v12_axon_zero_mismatch"] = float((frac["axon"] == 0.0) != (v12["axon"] == 0.0))

            agg[mode]["l1"].append(l1)
            agg[mode]["apical_delta"].append(ap_delta)
            agg[mode]["axon_delta"].append(ax_delta)
            agg[mode]["apical_present"].append(float(frac["apical"] > 0.0))
            agg[mode]["axon_present"].append(float(frac["axon"] > 0.0))
            agg[mode]["class_count"].append(class_count)

    for mode, parts in agg.items():
        for key, values in parts.items():
            arr = np.asarray(values, dtype=float)
            out[f"baseline_oof_{mode}_{key}_mean"] = float(arr.mean()) if arr.size else 0.0
            out[f"baseline_oof_{mode}_{key}_max"] = float(arr.max()) if arr.size else 0.0
            out[f"baseline_oof_{mode}_{key}_std"] = float(arr.std()) if arr.size else 0.0
        ap = np.asarray(parts["apical_present"], dtype=float)
        ax = np.asarray(parts["axon_present"], dtype=float)
        out[f"baseline_oof_{mode}_apical_present_vote_frac"] = float(ap.mean()) if ap.size else 0.0
        out[f"baseline_oof_{mode}_axon_present_vote_frac"] = float(ax.mean()) if ax.size else 0.0
        out[f"baseline_oof_{mode}_apical_presence_disagreement"] = float(ap.max() - ap.min()) if ap.size else 0.0
        out[f"baseline_oof_{mode}_axon_presence_disagreement"] = float(ax.max() - ax.min()) if ax.size else 0.0

    return out


__all__ = [
    "BASELINE_ENV_VAR",
    "BASELINE_METHODS",
    "baseline_model_status",
    "baseline_search_dirs",
    "build_baseline_disagreement_features",
    "resolve_baseline_model_path",
]
