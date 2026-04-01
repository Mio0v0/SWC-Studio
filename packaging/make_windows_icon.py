"""Generate a Windows .ico file from packaging/icon.png."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
PNG_PATH = ROOT_DIR / "packaging" / "icon.png"
ICO_PATH = ROOT_DIR / "packaging" / "icon.ico"


def main() -> int:
    if not PNG_PATH.exists():
        raise FileNotFoundError(f"Missing PNG icon: {PNG_PATH}")

    image = Image.open(PNG_PATH).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    image.save(ICO_PATH, format="ICO", sizes=sizes)
    print(f"Wrote Windows icon: {ICO_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
