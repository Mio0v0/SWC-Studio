"""Manual single-node type editing shared by GUI, CLI, and Python API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swcstudio.core.config import load_feature_config, merge_config
from swcstudio.core.reporting import operation_output_path_for_file, resolve_requested_output_path_for_file, timestamp_slug
from swcstudio.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swcstudio.plugins.registry import register_builtin_method, resolve_method

TOOL = "morphology_editing"
FEATURE = "manual_label"
FEATURE_KEY = f"{TOOL}.{FEATURE}"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "method": "default",
}


def _builtin_set_type(swc_text: str, node_id: int, new_type: int, config: dict[str, Any]) -> dict[str, Any]:
    _ = config
    df = parse_swc_text_preserve_tokens(swc_text)
    mask = df["id"].astype(int) == int(node_id)
    if not bool(mask.any()):
        raise ValueError(f"Node {int(node_id)} not found.")
    old_type = int(df.loc[mask, "type"].iloc[0])
    df.loc[mask, "type"] = int(new_type)
    return {
        "dataframe": df,
        "bytes": write_swc_to_bytes_preserve_tokens(df),
        "node_id": int(node_id),
        "old_type": old_type,
        "new_type": int(new_type),
    }


register_builtin_method(FEATURE_KEY, "default", _builtin_set_type)


def get_config() -> dict[str, Any]:
    loaded = load_feature_config(TOOL, FEATURE, default=DEFAULT_CONFIG)
    return merge_config(DEFAULT_CONFIG, loaded)


def set_node_type_text(
    swc_text: str,
    *,
    node_id: int,
    new_type: int,
    config_overrides: dict | None = None,
) -> dict[str, Any]:
    cfg = merge_config(get_config(), config_overrides)
    method = str(cfg.get("method", "default"))
    fn = resolve_method(FEATURE_KEY, method)
    out = fn(swc_text, int(node_id), int(new_type), cfg)
    if not isinstance(out, dict) or "bytes" not in out:
        raise TypeError("manual label method must return dict with 'bytes'")
    out["config_used"] = cfg
    return out


def set_node_type_file(
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
    out = set_node_type_text(text, node_id=node_id, new_type=new_type, config_overrides=config_overrides)

    output_path: Path | None = None
    run_timestamp = timestamp_slug()
    if write_output:
        output_path = (
            resolve_requested_output_path_for_file(fp, out_path)
            if out_path
            else operation_output_path_for_file(fp, "morphology_set_type", timestamp=run_timestamp)
        )
        output_path.write_bytes(out["bytes"])

    out["input_path"] = str(fp)
    out["output_path"] = str(output_path) if output_path else None
    return out
