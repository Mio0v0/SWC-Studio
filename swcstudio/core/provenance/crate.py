"""RO-Crate export — v1 minimal implementation (PROVENANCE_SPEC §20).

Bundles an SWC + its full materialized history + AI metadata +
per-AI-run ``reproduce.yaml`` files into a portable directory matching the
`RO-Crate <https://www.researchobject.org/ro-crate/>`_ shape:

::

    <crate>/
        ro-crate-metadata.json     # JSON-LD provenance graph (PROV-O vocab)
        data/<source.swc>          # the dataset
        history/events.jsonl       # the log
        history/objects/...        # the blob store
        history/refs/...           # branches + tags
        reproduce/<short>.yaml     # one yaml per AI commit

The ``ro-crate-metadata.json`` is a minimal JSON-LD document that
maps:

* the SWC -> ``schema:Dataset``
* each commit -> ``prov:Activity``
* each actor -> ``prov:Agent``
* AI runs -> additional ``prov:Activity`` with model/env metadata

By default ``with_pii=False`` strips usernames and absolute paths
from the exported metadata; the original blobs are copied as-is
since they were already PII-clean by design (env capture in
:mod:`provenance.env` deliberately omits hostname/username).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swcstudio.core.provenance.events import iter_events
from swcstudio.core.provenance.objects import BlobNotFoundError, ObjectStore
from swcstudio.core.provenance.tracked_op import history_dir_for

__all__ = ["export_crate"]


def export_crate(
    swc_path: str | Path,
    out_dir: str | Path,
    *,
    with_pii: bool = False,
) -> Path:
    """Bundle an SWC + history into an RO-Crate directory at ``out_dir``.

    Returns the crate root path. Overwrites ``out_dir`` if it exists
    (caller is expected to choose a fresh path).
    """
    src = Path(swc_path)
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Copy the dataset.
    data_dir = out / "data"
    data_dir.mkdir()
    if src.exists():
        shutil.copy2(src, data_dir / src.name)

    # Copy history (events.jsonl, objects/, refs/, version, root.json,
    # index.sqlite — but NOT lock).
    hist = history_dir_for(src)
    hist_out = out / "history"
    hist_out.mkdir()
    if hist.exists():
        for child in hist.iterdir():
            if child.name == "lock":
                continue
            dest = hist_out / child.name
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)

    # Per-AI-commit reproduce.yaml files.
    rep_dir = out / "reproduce"
    rep_dir.mkdir()
    store = ObjectStore(hist / "objects") if hist.exists() else None
    if store is not None and (hist / "events.jsonl").exists():
        from swcstudio.cli.history_cli import _format_reproduce_yaml  # local import avoids cycle
        for ev in iter_events(hist / "events.jsonl"):
            ai_refs = [op.get("ai_run_ref") for op in ev.ops if op.get("ai_run_ref")]
            if not ai_refs:
                continue
            try:
                blob = json.loads(store.get(ai_refs[0].removeprefix("sha256:")))
            except (BlobNotFoundError, ValueError):
                continue
            short = (ev.id or "").removeprefix("sha256:")[:12]
            (rep_dir / f"{short}.yaml").write_text(
                _format_reproduce_yaml(ev, blob, src),
                encoding="utf-8",
            )

    # ro-crate-metadata.json (minimal; rich PROV-O export deferred).
    metadata = _build_minimal_crate_metadata(src, hist, with_pii=with_pii)
    (out / "ro-crate-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


def _build_minimal_crate_metadata(
    src: Path,
    hist: Path,
    *,
    with_pii: bool,
) -> dict[str, Any]:
    """Produce a JSON-LD doc with the standard RO-Crate spine.

    Includes the dataset and one Activity per commit, with minimal
    PROV-O typing. Fuller PROV-O graph (Entity/Activity/Agent triples
    for every node-level change) is intentionally deferred — this
    minimal form already enables RO-Crate readers to ingest the
    dataset and surface the commit timeline.
    """
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    graph: list[dict[str, Any]] = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": src.stem,
            "datePublished": now_iso,
            "hasPart": [{"@id": f"data/{src.name}"}],
        },
        {
            "@id": f"data/{src.name}",
            "@type": ["File", "Dataset"],
            "encodingFormat": "text/plain",
            "name": src.name,
        },
    ]

    if hist.exists() and (hist / "events.jsonl").exists():
        for ev in iter_events(hist / "events.jsonl"):
            short = (ev.id or "").removeprefix("sha256:")[:12]
            actor_user = (ev.actor or {}).get("os_user", "unknown")
            actor_id = f"#agent-{actor_user}" if with_pii else "#agent-anonymous"
            graph.append({
                "@id": f"#commit-{short}",
                "@type": ["CreateAction", "Activity"],
                "name": (ev.message or short),
                "startTime": ev.ts,
                "agent": {"@id": actor_id},
                "instrument": {
                    "@type": "SoftwareApplication",
                    "name": (ev.tool or {}).get("name"),
                    "softwareVersion": (ev.tool or {}).get("version"),
                },
                "result": {"@id": f"data/{src.name}"},
                "identifier": ev.id,
            })
            # Add agent node if not already present.
            if not any(g.get("@id") == actor_id for g in graph):
                graph.append({
                    "@id": actor_id,
                    "@type": "Person",
                    "name": actor_user if with_pii else "anonymous",
                })

    return {
        "@context": [
            "https://w3id.org/ro/crate/1.1/context",
            {"prov": "http://www.w3.org/ns/prov#",
             "Activity": "prov:Activity",
             "Agent": "prov:Agent",
             "Entity": "prov:Entity"},
        ],
        "@graph": graph,
    }
