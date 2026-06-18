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
    BatchResult,
    DEFAULT_CONFIG,
    get_config as _get_engine_config,
)
from swcstudio.core.config import merge_config
from swcstudio.core.provenance import OpKind, config_params, run_tracked_batch
from swcstudio.plugins.registry import register_builtin_method

TOOL = "batch_processing"
FEATURE = "auto_typing"
FEATURE_KEY = f"{TOOL}.{FEATURE}"


def _builtin_run(folder: str, options: BatchOptions, config: dict[str, Any]):
    from swcstudio.tools.validation.features.auto_typing import auto_label_file

    effective_config = {
        key: value
        for key, value in config.items()
        if not str(key).startswith("__")
    }
    totals = {
        "nodes": 0,
        "type_changes": 0,
        "radius_changes": 0,
        "flagged": 0,
    }

    def _transform(path, _text):
        return auto_label_file(
            str(path),
            options=options,
            config_overrides=effective_config,
            output_path=None,
            write_output=False,
            write_log=False,
        )

    def _summary(path, result):
        out_counts = dict(result.get("out_type_counts", {}) or {})
        flag_result = dict(result.get("flag_result", {}) or {})
        totals["nodes"] += int(result.get("nodes_total", 0))
        totals["type_changes"] += int(result.get("type_changes", 0))
        totals["radius_changes"] += int(result.get("radius_changes", 0))
        totals["flagged"] += int(bool(flag_result.get("flagged", False)))
        return (
            f"{path.name}: nodes={int(result.get('nodes_total', 0))}, "
            f"type_changes={int(result.get('type_changes', 0))}, "
            f"radius_changes={int(result.get('radius_changes', 0))}, "
            f"cell_type={result.get('cell_type') or 'unknown'} "
            f"({result.get('cell_type_source') or 'stage1'}), "
            f"flag={bool(flag_result.get('flagged', False))}, "
            "out_types(soma/axon/basal/apic)="
            f"{out_counts.get(1, 0)}/{out_counts.get(2, 0)}/"
            f"{out_counts.get(3, 0)}/{out_counts.get(4, 0)}"
        )

    tracked = run_tracked_batch(
        folder,
        kind=OpKind.AUTO_LABEL,
        transform=_transform,
        params_for=lambda _path, result: {
            **config_params(None, effective_config),
            "options": asdict(options),
            "nodes_total": int(result.get("nodes_total", 0)),
            "type_changes": int(result.get("type_changes", 0)),
            "radius_changes": int(result.get("radius_changes", 0)),
            "cell_type_result": result.get("cell_type"),
            "cell_type_source": result.get("cell_type_source"),
            "stage1_confidence": result.get("stage1_confidence"),
            "flagged": bool(
                dict(result.get("flag_result", {}) or {}).get("flagged", False)
            ),
        },
        summary_for=_summary,
        message="GUI batch auto label",
        progress_callback=config.get("__progress_callback"),
    )
    failures = list(tracked.get("failures", []) or [])
    return BatchResult(
        folder=str(tracked["folder"]),
        out_dir=None,
        zip_path=None,
        files_total=int(tracked["files_total"]),
        files_processed=int(tracked["files_processed"]),
        files_failed=int(tracked["files_failed"]),
        files_qc_failed=sum("QC rejected" in str(item) for item in failures),
        total_nodes=int(totals["nodes"]),
        total_type_changes=int(totals["type_changes"]),
        total_radius_changes=int(totals["radius_changes"]),
        files_flagged=int(totals["flagged"]),
        failures=failures,
        per_file=list(tracked.get("per_file", []) or []),
        log_path=None,
        commits=list(tracked.get("commits", []) or []),
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
