"""Closed taxonomy of operation kinds (PROVENANCE_SPEC §3).

Why a closed enum + lightweight schema:

* The JSONL event log must be **stable across versions**: a v1 reader
  encountering a v1 op kind it doesn't recognize is a bug. So we lock
  the v1 set here and any new kind requires a v1.x additive bump.
* CLI/GUI handlers and plugins all reach for the same names. Having
  one place to look avoids drift between "auto_label" and "autolabel".
* Per-kind param validation is intentionally light — the heavy
  validation lives in the actual implementation modules
  (auto_label, radii_clean, etc.). What we promise here is "this
  field name exists and has this type"; what we don't promise is
  "the values are semantically valid for the operation."
"""

from __future__ import annotations

from enum import Enum
from typing import Any

__all__ = [
    "OpKind",
    "is_ai_op",
    "validate_op_record",
]


class OpKind(str, Enum):
    """Closed list of v1 operation kinds.

    String values double as the on-disk ``kind`` field. Inherits from
    ``str`` so callers can pass an OpKind anywhere a string is
    expected (``json.dumps`` works directly).
    """

    SET_TYPE         = "set_type"
    SET_RADIUS       = "set_radius"
    MANUAL_RADII     = "manual_radii"
    AUTO_FIX         = "auto_fix"
    AUTO_LABEL       = "auto_label"           # AI
    DENDROGRAM_EDIT  = "dendrogram_edit"
    GEOMETRY_EDIT    = "geometry_edit"
    RADII_CLEAN      = "radii_clean"
    SIMPLIFICATION   = "simplification"
    INDEX_CLEAN      = "index_clean"
    SPLIT            = "split"
    PLUGIN_OP        = "plugin_op"


# AI-classified ops — these are the ones tracked_op() must capture an
# environment fingerprint and AI-run record for. Matches PROVENANCE_SPEC
# §3 "Op kind" / §4 "AI ops also carry an ai_run_ref".
_AI_KINDS: frozenset[str] = frozenset({
    OpKind.AUTO_LABEL.value,
})


def is_ai_op(kind: str) -> bool:
    """Return True if ``kind`` is one of the AI-classified ops."""
    return kind in _AI_KINDS


# ---------------------------------------------------------------------
# minimal record validation (shape only; semantic checks live elsewhere)
# ---------------------------------------------------------------------


_VALID_KINDS: frozenset[str] = frozenset(k.value for k in OpKind)


def validate_op_record(op: dict[str, Any]) -> None:
    """Sanity-check the shape of an op dict before it's appended.

    Raises :class:`ValueError` on any problem. Specifically checks:

    * ``kind`` is one of the v1 OpKind values.
    * ``params`` is a dict (may be empty) — tracked_op stores op
      parameters here for later inspection / replay.
    * ``summary`` is a dict — small diff counts (nodes_added/modified/
      removed/etc.) for fast timeline display per spec §6 / M6.
    * If ``ai_run_ref`` is present, kind must be an AI op.

    What we do **not** check here: whether the params are semantically
    valid for that op kind. That's the implementation module's job.
    """
    if not isinstance(op, dict):
        raise ValueError(f"op must be a dict, got {type(op).__name__}")
    kind = op.get("kind")
    if kind not in _VALID_KINDS:
        raise ValueError(f"unknown op kind: {kind!r} (valid: {sorted(_VALID_KINDS)})")
    if "params" in op and not isinstance(op["params"], dict):
        raise ValueError(f"op.params must be a dict if present, got {type(op['params']).__name__}")
    if "summary" in op and not isinstance(op["summary"], dict):
        raise ValueError(f"op.summary must be a dict if present, got {type(op['summary']).__name__}")
    if "ai_run_ref" in op:
        if not is_ai_op(str(kind)):
            raise ValueError(f"ai_run_ref present on non-AI op kind {kind!r}")
        ref = op["ai_run_ref"]
        if not (isinstance(ref, str) and ref.startswith("sha256:")):
            raise ValueError(f"ai_run_ref must be a sha256:... string, got {ref!r}")
