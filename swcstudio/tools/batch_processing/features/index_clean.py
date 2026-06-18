"""Batch index clean feature shared by GUI, CLI, and Python API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swcstudio.core.config import load_feature_config, merge_config
from swcstudio.core.provenance import OpKind, run_tracked_batch
from swcstudio.tools.validation.features.index_clean import index_clean_text
from swcstudio.plugins.registry import register_builtin_method, resolve_method

TOOL = "batch_processing"
FEATURE = "index_clean"
FEATURE_KEY = f"{TOOL}.{FEATURE}"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "method": "default",
    "output": {"suffix": "_index_clean", "folder_suffix": "_index_clean"},
}


def _builtin_run(folder: str, config: dict[str, Any]) -> dict[str, Any]:
    def _transform(_path: Path, text: str) -> dict[str, Any]:
        return index_clean_text(text, config_overrides=config)

    return run_tracked_batch(
        folder,
        kind=OpKind.INDEX_CLEAN,
        transform=_transform,
        params_for=lambda _path, result: {
            "original_node_count": int(result.get("original_node_count", 0)),
            "new_node_count": int(result.get("new_node_count", 0)),
            "remapped_id_count": int(result.get("remapped_id_count", 0)),
        },
        summary_for=lambda path, result: (
            f"{path.name}: {int(result.get('original_node_count', 0))} nodes -> "
            f"{int(result.get('new_node_count', 0))} nodes, "
            f"remapped IDs: {int(result.get('remapped_id_count', 0))}"
        ),
        message="GUI batch index clean",
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
