"""Unified issue model used by the issue-driven repair workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from swctools.core.radii_cleaning import clean_radii_dataframe
from swctools.core.validation_catalog import CHECK_CATEGORY, CHECK_LABEL, CHECK_ORDER


_SEVERITY_RANK = {
    "critical": 0,
    "warning": 1,
    "info": 2,
}

_STATUS_RANK = {
    "open": 0,
    "fixing": 1,
    "skipped": 2,
    "fixed": 3,
}


@dataclass
class Issue:
    issue_id: str
    severity: str
    certainty: str
    domain: str
    title: str
    description: str
    node_ids: list[int] = field(default_factory=list)
    section_ids: list[int] = field(default_factory=list)
    tool_target: str = "validation"
    suggested_fix: str = ""
    confidence: float | None = None
    status: str = "open"
    source_key: str = ""
    source_label: str = ""
    source_category: str = ""
    source_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _severity_from_validation_row(row: dict[str, Any]) -> str:
    status = str(row.get("status", "")).strip().lower()
    if status == "fail":
        return "critical"
    if status == "warning":
        return "warning"
    return "info"


def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _blocked_reason_from_validation_row(row: dict[str, Any]) -> dict[str, str] | None:
    message = str(row.get("message", "")).strip()
    if "Validation error:" not in message:
        return None

    lines = _nonempty_lines(message)
    if not lines:
        return None

    last_line = lines[-1]
    if last_line.lower().startswith("unsupported section type:"):
        section_type = last_line.split(":", 1)[-1].strip() or "unknown"
        return {
            "code": f"unsupported_section_type_{section_type}",
            "title": "Checks blocked by unsupported node labels",
            "reason": last_line,
            "domain": "label",
            "tool_target": "label_editing",
            "suggested_fix": (
                "Soma may already be present, but some neurite nodes still use unsupported type "
                f"{section_type}. Relabel those nodes to valid SWC neurite types in Morphology Editing. "
                "Dependent checks will run automatically after relabeling."
            ),
        }

    return {
        "code": "validation_dependency_error",
        "title": "Checks blocked by incompatible morphology",
        "reason": last_line,
        "domain": "structure",
        "tool_target": "validation",
        "suggested_fix": "Resolve the prerequisite morphology problem first, then dependent checks will run automatically.",
    }


def validation_prerequisite_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    summary = {
        "missing_soma": False,
        "unsupported_section_types": set(),
        "blocked_reasons": [],
        "soma_gate_failed": False,
        "multiple_somas_failed": False,
    }
    if not isinstance(report, dict):
        return summary

    blocked_reason_map: dict[str, str] = {}
    for row in report.get("results", []):
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "")).strip().lower() == "pass":
            continue
        if str(row.get("key", "")).strip() == "has_soma":
            summary["missing_soma"] = True
        if str(row.get("key", "")).strip() == "valid_soma_format":
            summary["soma_gate_failed"] = True
        if str(row.get("key", "")).strip() == "multiple_somas":
            summary["multiple_somas_failed"] = True
        blocked = _blocked_reason_from_validation_row(row)
        if not blocked:
            continue
        code = str(blocked.get("code", "")).strip()
        reason = str(blocked.get("reason", "")).strip()
        if code:
            blocked_reason_map[code] = reason
        if code.startswith("unsupported_section_type_"):
            summary["unsupported_section_types"].add(code.rsplit("_", 1)[-1])

    summary["unsupported_section_types"] = sorted(summary["unsupported_section_types"])
    summary["blocked_reasons"] = [
        {"code": code, "reason": reason}
        for code, reason in sorted(blocked_reason_map.items())
    ]
    return summary


def _tool_target_for_key(key: str) -> tuple[str, str, str]:
    radii_keys = {
        "all_neurite_radii_nonzero",
        "soma_radius_nonzero",
        "no_ultranarrow_sections",
        "no_ultranarrow_starts",
        "no_fat_terminal_ends",
    }
    label_keys = {
        "has_axon",
        "has_basal_dendrite",
        "has_apical_dendrite",
    }
    simplification_keys = {
        "all_section_lengths_nonzero",
        "all_segment_lengths_nonzero",
        "no_duplicate_3d_points",
        "no_single_child_chains",
    }
    manual_edit_keys = {
        "no_back_tracking",
        "no_flat_neurites",
        "no_dangling_branches",
        "no_self_loop",
        "has_unifurcation",
        "has_multifurcation",
        "no_section_index_jumps",
        "no_root_index_jumps",
        "parent_id_less_than_child_id",
        "no_extreme_spatial_jump",
    }

    if key in radii_keys:
        return ("radii", "manual_radii", "Use Manual Radii Editing to inspect and set individual node radii, or Auto Radii Editing for broader cleanup.")
    if key in label_keys:
        return ("label", "auto_label", "Use the Auto Label panel to assign missing neurite types, then rerun dependent checks automatically.")
    if key in simplification_keys:
        return (
            "geometry",
            "simplification",
            "Open Simplification to collapse redundant points or inspect short/duplicate geometry.",
        )
    if key in manual_edit_keys:
        return (
            "structure",
            "label_editing",
            "Open Morphology Editing to inspect the highlighted branch and repair topology manually.",
        )
    if key == "valid_soma_format":
        return (
            "structure",
            "",
            "Complex soma format must be resolved before the rest of the validation pipeline can continue.",
        )
    if key == "multiple_somas":
        return (
            "structure",
            "",
            "Multiple disconnected soma groups remain. The only supported next step is to split each tree into its own SWC file.",
        )
    if key == "has_soma":
        return ("structure", "auto_label", "Use the Auto Label panel to assign a soma label so dependent checks can run.")
    if key == "no_invalid_negative_types":
        return ("label", "label_editing", "Relabel nodes with invalid negative type values to supported SWC types.")
    if key == "custom_types_defined":
        return ("label", "validation", "Define a display name and color for each custom SWC type used in this file.")
    return ("structure", "validation", "Inspect the highlighted nodes and validation results after editing.")


def issues_from_validation_report(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Normalize failed/warning validation rows into unified issue records."""
    if not isinstance(report, dict):
        return []

    issues: list[Issue] = []
    blocked_groups: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(report.get("results", [])):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "")).strip().lower()
        if status == "pass":
            continue

        blocked = _blocked_reason_from_validation_row(row)
        if blocked:
            code = str(blocked.get("code", "")).strip() or f"blocked_{idx}"
            group = blocked_groups.setdefault(
                code,
                {
                    "meta": dict(blocked),
                    "rows": [],
                },
            )
            group["rows"].append(dict(row))
            continue

        key = str(row.get("key", "")).strip()
        label = str(row.get("label") or CHECK_LABEL.get(key) or key or "Issue").strip()
        domain, tool_target, suggested_fix = _tool_target_for_key(key)
        severity = _severity_from_validation_row(row)
        node_key = ",".join(str(int(v)) for v in row.get("failing_node_ids", []) if str(v).strip())
        section_key = ",".join(str(int(v)) for v in row.get("failing_section_ids", []) if str(v).strip())
        issue = Issue(
            issue_id=f"validation:{key or idx}:{node_key}:{section_key}",
            severity=severity,
            certainty="rule",
            domain=domain,
            title=label,
            description=str(row.get("message", "")).strip(),
            node_ids=[int(v) for v in row.get("failing_node_ids", []) if str(v).strip()],
            section_ids=[int(v) for v in row.get("failing_section_ids", []) if str(v).strip()],
            tool_target=tool_target,
            suggested_fix=suggested_fix,
            source_key=key,
            source_label=label,
            source_category=str(CHECK_CATEGORY.get(key, "Other")),
            source_payload=dict(row),
        )
        issues.append(issue)

    for code, payload in blocked_groups.items():
        meta = dict(payload.get("meta", {}) or {})
        rows = list(payload.get("rows", []) or [])
        blocked_checks = [
            {
                "key": str(row.get("key", "")).strip(),
                "label": str(row.get("label") or CHECK_LABEL.get(str(row.get("key", "")).strip()) or "Check").strip(),
            }
            for row in rows
        ]
        blocked_checks.sort(key=lambda item: CHECK_ORDER.get(item["key"], 10_000))
        reason = str(meta.get("reason", "")).strip() or "an upstream morphology problem"
        issue = Issue(
            issue_id=f"blocked:{code}",
            severity="info",
            certainty="rule",
            domain=str(meta.get("domain", "structure")).strip() or "structure",
            title=str(meta.get("title", "Checks blocked")).strip() or "Checks blocked",
            description=f"{len(blocked_checks)} checks could not run because of {reason.lower()}.",
            tool_target=str(meta.get("tool_target", "validation")).strip() or "validation",
            suggested_fix=str(meta.get("suggested_fix", "")).strip(),
            source_key="blocked_validation_checks",
            source_label=str(meta.get("title", "Checks blocked")).strip() or "Checks blocked",
            source_category="Blocked checks",
            source_payload={
                "blocked_reason_code": code,
                "blocked_reason": reason,
                "blocked_checks": blocked_checks,
            },
        )
        issues.append(issue)

    issues.sort(
        key=lambda item: (
            _SEVERITY_RANK.get(item.severity, 9),
            CHECK_ORDER.get(item.source_key, 10_000),
            _STATUS_RANK.get(item.status, 9),
            item.title.lower(),
        )
    )
    return [item.to_dict() for item in issues]


