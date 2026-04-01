"""Single-file auto typing for Validation tool.

Uses the same core rule engine and JSON config as Batch Processing -> Auto Typing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from swcstudio.core.auto_typing import RuleBatchOptions, run_rule_file
from swcstudio.core.config import merge_config
from swcstudio.core.reporting import operation_output_path_for_file, resolve_requested_output_path_for_file, timestamp_slug
from swcstudio.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swcstudio.tools.batch_processing.features.auto_typing import get_config as get_batch_auto_config


def _options_from_config(cfg: dict[str, Any]) -> RuleBatchOptions:
    opts = dict(cfg.get("options", {}))
    return RuleBatchOptions(
        soma=bool(opts.get("soma", True)),
        axon=bool(opts.get("axon", True)),
        apic=bool(opts.get("apic", False)),
        basal=bool(opts.get("basal", True)),
        rad=False,
        zip_output=False,
    )


def run_file(
    file_path: str,
    *,
    options: RuleBatchOptions | None = None,
    config_overrides: dict | None = None,
    output_path: str | None = None,
    write_output: bool = True,
    write_log: bool = True,
):
    cfg = get_batch_auto_config()
    if isinstance(config_overrides, dict) and config_overrides:
        cfg = merge_config(cfg, config_overrides)
    opts = options if options is not None else _options_from_config(cfg)
    return run_rule_file(
        file_path,
        opts,
        output_path=output_path,
        write_output=write_output,
        write_log=write_log,
    )


def result_to_dataframe(result: object) -> pd.DataFrame:
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


def merge_types_only(base_df: pd.DataFrame, labeled_df: pd.DataFrame) -> pd.DataFrame:
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


def auto_label_file(
    file_path: str,
    *,
    options: RuleBatchOptions | None = None,
    config_overrides: dict | None = None,
    output_path: str | None = None,
    write_output: bool = True,
    write_log: bool = False,
) -> dict[str, Any]:
    in_path = Path(file_path)
    if not in_path.exists():
        raise FileNotFoundError(file_path)

    base_df = parse_swc_text_preserve_tokens(in_path.read_text(encoding="utf-8", errors="ignore"))
    result_obj = run_file(
        file_path,
        options=options,
        config_overrides=config_overrides,
        output_path=None,
        write_output=False,
        write_log=write_log,
    )
    labeled_df = result_to_dataframe(result_obj)
    merged_df = merge_types_only(base_df, labeled_df)
    out_bytes = write_swc_to_bytes_preserve_tokens(merged_df)

    out_path: Path | None = None
    run_timestamp = timestamp_slug()
    if write_output:
        out_path = (
            resolve_requested_output_path_for_file(in_path, output_path)
            if output_path
            else operation_output_path_for_file(in_path, "validation_auto_label", timestamp=run_timestamp)
        )
        out_path.write_bytes(out_bytes)

    return {
        "dataframe": merged_df,
        "bytes": out_bytes,
        "input_path": str(in_path),
        "output_path": str(out_path) if out_path is not None else None,
        "nodes_total": int(getattr(result_obj, "nodes_total", 0)),
        "type_changes": int(getattr(result_obj, "type_changes", 0)),
        "radius_changes": 0,
        "out_type_counts": dict(getattr(result_obj, "out_type_counts", {}) or {}),
        "change_details": list(getattr(result_obj, "change_details", []) or []),
        "result_obj": result_obj,
    }
