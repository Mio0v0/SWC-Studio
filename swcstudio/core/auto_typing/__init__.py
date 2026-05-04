"""Auto-typing engine for swcstudio (v9 ML pipeline).

This package is the single auto-labeling backend used everywhere in
swcstudio. It runs a four-stage pipeline that classifies every node in
an SWC into soma / axon / basal dendrite / apical dendrite:

* Stage 1: cell-type detector (sklearn ensemble, 49 whole-cell
  features) decides pyramidal vs interneuron.
* Stage 2: per-subtree axon/basal/apical classifier (sklearn
  ensemble), propagated to all branches in the same primary subtree.
* Stage 2b: GraphSAGE GNN over the branch graph re-decides
  apical-vs-basal for pyramidal dendrite branches. Skipped
  automatically if torch / torch_geometric / the GNN checkpoint are
  unavailable.
* Stage 3: topology refinement.

End users typically reach this code through the CLI (``swcstudio
validation auto-label``, ``swcstudio batch auto-typing``) or through
the GUI's Validation / Batch panels. They rarely import these modules
directly.

The model files are resolved via :mod:`swcstudio.core.model_paths` —
override location with ``--model-dir``, ``SWCSTUDIO_MODEL_DIR``, or the
GUI selector.
"""
from __future__ import annotations

from .config import DEFAULT_CONFIG, get_config, save_config
from .runner import (
    backend_status,
    is_available,
    run_batch,
    run_file,
)
from .types import BatchOptions, BatchResult, FileResult

# Pipeline-level entry points (used by callers that have already parsed
# SWC into the internal SWCNode representation, e.g. research code).
from .features import SWCNode, parse_swc  # noqa: F401
from .pipeline import (  # noqa: F401
    PipelineResult,
    run_pipeline,
    run_pipeline_on_nodes,
)


def run_folder(folder: str, opts: BatchOptions | None = None) -> BatchResult:
    """Convenience: run the engine on a folder with default options."""
    return run_batch(folder, opts if opts is not None else BatchOptions())


__all__ = [
    "BatchOptions",
    "BatchResult",
    "FileResult",
    "DEFAULT_CONFIG",
    "get_config",
    "save_config",
    "is_available",
    "backend_status",
    "run_file",
    "run_batch",
    "run_folder",
    "SWCNode",
    "parse_swc",
    "PipelineResult",
    "run_pipeline",
    "run_pipeline_on_nodes",
]
