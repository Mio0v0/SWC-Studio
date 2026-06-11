"""Deployment scoring for learned per-cell auto-label quality flags."""
from __future__ import annotations

import math
import re
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .confidence import ConfidenceConfig, summarize_confidence
from .features import SWCNode

F1_COL = "held_out_F1"

GT_OR_LABEL_COLUMNS = {
    "cell_type_gt",
    "held_out_F1",
    "acc",
    "axon_F1",
    "basal_F1",
    "apical_F1",
    "stage1_correct",
    "axon_frac",
    "apical_frac",
    "basal_frac",
    "apical_mean_z",
    "apical_above_soma",
    "apical_z_extent",
    "elapsed_s",
}

CONFIDENCE_NUMERIC_FEATURES = [
    "confidence_features_missing",
    "n_nodes_conf",
    "stage1_conf_conf_run",
    "pred_axon_conf_run",
    "pred_basal_conf_run",
    "pred_apical_conf_run",
    "node_label_disagree_frac",
    "node_conf_abs_delta_mean",
    "conf_mean",
    "conf_std",
    "conf_min",
    "conf_p05",
    "conf_p10",
    "conf_p25",
    "conf_median",
    "conf_frac_lt_05",
    "conf_frac_lt_06",
    "conf_frac_lt_07",
    "conf_frac_lt_08",
    "conf_frac_lt_09",
    "axon_conf_mean",
    "axon_conf_p10",
    "axon_conf_frac_lt_07",
    "basal_conf_mean",
    "basal_conf_p10",
    "basal_conf_frac_lt_07",
    "apical_conf_mean",
    "apical_conf_p10",
    "apical_conf_frac_lt_07",
    "n_pred_branches",
    "branch_conf_mean",
    "branch_conf_min",
    "branch_conf_p10",
    "branch_frac_conf_lt_07",
    "branch_frac_conf_lt_08",
    "branch_n_nodes_p90",
    "pred_soma_z",
    "pred_axon_z_extent",
    "pred_axon_z_mean_rel_soma",
    "pred_axon_z_std",
    "pred_axon_x_extent",
    "pred_axon_y_extent",
    "pred_basal_z_extent",
    "pred_basal_z_mean_rel_soma",
    "pred_basal_z_std",
    "pred_basal_x_extent",
    "pred_basal_y_extent",
    "pred_apical_z_extent",
    "pred_apical_z_mean_rel_soma",
    "pred_apical_z_std",
    "pred_apical_x_extent",
    "pred_apical_y_extent",
    "branch3_changed_frac",
    "branch3_label_disagree_frac",
    "branch3_conf_abs_delta_mean",
    "branch3_axon_delta_frac",
    "branch3_basal_delta_frac",
    "branch3_apical_delta_frac",
    "branch3_to_apical_frac",
    "branch3_from_apical_frac",
]
CONFIDENCE_CATEGORICAL_FEATURES = ["stage1_pred_conf_run"]
EXTRA_NUMERIC_PREFIXES = ("xmodel_", "baseline_")

_FLAG_CACHE: dict[str, dict[str, Any]] = {}


def _n_components(nodes: list[SWCNode]) -> int:
    n = len(nodes)
    if n == 0:
        return 0
    id_to_idx = {nd.id: i for i, nd in enumerate(nodes)}
    parent_idx = [-1] * n
    children: list[list[int]] = [[] for _ in nodes]
    for i, nd in enumerate(nodes):
        if nd.parent != -1 and nd.parent in id_to_idx:
            p = id_to_idx[nd.parent]
            parent_idx[i] = p
            children[p].append(i)

    visited = [False] * n
    n_comp = 0
    for start in range(n):
        if visited[start]:
            continue
        n_comp += 1
        stack = [start]
        while stack:
            i = stack.pop()
            if visited[i]:
                continue
            visited[i] = True
            p = parent_idx[i]
            if p >= 0 and not visited[p]:
                stack.append(p)
            stack.extend(j for j in children[i] if not visited[j])
    return n_comp


