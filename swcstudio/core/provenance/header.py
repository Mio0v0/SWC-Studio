"""Bounded ``# @PROV`` header for materialized SWC files.

Implements PROVENANCE_SPEC §5: every produced SWC carries exactly two
``# @PROV`` lines at the top — a *root* line (origin, written once)
and a *tip* line (current state, overwritten on every save). The full
chain stays in ``.history/``; the file itself only carries this
2-line "business card" pointer.

The two lines are deliberately the **only** comment lines beginning
with ``# @PROV`` we ever produce. That, combined with the spec §2 rule
that ``# @PROV`` lines are excluded from the canonical hash, makes the
header cycle-free:

* writing the tip line about state ``X`` does not change ``X``'s hash,
* so the tip line never invalidates itself.

This module is **stateless** byte manipulation. The values that go
into the lines (``root_sha``, ``tip``, ``parent``, etc.) are computed
upstream; we just format and splice.
"""

from __future__ import annotations

import re
from typing import NamedTuple

__all__ = [
    "ProvHeader",
    "format_root_line",
    "format_tip_line",
    "strip_prov_lines",
    "write_prov_header",
    "parse_prov_header",
]


PROV_PREFIX = "# @PROV"


class ProvHeader(NamedTuple):
    """Parsed contents of an SWC's two ``@PROV`` lines."""

    root: dict[str, str] | None
    tip: dict[str, str] | None


# ----------------------------------------------------------------------
# formatters
# ----------------------------------------------------------------------


def format_root_line(
    *,
    root_sha: str,
    file_name: str,
    created_utc: str,
) -> str:
    """Format the immutable root line written once at file creation.

    Example::

        # @PROV root=a1b2c3d4 file=neuron_001.swc created=2024-01-01T09:00:00Z
    """
    return (
        f"{PROV_PREFIX} "
        f"root={_short(root_sha)} "
        f"file={_safe(file_name)} "
        f"created={_safe(created_utc)}"
    )


def format_tip_line(
    *,
    tip: str,
    parent: str | None,
    ops: int,
    tool: str,
    actor: str,
    updated_utc: str,
    sidecar: str = ".history/",
) -> str:
    """Format the mutable tip line overwritten on every commit.

    Example::

        # @PROV tip=g7h8i9j0 parent=d4e5f6a7 ops=20 tool=swcstudio@0.2.0 \
                actor=tuo updated=2024-01-01T11:45:22Z sidecar=.history/
    """
    return (
        f"{PROV_PREFIX} "
        f"tip={_short(tip)} "
        f"parent={_short(parent) if parent else 'none'} "
        f"ops={int(ops)} "
        f"tool={_safe(tool)} "
        f"actor={_safe(actor)} "
        f"updated={_safe(updated_utc)} "
        f"sidecar={_safe(sidecar)}"
    )


# ----------------------------------------------------------------------
# splice
# ----------------------------------------------------------------------


def strip_prov_lines(data: bytes) -> bytes:
    """Return ``data`` with all existing ``# @PROV`` lines removed.

    Operates on raw bytes (not canonical form) so the result preserves
    every other byte exactly — line endings, trailing whitespace,
    float formatting, comment ordering. Only the @PROV lines, which
    we own, are touched.
    """
    text = data.decode("utf-8")
    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        # ``startswith`` test against the raw line catches both ``\n``
        # and ``\r\n``-terminated variants because the prefix doesn't
        # contain a line terminator.
        if line.lstrip().startswith(PROV_PREFIX):
            continue
        out_lines.append(line)
    return "".join(out_lines).encode("utf-8")


def write_prov_header(
    data: bytes,
    *,
    root_line: str,
    tip_line: str,
) -> bytes:
    """Return ``data`` with the supplied root + tip @PROV lines on top.

    Replaces any pre-existing @PROV lines (so updating the tip doesn't
    accumulate stale chains). Other comment lines and data rows are
    preserved bit-for-bit.

    The output always uses ``\\n`` after each header line. The body's
    line endings are not touched — we only own the bytes we wrote.
    """
    body = strip_prov_lines(data)
    header = (root_line + "\n" + tip_line + "\n").encode("utf-8")
    return header + body


# ----------------------------------------------------------------------
# parser (best-effort; for ``swcstudio history show`` and the GUI)
# ----------------------------------------------------------------------


_KV_RE = re.compile(r"(\w+)=(\S+)")


def parse_prov_header(data: bytes) -> ProvHeader:
    """Extract the most recent root + tip lines from an SWC's header.

    Returns ``ProvHeader(None, None)`` if neither line is present.
    Lines are matched by their first key (``root=`` -> root line,
    ``tip=`` -> tip line). If multiple lines of either kind exist
    (legacy files, manual edits), the *last* one wins — that's the
    one our writer produced most recently.
    """
    text = data.decode("utf-8", errors="replace")
    root: dict[str, str] | None = None
    tip: dict[str, str] | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith(PROV_PREFIX):
            continue
        kvs = dict(_KV_RE.findall(s))
        if "root" in kvs and "tip" not in kvs:
            root = kvs
        elif "tip" in kvs:
            tip = kvs
    return ProvHeader(root=root, tip=tip)


# ----------------------------------------------------------------------
# tiny helpers
# ----------------------------------------------------------------------


def _short(sha: str) -> str:
    """Display a short form of a SHA for the on-line header.

    The full sha lives in the sidecar; the header only needs enough
    bits to be a unique short pointer. We strip the ``sha256:`` prefix
    if present and keep the first 8 hex chars (32 bits — collision-
    free at SWC-Studio's scale).
    """
    s = sha.removeprefix("sha256:") if sha else ""
    return s[:8] or "none"


def _safe(s: str) -> str:
    """Quote a value if it contains spaces; otherwise pass through.

    The header is single-line and parsed by ``key=value`` splits on
    whitespace, so a value with embedded spaces would corrupt the
    line. We replace whitespace with ``_`` rather than quoting, to
    keep the line trivially greppable.
    """
    return re.sub(r"\s+", "_", str(s))
