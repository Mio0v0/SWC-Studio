"""Geometry editing controls for persistent selections and numeric graph edits."""

from __future__ import annotations

from typing import Any

import pandas as pd

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QAbstractItemView,
    QDialog,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QApplication,
    QSizePolicy,
)

from swctools.core.geometry_editing import (
    GeometrySelection,
    make_selection,
)
from swctools.gui.constants import SWC_COLS, label_for_type


class _CurrentPageStackedWidget(QStackedWidget):
    """A stacked widget that sizes itself to the current page only."""

    def sizeHint(self):
        widget = self.currentWidget()
        if widget is not None:
            return widget.sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self):
        widget = self.currentWidget()
        if widget is not None:
            return widget.minimumSizeHint()
        return super().minimumSizeHint()


class GeometryEditingPanel(QWidget):
    """Persistent geometry selection manager and operation panel."""

    selection_preview_changed = Signal(object, str, bool)
    focus_requested = Signal(int)
    move_node_requested = Signal(int, float, float, float)
    move_selection_requested = Signal(object, int, float, float, float)
    reconnect_requested = Signal(int, int)
    disconnect_requested = Signal(int, int)
    delete_node_requested = Signal(int, bool)
    delete_subtree_requested = Signal(int)
    insert_node_requested = Signal(int, int, float, float, float)
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._current_node_id: int | None = None
        self._items: list[dict[str, Any]] = []
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        desc = QLabel(
            "Build one or more geometry selections from clicked nodes or typed node IDs, then apply numeric "
            "move/reconnect/delete/insert operations to the active selection."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #555;")
        root.addWidget(desc)

        select_group = QGroupBox("Selection")
        select_group.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        select_layout = QVBoxLayout(select_group)
        select_layout.setContentsMargins(10, 10, 10, 10)
        select_layout.setSpacing(8)

        row_visibility = QHBoxLayout()
        row_visibility.addWidget(QLabel("Visibility:"))
        self._visibility_combo = QComboBox()
        self._style_combo(self._visibility_combo)
        self._visibility_combo.addItem("Dim Others", "dim")
        self._visibility_combo.addItem("Hide Others", "hide")
        self._visibility_combo.addItem("Show Whole Neuron", "show")
        self._visibility_combo.currentIndexChanged.connect(self._emit_selection_preview)
        row_visibility.addWidget(self._visibility_combo)
        self._auto_zoom_cb = QCheckBox("Auto Zoom to Selection")
        self._auto_zoom_cb.setChecked(True)
        self._auto_zoom_cb.stateChanged.connect(self._emit_selection_preview)
        row_visibility.addWidget(self._auto_zoom_cb)
        row_visibility.addStretch()
        select_layout.addLayout(row_visibility)

        row_add = QHBoxLayout()
        row_add.addWidget(QLabel("Node ID:"))
        self._node_input = QLineEdit()
        self._node_input.setPlaceholderText("Enter node ID or select from graph")
        row_add.addWidget(self._node_input)
        select_layout.addLayout(row_add)

        row_expand = QHBoxLayout()
        row_expand.addWidget(QLabel("Select:"))
        self._expand_combo = QComboBox()
        self._style_combo(self._expand_combo)
        self._expand_combo.addItem("Select node", "node")
        self._expand_combo.addItem("Select subtree", "subtree")
        self._expand_combo.addItem("Select upstream nodes", "upstream_nodes")
        self._expand_combo.addItem("Select downstream nodes", "downstream_nodes")
        self._expand_combo.addItem("Select entire branch", "branch")
        self._expand_combo.addItem("Select up bifurcation", "up_bifurcation")
        self._expand_combo.addItem("Select down bifurcation", "down_bifurcation")
        self._expand_combo.currentIndexChanged.connect(self._refresh_selection_mode_controls)
        row_expand.addWidget(self._expand_combo)
        self._expand_count_label = QLabel("Count:")
        row_expand.addWidget(self._expand_count_label)
        self._expand_count = QSpinBox()
        self._expand_count.setRange(1, 9999)
        self._expand_count.setValue(3)
        row_expand.addWidget(self._expand_count)
        self._btn_add_expand = QPushButton("Add Selection")
        self._btn_add_expand.clicked.connect(self._on_add_expanded_clicked)
        row_expand.addWidget(self._btn_add_expand)
        row_expand.addStretch()
        select_layout.addLayout(row_expand)

        self._selection_tree = QTreeWidget()
        self._selection_tree.setHeaderLabels(["Selected Items", "Count"])
        self._selection_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._selection_tree.itemSelectionChanged.connect(self._on_selection_tree_changed)
        self._selection_tree.currentItemChanged.connect(self._on_selection_tree_current_item_changed)
        self._selection_tree.itemClicked.connect(self._on_selection_tree_item_clicked)
        self._selection_tree.itemDoubleClicked.connect(self._on_selection_tree_double_clicked)
        self._selection_tree.setMinimumHeight(72)
        self._selection_tree.setMaximumHeight(96)
        select_layout.addWidget(self._selection_tree)

        row_sel_btns = QHBoxLayout()
        self._btn_remove_selected = QPushButton("Remove Selected")
        self._btn_remove_selected.clicked.connect(self._on_remove_selected)
        row_sel_btns.addWidget(self._btn_remove_selected)
        self._btn_clear_all = QPushButton("Clear All")
        self._btn_clear_all.clicked.connect(self._on_clear_all)
        row_sel_btns.addWidget(self._btn_clear_all)
        row_sel_btns.addStretch()
        select_layout.addLayout(row_sel_btns)

        root.addWidget(select_group)

        op_picker = QGroupBox("Edit Operation")
        op_picker.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        op_picker_layout = QVBoxLayout(op_picker)
        op_picker_layout.setContentsMargins(10, 10, 10, 10)
        op_picker_layout.setSpacing(8)
        op_picker_layout.setAlignment(Qt.AlignTop)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("Operation:"))
        self._operation_combo = QComboBox()
        self._style_combo(self._operation_combo)
        self._operation_combo.addItem("Connect", "connect")
        self._operation_combo.addItem("Disconnect", "disconnect")
        self._operation_combo.addItem("Insert", "insert")
        self._operation_combo.addItem("Delete", "delete")
        self._operation_combo.addItem("Move", "move")
        self._operation_combo.currentIndexChanged.connect(self._on_operation_combo_changed)
        op_row.addWidget(self._operation_combo)
        op_row.addStretch()
        op_picker_layout.addLayout(op_row)

        self._operation_stack = _CurrentPageStackedWidget()
        self._operation_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)

        connect_page = QWidget()
        connect_page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        connect_layout = QVBoxLayout(connect_page)
        connect_layout.setContentsMargins(0, 0, 0, 0)
        connect_layout.setSpacing(8)
        self._connect_summary = QLabel("Pick or add one or more selection items to define default source and target nodes.")
        self._connect_summary.setWordWrap(True)
        connect_layout.addWidget(self._connect_summary)
        connect_form = QFormLayout()
        connect_form.setContentsMargins(0, 0, 0, 0)
        connect_form.setSpacing(8)
        self._connect_source_input = QLineEdit()
        self._connect_source_input.setPlaceholderText("Source node ID")
        connect_form.addRow("Start Node:", self._connect_source_input)
        self._connect_target_input = QLineEdit()
        self._connect_target_input.setPlaceholderText("Target node ID")
        connect_form.addRow("End Node:", self._connect_target_input)
        connect_layout.addLayout(connect_form)
        self._btn_reconnect = QPushButton("Apply Connection")
        self._btn_reconnect.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_reconnect.clicked.connect(self._on_reconnect_clicked)
        connect_layout.addWidget(self._btn_reconnect)
        self._operation_stack.addWidget(connect_page)

        disconnect_page = QWidget()
        disconnect_page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        disconnect_layout = QVBoxLayout(disconnect_page)
        disconnect_layout.setContentsMargins(0, 0, 0, 0)
        disconnect_layout.setSpacing(8)
        self._disconnect_summary = QLabel("Choose a start node to disconnect from its current parent.")
        self._disconnect_summary.setWordWrap(True)
        disconnect_layout.addWidget(self._disconnect_summary)
        disconnect_form = QFormLayout()
        disconnect_form.setContentsMargins(0, 0, 0, 0)
        disconnect_form.setSpacing(8)
        self._disconnect_source_input = QLineEdit()
        self._disconnect_source_input.setPlaceholderText("Start node ID")
        disconnect_form.addRow("Start Node:", self._disconnect_source_input)
        self._disconnect_target_input = QLineEdit()
        self._disconnect_target_input.setPlaceholderText("End node ID")
        disconnect_form.addRow("End Node:", self._disconnect_target_input)
        disconnect_layout.addLayout(disconnect_form)
        self._btn_disconnect_only = QPushButton("Apply Disconnect")
        self._btn_disconnect_only.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_disconnect_only.clicked.connect(self._on_disconnect_clicked)
        disconnect_layout.addWidget(self._btn_disconnect_only)
        self._operation_stack.addWidget(disconnect_page)

        insert_page = QWidget()
        insert_layout = QVBoxLayout(insert_page)
        insert_layout.setContentsMargins(0, 0, 0, 0)
        insert_layout.setSpacing(8)
        self._insert_summary = QLabel("Choose start and end nodes for insertion or use the selected item defaults.")
        self._insert_summary.setWordWrap(True)
        insert_layout.addWidget(self._insert_summary)
        insert_form = QFormLayout()
        self._insert_start_input = QLineEdit()
        self._insert_start_input.setPlaceholderText("Start node ID")
        insert_form.addRow("Start Node:", self._insert_start_input)
        self._insert_end_input = QLineEdit()
        self._insert_end_input.setPlaceholderText("End node ID")
        insert_form.addRow("End Node:", self._insert_end_input)
        self._insert_x = self._make_coord_input()
        self._insert_y = self._make_coord_input()
        self._insert_z = self._make_coord_input()
        insert_form.addRow("New X:", self._insert_x)
        insert_form.addRow("New Y:", self._insert_y)
        insert_form.addRow("New Z:", self._insert_z)
        insert_layout.addLayout(insert_form)
        insert_btn_row = QHBoxLayout()
        self._btn_insert = QPushButton("Apply Insert")
        self._btn_insert.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_insert.clicked.connect(self._on_insert_clicked)
        insert_btn_row.addWidget(self._btn_insert)
        insert_layout.addLayout(insert_btn_row)
        self._operation_stack.addWidget(insert_page)

        delete_page = QWidget()
        delete_layout = QVBoxLayout(delete_page)
        delete_layout.setContentsMargins(0, 0, 0, 0)
        delete_layout.setSpacing(8)
        self._delete_summary = QLabel("Choose a node or subtree root to delete.")
        self._delete_summary.setWordWrap(True)
        delete_layout.addWidget(self._delete_summary)
        delete_form = QFormLayout()
        self._delete_node_input = QLineEdit()
        self._delete_node_input.setPlaceholderText("Node ID or subtree root")
        delete_form.addRow("Target Node:", self._delete_node_input)
        delete_layout.addLayout(delete_form)
        delete_btn_row = QHBoxLayout()
        self._btn_delete_node = QPushButton("Delete Node")
        self._btn_delete_node.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_delete_node.clicked.connect(lambda: self._on_delete_node_clicked(reconnect_children=False))
        delete_btn_row.addWidget(self._btn_delete_node)
        self._btn_delete_reconnect = QPushButton("Delete + Reconnect Children")
        self._btn_delete_reconnect.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_delete_reconnect.clicked.connect(lambda: self._on_delete_node_clicked(reconnect_children=True))
        delete_btn_row.addWidget(self._btn_delete_reconnect)
        self._btn_delete_subtree = QPushButton("Delete Subtree")
        self._btn_delete_subtree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_delete_subtree.clicked.connect(self._on_delete_subtree_clicked)
        delete_btn_row.addWidget(self._btn_delete_subtree)
        delete_layout.addLayout(delete_btn_row)
        self._operation_stack.addWidget(delete_page)

        move_page = QWidget()
        move_page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        move_layout = QVBoxLayout(move_page)
        move_layout.setContentsMargins(0, 0, 0, 0)
        move_layout.setSpacing(8)
        self._move_summary = QLabel("Move the currently selected nodes by entering a new XYZ position for the target anchor node.")
        self._move_summary.setWordWrap(True)
        move_layout.addWidget(self._move_summary)
        move_form = QFormLayout()
        move_form.setContentsMargins(0, 0, 0, 0)
        move_form.setSpacing(8)
        self._move_anchor_input = QLineEdit()
        self._move_anchor_input.setPlaceholderText("Anchor node ID")
        move_form.addRow("Target Node:", self._move_anchor_input)
        self._move_node_x = self._make_coord_input()
        self._move_node_y = self._make_coord_input()
        self._move_node_z = self._make_coord_input()
        move_form.addRow("New X:", self._move_node_x)
        move_form.addRow("New Y:", self._move_node_y)
        move_form.addRow("New Z:", self._move_node_z)
        move_layout.addLayout(move_form)
        self._btn_move_node = QPushButton("Apply Move")
        self._btn_move_node.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_move_node.clicked.connect(self._on_move_node_clicked)
        move_layout.addWidget(self._btn_move_node)
        self._operation_stack.addWidget(move_page)

        op_picker_layout.addWidget(self._operation_stack, 0, Qt.AlignTop)
        root.addWidget(op_picker, 0, Qt.AlignTop)

        root.addStretch()
        self._refresh_selection_mode_controls()
        self._set_operation_mode("connect")
        self._refresh_ui_from_selection()

    def _make_coord_input(self) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(6)
        box.setRange(-1_000_000.0, 1_000_000.0)
        box.setSingleStep(0.1)
        return box

    def _style_combo(self, combo: QComboBox):
        combo.setStyleSheet(
            "QComboBox QAbstractItemView {"
            "  background: #ffffff;"
            "  color: #132238;"
            "  selection-background-color: #d9e8fb;"
            "  selection-color: #132238;"
            "}"
            "QComboBox QAbstractItemView::item:hover {"
            "  background: #d9e8fb;"
            "  color: #132238;"
            "}"
            "QComboBox QAbstractItemView::item:selected {"
            "  background: #d9e8fb;"
            "  color: #132238;"
            "}"
        )

    def _selection_requires_count(self) -> bool:
        return str(self._expand_combo.currentData() or "").strip() in {"upstream_nodes", "downstream_nodes"}

    def _refresh_selection_mode_controls(self):
        needs_count = self._selection_requires_count()
        self._expand_count_label.setVisible(needs_count)
        self._expand_count.setVisible(needs_count)

    def _set_operation_mode(self, mode: str):
        mode_key = str(mode or "connect").strip().lower()
        mapping = {"connect": 0, "disconnect": 1, "insert": 2, "delete": 3, "move": 4}
        self._operation_stack.setCurrentIndex(mapping.get(mode_key, 0))
        self._operation_stack.updateGeometry()
        idx = self._operation_combo.findData(mode_key)
        if idx >= 0 and idx != self._operation_combo.currentIndex():
            self._operation_combo.blockSignals(True)
            self._operation_combo.setCurrentIndex(idx)
            self._operation_combo.blockSignals(False)

    def _on_operation_combo_changed(self):
        self._set_operation_mode(str(self._operation_combo.currentData() or "connect"))

    def set_loaded_swc(self, df: pd.DataFrame | None):
        self._df = df.loc[:, SWC_COLS] if isinstance(df, pd.DataFrame) and not df.empty else None
        valid_ids = set(self._df["id"].astype(int).tolist()) if self._df is not None else set()
        if valid_ids:
            kept = []
            for item in self._items:
                node_ids = [int(v) for v in item.get("node_ids", []) if int(v) in valid_ids]
                if not node_ids:
                    continue
                item["node_ids"] = node_ids
                kept.append(item)
            self._items = kept
        else:
            self._items = []
        self._rebuild_selection_tree()
        self._refresh_ui_from_selection()
        self._emit_selection_preview()

    def set_current_node(self, swc_id: int | None):
        self._current_node_id = int(swc_id) if swc_id is not None else None
        if self._current_node_id is not None and self._node_exists(self._current_node_id):
            self._node_input.setText(str(int(self._current_node_id)))
        elif not str(self._node_input.text() or "").strip():
            self._node_input.clear()
        self._refresh_ui_from_selection()

    def add_current_node_selection(self, swc_id: int):
        self.set_current_node(int(swc_id))
        self._add_selection_from_spec("node", int(swc_id), hops=None, auto_select=True)

    def clear_all_selections(self):
        self._items = []
        self._rebuild_selection_tree()
        self._refresh_ui_from_selection()
        self._emit_selection_preview()

    def snapshot_selection_state(self) -> dict[str, Any]:
        selected_ids = [str(item.get("item_id", "")) for item in self._selected_tree_items()]
        items: list[dict[str, Any]] = []
        for item in self._items:
            copied = dict(item)
            copied["node_ids"] = [int(v) for v in item.get("node_ids", [])]
            copied["meta"] = dict(item.get("meta") or {})
            items.append(copied)
        return {
            "items": items,
            "selected_item_ids": selected_ids,
            "current_node_id": int(self._current_node_id) if self._current_node_id is not None else None,
        }

    def restore_selection_state(self, state: dict[str, Any] | None, id_map: dict[int, int] | None):
        if self._df is None or self._df.empty:
            return
        snapshot = dict(state or {})
        mapping = {int(k): int(v) for k, v in dict(id_map or {}).items()}
        restored: list[dict[str, Any]] = []
        selected_item_ids: set[str] = {str(v) for v in snapshot.get("selected_item_ids", [])}
        selected_restored_id = ""
        for item in snapshot.get("items", []):
            item = dict(item)
            old_node_ids = [int(v) for v in item.get("node_ids", [])]
            mapped_node_ids = [int(mapping[v]) for v in old_node_ids if int(v) in mapping]
            if not mapped_node_ids:
                continue
            old_anchor = int(item.get("anchor_id", -1))
            anchor_id = int(mapping.get(old_anchor, mapped_node_ids[0]))
            kind = str(item.get("kind", "node") or "node").strip()
            hops = int((item.get("meta") or {}).get("hops", 0))
            try:
                selection = make_selection(self._df, kind=kind, anchor_id=anchor_id, hops=hops)
                restored_item = selection.to_dict()
            except Exception:
                restored_item = dict(item)
                restored_item["anchor_id"] = anchor_id
                restored_item["node_ids"] = mapped_node_ids
                restored_item["item_id"] = f"{kind}:{anchor_id}:{hops}:{len(mapped_node_ids)}"
            restored.append(restored_item)
            if str(item.get("item_id", "")) in selected_item_ids and not selected_restored_id:
                selected_restored_id = str(restored_item.get("item_id", ""))
        self._items = restored
        self._rebuild_selection_tree(select_item_id=selected_restored_id or None)
        current_old = snapshot.get("current_node_id")
        if current_old is not None and int(current_old) in mapping:
            self._current_node_id = int(mapping[int(current_old)])
            self._node_input.setText(str(int(self._current_node_id)))
        self._refresh_ui_from_selection()
        self._emit_selection_preview()

    def _node_exists(self, node_id: int) -> bool:
        return self._df is not None and bool((self._df["id"].astype(int) == int(node_id)).any())

    def _parse_node_input(self) -> int | None:
        text = str(self._node_input.text() or "").strip()
        if not text:
            return None
        try:
            node_id = int(text)
        except ValueError:
            return None
        return node_id if self._node_exists(node_id) else None

    def _resolve_anchor_node_id(self) -> int | None:
        active = self._active_selection_item()
        if active is not None:
            return int(active.get("anchor_id", -1))
        return int(self._current_node_id) if self._current_node_id is not None and self._node_exists(self._current_node_id) else None

    def _on_add_expanded_clicked(self):
        kind = str(self._expand_combo.currentData() or "").strip()
        node_id = self._parse_node_input()
        anchor_id = int(node_id) if node_id is not None else self._resolve_anchor_node_id()
        if anchor_id is None:
            self.log_message.emit("Geometry Editing: select or enter a node first.")
            return
        hops = int(self._expand_count.value()) if self._selection_requires_count() else None
        self._add_selection_from_spec(kind, int(anchor_id), hops=hops, auto_select=True)

    def _add_selection_from_spec(self, kind: str, anchor_id: int, *, hops: int | None, auto_select: bool):
        if self._df is None or self._df.empty:
            return
        try:
            selection = make_selection(self._df, kind=str(kind), anchor_id=int(anchor_id), hops=hops)
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit(f"Geometry Editing: {exc}")
            return
        selection_dict = selection.to_dict()
        if not any(str(item.get("item_id", "")) == str(selection_dict.get("item_id", "")) for item in self._items):
            self._items.append(selection_dict)
        self._rebuild_selection_tree(select_item_id=str(selection_dict.get("item_id", "")) if auto_select else None)
        self._refresh_ui_from_selection()
        self._emit_selection_preview()

    def _rebuild_selection_tree(self, select_item_id: str | None = None):
        wanted = str(select_item_id or "").strip()
        self._selection_tree.clear()
        for item in self._items:
            node_ids = [int(v) for v in item.get("node_ids", [])]
            tw = QTreeWidgetItem([str(item.get("label", "")), str(len(node_ids))])
            tw.setData(0, Qt.UserRole, dict(item))
            tw.setToolTip(0, str(item.get("detail", "")))
            self._selection_tree.addTopLevelItem(tw)
            if wanted and str(item.get("item_id", "")).strip() == wanted:
                tw.setSelected(True)
                self._selection_tree.setCurrentItem(tw)

    def _selection_tree_detail_text(self, item: dict[str, Any]) -> str:
        anchor_id = int(item.get("anchor_id", -1))
        row = self._row_for_node(anchor_id)
        if row is None:
            return ""
        type_id = int(row["type"])
        parent_id = int(row["parent"])
        child_ids: list[int] = []
        if self._df is not None and not self._df.empty:
            child_ids = (
                self._df.loc[self._df["parent"].astype(int) == anchor_id, "id"]
                .astype(int)
                .tolist()
            )
        child_text = ", ".join(str(v) for v in child_ids) if child_ids else "None"
        return (
            f"Type: {label_for_type(type_id)} ({type_id})\n"
            f"Radius: {float(row['radius']):.6g}\n"
            f"X: {float(row['x']):.6g}\n"
            f"Y: {float(row['y']):.6g}\n"
            f"Z: {float(row['z']):.6g}\n"
            f"Parent ID: {parent_id}\n"
            f"Children IDs: {child_text}"
        )

    def _start_node_for_selected_item(self, item: dict[str, Any]) -> int | None:
        if self._df is None or self._df.empty:
            return None
        node_ids = sorted({int(v) for v in item.get("node_ids", [])})
        if not node_ids:
            return None
        kind = str(item.get("kind", "") or "").strip()
        if kind == "node":
            return int(node_ids[0])
        node_id_set = set(node_ids)
        candidates: list[int] = []
        for node_id in node_ids:
            row = self._row_for_node(int(node_id))
            if row is None:
                continue
            parent_id = int(row["parent"])
            if parent_id not in node_id_set:
                candidates.append(int(node_id))
        if candidates:
            return int(min(candidates))
        return int(min(node_ids))

    def _selected_tree_items(self) -> list[dict[str, Any]]:
        out = []
        for item in self._selection_tree.selectedItems():
            payload = item.data(0, Qt.UserRole)
            if isinstance(payload, dict):
                out.append(dict(payload))
        return out

    def _current_tree_item_payload(self) -> dict[str, Any] | None:
        item = self._selection_tree.currentItem()
        if item is None:
            return None
        payload = item.data(0, Qt.UserRole)
        return dict(payload) if isinstance(payload, dict) else None

    def _selected_items_in_order(self) -> list[dict[str, Any]]:
        selected_ids = {str(item.get("item_id", "")) for item in self._selected_tree_items()}
        if not selected_ids:
            current_payload = self._current_tree_item_payload()
            if current_payload is not None:
                return [current_payload]
            return []
        ordered = [dict(item) for item in self._items if str(item.get("item_id", "")) in selected_ids]
        current_payload = self._current_tree_item_payload()
        current_id = str(current_payload.get("item_id", "")) if current_payload else ""
        if current_id:
            ordered.sort(key=lambda item: (str(item.get("item_id", "")) != current_id, self._items.index(item)))
        return ordered

    def _active_selection_item(self) -> dict[str, Any] | None:
        current_payload = self._current_tree_item_payload()
        if current_payload is not None:
            return current_payload
        selected = self._selected_tree_items()
        if selected:
            return dict(selected[0])
        return None

    def _union_selected_node_ids(self) -> list[int]:
        selected = self._selected_tree_items()
        if selected:
            source_items = selected
        else:
            current_payload = self._current_tree_item_payload()
            source_items = [current_payload] if current_payload is not None else []
        seen: set[int] = set()
        ordered: list[int] = []
        for item in source_items:
            for node_id in item.get("node_ids", []):
                node_id = int(node_id)
                if node_id in seen:
                    continue
                seen.add(node_id)
                ordered.append(node_id)
        return ordered

    def _on_selection_tree_changed(self):
        self._refresh_ui_from_selection()
        self._emit_selection_preview()

    def _on_selection_tree_current_item_changed(self, _current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None):
        self._refresh_ui_from_selection()

    def _on_selection_tree_item_clicked(self, item: QTreeWidgetItem, _column: int):
        modifiers = QApplication.keyboardModifiers()
        if not (modifiers & (Qt.ControlModifier | Qt.MetaModifier | Qt.ShiftModifier)):
            self._selection_tree.blockSignals(True)
            self._selection_tree.clearSelection()
            item.setSelected(True)
            self._selection_tree.setCurrentItem(item)
            self._selection_tree.blockSignals(False)
        self._refresh_ui_from_selection()
        self._emit_selection_preview()

    def _on_selection_tree_double_clicked(self, item: QTreeWidgetItem, _column: int):
        payload = item.data(0, Qt.UserRole)
        if isinstance(payload, dict):
            self.focus_requested.emit(int(payload.get("anchor_id", -1)))
            self._show_selection_info_dialog(dict(payload))

    def _show_selection_info_dialog(self, item: dict[str, Any]):
        if self._df is None or self._df.empty:
            return
        node_ids = sorted({int(v) for v in item.get("node_ids", [])})
        if not node_ids:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(str(item.get("label", "Selection Info")) or "Selection Info")
        dialog.resize(900, 420)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel(str(item.get("label", "Selection Info")) or "Selection Info")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #132238;")
        layout.addWidget(title)

        table = QTableWidget(len(node_ids), 8, dialog)
        table.setHorizontalHeaderLabels(
            ["Selected Node", "Type", "Radius", "Parent ID", "Children ID", "X", "Y", "Z"]
        )
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(False)
        table.setWordWrap(False)
        table.setStyleSheet(
            "QTableWidget { background: #fafafa; border: 1px solid #ddd; color: #333; font-size: 12px; }"
        )

        for row_idx, node_id in enumerate(node_ids):
            row = self._row_for_node(int(node_id))
            if row is None:
                values = [str(int(node_id)), "Missing", "", "", "", "", "", ""]
            else:
                type_id = int(row["type"])
                child_ids = (
                    self._df.loc[self._df["parent"].astype(int) == int(node_id), "id"].astype(int).tolist()
                    if self._df is not None and not self._df.empty
                    else []
                )
                values = [
                    str(int(node_id)),
                    f"{label_for_type(type_id)} ({type_id})",
                    f"{float(row['radius']):.6g}",
                    str(int(row["parent"])),
                    ", ".join(str(v) for v in child_ids) if child_ids else "None",
                    f"{float(row['x']):.6g}",
                    f"{float(row['y']):.6g}",
                    f"{float(row['z']):.6g}",
                ]
            for col_idx, value in enumerate(values):
                item_widget = QTableWidgetItem(value)
                table.setItem(row_idx, col_idx, item_widget)

        layout.addWidget(table, stretch=1)
        dialog.exec()

    def _on_remove_selected(self):
        selected_ids = {str(item.get("item_id", "")) for item in self._selected_tree_items()}
        if not selected_ids:
            return
        self._items = [item for item in self._items if str(item.get("item_id", "")) not in selected_ids]
        self._rebuild_selection_tree()
        self._refresh_ui_from_selection()
        self._emit_selection_preview()

    def _on_clear_all(self):
        self._items = []
        self._rebuild_selection_tree()
        self._refresh_ui_from_selection()
        self._emit_selection_preview()

    def _row_for_node(self, node_id: int) -> pd.Series | None:
        if self._df is None or self._df.empty:
            return None
        row = self._df.loc[self._df["id"].astype(int) == int(node_id)]
        return row.iloc[0] if not row.empty else None

    def _refresh_ui_from_selection(self):
        active = self._active_selection_item()
        union_node_ids = self._union_selected_node_ids()
        if self._df is None or self._df.empty:
            return

        if active is None:
            self._connect_summary.setText("Pick or add one or more selection items to define default source and target nodes.")
            self._disconnect_summary.setText("Choose start and end nodes to disconnect the edge between them.")
            self._insert_summary.setText("Choose start and end nodes for insertion or use the selected item defaults.")
            self._delete_summary.setText("Choose a node or subtree root to delete. Delete actions reindex IDs afterward.")
            self._move_summary.setText("Move the currently selected nodes by entering a new XYZ position for the target anchor node.")
            return

        ordered_items = self._selected_items_in_order()
        anchor_id = int(active.get("anchor_id", -1))
        row = self._row_for_node(anchor_id)
        if row is not None:
            self._move_node_x.setValue(float(row["x"]))
            self._move_node_y.setValue(float(row["y"]))
            self._move_node_z.setValue(float(row["z"]))
        self._refresh_operation_defaults(ordered_items)

    def _refresh_operation_defaults(self, ordered_items: list[dict[str, Any]]):
        if self._df is None or self._df.empty:
            return
        anchors = [int(item.get("anchor_id", -1)) for item in ordered_items if int(item.get("anchor_id", -1)) > 0]
        first_anchor = int(anchors[0]) if anchors else -1
        selected_node_ids: list[int] = []
        for item in ordered_items:
            for node_id in item.get("node_ids", []):
                try:
                    selected_node_ids.append(int(node_id))
                except (TypeError, ValueError):
                    continue
        selected_node_ids = sorted(set(selected_node_ids))

        default_start = None
        default_end = None
        default_hint = ""
        if len(ordered_items) >= 2 and selected_node_ids:
            default_start = int(selected_node_ids[0])
            default_end = int(selected_node_ids[-1])
            default_hint = (
                f"Default guess uses the smallest selected node ID as start ({default_start}) "
                f"and the largest selected node ID as end ({default_end})."
            )
        elif len(ordered_items) == 1:
            item_node_ids = sorted(
                {
                    int(node_id)
                    for node_id in ordered_items[0].get("node_ids", [])
                    if str(node_id).strip()
                }
            )
            if item_node_ids:
                default_start = int(item_node_ids[0])
                if len(item_node_ids) > 1:
                    default_end = int(item_node_ids[-1])
                    default_hint = (
                        f"Default tree range uses the smallest node ID as start ({default_start}) "
                        f"and the largest node ID as end ({default_end})."
                    )
                else:
                    default_hint = f"Default start uses the selected node ({default_start})."

        connect_source = default_start
        connect_target = default_end
        self._connect_source_input.setText(str(connect_source) if connect_source is not None else "")
        self._connect_target_input.setText(str(connect_target) if connect_target is not None else "")
        self._disconnect_source_input.setText(str(default_start) if default_start is not None else "")
        self._disconnect_target_input.setText(str(default_end) if default_end is not None else "")
        if default_start is not None:
            self._connect_summary.setText(
                (default_hint + " " if default_hint else "")
                + f"Current connect guess is start={self._connect_source_input.text() or 'None'} and "
                f"end={self._connect_target_input.text() or 'None'}. "
                "You can change either node ID freely before applying."
            )
            self._disconnect_summary.setText(
                (default_hint + " " if default_hint else "")
                + f"Current disconnect guess is start={self._disconnect_source_input.text() or 'None'} and "
                f"end={self._disconnect_target_input.text() or 'None'}. "
                "You can change either node ID freely before disconnecting."
            )
        else:
            self._connect_summary.setText("Enter start and end node IDs to connect or disconnect.")
            self._disconnect_summary.setText("Enter start and end node IDs to disconnect the edge between them.")

        insert_start = None
        insert_end = None
        insert_hint = ""
        if len(ordered_items) >= 2 and selected_node_ids:
            insert_start = int(selected_node_ids[0])
            insert_end = int(selected_node_ids[-1])
            insert_hint = (
                f"Default insert pair uses the smallest selected node ID as start ({insert_start}) "
                f"and the largest selected node ID as end ({insert_end})."
            )
        elif len(ordered_items) == 1 and default_start is not None:
            anchor_row = self._row_for_node(int(default_start))
            if anchor_row is not None:
                parent_id = int(anchor_row["parent"])
                children = self._df.loc[self._df["parent"].astype(int) == int(default_start), "id"].astype(int).tolist()
                if parent_id >= 0:
                    insert_start = parent_id
                    insert_end = int(default_start)
                elif children:
                    insert_start = int(default_start)
                    insert_end = int(children[0])
                insert_hint = (
                    f"Parent: {parent_id if parent_id >= 0 else 'None'} | "
                    f"Children: {', '.join(str(v) for v in children) if children else 'None'}"
                )
        self._insert_start_input.setText(str(insert_start) if insert_start is not None else "")
        self._insert_end_input.setText(str(insert_end) if insert_end is not None else "")
        self._insert_summary.setText(
            (insert_hint + " " if insert_hint else "")
            + "You can change start and end node IDs freely before inserting."
        )
        start_row = self._row_for_node(int(insert_start)) if insert_start is not None else None
        end_row = self._row_for_node(int(insert_end)) if insert_end is not None else None
        if start_row is not None and end_row is not None:
            self._insert_x.setValue((float(start_row["x"]) + float(end_row["x"])) * 0.5)
            self._insert_y.setValue((float(start_row["y"]) + float(end_row["y"])) * 0.5)
            self._insert_z.setValue((float(start_row["z"]) + float(end_row["z"])) * 0.5)

        move_anchor = default_start if default_start is not None else -1
        self._delete_node_input.setText(str(move_anchor) if move_anchor > 0 else "")
        self._move_anchor_input.setText(str(move_anchor) if move_anchor > 0 else "")
        move_row = self._row_for_node(int(move_anchor)) if move_anchor > 0 else None
        if move_row is not None:
            self._move_node_x.setValue(float(move_row["x"]))
            self._move_node_y.setValue(float(move_row["y"]))
            self._move_node_z.setValue(float(move_row["z"]))
        delete_hint = ""
        if move_anchor > 0:
            delete_row = self._row_for_node(int(move_anchor))
            if delete_row is not None:
                parent_id = int(delete_row["parent"])
                child_count = int((self._df["parent"].astype(int) == int(move_anchor)).sum())
                delete_hint = (
                    f"Default delete target is node {int(move_anchor)}. "
                    f"Parent: {parent_id if parent_id >= 0 else 'None'} | Children: {child_count}."
                )
        self._delete_summary.setText(
            (delete_hint + " " if delete_hint else "")
            + "You can change the target node ID freely before deleting."
        )
        selected_count = len(union_node_ids := self._union_selected_node_ids())
        self._move_summary.setText(
            f"Move {selected_count} selected node(s) by setting a new XYZ for anchor node "
            f"{self._move_anchor_input.text() or 'None'}. The same translation delta is applied to all selected parts."
        )

    def _emit_selection_preview(self):
        mode = str(self._visibility_combo.currentData() or "dim")
        auto_zoom = bool(self._auto_zoom_cb.isChecked())
        self.selection_preview_changed.emit(self._union_selected_node_ids(), mode, auto_zoom)

    def _on_move_node_clicked(self):
        try:
            anchor_id = int(str(self._move_anchor_input.text() or "").strip())
        except ValueError:
            self.log_message.emit("Geometry Editing: enter a valid move target node ID.")
            return
        selected_node_ids = self._union_selected_node_ids()
        if not selected_node_ids:
            self.log_message.emit("Geometry Editing: add or select at least one item first.")
            return
        self.move_selection_requested.emit(
            selected_node_ids,
            int(anchor_id),
            float(self._move_node_x.value()),
            float(self._move_node_y.value()),
            float(self._move_node_z.value()),
        )

    def _on_reconnect_clicked(self):
        try:
            source_id = int(str(self._connect_source_input.text() or "").strip())
            target_id = int(str(self._connect_target_input.text() or "").strip())
        except ValueError:
            self.log_message.emit("Geometry Editing: enter valid start and end node IDs.")
            return
        self.reconnect_requested.emit(int(source_id), int(target_id))

    def _on_disconnect_clicked(self):
        try:
            source_id = int(str(self._disconnect_source_input.text() or "").strip())
            target_id = int(str(self._disconnect_target_input.text() or "").strip())
        except ValueError:
            self.log_message.emit("Geometry Editing: enter valid start and end node IDs to disconnect.")
            return
        self.disconnect_requested.emit(int(source_id), int(target_id))

    def _on_delete_node_clicked(self, *, reconnect_children: bool):
        try:
            node_id = int(str(self._delete_node_input.text() or "").strip())
        except ValueError:
            self.log_message.emit("Geometry Editing: choose a valid node ID to delete.")
            return
        self.delete_node_requested.emit(int(node_id), bool(reconnect_children))

    def _on_delete_subtree_clicked(self):
        try:
            node_id = int(str(self._delete_node_input.text() or "").strip())
        except ValueError:
            self.log_message.emit("Geometry Editing: choose a valid subtree root node ID first.")
            return
        self.delete_subtree_requested.emit(int(node_id))

    def _on_insert_clicked(self):
        try:
            start_id = int(str(self._insert_start_input.text() or "").strip())
        except ValueError:
            self.log_message.emit("Geometry Editing: enter a valid start node ID for insert.")
            return
        end_text = str(self._insert_end_input.text() or "").strip()
        try:
            end_id = int(end_text) if end_text else -1
        except ValueError:
            self.log_message.emit("Geometry Editing: end node ID must be empty or a valid node ID.")
            return
        self.insert_node_requested.emit(
            int(start_id),
            int(end_id),
            float(self._insert_x.value()),
            float(self._insert_y.value()),
            float(self._insert_z.value()),
        )
