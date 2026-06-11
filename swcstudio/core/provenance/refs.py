"""Bookmarks into the event DAG: HEAD, branches, tags.

Implements PROVENANCE_SPEC §6 and the ``refs/`` layout from §1.

Each ref is a tiny plain-text file containing a single value:

* ``refs/HEAD`` — the *name* of the active branch (e.g. ``"main"``)
* ``refs/branches/<name>`` — the *commit id* the branch tip points at
* ``refs/tags/<name>`` — the *commit id* the tag points at (immutable)

Why files instead of a single JSON manifest:

* **Atomicity per ref.** Updating a single branch is a single
  ``os.replace``, which POSIX guarantees atomic. A multi-ref manifest
  would require a lock larger than what we already hold and a more
  complex update protocol.
* **Independent corruption.** A garbled tag file does not break
  branch resolution.
* **Mirrors git's mental model.** Anyone who's used git already knows
  this layout.

Branches are mutable (advance on each commit). Tags are immutable
(creating one twice with different sha is rejected). HEAD is a
single-line text file overwritten on ``switch``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

__all__ = [
    "RefError",
    "TagExistsError",
    "DEFAULT_BRANCH",
    "valid_ref_name",
    "read_head",
    "write_head",
    "read_branch",
    "write_branch",
    "delete_branch",
    "list_branches",
    "read_tag",
    "create_tag",
    "delete_tag",
    "list_tags",
    "init_refs",
]


DEFAULT_BRANCH = "main"

# Conservative ref name policy: alphanumerics, underscore, dash, dot,
# slash. No whitespace, no leading dot, no double-slash, no shell-magic
# characters. Rejects anything that would be awkward as a filename or
# in a CLI argument across all OSes we ship to.
_REF_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")


class RefError(ValueError):
    """Raised on invalid ref names or missing required refs."""


class TagExistsError(RefError):
    """Raised when attempting to overwrite an immutable tag."""


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def valid_ref_name(name: str) -> bool:
    """Return True if ``name`` is a legal branch/tag name."""
    if not isinstance(name, str) or not name:
        return False
    if ".." in name or "//" in name or name.endswith("/") or name.endswith("."):
        return False
    return bool(_REF_NAME_RE.match(name))


def _check_name(name: str) -> str:
    if not valid_ref_name(name):
        raise RefError(f"invalid ref name: {name!r}")
    return name


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically, with fsync.

    The caller must hold ``.history/lock`` to avoid concurrent writers
    on the same ref clobbering each other's tmp files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _read_single_line(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def _refs_root(history_dir: str | os.PathLike[str]) -> Path:
    return Path(history_dir) / "refs"


# ----------------------------------------------------------------------
# init
# ----------------------------------------------------------------------


def init_refs(history_dir: str | os.PathLike[str], *, branch: str = DEFAULT_BRANCH) -> None:
    """Initialize ``refs/HEAD`` and the default branch file (empty).

    Idempotent: if HEAD already exists, leaves it alone. The branch
    file is created empty if missing — its content is filled by the
    first commit on that branch.
    """
    _check_name(branch)
    refs = _refs_root(history_dir)
    (refs / "branches").mkdir(parents=True, exist_ok=True)
    (refs / "tags").mkdir(parents=True, exist_ok=True)
    head_path = refs / "HEAD"
    if not head_path.exists():
        _atomic_write_text(head_path, branch + "\n")
    branch_path = refs / "branches" / branch
    if not branch_path.exists():
        _atomic_write_text(branch_path, "")


# ----------------------------------------------------------------------
# HEAD
# ----------------------------------------------------------------------


def read_head(history_dir: str | os.PathLike[str]) -> str:
    """Return the active branch name.

    Raises :class:`RefError` if HEAD is missing — callers should
    ``init_refs`` first.
    """
    val = _read_single_line(_refs_root(history_dir) / "HEAD")
    if val is None:
        raise RefError("HEAD is not set; call init_refs() first")
    return val


def write_head(history_dir: str | os.PathLike[str], branch: str) -> None:
    """Set HEAD to ``branch`` (the branch must already exist)."""
    _check_name(branch)
    refs = _refs_root(history_dir)
    if not (refs / "branches" / branch).exists():
        raise RefError(f"cannot switch to nonexistent branch: {branch!r}")
    _atomic_write_text(refs / "HEAD", branch + "\n")


# ----------------------------------------------------------------------
# branches (mutable)
# ----------------------------------------------------------------------


def read_branch(history_dir: str | os.PathLike[str], name: str) -> str | None:
    """Return the commit id at the tip of branch ``name``, or None.

    None is returned if the branch file exists but is empty (a freshly
    created branch with no commits yet) OR if the branch does not
    exist at all. Callers that need to distinguish should use
    ``name in list_branches(...)``.
    """
    _check_name(name)
    return _read_single_line(_refs_root(history_dir) / "branches" / name)


def write_branch(history_dir: str | os.PathLike[str], name: str, sha: str) -> None:
    """Set branch ``name`` to point at commit ``sha``.

    Creates the branch if it does not exist. This is the verb the
    commit path calls to advance the active branch tip.
    """
    _check_name(name)
    if not _looks_like_event_id(sha):
        raise RefError(f"branch tip must be an event id (sha256:...): {sha!r}")
    _atomic_write_text(
        _refs_root(history_dir) / "branches" / name,
        sha + "\n",
    )


def delete_branch(history_dir: str | os.PathLike[str], name: str) -> None:
    """Delete branch ``name``. Raises if it does not exist or is HEAD."""
    _check_name(name)
    if read_head(history_dir) == name:
        raise RefError(f"cannot delete branch {name!r} while it is HEAD")
    path = _refs_root(history_dir) / "branches" / name
    if not path.exists():
        raise RefError(f"no such branch: {name!r}")
    path.unlink()


def list_branches(history_dir: str | os.PathLike[str]) -> list[str]:
    """Return all branch names, sorted."""
    return _list_dir(_refs_root(history_dir) / "branches")


# ----------------------------------------------------------------------
# tags (immutable)
# ----------------------------------------------------------------------


def read_tag(history_dir: str | os.PathLike[str], name: str) -> str | None:
    _check_name(name)
    return _read_single_line(_refs_root(history_dir) / "tags" / name)


def create_tag(history_dir: str | os.PathLike[str], name: str, sha: str) -> None:
    """Create tag ``name`` pointing at ``sha``.

    Raises :class:`TagExistsError` if a tag with this name already
    exists, even if it would point at the same sha — tags are strictly
    immutable in v1.
    """
    _check_name(name)
    if not _looks_like_event_id(sha):
        raise RefError(f"tag must point at an event id (sha256:...): {sha!r}")
    path = _refs_root(history_dir) / "tags" / name
    if path.exists():
        raise TagExistsError(f"tag already exists: {name!r}")
    _atomic_write_text(path, sha + "\n")


def delete_tag(history_dir: str | os.PathLike[str], name: str) -> None:
    """Delete tag ``name``. Provided for housekeeping/test cleanup;
    not exposed on the user-facing CLI in v1 (spec §6 makes tags
    immutable from the user's perspective).
    """
    _check_name(name)
    path = _refs_root(history_dir) / "tags" / name
    if not path.exists():
        raise RefError(f"no such tag: {name!r}")
    path.unlink()


def list_tags(history_dir: str | os.PathLike[str]) -> list[str]:
    return _list_dir(_refs_root(history_dir) / "tags")


# ----------------------------------------------------------------------
# internals
# ----------------------------------------------------------------------


def _list_dir(d: Path) -> list[str]:
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file() and not p.name.endswith(".tmp"))


def _looks_like_event_id(s: str) -> bool:
    # We use the "sha256:<hex>" format established in events.compute_event_id.
    return isinstance(s, str) and s.startswith("sha256:") and len(s) == 7 + 64


def _validate_iterable_names(names: Iterable[str]) -> None:
    for n in names:
        _check_name(n)
