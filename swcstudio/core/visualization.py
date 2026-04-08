"""Core visualization payload helpers."""

from __future__ import annotations

from typing import Any

import numpy as np

from swcstudio.core.swc_io import parse_swc_text_preserve_tokens


def _bbox(df) -> dict[str, list[float]]:
    if df.empty:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}
    mins = [float(df[c].min()) for c in ("x", "y", "z")]
    maxs = [float(df[c].max()) for c in ("x", "y", "z")]
    return {"min": mins, "max": maxs}


def build_mesh_payload_from_text(swc_text: str, config: dict[str, Any]) -> dict[str, Any]:
    """Build reusable mesh-related summary payload from SWC text."""
    df = parse_swc_text_preserve_tokens(swc_text)
    if df.empty:
        return {
            "nodes": 0,
            "segments": 0,
            "bbox": {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]},
            "mean_radius": 0.0,
            "edges": [],
        }

    id_to_idx = {int(df.iloc[i]["id"]): i for i in range(len(df))}
    edges: list[tuple[int, int]] = []
    for i in range(len(df)):
        pid = int(df.iloc[i]["parent"])
        if pid == -1:
            continue
        pidx = id_to_idx.get(pid)
        if pidx is None:
            continue
        edges.append((pidx, i))

    include_edges = bool(config.get("output", {}).get("include_edges", False))
    payload = {
        "nodes": int(len(df)),
        "segments": int(len(edges)),
        "bbox": _bbox(df),
        "mean_radius": float(np.nanmean(df["radius"].to_numpy(dtype=float))),
    }
    if include_edges:
        payload["edges"] = edges
    return payload
