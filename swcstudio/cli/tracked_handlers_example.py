"""Reference example: ``set-type`` handler converted to ``tracked_op``.

This file demonstrates the conversion recipe from
``docs/PROVENANCE_CONVERSION_GUIDE.md`` end-to-end on the simplest
CLI handler. It is **not wired into the CLI** — the existing
``swcstudio morphology set-type`` handler in :mod:`cli` is untouched.

Use this as a template when you migrate the real handlers, one at a
time, in their own commits.

Old handler shape (see swcstudio/cli/cli.py, ``morphology set-type``)::

    old_df = parse_swc_text_preserve_tokens(file.read_text())
    out = set_node_type_file(file, node_id=..., new_type=..., write_output=True)
    out["operation_log_path"] = _write_cli_operation_report(...)
    _print_json(out_without_bytes)

Three things that handler did that the new path replaces:

1. ``set_node_type_file(..., write_output=True)`` writes a new
   ``<stem>_morphology_set_type_<ts>.swc`` file next to the source
   and also returns the new bytes. Under the new path, we let
   ``tracked_op`` materialize ``<stem>_current.swc`` and store the
   structured diff in ``.history/``; we don't keep the timestamped
   per-op file.
2. ``_write_cli_operation_report`` writes a text report. Under the
   new path, ``swcstudio history show <sha> --format=text``
   renders an equivalent report on demand.
3. The JSON summary printed to stdout is what the human/CI sees.
   Preserve that exactly so scripts continue to parse it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from swcstudio.core.provenance import OpKind, tracked_op
from swcstudio.core.swc_io import (
    parse_swc_text_preserve_tokens,
    write_swc_to_bytes_preserve_tokens,
)

__all__ = ["tracked_set_type_handler"]


def tracked_set_type_handler(
    *,
    file: str | Path,
    node_id: int,
    new_type: int,
    message: str | None = None,
) -> int:
    """Convert ``morphology set-type`` to use the provenance layer.

    Behaviorally equivalent to::

        swcstudio morphology set-type <file> --node-id N --new-type T

    on the result; differences are: outputs land in
    ``<stem>_swc_studio_output/<stem>_current.swc`` with the bounded
    ``@PROV`` header, the operation is recorded as one commit in
    ``.history/events.jsonl``, and the matching text report is
    available on demand via ``swcstudio history show``.

    Returns process exit code (0 on success).
    """
    src = Path(file)
    if not src.exists():
        print(f"error: {src} does not exist")
        return 1

    with tracked_op(
        src,
        kind=OpKind.SET_TYPE,
        params={"node_id": int(node_id), "new_type": int(new_type)},
        message=message or f"set-type node={node_id} type={new_type}",
    ) as op:
        # Read input bytes through the tracked context (this is the
        # latest committed state, not necessarily the original).
        input_bytes = op.input_bytes
        if input_bytes is None:
            # First commit on a fresh dataset; fall back to the source
            # SWC on disk.
            input_bytes = src.read_bytes()

        # Apply the edit. We use the existing parser/writer so float
        # formats and comments round-trip exactly.
        df = parse_swc_text_preserve_tokens(input_bytes.decode("utf-8", errors="ignore"))
        mask = df["id"] == int(node_id)
        if not mask.any():
            print(f"error: node id {node_id} not found")
            return 1
        df.loc[mask, "type"] = int(new_type)
        new_bytes = write_swc_to_bytes_preserve_tokens(df)

        op.set_output(new_bytes)

    # JSON summary for scripts — mirrors the existing handler's contract.
    result: dict[str, Any] = {
        "ok": True,
        "node_id": int(node_id),
        "new_type": int(new_type),
        "commit_sha": op.result.commit_sha,
        "branch": op.result.branch,
        "input_sha": op.result.input_sha,
        "output_sha": op.result.output_sha,
        "diff_ref": op.result.diff_ref,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


# Optional small CLI shim so this can be exercised directly:
#   python -m swcstudio.cli.tracked_handlers_example --file F --node-id N --new-type T
def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--node-id", type=int, required=True)
    ap.add_argument("--new-type", type=int, required=True)
    ap.add_argument("--message")
    args = ap.parse_args()
    return tracked_set_type_handler(
        file=args.file,
        node_id=args.node_id,
        new_type=args.new_type,
        message=args.message,
    )


if __name__ == "__main__":
    raise SystemExit(_main())