def _safe_percentile(values: list[float], q: float, default: float = 0.0) -> float:
    return float(np.percentile(values, q)) if values else default


def _confidence_summary(labels: list[int], confs: list[float]) -> dict[str, float]:
    arr = np.asarray(confs, dtype=float)
    out: dict[str, float] = {
        "conf_mean": float(arr.mean()) if arr.size else 0.0,
        "conf_std": float(arr.std()) if arr.size else 0.0,
        "conf_min": float(arr.min()) if arr.size else 0.0,
        "conf_p05": float(np.percentile(arr, 5)) if arr.size else 0.0,
        "conf_p10": float(np.percentile(arr, 10)) if arr.size else 0.0,
        "conf_p25": float(np.percentile(arr, 25)) if arr.size else 0.0,
        "conf_median": float(np.median(arr)) if arr.size else 0.0,
    }
    for thr in (0.5, 0.6, 0.7, 0.8, 0.9):
        key = str(thr).replace(".", "")
        out[f"conf_frac_lt_{key}"] = float((arr < thr).mean()) if arr.size else 0.0

    lab_arr = np.asarray(labels, dtype=int)
    for label, name in {2: "axon", 3: "basal", 4: "apical"}.items():
        vals = arr[lab_arr == label]
        out[f"{name}_conf_mean"] = float(vals.mean()) if vals.size else 0.0
        out[f"{name}_conf_p10"] = float(np.percentile(vals, 10)) if vals.size else 0.0
        out[f"{name}_conf_frac_lt_07"] = float((vals < 0.7).mean()) if vals.size else 0.0
    return out


def _branch_summary(
    nodes: list[SWCNode],
    labels: list[int],
    confs: list[float],
    stage1_type: str,
    stage1_conf: float,
) -> dict[str, float]:
    cfg = ConfidenceConfig(node_low_threshold=0.7)
    branches, _cell = summarize_confidence(nodes, labels, confs, stage1_type, stage1_conf, cfg)
    means = [float(b.mean_confidence) for b in branches]
    mins = [float(b.min_confidence) for b in branches]
    n_nodes = [int(b.n_nodes) for b in branches]
    return {
        "n_pred_branches": len(branches),
        "branch_conf_mean": float(np.mean(means)) if means else 0.0,
        "branch_conf_min": min(mins) if mins else 0.0,
        "branch_conf_p10": _safe_percentile(means, 10),
        "branch_frac_conf_lt_07": float(np.mean([m < 0.7 for m in means])) if means else 0.0,
        "branch_frac_conf_lt_08": float(np.mean([m < 0.8 for m in means])) if means else 0.0,
        "branch_n_nodes_p90": _safe_percentile(n_nodes, 90),
    }


def _predicted_geometry(nodes: list[SWCNode], labels: list[int]) -> dict[str, float]:
    labels_arr = np.asarray(labels, dtype=int)
    soma_zs = [nd.z for nd, lab in zip(nodes, labels_arr) if lab == 1]
    if not soma_zs:
        soma_zs = [nd.z for nd in nodes if nd.type == 1]
    soma_z = float(np.mean(soma_zs)) if soma_zs else 0.0

    out: dict[str, float] = {"pred_soma_z": soma_z}
    for label, name in {2: "axon", 3: "basal", 4: "apical"}.items():
        xs = [nd.x for nd, lab in zip(nodes, labels_arr) if lab == label]
        ys = [nd.y for nd, lab in zip(nodes, labels_arr) if lab == label]
        zs = [nd.z for nd, lab in zip(nodes, labels_arr) if lab == label]
        if zs:
            out[f"pred_{name}_z_extent"] = float(max(zs) - min(zs))
            out[f"pred_{name}_z_mean_rel_soma"] = float(np.mean(zs) - soma_z)
            out[f"pred_{name}_z_std"] = float(np.std(zs))
            out[f"pred_{name}_x_extent"] = float(max(xs) - min(xs))
            out[f"pred_{name}_y_extent"] = float(max(ys) - min(ys))
        else:
            out[f"pred_{name}_z_extent"] = 0.0
            out[f"pred_{name}_z_mean_rel_soma"] = 0.0
            out[f"pred_{name}_z_std"] = 0.0
            out[f"pred_{name}_x_extent"] = 0.0
            out[f"pred_{name}_y_extent"] = 0.0
    return out


