#!/usr/bin/env python3
"""Download a curated Allen morphology benchmark for auto-label development.

This script downloads all available mouse Allen Cell Types Database
reconstructions that match either of two pyramidal benchmark groups:

- strict_pyramidal: spiny + intact apical
- relaxed_pyramidal: spiny + any apical status

Notes:
- There is no region filter.
- There is no sampling limit.
- strict_pyramidal is a subset of relaxed_pyramidal.
- Allen can return duplicate metadata rows for the same specimen, so rows are
  deduplicated by specimen id before download.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


API_URL = "https://api.brain-map.org/api/v2/data/query.json"
DOWNLOAD_URL = "https://api.brain-map.org/api/v2/well_known_file_download/{wkf_id}"


def fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def download_bytes(url: str) -> bytes:
    with urlopen(url) as response:
        return response.read()


def fetch_all_mouse_reconstructions(page_size: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        criteria = (
            "model::ApiCellTypesSpecimenDetail,"
            "rma::criteria,"
            "[donor__species$eq'Mus musculus'],"
            "[nrwkf__id$gt0],"
            f"rma::options[num_rows$eq{page_size}][start_row$eq{start}]"
        )
        url = f"{API_URL}?{urlencode({'criteria': criteria})}"
        payload = fetch_json(url)
        msg = payload.get("msg", [])
        if not msg:
            break
        rows.extend(msg)
        start += len(msg)
        if start >= int(payload.get("total_rows", 0)):
            break
    return rows


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_specimen: dict[int, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: int(item.get("specimen__id") or 0)):
        specimen_id = int(row.get("specimen__id") or 0)
        if specimen_id <= 0:
            continue
        by_specimen.setdefault(specimen_id, row)
    return list(by_specimen.values())


def spiny_status(row: dict[str, Any]) -> bool:
    return str(row.get("tag__dendrite_type") or "").strip().lower() == "spiny"


def intact_apical_status(row: dict[str, Any]) -> bool:
    return str(row.get("tag__apical") or "").strip().lower() == "intact"


def sanitize_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    safe = re.sub(r"_+", "_", safe).strip("._")
    return safe or "specimen"


def write_readme(out_dir: Path) -> None:
    text = """# Allen Auto-Label Benchmark

This dataset was downloaded from the Allen Cell Types Database using the Allen Brain Atlas API.

Selection rules:
- species: `Mus musculus`
- morphology reconstruction available (`nrwkf__id > 0`)
- no region filter

Benchmark groups:
- `strict_pyramidal`
  - `tag__dendrite_type == "spiny"`
  - `tag__apical == "intact"`
  - purpose: best available pyramidal ground truth
- `relaxed_pyramidal`
  - `tag__dendrite_type == "spiny"`
  - any apical status
  - purpose: larger robustness benchmark including truncated apicals

Important note:
- `strict_pyramidal` is a subset of `relaxed_pyramidal`.
- `metadata.csv` records specimen ids, Allen metadata fields, file paths, and benchmark group.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def download_specimen(row: dict[str, Any], destination: Path) -> None:
    wkf_id = int(row["nrwkf__id"])
    url = DOWNLOAD_URL.format(wkf_id=wkf_id)
    destination.write_bytes(download_bytes(url))


def write_metadata(out_dir: Path, assignments: list[dict[str, Any]]) -> Path:
    metadata_path = out_dir / "metadata.csv"
    with metadata_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "benchmark_group",
                "specimen_id",
                "specimen_name",
                "file_name",
                "relative_path",
                "download_url",
                "nrwkf_id",
                "line_name",
                "region",
                "structure_acronym",
                "layer",
                "dendrite_type",
                "apical_tag",
                "selection_rule",
            ],
        )
        writer.writeheader()
        writer.writerows(assignments)
    return metadata_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the full Allen mouse pyramidal benchmark for auto-label testing.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "allen_autolabel",
        help="Target dataset directory",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove the output directory before writing new contents",
    )
    args = parser.parse_args()

    out_dir = args.output_dir.resolve()
    if out_dir.exists() and args.force:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = dedupe_rows(fetch_all_mouse_reconstructions())
    strict_rows = [row for row in rows if spiny_status(row) and intact_apical_status(row)]
    relaxed_rows = [row for row in rows if spiny_status(row)]

    assignments: list[dict[str, Any]] = []
    for group_name, group_rows, selection_rule in (
        ("strict_pyramidal", strict_rows, 'spiny + intact apical'),
        ("relaxed_pyramidal", relaxed_rows, 'spiny + any apical status'),
    ):
        folder = out_dir / group_name
        folder.mkdir(parents=True, exist_ok=True)
        for row in sorted(group_rows, key=lambda item: int(item["specimen__id"])):
            specimen_id = int(row["specimen__id"])
            specimen_name = str(row["specimen__name"])
            filename = f"{sanitize_filename(specimen_name)}_{specimen_id}.swc"
            destination = folder / filename
            download_specimen(row, destination)
            assignments.append(
                {
                    "benchmark_group": group_name,
                    "specimen_id": specimen_id,
                    "specimen_name": specimen_name,
                    "file_name": filename,
                    "relative_path": str(destination.relative_to(out_dir)),
                    "download_url": DOWNLOAD_URL.format(wkf_id=int(row["nrwkf__id"])),
                    "nrwkf_id": int(row["nrwkf__id"]),
                    "line_name": str(row.get("line_name") or ""),
                    "region": str(row.get("structure_parent__acronym") or ""),
                    "structure_acronym": str(row.get("structure__acronym") or ""),
                    "layer": str(row.get("structure__layer") or ""),
                    "dendrite_type": str(row.get("tag__dendrite_type") or ""),
                    "apical_tag": str(row.get("tag__apical") or ""),
                    "selection_rule": selection_rule,
                }
            )

    assignments.sort(key=lambda row: (row["benchmark_group"], row["specimen_id"]))
    metadata_path = write_metadata(out_dir, assignments)
    write_readme(out_dir)

    print(f"output_dir: {out_dir}")
    print(f"metadata_csv: {metadata_path}")
    print(f"strict_pyramidal: {len(strict_rows)}")
    print(f"relaxed_pyramidal: {len(relaxed_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
