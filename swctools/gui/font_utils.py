"""Shared font helpers for the SWC Studio GUI."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


def pick_app_font() -> QFont:
    """Select a concrete installed UI font to avoid alias fallback."""
    families = set(QFontDatabase.families())
    for name in ("Helvetica Neue", "SF Pro Text", "Arial", "DejaVu Sans"):
        if name in families:
            return QFont(name, 11)
    font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
    if font.pointSize() <= 0:
        font.setPointSize(11)
    return font


def bold_font(base: QFont | None = None, point_size: int | None = None) -> QFont:
    """Return a bold copy of an existing font without forcing a legacy family alias."""
    font = QFont(base) if base is not None else pick_app_font()
    if point_size is not None:
        font.setPointSize(int(point_size))
    elif font.pointSize() <= 0:
        font.setPointSize(11)
    font.setBold(True)
    return font