def _branch3_disagreement_features(
    labels: list[int],
    confs: list[float],
    base_labels: list[int] | None,
    base_confs: list[float] | None,
) -> dict[str, float]:
    n = max(1, len(labels))
    if not base_labels or len(base_labels) != len(labels):
        return {
            "branch3_changed_frac": 0.0,
            "branch3_label_disagree_frac": 0.0,
            "branch3_conf_abs_delta_mean": 0.0,
            "branch3_axon_delta_frac": 0.0,
            "branch3_basal_delta_frac": 0.0,
            "branch3_apical_delta_frac": 0.0,
            "branch3_to_apical_frac": 0.0,
            "branch3_from_apical_frac": 0.0,
        }
    cur = np.asarray(labels, dtype=int)
    base = np.asarray(base_labels, dtype=int)
    changed = cur != base
    out = {
        "branch3_changed_frac": float(changed.mean()),
        "branch3_label_disagree_frac": float(changed.mean()),
        "branch3_conf_abs_delta_mean": float(
            np.mean(np.abs(np.asarray(confs, dtype=float) - np.asarray(base_confs or confs, dtype=float)))
        ),
        "branch3_axon_delta_frac": float(((cur == 2).sum() - (base == 2).sum()) / n),
        "branch3_basal_delta_frac": float(((cur == 3).sum() - (base == 3).sum()) / n),
        "branch3_apical_delta_frac": float(((cur == 4).sum() - (base == 4).sum()) / n),
        "branch3_to_apical_frac": float(((cur == 4) & (base != 4)).sum() / n),
        "branch3_from_apical_frac": float(((cur != 4) & (base == 4)).sum() / n),
    }
    return out


def _source_from_name(path: Path | str) -> str:
    name = Path(path).name
    return name.split("__", 1)[0] if "__" in name else ""


def _lab_tokens(filename: str) -> tuple[str, str]:
    rest = filename.split("__", 1)[1] if "__" in filename else filename
    stem = Path(rest).stem
    toks = [t.lower() for t in re.split(r"[-_\s]+", stem) if t]
    if not toks:
        return "", ""
    lab_prefix = toks[0]
    study_prefix = "_".join(toks[:2]) if len(toks) >= 2 else toks[0]
    return lab_prefix, study_prefix


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    numeric_base = [
        "n_nodes",
        "stage1_conf",
        "n_components",
        "pred_axon",
        "pred_basal",
        "pred_apical",
        "seed42_conf",
        "seed789_conf",
    ]
    for col in numeric_base:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "source" not in df.columns:
        df["source"] = df["file"].astype(str).str.split("__", n=1).str[0]
    if "stage1_pred" not in df.columns:
        df["stage1_pred"] = ""

    lab_parts = df["file"].astype(str).map(_lab_tokens)
    df["lab_prefix"] = [x[0] for x in lab_parts]
    df["study_prefix"] = [x[1] for x in lab_parts]

    non_soma = np.maximum(df["n_nodes"].fillna(0).to_numpy(dtype=float) - 1.0, 1.0)
    for cls in ("axon", "basal", "apical"):
        count_col = f"pred_{cls}"
        df[f"pred_{cls}_frac"] = df[count_col].fillna(0).to_numpy(dtype=float) / non_soma
        df[f"log_pred_{cls}"] = np.log1p(df[count_col].fillna(0).to_numpy(dtype=float))

    frac_cols = ["pred_axon_frac", "pred_basal_frac", "pred_apical_frac"]
    fracs = df[frac_cols].fillna(0.0).clip(lower=0.0)
    df["pred_entropy"] = (-(fracs * np.log(fracs.replace(0.0, np.nan)))).sum(axis=1).fillna(0.0)
    df["pred_class_count"] = (
        df[["pred_axon", "pred_basal", "pred_apical"]].fillna(0.0) > 0.0
    ).sum(axis=1)
    df["max_pred_frac"] = fracs.max(axis=1)
    df["pred_apical_zero"] = (df["pred_apical"].fillna(0.0) == 0.0).astype(int)
    df["pred_axon_zero"] = (df["pred_axon"].fillna(0.0) == 0.0).astype(int)
    df["single_class_pred"] = (df["pred_class_count"] == 1).astype(int)
    df["log_n_nodes"] = np.log1p(df["n_nodes"].fillna(0.0))
    df["stage1_uncertainty"] = 1.0 - df["stage1_conf"]
    df["stage1_is_pyramidal"] = (df["stage1_pred"] == "pyramidal").astype(int)
    df["pyr_no_apical"] = (
        (df["stage1_pred"] == "pyramidal") & (df["pred_apical"].fillna(0.0) == 0.0)
    ).astype(int)
    df["int_has_apical"] = (
        (df["stage1_pred"] == "interneuron") & (df["pred_apical"].fillna(0.0) > 0.0)
    ).astype(int)
    df["seed_pred_disagree"] = (df["seed42_pred"] != df["seed789_pred"]).astype(int)
    df["seed_conf_min"] = df[["seed42_conf", "seed789_conf"]].min(axis=1)
    df["seed_conf_max"] = df[["seed42_conf", "seed789_conf"]].max(axis=1)
    df["seed_conf_delta"] = (df["seed42_conf"] - df["seed789_conf"]).abs()

    forbidden = GT_OR_LABEL_COLUMNS & set(df.columns)
    if forbidden:
        df = df.drop(columns=list(forbidden), errors="ignore")
    return df


