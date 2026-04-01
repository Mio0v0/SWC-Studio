"""Auto-typing / rule-batch implementation moved to core.

This module contains the rule-based auto-typing logic formerly located in
`swctools.gui.rule_batch_processor`. It is kept in `swctools.core` so both GUI
and CLI can use the same implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import zipfile
import math
import numpy as np
from swctools.core.config import load_feature_config, merge_config, save_feature_config
from swctools.core.reporting import (
    auto_typing_log_path_for_file,
    format_auto_typing_report_text,
    write_text_report,
)


TOOL = "batch_processing"
FEATURE = "auto_typing"
_DEFAULT_CFG: dict[str, Any] | None = None


def _default_rules_config() -> dict[str, Any]:
    return {
        "class_labels": {"1": "soma", "2": "axon", "3": "basal", "4": "apical"},
        "branch_score_weights": {
            "axon": {
                "path": 0.14,
                "radial": 0.12,
                "root_path": 0.18,
                "root_radial": 0.12,
                "radius": 0.12,
                "branch": 0.04,
                "persistence": 0.16,
                "taper": 0.08,
                "symmetry": 0.04,
                "up": 0.02,
                "prior": 0.04,
            },
            "apical": {
                "z": 0.20,
                "up": 0.20,
                "path": 0.12,
                "root_path": 0.16,
                "radius": 0.12,
                "branch": 0.10,
                "taper": 0.06,
                "symmetry": 0.04,
                "prior": 0.14,
            },
            "basal": {
                "z": 0.12,
                "up": 0.12,
                "branch": 0.16,
                "radius": 0.14,
                "path": 0.08,
                "root_path": 0.20,
                "root_radial": 0.12,
                "persistence": 0.08,
                "taper": 0.10,
                "symmetry": 0.08,
                "prior": 0.08,
            },
        },
        "feature_windows": {
            "terminal_window_nodes": 3,
        },
        "segmenting": {"max_chunk_path": 180.0},
        "ml_blend": 0.28,
        "ml_base_weight": 0.72,
        "seed_prior_threshold": 0.55,
        "assign_missing": {"min_score": 0.58, "min_gain": -0.06},
        "smoothing": {"maj_fraction": 0.67, "flip_margin": 0.10, "continuity_margin": 0.02},
        "refinement": {
            "iterations": 2,
            "parent_weight": 0.14,
            "child_weight": 0.18,
            "island_max_path": 36.0,
            "island_relative_max": 0.35,
            "island_flip_margin": 0.14,
        },
        "soma_child_prior": {
            "branch_weight": 0.38,
            "branch_boost": 0.16,
            "propagation_weight": 0.30,
            "score_weights": {
                "axon": {
                    "path": 0.20,
                    "radial": 0.18,
                    "size": 0.18,
                    "radius": 0.10,
                    "branch": 0.08,
                    "persistence": 0.14,
                    "taper": 0.06,
                    "symmetry": 0.04,
                    "prior": 0.12,
                },
                "apical": {
                    "z": 0.22,
                    "up": 0.22,
                    "path": 0.14,
                    "size": 0.12,
                    "radius": 0.12,
                    "branch": 0.10,
                    "taper": 0.06,
                    "symmetry": 0.04,
                    "prior": 0.16,
                },
                "basal": {
                    "path": 0.20,
                    "radial": 0.18,
                    "radius": 0.14,
                    "branch": 0.12,
                    "z": 0.10,
                    "up": 0.10,
                    "persistence": 0.06,
                    "taper": 0.08,
                    "symmetry": 0.10,
                    "prior": 0.16,
                },
            },
        },
        "propagation_weights": {
            "self": 0.35,
            "parent": 0.35,
            "children": 0.20,
            "branch_prior": 0.30,
            "iterations": 4,
        },
        "radius": {"copy_parent_if_zero": True},
        "constraints": {
            "inherit_primary_subtree": True,
            "single_axon": True,
            "single_apical": True,
            "axon_primary_min_score": 0.42,
            "apical_primary_min_score": 0.42,
            "far_basal_distance_um": 500.0,
            "far_basal_penalty": 0.22,
            "thin_axon_max_base_radius_um": 1.0,
            "thin_axon_bonus": 0.10,
        },
        "notes": (
            "This JSON controls the auto-labeling behavior "
            "(weights, thresholds, and options), including hard primary-subtree inheritance, "
            "single-axon/apical constraints, path-persistence / terminal-taper features, "
            "and topology-aware refinement. Edit carefully."
        ),
    }


def _load_cfg() -> dict[str, Any]:
    global _DEFAULT_CFG
    if _DEFAULT_CFG is not None:
        return dict(_DEFAULT_CFG)

    feature_cfg = load_feature_config(TOOL, FEATURE, default={})
    rules_cfg = feature_cfg.get("rules", feature_cfg if "feature" not in feature_cfg else {})
    _DEFAULT_CFG = merge_config(_default_rules_config(), rules_cfg)
    return dict(_DEFAULT_CFG)


def get_config() -> dict:
    """Return the active configuration dict (loaded from JSON if available)."""
    return _load_cfg()


def save_config(cfg: dict) -> None:
    """Save rule settings into the batch auto-typing feature config."""
    global _DEFAULT_CFG
    feature_cfg = load_feature_config(TOOL, FEATURE, default={})
    updated_cfg = merge_config(feature_cfg, {"rules": cfg})
    save_feature_config(TOOL, FEATURE, updated_cfg)
    _DEFAULT_CFG = merge_config(_default_rules_config(), cfg)


@dataclass
class RuleBatchOptions:
    soma: bool = False
    axon: bool = False
    apic: bool = False
    basal: bool = False
    rad: bool = False
    zip_output: bool = False


@dataclass
class RuleBatchResult:
    folder: str
    out_dir: str
    zip_path: str | None
    files_total: int
    files_processed: int
    files_failed: int
    total_nodes: int
    total_type_changes: int
    total_radius_changes: int
    failures: list[str]
    per_file: list[str]
    log_path: str | None


@dataclass
class RuleFileResult:
    input_file: str
    output_file: str | None
    nodes_total: int
    type_changes: int
    radius_changes: int
    out_type_counts: dict[int, int]
    failures: list[str]
    change_details: list[str]
    log_path: str | None
    headers: list[str]
    rows: list[dict[str, Any]]
    types: list[int]
    radii: list[float]


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


def _build_topology(rows: list[dict[str, Any]]) -> tuple[list[int | None], list[list[int]], list[int]]:
    n = len(rows)
    id_to_idx = {int(row["id"]): i for i, row in enumerate(rows)}
    parent_idx: list[int | None] = [None] * n
    children: list[list[int]] = [[] for _ in range(n)]

    for i, row in enumerate(rows):
        pidx = id_to_idx.get(int(row["parent"]))
        parent_idx[i] = pidx
        if pidx is not None:
            children[pidx].append(i)

    roots = [i for i, row in enumerate(rows) if int(row["parent"]) == -1 or parent_idx[i] is None]
    roots.sort(key=lambda idx: int(rows[idx]["id"]))

    order: list[int] = []
    seen = set()
    queue = list(roots)
    while queue:
        idx = queue.pop(0)
        if idx in seen:
            continue
        seen.add(idx)
        order.append(idx)
        kids = sorted(children[idx], key=lambda k: int(rows[k]["id"]))
        queue.extend(kids)

    for i in sorted(range(n), key=lambda idx: int(rows[idx]["id"])):
        if i not in seen:
            order.append(i)

    return parent_idx, children, order


def _normalize_map(vals: dict[int, float]) -> dict[int, float]:
    if not vals:
        return {}
    lo = min(vals.values())
    hi = max(vals.values())
    if hi <= lo:
        return {k: 0.5 for k in vals}
    scale = hi - lo
    return {k: (v - lo) / scale for k, v in vals.items()}


def _iter_branch_segment(
    start: int,
    rows: list[dict[str, Any]],
    children: list[list[int]],
    parent_idx: list[int | None],
    max_chunk_path: float,
) -> list[int]:
    """Return a linear segment until a leaf, bifurcation, or chunk limit is reached."""
    out: list[int] = []
    cur = start
    seen = set()
    chunk_path = 0.0
    while cur not in seen:
        seen.add(cur)
        out.append(cur)
        kids = children[cur]
        if len(kids) != 1:
            break
        nxt = kids[0]
        pidx = parent_idx[nxt]
        if pidx is None:
            break
        dx = float(rows[nxt]["x"]) - float(rows[pidx]["x"])
        dy = float(rows[nxt]["y"]) - float(rows[pidx]["y"])
        dz = float(rows[nxt]["z"]) - float(rows[pidx]["z"])
        seg_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if out and chunk_path + seg_len > max_chunk_path:
            break
        chunk_path += seg_len
        cur = nxt
    return out


def _branch_partition(
    rows: list[dict[str, Any]],
    parent_idx: list[int | None],
    children: list[list[int]],
    types: list[int],
) -> tuple[dict[int, list[int]], dict[int, int], list[int]]:
    """Partition morphology into branch segments anchored at roots/bifurcations."""
    n = len(rows)
    roots = [i for i, p in enumerate(parent_idx) if p is None]
    soma_roots = [i for i in roots if int(types[i]) == 1]
    anchors = soma_roots if soma_roots else roots
    max_chunk_path = float(_load_cfg().get("segmenting", {}).get("max_chunk_path", 180.0))

    node_branch = [-1] * n
    branch_nodes: dict[int, list[int]] = {}
    branch_anchor: dict[int, int] = {}
    bid = 0
    seen_starts: set[int] = set()
    pending: list[tuple[int, int]] = []

    for anchor in anchors:
        kids = sorted(children[anchor], key=lambda i: int(rows[i]["id"]))
        if not kids and int(types[anchor]) != 1:
            pending.append((parent_idx[anchor] if parent_idx[anchor] is not None else anchor, anchor))
            continue
        for child in kids:
            pending.append((anchor, child))

    while pending:
        anchor, start = pending.pop(0)
        if start in seen_starts:
            continue
        seen_starts.add(start)

        nodes = _iter_branch_segment(start, rows, children, parent_idx, max_chunk_path)
        if not nodes:
            continue

        branch_nodes[bid] = nodes
        branch_anchor[bid] = anchor
        for x in nodes:
            if node_branch[x] == -1:
                node_branch[x] = bid

        tail = nodes[-1]
        kids = sorted(children[tail], key=lambda i: int(rows[i]["id"]))
        if len(kids) == 1:
            pending.append((tail, kids[0]))
        else:
            for child in kids:
                pending.append((tail, child))
        bid += 1

    for i in range(n):
        if node_branch[i] != -1 or int(types[i]) == 1:
            continue
        anchor = parent_idx[i] if parent_idx[i] is not None else i
        nodes = _iter_branch_segment(i, rows, children, parent_idx, max_chunk_path)
        branch_nodes[bid] = nodes
        branch_anchor[bid] = anchor
        for x in nodes:
            if node_branch[x] == -1:
                node_branch[x] = bid
        tail = nodes[-1]
        kids = sorted(children[tail], key=lambda j: int(rows[j]["id"]))
        if len(kids) == 1:
            pending.append((tail, kids[0]))
        else:
            for child in kids:
                pending.append((tail, child))
        bid += 1

    return branch_nodes, branch_anchor, node_branch


def _compute_root_metrics(
    rows: list[dict[str, Any]],
    parent_idx: list[int | None],
    children: list[list[int]],
    order: list[int],
) -> tuple[list[float], list[float], list[int], int | None]:
    n = len(rows)
    roots = [i for i, p in enumerate(parent_idx) if p is None]
    root_idx = roots[0] if roots else None
    path_from_root = [0.0] * n
    branch_order = [0] * n

    for i in order:
        pidx = parent_idx[i]
        if pidx is None:
            continue
        dx = float(rows[i]["x"]) - float(rows[pidx]["x"])
        dy = float(rows[i]["y"]) - float(rows[pidx]["y"])
        dz = float(rows[i]["z"]) - float(rows[pidx]["z"])
        path_from_root[i] = path_from_root[pidx] + math.sqrt(dx * dx + dy * dy + dz * dz)
        branch_order[i] = branch_order[pidx] + (1 if len(children[pidx]) > 1 else 0)

    if root_idx is None:
        return path_from_root, [0.0] * n, branch_order, None

    rx = float(rows[root_idx]["x"])
    ry = float(rows[root_idx]["y"])
    rz = float(rows[root_idx]["z"])
    radial_from_root = [
        math.sqrt(
            (float(row["x"]) - rx) ** 2
            + (float(row["y"]) - ry) ** 2
            + (float(row["z"]) - rz) ** 2
        )
        for row in rows
    ]
    return path_from_root, radial_from_root, branch_order, root_idx


def _window_mean(vals: list[float], count: int) -> float:
    if not vals:
        return 0.0
    take = max(1, min(int(count), len(vals)))
    return float(sum(vals[:take]) / take)


def _terminal_taper_ratio(nodes: list[int], rows: list[dict[str, Any]], *, window_nodes: int) -> float:
    if not nodes:
        return 1.0
    radii = [max(0.0, float(rows[idx]["radius"])) for idx in nodes]
    count = max(1, min(int(window_nodes), len(radii)))
    base = _window_mean(radii, count)
    tail = _window_mean(list(reversed(radii)), count)
    if base <= 1e-9:
        return 1.0
    return max(0.0, float(tail / base))


def _terminal_up_alignment(nodes: list[int], rows: list[dict[str, Any]]) -> float:
    if len(nodes) <= 1:
        return 0.5
    start = rows[nodes[0]]
    end = rows[nodes[-1]]
    dx = float(end["x"]) - float(start["x"])
    dy = float(end["y"]) - float(start["y"])
    dz = float(end["z"]) - float(start["z"])
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist <= 1e-9:
        return 0.5
    return max(0.0, min(1.0, (dz / dist + 1.0) * 0.5))


def _directional_persistence(path_length: float, euclidean_distance: float) -> float:
    if path_length <= 1e-9 or euclidean_distance <= 1e-9:
        return 0.5
    return max(0.0, min(1.0, float(euclidean_distance / path_length)))


def _branch_symmetry(anchor: int, rows: list[dict[str, Any]], children: list[list[int]]) -> float:
    kids = children[anchor]
    if len(kids) <= 1:
        return 0.5
    child_radii = [max(0.0, float(rows[idx]["radius"])) for idx in kids]
    if not child_radii:
        return 0.5
    med = float(np.median(child_radii))
    if med <= 1e-9:
        return 0.5
    mad = float(np.mean([abs(val - med) for val in child_radii]))
    symmetry = 1.0 - min(1.0, mad / med)
    return max(0.0, min(1.0, symmetry))


def _soma_child_owners(
    rows: list[dict[str, Any]],
    parent_idx: list[int | None],
    children: list[list[int]],
    types: list[int],
) -> tuple[int | None, dict[int, list[int]], list[int | None]]:
    soma_roots = [i for i, p in enumerate(parent_idx) if p is None and int(types[i]) == 1]
    root_idx = soma_roots[0] if soma_roots else next((i for i, p in enumerate(parent_idx) if p is None), None)
    owners: list[int | None] = [None] * len(rows)
    child_nodes: dict[int, list[int]] = {}
    if root_idx is None:
        return None, child_nodes, owners

    for child in sorted(children[root_idx], key=lambda i: int(rows[i]["id"])):
        stack = [child]
        child_nodes[child] = []
        while stack:
            idx = stack.pop()
            if owners[idx] is not None:
                continue
            owners[idx] = child
            child_nodes[child].append(idx)
            stack.extend(children[idx])
    return root_idx, child_nodes, owners


def _assign_soma_child_subtrees(
    rows: list[dict[str, Any]],
    parent_idx: list[int | None],
    children: list[list[int]],
    types: list[int],
    enabled_neurites: set[int],
    path_from_root: list[float],
    radial_from_root: list[float],
) -> tuple[dict[int, int], dict[int, dict[int, float]], list[int | None]]:
    soma_idx, child_nodes, node_child_owner = _soma_child_owners(rows, parent_idx, children, types)
    if soma_idx is None or not child_nodes or not enabled_neurites:
        return {}, {}, node_child_owner

    node_count = {child: float(len(nodes)) for child, nodes in child_nodes.items()}
    path_max = {child: max(path_from_root[i] for i in nodes) for child, nodes in child_nodes.items()}
    radial_max = {child: max(radial_from_root[i] for i in nodes) for child, nodes in child_nodes.items()}
    mean_radius = {
        child: sum(float(rows[i]["radius"]) for i in nodes) / max(1, len(nodes))
        for child, nodes in child_nodes.items()
    }
    branch_density = {
        child: sum(1 for i in nodes if len(children[i]) > 1) / max(1, len(nodes))
        for child, nodes in child_nodes.items()
    }
    soma_z = float(rows[soma_idx]["z"])
    z_max_rel = {
        child: max(float(rows[i]["z"]) - soma_z for i in nodes)
        for child, nodes in child_nodes.items()
    }
    terminal_window = int(_load_cfg().get("feature_windows", {}).get("terminal_window_nodes", 3))
    persistence = {
        child: _directional_persistence(path_max.get(child, 0.0), radial_max.get(child, 0.0))
        for child in child_nodes
    }
    taper_ratio = {
        child: _terminal_taper_ratio(nodes, rows, window_nodes=terminal_window)
        for child, nodes in child_nodes.items()
    }
    up_alignment = {
        child: _terminal_up_alignment(nodes, rows)
        for child, nodes in child_nodes.items()
    }
    symmetry = {
        child: _branch_symmetry(child, rows, children)
        for child in child_nodes
    }
    existing_ratio: dict[tuple[int, int], float] = {}
    for child, nodes in child_nodes.items():
        for cls in enabled_neurites:
            existing_ratio[(child, cls)] = sum(1 for i in nodes if int(types[i]) == cls) / max(1, len(nodes))

    n_size = _normalize_map(node_count)
    n_path = _normalize_map(path_max)
    n_radial = _normalize_map(radial_max)
    n_radius = _normalize_map(mean_radius)
    n_branch = _normalize_map(branch_density)
    n_z = _normalize_map(z_max_rel)
    n_persistence = dict(persistence)
    n_taper = {child: 1.0 - min(1.0, max(0.0, taper_ratio.get(child, 1.0))) for child in child_nodes}
    n_taper_axon = {child: min(1.0, max(0.0, taper_ratio.get(child, 1.0))) for child in child_nodes}
    n_up = dict(up_alignment)
    n_symmetry = dict(symmetry)

    cfg = _load_cfg().get("soma_child_prior", {})
    constraints = _load_cfg().get("constraints", {})
    far_basal_distance_um = float(constraints.get("far_basal_distance_um", 500.0))
    far_basal_penalty = float(constraints.get("far_basal_penalty", 0.22))
    thin_axon_max_base_radius = float(constraints.get("thin_axon_max_base_radius_um", 1.0))
    thin_axon_bonus = float(constraints.get("thin_axon_bonus", 0.10))
    weights = cfg.get("score_weights", {})
    child_scores: dict[int, dict[int, float]] = {}
    for child in child_nodes:
        sc: dict[int, float] = {}
        for cls in enabled_neurites:
            prior = existing_ratio.get((child, cls), 0.0)
            if cls == 2:
                w = weights.get("axon", {})
                s = (
                    w.get("path", 0.20) * n_path.get(child, 0.5)
                    + w.get("radial", 0.18) * n_radial.get(child, 0.5)
                    + w.get("size", 0.18) * n_size.get(child, 0.5)
                    + w.get("radius", 0.10) * (1.0 - n_radius.get(child, 0.5))
                    + w.get("branch", 0.08) * (1.0 - n_branch.get(child, 0.5))
                    + w.get("persistence", 0.14) * n_persistence.get(child, 0.5)
                    + w.get("taper", 0.06) * n_taper_axon.get(child, 0.5)
                    + w.get("symmetry", 0.04) * (1.0 - n_symmetry.get(child, 0.5))
                    + w.get("prior", 0.12) * prior
                )
                if float(rows[child]["radius"]) <= thin_axon_max_base_radius:
                    s += thin_axon_bonus
            elif cls == 4:
                w = weights.get("apical", {})
                s = (
                    w.get("z", 0.22) * n_z.get(child, 0.5)
                    + w.get("up", 0.22) * n_up.get(child, 0.5)
                    + w.get("path", 0.14) * n_path.get(child, 0.5)
                    + w.get("size", 0.12) * n_size.get(child, 0.5)
                    + w.get("radius", 0.12) * n_radius.get(child, 0.5)
                    + w.get("branch", 0.10) * n_branch.get(child, 0.5)
                    + w.get("taper", 0.06) * n_taper.get(child, 0.5)
                    + w.get("symmetry", 0.04) * n_symmetry.get(child, 0.5)
                    + w.get("prior", 0.16) * prior
                )
            else:
                w = weights.get("basal", {})
                s = (
                    w.get("path", 0.20) * (1.0 - n_path.get(child, 0.5))
                    + w.get("radial", 0.18) * (1.0 - n_radial.get(child, 0.5))
                    + w.get("radius", 0.14) * n_radius.get(child, 0.5)
                    + w.get("branch", 0.12) * n_branch.get(child, 0.5)
                    + w.get("z", 0.10) * (1.0 - n_z.get(child, 0.5))
                    + w.get("up", 0.10) * (1.0 - n_up.get(child, 0.5))
                    + w.get("persistence", 0.06) * (1.0 - n_persistence.get(child, 0.5))
                    + w.get("taper", 0.08) * n_taper.get(child, 0.5)
                    + w.get("symmetry", 0.10) * n_symmetry.get(child, 0.5)
                    + w.get("prior", 0.16) * prior
                )
                if max(path_max.get(child, 0.0), radial_max.get(child, 0.0)) > far_basal_distance_um:
                    s -= far_basal_penalty
            sc[cls] = s
        child_scores[child] = sc

    child_class = _assign_branches(child_nodes, child_scores, enabled_neurites)
    return child_class, child_scores, node_child_owner


def _pick_best_class(scores: dict[int, float], allowed: set[int]) -> int | None:
    if not allowed:
        return None
    ordered = sorted(allowed)
    return max(ordered, key=lambda cls: (float(scores.get(cls, float("-inf"))), -int(cls)))


def _enforce_primary_subtree_constraints(
    child_scores: dict[int, dict[int, float]],
    enabled_neurites: set[int],
) -> dict[int, int]:
    if not child_scores or not enabled_neurites:
        return {}

    cfg = _load_cfg().get("constraints", {})
    inherit_primary_subtree = bool(cfg.get("inherit_primary_subtree", True))
    single_axon = bool(cfg.get("single_axon", True))
    single_apical = bool(cfg.get("single_apical", True))
    axon_primary_min = float(cfg.get("axon_primary_min_score", 0.42))
    apical_primary_min = float(cfg.get("apical_primary_min_score", 0.42))

    child_ids = sorted(child_scores)
    out = _assign_branches({child: [child] for child in child_ids}, child_scores, enabled_neurites)
    if not inherit_primary_subtree:
        return out

    axon_owner: int | None = None
    if single_axon and 2 in enabled_neurites and child_ids:
        best = max(child_ids, key=lambda child: float(child_scores.get(child, {}).get(2, float("-inf"))))
        if float(child_scores.get(best, {}).get(2, float("-inf"))) >= axon_primary_min:
            axon_owner = best

    apical_owner: int | None = None
    if single_apical and 4 in enabled_neurites and child_ids:
        remaining = [child for child in child_ids if child != axon_owner]
        if remaining:
            best = max(remaining, key=lambda child: float(child_scores.get(child, {}).get(4, float("-inf"))))
            if float(child_scores.get(best, {}).get(4, float("-inf"))) >= apical_primary_min:
                apical_owner = best

    fallback_shared = set(enabled_neurites)
    if len(fallback_shared - {2, 4}) <= 0:
        fallback_shared = set(enabled_neurites)

    for child in child_ids:
        if child == axon_owner:
            out[child] = 2
            continue
        if child == apical_owner:
            out[child] = 4
            continue

        allowed = set(enabled_neurites)
        if single_axon and axon_owner is not None and 2 in allowed and len(allowed - {2}) >= 1:
            allowed.discard(2)
        if single_apical and apical_owner is not None and 4 in allowed and len(allowed - {4}) >= 1:
            allowed.discard(4)
        if not allowed:
            allowed = set(fallback_shared)

        picked = _pick_best_class(child_scores.get(child, {}), allowed)
        if picked is not None:
            out[child] = picked
    return out


def _branch_scores(
    rows: list[dict[str, Any]],
    parent_idx: list[int | None],
    children: list[list[int]],
    types: list[int],
    branch_nodes: dict[int, list[int]],
    branch_anchor: dict[int, int],
    enabled_neurites: set[int],
    path_from_root: list[float],
    radial_from_root: list[float],
    node_child_owner: list[int | None],
    child_class: dict[int, int],
    child_scores: dict[int, dict[int, float]],
) -> tuple[dict[int, dict[int, float]], dict[int, tuple[float, ...]], dict[tuple[int, int], float]]:
    x = [float(r["x"]) for r in rows]
    y = [float(r["y"]) for r in rows]
    z = [float(r["z"]) for r in rows]
    rad = [float(r["radius"]) for r in rows]

    path_len: dict[int, float] = {}
    radial_extent: dict[int, float] = {}
    mean_radius: dict[int, float] = {}
    branchiness: dict[int, float] = {}
    z_mean_rel: dict[int, float] = {}
    root_path_mean: dict[int, float] = {}
    root_radial_mean: dict[int, float] = {}
    persistence: dict[int, float] = {}
    taper_ratio: dict[int, float] = {}
    up_alignment: dict[int, float] = {}
    symmetry: dict[int, float] = {}
    existing_ratio: dict[tuple[int, int], float] = {}

    terminal_window = int(_load_cfg().get("feature_windows", {}).get("terminal_window_nodes", 3))
    for bid, nodes in branch_nodes.items():
        a = branch_anchor[bid]
        ax, ay, az = x[a], y[a], z[a]
        plen = 0.0
        max_r = 0.0
        bif = 0
        for i in nodes:
            p = parent_idx[i]
            if p is not None:
                dx = x[i] - x[p]
                dy = y[i] - y[p]
                dz = z[i] - z[p]
                plen += math.sqrt(dx * dx + dy * dy + dz * dz)
            dxa = x[i] - ax
            dya = y[i] - ay
            dza = z[i] - az
            max_r = max(max_r, math.sqrt(dxa * dxa + dya * dya + dza * dza))
            if len(children[i]) > 1:
                bif += 1

        path_len[bid] = plen
        radial_extent[bid] = max_r
        mean_radius[bid] = sum(rad[i] for i in nodes) / max(1, len(nodes))
        branchiness[bid] = bif / max(1, len(nodes))
        z_mean_rel[bid] = sum((z[i] - az) for i in nodes) / max(1, len(nodes))
        root_path_mean[bid] = sum(path_from_root[i] for i in nodes) / max(1, len(nodes))
        root_radial_mean[bid] = sum(radial_from_root[i] for i in nodes) / max(1, len(nodes))
        persistence[bid] = _directional_persistence(plen, max_r)
        taper_ratio[bid] = _terminal_taper_ratio(nodes, rows, window_nodes=terminal_window)
        up_alignment[bid] = _terminal_up_alignment([a] + nodes, rows)
        symmetry[bid] = _branch_symmetry(a, rows, children)

        for cls in enabled_neurites:
            c = sum(1 for i in nodes if int(types[i]) == cls)
            existing_ratio[(bid, cls)] = c / max(1, len(nodes))

    n_path = _normalize_map(path_len)
    n_radial = _normalize_map(radial_extent)
    n_radius = _normalize_map(mean_radius)
    n_branch = _normalize_map(branchiness)
    n_z = _normalize_map(z_mean_rel)
    n_root_path = _normalize_map(root_path_mean)
    n_root_radial = _normalize_map(root_radial_mean)
    n_persistence = dict(persistence)
    n_taper = {bid: 1.0 - min(1.0, max(0.0, taper_ratio.get(bid, 1.0))) for bid in branch_nodes}
    n_taper_axon = {bid: min(1.0, max(0.0, taper_ratio.get(bid, 1.0))) for bid in branch_nodes}
    n_up = dict(up_alignment)
    n_symmetry = dict(symmetry)

    scores: dict[int, dict[int, float]] = {}
    features: dict[int, tuple[float, ...]] = {}
    cfg = _load_cfg()
    constraints = cfg.get("constraints", {})
    far_basal_distance_um = float(constraints.get("far_basal_distance_um", 500.0))
    far_basal_penalty = float(constraints.get("far_basal_penalty", 0.22))
    thin_axon_max_base_radius = float(constraints.get("thin_axon_max_base_radius_um", 1.0))
    thin_axon_bonus = float(constraints.get("thin_axon_bonus", 0.10))
    weights = cfg.get("branch_score_weights", {})
    child_prior_cfg = cfg.get("soma_child_prior", {})
    child_branch_weight = float(child_prior_cfg.get("branch_weight", 0.38))
    child_branch_boost = float(child_prior_cfg.get("branch_boost", 0.16))
    for bid in branch_nodes:
        features[bid] = (
            n_path.get(bid, 0.5),
            n_radial.get(bid, 0.5),
            n_radius.get(bid, 0.5),
            n_branch.get(bid, 0.5),
            n_z.get(bid, 0.5),
            n_root_path.get(bid, 0.5),
            n_root_radial.get(bid, 0.5),
            n_persistence.get(bid, 0.5),
            n_taper.get(bid, 0.5),
            n_up.get(bid, 0.5),
            n_symmetry.get(bid, 0.5),
        )
        owner = next((node_child_owner[i] for i in branch_nodes[bid] if node_child_owner[i] is not None), None)
        br_scores: dict[int, float] = {}
        for cls in enabled_neurites:
            prior = existing_ratio.get((bid, cls), 0.0)
            if cls == 2:
                w = weights.get("axon", {})
                s = (
                    w.get("path", 0.14) * n_path.get(bid, 0.5)
                    + w.get("radial", 0.12) * n_radial.get(bid, 0.5)
                    + w.get("root_path", 0.18) * n_root_path.get(bid, 0.5)
                    + w.get("root_radial", 0.12) * n_root_radial.get(bid, 0.5)
                    + w.get("radius", 0.12) * (1.0 - n_radius.get(bid, 0.5))
                    + w.get("branch", 0.04) * (1.0 - n_branch.get(bid, 0.5))
                    + w.get("persistence", 0.16) * n_persistence.get(bid, 0.5)
                    + w.get("taper", 0.08) * n_taper_axon.get(bid, 0.5)
                    + w.get("symmetry", 0.04) * (1.0 - n_symmetry.get(bid, 0.5))
                    + w.get("up", 0.02) * (1.0 - abs(0.5 - n_up.get(bid, 0.5)) * 2.0)
                    + w.get("prior", 0.04) * prior
                )
                if float(rows[branch_nodes[bid][0]]["radius"]) <= thin_axon_max_base_radius:
                    s += thin_axon_bonus
            elif cls == 4:
                w = weights.get("apical", {})
                s = (
                    w.get("z", 0.20) * n_z.get(bid, 0.5)
                    + w.get("up", 0.20) * n_up.get(bid, 0.5)
                    + w.get("path", 0.12) * n_path.get(bid, 0.5)
                    + w.get("root_path", 0.16) * n_root_path.get(bid, 0.5)
                    + w.get("radius", 0.12) * n_radius.get(bid, 0.5)
                    + w.get("branch", 0.10) * n_branch.get(bid, 0.5)
                    + w.get("taper", 0.06) * n_taper.get(bid, 0.5)
                    + w.get("symmetry", 0.04) * n_symmetry.get(bid, 0.5)
                    + w.get("prior", 0.14) * prior
                )
            else:
                w = weights.get("basal", {})
                s = (
                    w.get("z", 0.12) * (1.0 - n_z.get(bid, 0.5))
                    + w.get("up", 0.12) * (1.0 - n_up.get(bid, 0.5))
                    + w.get("branch", 0.16) * n_branch.get(bid, 0.5)
                    + w.get("radius", 0.14) * n_radius.get(bid, 0.5)
                    + w.get("path", 0.08) * (1.0 - n_path.get(bid, 0.5))
                    + w.get("root_path", 0.20) * (1.0 - n_root_path.get(bid, 0.5))
                    + w.get("root_radial", 0.12) * (1.0 - n_root_radial.get(bid, 0.5))
                    + w.get("persistence", 0.08) * (1.0 - n_persistence.get(bid, 0.5))
                    + w.get("taper", 0.10) * n_taper.get(bid, 0.5)
                    + w.get("symmetry", 0.08) * n_symmetry.get(bid, 0.5)
                    + w.get("prior", 0.08) * prior
                )
                if max(root_path_mean.get(bid, 0.0), root_radial_mean.get(bid, 0.0)) > far_basal_distance_um:
                    s -= far_basal_penalty
            if owner is not None and owner in child_scores:
                s += child_branch_weight * child_scores[owner].get(cls, 0.0)
                if child_class.get(owner) == cls:
                    s += child_branch_boost
            br_scores[cls] = s
        scores[bid] = br_scores
    return scores, features, existing_ratio


def _enforce_owner_labels_on_branches(
    branch_class: dict[int, int],
    branch_nodes: dict[int, list[int]],
    node_child_owner: list[int | None],
    child_class: dict[int, int],
) -> dict[int, int]:
    if not branch_class or not child_class:
        return branch_class
    if not bool(_load_cfg().get("constraints", {}).get("inherit_primary_subtree", True)):
        return branch_class
    out = dict(branch_class)
    for bid, nodes in branch_nodes.items():
        owner = next((node_child_owner[i] for i in nodes if i < len(node_child_owner) and node_child_owner[i] is not None), None)
        if owner is not None and owner in child_class:
            out[bid] = int(child_class[owner])
    return out


def _euclid_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    d2 = 0.0
    for x, y in zip(a, b):
        d = x - y
        d2 += d * d
    dist = math.sqrt(d2)
    max_dist = math.sqrt(float(len(a)))
    if max_dist <= 0:
        return 0.5
    sim = 1.0 - (dist / max_dist)
    return max(0.0, min(1.0, sim))


def _ml_refine_scores(
    scores: dict[int, dict[int, float]],
    features: dict[int, tuple[float, ...]],
    existing_ratio: dict[tuple[int, int], float],
    enabled_neurites: set[int],
) -> dict[int, dict[int, float]]:
    if not scores or not enabled_neurites:
        return scores

    classes = sorted(enabled_neurites)
    branch_ids = sorted(features.keys())
    if not branch_ids:
        return scores

    cfg = _load_cfg()
    seed_map: dict[int, list[int]] = {c: [] for c in classes}
    seed_prior_threshold = float(cfg.get("seed_prior_threshold", 0.55))
    for bid in branch_ids:
        priors = {c: existing_ratio.get((bid, c), 0.0) for c in classes}
        best_c = max(classes, key=lambda c: priors[c])
        if priors[best_c] >= seed_prior_threshold:
            seed_map[best_c].append(bid)

    for c in classes:
        if seed_map[c]:
            continue
        best_bid = max(branch_ids, key=lambda b: scores.get(b, {}).get(c, -1e9))
        seed_map[c].append(best_bid)

    prototypes: dict[int, tuple[float, ...]] = {}
    for c in classes:
        seeds = seed_map[c]
        if not seeds:
            continue
        dim = len(features[seeds[0]])
        acc = [0.0] * dim
        for b in seeds:
            fv = features[b]
            for i in range(dim):
                acc[i] += fv[i]
        n = float(len(seeds))
        prototypes[c] = tuple(v / n for v in acc)

    out: dict[int, dict[int, float]] = {}
    for bid in branch_ids:
        out[bid] = {}
        fv = features[bid]
        for c in classes:
            base = scores.get(bid, {}).get(c, 0.0)
            proto = prototypes.get(c)
            if proto is None:
                out[bid][c] = base
                continue
            sim = _euclid_similarity(fv, proto)
            ml_blend = float(cfg.get("ml_blend", 0.28))
            ml_base = float(cfg.get("ml_base_weight", 0.72))
            out[bid][c] = ml_base * base + ml_blend * sim
    return out


def _assign_branches(
    branch_nodes: dict[int, list[int]],
    scores: dict[int, dict[int, float]],
    enabled_neurites: set[int],
) -> dict[int, int]:
    if not branch_nodes or not enabled_neurites:
        return {}

    selected = sorted(enabled_neurites)
    assign: dict[int, int] = {}
    if len(selected) == 1:
        only = selected[0]
        for bid in branch_nodes:
            assign[bid] = only
        return assign

    for bid in branch_nodes:
        b_scores = scores.get(bid, {})
        cls = max(selected, key=lambda c: b_scores.get(c, -1e9))
        assign[bid] = cls

    missing = [c for c in selected if c not in set(assign.values())]
    if missing and len(branch_nodes) >= len(selected):
        for need in missing:
            best_bid = None
            best_gain = -1e9
            best_need_score = -1e9
            for bid in branch_nodes:
                cur = assign[bid]
                cur_s = scores.get(bid, {}).get(cur, 0.0)
                need_s = scores.get(bid, {}).get(need, 0.0)
                gain = need_s - cur_s
                if gain > best_gain:
                    best_gain = gain
                    best_need_score = need_s
                    best_bid = bid
            assign_cfg = _load_cfg().get("assign_missing", {})
            min_score = float(assign_cfg.get("min_score", 0.58))
            min_gain = float(assign_cfg.get("min_gain", -0.06))
            if best_bid is not None and (best_need_score >= min_score and best_gain >= min_gain):
                assign[best_bid] = need
    return assign


def _smooth_branch_labels(
    branch_class: dict[int, int],
    scores: dict[int, dict[int, float]],
    branch_anchor: dict[int, int],
    node_branch: list[int] | None = None,
) -> dict[int, int]:
    if not branch_class:
        return branch_class

    out = dict(branch_class)
    anchor_to_branches: dict[int, list[int]] = {}
    for bid, a in branch_anchor.items():
        anchor_to_branches.setdefault(a, []).append(bid)

    smooth_cfg = _load_cfg().get("smoothing", {})
    maj_frac = float(smooth_cfg.get("maj_fraction", 0.67))
    flip_margin = float(smooth_cfg.get("flip_margin", 0.10))
    continuity_margin = float(smooth_cfg.get("continuity_margin", 0.02))

    for bid, cur_cls in list(out.items()):
        anchor = branch_anchor.get(bid)
        sibs = [s for s in anchor_to_branches.get(anchor, []) if s != bid]
        if len(sibs) >= 2:
            counts: dict[int, int] = {}
            for s in sibs:
                c = out.get(s)
                if c is None:
                    continue
                counts[c] = counts.get(c, 0) + 1
            if counts:
                maj_cls, maj_count = max(counts.items(), key=lambda kv: kv[1])
                if maj_cls != cur_cls and maj_count / max(1, len(sibs)) >= maj_frac:
                    cur_score = scores.get(bid, {}).get(cur_cls, 0.0)
                    maj_score = scores.get(bid, {}).get(maj_cls, 0.0)
                    if cur_score - maj_score < flip_margin:
                        out[bid] = maj_cls
                        cur_cls = maj_cls

        if node_branch is None or anchor is None or anchor < 0 or anchor >= len(node_branch):
            continue
        parent_bid = node_branch[anchor]
        if parent_bid == -1 or parent_bid == bid or parent_bid not in out:
            continue
        parent_cls = out[parent_bid]
        if parent_cls == cur_cls:
            continue
        cur_score = scores.get(bid, {}).get(cur_cls, 0.0)
        parent_score = scores.get(bid, {}).get(parent_cls, 0.0)
        if cur_score - parent_score < continuity_margin:
            out[bid] = parent_cls

    return out



def _branch_path_lengths(
    rows: list[dict[str, Any]],
    parent_idx: list[int | None],
    branch_nodes: dict[int, list[int]],
) -> dict[int, float]:
    lengths: dict[int, float] = {}
    for bid, nodes in branch_nodes.items():
        plen = 0.0
        for i in nodes:
            pidx = parent_idx[i]
            if pidx is None:
                continue
            dx = float(rows[i]["x"]) - float(rows[pidx]["x"])
            dy = float(rows[i]["y"]) - float(rows[pidx]["y"])
            dz = float(rows[i]["z"]) - float(rows[pidx]["z"])
            plen += math.sqrt(dx * dx + dy * dy + dz * dz)
        lengths[bid] = plen
    return lengths


def _branch_graph(
    branch_anchor: dict[int, int],
    node_branch: list[int],
) -> tuple[dict[int, int], dict[int, list[int]]]:
    branch_parent: dict[int, int] = {}
    branch_children: dict[int, list[int]] = {}
    for bid, anchor in branch_anchor.items():
        if anchor < 0 or anchor >= len(node_branch):
            continue
        parent_bid = node_branch[anchor]
        if parent_bid == -1 or parent_bid == bid:
            continue
        branch_parent[bid] = parent_bid
        branch_children.setdefault(parent_bid, []).append(bid)
    return branch_parent, branch_children


def _neighbor_refine_scores(
    scores: dict[int, dict[int, float]],
    branch_class: dict[int, int],
    branch_parent: dict[int, int],
    branch_children: dict[int, list[int]],
) -> dict[int, dict[int, float]]:
    cfg = _load_cfg().get("refinement", {})
    parent_weight = float(cfg.get("parent_weight", 0.14))
    child_weight = float(cfg.get("child_weight", 0.18))
    out = {bid: dict(sc) for bid, sc in scores.items()}
    for bid, sc in out.items():
        parent = branch_parent.get(bid)
        if parent in branch_class:
            cls = branch_class[parent]
            sc[cls] = sc.get(cls, 0.0) + parent_weight
        kids = branch_children.get(bid, [])
        if kids:
            weight = child_weight / max(1, len(kids))
            for child in kids:
                cls = branch_class.get(child)
                if cls is None:
                    continue
                sc[cls] = sc.get(cls, 0.0) + weight
    return out


def _refine_topology_branch_labels(
    branch_class: dict[int, int],
    scores: dict[int, dict[int, float]],
    branch_parent: dict[int, int],
    branch_children: dict[int, list[int]],
    branch_lengths: dict[int, float],
) -> dict[int, int]:
    if not branch_class:
        return branch_class

    cfg = _load_cfg().get("refinement", {})
    iterations = max(1, int(cfg.get("iterations", 2)))
    island_max_path = float(cfg.get("island_max_path", 36.0))
    island_relative_max = float(cfg.get("island_relative_max", 0.35))
    island_flip_margin = float(cfg.get("island_flip_margin", 0.14))

    out = dict(branch_class)
    for _ in range(iterations):
        updated = dict(out)
        for bid, cur_cls in out.items():
            parent = branch_parent.get(bid)
            if parent is None or parent not in out:
                continue
            parent_cls = out[parent]
            if parent_cls == cur_cls:
                continue
            matching_children = [child for child in branch_children.get(bid, []) if out.get(child) == parent_cls]
            if not matching_children:
                continue

            cur_score = scores.get(bid, {}).get(cur_cls, 0.0)
            target_score = scores.get(bid, {}).get(parent_cls, 0.0)
            branch_len = branch_lengths.get(bid, 0.0)
            ref_len = max(
                [branch_lengths.get(parent, 0.0)] + [branch_lengths.get(child, 0.0) for child in matching_children] + [1.0]
            )
            is_short_island = (
                branch_len <= island_max_path
                or branch_len <= island_relative_max * ref_len
                or cur_score - target_score < island_flip_margin
            )
            if is_short_island:
                updated[bid] = parent_cls
        out = updated
    return out

def _apply_rules(rows: list[dict[str, Any]], opts: RuleBatchOptions) -> tuple[list[int], list[float], int, int]:
    orig_types = [int(row["type"]) for row in rows]
    types = list(orig_types)
    orig_radii = [float(row["radius"]) for row in rows]
    radii = list(orig_radii)
    parent_idx, children, order = _build_topology(rows)
    path_from_root, radial_from_root, _, _ = _compute_root_metrics(rows, parent_idx, children, order)

    if opts.soma:
        for i, row in enumerate(rows):
            if int(row["parent"]) == -1 and types[i] != 1:
                types[i] = 1

    enabled_neurites: set[int] = set()
    if opts.axon:
        enabled_neurites.add(2)
    if opts.basal:
        enabled_neurites.add(3)
    if opts.apic:
        enabled_neurites.add(4)

    if enabled_neurites:
        child_class, child_scores, node_child_owner = _assign_soma_child_subtrees(
            rows,
            parent_idx,
            children,
            types,
            enabled_neurites,
            path_from_root,
            radial_from_root,
        )
        child_class = _enforce_primary_subtree_constraints(child_scores, enabled_neurites)
        branch_nodes, branch_anchor, node_branch = _branch_partition(rows, parent_idx, children, types)
        scores, features, existing_ratio = _branch_scores(
            rows,
            parent_idx,
            children,
            types,
            branch_nodes,
            branch_anchor,
            enabled_neurites,
            path_from_root,
            radial_from_root,
            node_child_owner,
            child_class,
            child_scores,
        )
        scores = _ml_refine_scores(scores, features, existing_ratio, enabled_neurites)
        branch_class = _assign_branches(branch_nodes, scores, enabled_neurites)
        branch_class = _smooth_branch_labels(branch_class, scores, branch_anchor, node_branch)
        branch_class = _enforce_owner_labels_on_branches(branch_class, branch_nodes, node_child_owner, child_class)
        branch_parent, branch_children = _branch_graph(branch_anchor, node_branch)
        branch_lengths = _branch_path_lengths(rows, parent_idx, branch_nodes)
        scores = _neighbor_refine_scores(scores, branch_class, branch_parent, branch_children)
        branch_class = _assign_branches(branch_nodes, scores, enabled_neurites)
        branch_class = _smooth_branch_labels(branch_class, scores, branch_anchor, node_branch)
        branch_class = _enforce_owner_labels_on_branches(branch_class, branch_nodes, node_child_owner, child_class)
        branch_class = _refine_topology_branch_labels(
            branch_class,
            scores,
            branch_parent,
            branch_children,
            branch_lengths,
        )
        branch_class = _enforce_owner_labels_on_branches(branch_class, branch_nodes, node_child_owner, child_class)

        for bid, nodes in branch_nodes.items():
            cls = branch_class.get(bid)
            if cls is None:
                continue
            for i in nodes:
                if opts.soma and int(types[i]) == 1:
                    continue
                types[i] = cls

        if opts.soma:
            for i, row in enumerate(rows):
                if int(row["parent"]) == -1:
                    types[i] = 1

    if opts.rad:
        radius_cfg = _load_cfg().get("radius", {})
        copy_parent = bool(radius_cfg.get("copy_parent_if_zero", True))
        if copy_parent:
            for idx in order:
                pidx = parent_idx[idx]
                if pidx is None:
                    continue
                if radii[idx] <= 0 and radii[pidx] > 0:
                    radii[idx] = radii[pidx]

    type_changes = sum(1 for old, new in zip(orig_types, types) if int(old) != int(new))
    radius_changes = sum(1 for old, new in zip(orig_radii, radii) if float(old) != float(new))
    return types, radii, type_changes, radius_changes


def _write_swc(path: Path, headers: list[str], rows: list[dict[str, Any]], types: list[int], radii: list[float]) -> None:
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


def run_rule_file(
    file_path: str,
    opts: RuleBatchOptions,
    *,
    output_path: str | None = None,
    write_output: bool = True,
    write_log: bool = True,
) -> RuleFileResult:
    in_path = Path(file_path)
    headers, rows = _parse_swc(in_path)
    if not rows:
        raise ValueError(f"{in_path.name}: no valid SWC rows")

    orig_types = [int(r["type"]) for r in rows]
    orig_radii = [float(r["radius"]) for r in rows]
    types, radii, type_changes, radius_changes = _apply_rules(rows, opts)

    out_path: Path | None = None
    if write_output:
        out_path = (
            Path(output_path)
            if output_path
            else in_path.with_name(f"{in_path.stem}_auto_typed{in_path.suffix}")
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
        log_target = auto_typing_log_path_for_file(in_path)
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

    return RuleFileResult(
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


def run_rule_batch(folder: str, opts: RuleBatchOptions) -> RuleBatchResult:
    in_dir = Path(folder)
    swc_files = sorted([p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() == ".swc"])

    out_dir = in_dir / f"{in_dir.name}_auto_typing"
    out_dir.mkdir(parents=True, exist_ok=True)

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
            types, radii, type_changes, radius_changes = _apply_rules(rows, opts)
            out_path = out_dir / swc_path.name
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
                    swc_path.name,
                    rows,
                    orig_types,
                    types,
                    orig_radii,
                    radii,
                )
            )
        except Exception as e:
            failures.append(f"{swc_path.name}: {e}")

    zip_path: str | None = None
    if opts.zip_output and processed > 0:
        zip_target = in_dir / f"{in_dir.name}_auto_typing.zip"
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
    log_path = write_text_report(out_dir / "auto_typing_report.txt", format_auto_typing_report_text(payload))

    return RuleBatchResult(
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
