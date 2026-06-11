"""``swcstudio history ...`` subcommand group.

Implements PROVENANCE_SPEC §13. The full v1 surface (all 12 verbs)
ships in this slice. Each verb is a thin wrapper over the
``swcstudio.core.provenance`` API — no algorithmic logic lives here.

This module is split out from the main ``cli.py`` to keep the new
provenance commands isolated and to keep the diff to ``cli.py``
itself trivially small (one import + one ``add_history_subparser``
call + one dispatch ``if`` arm).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swcstudio.core.provenance import (
    BlobCorruptError,
    BlobNotFoundError,
    LockHeldError,
    ObjectStore,
    RefError,
    TagExistsError,
    create_tag,
    current_swc_path_for,
    delete_branch,
    history_dir_for,
    init_history,
    init_refs,
    iter_events,
    list_branches,
    list_tags,
    migrate_legacy_output_dir,
    needs_migration,
    open_index,
    rebuild_index,
    read_branch,
    read_head,
    read_tag,
    render_commit_text,
    render_history_log_text,
    write_branch,
    write_head,
)

__all__ = [
    "add_history_subparser",
    "dispatch_history",
]


# ----------------------------------------------------------------------
# parser plumbing
# ----------------------------------------------------------------------


def add_history_subparser(sub: argparse._SubParsersAction) -> None:
    """Register the ``history`` tool group on the main subparsers."""
    history = sub.add_parser(
        "history",
        help="Provenance & versioning (per PROVENANCE_SPEC.md)",
        description="Inspect, branch, tag, checkout, verify, and export the provenance history of an SWC dataset.",
    )
    hsub = history.add_subparsers(dest="history_cmd")

    # log
    log = hsub.add_parser("log", help="Show commit history for a file")
    log.add_argument("file", type=Path)
    log.add_argument("--branch")
    log.add_argument("--actor")
    log.add_argument("--since")
    log.add_argument("--until")
    log.add_argument("--limit", type=int)

    # show
    show = hsub.add_parser("show", help="Show details for one commit")
    show.add_argument("file", type=Path)
    show.add_argument("sha", help="Full or short commit sha")
    show.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="fmt",
    )

    # checkout
    checkout = hsub.add_parser(
        "checkout",
        help="Materialize a past state as a read-only SWC",
    )
    checkout.add_argument("file", type=Path)
    checkout.add_argument("sha")
    checkout.add_argument(
        "-o", "--output",
        type=Path,
        help="Where to write the materialized SWC (default: <stem>_<short_sha>.swc next to the source)",
    )

    # branch
    branch = hsub.add_parser("branch", help="List branches or create a new one")
    branch.add_argument("file", type=Path)
    branch.add_argument("name", nargs="?", help="If given, create this branch")
    branch.add_argument("--from", dest="from_sha", help="Commit sha to branch from (default HEAD)")

    # switch
    switch = hsub.add_parser("switch", help="Switch the active branch")
    switch.add_argument("file", type=Path)
    switch.add_argument("name")

    # tag
    tag = hsub.add_parser("tag", help="List tags or create one")
    tag.add_argument("file", type=Path)
    tag.add_argument("name", nargs="?")
    tag.add_argument("sha", nargs="?", help="Commit sha (default HEAD tip)")

    # checkpoint
    cp = hsub.add_parser(
        "checkpoint",
        help="Materialize a past commit as a labeled .swc next to current.swc",
    )
    cp.add_argument("file", type=Path)
    cp.add_argument("sha")
    cp.add_argument("--label", required=True)

    # reproduce
    rep = hsub.add_parser(
        "reproduce",
        help="Emit a reproduce.yaml for an AI commit",
    )
    rep.add_argument("file", type=Path)
    rep.add_argument("sha")
    rep.add_argument("-o", "--output", type=Path)

    # reindex
    ri = hsub.add_parser("reindex", help="Rebuild index.sqlite from events.jsonl")
    ri.add_argument("file", type=Path)

    # verify
    vf = hsub.add_parser("verify", help="Hash-check every blob")
    vf.add_argument("file", type=Path)

    # gc
    gc = hsub.add_parser("gc", help="Remove blobs no branch or tag references")
    gc.add_argument("file", type=Path)
    gc.add_argument("--dry-run", action="store_true",
                    help="Only print what would be removed")

    # export-crate
    ec = hsub.add_parser("export-crate", help="Bundle file + history as RO-Crate")
    ec.add_argument("file", type=Path)
    ec.add_argument("-o", "--output", type=Path, required=True,
                    help="Output directory for the crate")
    ec.add_argument("--with-pii", action="store_true",
                    help="Include hostnames/usernames/paths (default: stripped)")

    # init (utility — implicit on first tracked_op, but useful for migration)
    init_p = hsub.add_parser("init", help="Initialize .history/ and migrate any legacy output")
    init_p.add_argument("file", type=Path)


# ----------------------------------------------------------------------
# dispatch
# ----------------------------------------------------------------------


def dispatch_history(args: argparse.Namespace) -> int:
    """Run the requested ``history`` subcommand. Returns process exit code."""
    cmd = getattr(args, "history_cmd", None)
    if not cmd:
        print("usage: swcstudio history <subcommand> [...]", file=sys.stderr)
        return 2

    try:
        return _DISPATCH[cmd](args)
    except (LockHeldError, RefError, TagExistsError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


# ----------------------------------------------------------------------
# verb implementations
# ----------------------------------------------------------------------


def _cmd_log(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    out = render_history_log_text(
        hist,
        branch=args.branch,
        actor=args.actor,
        since=args.since,
        until=args.until,
        limit=args.limit,
    )
    print(out, end="")
    return 0


def _cmd_show(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    if args.fmt == "json":
        ev = _resolve_event_or_die(hist, args.sha)
        print(json.dumps(ev.to_json_obj(), indent=2, sort_keys=True))
    else:
        print(render_commit_text(hist, args.sha), end="")
    return 0


def _cmd_checkout(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    ev = _resolve_event_or_die(hist, args.sha)
    bytes_at_sha = _materialize_state_at(hist, ev.id)
    short = ev.id.removeprefix("sha256:")[:12]
    if args.output:
        out_path = Path(args.output)
    else:
        src = Path(args.file)
        out_path = src.parent / f"{src.stem}_{short}.swc"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes_at_sha)
    print(f"checked out {short} -> {out_path}")
    return 0


def _cmd_branch(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    if args.name is None:
        for name in list_branches(hist):
            tip = read_branch(hist, name)
            star = "*" if name == read_head(hist) else " "
            short = (tip or "").removeprefix("sha256:")[:12] or "(empty)"
            print(f"{star} {name:<20} {short}")
        return 0
    # Create
    if args.from_sha is None:
        head = read_head(hist)
        sha = read_branch(hist, head)
        if sha is None:
            print(f"error: cannot branch from empty branch {head!r}", file=sys.stderr)
            return 1
    else:
        sha = _resolve_event_or_die(hist, args.from_sha).id
    write_branch(hist, args.name, sha)
    print(f"created branch {args.name!r} at {sha.removeprefix('sha256:')[:12]}")
    return 0


def _cmd_switch(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    write_head(hist, args.name)
    print(f"switched to branch {args.name!r}")
    return 0


def _cmd_tag(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    if args.name is None:
        for name in list_tags(hist):
            sha = read_tag(hist, name)
            print(f"{name:<24} {(sha or '').removeprefix('sha256:')[:12]}")
        return 0
    if args.sha is None:
        head = read_head(hist)
        sha = read_branch(hist, head)
        if sha is None:
            print(f"error: cannot tag empty branch {head!r}", file=sys.stderr)
            return 1
    else:
        sha = _resolve_event_or_die(hist, args.sha).id
    create_tag(hist, args.name, sha)
    print(f"created tag {args.name!r} -> {sha.removeprefix('sha256:')[:12]}")
    return 0


def _cmd_checkpoint(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    ev = _resolve_event_or_die(hist, args.sha)
    body = _materialize_state_at(hist, ev.id)
    src = Path(args.file)
    out_dir = current_swc_path_for(src).parent
    label = "".join(c if c.isalnum() or c in "-_" else "_" for c in args.label)
    out_path = out_dir / f"{src.stem}_{label}.swc"
    out_path.write_bytes(body)
    print(f"materialized checkpoint -> {out_path}")
    return 0


def _cmd_reproduce(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    ev = _resolve_event_or_die(hist, args.sha)
    ai_refs = [op.get("ai_run_ref") for op in ev.ops if op.get("ai_run_ref")]
    if not ai_refs:
        print(f"error: commit {args.sha} has no AI runs", file=sys.stderr)
        return 1

    store = ObjectStore(hist / "objects")
    blob = json.loads(store.get(ai_refs[0].removeprefix("sha256:")))

    yaml_text = _format_reproduce_yaml(ev, blob, args.file)
    out_path = args.output or Path(f"reproduce_{ev.id.removeprefix('sha256:')[:12]}.yaml")
    out_path.write_text(yaml_text, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


def _cmd_reindex(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    n = rebuild_index(hist)
    print(f"reindexed {n} commits")
    return 0


def _cmd_verify(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    store = ObjectStore(hist / "objects")
    n_ok = n_bad = 0
    for sha in store.iter_shas():
        try:
            store.verify(sha)
            n_ok += 1
        except (BlobCorruptError, BlobNotFoundError) as e:
            n_bad += 1
            print(f"FAIL {sha}: {e}")
    print(f"verified {n_ok} blobs, {n_bad} failures")
    return 1 if n_bad else 0


def _cmd_gc(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    store = ObjectStore(hist / "objects")
    reachable = _reachable_blobs(hist)
    all_shas = set(store.iter_shas())
    unreachable = sorted(all_shas - reachable)
    if not unreachable:
        print("nothing to remove")
        return 0
    if args.dry_run:
        for sha in unreachable:
            print(f"would remove {sha}")
        print(f"({len(unreachable)} blobs would be removed)")
        return 0
    for sha in unreachable:
        store.remove(sha)
    print(f"removed {len(unreachable)} blobs")
    return 0


def _cmd_export_crate(args) -> int:
    hist = history_dir_for(args.file)
    _ensure_history_or_die(args.file, hist)
    # Crate writer lives in slice 13 (provenance.crate). For the v1 CLI
    # we surface the verb so it's discoverable; the implementation lives
    # in the dedicated module.
    from swcstudio.core.provenance.crate import export_crate
    out = export_crate(args.file, args.output, with_pii=args.with_pii)
    print(f"wrote crate -> {out}")
    return 0


def _cmd_init(args) -> int:
    hist = history_dir_for(args.file)
    if needs_migration(args.file):
        outcome = migrate_legacy_output_dir(args.file)
        msg = "initialized .history/"
        if outcome.imported_commit:
            msg += f"; imported state from {outcome.imported_from.name}"
        if outcome.legacy_files_kept:
            msg += f"; kept {outcome.legacy_files_kept} legacy file(s)"
        print(msg)
    elif hist.exists():
        print("history already initialized")
    else:
        init_history(args.file)
        print("initialized .history/")
    return 0


_DISPATCH = {
    "log":          _cmd_log,
    "show":         _cmd_show,
    "checkout":     _cmd_checkout,
    "branch":       _cmd_branch,
    "switch":       _cmd_switch,
    "tag":          _cmd_tag,
    "checkpoint":   _cmd_checkpoint,
    "reproduce":    _cmd_reproduce,
    "reindex":      _cmd_reindex,
    "verify":       _cmd_verify,
    "gc":           _cmd_gc,
    "export-crate": _cmd_export_crate,
    "init":         _cmd_init,
}


# ----------------------------------------------------------------------
# helpers shared by verbs
# ----------------------------------------------------------------------


def _ensure_history_or_die(file_path: Path, hist: Path) -> None:
    if not hist.exists():
        raise FileNotFoundError(
            f"no .history/ at {hist}; run 'swcstudio history init {file_path}' first"
        )


def _resolve_event_or_die(hist: Path, sha_or_prefix: str):
    """Find an event by full sha or unique short prefix.

    Reads events.jsonl directly so this works even when the SQLite
    index is out of sync.
    """
    target = sha_or_prefix.removeprefix("sha256:").lower()
    if len(target) < 6:
        raise FileNotFoundError(f"sha prefix too short: {sha_or_prefix!r}")
    matches = []
    for ev in iter_events(hist / "events.jsonl"):
        ev_hex = (ev.id or "").removeprefix("sha256:").lower()
        if ev_hex.startswith(target):
            matches.append(ev)
    if not matches:
        raise FileNotFoundError(f"no commit matching {sha_or_prefix!r}")
    if len(matches) > 1:
        raise FileNotFoundError(
            f"ambiguous commit prefix {sha_or_prefix!r} matches {len(matches)} commits"
        )
    return matches[0]


def _materialize_state_at(hist: Path, commit_sha: str) -> bytes:
    """Reconstruct canonical SWC bytes at ``commit_sha``.

    v1 strategy (no snapshot blobs yet): anchor at the active branch's
    ``current.swc`` (which we always materialize at the tip), then
    walk **backward from the tip toward the target**, inverting each
    intervening diff. Once we reach the target, its own diff is the
    last one we DON'T undo — we want to land at the target's output
    state, which is exactly the state right after applying its diff.

    Future enhancement (slice 9b): periodic snapshot blobs let us
    anchor at the nearest snapshot ≤ target instead, replacing the
    tip-anchored backward walk with O(1) anchoring + at most 49
    forward replays.
    """
    by_id = {ev.id: ev for ev in iter_events(hist / "events.jsonl")}
    if commit_sha not in by_id:
        raise FileNotFoundError(f"unknown commit {commit_sha}")

    # Find the tip from the active branch.
    head = read_head(hist)
    tip = read_branch(hist, head)
    if tip is None or tip not in by_id:
        # Fall back to scanning every branch for one that contains
        # commit_sha (covers the case where target is on a non-active
        # branch).
        tip = _find_branch_tip_containing(hist, by_id, commit_sha)
        if tip is None:
            raise FileNotFoundError(f"commit {commit_sha} not reachable from any branch")

    # Walk parents from tip back until we hit target. Build the
    # ordered chain [tip, tip-1, ..., target].
    chain: list = []
    cur = tip
    while cur is not None and cur in by_id:
        chain.append(by_id[cur])
        if cur == commit_sha:
            break
        cur = by_id[cur].parent
    if not chain or chain[-1].id != commit_sha:
        # Target is on a different branch than tip; try every branch.
        tip = _find_branch_tip_containing(hist, by_id, commit_sha)
        if tip is None:
            raise FileNotFoundError(f"commit {commit_sha} not on any branch's history")
        chain = []
        cur = tip
        while cur is not None and cur in by_id:
            chain.append(by_id[cur])
            if cur == commit_sha:
                break
            cur = by_id[cur].parent
        if not chain or chain[-1].id != commit_sha:
            raise FileNotFoundError(
                f"cannot reach commit {commit_sha} from any branch tip"
            )

    # Anchor at current.swc (state at tip), strip @PROV header, then
    # undo every diff between tip and target (exclusive of target's own
    # diff — undoing target's diff would land us at target's *input*
    # state, which is one commit too far back).
    cur_path = current_swc_path_for(_swc_for_history(hist))
    if not cur_path.exists():
        raise FileNotFoundError(
            f"no current.swc to anchor checkout at {commit_sha}"
        )
    from swcstudio.core.provenance.header import strip_prov_lines
    state = strip_prov_lines(cur_path.read_bytes())

    # If target IS the tip, no undo needed — return current state.
    if chain[0].id == commit_sha:
        return state

    store = ObjectStore(hist / "objects")
    # chain[0] is tip; chain[-1] is target. Undo diffs at indices
    # 0, 1, ..., (len-2). Each undo moves us one commit earlier.
    for i in range(0, len(chain) - 1):
        ev = chain[i]
        if not ev.diff_ref:
            continue
        try:
            diff = json.loads(store.get(ev.diff_ref.removeprefix("sha256:")))
            state = _undo_diff(state, diff)
        except (BlobNotFoundError, ValueError):
            pass
    return state


def _find_branch_tip_containing(hist: Path, by_id: dict, commit_sha: str) -> str | None:
    """Return the tip of any branch that has ``commit_sha`` in its parent chain."""
    for name in list_branches(hist):
        tip = read_branch(hist, name)
        if not tip:
            continue
        cur = tip
        while cur is not None and cur in by_id:
            if cur == commit_sha:
                return tip
            cur = by_id[cur].parent
    return None


def _undo_diff(state: bytes, diff: dict) -> bytes:
    """Apply the inverse of a diff blob to reconstruct the prior state.

    Linear walk over canonical row form. Sufficient for v1 checkout
    of typical histories; future snapshot-based replay (slice 9b)
    will replace this with O(1) anchoring.
    """
    rows = {}
    for line in state.decode("utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) < 7:
            continue
        rows[int(float(parts[0]))] = parts

    # Undo node_changes
    for c in diff.get("node_changes", []):
        nid = int(c["id"])
        field = c["field"]
        before = c["before"]
        if nid not in rows:
            continue
        col = {"type": 1, "x": 2, "y": 3, "z": 4, "radius": 5}.get(field)
        if col is None:
            continue
        rows[nid][col] = str(before)

    # Undo topology_changes
    for c in diff.get("topology_changes", []):
        kind = c.get("kind")
        nid = int(c["id"])
        if kind == "add":
            rows.pop(nid, None)
        elif kind == "remove":
            row_text = c.get("row")
            if row_text:
                parts = str(row_text).split()
                if len(parts) >= 7:
                    rows[nid] = parts
        elif kind == "reparent":
            if nid in rows:
                rows[nid][6] = str(c.get("before"))

    out_lines = [" ".join(rows[k]) for k in sorted(rows)]
    return ("\n".join(out_lines) + "\n").encode("utf-8")


def _swc_for_history(hist: Path) -> Path:
    """Reverse-map a .history/ dir back to the SWC it tracks.

    .history/ lives at <stem>_swc_studio_output/.history/, so the
    SWC is at <parent>/<stem>.swc.
    """
    out_dir = hist.parent
    if out_dir.name.endswith("_swc_studio_output"):
        stem = out_dir.name[: -len("_swc_studio_output")]
        return out_dir.parent / f"{stem}.swc"
    return out_dir.parent / f"{out_dir.name}.swc"


def _reachable_blobs(hist: Path) -> set[str]:
    """Walk every branch + tag, mark every blob that's referenced."""
    reachable: set[str] = set()
    by_id = {ev.id: ev for ev in iter_events(hist / "events.jsonl")}
    seeds: list[str] = []
    for name in list_branches(hist):
        tip = read_branch(hist, name)
        if tip:
            seeds.append(tip)
    for name in list_tags(hist):
        sha = read_tag(hist, name)
        if sha:
            seeds.append(sha)

    seen_commits: set[str] = set()
    stack = list(seeds)
    while stack:
        cur = stack.pop()
        if cur in seen_commits or cur not in by_id:
            continue
        seen_commits.add(cur)
        ev = by_id[cur]
        if ev.diff_ref:
            reachable.add(ev.diff_ref.removeprefix("sha256:"))
        for op in ev.ops:
            ai_ref = op.get("ai_run_ref")
            if ai_ref:
                reachable.add(ai_ref.removeprefix("sha256:"))
                # Also pull in env blob via the ai_run blob.
                try:
                    store = ObjectStore(hist / "objects")
                    blob = json.loads(store.get(ai_ref.removeprefix("sha256:")))
                    if blob.get("env_hash"):
                        reachable.add(blob["env_hash"])
                    for art in blob.get("artifacts", []):
                        ref = (art.get("sha256") or "")
                        if ref:
                            reachable.add(ref.removeprefix("sha256:"))
                except (BlobNotFoundError, ValueError):
                    pass
        if ev.parent:
            stack.append(ev.parent)
    return reachable


