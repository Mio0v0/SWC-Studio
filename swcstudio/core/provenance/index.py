"""SQLite index over the JSONL event log.

Implements PROVENANCE_SPEC §11. The index is a **rebuildable cache** —
the JSONL log is the source of truth. If the SQLite says X and JSONL
says Y, JSONL wins. ``rebuild_index`` walks the log from scratch and
recreates the database.

What the index buys us is fast queries:

* "every commit by Alice in date range R" — indexed
* "every change to node 47" — indexed
* "every AI run that used model version v8" — indexed
* "the tip of branch X" — refs already give this; we don't duplicate

What the index does NOT do:

* It is not the source of truth. Never write events directly to
  SQLite without also writing to events.jsonl.
* It does not own the refs files. ``refs/`` is its own atomic store.
* It does not store blob bytes. ``objects/`` does.

Why a per-event sync (rather than rebuild-on-read):

* Live ``swcstudio history log`` calls should not pay an O(N) replay
  cost. The index is updated inside the same critical section as the
  event-log append, in the same SQLite transaction, so JSONL +
  SQLite move forward atomically.
* If they ever diverge (manual JSONL edit, partial fs corruption),
  ``rebuild_index`` resets SQLite from JSONL in seconds.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Iterator

from swcstudio.core.provenance.events import (
    MAX_SUPPORTED_SCHEMA_VERSION,
    Event,
    iter_events,
)

__all__ = [
    "INDEX_SCHEMA_VERSION",
    "open_index",
    "ensure_schema",
    "insert_event",
    "rebuild_index",
    "query_commits",
    "query_ai_runs",
    "query_node_changes",
]


# Bumped only when the SQLite schema itself changes shape. Independent
# of the JSONL schema_version. Mismatch triggers an automatic rebuild
# from JSONL — safe because the SQLite is a cache.
INDEX_SCHEMA_VERSION = 1


_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS commits (
    sha          TEXT PRIMARY KEY,
    parent       TEXT,
    branch       TEXT,
    ts           TEXT,
    os_user      TEXT,
    tool_version TEXT,
    tool_git_sha TEXT,
    session_id   TEXT,
    message      TEXT,
    input_sha    TEXT,
    output_sha   TEXT,
    diff_ref     TEXT,
    is_snapshot  INTEGER NOT NULL DEFAULT 0,
    derived_root TEXT,
    derived_commit TEXT
);
CREATE INDEX IF NOT EXISTS commits_parent ON commits(parent);
CREATE INDEX IF NOT EXISTS commits_ts     ON commits(ts);
CREATE INDEX IF NOT EXISTS commits_user   ON commits(os_user);
CREATE INDEX IF NOT EXISTS commits_branch ON commits(branch);

CREATE TABLE IF NOT EXISTS ops (
    op_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha   TEXT NOT NULL REFERENCES commits(sha) ON DELETE CASCADE,
    op_index     INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    params_json  TEXT,
    summary_json TEXT,
    ai_run_ref   TEXT
);
CREATE INDEX IF NOT EXISTS ops_commit ON ops(commit_sha);
CREATE INDEX IF NOT EXISTS ops_kind   ON ops(kind);

CREATE TABLE IF NOT EXISTS node_changes (
    op_id    INTEGER NOT NULL REFERENCES ops(op_id) ON DELETE CASCADE,
    node_id  INTEGER NOT NULL,
    field    TEXT NOT NULL,
    before   TEXT,
    after    TEXT
);
CREATE INDEX IF NOT EXISTS node_changes_node ON node_changes(node_id);
CREATE INDEX IF NOT EXISTS node_changes_op   ON node_changes(op_id);

CREATE TABLE IF NOT EXISTS ai_runs (
    ai_run_ref     TEXT PRIMARY KEY,
    commit_sha     TEXT NOT NULL REFERENCES commits(sha) ON DELETE CASCADE,
    model_sha      TEXT,
    model_version  TEXT,
    started_at     TEXT,
    finished_at    TEXT,
    env_hash       TEXT,
    metrics_json   TEXT,
    params_json    TEXT
);
CREATE INDEX IF NOT EXISTS ai_runs_model      ON ai_runs(model_sha);
CREATE INDEX IF NOT EXISTS ai_runs_model_ver  ON ai_runs(model_version);
"""


# ----------------------------------------------------------------------
# connection management
# ----------------------------------------------------------------------


