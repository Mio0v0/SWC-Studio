"""Persistent custom SWC type metadata."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DEFAULT_CUSTOM_COLOR = "#ff7f0e"
_DEFAULT_CUSTOM_TYPE_PALETTE = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
]
_CACHE: dict[int, dict[str, str]] | None = None


def custom_type_registry_path() -> Path:
    override = os.environ.get("SWCTOOLS_CUSTOM_TYPES_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".swc_studio" / "custom_types.json"


def default_custom_color_for_type(type_id: int) -> str:
    try:
        type_id = int(type_id)
    except Exception:
        return _DEFAULT_CUSTOM_COLOR
    if type_id < 5:
        return _DEFAULT_CUSTOM_COLOR
    offset = (type_id - 5) % len(_DEFAULT_CUSTOM_TYPE_PALETTE)
    return _DEFAULT_CUSTOM_TYPE_PALETTE[offset]


def _normalize_color(value: str, *, fallback_type_id: int | None = None) -> str:
    text = str(value or "").strip()
    if _HEX_RE.match(text):
        return text.lower()
    if fallback_type_id is not None:
        return default_custom_color_for_type(int(fallback_type_id))
    return _DEFAULT_CUSTOM_COLOR


def load_custom_type_definitions(*, force: bool = False) -> dict[int, dict[str, str]]:
    global _CACHE
    if _CACHE is not None and not force:
        return {int(k): dict(v) for k, v in _CACHE.items()}

    path = custom_type_registry_path()
    out: dict[int, dict[str, str]] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw_types = dict(payload.get("types", {}) or {})
            for raw_key, raw_value in raw_types.items():
                try:
                    type_id = int(raw_key)
                except Exception:
                    continue
                if type_id < 5 or not isinstance(raw_value, dict):
                    continue
                name = str(raw_value.get("name", "")).strip()
                color = _normalize_color(str(raw_value.get("color", "")).strip(), fallback_type_id=type_id)
                notes = str(raw_value.get("notes", "")).strip()
                if not name:
                    continue
                out[type_id] = {"name": name, "color": color, "notes": notes}
        except Exception:
            out = {}

    _CACHE = out
    return {int(k): dict(v) for k, v in out.items()}


def save_custom_type_definitions(definitions: dict[int, dict[str, str]]) -> Path:
    global _CACHE
    cleaned: dict[str, dict[str, str]] = {}
    for raw_type_id, raw_value in dict(definitions or {}).items():
        try:
            type_id = int(raw_type_id)
        except Exception:
            continue
        if type_id < 5 or not isinstance(raw_value, dict):
            continue
        name = str(raw_value.get("name", "")).strip()
        if not name:
            continue
        notes = str(raw_value.get("notes", "")).strip()
        cleaned[str(type_id)] = {
            "name": name,
            "color": _normalize_color(str(raw_value.get("color", "")).strip(), fallback_type_id=type_id),
            "notes": notes,
        }

    path = custom_type_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"types": cleaned}
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    _CACHE = {int(k): dict(v) for k, v in cleaned.items()}
    return path


def get_custom_type_definition(type_id: int) -> dict[str, str] | None:
    type_id = int(type_id)
    if type_id < 5:
        return None
    return load_custom_type_definitions().get(type_id)


def set_custom_type_definition(type_id: int, *, name: str, color: str, notes: str = "") -> Path:
    type_id = int(type_id)
    definitions = load_custom_type_definitions()
    definitions[type_id] = {
        "name": str(name).strip(),
        "color": _normalize_color(color, fallback_type_id=type_id),
        "notes": str(notes).strip(),
    }
    return save_custom_type_definitions(definitions)
