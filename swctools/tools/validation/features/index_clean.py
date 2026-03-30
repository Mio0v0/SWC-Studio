"""Single-file index clean feature shared by GUI, CLI, and Python API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swctools.core.config import load_feature_config, merge_config
from swctools.core.geometry_editing import reindex_dataframe_with_map
from swctools.core.reporting import write_text_report
from swctools.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swctools.plugins.registry import register_builtin_method, resolve_method

TOOL = "validation"
FEATURE = "index_clean"
FEATURE_KEY = f"{TOOL}.{FEATURE}"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "method": "default",
    "output": {"suffix": "_index_clean"},
}


def _builtin_index_clean(swc_text: str, config: dict[str, Any]) -> dict[str, Any]:
    df = parse_swc_text_preserve_tokens(swc_text)
    clean_df, id_map = reindex_dataframe_with_map(df)
    changed = sum(1 for old_id, new_id in dict(id_map).items() if int(old_id) != int(new_id))
    return {
        "dataframe": clean_df,
        "bytes": write_swc_to_bytes_preserve_tokens(clean_df),
        "id_map": dict(id_map),
        "original_node_count": int(len(df)),
        "new_node_count": int(len(clean_df)),
        "remapped_id_count": int(changed),
    }


register_builtin_method(FEATURE_KEY, "default", _builtin_index_clean)


def get_config() -> dict[str, Any]:
    loaded = load_feature_config(TOOL, FEATURE, default=DEFAULT_CONFIG)
    return merge_config(DEFAULT_CONFIG, loaded)


def index_clean_text(swc_text: str, *, config_overrides: dict | None = None) -> dict[str, Any]:
    cfg = merge_config(get_config(), config_overrides)
    method = str(cfg.get("method", "default"))
    fn = resolve_method(FEATURE_KEY, method)
    out = fn(swc_text, cfg)
    if not isinstance(out, dict) or "dataframe" not in out or "bytes" not in out:
        raise TypeError("validation index clean method must return dict with 'dataframe' and 'bytes'")
    out["config_used"] = cfg
    return out


def index_clean_file(
    path: str,
    *,
    out_path: str | None = None,
    write_output: bool = False,
    config_overrides: dict | None = None,
) -> dict[str, Any]:
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(path)
    text = fp.read_text(encoding="utf-8", errors="ignore")
    out = index_clean_text(text, config_overrides=config_overrides)
    cfg = dict(out.get("config_used", {}))
    suffix = str(cfg.get("output", {}).get("suffix", "_index_clean"))

    output_path: Path | None = None
    if write_output:
        output_path = Path(out_path) if out_path else fp.with_name(f"{fp.stem}{suffix}{fp.suffix}")
        output_path.write_bytes(out["bytes"])

    lines = [
        "Validation Index Clean Report",
        "-----------------------------",
        f"Input file: {fp}",
        f"Output file: {output_path if output_path else '(not written)'}",
        f"Original node count: {int(out.get('original_node_count', 0))}",
        f"New node count: {int(out.get('new_node_count', 0))}",
        f"Remapped ID count: {int(out.get('remapped_id_count', 0))}",
    ]
    report_path = write_text_report(fp.with_name(f"{fp.stem}_index_clean_report.txt"), "\n".join(lines) + "\n")
    out["input_path"] = str(fp)
    out["output_path"] = str(output_path) if output_path else None
    out["log_path"] = report_path
    return out
