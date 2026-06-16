"""Cross-file lineage helpers (PROVENANCE_SPEC §19, decision M10).

Whenever an SWC is created from another via any SWC-Studio path
(``split``, ``checkout -o``, plugin derivation), the new file's first
commit records ``derived_from = {root_sha, commit_sha, path}``. The
new file gets its own ``root_sha`` and its own sidecar history archive;
the ``derived_from`` field is the cross-file edge connecting the two
histories.

This module provides:

* :func:`derived_from_payload` — builds the dict tracked_op accepts
  via its ``derived_from=`` parameter.
* :func:`find_descendants` — walk a project-level index to surface
  all files that descend from a given root (the "everything that
  came from neuron_001.swc" query).

External ``cp`` is not handled here — the file system gives us no
hook to capture an unrecorded copy. If the user wants lineage
preserved across a copy, they must use ``swcstudio history checkout
-o`` (or its GUI equivalent), which calls ``derived_from_payload``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from swcstudio.core.provenance.canonical import canonical_swc, sha256_hex
from swcstudio.core.provenance.archive import open_history_for_read
from swcstudio.core.provenance.tracked_op import history_dir_for

__all__ = [
    "derived_from_payload",
    "derived_from_for_swc_path",
    "find_descendants",
]


def derived_from_payload(
    *,
    source_root_sha: str,
    source_commit_sha: str,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the ``derived_from`` dict for tracked_op.

    All three pieces of identifying info are recorded so future
    queries can join either by content (``root_sha``), by exact
    state (``commit_sha``), or by display name (``path``).
    """
    payload: dict[str, Any] = {
        "root_sha": _ensure_prefix(source_root_sha),
        "commit_sha": _ensure_prefix(source_commit_sha),
    }
    if source_path:
        payload["path"] = str(Path(source_path).name)
    return payload


def derived_from_for_swc_path(
    source_swc_path: str | Path,
    *,
    source_commit_sha: str | None = None,
) -> dict[str, Any] | None:
    """Convenience builder for the common case.

    Reads the source SWC's bytes (canonicalizes them to compute
    ``root_sha``) and pairs it with an explicit ``commit_sha`` if
    given, otherwise the current branch tip from the source's history.

    Returns ``None`` if the source has no history (it's an external
    file with no SWC-Studio lineage to forward).
    """
    src = Path(source_swc_path)
    if not src.exists():
        return None
    body = src.read_bytes()
    root = sha256_hex(canonical_swc(body))

    if source_commit_sha is None:
        # Fall back to the source's current branch tip if available.
        try:
            from swcstudio.core.provenance.refs import read_branch, read_head
            hist = history_dir_for(src)
            with open_history_for_read(src, hist) as live_hist:
                head = read_head(live_hist)
                tip = read_branch(live_hist, head)
            if tip:
                source_commit_sha = tip
        except Exception:
            return None
        if source_commit_sha is None:
            return None

    return derived_from_payload(
        source_root_sha=root,
        source_commit_sha=source_commit_sha,
        source_path=src.name,
    )


def find_descendants(
    project_index_conn: sqlite3.Connection,
    *,
    root_sha: str,
) -> list[sqlite3.Row]:
    """Return every commit (across the project) that derives from ``root_sha``.

    The project-level index (spec §1) keeps a ``derived_root`` column
    on commits populated from each commit's ``derived_from.root_sha``.
    This is the join key for cross-file lineage walks.

    The per-file ``index.sqlite`` carries the same column for
    completeness, so this query also works against a single-file
    index — it just only returns matches inside that one file's
    history.
    """
    sha = _ensure_prefix(root_sha)
    return list(project_index_conn.execute(
        """
        SELECT sha, branch, ts, os_user, message, derived_root, derived_commit
        FROM commits
        WHERE derived_root = ?
        ORDER BY ts ASC
        """,
        (sha,),
    ))


# ---------------------------------------------------------------------- #


def _ensure_prefix(s: str) -> str:
    """Normalize a sha string to the ``sha256:<hex>`` form we store."""
    if not s:
        return s
    if s.startswith("sha256:"):
        return s
    return "sha256:" + s
