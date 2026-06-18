"""Installation diagnostics for fresh and upgraded SWC-Studio environments."""
from __future__ import annotations

import importlib
import importlib.metadata
import platform
import sys
from pathlib import Path
from typing import Any

from swcstudio import __version__
from swcstudio.core.model_paths import MODEL_FILES, resolve_model_path


SUPPORTED_PYTHON = ">=3.10,<3.13"

RUNTIME_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("morphio", "morphio"),
    ("neurom", "neurom"),
    ("scikit-learn", "sklearn"),
    ("joblib", "joblib"),
    ("xgboost", "xgboost"),
    ("torch", "torch"),
    ("torch-geometric", "torch_geometric"),
    ("PySide6", "PySide6"),
    ("pyqtgraph", "pyqtgraph"),
    ("vispy", "vispy"),
    ("zstandard", "zstandard"),
    ("pyzipper", "pyzipper"),
)

REQUIRED_CONFIGS: tuple[str, ...] = (
    "batch_processing/configs/auto_typing.json",
    "batch_processing/configs/batch_validation.json",
    "batch_processing/configs/radii_cleaning.json",
    "batch_processing/configs/split.json",
    "batch_processing/configs/swc_splitter.json",
    "morphology_editing/configs/dendrogram_editing.json",
    "morphology_editing/configs/simplification.json",
    "validation/configs/auto_fix.json",
    "validation/configs/default.json",
    "validation/configs/radii_cleaning.json",
    "validation/configs/run_checks.json",
    "visualization/configs/mesh_editing.json",
)


def _dependency_report(distribution: str, module: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "distribution": distribution,
        "module": module,
        "ok": False,
        "version": None,
        "error": None,
    }
    try:
        importlib.import_module(module)
        try:
            row["version"] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            imported = sys.modules.get(module)
            row["version"] = str(getattr(imported, "__version__", "unknown"))
        row["ok"] = True
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{exc.__class__.__name__}: {exc}"
    return row


def _load_model(short_name: str, path: Path) -> None:
    if short_name == "stage1":
        from swcstudio.core.auto_typing.cell_type_detector import CellTypeClassifier

        CellTypeClassifier.load(path)
        return
    if short_name == "stage2":
        from swcstudio.core.auto_typing.pipeline import _load_stage2_bundle

        _load_stage2_bundle(path)
        return
    if short_name == "gnn":
        import torch

        from swcstudio.core.auto_typing.gnn_inference import load_gnn

        load_gnn(path, device=torch.device("cpu"))
        return
    if short_name == "branch3":
        import torch

        from swcstudio.core.auto_typing.gnn_branch3_inference import load_branch3

        load_branch3(path, device=torch.device("cpu"))
        return
    if short_name == "qc_gate":
        from swcstudio.core.auto_typing.qc_input import QCGate

        QCGate.load(path)
        return

    import joblib

    joblib.load(path)


def check_installation(*, load_models: bool = True) -> dict[str, Any]:
    """Return a JSON-serializable runtime, data-file, and model report."""
    dependencies = [
        _dependency_report(distribution, module)
        for distribution, module in RUNTIME_DEPENDENCIES
    ]

    tools_dir = Path(__file__).resolve().parents[1] / "tools"
    configs = []
    for relative in REQUIRED_CONFIGS:
        path = tools_dir / relative
        configs.append(
            {
                "name": relative,
                "ok": path.is_file(),
                "path": str(path),
            }
        )

    models = []
    for short_name, filename in MODEL_FILES.items():
        path = resolve_model_path(short_name, auto_download=False)
        row: dict[str, Any] = {
            "name": short_name,
            "filename": filename,
            "ok": path is not None,
            "path": str(path) if path is not None else None,
            "loaded": None,
            "error": None,
        }
        if path is not None and load_models:
            try:
                _load_model(short_name, path)
                row["loaded"] = True
            except Exception as exc:  # noqa: BLE001
                row["ok"] = False
                row["loaded"] = False
                row["error"] = f"{exc.__class__.__name__}: {exc}"
        models.append(row)

    gui: dict[str, Any] = {"ok": False, "error": None}
    try:
        importlib.import_module("swcstudio.gui.main")
        gui["ok"] = True
    except Exception as exc:  # noqa: BLE001
        gui["error"] = f"{exc.__class__.__name__}: {exc}"

    python_ok = (3, 10) <= sys.version_info[:2] < (3, 13)
    ok = (
        python_ok
        and all(row["ok"] for row in dependencies)
        and all(row["ok"] for row in configs)
        and all(row["ok"] for row in models)
        and bool(gui["ok"])
    )
    return {
        "ok": ok,
        "swcstudio_version": __version__,
        "python": platform.python_version(),
        "supported_python": SUPPORTED_PYTHON,
        "python_ok": python_ok,
        "platform": platform.platform(),
        "executable": sys.executable,
        "dependencies": dependencies,
        "configs": configs,
        "models": models,
        "gui": gui,
        "model_loading_checked": load_models,
    }


def format_installation_report(report: dict[str, Any]) -> str:
    """Format :func:`check_installation` for terminal users."""
    marker = "PASS" if report["ok"] else "FAIL"
    lines = [
        f"SWC-Studio installation check: {marker}",
        f"  Version: {report['swcstudio_version']}",
        (
            f"  Python: {report['python']} "
            f"({report['supported_python']}) "
            f"[{'OK' if report['python_ok'] else 'UNSUPPORTED'}]"
        ),
        f"  Platform: {report['platform']}",
        f"  Executable: {report['executable']}",
        "",
        "Dependencies:",
    ]
    for row in report["dependencies"]:
        detail = row["version"] if row["ok"] else row["error"]
        lines.append(
            f"  [{'OK' if row['ok'] else 'MISSING'}] "
            f"{row['distribution']}: {detail}"
        )

    lines.extend(["", "Configuration files:"])
    for row in report["configs"]:
        lines.append(f"  [{'OK' if row['ok'] else 'MISSING'}] {row['name']}")

    lines.extend(["", "Production models:"])
    for row in report["models"]:
        state = "OK" if row["ok"] else "FAILED"
        detail = row["path"] or "not found"
        if row["error"]:
            detail = f"{detail} ({row['error']})"
        lines.append(f"  [{state}] {row['filename']}: {detail}")

    gui = report["gui"]
    lines.extend(
        [
            "",
            (
                f"GUI import: {'OK' if gui['ok'] else 'FAILED'}"
                + (f" ({gui['error']})" if gui["error"] else "")
            ),
        ]
    )
    if not report["ok"]:
        lines.extend(
            [
                "",
                "Repair this environment with:",
                (
                    f'  "{report["executable"]}" -m pip install '
                    "--upgrade --force-reinstall swcstudio"
                ),
            ]
        )
    return "\n".join(lines)


__all__ = [
    "REQUIRED_CONFIGS",
    "RUNTIME_DEPENDENCIES",
    "SUPPORTED_PYTHON",
    "check_installation",
    "format_installation_report",
]
