"""Compatibility aliases for research-repo-trained pickle artifacts."""
from __future__ import annotations

import sys
import types


def install_hybrid_pickle_aliases() -> None:
    """Expose local deployment modules under the old ``hybrid.*`` names.

    The accepted v12 pickles were trained in the research pipeline where
    helper classes lived under ``hybrid``. SWC-Studio vendors the same
    inference helpers under ``swcstudio.core.auto_typing``; these aliases
    let pickle resolve the original module names without depending on the
    research repo being importable.
    """
    root = sys.modules.get("hybrid")
    if root is None:
        root = types.ModuleType("hybrid")
        root.__path__ = []  # mark as package-like for submodule imports
        sys.modules["hybrid"] = root

    from . import _xgb_classifiers  # noqa: PLC0415

    sys.modules.setdefault("hybrid._xgb_classifiers", _xgb_classifiers)
    setattr(root, "_xgb_classifiers", _xgb_classifiers)
