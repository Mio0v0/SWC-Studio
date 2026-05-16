# Converting existing handlers to `tracked_op` (slice 10 + 12 guide)

The provenance engine (slices 1–9) is in place. Every existing CLI
handler and GUI action that mutates an SWC still uses the old direct-
write + `format_*_report_text` pattern. This guide is the canonical
recipe for converting one handler at a time, in commits small enough
to review and revert.

Per spec §15 / M9: the `format_*_report_text` helpers in
`swcstudio.core.reporting` are scheduled for **deletion**, but only
after every call site has been converted. Until then, both code
paths can coexist — the new path writes to `.history/`, the old path
still writes its text report, and the text-report writing happens to
be redundant (because `swcstudio.core.provenance.render` produces
equivalent output on demand from the event log).

## The five-step recipe

For each handler that mutates an SWC file:

### 1. Identify the operation

Find the matching `OpKind` value. The closed v1 list is in
`swcstudio.core.provenance.ops.OpKind`. If your handler is one of
the standard ops, use the matching kind. If it's a plugin-specific
operation, use `OpKind.PLUGIN_OP` with a descriptive `params["plugin"]`.

Example mapping (handler → kind):

| Handler                                 | Kind                  |
|-----------------------------------------|-----------------------|
| `cli auto-fix`                          | `OpKind.AUTO_FIX`     |
| `cli auto-label`                        | `OpKind.AUTO_LABEL`   |
| `cli radii-clean`                       | `OpKind.RADII_CLEAN`  |
| `cli set-type`                          | `OpKind.SET_TYPE`     |
| `cli set-radius`                        | `OpKind.SET_RADIUS`   |
| `cli dendrogram-edit`                   | `OpKind.DENDROGRAM_EDIT` |
| `cli simplify`                          | `OpKind.SIMPLIFICATION` |
| `cli index-clean`                       | `OpKind.INDEX_CLEAN`  |
| `cli split`                             | `OpKind.SPLIT`        |
| `cli geometry move-node`/`delete`/...   | `OpKind.GEOMETRY_EDIT` |
| Plugin-defined op                       | `OpKind.PLUGIN_OP`    |

### 2. Wrap the mutation in `tracked_op`

The old handler typically:

1. Reads the SWC file from disk.
2. Calls a feature function that returns either new SWC bytes or
   a new path to a written file.
3. Calls `write_*_report_for_file()` to write a text report.
4. Returns / prints a summary.

The new shape:

```python
from swcstudio.core.provenance import tracked_op, OpKind

def cli_set_type(args):
    src = Path(args.file)
    with tracked_op(
        src,
        kind=OpKind.SET_TYPE,
        params={"node_id": args.node_id, "type": args.type},
        message=args.message or f"set-type node={args.node_id} type={args.type}",
    ) as op:
        # op.input_bytes is the latest committed state (or original on first op)
        new_bytes = set_node_type_in_bytes(op.input_bytes, args.node_id, args.type)
        op.set_output(new_bytes)
    print(f"committed {op.result.commit_sha[:19]} on {op.result.branch}")
    return 0
```

Three things changed:

* The mutation reads from `op.input_bytes` instead of re-reading the
  file. That's the latest committed state, which may differ from the
  original SWC if previous commits exist.
* The output is handed to `op.set_output(...)` instead of written
  directly to disk. The wrapper materializes `current.swc` with the
  refreshed `@PROV` header.
* The text report is NOT written separately. `swcstudio history
  show <sha> --format=text` reproduces it on demand from the event
  log; `swcstudio history log` is the per-file timeline.

### 3. AI handlers — set `is_ai=True` or use an AI kind

For `OpKind.AUTO_LABEL` and any future AI ops, the wrapper
automatically captures an environment fingerprint and writes an AI-
run blob. The caller can attach metrics via the result, though slice
7's API expects metrics to live in `op.set_output`-relative state:

```python
with tracked_op(
    src,
    kind=OpKind.AUTO_LABEL,
    params={"model_version": cfg.model_version, "rng_seed": cfg.rng_seed},
    message="auto-label apical/basal",
) as op:
    result = run_auto_label(op.input_bytes, **cfg.as_dict())
    op.set_output(result.swc_bytes)
```

The env capture happens on entry; the AI-run blob is finalized on
exit. The user can later run:

```
swcstudio history reproduce <sha> -o repro.yaml
```

to get a portable spec a colleague can use to recompute the same
result.

### 4. Plugin handlers — same recipe, `kind=OpKind.PLUGIN_OP`

Plugins follow the same pattern but use `PLUGIN_OP` and put their
identifying info in `params`:

```python
with tracked_op(
    src,
    kind=OpKind.PLUGIN_OP,
    params={"plugin": "brainglobe-coloring", "version": "1.2.0", **plugin_args},
    message=f"brainglobe-coloring on {src.name}",
) as op:
    op.set_output(mutate(op.input_bytes, **plugin_args))
```

### 5. Delete the old text-report write

After conversion, remove the call to the matching
`format_*_report_text` helper and its `write_*_report_for_file` /
`write_text_report` invocation. Do this only after the corresponding
handler is fully on the new path.

When every call site is converted, the helpers themselves can be
deleted from `swcstudio.core.reporting` as the final commit of slice
10 (per spec M9).

## GUI-side notes (slice 12)

GUI actions that mutate inside a single user click should each use
`tracked_op`. A whole interactive editing session (e.g. the user
opens an SWC, makes ten manual edits over five minutes, then closes)
should use `tracked_session`:

```python
from swcstudio.core.provenance import tracked_session

# Entered when a file is opened in the editor tab
session = tracked_session(swc_path, message="GUI editing session").__enter__()
try:
    while user_is_editing:
        action = wait_for_user_action()
        session.add_op(kind=action.kind, params=action.params)
        ...
    session.set_output(final_bytes)
finally:
    session.__exit__(None, None, None)
```

(In real GUI code this lives behind a context manager wired into the
tab's open/close lifecycle.)

GUI AI ops use `session.add_ai_op(...)` instead of `add_op(...)` so
the env fingerprint is captured at the time the AI ran, not at
session close.

## Migration of pre-existing output dirs

For files that already have a `<stem>_swc_studio_output/` directory
from before this work, the first `tracked_op` call on them will
*not* automatically import the legacy state — by design (M11,
clean-slate). Users (or a one-time GUI prompt) should explicitly
run:

```
swcstudio history init <file>
```

which:

* initializes `.history/`,
* creates one synthetic "import" commit anchored at the most-recent
  `_closed_<ts>.swc` (if any),
* leaves all legacy files in place.

The synthetic commit's message identifies it as a pre-history
import. From that point forward, every mutation goes through
`tracked_op`.

## Coexistence with old reports during transition

During the gradual conversion, both code paths can run side-by-side:

* New code path: writes to `.history/`, generates no text report.
* Old code path: writes the old text report next to the original
  SWC, unchanged.

A handler should not call both paths for the same op (that would
write the same content via two channels). Pick the path per
handler, and migrate at your own pace.

## When to delete `swcstudio.core.reporting`

Per spec §15, the entire module is removed once every call site is
converted. The deletion commit should:

1. Delete `swcstudio/core/reporting.py`.
2. Remove every `from swcstudio.core.reporting import ...` line.
3. Run the test suite; fix any remaining imports.

Until then, `swcstudio.core.reporting` and
`swcstudio.core.provenance.render` coexist. They produce equivalent
text for the same data; the new module just sources its data from
the event log rather than from inline arguments.
