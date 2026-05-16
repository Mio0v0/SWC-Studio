"""Structured diff between two canonical-SWC byte streams.

Implements PROVENANCE_SPEC §4 ("Diff blob"). The diff is computed
**from canonical SWC bytes** — the same form used to compute hashes
— so two equivalent SWCs produce an empty diff and the diff result
matches what a future ``apply_diff`` would need to round-trip the
state.

What the diff tells you, structurally:

* **node_changes**: per-(node_id, field) before/after for nodes
  present on both sides.
* **topology_changes**: nodes added or removed, and reparenting events
  (where a node is in both sides but its ``parent`` field changed).

Why we represent reparenting as a topology change rather than as a
node_change with field=parent: parent edges are the connectivity
backbone of an SWC, not a per-node attribute like radius. Walking
"every reparent" should be cheap; lumping it with field-level
changes would make that walk O(N).

Diff payloads are the input to:

* the ``objects/`` blob written per commit
* the ``summary`` counts inlined into the event line
* the ``node_changes`` rows inserted into SQLite

A snapshot is conceptually a diff against the empty SWC; we model
that elsewhere (snapshots.py) and don't represent it as a diff blob.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from swcstudio.core.provenance.canonical import canonical_swc

__all__ = [
    "DiffPayload",
    "compute_swc_diff",
    "summarize_diff",
]


# Field names from the seven-column SWC row. Order matters for parsing
# (we split on whitespace and zip) but for diff display we name them.
_FIELD_NAMES = ("type", "x", "y", "z", "radius", "parent")
# id is the row key, not a diffable field. parent is treated specially
# below as a topology relationship, not a per-node attribute.


@dataclass
class DiffPayload:
    """Structured diff suitable for serialization to a diff blob."""

    schema_version: int = 1
    from_sha: str | None = None
    to_sha: str | None = None
    node_changes: list[dict[str, Any]] = field(default_factory=list)
    topology_changes: list[dict[str, Any]] = field(default_factory=list)

    def to_json_obj(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "from": self.from_sha,
            "to": self.to_sha,
            "node_changes": list(self.node_changes),
            "topology_changes": list(self.topology_changes),
        }


def compute_swc_diff(
    before: bytes,
    after: bytes,
    *,
    from_sha: str | None = None,
    to_sha: str | None = None,
) -> DiffPayload:
    """Compute a structured diff between two raw SWC byte streams.

    Both inputs are canonicalized first (so cosmetic differences are
    absorbed exactly the same way our hashes absorb them). The result
    is a :class:`DiffPayload` ready to be JSON-encoded and stored as
    a blob.

    Identity short-circuit: if ``before == after`` after
    canonicalization, returns an empty diff (no node changes, no
    topology changes). This is the right answer — nothing changed —
    even if the raw bytes differed cosmetically.
    """
    before_rows = _parse_canonical(before)
    after_rows = _parse_canonical(after)

    payload = DiffPayload(from_sha=from_sha, to_sha=to_sha)

    before_ids = set(before_rows)
    after_ids = set(after_rows)

    # Topology: removals first, then adds, then reparents (stable order
    # makes diff blobs byte-stable for identical inputs).
    for nid in sorted(before_ids - after_ids):
        payload.topology_changes.append({"kind": "remove", "id": nid})

    for nid in sorted(after_ids - before_ids):
        payload.topology_changes.append({
            "kind": "add",
            "id": nid,
            "row": after_rows[nid]["raw"],
        })

    # Field-level + reparent changes for nodes present on both sides.
    for nid in sorted(before_ids & after_ids):
        b = before_rows[nid]
        a = after_rows[nid]
        # parent change is a topology event, not a node_change row.
        if b["parent_str"] != a["parent_str"]:
            payload.topology_changes.append({
                "kind": "reparent",
                "id": nid,
                "before": _coerce_int(b["parent_str"]),
                "after": _coerce_int(a["parent_str"]),
            })
        # Other fields: type, x, y, z, radius. We compare the *string*
        # form (preserving the user's float representation, per spec §2
        # "pass-through") so trailing zeros etc. round-trip exactly.
        for fname, b_str, a_str in (
            ("type",   b["type_str"],   a["type_str"]),
            ("x",      b["x_str"],      a["x_str"]),
            ("y",      b["y_str"],      a["y_str"]),
            ("z",      b["z_str"],      a["z_str"]),
            ("radius", b["radius_str"], a["radius_str"]),
        ):
            if b_str != a_str:
                payload.node_changes.append({
                    "id": nid,
                    "field": fname,
                    "before": _coerce_value(fname, b_str),
                    "after":  _coerce_value(fname, a_str),
                })

    return payload


def summarize_diff(payload: DiffPayload) -> dict[str, int]:
    """Compact counts suitable for inlining into the event ``summary``.

    Spec §6 / M6: the event line carries this dict so timelines render
    without decompressing the diff blob.
    """
    added = sum(1 for c in payload.topology_changes if c["kind"] == "add")
    removed = sum(1 for c in payload.topology_changes if c["kind"] == "remove")
    reparented = sum(1 for c in payload.topology_changes if c["kind"] == "reparent")
    modified_nodes = len({c["id"] for c in payload.node_changes})
    return {
        "nodes_added": added,
        "nodes_removed": removed,
        "nodes_modified": modified_nodes,
        "fields_changed": len(payload.node_changes),
        "reparented": reparented,
    }


# ----------------------------------------------------------------------
# internals: minimal canonical-SWC row parser
# ----------------------------------------------------------------------


def _parse_canonical(raw: bytes) -> dict[int, dict[str, Any]]:
    """Parse canonical SWC bytes into ``{id: {fields}}``.

    The parser keeps both the typed value and the original string for
    each numeric field, so :func:`compute_swc_diff` can detect a real
    difference even when the typed values would compare equal (e.g.
    ``"3.14"`` vs ``"3.140"``).

    We re-canonicalize defensively so callers can pass either raw or
    already-canonical bytes — the result is the same either way, and
    bypassing canonicalization here would risk diffs that disagree
    with hashes.
    """
    text = canonical_swc(raw).decode("utf-8")
    rows: dict[int, dict[str, Any]] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) < 7:
            continue  # malformed row; downstream tools warn — not our job here
        id_tok, type_tok, x_tok, y_tok, z_tok, radius_tok, parent_tok = parts[:7]
        try:
            nid = int(float(id_tok))
        except ValueError:
            continue
        rows[nid] = {
            "raw": s,
            "type_str":   type_tok,
            "x_str":      x_tok,
            "y_str":      y_tok,
            "z_str":      z_tok,
            "radius_str": radius_tok,
            "parent_str": parent_tok,
        }
    return rows


def _coerce_value(field_name: str, s: str) -> Any:
    """Convert a field's string form to a JSON-friendly typed value.

    Used for the ``before``/``after`` fields in node_changes so the
    diff blob and the SQLite ``node_changes`` table store proper
    numbers rather than quoted strings.
    """
    if field_name == "type":
        return _coerce_int(s)
    return _coerce_float(s)


def _coerce_int(s: str) -> int:
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0


def _coerce_float(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return 0.0
