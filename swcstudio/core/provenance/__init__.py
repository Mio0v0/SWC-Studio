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
from swcstudio.core.provenance.index import (
    INDEX_SCHEMA_VERSION,
    ensure_schema,
    insert_ai_run,
    insert_event,
    open_index,
    query_ai_runs,
    query_commits,
    query_node_changes,
    rebuild_index,
)
from swcstudio.core.provenance.events import (
    MAX_SUPPORTED_SCHEMA_VERSION,
    Event,
    append_event,
    canonical_json,
    compute_event_id,
    iter_events,
    load_events,
    new_session_id,
)
from swcstudio.core.provenance.lockfile import LockFile, LockHeldError
from swcstudio.core.provenance.objects import (
    BlobCorruptError,
    BlobNotFoundError,
    ObjectStore,
)
from swcstudio.core.provenance.refs import (
    DEFAULT_BRANCH,
    RefError,
    TagExistsError,
    create_tag,
    delete_branch,
    delete_tag,
    init_refs,
    list_branches,
    list_tags,
    read_branch,
    read_head,
    read_tag,
    valid_ref_name,
    write_branch,
    write_head,
)

__all__ = [
    "BlobCorruptError",
    "BlobNotFoundError",
    "DEFAULT_BRANCH",
    "Event",
    "INDEX_SCHEMA_VERSION",
    "LockFile",
    "LockHeldError",
    "MAX_SUPPORTED_SCHEMA_VERSION",
    "ObjectStore",
    "RefError",
    "TagExistsError",
    "append_event",
    "canonical_json",
    "canonical_swc",
    "compute_event_id",
    "create_tag",
    "delete_branch",
    "delete_tag",
    "ensure_schema",
    "init_refs",
    "insert_ai_run",
    "insert_event",
    "iter_events",
    "list_branches",
    "list_tags",
    "load_events",
    "new_session_id",
    "open_index",
    "query_ai_runs",
    "query_commits",
    "query_node_changes",
    "read_branch",
    "read_head",
    "read_tag",
    "rebuild_index",
    "root_sha",
    "sha256_hex",
    "valid_ref_name",
    "write_branch",
    "write_head",
]
