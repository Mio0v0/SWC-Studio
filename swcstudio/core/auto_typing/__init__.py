"""Auto-typing engine for swcstudio (v9 ML pipeline).

This package is the single auto-labeling backend used everywhere in
swcstudio. It runs a four-stage pipeline that classifies every node in
an SWC into soma / axon / basal dendrite / apical dendrite:

* Stage 1: cell-type detector (sklearn ensemble, 49 whole-cell
  features) decides pyramidal vs interneuron.
* Stage 2: per-subtree axon/basal/apical classifier (sklearn
  ensemble), propagated to all branches in the same primary subtree.
* Stage 2b: GraphSAGE GNN over the branch graph re-decides
  apical-vs-basal for pyramidal dendrite branches.
* Stage 3: topology refinement.

All four stages are required. The package's required dependencies
include sklearn, torch, and torch_geometric, and ``pip install -e .``
ships the trained model files for every stage.

End users typically reach this code through the CLI (``swcstudio
validation auto-label``, ``swcstudio batch auto-typing``) or through
the GUI's Validation / Batch panels. They rarely import these modules
directly.

The model files are resolved via :mod:`swcstudio.core.model_paths` —
override location with ``--model-dir``, ``SWCSTUDIO_MODEL_DIR``, or the
GUI selector.
"""
from __future__ import annotations

import warnings as _warnings

# Silence sklearn's InconsistentVersionWarning for the bundled pickles.
# The package pins ``scikit-learn>=1.5,<1.6``, so any mismatch with the
# trained-on version is patch-level only (e.g. 1.5.1 trained vs 1.5.2
# installed), which sklearn keeps wire-compatible. The warning is
# noisy — sklearn fires it once per estimator inside a pickled bundle,
# so users would see ~10 identical messages on the first auto-label
# run — and is not actionable at the patch level. A real cross-minor
# mismatch would already raise an ``ImportError`` from a missing C
# symbol, not this warning, so suppressing it doesn't hide real bugs.
try:
    from sklearn.exceptions import InconsistentVersionWarning as _InconsistentVersionWarning  # noqa: PLC0415
    _warnings.filterwarnings("ignore", category=_InconsistentVersionWarning)
except ImportError:  # pragma: no cover - sklearn is a required dep
    pass

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
