"""Clean-slate import from existing pre-history output dirs (M11 + spec §16).

Per the locked decision (M11), we do **not** try to reconstruct
provenance from old text reports. Instead, on first encounter with a
pre-existing ``<stem>_swc_studio_output/`` containing legacy artifacts
(``_closed_*.swc``, text reports), we:

1. Initialize ``.history/`` fresh.
2. Create one synthetic ``import`` commit whose ``output_sha`` is the
   canonical hash of the most-recent ``_closed_*.swc`` (if any) or of
   the original SWC otherwise.
3. Leave the legacy files in place — we do not delete them.
4. Surface a one-time message to the caller so the GUI/CLI can
   notify the user that history is now tracked.

The synthetic commit carries an explicit ``message`` recording the
import and ``schema_version=1`` like any other event, so it appears
in the timeline as a normal first commit and not as a special case.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from swcstudio.core.provenance.archive import archive_path_for
from swcstudio.core.provenance.ops import OpKind
from swcstudio.core.provenance.tracked_op import (
    OpResult,
    history_dir_for,
    init_history,
    tracked_op,
)

__all__ = [
    "MigrationOutcome",
    "needs_migration",
    "migrate_legacy_output_dir",
]


_LEGACY_CLOSED_RE = re.compile(r"^(?P<stem>.+?)_closed_(?P<ts>\d{8}_\d{6})\.swc$")


class MigrationOutcome(NamedTuple):
    """What :func:`migrate_legacy_output_dir` did, for caller messaging."""

    history_initialized: bool          # True if .history/ was newly created
    imported_commit: OpResult | None   # the synthetic import commit, if one was made
    imported_from: Path | None         # the legacy file we treated as the imported state
    legacy_files_kept: int             # count of pre-existing files left in place


def needs_migration(swc_path: str | Path) -> bool:
    """Quick check: does this dataset have legacy artifacts but no .history?"""
    out_dir = _output_dir(swc_path)
    if not out_dir.exists():
        return False
    if archive_path_for(swc_path).exists():
        return False
    if (out_dir / ".history").exists():
        return False  # already migrated
    return any(_iter_legacy_artifacts(out_dir))


def migrate_legacy_output_dir(swc_path: str | Path) -> MigrationOutcome:
    """Initialize ``.history/`` and (if applicable) record the import commit.

    Idempotent: running twice on the same path returns the same
    "history already exists" outcome on the second call.
    """
    p = Path(swc_path)
    out_dir = _output_dir(p)
    hist = history_dir_for(p)

    # Already migrated.
    if hist.exists() or archive_path_for(p).exists():
        return MigrationOutcome(
            history_initialized=False,
            imported_commit=None,
            imported_from=None,
            legacy_files_kept=_count_legacy(out_dir),
        )

    init_history(p)

    legacy = _most_recent_closed_swc(out_dir)
    legacy_count = _count_legacy(out_dir)

    if legacy is None:
        # No pre-existing closed copy. We could still create a no-op
        # "init" commit so the timeline has a starting point, but that
        # adds noise — the first real edit is a perfectly fine first
        # commit.
        return MigrationOutcome(
            history_initialized=True,
            imported_commit=None,
            imported_from=None,
            legacy_files_kept=legacy_count,
        )

    body = legacy.read_bytes()
    msg = f"Imported from pre-history sidecar (legacy file: {legacy.name})"
    with tracked_op(p, kind=OpKind.PLUGIN_OP,
                    params={"migration": "legacy_pre_history",
                            "legacy_file": legacy.name},
                    message=msg) as op:
        op.set_output(body)
    return MigrationOutcome(
        history_initialized=True,
        imported_commit=op.result,
        imported_from=legacy,
        legacy_files_kept=legacy_count,
    )


# ----------------------------------------------------------------------
# internals
# ----------------------------------------------------------------------


def _output_dir(swc_path: str | Path) -> Path:
    p = Path(swc_path)
    if p.parent.name.endswith("_swc_studio_output"):
        return p.parent
    return p.parent / f"{p.stem}_swc_studio_output"


def _iter_legacy_artifacts(out_dir: Path):
    """Yield paths considered "pre-history" artifacts.

    Anything in the output dir that is NOT inside ``.history/`` and
    NOT the new ``<stem>_current.swc`` counts. Includes
    ``_closed_*.swc``, text reports, batch reports, etc.
    """
    if not out_dir.exists():
        return
    for child in out_dir.iterdir():
        if child.name == ".history":
            continue
        if child.name.endswith("_current.swc"):
            continue
        yield child


def _count_legacy(out_dir: Path) -> int:
    return sum(1 for _ in _iter_legacy_artifacts(out_dir))


def _most_recent_closed_swc(out_dir: Path) -> Path | None:
    """Find the most-recent ``_closed_<ts>.swc`` by timestamp in name."""
    candidates: list[tuple[str, Path]] = []
    for child in out_dir.iterdir() if out_dir.exists() else []:
        if not child.is_file():
            continue
        m = _LEGACY_CLOSED_RE.match(child.name)
        if m:
            candidates.append((m.group("ts"), child))
    if not candidates:
        return None
    # ts format is YYYYMMDD_HHMMSS so plain string sort = chronological
    candidates.sort()
    return candidates[-1][1]
