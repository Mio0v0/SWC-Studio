"""Manual single-node radius editing shared by GUI, CLI, and Python API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swcstudio.core.config import load_feature_config, merge_config
from swcstudio.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swcstudio.plugins.registry import register_builtin_method, resolve_method

TOOL = "morphology_editing"
FEATURE = "manual_radii"
FEATURE_KEY = f"{TOOL}.{FEATURE}"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "method": "default",
    "output": {"suffix": "_radius_edited"},
}


def _builtin_set_radius(swc_text: str, node_id: int, radius: float, config: dict[str, Any]) -> dict[str, Any]:
    _ = config
    df = parse_swc_text_preserve_tokens(swc_text)
    mask = df["id"].astype(int) == int(node_id)
    if not bool(mask.any()):
        raise ValueError(f"Node {int(node_id)} not found.")
    old_radius = float(df.loc[mask, "radius"].iloc[0])
    df.loc[mask, "radius"] = float(radius)
    return {
        "dataframe": df,
        "bytes": write_swc_to_bytes_preserve_tokens(df),
        "node_id": int(node_id),
        "old_radius": old_radius,
        "new_radius": float(radius),
    }


register_builtin_method(FEATURE_KEY, "default", _builtin_set_radius)


def get_config() -> dict[str, Any]:
    loaded = load_feature_config(TOOL, FEATURE, default=DEFAULT_CONFIG)
    return merge_config(DEFAULT_CONFIG, loaded)


def set_node_radius_text(
    swc_text: str,
    *,
    node_id: int,
    radius: float,
    config_overrides: dict | None = None,
) -> dict[str, Any]:
    cfg = merge_config(get_config(), config_overrides)
    method = str(cfg.get("method", "default"))
    fn = resolve_method(FEATURE_KEY, method)
    out = fn(swc_text, int(node_id), float(radius), cfg)
    if not isinstance(out, dict) or "bytes" not in out:
        raise TypeError("manual radii method must return dict with 'bytes'")
    out["config_used"] = cfg
    return out


def set_node_radius_file(
    path: str,
    *,
    node_id: int,
    radius: float,
    out_path: str | None = None,
    write_output: bool = False,
    config_overrides: dict | None = None,
) -> dict[str, Any]:
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(path)
    text = fp.read_text(encoding="utf-8", errors="ignore")
    out = set_node_radius_text(text, node_id=node_id, radius=radius, config_overrides=config_overrides)
    cfg = dict(out.get("config_used", {}))
    suffix = str(cfg.get("output", {}).get("suffix", "_radius_edited"))

    output_path: Path | None = None
    if write_output:
        output_path = Path(out_path) if out_path else fp.with_name(f"{fp.stem}{suffix}{fp.suffix}")
        output_path.write_bytes(out["bytes"])

    out["input_path"] = str(fp)
    out["output_path"] = str(output_path) if output_path else None
    return out
