"""Crash-isolated process entry point for GUI single-file auto-labeling."""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path


def run_files(request_path: str, output_path: str) -> None:
    """Run one trusted local GUI auto-label request and pickle its result."""
    with Path(request_path).open("rb") as stream:
        request = pickle.load(stream)  # noqa: S301 - private 0600 temp file

    if request.get("kind") == "batch":
        from swcstudio.tools.batch_processing.features.auto_typing import (
            run_folder as run_auto_typing_folder,
        )

        progress_path = Path(request["progress_path"])

        def _write_progress(index: int, total: int, name: str) -> None:
            payload = {
                "index": int(index),
                "total": int(total),
                "name": str(name),
            }
            with progress_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
                stream.flush()

        result = run_auto_typing_folder(
            str(request["folder"]),
            options=request["options"],
            config_overrides=request.get("config_overrides"),
            progress_callback=_write_progress,
        )
    else:
        from swcstudio.tools.validation.features.auto_typing import (
            run_file as run_validation_auto_typing_file,
        )

        result = run_validation_auto_typing_file(
            str(request["file_path"]),
            options=request["options"],
            config_overrides=request.get("config_overrides"),
            write_output=False,
            write_log=False,
        )
    with Path(output_path).open("wb") as stream:
        pickle.dump(result, stream, protocol=pickle.HIGHEST_PROTOCOL)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(
            "usage: python -m swcstudio.gui.auto_label_process REQUEST OUTPUT",
            file=sys.stderr,
        )
        return 2
    run_files(args[0], args[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