def issues_from_radii_suspicion(
    df: pd.DataFrame | None,
    *,
    limit: int = 0,
    ignore_node_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Surface likely abnormal radii as suspicious issues using the shared radii cleaner."""
    if df is None or df.empty:
        return []

    ignored = {int(v) for v in (ignore_node_ids or set())}
    try:
        result = clean_radii_dataframe(df)
    except Exception:
        return []

    changes: list[dict[str, Any]] = []
    for row in list(result.get("change_details", [])):
        node_id = int(row.get("node_id", -1))
        if node_id < 0 or node_id in ignored:
            continue
        new_radius = float(row.get("new_radius", 0.0))
        old_radius = float(row.get("old_radius", 0.0))
        reasons = list(row.get("reasons", []))
        changes.append(
            {
                "node_id": node_id,
                "old_radius": old_radius,
                "new_radius": new_radius,
                "reasons": reasons,
            }
        )

    changes.sort(key=lambda item: int(item["node_id"]))
    if limit > 0:
        changes = changes[: int(limit)]
    if not changes:
        return []

    node_ids = [int(item["node_id"]) for item in changes]
    issue = Issue(
        issue_id=f"suspicious:radii_batch:{node_ids[0]}:{node_ids[-1]}:{len(node_ids)}",
        severity="warning",
        certainty="suspicious",
        domain="radii",
        title="Outlier radii detected",
        description=f"{len(node_ids)} nodes have suspicious radii relative to nearby branches.",
        node_ids=node_ids,
        tool_target="radii_cleaning",
        suggested_fix=f"Review the suggested radii in Auto Radii Editing or inspect individual nodes in Manual Radii Editing.",
        source_key="radii_outlier_batch",
        source_label="Outlier radii detected",
        source_category="Suspicious radii",
        source_payload={
            "changes": changes,
        },
    )
    return [issue.to_dict()]


def issues_from_type_suspicion(
    rows: list[dict[str, Any]] | None,
    suggested_types: list[int] | None,
    *,
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Surface likely wrong labels by comparing current vs suggested node types."""
    if not rows or not suggested_types:
        return []

    changes: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if idx >= len(suggested_types):
            break
        node_id = int(row.get("id", -1))
        old_type = int(row.get("type", 0))
        new_type = int(suggested_types[idx])
        if node_id < 0 or old_type == new_type:
            continue
        changes.append(
            {
                "node_id": node_id,
                "old_type": old_type,
                "new_type": new_type,
            }
        )

    changes.sort(key=lambda item: int(item["node_id"]))
    if limit > 0:
        changes = changes[: int(limit)]
    if not changes:
        return []

    node_ids = [int(item["node_id"]) for item in changes]
    issue = Issue(
        issue_id=f"suspicious:type_batch:{node_ids[0]}:{node_ids[-1]}:{len(node_ids)}",
        severity="warning",
        certainty="suspicious",
        domain="label",
        title="Likely wrong labels",
        description=f"Rule-based typing found {len(node_ids)} nodes with likely incorrect neurite types.",
        node_ids=node_ids,
        tool_target="label_editing",
        suggested_fix=f"Apply the suggested labels to {len(node_ids)} nodes or inspect them manually in Morphology Editing.",
        source_key="type_suspicion_batch",
        source_label="Likely wrong labels",
        source_category="Suspicious labels",
        source_payload={
            "changes": changes,
        },
    )
    return [issue.to_dict()]
