"""swctools CLI.

The CLI is a thin interface layer over the shared tool/feature library API.
No algorithmic logic should live here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swctools.core.auto_typing import RuleBatchOptions
from swctools.core.auto_typing_catalog import format_auto_typing_guide_text
from swctools.core.config import merge_config
from swctools.core.geometry_editing import (
    delete_node as geometry_delete_node,
    delete_subtree as geometry_delete_subtree,
    disconnect_branch as geometry_disconnect_branch,
    insert_node_between as geometry_insert_node_between,
    move_node_absolute as geometry_move_node_absolute,
    move_subtree_absolute as geometry_move_subtree_absolute,
    reconnect_branch as geometry_reconnect_branch,
)
from swctools.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swctools.core.issues import build_issue_list, issues_from_type_suspicion
from swctools.plugins import (
    autoload_plugins_from_environment,
    list_all_feature_methods,
    list_feature_methods,
    list_plugins,
    load_plugin_module,
)
from swctools.tools.batch_processing.features.auto_typing import run_folder as run_auto_typing
from swctools.tools.batch_processing.features.batch_validation import validate_folder
from swctools.tools.batch_processing.features.index_clean import run_folder as batch_index_clean_folder
from swctools.tools.batch_processing.features.radii_cleaning import clean_path as batch_clean_radii_path
from swctools.tools.batch_processing.features.simplification import run_folder as batch_simplify_folder
from swctools.tools.batch_processing.features.swc_splitter import split_folder
from swctools.tools.morphology_editing.features.dendrogram_editing import (
    reassign_subtree_types_in_file,
)
from swctools.tools.morphology_editing.features.manual_radii import set_node_radius_file
from swctools.tools.morphology_editing.features.simplification import (
    get_config as get_simplification_config,
    simplify_file as simplify_morphology_file,
)

from swctools.tools.validation.features.auto_fix import auto_fix_file
from swctools.tools.validation.features.auto_typing import run_file as run_validation_auto_typing_file
from swctools.tools.validation.features.index_clean import index_clean_file as validation_index_clean_file
from swctools.tools.validation.features.radii_cleaning import clean_path as validation_clean_radii_path
from swctools.tools.validation.features.run_checks import validate_file as run_validation_checks_file
from swctools.tools.validation import build_precheck_summary, load_validation_config
from swctools.tools.visualization.features.mesh_editing import build_mesh_from_file
from swctools.core.validation_catalog import group_rows_by_category, rule_for_key
from swctools.core.reporting import (
    format_validation_report_text,
    validation_log_path_for_file,
    write_text_report,
)


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


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
    report = run_validation_checks_file(str(file_path), config_overrides=config_overrides)
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    df = parse_swc_text_preserve_tokens(text)

    type_suspicious: list[dict] = []
    try:
        result_obj = run_validation_auto_typing_file(
            str(file_path),
            write_output=False,
            write_log=False,
        )
        type_suspicious = issues_from_type_suspicion(
            list(getattr(result_obj, "rows", []) or []),
            list(getattr(result_obj, "types", []) or []),
        )
    except Exception:
        type_suspicious = []

    return build_issue_list(df, report, type_suspicious=type_suspicious)


def _write_geometry_output(input_path: Path, df, *, out_path: str = "", write_output: bool = False, suffix: str) -> str | None:
    output_path: Path | None = None
    if write_output:
        output_path = Path(out_path) if out_path else input_path.with_name(f"{input_path.stem}{suffix}{input_path.suffix}")
        output_path.write_bytes(write_swc_to_bytes_preserve_tokens(df))
    return str(output_path) if output_path else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="swctools")
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
    val_auto_fix.add_argument("--write", action="store_true", default=False)
    val_auto_fix.add_argument("--out", default="", help="Output file path (used with --write)")
    _feature_json_arg(val_auto_fix)

    val_guide = val_sub.add_parser("rule-guide", help="Show validation rule guide (no file required)")
    _feature_json_arg(val_guide)

    val_run = val_sub.add_parser("run", help="Run structured validation checks on one SWC file")
    val_run.add_argument("file", type=Path)
    _feature_json_arg(val_run)

    val_radii = val_sub.add_parser("radii-clean", help="Radii cleaning on a file or folder")
    val_radii.add_argument("target", type=Path)
    _feature_json_arg(val_radii)

    val_index = val_sub.add_parser("index-clean", help="Reorder and reindex one SWC file")
    val_index.add_argument("file", type=Path)
    val_index.add_argument("--write", action="store_true", default=False)
    val_index.add_argument("--out", default="", help="Output file path (used with --write)")
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
    morph_d.add_argument("--write", action="store_true", default=False)
    morph_d.add_argument("--out", default="", help="Output file path (used with --write)")
    _feature_json_arg(morph_d)

    morph_radius = morph_sub.add_parser("set-radius", help="Set one node radius in a file")
    morph_radius.add_argument("file", type=Path)
    morph_radius.add_argument("--node-id", required=True, type=int)
    morph_radius.add_argument("--radius", required=True, type=float)
    morph_radius.add_argument("--write", action="store_true", default=False)
    morph_radius.add_argument("--out", default="", help="Output file path (used with --write)")
    _feature_json_arg(morph_radius)

    # ------------------------------ geometry
    geometry = sub.add_parser("geometry", help="Geometry editing operations without GUI")
    geom_sub = geometry.add_subparsers(dest="feature")

    geom_simplify = geom_sub.add_parser("simplify", help="Graph-aware SWC simplification")
    geom_simplify.add_argument("file", type=Path)
    geom_simplify.add_argument("--write", action="store_true", default=False)
    geom_simplify.add_argument("--out", default="", help="Output file path (used with --write)")
    _feature_json_arg(geom_simplify)

    geom_move_node = geom_sub.add_parser("move-node", help="Move one node to absolute XYZ")
    geom_move_node.add_argument("file", type=Path)
    geom_move_node.add_argument("--node-id", required=True, type=int)
    geom_move_node.add_argument("--x", required=True, type=float)
    geom_move_node.add_argument("--y", required=True, type=float)
    geom_move_node.add_argument("--z", required=True, type=float)
    geom_move_node.add_argument("--write", action="store_true", default=False)
    geom_move_node.add_argument("--out", default="", help="Output file path (used with --write)")

    geom_move_subtree = geom_sub.add_parser("move-subtree", help="Move a subtree by setting its root to absolute XYZ")
    geom_move_subtree.add_argument("file", type=Path)
    geom_move_subtree.add_argument("--root-id", required=True, type=int)
    geom_move_subtree.add_argument("--x", required=True, type=float)
    geom_move_subtree.add_argument("--y", required=True, type=float)
    geom_move_subtree.add_argument("--z", required=True, type=float)
    geom_move_subtree.add_argument("--write", action="store_true", default=False)
    geom_move_subtree.add_argument("--out", default="", help="Output file path (used with --write)")

    geom_connect = geom_sub.add_parser("connect", help="Set end-node parent to start-node")
    geom_connect.add_argument("file", type=Path)
    geom_connect.add_argument("--start-id", required=True, type=int)
    geom_connect.add_argument("--end-id", required=True, type=int)
    geom_connect.add_argument("--write", action="store_true", default=False)
    geom_connect.add_argument("--out", default="", help="Output file path (used with --write)")

    geom_disconnect = geom_sub.add_parser("disconnect", help="Disconnect all edges along the path between start and end")
    geom_disconnect.add_argument("file", type=Path)
    geom_disconnect.add_argument("--start-id", required=True, type=int)
    geom_disconnect.add_argument("--end-id", required=True, type=int)
    geom_disconnect.add_argument("--write", action="store_true", default=False)
    geom_disconnect.add_argument("--out", default="", help="Output file path (used with --write)")

    geom_delete = geom_sub.add_parser("delete-node", help="Delete one node")
    geom_delete.add_argument("file", type=Path)
    geom_delete.add_argument("--node-id", required=True, type=int)
    geom_delete.add_argument("--reconnect-children", action="store_true", default=False)
    geom_delete.add_argument("--write", action="store_true", default=False)
    geom_delete.add_argument("--out", default="", help="Output file path (used with --write)")

    geom_delete_sub = geom_sub.add_parser("delete-subtree", help="Delete one subtree")
    geom_delete_sub.add_argument("file", type=Path)
    geom_delete_sub.add_argument("--root-id", required=True, type=int)
    geom_delete_sub.add_argument("--write", action="store_true", default=False)
    geom_delete_sub.add_argument("--out", default="", help="Output file path (used with --write)")

    geom_insert = geom_sub.add_parser("insert", help="Insert a node after start and optionally before end")
    geom_insert.add_argument("file", type=Path)
    geom_insert.add_argument("--start-id", required=True, type=int)
    geom_insert.add_argument("--end-id", type=int, default=-1)
    geom_insert.add_argument("--x", required=True, type=float)
    geom_insert.add_argument("--y", required=True, type=float)
    geom_insert.add_argument("--z", required=True, type=float)
    geom_insert.add_argument("--radius", type=float, default=None)
    geom_insert.add_argument("--type-id", type=int, default=None)
    geom_insert.add_argument("--write", action="store_true", default=False)
    geom_insert.add_argument("--out", default="", help="Output file path (used with --write)")

    # ------------------------------ plugins
    plugins = sub.add_parser("plugins", help="Plugin manager and registry inspection")
    plugins_sub = plugins.add_subparsers(dest="feature")

    plugins_list = plugins_sub.add_parser("list", help="List plugin + builtin methods")
    plugins_list.add_argument("--feature-key", default="")
    plugins_list_loaded = plugins_sub.add_parser("list-loaded", help="List loaded plugin manifests")
    plugins_load = plugins_sub.add_parser("load", help="Load plugin module by import path")
    plugins_load.add_argument("module", help="Python module path, e.g. my_plugins.brain_globe")

    return p


def main(argv: list[str] | None = None) -> int:
    autoload_plugins_from_environment()
    argv = argv if argv is not None else sys.argv[1:]
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
            _print_json(out)
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
                config_overrides=_parse_config_overrides(args.config_json),
            )
            _print_json(out)
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
            return 0

        if args.tool == "validation" and args.feature == "auto-fix":
            out = auto_fix_file(
                str(args.file),
                out_path=(args.out or None),
                write_output=bool(args.write),
                config_overrides=_parse_config_overrides(args.config_json),
            )
            report = out.get("report", {})
            if isinstance(report, dict):
                _print_validation_results(report)
                report_path = write_text_report(
                    validation_log_path_for_file(args.file),
                    format_validation_report_text(report),
                )
                out["report_path"] = report_path
                print("\nReport file: " + report_path + "\n")
            # Avoid dumping full sanitized SWC content in terminal.
            out_print = {
                "input_path": out.get("input_path"),
                "output_path": out.get("output_path"),
                "report_path": out.get("report_path"),
                "result_count": len(list(out.get("rows", []) or [])),
                "sanitized_text_length": len(str(out.get("sanitized_text", "") or "")),
            }
            _print_json(out_print)
            return 0

        if args.tool == "validation" and args.feature == "index-clean":
            out = validation_index_clean_file(
                str(args.file),
                out_path=(args.out or None),
                write_output=bool(args.write),
                config_overrides=_parse_config_overrides(args.config_json),
            )
            out_print = {k: v for k, v in out.items() if k not in {"bytes", "dataframe", "id_map", "config_used"}}
            out_print["id_map_size"] = len(dict(out.get("id_map", {})))
            _print_json(out_print)
            if out.get("log_path"):
                print(f"\nReport file: {out.get('log_path')}")
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
            out = reassign_subtree_types_in_file(
                str(args.file),
                node_id=int(args.node_id),
                new_type=int(args.new_type),
                out_path=(args.out or None),
                write_output=bool(args.write),
                config_overrides=_parse_config_overrides(args.config_json),
            )
            out = {k: v for k, v in out.items() if k not in {"bytes", "dataframe"}}
            _print_json(out)
            return 0

        if args.tool == "morphology" and args.feature == "set-radius":
            out = set_node_radius_file(
                str(args.file),
                node_id=int(args.node_id),
                radius=float(args.radius),
                out_path=(args.out or None),
                write_output=bool(args.write),
                config_overrides=_parse_config_overrides(args.config_json),
            )
            out_print = {k: v for k, v in out.items() if k not in {"bytes", "dataframe", "config_used"}}
            _print_json(out_print)
            return 0

        # -------- geometry
        if args.tool == "geometry" and args.feature:
            if args.feature == "simplify":
                cfg_overrides = _parse_config_overrides(args.config_json)
                cfg_effective = merge_config(get_simplification_config(), cfg_overrides or {})
                _print_simplification_rule_guide(cfg_effective)
                out = simplify_morphology_file(
                    str(args.file),
                    out_path=(args.out or None),
                    write_output=bool(args.write),
                    config_overrides=cfg_overrides,
                )
                out_print = {
                    k: v
                    for k, v in out.items()
                    if k not in {"bytes", "dataframe", "kept_node_ids", "removed_node_ids", "summary"}
                }
                out_print["kept_node_count"] = len(list(out.get("kept_node_ids", [])))
                out_print["removed_node_count"] = len(list(out.get("removed_node_ids", [])))
                _print_json(out_print)
                if out.get("log_path"):
                    print(f"\nReport file: {out.get('log_path')}")
                return 0

            file_path = Path(args.file)
            if not file_path.exists():
                raise FileNotFoundError(str(file_path))
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            df = parse_swc_text_preserve_tokens(text)

            if args.feature == "move-node":
                out_df = geometry_move_node_absolute(df, int(args.node_id), float(args.x), float(args.y), float(args.z))
                output_path = _write_geometry_output(file_path, out_df, out_path=args.out, write_output=bool(args.write), suffix="_moved")
                _print_json({"operation": "move-node", "node_id": int(args.node_id), "output_path": output_path})
                return 0

            if args.feature == "move-subtree":
                out_df = geometry_move_subtree_absolute(df, int(args.root_id), float(args.x), float(args.y), float(args.z))
                output_path = _write_geometry_output(file_path, out_df, out_path=args.out, write_output=bool(args.write), suffix="_subtree_moved")
                _print_json({"operation": "move-subtree", "root_id": int(args.root_id), "output_path": output_path})
                return 0

            if args.feature == "connect":
                out_df = geometry_reconnect_branch(df, int(args.start_id), int(args.end_id))
                output_path = _write_geometry_output(file_path, out_df, out_path=args.out, write_output=bool(args.write), suffix="_connected")
                _print_json({
                    "operation": "connect",
                    "start_id": int(args.start_id),
                    "end_id": int(args.end_id),
                    "output_path": output_path,
                })
                return 0

            if args.feature == "disconnect":
                out_df = geometry_disconnect_branch(df, int(args.start_id), int(args.end_id))
                output_path = _write_geometry_output(file_path, out_df, out_path=args.out, write_output=bool(args.write), suffix="_disconnected")
                _print_json({
                    "operation": "disconnect",
                    "start_id": int(args.start_id),
                    "end_id": int(args.end_id),
                    "output_path": output_path,
                })
                return 0

            if args.feature == "delete-node":
                out_df = geometry_delete_node(df, int(args.node_id), reconnect_children=bool(args.reconnect_children))
                output_path = _write_geometry_output(file_path, out_df, out_path=args.out, write_output=bool(args.write), suffix="_node_deleted")
                _print_json({
                    "operation": "delete-node",
                    "node_id": int(args.node_id),
                    "reconnect_children": bool(args.reconnect_children),
                    "output_path": output_path,
                })
                return 0

            if args.feature == "delete-subtree":
                out_df = geometry_delete_subtree(df, int(args.root_id))
                output_path = _write_geometry_output(file_path, out_df, out_path=args.out, write_output=bool(args.write), suffix="_subtree_deleted")
                _print_json({
                    "operation": "delete-subtree",
                    "root_id": int(args.root_id),
                    "output_path": output_path,
                })
                return 0

            if args.feature == "insert":
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
                output_path = _write_geometry_output(file_path, out_df, out_path=args.out, write_output=bool(args.write), suffix="_inserted")
                _print_json({
                    "operation": "insert",
                    "start_id": int(args.start_id),
                    "end_id": int(args.end_id),
                    "output_path": output_path,
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
