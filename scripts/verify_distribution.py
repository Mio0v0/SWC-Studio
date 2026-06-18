"""Verify that a wheel or sdist contains every runtime data file and dependency."""
from __future__ import annotations

import argparse
import email
import glob
import json
import re
import tarfile
import zipfile
from pathlib import Path


MODEL_FILES = (
    "branch_classifier.pkl",
    "cell_type_classifier.pkl",
    "flag_model_all.joblib",
    "flag_model_interneuron.joblib",
    "flag_model_pyramidal.joblib",
    "gnn_apical_basal.pt",
    "gnn_branch3_rescue.pt",
    "qc_gate.pkl",
)

CONFIG_FILES = (
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

RUNTIME_DISTRIBUTIONS = {
    "joblib",
    "morphio",
    "neurom",
    "numpy",
    "pandas",
    "pyqtgraph",
    "pyside6",
    "pyzipper",
    "scikit-learn",
    "scipy",
    "torch",
    "torch-geometric",
    "vispy",
    "xgboost",
    "zstandard",
}


def _normalise_distribution(raw: str) -> str:
    name = re.split(r"[\s(<=>;!\[]", raw, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


def _read_artifact(path: Path) -> tuple[set[str], bytes]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            members = set(archive.namelist())
            metadata_name = next(
                name for name in members if name.endswith(".dist-info/METADATA")
            )
            return members, archive.read(metadata_name)

    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = {member.name for member in archive.getmembers()}
            metadata_name = next(
                name for name in members if name.endswith("/PKG-INFO")
            )
            metadata_file = archive.extractfile(metadata_name)
            if metadata_file is None:
                raise RuntimeError(f"Could not read {metadata_name}")
            return members, metadata_file.read()

    raise ValueError(f"Unsupported artifact type: {path}")


def verify_distribution(path: Path) -> dict:
    members, metadata_bytes = _read_artifact(path)
    required_suffixes = {
        *(f"swcstudio/data/models/{name}" for name in MODEL_FILES),
        *(f"swcstudio/tools/{name}" for name in CONFIG_FILES),
    }
    missing_files = sorted(
        suffix
        for suffix in required_suffixes
        if not any(member.endswith(suffix) for member in members)
    )

    metadata = email.message_from_bytes(metadata_bytes)
    dependencies = {
        _normalise_distribution(value)
        for value in metadata.get_all("Requires-Dist", [])
    }
    missing_dependencies = sorted(RUNTIME_DISTRIBUTIONS - dependencies)
    result = {
        "artifact": str(path),
        "ok": not missing_files and not missing_dependencies,
        "model_count": sum(
            any(member.endswith(f"swcstudio/data/models/{name}") for member in members)
            for name in MODEL_FILES
        ),
        "config_count": sum(
            any(member.endswith(f"swcstudio/tools/{name}") for member in members)
            for name in CONFIG_FILES
        ),
        "missing_files": missing_files,
        "missing_dependencies": missing_dependencies,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()

    artifacts: list[Path] = []
    for raw_path in args.artifacts:
        raw = str(raw_path)
        if any(char in raw for char in "*?["):
            artifacts.extend(Path(match) for match in glob.glob(raw))
        else:
            artifacts.append(raw_path)
    if not artifacts:
        parser.error("no distribution artifacts matched")

    reports = [verify_distribution(path.resolve()) for path in artifacts]
    print(json.dumps(reports, indent=2, sort_keys=True))
    return 0 if all(report["ok"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