def _load_bundle(path: Path) -> dict[str, Any]:
    key = str(path.resolve())
    if key not in _FLAG_CACHE:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _FLAG_CACHE[key] = joblib.load(path)
    return _FLAG_CACHE[key]


def _selected_threshold(bundle: dict[str, Any], strictness: float) -> dict[str, Any]:
    strictness = min(1.0, max(0.0, float(strictness)))
    recall_thresholds = list(bundle.get("validation_recall_thresholds", []) or [])
    usable = [t for t in recall_thresholds if math.isfinite(float(t.get("score_threshold", math.inf)))]
    if usable:
        target = 0.50 + strictness * 0.45
        chosen = min(usable, key=lambda t: abs(float(t.get("target_recall", 0.0)) - target))
        return {
            "kind": "target_recall",
            "target": float(chosen.get("target_recall", target)),
            "threshold": float(chosen["score_threshold"]),
            "validation_precision": chosen.get("validation_precision"),
            "validation_recall": chosen.get("validation_recall"),
        }

    rank_thresholds = list(bundle.get("validation_rank_thresholds", []) or [])
    usable = [t for t in rank_thresholds if math.isfinite(float(t.get("rank_score_threshold", math.inf)))]
    if usable:
        target_reject_rate = 0.005 + strictness * 0.245
        chosen = min(usable, key=lambda t: abs(float(t.get("reject_rate", 0.0)) - target_reject_rate))
        return {
            "kind": "reject_rate",
            "target": float(chosen.get("reject_rate", target_reject_rate)),
            "threshold": float(chosen["rank_score_threshold"]),
            "validation_precision": None,
            "validation_recall": None,
        }

    return {
        "kind": "prob_bad",
        "target": 0.5,
        "threshold": 0.5,
        "validation_precision": None,
        "validation_recall": None,
    }


