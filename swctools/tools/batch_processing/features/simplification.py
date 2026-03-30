"""Batch simplification feature shared by GUI, CLI, and Python API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from swctools.core.config import load_feature_config, merge_config
from swctools.core.reporting import write_text_report
from swctools.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swctools.plugins.registry import register_builtin_method, resolve_method
from swctools.tools.morphology_editing.features.simplification import (
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


def _write_batch_report(out_dir: Path, name: str, lines: list[str]) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / name
    return write_text_report(report_path, "\n".join(lines).rstrip() + "\n")


def _builtin_run(folder: str, config: dict[str, Any]) -> dict[str, Any]:
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        raise NotADirectoryError(folder)

    swc_files = sorted(
        [p for p in folder_path.iterdir() if p.is_file() and p.suffix.lower() == ".swc"],
        key=lambda p: p.name.lower(),
    )
    if not swc_files:
        raise FileNotFoundError(f"No .swc files found in: {folder}")

    output_cfg = dict(config.get("output", {}))
    out_dir = folder_path / f"{folder_path.name}{str(output_cfg.get('folder_suffix', '_simplified'))}"
    out_dir.mkdir(parents=True, exist_ok=True)
    simplify_cfg = dict(config.get("simplification", {}))
    suffix = str(output_cfg.get("suffix", "_simplified"))

    processed = 0
    failures: list[str] = []
    per_file: list[str] = []

    for swc_path in swc_files:
        try:
            text = swc_path.read_text(encoding="utf-8", errors="ignore")
            df = parse_swc_text_preserve_tokens(text)
            result = simplify_dataframe(df, config_overrides=simplify_cfg)
            out_df = result.get("dataframe")
            if not isinstance(out_df, pd.DataFrame) or out_df.empty:
                raise ValueError("simplification produced empty output")
            out_path = out_dir / f"{swc_path.stem}{suffix}{swc_path.suffix}"
            out_path.write_bytes(write_swc_to_bytes_preserve_tokens(out_df))
            processed += 1
            per_file.append(
                f"{swc_path.name}: {int(result.get('original_node_count', 0))} -> "
                f"{int(result.get('new_node_count', 0))} nodes "
                f"({float(result.get('reduction_percent', 0.0)):.2f}%)"
            )
        except Exception as e:  # noqa: BLE001
            failures.append(f"{swc_path.name}: {e}")

    lines = [
        "Batch Simplification Report",
        "---------------------------",
        f"Folder: {folder_path}",
        f"Output folder: {out_dir}",
        f"Detected SWC files: {len(swc_files)}",
        f"Processed: {processed}",
        f"Failed: {len(failures)}",
        "",
        "Per-file summary:",
        *per_file[:100],
    ]
    if len(per_file) > 100:
        lines.append(f"... ({len(per_file) - 100} more)")
    if failures:
        lines.extend(["", "Errors:", *failures[:50]])
        if len(failures) > 50:
            lines.append(f"... ({len(failures) - 50} more)")

    report_path = _write_batch_report(out_dir, "batch_simplification_report.txt", lines)
    return {
        "folder": str(folder_path),
        "out_dir": str(out_dir),
        "files_total": len(swc_files),
        "files_processed": processed,
        "files_failed": len(failures),
        "per_file": per_file,
        "failures": failures,
        "log_path": report_path,
    }


register_builtin_method(FEATURE_KEY, "default", _builtin_run)


def get_config() -> dict[str, Any]:
    loaded = load_feature_config(TOOL, FEATURE, default=DEFAULT_CONFIG)
    return merge_config(DEFAULT_CONFIG, loaded)


def run_folder(folder: str, *, config_overrides: dict | None = None) -> dict[str, Any]:
    cfg = merge_config(get_config(), config_overrides)
    method = str(cfg.get("method", "default"))
    fn = resolve_method(FEATURE_KEY, method)
    return fn(folder, cfg)
