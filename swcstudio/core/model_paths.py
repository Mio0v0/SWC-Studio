"""Resolve where the auto-typing models live on disk.

The auto-typing engine (:mod:`swcstudio.core.auto_typing`) needs three
trained model files:

* ``cell_type_classifier.pkl`` — Stage 1 (whole-cell pyramidal vs interneuron)
* ``branch_classifier.pkl`` — Stage 2 (per-branch / per-subtree multiclass)
* ``gnn_apical_basal.pt`` — optional Stage 2b GraphSAGE GNN

Search order (first existing wins):

1. The directory passed in via the function argument or via the
   ``SWCSTUDIO_MODEL_DIR`` environment variable (highest precedence,
   used for "I trained my own models" workflows).
2. The user data directory:

   * Windows: ``%APPDATA%\\swcstudio\\models``
   * macOS: ``~/Library/Application Support/swcstudio/models``
   * Linux: ``~/.local/share/swcstudio/models``

3. The bundled directory inside the installed package
   (``swcstudio/data/models``). All three model files are shipped
   here so a fresh ``pip install`` produces a fully working engine.

Public API:

* ``user_model_dir()`` — user data dir (creates if missing)
* ``bundled_model_dir()`` — dir inside the installed package
* ``resolve_model_path(name, override=None)`` — full path or ``None``
* ``available_models(override=None)`` — ``dict[name -> Path | None]``

Calling code never hard-codes paths. It calls
``resolve_model_path("gnn_apical_basal.pt")`` and gets either a real
path or ``None`` (in which case the GNN step is skipped).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

# Standard model file names. Custom-trained models keep these names so
# they are picked up automatically.
MODEL_FILES = {
    "stage1": "cell_type_classifier.pkl",
    "stage2": "branch_classifier.pkl",
    "gnn":    "gnn_apical_basal.pt",
}

ENV_VAR = "SWCSTUDIO_MODEL_DIR"


def _user_data_root() -> Path:
    """Per-platform user data directory root."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    # Linux / other unix
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base)
    return Path.home() / ".local" / "share"


def user_model_dir() -> Path:
    """User data directory for swcstudio models. Created on first use."""
    out = _user_data_root() / "swcstudio" / "models"
    out.mkdir(parents=True, exist_ok=True)
    return out


def bundled_model_dir() -> Path:
    """Directory shipped inside the installed swcstudio package."""
    return Path(__file__).resolve().parent.parent / "data" / "models"


def search_dirs(override: str | os.PathLike | None = None) -> list[Path]:
    """Ordered list of directories that may hold model files."""
    out: list[Path] = []
    if override:
        out.append(Path(override))
    env_override = os.environ.get(ENV_VAR)
    if env_override:
        out.append(Path(env_override))
    out.append(user_model_dir())
    out.append(bundled_model_dir())
    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduped: list[Path] = []
    for d in out:
        key = str(d.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)
    return deduped


def resolve_model_path(
    name_or_filename: str,
    *,
    override: str | os.PathLike | None = None,
) -> Path | None:
    """Locate one model file by short name or by literal filename.

    ``name_or_filename`` accepts both ``"stage1"`` and
    ``"cell_type_classifier.pkl"``. Returns the first existing path
    found in :func:`search_dirs`, or ``None``.
    """
    fname = MODEL_FILES.get(name_or_filename, name_or_filename)
    for d in search_dirs(override):
        candidate = d / fname
        if candidate.is_file():
            return candidate
    return None


def available_models(
    override: str | os.PathLike | None = None,
) -> dict[str, Path | None]:
    """Return ``{short_name: Path | None}`` for every standard model."""
    return {key: resolve_model_path(key, override=override) for key in MODEL_FILES}


def diagnostic_search_report(
    override: str | os.PathLike | None = None,
) -> str:
    """Human-readable description of where the resolver looked. Useful in
    error messages when a model cannot be found."""
    lines: list[str] = ["Search order:"]
    for d in search_dirs(override):
        marker = "[EXISTS]" if d.is_dir() else "[MISSING]"
        lines.append(f"  {marker} {d}")
    lines.append("Required files:")
    for short, fname in MODEL_FILES.items():
        found = resolve_model_path(short, override=override)
        marker = f"[FOUND] {found}" if found else "[NOT FOUND]"
        lines.append(f"  {short:<8s} ({fname})  {marker}")
    lines.append(
        f"Override via env var {ENV_VAR}=/path/to/dir or via the "
        f"`--model-dir` CLI flag / GUI selector."
    )
    return "\n".join(lines)
