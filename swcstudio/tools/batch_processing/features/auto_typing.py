"""Auto-typing feature for the Batch Processing tool.

Thin wrapper around :mod:`swcstudio.core.auto_typing`. The engine itself
is the v9 ML pipeline and has no alternative backends; this module
exists to register the feature with the plugin system and to expose the
config plumbing the GUI / CLI need.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

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
    )


register_builtin_method(FEATURE_KEY, "default", _builtin_run)


def get_config() -> dict[str, Any]:
    return _get_engine_config()


def _options_from_config(cfg: dict[str, Any]) -> BatchOptions:
    _ = cfg
    return BatchOptions(
        soma=True,
        axon=True,
        apic=False,
        basal=True,
        rad=False,
        zip_output=False,
    )


def run_folder(
    folder: str,
    *,
    options: BatchOptions | None = None,
    config_overrides: dict | None = None,
):
    cfg = merge_config(get_config(), config_overrides)
    opts = options if options is not None else _options_from_config(cfg)
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
