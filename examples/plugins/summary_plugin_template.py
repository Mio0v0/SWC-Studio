"""Template plugin: custom analysis summary method for swcstudio.

Copy this file into your own plugin package and update function bodies.
This template follows the swcstudio plugin contract (api_version=1).
"""

from __future__ import annotations

from pathlib import Path


PLUGIN_MANIFEST = {
    "plugin_id": "lab.summary_plugin",
    "name": "Custom Summary Plugin",
    "version": "0.1.0",
    "api_version": "1",
    "description": "Example plugin that extends analysis.summary in swcstudio.",
    "author": "SWC-Studio",
    "capabilities": [
        "analysis",
        "custom_metrics",
    ],
}


def _custom_summary(swc_text: str, config: dict[str, object]) -> dict[str, object]:
    line_count = sum(1 for line in swc_text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    return {
        "nodes": line_count,
        "summary_method": "lab_summary",
        "note": "Template plugin executed. Replace with your real summary logic.",
    }


def register_plugin(registrar) -> None:
    """Entry point required by swcstudio plugin loader."""
    registrar.register_method(
        "analysis.summary",
        "lab_summary",
        _custom_summary,
    )
