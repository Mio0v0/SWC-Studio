"""Floating guide widget describing the auto-typing engine."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

_TITLE = "Auto-Label Engine"

_BODY = (
    "Three-stage machine-learning pipeline that labels every node in\n"
    "an SWC as soma, axon, basal dendrite, or apical dendrite.\n"
    "\n"
    "Stage 1 — Cell type\n"
    "  Decides whether the cell is pyramidal or interneuron from its\n"
    "  whole-cell shape (size, branching pattern, orientation). When\n"
    "  uncertain, runs Stages 2+3 for both possibilities and picks the\n"
    "  more confident result.\n"
    "\n"
    "Stage 2 — Branch classifier\n"
    "  Each dendritic branch is classified as axon, basal, or apical.\n"
    "  Predictions are made per primary branch off the soma so all\n"
    "  nodes within the same branch get the same label.\n"
    "\n"
    "Stage 3 — Topology refinement\n"
    "  Cleans up small islands of disagreeing labels and enforces\n"
    "  biological constraints: at most one primary axon, one primary\n"
    "  apical, and consistent labels along each track from soma to\n"
    "  leaf.\n"
    "\n"
    "Model files\n"
    "  Bundled with the package by default. Use the Model dir picker\n"
    "  to point at custom-trained models; leave it blank to use the\n"
    "  bundled ones.\n"
)


class AutoTypingGuideWidget(QWidget):
    """Static guide panel shown as a floating dock for Auto Label Editing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._title = QLabel(_TITLE)
        self._title.setStyleSheet("font-size: 14px; font-weight: 700; color: #222;")
        layout.addWidget(self._title)

        self._body = QLabel(_BODY)
        self._body.setWordWrap(True)
        self._body.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._body.setStyleSheet(
            "QLabel {"
            "  font-size: 12px;"
            "  color: #444;"
            "  background: #f6f6f6;"
            "  border: 1px solid #ddd;"
            "  padding: 8px;"
            "}"
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self._body)
        layout.addWidget(scroll, stretch=1)

    def refresh(self):
        """No-op: the guide is static now that there are no tunable rule weights."""
        return None
