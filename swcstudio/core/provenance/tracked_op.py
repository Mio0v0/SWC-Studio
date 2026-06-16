"""The mandatory mutation context manager.

Implements PROVENANCE_SPEC §8. Every code path that mutates an SWC —
CLI handlers, GUI actions, plugins — goes through one of two entry
points here:

* :class:`tracked_op` — atomic single operation, becomes one commit.
* :class:`tracked_session` — long-lived (interactive GUI session),
  collects multiple sub-ops, becomes one commit on exit.

The context manager owns the entire write protocol from spec §8 step
list:

1. Acquire ``.history/lock``. Fail loudly on contention.
2. Snapshot input bytes from disk; canonicalize; record input_sha.
3. For AI ops, capture env (deduplicated against existing blob).
4. Run the body — caller mutates and calls ``op.set_output(bytes)``.
5. Compute structured diff vs input; write diff blob.
6. For AI ops, finalize AIRun and write its blob.
7. Build Event, compute event id, append to JSONL.
8. Update active branch ref to new commit sha (atomic).
9. Insert into SQLite index in same critical section.
10. Materialize ``current.swc`` with refreshed @PROV header.
11. Release lock (always, including failure paths).

If any step fails, partial writes are cleaned up and the lock is
released. Crash-safety: append-only blobs are immutable; a partial
event line is never created (we write one line atomically). Refs
update via ``os.replace`` so a crash leaves either the old or new
tip, never garbage.

This module deliberately keeps swcstudio.core.swc_io and the editing
modules at arm's length — it operates on raw SWC bytes only so the
provenance layer can be unit-tested without dragging in the full
editing stack.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import swcstudio
from swcstudio.core.provenance.archive import (
    archive_history_dir,
    archive_name_for,
    ensure_history_manifest,
    ensure_history_materialized,
    history_repo_info,
)
from swcstudio.core.provenance.ai_run import (
    AIRun,
    AIRunStatus,
    ai_run_to_blob_bytes,
    build_ai_run,
)
from swcstudio.core.provenance.canonical import canonical_swc, sha256_hex
from swcstudio.core.provenance.diff import compute_swc_diff, summarize_diff
from swcstudio.core.provenance.env import capture_env
from swcstudio.core.provenance.events import (
    Event,
    append_event,
    canonical_json,
    compute_event_id,
    new_session_id,
)
from swcstudio.core.provenance.header import (
    format_root_line,
    format_tip_line,
    write_prov_header,
)
from swcstudio.core.provenance.index import (
    ensure_schema,
    insert_ai_run,
    insert_event,
    open_index,
)
from swcstudio.core.provenance.lockfile import LockFile
from swcstudio.core.provenance.objects import ObjectStore
from swcstudio.core.provenance.ops import OpKind, is_ai_op, validate_op_record
from swcstudio.core.provenance.refs import (
    DEFAULT_BRANCH,
    init_refs,
    read_branch,
    read_head,
    write_branch,
)

__all__ = [
    "FORMAT_VERSION",
    "OpResult",
    "tracked_op",
    "tracked_session",
    "init_history",
    "history_dir_for",
    "current_swc_path_for",
]


# Per-history-store format version, written to ``.history/version``.
# Independent of the per-event ``schema_version`` and the SQLite
# ``INDEX_SCHEMA_VERSION`` (spec §17).
FORMAT_VERSION = 1


# ----------------------------------------------------------------------
# path helpers — where everything lives on disk
# ----------------------------------------------------------------------


def _output_dir_for(swc_path: str | os.PathLike[str]) -> Path:
    """Return the ``<stem>_swc_studio_output/`` dir next to ``swc_path``.

    Mirrors swcstudio.core.reporting.output_dir_for_file but does not
    import that module (which is being deleted in a later slice).
    """
    p = Path(swc_path)
    if p.parent.name.endswith("_swc_studio_output"):
        return p.parent
    return p.parent / f"{p.stem}_swc_studio_output"


def history_dir_for(swc_path: str | os.PathLike[str]) -> Path:
    """Return the transient working ``.history/`` directory for ``swc_path``.

    The durable user-visible store is ``<stem>_history.swcstudio``.
    Writers materialize this directory while committing, then archive it
    and remove the working tree.
    """
    return _output_dir_for(swc_path) / ".history"


def current_swc_path_for(swc_path: str | os.PathLike[str]) -> Path:
    """Return the ``<stem>_current.swc`` path for ``swc_path``."""
    p = Path(swc_path)
    out = _output_dir_for(p)
    return out / f"{p.stem}_current.swc"


def init_history(
    swc_path: str | os.PathLike[str],
    *,
    branch: str = DEFAULT_BRANCH,
) -> Path:
    """Initialize ``.history/`` for ``swc_path`` if it does not exist.

    Creates the directory tree, writes ``.history/version``,
    initializes refs (HEAD + empty default branch), and ensures the
    SQLite index has its schema. Idempotent.
    """
    hist = history_dir_for(swc_path)
    ensure_history_materialized(swc_path, hist)
    hist.mkdir(parents=True, exist_ok=True)
    version_file = hist / "version"
    if not version_file.exists():
        version_file.write_text(f"{FORMAT_VERSION}\n", encoding="utf-8")
    init_refs(hist, branch=branch)
    ensure_history_manifest(hist, swc_path)
    # Touch the index so subsequent reads/writes don't have to test for it.
    conn = open_index(hist)
    try:
        ensure_schema(conn)
    finally:
        conn.close()
    return hist


def _check_format_version(hist: Path) -> None:
    """Spec §17: refuse to write to a history dir from a newer format."""
    version_file = hist / "version"
    if not version_file.exists():
        return
    try:
        v = int(version_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return
    if v > FORMAT_VERSION:
        raise RuntimeError(
            f"history at {hist} was written by a newer SWC-Studio "
            f"(format v{v}); please upgrade. This build supports up to v{FORMAT_VERSION}."
        )


# ----------------------------------------------------------------------
# the public API surface
# ----------------------------------------------------------------------


@dataclass
class OpResult:
    """Returned to the caller after a successful tracked_op block.

    Attributes:
      commit_sha: the new commit's event id ("sha256:...")
      input_sha:  canonical sha of the SWC bytes before the op (None if first)
      output_sha: canonical sha of the SWC bytes after the op
      diff_ref:   sha of the diff blob (None if first commit / no change)
      ai_run_ref: sha of the AI-run blob (only for AI ops)
      branch:     the branch this commit landed on
      message:    the message recorded
    """

    commit_sha: str
    input_sha: str | None
    output_sha: str
    diff_ref: str | None
    ai_run_ref: str | None
    branch: str
    message: str


class _TrackedContext:
    """Internal — base class shared by tracked_op and tracked_session.

    Owns the lock, input read, output capture, and the commit write.
    Subclasses differ in how they collect ``ops`` (one for tracked_op,
    many for tracked_session).
    """

    def __init__(
        self,
        swc_path: str | os.PathLike[str],
        *,
        message: str = "",
        actor: str | None = None,
        derived_from: dict[str, Any] | None = None,
    ) -> None:
        self.swc_path = Path(swc_path)
        self.hist = history_dir_for(swc_path)
        self.message = message
        self._actor = actor or _default_actor()
        self._derived_from = derived_from
        self._lock = LockFile(self.hist)
        self._store: ObjectStore | None = None
        self._input_bytes: bytes | None = None
        self._input_sha: str | None = None
        self._output_bytes: bytes | None = None
        self._ops: list[dict[str, Any]] = []
        self._ai_runs: list[tuple[str, AIRun]] = []  # (op_index_marker, run); set by add_ai_run
        self._session_id: str = new_session_id()
        self._started_at: str = _utcnow()
        self.result: OpResult | None = None

    # ------------------------------------------------------------------
    # context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "_TrackedContext":
        init_history(self.swc_path)
        _check_format_version(self.hist)
        self._lock.acquire()
        try:
            self._store = ObjectStore(self.hist / "objects")
            # Snapshot input bytes. If the dataset has never been
            # tracked (no current.swc yet), fall back to the source
            # path. If neither exists, treat as a fresh dataset
            # (input_sha=None for the first commit).
            input_path = current_swc_path_for(self.swc_path)
            if input_path.exists():
                self._input_bytes = input_path.read_bytes()
            elif self.swc_path.exists():
                self._input_bytes = self.swc_path.read_bytes()
            else:
                self._input_bytes = None
            if self._input_bytes is not None:
                self._input_sha = sha256_hex(canonical_swc(self._input_bytes))
        except BaseException:
            self._lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self._commit()
        finally:
            self._lock.release()
            archive_history_dir(self.hist, self.swc_path, remove_dir=True)

    # ------------------------------------------------------------------
    # caller-facing API used inside the with-block
    # ------------------------------------------------------------------

    @property
    def input_bytes(self) -> bytes | None:
        """The SWC bytes the body started from (None if first commit)."""
        return self._input_bytes

    @property
    def input_sha(self) -> str | None:
        return self._input_sha

    def set_output(self, data: bytes) -> None:
        """Record the post-op SWC bytes. Required exactly once per op."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("set_output expects bytes")
        self._output_bytes = bytes(data)

    # ------------------------------------------------------------------
    # commit protocol — runs at __exit__ time on success
    # ------------------------------------------------------------------

    def _commit(self) -> None:
        if self._output_bytes is None:
            raise RuntimeError(
                "tracked_op body did not call op.set_output(bytes); "
                "no output SWC to commit"
            )

        out_canonical = canonical_swc(self._output_bytes)
        output_sha = sha256_hex(out_canonical)

        store = self._store
        assert store is not None  # set in __enter__

        # Diff blob (skip if input_sha is None — first commit has no
        # before-state to diff against; the snapshot itself is the
        # record).
        diff_ref: str | None = None
        node_changes_for_op: dict[int, list[dict[str, Any]]] = {}
        if self._input_bytes is not None:
            payload = compute_swc_diff(
                self._input_bytes, self._output_bytes,
                from_sha="sha256:" + (self._input_sha or ""),
                to_sha="sha256:" + output_sha,
            )
            if payload.node_changes or payload.topology_changes:
                diff_blob = canonical_json(payload.to_json_obj())
                diff_ref = "sha256:" + store.put(diff_blob)
            # Inline summaries get attached to each op below.
            for i in range(len(self._ops)):
                self._ops[i].setdefault("summary", summarize_diff(payload))
            # node_changes routed to SQLite for query_node_changes
            for i in range(len(self._ops)):
                node_changes_for_op[i] = list(payload.node_changes)

        # AI-run blobs: write each, attach refs to the matching ops.
        for i, run in self._enumerate_ai_runs():
            run.status = AIRunStatus.FINISHED
            run.finished_at = _utcnow()
            ai_blob = ai_run_to_blob_bytes(run)
            ai_ref = "sha256:" + store.put(ai_blob)
            self._ops[i]["ai_run_ref"] = ai_ref

        # Validate every op's shape one last time before we hash + commit.
        for op in self._ops:
            validate_op_record(op)

        # Build the event. parent = current branch tip (None if first).
        head = read_head(self.hist)
        parent = read_branch(self.hist, head)

        event = Event(
            schema_version=1,
            kind="commit",
            parent=parent,
            branch=head,
            ts=self._started_at,
            actor={"os_user": self._actor},
            tool=_tool_identity(),
            session_id=self._session_id,
            message=self.message,
            ops=self._ops,
            input_sha=self._input_sha,
            output_sha=output_sha,
            diff_ref=diff_ref,
            derived_from=self._derived_from,
        )
        event.id = compute_event_id(event.to_json_obj())

        # ---- Atomicity ----
        # Step 1: append the event line. If we crash after this, the
        # commit "exists" in the JSONL log but no ref points at it —
        # a future rebuild_index would find it as an unreachable
        # commit, harmless.
        append_event(self.hist / "events.jsonl", event)

        # Step 2: index it (best-effort; recoverable via rebuild_index
        # if the index falls behind).
        conn = open_index(self.hist)
        try:
            ensure_schema(conn)
            insert_event(conn, event, node_changes_for_op=node_changes_for_op)
            for i, run in self._enumerate_ai_runs():
                ai_ref_str = self._ops[i].get("ai_run_ref")
                if ai_ref_str:
                    insert_ai_run(
                        conn,
                        ai_run_ref=ai_ref_str,
                        commit_sha=event.id,
                        model_sha=str(run.params.get("model_sha", "")) or None,
                        model_version=str(run.params.get("model_version", "")) or None,
                        started_at=run.started_at,
                        finished_at=run.finished_at,
                        env_hash=run.env_hash,
                        metrics=run.metrics,
                        params=run.params,
                    )
        finally:
            conn.close()

        # Step 3: advance the branch ref to the new commit. POSIX-atomic
        # rename ensures we either see the old tip or the new tip,
        # never a half-written ref file.
        write_branch(self.hist, head, event.id)

        # Step 4: materialize current.swc with the refreshed @PROV
        # header. This is the file the user actually opens.
        self._materialize_current_swc(event.id, parent, head, output_sha, out_canonical)

        self.result = OpResult(
            commit_sha=event.id,
            input_sha=self._input_sha,
            output_sha=output_sha,
            diff_ref=diff_ref,
            ai_run_ref=self._ops[0].get("ai_run_ref") if self._ops else None,
            branch=head,
            message=self.message,
        )

    # ------------------------------------------------------------------
    # @PROV header stamping
    # ------------------------------------------------------------------

    def _materialize_current_swc(
        self,
        commit_sha: str,
        parent: str | None,
        branch: str,
        output_sha: str,
        out_canonical: bytes,
    ) -> None:
        # Count commits on this branch by walking from tip → root via
        # SQLite (we just inserted the new commit, so it's there).
        ops_count = self._count_branch_commits(branch)

        repo = history_repo_info(self.hist, self.swc_path)
        root_sha_short, file_name, created = self._root_line_inputs()
        root_line = format_root_line(
            root_sha=root_sha_short,
            file_name=file_name,
            created_utc=created,
            repo=archive_name_for(self.swc_path),
            repo_id=str(repo.get("repo_id", "")) or None,
        )
        tip_line = format_tip_line(
            tip=commit_sha,
            parent=parent,
            ops=ops_count,
            tool=f"{_tool_identity()['name']}@{_tool_identity()['version']}",
            actor=self._actor,
            updated_utc=self._started_at,
            sidecar=archive_name_for(self.swc_path),
            repo_id=str(repo.get("repo_id", "")) or None,
        )

        # Use the *output* bytes the caller produced (preserves their
        # float formatting / comments / etc.) and splice the @PROV
        # lines on top.
        body_bytes = self._output_bytes if self._output_bytes is not None else out_canonical
        stamped = write_prov_header(body_bytes, root_line=root_line, tip_line=tip_line)
        out_path = current_swc_path_for(self.swc_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(stamped)

    def _root_line_inputs(self) -> tuple[str, str, str]:
        """Return (root_sha_for_header, file_name, created_utc).

        The root is the dataset's *original* sha. We persist it once
        in ``.history/root.json`` so subsequent commits keep producing
        the same root line even if the original file has been moved
        or replaced.
        """
        marker = self.hist / "root.json"
        if marker.exists():
            import json
            d = json.loads(marker.read_text(encoding="utf-8"))
            return d["root_sha"], d.get("file_name", self.swc_path.name), d.get("created", _utcnow())

        # First commit on this dataset — record it.
        if self._input_bytes is not None:
            r = sha256_hex(canonical_swc(self._input_bytes))
        elif self._output_bytes is not None:
            r = sha256_hex(canonical_swc(self._output_bytes))
        else:
            r = "0" * 64
        created = _utcnow()
        import json
        marker.write_text(
            json.dumps(
                {"root_sha": "sha256:" + r, "file_name": self.swc_path.name, "created": created},
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        return "sha256:" + r, self.swc_path.name, created

    def _count_branch_commits(self, branch: str) -> int:
        """Count commits on ``branch`` (cheap SQL aggregate)."""
        conn = open_index(self.hist)
        try:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT COUNT(*) FROM commits WHERE branch = ?", (branch,)
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # AI-run plumbing — populated by tracked_op for AI ops
    # ------------------------------------------------------------------

    def _enumerate_ai_runs(self) -> Iterator[tuple[int, AIRun]]:
        """Yield (op_index, AIRun) pairs for ops that registered an AI run."""
        for i, run in self._ai_runs:
            yield int(i), run


# ----------------------------------------------------------------------
# tracked_op — single atomic op
# ----------------------------------------------------------------------


@contextmanager
def tracked_op(
    swc_path: str | os.PathLike[str],
    *,
    kind: str | OpKind,
    params: dict[str, Any] | None = None,
    message: str = "",
    actor: str | None = None,
    is_ai: bool | None = None,
    derived_from: dict[str, Any] | None = None,
) -> Iterator[_TrackedContext]:
    """Wrap a single SWC mutation in a provenance commit.

    Use::

        with tracked_op(path, kind="set_radius",
                        params={"node_ids": [5], "radius": 0.4},
                        message="Manual radii cleanup") as op:
            new_bytes = mutate(op.input_bytes, ...)
            op.set_output(new_bytes)

    For AI ops, set ``is_ai=True`` (or rely on auto-detect via
    :func:`ops.is_ai_op`). The wrapper captures an env fingerprint
    on entry, builds an :class:`AIRun` record, and writes it as a
    separate blob alongside the diff.
    """
    ctx = _TrackedContext(
        swc_path,
        message=message,
        actor=actor,
        derived_from=derived_from,
    )
    kind_str = kind.value if isinstance(kind, OpKind) else str(kind)
    op_record: dict[str, Any] = {
        "kind": kind_str,
        "params": dict(params or {}),
    }
    ctx._ops.append(op_record)

    # AI capture: env fingerprint + AIRun in RUNNING state.
    auto_ai = is_ai_op(kind_str) if is_ai is None else bool(is_ai)
    if auto_ai:
        env = capture_env()
        env_blob = canonical_json(env)
        with ctx as live:
            store = live._store
            assert store is not None
            env_h = store.put(env_blob)
            run = build_ai_run(
                started_at=live._started_at,
                params=dict(params or {}),
                source_version=_tool_identity(),
                env_hash=env_h,
            )
            live._ai_runs.append((0, run))
            yield live
        return

    # Non-AI single op.
    with ctx as live:
        yield live


# ----------------------------------------------------------------------
# tracked_session — long-lived (GUI) with multiple sub-ops
# ----------------------------------------------------------------------


@contextmanager
def tracked_session(
    swc_path: str | os.PathLike[str],
    *,
    message: str = "",
    actor: str | None = None,
) -> Iterator["_SessionHandle"]:
    """Wrap a GUI session of many sub-ops in a single commit.

    Use::

        with tracked_session(path, message="Manual cleanup") as session:
            for action in user_actions:
                session.add_op(kind="set_radius", params={...})
            session.set_output(final_bytes)

    Sub-ops are appended in order and become the ``ops`` list of one
    commit on exit. AI sub-ops are supported via
    :meth:`_SessionHandle.add_ai_op`, which captures an env at the
    time the AI ran and attaches an AIRun to that sub-op.
    """
    ctx = _TrackedContext(swc_path, message=message, actor=actor)
    handle = _SessionHandle(ctx)
    with ctx:
        yield handle


class _SessionHandle:
    """Caller-facing handle for tracked_session."""

    def __init__(self, ctx: _TrackedContext) -> None:
        self._ctx = ctx

    @property
    def input_bytes(self) -> bytes | None:
        return self._ctx.input_bytes

    @property
    def input_sha(self) -> str | None:
        return self._ctx.input_sha

    def add_op(
        self,
        *,
        kind: str | OpKind,
        params: dict[str, Any] | None = None,
    ) -> int:
        """Record one sub-op. Returns its index for AI-run attachment."""
        kind_str = kind.value if isinstance(kind, OpKind) else str(kind)
        self._ctx._ops.append({"kind": kind_str, "params": dict(params or {})})
        return len(self._ctx._ops) - 1

    def add_ai_op(
        self,
        *,
        kind: str | OpKind,
        params: dict[str, Any] | None = None,
    ) -> int:
        """Record an AI sub-op with env capture. Returns its index."""
        idx = self.add_op(kind=kind, params=params)
        env = capture_env()
        env_blob = canonical_json(env)
        store = self._ctx._store
        if store is None:
            # tracked_session has not entered the lock yet; defer the
            # actual blob put to commit time. Stash the bytes on the
            # AIRun so we still have it.
            env_h = ""
        else:
            env_h = store.put(env_blob)
        run = build_ai_run(
            started_at=_utcnow(),
            params=dict(params or {}),
            source_version=_tool_identity(),
            env_hash=env_h,
        )
        self._ctx._ai_runs.append((idx, run))
        return idx

    def set_output(self, data: bytes) -> None:
        self._ctx.set_output(data)


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_actor() -> str:
    """OS username — actor identity per spec §2."""
    import getpass
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _tool_identity() -> dict[str, str]:
    """Per spec §2: tool = name + version + (optional) git short sha."""
    name = "swcstudio"
    version = getattr(swcstudio, "__version__", "0.0.0")
    git_sha = _git_short_sha()
    out = {"name": name, "version": str(version)}
    if git_sha:
        out["git_sha"] = git_sha
    return out


def _git_short_sha() -> str | None:
    """Best-effort ``git rev-parse --short HEAD`` for source installs.

    Returns None for pip installs (no .git) or if git isn't on PATH.
    Cheap fail: stdlib only, suppress all errors. We never want to
    crash a real edit because we couldn't read git metadata.
    """
    try:
        import subprocess
        repo_root = Path(swcstudio.__file__).resolve().parent.parent
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None
