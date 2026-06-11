"""Inference feature helpers for the 3-class Branch3 rescue head."""
from __future__ import annotations

import numpy as np

from .branch_features import BRANCH_FEATURE_NAMES
from .pipeline import _branch_feature_with_owner
from .train_stage2 import OWNER_AUG_FEATURE_NAMES

SWC_LABELS = (2, 3, 4)
LABEL_TO_CLASS = {2: 0, 3: 1, 4: 2}
CLASS_TO_LABEL = {0: 2, 1: 3, 2: 4}

BRANCH3_EXTRA_FEATURE_NAMES: tuple[str, ...] = (
    "current_is_axon",
    "current_is_basal",
    "current_is_apical",
    "current_confidence",
    "owner_apical_margin",
    "owner_basal_margin",
    "owner_axon_margin",
    "owner_apical_rank",
    "owner_is_best_apical",
    "owner_best_apical_prob",
    "owner_best_apical_margin",
    "has_owner_info",
)

BRANCH3_FEATURE_NAMES: tuple[str, ...] = (
    tuple(BRANCH_FEATURE_NAMES)
    + tuple(OWNER_AUG_FEATURE_NAMES)
    + BRANCH3_EXTRA_FEATURE_NAMES
)


def _owner_extra(
    primary_root_idx: int | None,
    subtree_owner_map: dict[int, dict[str, float | int]],
) -> np.ndarray:
    if primary_root_idx is None or primary_root_idx not in subtree_owner_map:
        return np.zeros(len(BRANCH3_EXTRA_FEATURE_NAMES) - 4, dtype=np.float32)

    owner_items = []
    for root, info in subtree_owner_map.items():
        p4 = float(info.get("prob_4", 0.0))
        p3 = float(info.get("prob_3", 0.0))
        p2 = float(info.get("prob_2", 0.0))
        owner_items.append((root, p4, p4 - max(p2, p3)))
    owner_items.sort(key=lambda x: x[1], reverse=True)
    rank_by_root = {
        root: (1.0 - rank / max(1, len(owner_items) - 1)) if len(owner_items) > 1 else 1.0
        for rank, (root, _, _) in enumerate(owner_items)
    }
    best_root, best_apical_prob, best_apical_margin = owner_items[0]

    info = subtree_owner_map[primary_root_idx]
    p2 = float(info.get("prob_2", 0.0))
    p3 = float(info.get("prob_3", 0.0))
    p4 = float(info.get("prob_4", 0.0))
    return np.array(
        [
            p4 - max(p2, p3),
            p3 - max(p2, p4),
            p2 - max(p3, p4),
            rank_by_root.get(primary_root_idx, 0.0),
            1.0 if primary_root_idx == best_root else 0.0,
            best_apical_prob,
            best_apical_margin,
            1.0,
        ],
        dtype=np.float32,
    )


def _branch_feature_vector(
    br,
    subtree_owner_map: dict[int, dict[str, float | int]],
    current_label: int,
    current_conf: float,
) -> np.ndarray:
    base = _branch_feature_with_owner(br, subtree_owner_map).astype(np.float32)
    cur = np.array(
        [
            1.0 if current_label == 2 else 0.0,
            1.0 if current_label == 3 else 0.0,
            1.0 if current_label == 4 else 0.0,
            float(current_conf),
        ],
        dtype=np.float32,
    )
    owner = _owner_extra(getattr(br, "primary_root_idx", None), subtree_owner_map)
    out = np.concatenate([base, cur, owner]).astype(np.float32)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
