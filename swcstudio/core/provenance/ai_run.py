"""AI-run record (MLflow-shaped).

Implements PROVENANCE_SPEC §4 ("AI-run blob"). Every AI op (currently
just ``auto_label``) writes one of these alongside its diff blob, plus
a reference to a deduplicated env blob.

Schema names match MLflow's ``Run`` shape so a future MLflow
adapter is a thin field-mapping rather than a translation layer.
Spec §15 is explicit: we do **not** depend on MLflow at runtime; we
just borrow the field names.

What this module owns:

* The :class:`AIRun` dataclass (in-memory shape).
* :func:`build_ai_run`: a small builder that fills in immutable
  fields the caller usually doesn't want to write by hand
  (run_id, schema_version).
* :func:`ai_run_to_blob_bytes`: deterministic JSON encoding suitable
  for ``ObjectStore.put``.

What lives elsewhere:

* The actual env capture — :mod:`swcstudio.core.provenance.env`.
* The decision to call this module — :mod:`tracked_op` (slice 7),
  triggered by :func:`ops.is_ai_op`.
* SQLite ``ai_runs`` row insertion — :mod:`index.insert_ai_run`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from swcstudio.core.provenance.events import canonical_json, new_session_id

__all__ = [
    "AIRUN_SCHEMA_VERSION",
    "AIRun",
    "AIRunStatus",
    "build_ai_run",
    "ai_run_to_blob_bytes",
]


AIRUN_SCHEMA_VERSION = 1


class AIRunStatus(str):
    """String constants for AI run status. Plain strings for JSON friendliness."""

    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


@dataclass
class AIRun:
    """Per-AI-execution record.

    Stored as a blob (one per AI op). Referenced from the event line
    via ``op["ai_run_ref"]`` and indexed in SQLite ``ai_runs`` for
    queries like "every auto_label using model v8".

    Fields mirror MLflow's ``Run``:

    * ``run_id`` — unique per execution.
    * ``status`` — RUNNING / FINISHED / FAILED.
    * ``started_at`` / ``finished_at`` — ISO-8601 UTC strings.
    * ``params`` — the input parameters the AI was called with
      (model_version, rng_seed, etc.).
    * ``metrics`` — the output measurements (nodes_labeled,
      low_conf_count, …).
    * ``artifacts`` — list of ``{"name", "sha256"}`` references to
      ``objects/`` blobs that participated (the model file, input
      and output SWCs).
    * ``source_version`` — tool name+version+git_sha that ran it.
    * ``env_hash`` — bare hex sha of the env blob (deduplicated).
    """

    schema_version: int = AIRUN_SCHEMA_VERSION
    run_id: str = ""
    status: str = AIRunStatus.RUNNING
    started_at: str = ""
    finished_at: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, str]] = field(default_factory=list)
    source_version: dict[str, Any] = field(default_factory=dict)
    env_hash: str = ""

    def to_json_obj(self) -> dict[str, Any]:
        d = asdict(self)
        # Drop None values for fields we declare as Optional, so the
        # blob is canonical for FINISHED runs (no stray ``"finished_at": null``
        # for the common case).
        return {k: v for k, v in d.items() if v is not None}


def build_ai_run(
    *,
    started_at: str,
    params: dict[str, Any] | None = None,
    source_version: dict[str, Any] | None = None,
    env_hash: str = "",
    run_id: str | None = None,
) -> AIRun:
    """Construct an :class:`AIRun` with sensible defaults.

    The caller (typically tracked_op) updates ``status``,
    ``finished_at``, ``metrics``, and ``artifacts`` after the AI
    body returns.
    """
    return AIRun(
        run_id=run_id or new_session_id(),
        status=AIRunStatus.RUNNING,
        started_at=started_at,
        finished_at=None,
        params=dict(params or {}),
        metrics={},
        artifacts=[],
        source_version=dict(source_version or {}),
        env_hash=env_hash,
    )


def ai_run_to_blob_bytes(run: AIRun) -> bytes:
    """Serialize an :class:`AIRun` to canonical JSON bytes for ObjectStore.put.

    Matches the encoding used elsewhere in the provenance layer
    (sorted keys, compact separators) so two byte-identical AI runs
    produce the same blob hash.
    """
    return canonical_json(run.to_json_obj())
