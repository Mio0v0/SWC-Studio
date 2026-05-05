"""Helper used by packaging/build_windows.ps1 to zip the dist tree.

Python's zipfile doesn't race AV / Windows Search the way
``Compress-Archive`` does on freshly-written PyInstaller output, so
the build script shells out here instead of using the PowerShell
cmdlet. Kept as a tracked file (instead of an inline here-string in
the .ps1) so the backslash handling is unambiguous.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main(src_path: str, dst_path: str) -> int:
    src = Path(src_path)
    dst = Path(dst_path)
    if not src.is_dir():
        print(f"ERROR: source folder not found: {src}", file=sys.stderr)
        return 2
    dst.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    sep = "\\"
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for entry in src.rglob("*"):
            if entry.is_file():
                rel = str(entry.relative_to(src)).replace(sep, "/")
                arcname = f"{src.name}/{rel}"
                z.write(entry, arcname=arcname)
                n += 1
    size_mb = dst.stat().st_size / 1024 / 1024
    print(f"OK: {dst} | {n} files | {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <src_dir> <dst_zip>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
