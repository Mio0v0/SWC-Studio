"""Batch simplification feature shared by GUI, CLI, and Python API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from swcstudio.core.config import load_feature_config, merge_config
from swcstudio.core.provenance import (
    OpKind,
    config_params,
    run_tracked_batch,
)
from swcstudio.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swcstudio.plugins.registry import register_builtin_method, resolve_method
from swcstudio.tools.morphology_editing.features.simplification import (
    DEFAULT_CONFIG as _SIMPLIFY_DEFAULT_CFG,
    simplify_dataframe,
)

TOOL = "batch_processing"
FEATURE = "simplification"
FEATURE_KEY = f"{TOOL}.{FEATURE}"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "method": "default",
    "simplification": dict(_SIMPLIFY_DEFAULT_CFG),
    "output": {"suffix": "_simplified", "folder_suffix": "_simplified"},
}


def _builtin_run(folder: str, config: dict[str, Any]) -> dict[str, Any]:
    simplify_cfg = dict(config.get("simplification", {}))

    def _transform(_path: Path, text: str) -> dict[str, Any]:
        df = parse_swc_text_preserve_tokens(text)
        result = simplify_dataframe(df, config_overrides=simplify_cfg)
        out_df = result.get("dataframe")
        if not isinstance(out_df, pd.DataFrame) or out_df.empty:
            raise ValueError("simplification produced empty output")
        result["bytes"] = write_swc_to_bytes_preserve_tokens(out_df)
        return result

    return run_tracked_batch(
        folder,
        kind=OpKind.SIMPLIFICATION,
        transform=_transform,
        params_for=lambda _path, result: {
            **config_params(None, dict(result.get("config_used", config))),
            "original_node_count": int(result.get("original_node_count", 0)),
            "new_node_count": int(result.get("new_node_count", 0)),
            "reduction_percent": float(result.get("reduction_percent", 0.0)),
        },
        summary_for=lambda path, result: (
            f"{path.name}: {int(result.get('original_node_count', 0))} -> "
            f"{int(result.get('new_node_count', 0))} nodes "
            f"({float(result.get('reduction_percent', 0.0)):.2f}% reduction)"
        ),
        message="GUI batch simplification",
    )


register_builtin_method(FEATURE_KEY, "default", _builtin_run)


def get_config() -> dict[str, Any]:
    loaded = load_feature_config(TOOL, FEATURE, default=DEFAULT_CONFIG)
    return merge_config(DEFAULT_CONFIG, loaded)


def run_folder(folder: str, *, config_overrides: dict | None = None) -> dict[str, Any]:
    cfg = merge_config(get_config(), config_overrides)
    method = str(cfg.get("method", "default"))
    fn = resolve_method(FEATURE_KEY, method)
    return fn(folder, cfg)