def build_feature_row(
    *,
    file_name: str,
    nodes: list[SWCNode],
    labels: list[int],
    confidences: list[float],
    stage1_cell_type: str,
    stage1_confidence: float,
    base_labels: list[int] | None = None,
    base_confidences: list[float] | None = None,
) -> dict[str, Any]:
    counts = Counter(int(x) for x in labels)
    row: dict[str, Any] = {
        "file": file_name,
        "n_nodes": len(nodes),
        "stage1_pred": stage1_cell_type,
        "stage1_conf": float(stage1_confidence),
        "n_components": _n_components(nodes),
        "pred_axon": counts.get(2, 0),
        "pred_basal": counts.get(3, 0),
        "pred_apical": counts.get(4, 0),
        "source": _source_from_name(file_name),
        "seed42_pred": stage1_cell_type,
        "seed42_conf": float(stage1_confidence),
        "seed789_pred": stage1_cell_type,
        "seed789_conf": float(stage1_confidence),
        "confidence_features_missing": 0,
        "held_out_F1": np.nan,
        "n_nodes_conf": len(nodes),
        "stage1_pred_conf_run": stage1_cell_type,
        "stage1_conf_conf_run": float(stage1_confidence),
        "pred_axon_conf_run": counts.get(2, 0),
        "pred_basal_conf_run": counts.get(3, 0),
        "pred_apical_conf_run": counts.get(4, 0),
        "node_label_disagree_frac": 0.0,
        "node_conf_abs_delta_mean": 0.0,
    }
    row.update(_confidence_summary(labels, confidences))
    row.update(_branch_summary(nodes, labels, confidences, stage1_cell_type, stage1_confidence))
    row.update(_branch3_disagreement_features(labels, confidences, base_labels, base_confidences))
    row.update(_predicted_geometry(nodes, labels))
    return row


def score_flag(
    *,
    flag_model_path: Path,
    feature_row: dict[str, Any],
    cell_type_for_filter: str,
    strictness: float,
) -> dict[str, Any]:
    bundle = _load_bundle(flag_model_path)
    required_numeric = [str(c) for c in bundle.get("numeric_features", [])]
    unsupported = [c for c in required_numeric if c.startswith("xmodel_")]
    if unsupported:
        raise RuntimeError(
            "Selected flag model requires multi-v12 xmodel features that are "
            "not enabled in this SWC-Studio deployment."
        )

    feature_df = _engineer_features(pd.DataFrame([feature_row]))
    missing_baseline = [
        c for c in required_numeric
        if c.startswith("baseline_") and c not in feature_df.columns
    ]
    if missing_baseline:
        raise RuntimeError(
            "Selected flag model requires baseline-disagreement features, "
            "but they were not computed for this run."
        )
    for col in required_numeric:
        if col not in feature_df.columns:
            feature_df[col] = np.nan
    for col in [str(c) for c in bundle.get("categorical_features", [])]:
        if col not in feature_df.columns:
            feature_df[col] = ""

    rank_model = bundle["rank_model"]
    calibrated_model = bundle["calibrated_model"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rank_score = float(rank_model.predict_proba(feature_df)[:, 1][0])
        prob_bad = float(calibrated_model.predict_proba(feature_df)[:, 1][0])

    threshold = _selected_threshold(bundle, strictness)
    cell_type_filter = str(bundle.get("cell_type_filter") or "all")
    eligible = cell_type_filter == "all" or cell_type_for_filter == cell_type_filter
    flagged = bool(eligible and rank_score >= float(threshold["threshold"]))

    return {
        "enabled": True,
        "model_path": str(flag_model_path),
        "target_threshold": bundle.get("target_threshold", 0.6),
        "cell_type_filter": cell_type_filter,
        "eligible_by_cell_type": eligible,
        "cell_type_used": cell_type_for_filter,
        "rank_score": rank_score,
        "prob_bad": prob_bad,
        "strictness": float(strictness),
        "threshold": threshold,
        "flagged": flagged,
        "selected_model": bundle.get("selected_model_name"),
        "selected_feature_set": bundle.get("selected_feature_set"),
        "selected_feature_mode": bundle.get("feature_mode") or (
            "baseline" if any(c.startswith("baseline_") for c in required_numeric) else "compact"
        ),
        "n_baseline_features": sum(c.startswith("baseline_") for c in required_numeric),
    }
