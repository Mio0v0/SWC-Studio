"""swcstudio CLI.

The CLI is a thin interface layer over the shared tool/feature library API.
No algorithmic logic should live here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swcstudio.core.auto_typing import RuleBatchOptions
from swcstudio.core.auto_typing_catalog import format_auto_typing_guide_text
from swcstudio.core.config import merge_config
from swcstudio.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swcstudio.core.issues import build_issue_list
from swcstudio.plugins import (
    autoload_plugins_from_environment,
    list_all_feature_methods,
    list_feature_methods,
    list_plugins,
    load_plugin_module,
)
from swcstudio.tools.batch_processing.features.auto_typing import run_folder as run_auto_typing
from swcstudio.tools.batch_processing.features.batch_validation import validate_folder
from swcstudio.tools.batch_processing.features.index_clean import run_folder as batch_index_clean_folder
from swcstudio.tools.batch_processing.features.radii_cleaning import clean_path as batch_clean_radii_path
from swcstudio.tools.batch_processing.features.simplification import run_folder as batch_simplify_folder
from swcstudio.tools.batch_processing.features.swc_splitter import split_folder
from swcstudio.tools.geometry_editing.features.operations import (
    delete_node as geometry_delete_node,
    delete_subtree as geometry_delete_subtree,
    disconnect_branch as geometry_disconnect_branch,
    insert_node_between as geometry_insert_node_between,
    label_for_type,
    move_node_absolute as geometry_move_node_absolute,
    move_subtree_absolute as geometry_move_subtree_absolute,
    path_between_nodes,
    reconnect_branch as geometry_reconnect_branch,
    subtree_node_ids,
)
from swcstudio.tools.morphology_editing.features.dendrogram_editing import (
    reassign_subtree_types_in_file,
)
from swcstudio.tools.morphology_editing.features.manual_label import set_node_type_file
from swcstudio.tools.morphology_editing.features.manual_radii import set_node_radius_file
from swcstudio.tools.morphology_editing.features.simplification import (
    get_config as get_simplification_config,
    simplify_file as simplify_morphology_file,
)

from swcstudio.tools.validation.features.auto_fix import auto_fix_file
from swcstudio.tools.validation.features.auto_typing import auto_label_file as validation_auto_label_file
from swcstudio.tools.validation.features.index_clean import index_clean_file as validation_index_clean_file
from swcstudio.tools.validation.features.radii_cleaning import clean_path as validation_clean_radii_path
from swcstudio.tools.validation.features.run_checks import validate_file as run_validation_checks_file
from swcstudio.tools.validation import build_precheck_summary, load_validation_config
from swcstudio.tools.visualization.features.mesh_editing import build_mesh_from_file
from swcstudio.core.validation_catalog import group_rows_by_category, rule_for_key
from swcstudio.core.reporting import (
    format_validation_report_text,
    operation_output_path_for_file,
    operation_report_path_for_file,
    resolve_requested_output_path_for_file,
    validation_index_clean_detail_lines,
    validation_log_path_for_file,
    write_operation_report_for_file,
    write_text_report,
)


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _summarize_batch_radii_output(out: dict) -> dict:
    mode = str(out.get("mode", ""))
    if mode == "file":
        summary = {
            k: v
            for k, v in out.items()
            if k not in {"dataframe", "bytes", "config_used", "change_details", "change_lines"}
        }
        summary["change_count"] = int(out.get("change_count", len(list(out.get("change_details", []) or []))))
        return summary

    if mode == "folder":
        per_file_summary = []
        for row in list(out.get("per_file", []) or []):
            per_file_summary.append(
                {
                    "file": row.get("file"),
                    "radius_changes": int(row.get("radius_changes", 0)),
                    "change_count": int(row.get("change_count", 0)),
                    "out_file": row.get("out_file"),
                }
            )
        summary = {
            k: v
            for k, v in out.items()
            if k not in {"config_used", "per_file"}
        }
        summary["per_file"] = per_file_summary
        return summary

    return {
        k: v
        for k, v in out.items()
        if k not in {"dataframe", "bytes", "config_used", "change_details", "change_lines"}
    }


def _summarize_dendrogram_edit_output(out: dict) -> dict:
    changed_node_ids = list(out.get("changed_node_ids", []) or [])
    summary = {
        k: v
        for k, v in out.items()
        if k not in {"bytes", "dataframe", "changed_node_ids"}
    }
    summary["changed_node_count"] = len(changed_node_ids)
    if changed_node_ids:
        summary["changed_node_id_preview"] = changed_node_ids[:10]
    return summary


def _feature_json_arg(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--config-json",
        default="",
        help="Inline JSON object used to override feature config values for this run.",
    )


def _parse_config_overrides(raw: str) -> dict | None:
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--config-json must be a JSON object")
    return data


def _print_validation_precheck(report: dict) -> None:
    print("Pre-check Summary")
    print("-----------------")
    groups = group_rows_by_category(list(report.get("precheck", [])))
    for category, items in groups:
        print(f"{category}:")
        for item in items:
            key = str(item.get("key", ""))
            rule = rule_for_key(key)
            params = item.get("params") or {}
            print(f"- {item.get('label', item.get('key', ''))}")
            if rule:
                print(f"  rule: {rule}")
            if params:
                print(f"  params: {params}")
        print("")


def _status_tag(status: str) -> str:
    s = str(status or "").lower()
    if s == "pass":
        return "PASS"
    if s == "warning":
        return "WARN"
    return "FAIL"


def _print_validation_results(report: dict) -> None:
    summary = report.get("summary", {})
    print("")
    print("Validation Results")
    print("------------------")
    print(
        f"total={summary.get('total', 0)} "
        f"pass={summary.get('pass', 0)} "
        f"warning={summary.get('warning', 0)} "
        f"fail={summary.get('fail', 0)}"
    )
    groups = group_rows_by_category(list(report.get("results", [])))
    for category, items in groups:
        print(f"{category}:")
        for row in items:
            print(f"- [{_status_tag(str(row.get('status', '')))}] {row.get('label', row.get('key', ''))}")
        print("")

    details = [
        r
        for r in report.get("results", [])
        if r.get("status") in {"warning", "fail"}
    ]
    if details:
        print("")
        print("Detailed Findings")
        print("-----------------")
        for row in details:
            print(f"* {row.get('label', row.get('key', ''))} ({_status_tag(str(row.get('status', '')))})")
            print(f"  reason: {row.get('message')}")
            print(f"  params: {row.get('params_used', {})}")
            print(f"  thresholds: {row.get('thresholds_used', {})}")
            print(f"  failing_node_ids: {row.get('failing_node_ids', [])}")
            print(f"  failing_section_ids: {row.get('failing_section_ids', [])}")
            print(f"  metrics: {row.get('metrics', {})}")


def _print_auto_typing_guide() -> None:
    print(format_auto_typing_guide_text())
    print("")


def _print_simplification_rule_guide(cfg: dict | None = None) -> None:
    cfg0 = dict(cfg or {})
    thr = dict(cfg0.get("thresholds", {}))
    flags = dict(cfg0.get("flags", {}))
    eps = float(thr.get("epsilon", 2.0))
    radius_tol = float(thr.get("radius_tolerance", 0.5))
    keep_tips = bool(flags.get("keep_tips", True))
    keep_bifs = bool(flags.get("keep_bifurcations", True))
    keep_roots = bool(flags.get("keep_roots", True))
    lines = [
        "Simplification Rule Guide",
        "-------------------------",
        "1) Build directed SWC graph from id/parent.",
        "2) Protect structural nodes (roots + optional tips + optional bifurcations).",
        "3) Split into anchor-to-anchor linear paths.",
        "4) Run RDP on each path interior using epsilon.",
        "5) Protect radius-sensitive nodes when deviation exceeds radius_tolerance.",
        "6) Rewire kept nodes to nearest kept ancestor.",
        "",
        "Radius-sensitive rule:",
        "  abs(node_radius - path_mean_radius) / path_mean_radius > radius_tolerance",
        "",
        "Parameters used for this run:",
        f"- epsilon: {eps}",
        f"- radius_tolerance: {radius_tol}",
        f"- keep_tips: {keep_tips}",
        f"- keep_bifurcations: {keep_bifs}",
        f"- keep_roots: {keep_roots}",
        "",
    ]
    print("\n".join(lines))


def _print_batch_validation_results(batch_report: dict) -> None:
    print("")
    print("Batch Validation Results")
    print("------------------------")
    print(f"folder={batch_report.get('folder', '')}")
    print(
        f"files_total={batch_report.get('files_total', 0)} "
        f"files_validated={batch_report.get('files_validated', 0)} "
        f"files_failed={batch_report.get('files_failed', 0)}"
    )
    totals = dict(batch_report.get("summary_total", {}))
    print(
        f"checks_total={totals.get('total', 0)} "
        f"pass={totals.get('pass', 0)} "
        f"warning={totals.get('warning', 0)} "
        f"fail={totals.get('fail', 0)}"
    )

    for file_row in batch_report.get("results", []):
        file_name = str(file_row.get("file", ""))
        report = dict(file_row.get("report", {}))
        print("")
        print(f"File: {file_name}")
        _print_validation_results(report)

    fails = list(batch_report.get("failures", []))
    if fails:
        print("")
        print("Batch file-level errors")
        print("-----------------------")
        for err in fails:
            print(f"- {err}")


def _print_issue_check_results(file_path: Path, issues: list[dict]) -> None:
    critical = sum(1 for item in issues if str(item.get("severity", "")).strip() == "critical")
    warning = sum(1 for item in issues if str(item.get("severity", "")).strip() == "warning")
    info = sum(1 for item in issues if str(item.get("severity", "")).strip() == "info")
    muted = sum(1 for item in issues if str(item.get("status", "")).strip().lower() in {"muted", "skipped"})

    print("Issue Check")
    print("-----------")
    print(f"Input: {file_path}")
    print(f"Total: {len(issues)}")
    print(f"Critical: {critical}")
    print(f"Warning: {warning}")
    print(f"Info: {info}")
    print(f"Muted: {muted}")

    if not issues:
        print("")
        print("No issues found.")
        return

    grouped = {
        "critical": [item for item in issues if str(item.get("severity", "")).strip() == "critical"],
        "warning": [item for item in issues if str(item.get("severity", "")).strip() == "warning"],
        "info": [item for item in issues if str(item.get("severity", "")).strip() == "info"],
        "muted": [item for item in issues if str(item.get("status", "")).strip().lower() in {"muted", "skipped"}],
    }

    for label, items in grouped.items():
        if not items:
            continue
        print("")
        print(label.capitalize())
        print("-" * len(label.capitalize()))
        for idx, issue in enumerate(items, start=1):
            node_ids = [int(v) for v in issue.get("node_ids", []) if str(v).strip()]
            section_ids = [int(v) for v in issue.get("section_ids", []) if str(v).strip()]
            tool_target = str(issue.get("tool_target", "")).strip() or "validation"
            print(f"{idx}. {issue.get('title', 'Issue')}")
            print(f"   key: {issue.get('source_key', '') or 'n/a'}")
            print(f"   certainty: {issue.get('certainty', '') or 'n/a'}")
            print(f"   tool: {tool_target}")
            if issue.get("description"):
                print(f"   detail: {issue.get('description')}")
            if issue.get("suggested_fix"):
                print(f"   suggested fix: {issue.get('suggested_fix')}")
            if node_ids:
                preview = ", ".join(str(v) for v in node_ids[:20])
                if len(node_ids) > 20:
                    preview += f", ... (+{len(node_ids) - 20} more)"
                print(f"   node_ids ({len(node_ids)}): {preview}")
            if section_ids:
                preview = ", ".join(str(v) for v in section_ids[:20])
                if len(section_ids) > 20:
                    preview += f", ... (+{len(section_ids) - 20} more)"
                print(f"   section_ids ({len(section_ids)}): {preview}")


def _build_cli_issue_list(file_path: Path, *, config_overrides: dict | None = None) -> list[dict]:
    report = run_validation_checks_file(str(file_path), config_overrides=config_overrides).to_dict()
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    df = parse_swc_text_preserve_tokens(text)
    return build_issue_list(df, report)


def _write_geometry_output(
    input_path: Path,
    df,
    *,
    operation_name: str,
) -> str:
    output_path = operation_output_path_for_file(input_path, operation_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(write_swc_to_bytes_preserve_tokens(df))
    return str(output_path)


def _write_cli_operation_report(
    source_path: Path,
    *,
    operation_name: str,
    title: str,
    summary: str,
    details: list[str] | None = None,
    old_df=None,
    new_df=None,
    id_map: dict[int, int] | None = None,
    change_rows: list[dict] | None = None,
    output_dir: str | Path | None = None,
) -> str:
    return write_operation_report_for_file(
        source_path,
        operation_name,
        title=title,
        summary=summary,
        details=list(details or []),
        old_df=old_df,
        new_df=new_df,
        id_map=id_map,
        change_rows=change_rows,
        output_dir=output_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="swcstudio",
        description=(
            "SWC-Studio CLI. Use direct commands such as 'validate', 'radii-clean', "
            "'simplify', 'set-type', or 'connect'. Legacy grouped commands remain supported."
        ),
    )
    check = p.add_subparsers(dest="tool")
    check_cmd = check.add_parser("check", help="Print the GUI-style issue list for one SWC file")
    check_cmd.add_argument("file", type=Path)
    _feature_json_arg(check_cmd)
    sub = check

    # ------------------------------ batch
    batch = sub.add_parser("batch", help="Batch Processing features")
    batch_sub = batch.add_subparsers(dest="feature")

    batch_validate = batch_sub.add_parser(
        "validate",
        help="Batch Validation on a folder, or use literal rule-guide to print rules",
    )
    batch_validate.add_argument(
        "folder",
        type=Path,
        help="Folder path, or literal rule-guide",
    )
    _feature_json_arg(batch_validate)

    batch_split = batch_sub.add_parser("split", help="Split SWC files by soma roots")
    batch_split.add_argument("folder", type=Path)
    _feature_json_arg(batch_split)

    batch_auto = batch_sub.add_parser("auto-typing", help="Rule-based auto typing on folder")
    batch_auto.add_argument("folder", type=Path)
    batch_auto.add_argument("--soma", action="store_true", default=False)
    batch_auto.add_argument("--axon", action="store_true", default=False)
    batch_auto.add_argument("--apic", action="store_true", default=False)
    batch_auto.add_argument("--basal", action="store_true", default=False)
    _feature_json_arg(batch_auto)

    batch_radii = batch_sub.add_parser("radii-clean", help="Radii cleaning on a file or folder")
    batch_radii.add_argument("target", type=Path)
    _feature_json_arg(batch_radii)

    batch_simplify = batch_sub.add_parser("simplify", help="Run simplification on all SWC files in a folder")
    batch_simplify.add_argument("folder", type=Path)
    _feature_json_arg(batch_simplify)

    batch_index = batch_sub.add_parser("index-clean", help="Reorder and reindex all SWC files in a folder")
    batch_index.add_argument("folder", type=Path)
    _feature_json_arg(batch_index)

    # ------------------------------ validation
    validation = sub.add_parser("validation", help="Validation features")
    val_sub = validation.add_subparsers(dest="feature")

    val_auto_fix = val_sub.add_parser("auto-fix", help="Validate and sanitize one SWC file")
    val_auto_fix.add_argument("file", type=Path)
    _feature_json_arg(val_auto_fix)

    val_guide = val_sub.add_parser("rule-guide", help="Show validation rule guide (no file required)")
    _feature_json_arg(val_guide)

    val_run = val_sub.add_parser("run", help="Run structured validation checks on one SWC file")
    val_run.add_argument("file", type=Path)
    _feature_json_arg(val_run)

    val_auto_label = val_sub.add_parser("auto-label", help="Apply rule-based auto label editing to one SWC file")
    val_auto_label.add_argument("file", type=Path)
    val_auto_label.add_argument("--soma", action="store_true", default=False)
    val_auto_label.add_argument("--axon", action="store_true", default=False)
    val_auto_label.add_argument("--apic", action="store_true", default=False)
    val_auto_label.add_argument("--basal", action="store_true", default=False)
    _feature_json_arg(val_auto_label)

    val_radii = val_sub.add_parser("radii-clean", help="Radii cleaning on a file or folder")
    val_radii.add_argument("target", type=Path)
    _feature_json_arg(val_radii)

    val_index = val_sub.add_parser("index-clean", help="Reorder and reindex one SWC file")
    val_index.add_argument("file", type=Path)
    _feature_json_arg(val_index)

    # ------------------------------ visualization
    visualization = sub.add_parser("visualization", help="Visualization backends")
    viz_sub = visualization.add_subparsers(dest="feature")

    viz_mesh = viz_sub.add_parser("mesh-editing", help="Build reusable mesh payload for a file")
    viz_mesh.add_argument("file", type=Path)
    viz_mesh.add_argument("--include-edges", action="store_true", default=False)
    _feature_json_arg(viz_mesh)

    # ------------------------------ morphology
    morphology = sub.add_parser("morphology", help="Morphology Editing features")
    morph_sub = morphology.add_subparsers(dest="feature")

    morph_d = morph_sub.add_parser("dendrogram-edit", help="Reassign a subtree node type")
    morph_d.add_argument("file", type=Path)
    morph_d.add_argument("--node-id", required=True, type=int)
    morph_d.add_argument("--new-type", required=True, type=int)
    _feature_json_arg(morph_d)

    morph_radius = morph_sub.add_parser("set-radius", help="Set one node radius in a file")
    morph_radius.add_argument("file", type=Path)
    morph_radius.add_argument("--node-id", required=True, type=int)
    morph_radius.add_argument("--radius", required=True, type=float)
    _feature_json_arg(morph_radius)

    morph_type = morph_sub.add_parser("set-type", help="Set one node type in a file")
    morph_type.add_argument("file", type=Path)
    morph_type.add_argument("--node-id", required=True, type=int)
    morph_type.add_argument("--new-type", required=True, type=int)
    _feature_json_arg(morph_type)

    # ------------------------------ geometry
    geometry = sub.add_parser("geometry", help="Geometry editing operations without GUI")
    geom_sub = geometry.add_subparsers(dest="feature")

    geom_simplify = geom_sub.add_parser("simplify", help="Graph-aware SWC simplification")
    geom_simplify.add_argument("file", type=Path)
    _feature_json_arg(geom_simplify)

    geom_move_node = geom_sub.add_parser("move-node", help="Move one node to absolute XYZ")
    geom_move_node.add_argument("file", type=Path)
    geom_move_node.add_argument("--node-id", required=True, type=int)
    geom_move_node.add_argument("--x", required=True, type=float)
    geom_move_node.add_argument("--y", required=True, type=float)
    geom_move_node.add_argument("--z", required=True, type=float)
    geom_move_subtree = geom_sub.add_parser("move-subtree", help="Move a subtree by setting its root to absolute XYZ")
    geom_move_subtree.add_argument("file", type=Path)
    geom_move_subtree.add_argument("--root-id", required=True, type=int)
    geom_move_subtree.add_argument("--x", required=True, type=float)
    geom_move_subtree.add_argument("--y", required=True, type=float)
    geom_move_subtree.add_argument("--z", required=True, type=float)
    geom_connect = geom_sub.add_parser("connect", help="Set end-node parent to start-node")
    geom_connect.add_argument("file", type=Path)
    geom_connect.add_argument("--start-id", required=True, type=int)
    geom_connect.add_argument("--end-id", required=True, type=int)
    geom_disconnect = geom_sub.add_parser("disconnect", help="Disconnect all edges along the path between start and end")
    geom_disconnect.add_argument("file", type=Path)
    geom_disconnect.add_argument("--start-id", required=True, type=int)
    geom_disconnect.add_argument("--end-id", required=True, type=int)
    geom_delete = geom_sub.add_parser("delete-node", help="Delete one node")
    geom_delete.add_argument("file", type=Path)
    geom_delete.add_argument("--node-id", required=True, type=int)
    geom_delete.add_argument("--reconnect-children", action="store_true", default=False)
    geom_delete_sub = geom_sub.add_parser("delete-subtree", help="Delete one subtree")
    geom_delete_sub.add_argument("file", type=Path)
    geom_delete_sub.add_argument("--root-id", required=True, type=int)
    geom_insert = geom_sub.add_parser("insert", help="Insert a node after start and optionally before end")
    geom_insert.add_argument("file", type=Path)
    geom_insert.add_argument("--start-id", required=True, type=int)
    geom_insert.add_argument("--end-id", type=int, default=-1)
    geom_insert.add_argument("--x", required=True, type=float)
    geom_insert.add_argument("--y", required=True, type=float)
    geom_insert.add_argument("--z", required=True, type=float)
    geom_insert.add_argument("--radius", type=float, default=None)
    geom_insert.add_argument("--type-id", type=int, default=None)
    # ------------------------------ plugins
    plugins = sub.add_parser("plugins", help="Plugin manager and registry inspection")
    plugins_sub = plugins.add_subparsers(dest="feature")

    plugins_list = plugins_sub.add_parser("list", help="List plugin + builtin methods")
    plugins_list.add_argument("--feature-key", default="")
    plugins_list_loaded = plugins_sub.add_parser("list-loaded", help="List loaded plugin manifests")
    plugins_load = plugins_sub.add_parser("load", help="Load plugin module by import path")
    plugins_load.add_argument("module", help="Python module path, e.g. my_plugins.brain_globe")

    return p


def _looks_like_file_target(raw: str) -> bool:
    target = Path(str(raw or ""))
    if target.exists():
        return target.is_file()
    return target.suffix.lower() == ".swc"


def _normalize_cli_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv

    first = str(argv[0]).strip()
    if first in {
        "check",
        "batch",
        "validation",
        "visualization",
        "morphology",
        "geometry",
        "plugins",
    }:
        return argv

    if first == "plugins-list":
        return ["plugins", "list", *argv[1:]]
    if first == "plugins-list-loaded":
        return ["plugins", "list-loaded", *argv[1:]]
    if first == "plugins-load":
        return ["plugins", "load", *argv[1:]]

    if first == "rule-guide":
        return ["validation", "rule-guide", *argv[1:]]
    if first == "run":
        return ["validation", "run", *argv[1:]]
    if first == "auto-fix":
        return ["validation", "auto-fix", *argv[1:]]
    if first == "auto-label":
        return ["validation", "auto-label", *argv[1:]]
    if first == "radii-clean":
        return ["validation", "radii-clean", *argv[1:]]
    if first == "mesh-editing":
        return ["visualization", "mesh-editing", *argv[1:]]
    if first == "dendrogram-edit":
        return ["morphology", "dendrogram-edit", *argv[1:]]
    if first == "set-radius":
        return ["morphology", "set-radius", *argv[1:]]
    if first == "set-type":
        return ["morphology", "set-type", *argv[1:]]
    if first in {
        "move-node",
        "move-subtree",
        "connect",
        "disconnect",
        "delete-node",
        "delete-subtree",
        "insert",
    }:
        return ["geometry", first, *argv[1:]]
    if first == "split":
        return ["batch", "split", *argv[1:]]
    if first == "auto-typing":
        return ["batch", "auto-typing", *argv[1:]]

    if first == "validate":
        if len(argv) < 2:
            return argv
        target = str(argv[1]).strip()
        if target.lower() == "rule-guide":
            return ["validation", "rule-guide", *argv[2:]]
        if _looks_like_file_target(target):
            return ["validation", "run", *argv[1:]]
        return ["batch", "validate", *argv[1:]]

    if first == "simplify":
        if len(argv) < 2:
            return argv
        return (
            ["geometry", "simplify", *argv[1:]]
            if _looks_like_file_target(str(argv[1]))
            else ["batch", "simplify", *argv[1:]]
        )

    if first == "index-clean":
        if len(argv) < 2:
            return argv
        return (
            ["validation", "index-clean", *argv[1:]]
            if _looks_like_file_target(str(argv[1]))
            else ["batch", "index-clean", *argv[1:]]
        )

    return argv


def main(argv: list[str] | None = None) -> int:
    autoload_plugins_from_environment()
    argv = argv if argv is not None else sys.argv[1:]
    argv = _normalize_cli_argv(list(argv))
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.tool == "check":
            file_path = Path(args.file)
            if not file_path.exists():
                raise FileNotFoundError(str(file_path))
            issues = _build_cli_issue_list(file_path, config_overrides=_parse_config_overrides(args.config_json))
            _print_issue_check_results(file_path, issues)
            return 0

        # -------- batch
        if args.tool == "batch" and args.feature == "validate":
            cfg_overrides = _parse_config_overrides(args.config_json)
            target = str(args.folder).strip().lower()
            if target == "rule-guide":
                cfg = load_validation_config(overrides=cfg_overrides)
                precheck = [p.to_dict() for p in build_precheck_summary(cfg)]
                _print_validation_precheck({"precheck": precheck})
                return 0

            out = validate_folder(
                str(args.folder),
                config_overrides=cfg_overrides,
            )
            _print_validation_precheck({"precheck": out.get("precheck", [])})
            _print_batch_validation_results(out)
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
            return 0

        if args.tool == "batch" and args.feature == "split":
            out = split_folder(
                str(args.folder),
                config_overrides=_parse_config_overrides(args.config_json),
            )
            _print_json(out)
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
            return 0

        if args.tool == "batch" and args.feature == "auto-typing":
            _print_auto_typing_guide()
            has_explicit_flags = any(
                bool(v)
                for v in (args.soma, args.axon, args.apic, args.basal)
            )
            opts = (
                RuleBatchOptions(
                    soma=bool(args.soma),
                    axon=bool(args.axon),
                    apic=bool(args.apic),
                    basal=bool(args.basal),
                    rad=False,
                    zip_output=False,
                )
                if has_explicit_flags
                else None
            )
            out = run_auto_typing(
                str(args.folder),
                options=opts,
                config_overrides=_parse_config_overrides(args.config_json),
            )
            _print_json(out.__dict__)
            if getattr(out, "log_path", None):
                print(f"\nReport file: {out.log_path}")
            return 0

        if args.tool == "batch" and args.feature == "radii-clean":
            out = batch_clean_radii_path(
                str(args.target),
                config_overrides=_parse_config_overrides(args.config_json),
            )
            _print_json(_summarize_batch_radii_output(out))
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
            return 0

        if args.tool == "batch" and args.feature == "simplify":
            out = batch_simplify_folder(
                str(args.folder),
                config_overrides=_parse_config_overrides(args.config_json),
            )
            _print_json(out)
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
            return 0

        if args.tool == "batch" and args.feature == "index-clean":
            out = batch_index_clean_folder(
                str(args.folder),
                config_overrides=_parse_config_overrides(args.config_json),
            )
            _print_json(out)
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
            return 0

        # -------- validation
        if args.tool == "validation" and args.feature == "rule-guide":
            cfg = load_validation_config(overrides=_parse_config_overrides(args.config_json))
            precheck = [p.to_dict() for p in build_precheck_summary(cfg)]
            _print_validation_precheck({"precheck": precheck})
            return 0

        if args.tool == "validation" and args.feature == "run":
            report = run_validation_checks_file(
                str(args.file),
                config_overrides=_parse_config_overrides(args.config_json),
            ).to_dict()
            _print_validation_results(report)
            report_path = write_text_report(
                validation_log_path_for_file(args.file),
                format_validation_report_text(report),
            )
            print(f"\nReport file: {report_path}")
            return 0

        if args.tool == "validation" and args.feature == "radii-clean":
            out = validation_clean_radii_path(
                str(args.target),
                write_file_report=False,
                config_overrides=_parse_config_overrides(args.config_json),
            )
            if Path(args.target).is_file() and str(out.get("mode", "")) == "file":
                target_path = Path(args.target)
                old_df = parse_swc_text_preserve_tokens(target_path.read_text(encoding="utf-8", errors="ignore"))
                new_df = out.get("dataframe")
                change_rows = []
                for row in list(out.get("change_details", []) or []):
                    node_id = int(row.get("node_id", -1))
                    if node_id < 0:
                        continue
                    change_rows.append(
                        {
                            "node_id": str(node_id),
                            "changed_keys": ["radius"],
                            "old_values": {"radius": f"{float(row.get('old_radius', 0.0)):.10g}"},
                            "new_values": {"radius": f"{float(row.get('new_radius', 0.0)):.10g}"},
                            "old_parameters": f"radius={float(row.get('old_radius', 0.0)):.10g}",
                            "new_parameters": f"radius={float(row.get('new_radius', 0.0)):.10g}",
                        }
                    )
                out["operation_log_path"] = _write_cli_operation_report(
                    target_path,
                    operation_name="radii_cleaning",
                    title="Auto Radii Editing",
                    summary=(
                        "Applied automatic radii cleaning to current SWC; "
                        f"passes={int(out.get('passes', 0))}; "
                        f"radius_changes={int(out.get('radius_changes', 0))}."
                    ),
                    details=[],
                    old_df=old_df,
                    new_df=new_df,
                    change_rows=change_rows,
                )
            out_print = {
                k: v
                for k, v in out.items()
                if k not in {"dataframe", "bytes", "config_used", "change_details", "change_lines"}
            }
            if not out_print.get("log_path"):
                out_print.pop("log_path", None)
            _print_json(out_print)
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
            if out.get("operation_log_path"):
                print(f"Operation report: {out.get('operation_log_path')}")
            return 0

        if args.tool == "validation" and args.feature == "auto-fix":
            old_df = parse_swc_text_preserve_tokens(Path(args.file).read_text(encoding="utf-8", errors="ignore"))
            out = auto_fix_file(
                str(args.file),
                out_path=None,
                write_output=True,
                config_overrides=_parse_config_overrides(args.config_json),
            )
            report = out.get("report", {})
            if isinstance(report, dict):
                _print_validation_results(report)
                report_path = write_text_report(
                    operation_report_path_for_file(args.file, "validation_auto_fix"),
                    format_validation_report_text(report),
                )
                out["report_path"] = report_path
                print("\nReport file: " + report_path + "\n")
            try:
                new_df = parse_swc_text_preserve_tokens(str(out.get("sanitized_text", "") or ""))
                out["operation_log_path"] = _write_cli_operation_report(
                    Path(args.file),
                    operation_name="validation_auto_fix",
                    title="Validation Auto Fix",
                    summary="Validated and sanitized one SWC file.",
                    details=[
                        f"Input: {args.file}",
                        f"Output: {out.get('output_path') or ''}",
                        f"Result count: {len(list(out.get('rows', []) or []))}",
                    ],
                    old_df=old_df,
                    new_df=new_df,
                )
            except Exception:
                pass
            # Avoid dumping full sanitized SWC content in terminal.
            out_print = {
                "input_path": out.get("input_path"),
                "output_path": out.get("output_path"),
                "report_path": out.get("report_path"),
                "operation_log_path": out.get("operation_log_path"),
                "result_count": len(list(out.get("rows", []) or [])),
                "sanitized_text_length": len(str(out.get("sanitized_text", "") or "")),
            }
            _print_json(out_print)
            if out.get("operation_log_path"):
                print(f"Operation report: {out.get('operation_log_path')}")
            return 0

        if args.tool == "validation" and args.feature == "auto-label":
            has_explicit_flags = any(bool(v) for v in (args.soma, args.axon, args.apic, args.basal))
            opts = (
                RuleBatchOptions(
                    soma=bool(args.soma),
                    axon=bool(args.axon),
                    apic=bool(args.apic),
                    basal=bool(args.basal),
                    rad=False,
                    zip_output=False,
                )
                if has_explicit_flags
                else None
            )
            old_df = parse_swc_text_preserve_tokens(Path(args.file).read_text(encoding="utf-8", errors="ignore"))
            out = validation_auto_label_file(
                str(args.file),
                options=opts,
                config_overrides=_parse_config_overrides(args.config_json),
                output_path=None,
                write_output=True,
                write_log=False,
            )
            out_counts = dict(out.get("out_type_counts", {}) or {})
            out["operation_log_path"] = _write_cli_operation_report(
                Path(args.file),
                operation_name="validation_auto_label",
                title="Validation Auto Label Editing Run",
                summary=(
                    "Applied auto label editing to current SWC; "
                    f"type_changes={int(out.get('type_changes', 0))}"
                ),
                details=[
                    f"Input: {args.file}",
                    f"Nodes: {int(out.get('nodes_total', 0))}",
                    f"Type changes: {int(out.get('type_changes', 0))}",
                    "Out types (1/2/3/4): "
                    f"{out_counts.get(1, 0)}/{out_counts.get(2, 0)}/{out_counts.get(3, 0)}/{out_counts.get(4, 0)}",
                ],
                old_df=old_df,
                new_df=out.get("dataframe"),
            )
            out_print = {k: v for k, v in out.items() if k not in {"dataframe", "bytes", "result_obj"}}
            _print_json(out_print)
            if out.get("operation_log_path"):
                print(f"\nOperation report: {out.get('operation_log_path')}")
            return 0

        if args.tool == "validation" and args.feature == "index-clean":
            old_df = parse_swc_text_preserve_tokens(Path(args.file).read_text(encoding="utf-8", errors="ignore"))
            out = validation_index_clean_file(
                str(args.file),
                out_path=None,
                write_output=True,
                write_report=False,
                config_overrides=_parse_config_overrides(args.config_json),
            )
            out["operation_log_path"] = _write_cli_operation_report(
                Path(args.file),
                operation_name="validation_index_clean",
                title="Validation Index Clean",
                summary="Reordered and reindexed the SWC for clean parent-before-child indexing.",
                details=validation_index_clean_detail_lines(
                    input_path=str(args.file),
                    output_path=str(out.get("output_path") or ""),
                    original_node_count=int(out.get("original_node_count", 0)),
                    new_node_count=int(out.get("new_node_count", 0)),
                    remapped_id_count=int(out.get("remapped_id_count", 0)),
                ),
                old_df=old_df,
                new_df=out.get("dataframe"),
                id_map=dict(out.get("id_map", {}) or {}),
            )
            out_print = {k: v for k, v in out.items() if k not in {"bytes", "dataframe", "id_map", "config_used"}}
            if not out_print.get("log_path"):
                out_print.pop("log_path", None)
            out_print["id_map_size"] = len(dict(out.get("id_map", {})))
            _print_json(out_print)
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
            if out.get("operation_log_path"):
                print(f"Operation report: {out.get('operation_log_path')}")
            return 0

        # -------- visualization
        if args.tool == "visualization" and args.feature == "mesh-editing":
            cfg = _parse_config_overrides(args.config_json) or {}
            if args.include_edges:
                cfg["output"] = dict(cfg.get("output", {}))
                cfg["output"]["include_edges"] = True
            out = build_mesh_from_file(str(args.file), config_overrides=cfg)
            _print_json(out)
            return 0

        # -------- morphology
        if args.tool == "morphology" and args.feature == "dendrogram-edit":
            old_df = parse_swc_text_preserve_tokens(Path(args.file).read_text(encoding="utf-8", errors="ignore"))
            out = reassign_subtree_types_in_file(
                str(args.file),
                node_id=int(args.node_id),
                new_type=int(args.new_type),
                out_path=None,
                write_output=True,
                config_overrides=_parse_config_overrides(args.config_json),
            )
            out["operation_log_path"] = _write_cli_operation_report(
                Path(args.file),
                operation_name="morphology_dendrogram_edit",
                title="Manual Label Edit",
                summary="Applied labeling edits in Morphology Editing.",
                details=[],
                    old_df=old_df,
                    new_df=out.get("dataframe"),
            )
            out_print = _summarize_dendrogram_edit_output(out)
            _print_json(out_print)
            if out.get("operation_log_path"):
                print(f"\nOperation report: {out.get('operation_log_path')}")
            return 0

        if args.tool == "morphology" and args.feature == "set-radius":
            old_df = parse_swc_text_preserve_tokens(Path(args.file).read_text(encoding="utf-8", errors="ignore"))
            out = set_node_radius_file(
                str(args.file),
                node_id=int(args.node_id),
                radius=float(args.radius),
                out_path=None,
                write_output=True,
                config_overrides=_parse_config_overrides(args.config_json),
            )
            out["operation_log_path"] = _write_cli_operation_report(
                Path(args.file),
                operation_name="morphology_set_radius",
                title="Manual Radius Edit",
                summary=(
                    f"Updated node {int(args.node_id)} radius from "
                    f"{float(out.get('old_radius', 0.0)):.6g} to {float(out.get('new_radius', 0.0)):.6g}."
                ),
                details=[],
                old_df=old_df,
                new_df=out.get("dataframe"),
            )
            out_print = {k: v for k, v in out.items() if k not in {"bytes", "dataframe", "config_used"}}
            _print_json(out_print)
            if out.get("operation_log_path"):
                print(f"\nOperation report: {out.get('operation_log_path')}")
            return 0

        if args.tool == "morphology" and args.feature == "set-type":
            old_df = parse_swc_text_preserve_tokens(Path(args.file).read_text(encoding="utf-8", errors="ignore"))
            out = set_node_type_file(
                str(args.file),
                node_id=int(args.node_id),
                new_type=int(args.new_type),
                out_path=None,
                write_output=True,
                config_overrides=_parse_config_overrides(args.config_json),
            )
            out["operation_log_path"] = _write_cli_operation_report(
                Path(args.file),
                operation_name="morphology_set_type",
                title="Manual Label Edit",
                summary="Applied labeling edits in Morphology Editing.",
                details=[],
                old_df=old_df,
                new_df=out.get("dataframe"),
            )
            out_print = {k: v for k, v in out.items() if k not in {"bytes", "dataframe", "config_used"}}
            _print_json(out_print)
            if out.get("operation_log_path"):
                print(f"\nOperation report: {out.get('operation_log_path')}")
            return 0

        # -------- geometry
        if args.tool == "geometry" and args.feature:
            if args.feature == "simplify":
                old_df = parse_swc_text_preserve_tokens(Path(args.file).read_text(encoding="utf-8", errors="ignore"))
                cfg_overrides = _parse_config_overrides(args.config_json)
                cfg_effective = merge_config(get_simplification_config(), cfg_overrides or {})
                _print_simplification_rule_guide(cfg_effective)
                out = simplify_morphology_file(
                    str(args.file),
                    out_path=None,
                    write_output=True,
                    write_report=False,
                    config_overrides=cfg_overrides,
                )
                out_print = {
                    k: v
                    for k, v in out.items()
                    if k not in {"bytes", "dataframe", "kept_node_ids", "removed_node_ids", "summary"}
                }
                out["operation_log_path"] = _write_cli_operation_report(
                    Path(args.file),
                    operation_name="geometry_simplify",
                    title="Simplification",
                    summary=(
                        f"Simplified the current SWC from {int(out.get('original_node_count', 0))} "
                        f"to {int(out.get('new_node_count', 0))} nodes."
                    ),
                    details=[
                        f"Reduction (%): {float(out.get('reduction_percent', 0.0)):.2f}",
                        f"Removed nodes: {len(list(out.get('removed_node_ids', []) or []))}",
                        f"Protected counts: {dict(out.get('protected_counts', {}))}",
                        f"Parameters used: {dict(out.get('params_used', {}))}",
                    ],
                    old_df=old_df,
                    new_df=out.get("dataframe"),
                )
                out_print["kept_node_count"] = len(list(out.get("kept_node_ids", [])))
                out_print["removed_node_count"] = len(list(out.get("removed_node_ids", [])))
                if not out_print.get("log_path"):
                    out_print.pop("log_path", None)
                out_print["operation_log_path"] = out.get("operation_log_path")
                _print_json(out_print)
                if out.get("log_path"):
                    print(f"\nReport file: {out.get('log_path')}")
                if out.get("operation_log_path"):
                    print(f"Operation report: {out.get('operation_log_path')}")
                return 0

            file_path = Path(args.file)
            if not file_path.exists():
                raise FileNotFoundError(str(file_path))
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            df = parse_swc_text_preserve_tokens(text)

            if args.feature == "move-node":
                out_df = geometry_move_node_absolute(df, int(args.node_id), float(args.x), float(args.y), float(args.z))
                output_path = _write_geometry_output(
                    file_path,
                    out_df,
                    operation_name="geometry_move_node",
                )
                operation_log_path = _write_cli_operation_report(
                    file_path,
                    operation_name="geometry_move_node",
                    title="Move Node",
                    summary=f"Moved node {int(args.node_id)} to absolute coordinates.",
                    details=[
                        f"Node ID: {int(args.node_id)}",
                        f"New XYZ: ({float(args.x):.5g}, {float(args.y):.5g}, {float(args.z):.5g})",
                        f"Output: {output_path or '(not written)'}",
                    ],
                    old_df=df,
                    new_df=out_df,
                    output_dir=Path(output_path).parent,
                )
                _print_json({"operation": "move-node", "node_id": int(args.node_id), "output_path": output_path, "operation_log_path": operation_log_path})
                return 0

            if args.feature == "move-subtree":
                out_df = geometry_move_subtree_absolute(df, int(args.root_id), float(args.x), float(args.y), float(args.z))
                output_path = _write_geometry_output(
                    file_path,
                    out_df,
                    operation_name="geometry_move_subtree",
                )
                operation_log_path = _write_cli_operation_report(
                    file_path,
                    operation_name="geometry_move_subtree",
                    title="Move Subtree",
                    summary=f"Moved subtree rooted at node {int(args.root_id)} to absolute coordinates.",
                    details=[
                        f"Root node ID: {int(args.root_id)}",
                        f"New XYZ: ({float(args.x):.5g}, {float(args.y):.5g}, {float(args.z):.5g})",
                        f"Output: {output_path or '(not written)'}",
                    ],
                    old_df=df,
                    new_df=out_df,
                    output_dir=Path(output_path).parent,
                )
                _print_json({"operation": "move-subtree", "root_id": int(args.root_id), "output_path": output_path, "operation_log_path": operation_log_path})
                return 0

            if args.feature == "connect":
                end_row = df.loc[df["id"].astype(int) == int(args.end_id)].iloc[0]
                old_parent = int(end_row["parent"])
                out_df = geometry_reconnect_branch(df, int(args.start_id), int(args.end_id))
                output_path = _write_geometry_output(
                    file_path,
                    out_df,
                    operation_name="geometry_connect",
                )
                operation_log_path = _write_cli_operation_report(
                    file_path,
                    operation_name="geometry_connect",
                    title="Reconnect Branch",
                    summary=f"Connected end node {int(args.end_id)} to start node {int(args.start_id)}.",
                    details=[
                        f"Start node ID: {int(args.start_id)}",
                        f"End node ID: {int(args.end_id)}",
                        f"End node old parent ID: {old_parent}",
                        f"End node new parent ID: {int(args.start_id)}",
                        "Node IDs preserved; no automatic renumbering.",
                    ],
                    old_df=df,
                    new_df=out_df,
                    output_dir=Path(output_path).parent,
                )
                _print_json({
                    "operation": "connect",
                    "start_id": int(args.start_id),
                    "end_id": int(args.end_id),
                    "output_path": output_path,
                    "operation_log_path": operation_log_path,
                })
                return 0

            if args.feature == "disconnect":
                parent_by_id = {
                    int(row["id"]): int(row["parent"])
                    for _, row in df[["id", "parent"]].iterrows()
                }
                path = path_between_nodes(df, int(args.start_id), int(args.end_id))
                if len(path) < 2:
                    raise ValueError("Start and end nodes are not connected.")
                disconnected_children: list[int] = []
                old_edges: list[str] = []
                for left, right in zip(path[:-1], path[1:]):
                    left = int(left)
                    right = int(right)
                    if int(parent_by_id.get(left, -1)) == right:
                        disconnected_children.append(left)
                        old_edges.append(f"{right} -> {left}")
                    elif int(parent_by_id.get(right, -1)) == left:
                        disconnected_children.append(right)
                        old_edges.append(f"{left} -> {right}")
                    else:
                        raise ValueError("Encountered a non-parent-child step while disconnecting the selected path.")
                out_df = geometry_disconnect_branch(df, int(args.start_id), int(args.end_id))
                output_path = _write_geometry_output(
                    file_path,
                    out_df,
                    operation_name="geometry_disconnect",
                )
                operation_log_path = _write_cli_operation_report(
                    file_path,
                    operation_name="geometry_disconnect",
                    title="Disconnect Branch",
                    summary=f"Disconnected the path between {int(args.start_id)} and {int(args.end_id)}.",
                    details=[
                        f"Start node ID: {int(args.start_id)}",
                        f"End node ID: {int(args.end_id)}",
                        f"Path nodes: {', '.join(str(v) for v in path)}",
                        f"Disconnected child node IDs: {', '.join(str(v) for v in disconnected_children)}",
                        f"Disconnected edges: {', '.join(old_edges)}",
                        "New parent IDs on disconnected child nodes: -1",
                        "Node IDs preserved; no automatic renumbering.",
                    ],
                    old_df=df,
                    new_df=out_df,
                    output_dir=Path(output_path).parent,
                )
                _print_json({
                    "operation": "disconnect",
                    "start_id": int(args.start_id),
                    "end_id": int(args.end_id),
                    "output_path": output_path,
                    "operation_log_path": operation_log_path,
                })
                return 0

            if args.feature == "delete-node":
                row = df.loc[df["id"].astype(int) == int(args.node_id)].iloc[0]
                child_count = int((df["parent"].astype(int) == int(args.node_id)).sum())
                out_df = geometry_delete_node(df, int(args.node_id), reconnect_children=bool(args.reconnect_children))
                output_path = _write_geometry_output(
                    file_path,
                    out_df,
                    operation_name="geometry_delete_node",
                )
                operation_log_path = _write_cli_operation_report(
                    file_path,
                    operation_name="geometry_delete_node",
                    title="Delete Node" if not bool(args.reconnect_children) else "Delete Node + Reconnect Children",
                    summary=f"Deleted node {int(args.node_id)}.",
                    details=[
                        f"Node ID: {int(args.node_id)}",
                        f"Type: {label_for_type(int(row['type']))} ({int(row['type'])})",
                        f"Child count: {child_count}",
                        f"Reconnect children: {'yes' if bool(args.reconnect_children) else 'no'}",
                        "Remaining node IDs preserved; no automatic renumbering.",
                    ],
                    old_df=df,
                    new_df=out_df,
                    output_dir=Path(output_path).parent,
                )
                _print_json({
                    "operation": "delete-node",
                    "node_id": int(args.node_id),
                    "reconnect_children": bool(args.reconnect_children),
                    "output_path": output_path,
                    "operation_log_path": operation_log_path,
                })
                return 0

            if args.feature == "delete-subtree":
                subtree_size = int(len(subtree_node_ids(df, int(args.root_id))))
                out_df = geometry_delete_subtree(df, int(args.root_id))
                output_path = _write_geometry_output(
                    file_path,
                    out_df,
                    operation_name="geometry_delete_subtree",
                )
                operation_log_path = _write_cli_operation_report(
                    file_path,
                    operation_name="geometry_delete_subtree",
                    title="Delete Subtree",
                    summary=f"Deleted subtree rooted at node {int(args.root_id)}.",
                    details=[
                        f"Subtree root ID: {int(args.root_id)}",
                        f"Removed node count: {subtree_size}",
                        "Remaining node IDs preserved; no automatic renumbering.",
                    ],
                    old_df=df,
                    new_df=out_df,
                    output_dir=Path(output_path).parent,
                )
                _print_json({
                    "operation": "delete-subtree",
                    "root_id": int(args.root_id),
                    "output_path": output_path,
                    "operation_log_path": operation_log_path,
                })
                return 0

            if args.feature == "insert":
                end_row = None
                if int(args.end_id) >= 0:
                    end_row = df.loc[df["id"].astype(int) == int(args.end_id)].iloc[0]
                inserted_node_id = int(df["id"].astype(int).max()) + 1
                out_df = geometry_insert_node_between(
                    df,
                    int(args.start_id),
                    int(args.end_id),
                    x=float(args.x),
                    y=float(args.y),
                    z=float(args.z),
                    radius=args.radius,
                    type_id=args.type_id,
                )
                output_path = _write_geometry_output(
                    file_path,
                    out_df,
                    operation_name="geometry_insert",
                )
                operation_log_path = _write_cli_operation_report(
                    file_path,
                    operation_name="geometry_insert",
                    title="Insert Node",
                    summary=(
                        f"Inserted a node between {int(args.start_id)} and {int(args.end_id)}."
                        if int(args.end_id) >= 0
                        else f"Inserted a child node under {int(args.start_id)}."
                    ),
                    details=[
                        f"Start node ID: {int(args.start_id)}",
                        f"End node ID: {int(args.end_id)}" if int(args.end_id) >= 0 else "End node ID: None",
                        f"Inserted node ID: {inserted_node_id}",
                        (
                            f"End node type: {label_for_type(int(end_row['type']))} ({int(end_row['type'])})"
                            if end_row is not None
                            else "Inserted node has no child; end node was not provided."
                        ),
                        f"Inserted XYZ: ({float(args.x):.5g}, {float(args.y):.5g}, {float(args.z):.5g})",
                        "Existing node IDs preserved; inserted node uses max(existing ID)+1.",
                    ],
                    old_df=df,
                    new_df=out_df,
                    output_dir=Path(output_path).parent,
                )
                _print_json({
                    "operation": "insert",
                    "start_id": int(args.start_id),
                    "end_id": int(args.end_id),
                    "output_path": output_path,
                    "operation_log_path": operation_log_path,
                })
                return 0

        # -------- plugins
        if args.tool == "plugins" and args.feature == "list":
            if args.feature_key:
                _print_json(list_feature_methods(args.feature_key))
            else:
                _print_json(list_all_feature_methods())
            return 0
        if args.tool == "plugins" and args.feature == "list-loaded":
            _print_json({"plugins": list_plugins()})
            return 0
        if args.tool == "plugins" and args.feature == "load":
            _print_json(load_plugin_module(str(args.module)))
            return 0

        parser.print_help()
        return 1

    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