def _format_reproduce_yaml(ev, ai_blob: dict, source_path: Path) -> str:
    """Emit a minimal reproduce.yaml for an AI commit.

    Matches the shape advertised in PROVENANCE_SPEC §12.
    """
    params = ai_blob.get("params", {}) or {}
    artifacts = {a.get("name"): a.get("sha256") for a in ai_blob.get("artifacts", []) or []}
    lines = [
        "schema_version: 1",
        f"op:        {ev.ops[0].get('kind') if ev.ops else 'unknown'}",
        f"input:     {{sha256: {ev.input_sha or 'null'}, path: {source_path.name!r}}}",
        f"output:    {{sha256: {ev.output_sha or 'null'}}}",
        f"params:    {json.dumps(params, sort_keys=True)}",
    ]
    if artifacts.get("model.pkl"):
        lines.append(f"model:     {{sha256: {artifacts['model.pkl']}}}")
    lines.append(f"env_hash:  {ai_blob.get('env_hash', 'null')}")
    arg_pieces = [f"swcstudio auto-label"]
    for k, v in sorted(params.items()):
        arg_pieces.append(f"--{k.replace('_','-')} {v}")
    arg_pieces.append(source_path.name)
    lines.append(f"command:   {' '.join(arg_pieces)!r}")
    return "\n".join(lines) + "\n"
