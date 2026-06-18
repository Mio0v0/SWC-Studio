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
    # apic defaults to True because the engine auto-detects apical
    # subtrees (only assigning the apical label when a subtree passes
    # a learned score + minimum-radius threshold). Setting apic=False
    # tells the runner to REJECT apical predictions even when the
    # engine produces them, which causes nodes to fall back to the
    # original SWC type — and if that type was 0 (undefined), the
    # whole subtree shows as undefined in the GUI. Default True is
    # the right semantic: trust the engine. Pass False explicitly
    # only when forcing 3-class soma/axon/basal output.
    apic: bool = True
    basal: bool = True
    rad: bool = False
    zip_output: bool = False
    cell_type: str | None = None
    flag_enabled: bool = True
    flag_strictness: float = 0.5
    flag_feature_mode: str = "compact"


@dataclass
class BatchResult:
    folder: str
    out_dir: str | None
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
    files_flagged: int = 0
    files_qc_failed: int = 0
    commits: list[dict[str, Any]] | None = None


@dataclass
class FileResult:
    input_file: str
    output_file: str | None
    nodes_total: int
    type_changes: int
    radius_changes: int
    out_type_counts: dict[int, int]
    cell_type: str | None
    cell_type_source: str
    stage1_confidence: float | None
    qc_result: dict[str, Any] | None
    flag_result: dict[str, Any] | None
    failures: list[str]
    change_details: list[str]
    log_path: str | None
    headers: list[str]
    rows: list[dict[str, Any]]
    types: list[int]
    radii: list[float]


__all__ = ["BatchOptions", "BatchResult", "FileResult"]
