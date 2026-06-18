#!/usr/bin/env python3
"""Stage replaceable SWC-Studio code and model layers beside a runtime."""

from __future__ import annotations

import argparse
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _ignore_source(_directory: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", "models"}
    ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
    return ignored


def stage_payload(source_root: Path, runtime_root: Path, app_version: str) -> None:
    source_package = source_root / "swcstudio"
    source_models = source_package / "data" / "models"
    if not (source_package / "__init__.py").is_file():
        raise FileNotFoundError(f"SWC-Studio package not found: {source_package}")
    if not source_models.is_dir():
        raise FileNotFoundError(f"Bundled models not found: {source_models}")
    if not runtime_root.is_dir():
        raise FileNotFoundError(f"Runtime root not found: {runtime_root}")

    app_root = runtime_root / "app"
    code_target = app_root / "swcstudio"
    models_target = runtime_root / "models"

    for target in (code_target, models_target):
        if target.exists():
            shutil.rmtree(target)
    app_root.mkdir(parents=True, exist_ok=True)

    shutil.copytree(source_package, code_target, ignore=_ignore_source)
    shutil.copytree(
        source_models,
        models_target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    (app_root / "VERSION").write_text(app_version + "\n", encoding="utf-8")
    (models_target / "VERSION").write_text(app_version + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--version")
    args = parser.parse_args()

    if args.version:
        app_version = args.version
    else:
        try:
            app_version = version("swcstudio")
        except PackageNotFoundError:
            app_version = "0.0.0"

    stage_payload(
        args.source_root.resolve(),
        args.runtime_root.resolve(),
        app_version,
    )
    print(f"Staged modular code:   {args.runtime_root / 'app' / 'swcstudio'}")
    print(f"Staged modular models: {args.runtime_root / 'models'}")
    print(f"Version: {app_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
