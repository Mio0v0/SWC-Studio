"""SWC-Studio provenance, versioning, and reproducibility layer.

See ``docs/PROVENANCE_SPEC.md`` for the full design contract.

Slice-1 status: ``canonical`` (this file) is the foundation. Other
modules — ``objects``, ``events``, ``lockfile``, ``refs``, ``index``,
``tracked_op``, ``render`` — are added incrementally, each on top of
the previous one.
"""

from __future__ import annotations

from swcstudio.core.provenance.crate import export_crate
from swcstudio.core.provenance.batch import config_params, run_tracked_batch
from swcstudio.core.provenance.derived import (
    derived_from_for_swc_path,
    derived_from_payload,
    find_descendants,
)
from swcstudio.core.provenance.migration import (
    MigrationOutcome,
    migrate_legacy_output_dir,
    needs_migration,
)
from swcstudio.core.provenance.render import (
    render_ai_run_text,
    render_commit_text,
    render_diff_text,
    render_history_log_text,
)
from swcstudio.core.provenance.archive import (
    ARCHIVE_FORMAT_VERSION,
    ARCHIVE_SUFFIX,
    LEGACY_ARCHIVE_SUFFIX,
    MANIFEST_NAME,
    PASSWORD_ENV,
    archive_history_dir,
    archive_name_for,
    archive_path_for,
    ensure_history_manifest,
    ensure_history_materialized,
    history_archive_exists,
    history_repo_info,
    open_history_for_read,
)
from swcstudio.core.provenance.tracked_op import (
    FORMAT_VERSION,
    OpResult,
    current_swc_path_for,
    history_dir_for,
    init_history,
    tracked_op,
    tracked_session,
)
from swcstudio.core.provenance.ai_run import (
    AIRUN_SCHEMA_VERSION,
    AIRun,
    AIRunStatus,
    ai_run_to_blob_bytes,
    build_ai_run,
)
from swcstudio.core.provenance.env import (
    ENV_SCHEMA_VERSION,
    capture_env,
    env_hash,
)
from swcstudio.core.provenance.diff import (
    DiffPayload,
    compute_swc_diff,
    summarize_diff,
)
from swcstudio.core.provenance.header import (
    PROV_PREFIX,
    ProvHeader,
    format_root_line,
    format_tip_line,
    parse_prov_header,
    strip_prov_lines,
    write_prov_header,
)
from swcstudio.core.provenance.ops import (
    OpKind,
    is_ai_op,
    operation_display_name,
    operation_display_parameters,
    validate_op_record,
)
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
    "AIRUN_SCHEMA_VERSION",
    "ARCHIVE_FORMAT_VERSION",
    "ARCHIVE_SUFFIX",
    "LEGACY_ARCHIVE_SUFFIX",
    "AIRun",
    "AIRunStatus",
    "BlobCorruptError",
    "BlobNotFoundError",
    "DEFAULT_BRANCH",
    "DiffPayload",
    "ENV_SCHEMA_VERSION",
    "FORMAT_VERSION",
    "MigrationOutcome",
    "MANIFEST_NAME",
    "OpResult",
    "PASSWORD_ENV",
    "derived_from_for_swc_path",
    "derived_from_payload",
    "export_crate",
    "find_descendants",
    "migrate_legacy_output_dir",
    "needs_migration",
    "render_ai_run_text",
    "render_commit_text",
    "render_diff_text",
    "render_history_log_text",
    "ai_run_to_blob_bytes",
    "build_ai_run",
    "capture_env",
    "config_params",
    "current_swc_path_for",
    "env_hash",
    "history_dir_for",
    "init_history",
    "tracked_op",
    "tracked_session",
    "Event",
    "INDEX_SCHEMA_VERSION",
    "LockFile",
    "LockHeldError",
    "MAX_SUPPORTED_SCHEMA_VERSION",
    "ObjectStore",
    "OpKind",
    "operation_display_name",
    "operation_display_parameters",
    "PROV_PREFIX",
    "ProvHeader",
    "RefError",
    "TagExistsError",
    "append_event",
    "archive_history_dir",
    "archive_name_for",
    "archive_path_for",
    "canonical_json",
    "canonical_swc",
    "compute_event_id",
    "compute_swc_diff",
    "create_tag",
    "delete_branch",
    "delete_tag",
    "ensure_schema",
    "ensure_history_manifest",
    "ensure_history_materialized",
    "format_root_line",
    "format_tip_line",
    "init_refs",
    "insert_ai_run",
    "insert_event",
    "is_ai_op",
    "iter_events",
    "history_archive_exists",
    "history_repo_info",
    "list_branches",
    "list_tags",
    "load_events",
    "new_session_id",
    "open_index",
    "open_history_for_read",
    "parse_prov_header",
    "query_ai_runs",
    "query_commits",
    "query_node_changes",
    "read_branch",
    "read_head",
    "read_tag",
    "rebuild_index",
    "root_sha",
    "run_tracked_batch",
    "sha256_hex",
    "strip_prov_lines",
    "summarize_diff",
    "valid_ref_name",
    "validate_op_record",
    "write_branch",
    "write_head",
    "write_prov_header",
]
