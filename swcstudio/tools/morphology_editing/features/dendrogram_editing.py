"""Dendrogram editing backend utilities.

Provides data-level operations used by interactive dendrogram editors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from swcstudio.core.config import load_feature_config, merge_config
from swcstudio.core.subtree_editing import reassign_subtree_types_dataframe
from swcstudio.core.reporting import operation_output_path_for_file, resolve_requested_output_path_for_file, timestamp_slug
from swcstudio.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swcstudio.plugins.registry import register_builtin_method, resolve_method

TOOL = "morphology_editing"
FEATURE = "dendrogram_editing"
FEATURE_KEY = f"{TOOL}.{FEATURE}"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "method": "default",
    "rules": {
        "include_selected_node": True,
        "preserve_soma_type": True,
    },
}

def _builtin_reassign_subtree(
    df: pd.DataFrame,
    node_id: int,
    new_type: int,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, int, list[int]]:
    return reassign_subtree_types_dataframe(df, node_id, new_type, config)


register_builtin_method(FEATURE_KEY, "default", _builtin_reassign_subtree)


def get_config() -> dict[str, Any]:
    loaded = load_feature_config(TOOL, FEATURE, default=DEFAULT_CONFIG)
    return merge_config(DEFAULT_CONFIG, loaded)


def reassign_subtree_types(
    swc_text: str,
    *,
    node_id: int,
    new_type: int,
    config_overrides: dict | None = None,
) -> dict[str, Any]:
    cfg = merge_config(get_config(), config_overrides)

    df = parse_swc_text_preserve_tokens(swc_text)
    method = str(cfg.get("method", "default"))
    fn = resolve_method(FEATURE_KEY, method)
    out_df, changed, changed_ids = fn(df, int(node_id), int(new_type), cfg)

    return {
        "changes": int(changed),
        "changed_node_ids": changed_ids,
        "dataframe": out_df,
        "bytes": write_swc_to_bytes_preserve_tokens(out_df),
    }


def reassign_subtree_types_in_file(
    path: str,
    *,
    node_id: int,
    new_type: int,
    out_path: str | None = None,
    write_output: bool = False,
    config_overrides: dict | None = None,
) -> dict[str, Any]:
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(path)

    text = fp.read_text(encoding="utf-8", errors="ignore")
    out = reassign_subtree_types(
        text,
        node_id=node_id,
        new_type=new_type,
        config_overrides=config_overrides,
    )

    output_path: Path | None = None
    run_timestamp = timestamp_slug()
    if write_output:
        output_path = (
            resolve_requested_output_path_for_file(fp, out_path)
            if out_path
            else operation_output_path_for_file(fp, "morphology_dendrogram_edit", timestamp=run_timestamp)
        )
        output_path.write_bytes(out["bytes"])

    out["input_path"] = str(fp)
    out["output_path"] = str(output_path) if output_path else None
    return out
