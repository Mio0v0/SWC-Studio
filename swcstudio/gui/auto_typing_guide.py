"""Floating guide widget describing the auto-typing engine."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

_TITLE = "Auto-Typing Engine — v9 ML pipeline"

_BODY = (
    "swcstudio's auto-labeling uses a four-stage ML pipeline:\n"
    "\n"
    "Stage 1 — Cell-type detector\n"
    "  An sklearn ensemble over 49 whole-cell features decides whether\n"
    "  the morphology is pyramidal or interneuron. A soft handoff runs\n"
    "  Stage 2+3 for both cell types when Stage 1 is uncertain and\n"
    "  picks the higher-confidence outcome.\n"
    "\n"
    "Stage 2 — Per-subtree classifier\n"
    "  Branches are grouped into primary subtrees rooted at soma\n"
    "  children. An sklearn ensemble assigns each subtree to axon,\n"
    "  basal, or apical, then propagates the label to every node in\n"
    "  the subtree (no mid-track type switches).\n"
    "\n"
    "Stage 2b — GraphSAGE GNN (optional)\n"
    "  For pyramidal dendrites, a small GraphSAGE model over the branch\n"
    "  graph re-decides apical vs basal. Skipped automatically if torch\n"
    "  / torch_geometric / the GNN checkpoint are not available.\n"
    "\n"
    "Stage 3 — Topology refinement\n"
    "  Short islands are flipped, parent/child neighbourhoods smoothed.\n"
    "  Hard constraints are enforced at the soma boundary: at most one\n"
    "  primary axon and one primary apical winner.\n"
    "\n"
    "Models\n"
    "  Resolved via SWCSTUDIO_MODEL_DIR, the GUI model-dir picker, or\n"
    "  the user / bundled defaults. Required files:\n"
    "    cell_type_classifier.pkl   (Stage 1)\n"
    "    branch_classifier.pkl      (Stage 2)\n"
    "    gnn_apical_basal.pt        (Stage 2b — optional)\n"
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
