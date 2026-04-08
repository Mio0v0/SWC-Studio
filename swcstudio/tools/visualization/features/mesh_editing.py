"""Mesh editing feature backend.

This module provides a reusable backend payload that both GUI and CLI can use
for mesh-related operations without duplicating parsing logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swcstudio.core.config import load_feature_config, merge_config
from swcstudio.core.visualization import build_mesh_payload_from_text
from swcstudio.plugins.registry import register_builtin_method, resolve_method

TOOL = "visualization"
FEATURE = "mesh_editing"
FEATURE_KEY = f"{TOOL}.{FEATURE}"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "method": "default",
    "output": {
        "include_edges": False,
    },
}

def _builtin_build_mesh_payload(swc_text: str, config: dict[str, Any]) -> dict[str, Any]:
    return build_mesh_payload_from_text(swc_text, config)


register_builtin_method(FEATURE_KEY, "default", _builtin_build_mesh_payload)


def get_config() -> dict[str, Any]:
    loaded = load_feature_config(TOOL, FEATURE, default=DEFAULT_CONFIG)
    return merge_config(DEFAULT_CONFIG, loaded)


def build_mesh_from_text(swc_text: str, *, config_overrides: dict | None = None) -> dict[str, Any]:
    cfg = merge_config(get_config(), config_overrides)

    method = str(cfg.get("method", "default"))
    fn = resolve_method(FEATURE_KEY, method)
    return fn(swc_text, cfg)


def build_mesh_from_file(path: str, *, config_overrides: dict | None = None) -> dict[str, Any]:
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(path)
    text = fp.read_text(encoding="utf-8", errors="ignore")
    out = build_mesh_from_text(text, config_overrides=config_overrides)
    out["input_path"] = str(fp)
    return out
