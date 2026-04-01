"""Manual per-node radii editing panel for Morphology Editing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from swcstudio.core.radii_cleaning import radii_stats_by_type
from .constants import label_for_type


class ManualRadiiPanel(QWidget):
    """Inspect per-type radius distribution for the selected node and edit its radius."""

    apply_requested = Signal(int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._stats: dict[str, object] = {}
        self._stats_dirty = False
        self._filename: str = ""
        self._selected_node_id: int | None = None
        self._selected_type_id: int | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        desc = QLabel(
            "Select a node in the graph, dendrogram, or 3D view to inspect its type-specific radius distribution "
            "and set a new radius for that node."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #555;")
        root.addWidget(desc)

        self._hist_plot = pg.PlotWidget(background="white")
        self._hist_plot.setMinimumHeight(160)
        self._hist_plot.showGrid(x=True, y=True, alpha=0.15)
        self._hist_plot.getAxis("bottom").setLabel("Radius (clipped 0-5)")
        self._hist_plot.getAxis("left").setLabel("Fraction per bin")
        ax_bottom = self._hist_plot.getAxis("bottom")
        ax_left = self._hist_plot.getAxis("left")
        ax_bottom.setTextPen(pg.mkColor("#222"))
        ax_left.setTextPen(pg.mkColor("#222"))
        ax_bottom.setPen(pg.mkPen("#666"))
        ax_left.setPen(pg.mkPen("#666"))
        tick_font = QFont()
        tick_font.setPointSize(11)
        ax_bottom.setTickFont(tick_font)
        ax_left.setTickFont(tick_font)
        self._hist_plot.enableAutoRange(x=False, y=True)
        self._hist_plot.setXRange(0.0, 5.0, padding=0.0)
        root.addWidget(self._hist_plot, stretch=1)

        self._stats_box = QPlainTextEdit()
        self._stats_box.setReadOnly(True)
        self._stats_box.setMinimumHeight(120)
        self._stats_box.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #fafafa; border: 1px solid #ddd; color: #333;"
            "  font-family: Menlo, Consolas, monospace; font-size: 12px;"
            "}"
        )
        root.addWidget(self._stats_box, stretch=1)

        apply_row = QHBoxLayout()
        apply_row.addWidget(QLabel("New radius:"))
        self._radius_input = QDoubleSpinBox()
        self._radius_input.setDecimals(6)
        self._radius_input.setRange(0.0, 1_000_000.0)
        self._radius_input.setSingleStep(0.01)
        self._radius_input.setEnabled(False)
        apply_row.addWidget(self._radius_input, stretch=1)
        self._apply_btn = QPushButton("Apply Radius")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        apply_row.addWidget(self._apply_btn)
        root.addLayout(apply_row)

        self._status = QLabel("No node selected.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 11px; color: #555;")
        root.addWidget(self._status)

        self.clear_selection()

    def set_loaded_swc(self, df: pd.DataFrame | None, filename: str = ""):
        self._filename = str(filename or "")
        if df is None or df.empty:
            self._df = None
            self._stats = {}
            self._stats_dirty = False
            self.clear_selection()
            return
        self._df = df
        self._stats = {}
        self._stats_dirty = True
        if self.isVisible():
            self._ensure_stats_loaded()
        if self._selected_node_id is not None and int(self._selected_node_id) in set(self._df["id"].astype(int).tolist()):
            self.set_selected_node(int(self._selected_node_id))
        else:
            self.clear_selection()

    def _ensure_stats_loaded(self):
        if self._df is None or self._df.empty:
            self._stats = {}
            self._stats_dirty = False
            return
        if not self._stats_dirty:
            return
        self._stats = dict(radii_stats_by_type(self._df, bins=20))
        self._stats_dirty = False

    def ensure_stats_loaded(self):
        """Load cached radii stats on demand when this panel becomes active."""
        self._ensure_stats_loaded()

    def showEvent(self, event):
        super().showEvent(event)
        if self._df is not None and self._stats_dirty:
            self._ensure_stats_loaded()

    def clear_selection(self):
        self._selected_node_id = None
        self._selected_type_id = None
        self._radius_input.blockSignals(True)
        self._radius_input.setValue(0.0)
        self._radius_input.blockSignals(False)
        self._radius_input.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._hist_plot.clear()
        self._hist_plot.setTitle("Select a node to view type-specific radii distribution")
        self._stats_box.setPlainText("No node selected.")
        self._status.setText("Select a node in the viewer or dendrogram to edit its radius.")

    def set_selected_node(self, swc_id: int):
        if self._df is None or self._df.empty:
            self.clear_selection()
            return
        self._ensure_stats_loaded()
        row = self._df.loc[self._df["id"].astype(int) == int(swc_id)]
        if row.empty:
            self.clear_selection()
            return

        node = row.iloc[0]
        type_id = int(node["type"])
        radius = float(node["radius"])
        type_rows = self._df.loc[self._df["type"].astype(int) == type_id]
        type_stats = dict(dict(self._stats.get("type_stats", {})).get(str(type_id), {}) or {})

        self._selected_node_id = int(swc_id)
        self._selected_type_id = int(type_id)
        self._radius_input.blockSignals(True)
        self._radius_input.setValue(radius)
        self._radius_input.blockSignals(False)
        self._radius_input.setEnabled(True)
        self._apply_btn.setEnabled(True)
        self._status.setText(f"Editing node {int(swc_id)} in {self._filename or 'current SWC'}.")
        self._draw_histogram(type_id, radius)
        self._stats_box.setPlainText(self._format_stats_text(type_id, radius, type_stats))

    def _draw_histogram(self, type_id: int, node_radius: float):
        self._hist_plot.clear()
        if self._df is None or self._df.empty:
            self._hist_plot.setTitle("No radii data loaded")
            return

        vals = np.asarray(
            self._df.loc[self._df["type"].astype(int) == int(type_id), "radius"],
            dtype=float,
        )
        vals = vals[np.isfinite(vals) & (vals > 0.0)]
        if vals.size == 0:
            self._hist_plot.setTitle(f"Type {type_id}: no valid positive radii")
            return

        x_lo = 0.0
        x_hi = 5.0
        bin_count = 40
        counts_np, edges_np = np.histogram(vals, bins=bin_count, range=(x_lo, x_hi))
        counts = counts_np.astype(float)
        total = float(vals.size)
        heights = counts / total if total > 0 else counts
        centers = []
        widths = []
        edges = edges_np.astype(float)
        for i, h in enumerate(heights.tolist()):
            lo = float(edges[i])
            hi = float(edges[i + 1])
            centers.append((lo + hi) * 0.5)
            widths.append(max(1e-12, (hi - lo) * 0.92))

        bars = pg.BarGraphItem(
            x=centers,
            height=heights,
            width=widths,
            brush=pg.mkBrush(80, 120, 200, 180),
            pen=pg.mkPen(30, 60, 120, 220),
        )
        self._hist_plot.addItem(bars)
        mean = float(np.mean(vals))
        median = float(np.percentile(vals, 50))
        q1 = float(np.percentile(vals, 25))
        q3 = float(np.percentile(vals, 75))
        for pos, pen in (
            (mean, pg.mkPen("#2e8b57", width=2)),
            (median, pg.mkPen("#8b0000", width=2)),
            (q1, pg.mkPen("#555", style=Qt.DashLine)),
            (q3, pg.mkPen("#555", style=Qt.DashLine)),
        ):
            line = pg.InfiniteLine(pos=float(pos), angle=90, pen=pen)
            line.setZValue(10)
            self._hist_plot.addItem(line)
        selected_line = pg.InfiniteLine(pos=float(node_radius), angle=90, pen=pg.mkPen("#18e0cf", width=3))
        selected_line.setZValue(11)
        self._hist_plot.addItem(selected_line)
        self._hist_plot.setXRange(0.0, 5.0, padding=0.0)
        ymax = float(np.max(heights)) if heights.size else 1.0
        self._hist_plot.setYRange(0.0, max(0.05, ymax * 1.15), padding=0.0)
        clipped_hi = int(np.sum(vals > x_hi))
        self._hist_plot.setTitle(
            f"{self._filename or 'current SWC'} | Type {type_id} ({label_for_type(type_id)}) "
            f"| mean={mean:.4g} median={median:.4g} q1={q1:.4g} q3={q3:.4g} "
            f"| N={int(total)} clipped>5={clipped_hi}"
        )

    def _format_stats_text(self, type_id: int, node_radius: float, stats: dict[str, object]) -> str:
        if not stats or int(stats.get("count_valid_positive", 0) or 0) <= 0:
            return (
                f"Selected node type: {label_for_type(type_id)} ({type_id})\n"
                f"Current radius: {node_radius:.6g}\n\n"
                "No valid positive radii are available for this type."
            )
        return (
            f"Selected node type: {label_for_type(type_id)} ({type_id})\n"
            f"Current radius: {node_radius:.6g}\n"
            f"Type count total: {int(stats.get('count_total', 0) or 0)}\n"
            f"Valid positive radii: {int(stats.get('count_valid_positive', 0) or 0)}\n\n"
            f"Mean:   {float(stats.get('mean', 0.0) or 0.0):.6g}\n"
            f"Median: {float(stats.get('median', 0.0) or 0.0):.6g}\n"
            f"Q1:     {float(stats.get('q1', 0.0) or 0.0):.6g}\n"
            f"Q3:     {float(stats.get('q3', 0.0) or 0.0):.6g}\n"
            f"Min:    {float(stats.get('min', 0.0) or 0.0):.6g}\n"
            f"Max:    {float(stats.get('max', 0.0) or 0.0):.6g}"
        )

    def _on_apply_clicked(self):
        if self._selected_node_id is None:
            return
        self.apply_requested.emit(int(self._selected_node_id), float(self._radius_input.value()))
