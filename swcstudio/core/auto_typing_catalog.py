"""Shared auto-typing guide text for CLI and GUI."""

from __future__ import annotations

from typing import Any

from swcstudio.core.auto_typing import get_auto_rules_config


def _f(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return float(default)


def _i(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:  # noqa: BLE001
        return int(default)


def _b(v: Any, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    if v is None:
        return bool(default)
    return bool(v)


def get_auto_typing_guide(config: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = config if isinstance(config, dict) else get_auto_rules_config()

    w_axon = cfg.get("branch_score_weights", {}).get("axon", {})
    w_apical = cfg.get("branch_score_weights", {}).get("apical", {})
    w_basal = cfg.get("branch_score_weights", {}).get("basal", {})
    feature_cfg = cfg.get("feature_windows", {})

    ax_path = _f(w_axon.get("path", 0.14), 0.14)
    ax_radial = _f(w_axon.get("radial", 0.12), 0.12)
    ax_radius = _f(w_axon.get("radius", 0.12), 0.12)
    ax_branch = _f(w_axon.get("branch", 0.04), 0.04)
    ax_persistence = _f(w_axon.get("persistence", 0.16), 0.16)
    ax_taper = _f(w_axon.get("taper", 0.08), 0.08)
    ax_prior = _f(w_axon.get("prior", 0.04), 0.04)

    ap_z = _f(w_apical.get("z", 0.20), 0.20)
    ap_up = _f(w_apical.get("up", 0.20), 0.20)
    ap_path = _f(w_apical.get("path", 0.12), 0.12)
    ap_radius = _f(w_apical.get("radius", 0.12), 0.12)
    ap_branch = _f(w_apical.get("branch", 0.10), 0.10)
    ap_taper = _f(w_apical.get("taper", 0.06), 0.06)
    ap_prior = _f(w_apical.get("prior", 0.14), 0.14)

    ba_z = _f(w_basal.get("z", 0.12), 0.12)
    ba_up = _f(w_basal.get("up", 0.12), 0.12)
    ba_branch = _f(w_basal.get("branch", 0.16), 0.16)
    ba_radius = _f(w_basal.get("radius", 0.14), 0.14)
    ba_path = _f(w_basal.get("path", 0.08), 0.08)
    ba_persistence = _f(w_basal.get("persistence", 0.08), 0.08)
    ba_taper = _f(w_basal.get("taper", 0.10), 0.10)
    ba_prior = _f(w_basal.get("prior", 0.08), 0.08)

    seed_prior_threshold = _f(cfg.get("seed_prior_threshold", 0.55), 0.55)
    ml_blend = _f(cfg.get("ml_blend", 0.28), 0.28)
    ml_base_weight = _f(cfg.get("ml_base_weight", 0.72), 0.72)

    assign_cfg = cfg.get("assign_missing", {})
    min_score = _f(assign_cfg.get("min_score", 0.58), 0.58)
    min_gain = _f(assign_cfg.get("min_gain", -0.06), -0.06)

    smooth_cfg = cfg.get("smoothing", {})
    maj_fraction = _f(smooth_cfg.get("maj_fraction", 0.67), 0.67)
    flip_margin = _f(smooth_cfg.get("flip_margin", 0.10), 0.10)

    prop_cfg = cfg.get("propagation_weights", {})
    w_self = _f(prop_cfg.get("self", 0.35), 0.35)
    w_parent = _f(prop_cfg.get("parent", 0.35), 0.35)
    w_children = _f(prop_cfg.get("children", 0.20), 0.20)
    w_branch_prior = _f(prop_cfg.get("branch_prior", 0.30), 0.30)
    prop_iters = _i(prop_cfg.get("iterations", 4), 4)

    radius_cfg = cfg.get("radius", {})
    copy_parent_if_zero = _b(radius_cfg.get("copy_parent_if_zero", True), True)

    constraints_cfg = cfg.get("constraints", {})
    inherit_primary_subtree = _b(constraints_cfg.get("inherit_primary_subtree", True), True)
    single_axon = _b(constraints_cfg.get("single_axon", True), True)
    single_apical = _b(constraints_cfg.get("single_apical", True), True)
    axon_primary_min = _f(constraints_cfg.get("axon_primary_min_score", 0.42), 0.42)
    apical_primary_min = _f(constraints_cfg.get("apical_primary_min_score", 0.42), 0.42)
    far_basal_distance = _f(constraints_cfg.get("far_basal_distance_um", 500.0), 500.0)
    far_basal_penalty = _f(constraints_cfg.get("far_basal_penalty", 0.22), 0.22)
    thin_axon_radius = _f(constraints_cfg.get("thin_axon_max_base_radius_um", 1.0), 1.0)
    thin_axon_bonus = _f(constraints_cfg.get("thin_axon_bonus", 0.10), 0.10)
    terminal_window = _i(feature_cfg.get("terminal_window_nodes", 3), 3)

    body = (
        "This panel shows the JSON configuration that controls the auto-labeling\n"
        "algorithm.\n"
        "You can edit thresholds and weights and save to change behavior.\n\n"
        "Decision summary:\n"
        "1) Treat the SWC as directed paths / branch segments, not as independent nodes.\n"
        "2) Identify soma-child primary subtrees and score them as axon/apical/basal.\n"
        "3) Use path-aware geometry features:\n"
        "   path length, radial extent, mean radius, branchiness, directional persistence,\n"
        "   terminal taper, and alignment with the global +Z up direction.\n"
        "4) Enforce hard constraints at the soma boundary:\n"
        "   one primary axon winner, one primary apical winner, and subtree-wide\n"
        "   inheritance from each primary branch.\n"
        "5) Score branch segments for local geometry, optionally refine via\n"
        "   nearest-centroid similarity, then smooth short topological islands.\n"
        "6) Override every branch inside a classified primary subtree back to the\n"
        "   primary subtree class so no type switch can appear mid-track.\n"
        "7) Radius rule: copy parent radius into zero/invalid radii when enabled.\n\n"
        "Hard topology constraints:\n"
        f"- Primary subtree inheritance: {inherit_primary_subtree}\n"
        f"- Single axon winner: {single_axon} (min primary score {axon_primary_min:.3f})\n"
        f"- Single apical winner: {single_apical} (min primary score {apical_primary_min:.3f})\n"
        f"- Basal distance penalty: subtract {far_basal_penalty:.3f} when a candidate\n"
        f"  subtree/branch extends beyond {far_basal_distance:.1f} um from the soma/root.\n\n"
        f"- Thin-axon bonus: +{thin_axon_bonus:.3f} when a primary/branch base radius is <= {thin_axon_radius:.2f} um.\n"
        f"- Terminal taper window: last/first {terminal_window} node(s) are compared to estimate distal taper.\n\n"
        "Type decision boundaries:\n"
        "- Soma (type 1): if --soma is enabled, root nodes (parent == -1) are\n"
        "  forced to soma before and after branch assignment.\n"
        "- Axon score:\n"
        f"  score_axon = {ax_path:.3f}*path + {ax_radial:.3f}*radial + {ax_persistence:.3f}*persistence + "
        f"{ax_taper:.3f}*terminal_consistency + {ax_radius:.3f}*(1-radius) + "
        f"{ax_branch:.3f}*(1-branchiness) + {ax_prior:.3f}*prior\n"
        "- Apical score:\n"
        f"  score_apical = {ap_z:.3f}*z + {ap_up:.3f}*up_alignment + {ap_path:.3f}*path + "
        f"{ap_radius:.3f}*radius + {ap_branch:.3f}*branchiness + {ap_taper:.3f}*taper + {ap_prior:.3f}*prior\n"
        "- Basal score:\n"
        f"  score_basal = {ba_z:.3f}*(1-z) + {ba_up:.3f}*(1-up_alignment) + {ba_branch:.3f}*branchiness + "
        f"{ba_radius:.3f}*radius + {ba_path:.3f}*path + {ba_persistence:.3f}*(1-persistence) + "
        f"{ba_taper:.3f}*taper + {ba_prior:.3f}*prior\n"
        "- Branch class assignment: choose highest score among enabled classes.\n\n"
        "Global thresholds:\n"
        f"- Seed prior threshold: prior >= {seed_prior_threshold:.3f}\n"
        f"- Missing-class reassignment: score >= {min_score:.3f} and gain >= {min_gain:.3f}\n"
        f"- Sibling smoothing: majority >= {maj_fraction:.3f} and margin < {flip_margin:.3f}\n"
        f"- ML blend: final = ({ml_base_weight:.3f} * base_score) + ({ml_blend:.3f} * similarity)\n"
        f"- Legacy propagation weights retained in JSON for compatibility: self={w_self:.3f}, "
        f"parent={w_parent:.3f}, children_total={w_children:.3f}, branch_prior={w_branch_prior:.3f}, iterations={prop_iters}\n"
        f"- Radius boundary: copy_parent_if_zero = {copy_parent_if_zero}"
    )
    return {"title": "Decision engine — auto-label rules", "body": body}


def format_auto_typing_guide_text(config: dict[str, Any] | None = None) -> str:
    guide = get_auto_typing_guide(config=config)
    title = str(guide.get("title", "Auto Typing Rule Guide"))
    body = str(guide.get("body", "")).rstrip()
    return f"{title}\n{'-' * len(title)}\n{body}".rstrip()