def open_index(history_dir: str | os.PathLike[str]) -> sqlite3.Connection:
    """Open or create ``.history/index.sqlite`` in WAL mode.

    Sets reasonable pragmas for a small embedded index that's
    occasionally written by short-lived ops:

    * WAL journaling — readers don't block the (briefly) writing tracked_op
    * synchronous=NORMAL — pairs safely with WAL; durability is owned
      by the JSONL log, so an SQLite crash mid-commit is recoverable
      via rebuild_index
    * foreign_keys=ON — enforce the ON DELETE CASCADE relationships
    """
    path = Path(history_dir) / "index.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit; we manage txns explicitly
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables/indexes if missing; bump schema-version row."""
    conn.executescript(_SCHEMA_DDL)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        ("schema_version", str(INDEX_SCHEMA_VERSION)),
    )


# ----------------------------------------------------------------------
# write path
# ----------------------------------------------------------------------


def insert_event(
    conn: sqlite3.Connection,
    event: Event,
    *,
    node_changes_for_op: dict[int, list[dict[str, Any]]] | None = None,
) -> list[int]:
    """Insert one event into the index.

    The optional ``node_changes_for_op`` maps the integer op-index
    within ``event.ops`` to a list of node-level change rows
    (``{"id", "field", "before", "after"}``). Tracked_op passes this
    after computing the structured diff so detailed queries
    (``every change to node 47``) work without re-reading diff blobs.

    Returns the per-history operation IDs assigned in ``event.ops``
    order. Every SWC has its own sequence: ``op-1``, ``op-2``, ...

    Idempotent on the commit sha — calling twice with the same event
    is a no-op (INSERT OR IGNORE on commits, then op rows fall through
    the foreign-key check). This makes rebuild_index restartable.
    """
    derived = event.derived_from or {}
    operation_ids: list[int] = []
    conn.execute("BEGIN")
    try:
        # commits row
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO commits(
                sha, parent, branch, ts, os_user, tool_version, tool_git_sha,
                session_id, message, input_sha, output_sha, diff_ref,
                is_snapshot, derived_root, derived_commit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.parent,
                event.branch,
                event.ts,
                (event.actor or {}).get("os_user"),
                (event.tool or {}).get("version"),
                (event.tool or {}).get("git_sha"),
                event.session_id,
                event.message,
                event.input_sha,
                event.output_sha,
                event.diff_ref,
                int(event.is_snapshot),
                derived.get("root_sha"),
                derived.get("commit_sha"),
            ),
        )
        # If the commit was already present, skip op/ai_run/node_change
        # writes too — we don't want duplicates.
        if cur.rowcount == 0:
            conn.execute("COMMIT")
            return operation_ids

        # ops rows
        for i, op in enumerate(event.ops or []):
            params_json = json.dumps(op.get("params"), sort_keys=True) if "params" in op else None
            summary_json = json.dumps(op.get("summary"), sort_keys=True) if "summary" in op else None
            ai_ref = op.get("ai_run_ref")
            cur2 = conn.execute(
                """
                INSERT INTO ops(commit_sha, op_index, kind, params_json, summary_json, ai_run_ref)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event.id, i, str(op.get("kind", "")), params_json, summary_json, ai_ref),
            )
            op_row_id = cur2.lastrowid
            operation_ids.append(int(op_row_id))

            # node_changes rows (caller-supplied; tracked_op pre-computes
            # the structured diff so we don't decompress blobs here)
            ncs = (node_changes_for_op or {}).get(i, [])
            for nc in ncs:
                conn.execute(
                    """
                    INSERT INTO node_changes(op_id, node_id, field, before, after)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        op_row_id,
                        int(nc["id"]),
                        str(nc["field"]),
                        _scalar_to_text(nc.get("before")),
                        _scalar_to_text(nc.get("after")),
                    ),
                )

            # ai_runs row (one per op carrying ai_run_ref). Caller is
            # responsible for inserting the ai_run details separately
            # via insert_ai_run since that requires reading the AI-run
            # blob; here we only record the reference.
        conn.execute("COMMIT")
        return operation_ids
    except Exception:
        conn.execute("ROLLBACK")
        raise


def insert_ai_run(
    conn: sqlite3.Connection,
    *,
    ai_run_ref: str,
    commit_sha: str,
    model_sha: str | None,
    model_version: str | None,
    started_at: str | None,
    finished_at: str | None,
    env_hash: str | None,
    metrics: dict[str, Any] | None,
    params: dict[str, Any] | None,
) -> None:
    """Insert one AI-run record. Idempotent on ai_run_ref.

    Tracked_op calls this after writing the AI-run blob to objects/.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO ai_runs(
            ai_run_ref, commit_sha, model_sha, model_version,
            started_at, finished_at, env_hash, metrics_json, params_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ai_run_ref, commit_sha, model_sha, model_version,
            started_at, finished_at, env_hash,
            json.dumps(metrics, sort_keys=True) if metrics is not None else None,
            json.dumps(params, sort_keys=True) if params is not None else None,
        ),
    )


