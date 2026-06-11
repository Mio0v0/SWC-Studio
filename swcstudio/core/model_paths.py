"""Resolve where the auto-typing models live on disk.

The auto-typing engine (:mod:`swcstudio.core.auto_typing`) is the v12
QC-label-flag path. Its required core model files are:

* ``cell_type_classifier.pkl`` — Stage 1 (whole-cell pyramidal vs interneuron)
* ``branch_classifier.pkl`` — Stage 2 (per-branch / per-subtree multiclass)
* ``gnn_apical_basal.pt`` — Stage 2b GraphSAGE GNN
* ``gnn_branch3_rescue.pt`` — conservative Branch3 rescue head
* ``qc_gate.pkl`` — runtime QC gate

Optional learned flag models add per-cell bad-label flag scoring:

* ``flag_model_pyramidal.joblib``
* ``flag_model_interneuron.joblib``
* ``flag_model_all.joblib``
* ``flag_model_pyramidal_baseline.joblib`` (optional heavy flagger)
* ``flag_model_all_baseline.joblib`` (optional heavy flagger)

Search order (first existing wins):

1. The directory passed in via the function argument or via the
   ``SWCSTUDIO_MODEL_DIR`` environment variable (highest precedence,
   used for "I trained my own models" workflows).
2. The user data directory:

   * Windows: ``%APPDATA%\\swcstudio\\models``
   * macOS: ``~/Library/Application Support/swcstudio/models``
   * Linux: ``~/.local/share/swcstudio/models``

3. The bundled directory inside the installed package
   (``swcstudio/data/models``). Source installs keep the current model
   files here; pip installs can fetch the model layer on first use.

Public API:

* ``user_model_dir()`` — user data dir (creates if missing)
* ``bundled_model_dir()`` — dir inside the installed package
* ``resolve_model_path(name, override=None)`` — full path or ``None``
* ``available_models(override=None)`` — ``dict[name -> Path | None]``

Calling code never hard-codes paths. It calls
``resolve_model_path("gnn_apical_basal.pt")`` and gets either a real
path or ``None``.
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
    "branch3": "gnn_branch3_rescue.pt",
    "qc_gate": "qc_gate.pkl",
    "flag_pyramidal": "flag_model_pyramidal.joblib",
    "flag_interneuron": "flag_model_interneuron.joblib",
    "flag_all": "flag_model_all.joblib",
    "flag_pyramidal_baseline": "flag_model_pyramidal_baseline.joblib",
    "flag_all_baseline": "flag_model_all_baseline.joblib",
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
    auto_download: bool = True,
) -> Path | None:
    """Locate one model file by short name or by literal filename.

    ``name_or_filename`` accepts both ``"stage1"`` and
    ``"cell_type_classifier.pkl"``. Returns the first existing path
    found in :func:`search_dirs`, or ``None``.

    If no local copy is found and ``auto_download=True`` (default),
    falls back to fetching the models package from GitHub Releases via
    :mod:`swcstudio.core.updater`. This is what makes pip-installed
    users work out of the box without bundling 60 MB of models inside
    the wheel — the first auto-label call triggers a one-time download
    into the user data dir, and subsequent calls find it cached.

    Set ``auto_download=False`` to skip the network fallback (used by
    diagnostic / testing paths that want to know "is the model
    physically here right now").
    """
    fname = MODEL_FILES.get(name_or_filename, name_or_filename)
    for d in search_dirs(override):
        candidate = d / fname
        if candidate.is_file():
            return candidate

    if not auto_download:
        return None

    # Lazy import — keeps `model_paths` itself stdlib-only and avoids a
    # circular import at module load time (`updater` doesn't import
    # `model_paths`, but importing it eagerly here would still bind a
    # network-capable module into a path-resolution helper).
    try:
        from swcstudio.core import updater  # noqa: WPS433
    except ImportError:
        return None

    manifest = updater.fetch_manifest()
    if manifest is None or manifest.models is None:
        return None
    try:
        updater.apply_update("models", manifest.models)
    except Exception:
        # Network failure / disk failure / integrity mismatch — give up
        # silently and let the caller report "model not found".
        return None

    # Re-scan after the download. The user override dir
    # (~/Library/Application Support/SWC-Studio/models/) is part of
    # search_dirs(), so the fresh files will be found.
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
