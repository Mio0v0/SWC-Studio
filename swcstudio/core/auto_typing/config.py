"""Persisted user-facing configuration for the auto-typing feature.

The auto-typing engine itself is the v12 QC-label-flag pipeline. The
runtime knobs end users edit are model directory overrides, optional
cell-type override, and flag scoring strictness. They live in the same
JSON config the Batch Processing tool already persists, so the GUI / CLI
continue to read and write a single file.
"""
from __future__ import annotations

from typing import Any

from swcstudio.core.config import load_feature_config, merge_config, save_feature_config

TOOL = "batch_processing"
FEATURE = "auto_typing"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "model_dir": "",
    "use_subtree_stage2": True,
    "cell_type": "unknown",
    "flag_enabled": True,
    "flag_strictness": 0.5,
    "flag_feature_mode": "compact",
}

_CACHED: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    """Return the merged auto-typing config (defaults + persisted user
    overrides). Cached for fast repeat access in batch mode."""
    global _CACHED
    if _CACHED is None:
        _CACHED = merge_config(DEFAULT_CONFIG, load_feature_config(TOOL, FEATURE, default={}))
    return dict(_CACHED)


def save_config(cfg: dict[str, Any]) -> None:
    """Save user-edited auto-typing config to disk."""
    global _CACHED
    save_feature_config(TOOL, FEATURE, cfg)
    _CACHED = merge_config(DEFAULT_CONFIG, cfg)


def reset_cache() -> None:
    """Drop the in-memory config cache so the next ``get_config`` call
    reloads from disk. Used by tests."""
    global _CACHED
    _CACHED = None


__all__ = ["DEFAULT_CONFIG", "TOOL", "FEATURE", "get_config", "save_config", "reset_cache"]