# ----------------------------------------------------------------------
# rebuild
# ----------------------------------------------------------------------


def rebuild_index(history_dir: str | os.PathLike[str]) -> int:
    """Rebuild ``.history/index.sqlite`` from ``events.jsonl`` and return event count.

    Drops every table and recreates them, then walks the JSONL log in
    order and re-inserts each event. AI-run details are NOT
    reconstructed here (we'd need to decompress every AI-run blob);
    the ``ai_runs`` table is left empty on rebuild and re-populated
    lazily, or by a future ``swcstudio history reindex --deep`` pass.
    """
    log_path = Path(history_dir) / "events.jsonl"
    db_path = Path(history_dir) / "index.sqlite"
    # Easiest correct rebuild: blow away the file and recreate.
    if db_path.exists():
        db_path.unlink()
    # WAL sidecar files; harmless if missing.
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()

    conn = open_index(history_dir)
    try:
        ensure_schema(conn)
        count = 0
        for event in iter_events(log_path):
            insert_event(conn, event)
            count += 1
        return count
    finally:
        conn.close()


# ----------------------------------------------------------------------
# read path — high-level convenience queries
# ----------------------------------------------------------------------


def query_commits(
    conn: sqlite3.Connection,
    *,
    branch: str | None = None,
    actor: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Common-case commit lookup. All filters AND together; None = no filter.

    Returns rows ordered most-recent-first.
    """
    sql = "SELECT * FROM commits WHERE 1=1"
    params: list[Any] = []
    if branch is not None:
        sql += " AND branch = ?"
        params.append(branch)
    if actor is not None:
        sql += " AND os_user = ?"
        params.append(actor)
    if since is not None:
        sql += " AND ts >= ?"
        params.append(since)
    if until is not None:
        sql += " AND ts < ?"
        params.append(until)
    sql += " ORDER BY ts DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    return list(conn.execute(sql, params))


def query_ai_runs(
    conn: sqlite3.Connection,
    *,
    model_version: str | None = None,
    actor: str | None = None,
) -> list[sqlite3.Row]:
    """AI runs joined back to their commit for actor/ts."""
    sql = (
        "SELECT a.*, c.ts AS commit_ts, c.os_user AS commit_user "
        "FROM ai_runs a JOIN commits c ON c.sha = a.commit_sha WHERE 1=1"
    )
    params: list[Any] = []
    if model_version is not None:
        sql += " AND a.model_version = ?"
        params.append(model_version)
    if actor is not None:
        sql += " AND c.os_user = ?"
        params.append(actor)
    sql += " ORDER BY c.ts DESC"
    return list(conn.execute(sql, params))


def query_node_changes(
    conn: sqlite3.Connection,
    *,
    node_id: int,
) -> list[sqlite3.Row]:
    """Every recorded change to a single node, oldest first.

    Joins through ops -> commits so the result includes ts, actor, op kind.
    """
    return list(conn.execute(
        """
        SELECT c.ts, c.os_user, o.kind, n.field, n.before, n.after
        FROM node_changes n
        JOIN ops o     ON o.op_id      = n.op_id
        JOIN commits c ON c.sha        = o.commit_sha
        WHERE n.node_id = ?
        ORDER BY c.ts ASC
        """,
        (int(node_id),),
    ))


# ----------------------------------------------------------------------
# internals
# ----------------------------------------------------------------------


def _scalar_to_text(v: Any) -> str | None:
    """SQLite-friendly stringification for diff before/after values.

    Numbers are stored as their JSON form to preserve sign/scale
    (e.g. -0.0 vs 0.0). None stays None for "no value here".
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return json.dumps(v)
    return str(v)
