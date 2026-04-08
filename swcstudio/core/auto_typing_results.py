"""Core transforms for rule-based auto-typing outputs."""

from __future__ import annotations

import pandas as pd


def auto_typing_result_to_dataframe(result: object) -> pd.DataFrame:
    rows = list(getattr(result, "rows", []))
    types = list(getattr(result, "types", []))
    radii = list(getattr(result, "radii", []))
    if not rows:
        return pd.DataFrame(columns=["id", "type", "x", "y", "z", "radius", "parent"])

    data = []
    for i, row in enumerate(rows):
        data.append(
            {
                "id": int(row.get("id", 0)),
                "type": int(types[i] if i < len(types) else row.get("type", 0)),
                "x": float(row.get("x", 0.0)),
                "y": float(row.get("y", 0.0)),
                "z": float(row.get("z", 0.0)),
                "radius": float(radii[i] if i < len(radii) else row.get("radius", 0.0)),
                "parent": int(row.get("parent", -1)),
            }
        )
    return pd.DataFrame(data, columns=["id", "type", "x", "y", "z", "radius", "parent"])


def merge_labeled_types_only(base_df: pd.DataFrame, labeled_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(base_df, pd.DataFrame) or base_df.empty:
        return pd.DataFrame(columns=["id", "type", "x", "y", "z", "radius", "parent"])
    out = base_df.copy()
    if not isinstance(labeled_df, pd.DataFrame) or labeled_df.empty:
        return out
    type_map = {
        int(row["id"]): int(row["type"])
        for _, row in labeled_df.loc[:, ["id", "type"]].iterrows()
    }
    out["type"] = out["id"].astype(int).map(type_map).fillna(out["type"]).astype(int)
    return out
