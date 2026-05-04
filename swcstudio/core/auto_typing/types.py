"""Public dataclasses for the auto-typing engine.

These describe the user-facing options (which neurite types to assign,
whether to clean radii, whether to zip the batch output) and the
result shapes returned by :func:`run_file` / :func:`run_batch`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BatchOptions:
    soma: bool = True
    axon: bool = True
    apic: bool = False
    basal: bool = True
    rad: bool = False
    zip_output: bool = False


@dataclass
class BatchResult:
    folder: str
    out_dir: str
    zip_path: str | None
    files_total: int
    files_processed: int
    files_failed: int
    total_nodes: int
    total_type_changes: int
    total_radius_changes: int
    failures: list[str]
    per_file: list[str]
    log_path: str | None


@dataclass
class FileResult:
    input_file: str
    output_file: str | None
    nodes_total: int
    type_changes: int
    radius_changes: int
    out_type_counts: dict[int, int]
    failures: list[str]
    change_details: list[str]
    log_path: str | None
    headers: list[str]
    rows: list[dict[str, Any]]
    types: list[int]
    radii: list[float]


__all__ = ["BatchOptions", "BatchResult", "FileResult"]
