"""Auto-typing feature for the Batch Processing tool.

Thin wrapper around :mod:`swcstudio.core.auto_typing`. The engine itself
is the v12 QC-label-flag pipeline and has no alternative backends; this
module exists to register the feature with the plugin system and to
expose the model directory, cell-type override, and flag strictness
plumbing the GUI / CLI need.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from swcstudio.core.auto_typing import (
    BatchOptions,
    DEFAULT_CONFIG,
    get_config as _get_engine_config,
    run_batch,
)
from swcstudio.core.config import merge_config
from swcstudio.plugins.registry import register_builtin_method

TOOL = "batch_processing"
FEATURE = "auto_typing"
FEATURE_KEY = f"{TOOL}.{FEATURE}"


def _builtin_run(folder: str, options: BatchOptions, config: dict[str, Any]):
    return run_batch(
        folder,
        options,
        model_dir=(config.get("model_dir") or None),
        use_subtree_stage2=bool(config.get("use_subtree_stage2", True)),
        progress_callback=config.get("__progress_callback"),
    )


register_builtin_method(FEATURE_KEY, "default", _builtin_run)


def get_config() -> dict[str, Any]:
    return _get_engine_config()


def _options_from_config(cfg: dict[str, Any]) -> BatchOptions:
    return BatchOptions(
        soma=True,
        axon=True,
        apic=True,
        basal=True,
        rad=False,
        zip_output=False,
        cell_type=(cfg.get("cell_type") or "unknown"),
        flag_enabled=bool(cfg.get("flag_enabled", True)),
        flag_strictness=float(cfg.get("flag_strictness", 0.5)),
        flag_feature_mode="compact",
    )


def run_folder(
    folder: str,
    *,
    options: BatchOptions | None = None,
    config_overrides: dict | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
):
    cfg = merge_config(get_config(), config_overrides)
    opts = options if options is not None else _options_from_config(cfg)
    if progress_callback is not None:
        # Stash the callback in the config dict so the registered method
        # can pick it up without breaking the (folder, options, config)
        # plugin signature.
        cfg = dict(cfg)
        cfg["__progress_callback"] = progress_callback
    return _builtin_run(folder, opts, cfg)


def options_to_dict(opts: BatchOptions) -> dict[str, Any]:
    return asdict(opts)


__all__ = [
    "TOOL",
    "FEATURE",
    "FEATURE_KEY",
    "DEFAULT_CONFIG",
    "BatchOptions",
    "get_config",
    "run_folder",
    "options_to_dict",
]
