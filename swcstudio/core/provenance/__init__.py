"""SWC-Studio provenance, versioning, and reproducibility layer.

See ``docs/PROVENANCE_SPEC.md`` for the full design contract.

Slice-1 status: ``canonical`` (this file) is the foundation. Other
modules — ``objects``, ``events``, ``lockfile``, ``refs``, ``index``,
``tracked_op``, ``render`` — are added incrementally, each on top of
the previous one.
"""

from __future__ import annotations

from swcstudio.core.provenance.canonical import (
    canonical_swc,
    root_sha,
    sha256_hex,
)
from swcstudio.core.provenance.lockfile import LockFile, LockHeldError
from swcstudio.core.provenance.objects import (
    BlobCorruptError,
    BlobNotFoundError,
    ObjectStore,
)

__all__ = [
    "BlobCorruptError",
    "BlobNotFoundError",
    "LockFile",
    "LockHeldError",
    "ObjectStore",
    "canonical_swc",
    "root_sha",
    "sha256_hex",
]
