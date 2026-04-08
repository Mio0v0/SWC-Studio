"""Core subtree relabeling helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _build_children(df: pd.DataFrame) -> tuple[dict[int, int], list[list[int]]]:
    id_to_idx = {int(df.iloc[i]["id"]): i for i in range(len(df))}
    children: list[list[int]] = [[] for _ in range(len(df))]
    for i in range(len(df)):
        pid = int(df.iloc[i]["parent"])
        pidx = id_to_idx.get(pid)
        if pidx is not None:
            children[pidx].append(i)
    return id_to_idx, children


def _collect_subtree(start_idx: int, children: list[list[int]]) -> list[int]:
    out: list[int] = []
    stack = [start_idx]
    seen = set()
    while stack:
        idx = stack.pop()
        if idx in seen:
            continue
        seen.add(idx)
        out.append(idx)
        stack.extend(children[idx])
    return out


def reassign_subtree_types_dataframe(
    df: pd.DataFrame,
    node_id: int,
    new_type: int,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, int, list[int]]:
    """Reassign node types in a selected subtree."""
    id_to_idx, children = _build_children(df)
    start_idx = id_to_idx.get(int(node_id))
    if start_idx is None:
        raise KeyError(f"Node id {node_id} not found")

    rules = config.get("rules", {})
    include_selected = bool(rules.get("include_selected_node", True))
    preserve_soma = bool(rules.get("preserve_soma_type", True))

    target_idx = _collect_subtree(start_idx, children)
    if not include_selected:
        target_idx = [i for i in target_idx if i != start_idx]

    out = df.copy()
    changed = 0
    changed_ids: list[int] = []
    for i in target_idx:
        current_type = int(out.iloc[i]["type"])
        if preserve_soma and current_type == 1:
            continue
        if current_type == int(new_type):
            continue
        out.at[out.index[i], "type"] = int(new_type)
        changed += 1
        changed_ids.append(int(out.iloc[i]["id"]))

    return out, changed, changed_ids
