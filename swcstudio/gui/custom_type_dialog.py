"""Dialog for defining names and colors for custom SWC types."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QScrollArea,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from swcstudio.core.custom_types import (
    default_custom_color_for_type,
    get_custom_type_definition,
    load_custom_type_definitions,
    save_custom_type_definitions,
)


class DefineCustomTypesDialog(QDialog):
    definitions_changed = Signal(object)

    def __init__(self, custom_types: list[dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Define Custom Types")
        self.resize(760, 520)
        self._rows: dict[int, dict[str, Any]] = {}
        self._row_seq: int = 0
        self._form: QFormLayout | None = None
        self._suspend_live_updates: bool = False
        self._build_ui(custom_types)

    def _build_ui(self, custom_types: list[dict[str, Any]]):
        self._suspend_live_updates = True
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        intro = QLabel(
            "Define as many custom SWC node types as needed. Each type needs a unique ID, name, color, and optional notes."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        add_row = QHBoxLayout()
        self._btn_add = QPushButton("Add Custom Type")
        self._btn_add.clicked.connect(self._on_add_clicked)
        add_row.addWidget(self._btn_add)
        add_row.addStretch()
        root.addLayout(add_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        form = QFormLayout(host)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(10)
        self._form = form

        existing_defs = load_custom_type_definitions(force=True)
        requested_counts: dict[int, int] = {}
        for item in custom_types:
            try:
                type_id = int(item.get("type_id", -1))
            except Exception:
                continue
            if type_id < 5:
                continue
            requested_counts[type_id] = int(item.get("node_count", 0))

        all_type_ids = sorted(set(existing_defs.keys()) | set(requested_counts.keys()))
        for type_id in all_type_ids:
            self._add_type_row(type_id, requested_counts.get(type_id, 0))

        scroll.setWidget(host)
        root.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

        self._suspend_live_updates = False

    def _apply_color_button_style(self, button: QPushButton, hex_color: str):
        button.setText(hex_color)
        button.setStyleSheet(
            f"QPushButton {{ background: {hex_color}; color: #111; border: 1px solid #cfd9e6; border-radius: 8px; padding: 6px 10px; }}"
        )

    def _next_available_type_id(self) -> int:
        used = {int(row["type_spin"].value()) for row in self._rows.values()}
        candidate = 5
        while candidate in used:
            candidate += 1
        return candidate

    def _add_type_row(self, type_id: int, node_count: int):
        if self._form is None:
            return
        type_id = max(5, int(type_id))
        if type_id in self._rows:
            return
        existing = get_custom_type_definition(type_id) or {}
        color = str(existing.get("color", "")).strip() or default_custom_color_for_type(type_id)

        type_spin = QSpinBox()
        type_spin.setRange(5, 9999)
        type_spin.setValue(type_id)

        name_edit = QLineEdit(str(existing.get("name", "")).strip() or f"custom type {type_id}")
        color_btn = QPushButton()
        self._apply_color_button_style(color_btn, color)
        notes_edit = QLineEdit(str(existing.get("notes", "")).strip())
        remove_btn = QPushButton("Remove")

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(QLabel("Type"))
        row_layout.addWidget(type_spin)
        row_layout.addWidget(QLabel("Name"))
        row_layout.addWidget(name_edit, stretch=1)
        row_layout.addWidget(QLabel("Color"))
        row_layout.addWidget(color_btn)
        row_layout.addWidget(QLabel("Notes"))
        row_layout.addWidget(notes_edit, stretch=1)
        row_layout.addWidget(remove_btn)

        if node_count > 0:
            label = QLabel(f"Type {type_id} ({node_count} nodes)")
        else:
            label = QLabel(f"Type {type_id}")
        self._form.addRow(label, row_widget)

        row_id = self._row_seq
        self._row_seq += 1
        row = {
            "row_id": row_id,
            "type_id": type_id,
            "label": label,
            "row_widget": row_widget,
            "type_spin": type_spin,
            "name_edit": name_edit,
            "color_btn": color_btn,
            "notes_edit": notes_edit,
            "color": color,
            "node_count": node_count,
        }
        color_btn.clicked.connect(lambda _=False, current_row=row: self._choose_color(current_row))
        type_spin.valueChanged.connect(lambda value, current_row=row: self._on_type_id_changed(current_row, value))
        name_edit.textChanged.connect(lambda _=None: self._emit_definitions_changed())
        notes_edit.textChanged.connect(lambda _=None: self._emit_definitions_changed())
        remove_btn.clicked.connect(lambda _=False, current_row=row: self._remove_row(current_row))
        self._rows[row_id] = row
        self._emit_definitions_changed()

    def _on_add_clicked(self):
        self._add_type_row(self._next_available_type_id(), 0)

    def _on_type_id_changed(self, row: dict[str, Any], new_type_id: int):
        new_type_id = max(5, int(new_type_id))
        original_type_id = int(row["type_id"])
        if new_type_id == original_type_id:
            return
        used = {
            int(other_row["type_spin"].value())
            for other_row in self._rows.values()
            if other_row is not row
        }
        if new_type_id in used:
            QMessageBox.warning(self, "Duplicate Type ID", f"Type {new_type_id} already exists.")
            row["type_spin"].blockSignals(True)
            row["type_spin"].setValue(original_type_id)
            row["type_spin"].blockSignals(False)
            return
        row["type_id"] = new_type_id
        row["label"].setText(
            f"Type {new_type_id} ({row['node_count']} nodes)" if int(row["node_count"]) > 0 else f"Type {new_type_id}"
        )
        if not str(row["name_edit"].text()).strip() or str(row["name_edit"].text()).strip() == f"custom type {original_type_id}":
            row["name_edit"].setText(f"custom type {new_type_id}")
        self._emit_definitions_changed()

    def _choose_color(self, row: dict[str, Any]):
        current = QColor(str(row["color"]))
        color = QColorDialog.getColor(current, self, f"Choose Color for Type {int(row['type_spin'].value())}")
        if not color.isValid():
            return
        hex_color = color.name()
        row["color"] = hex_color
        self._apply_color_button_style(row["color_btn"], hex_color)
        save_custom_type_definitions(self.definitions())
        self.definitions_changed.emit(load_custom_type_definitions(force=True))

    def _remove_row(self, row: dict[str, Any]):
        row_id = int(row["row_id"])
        row = self._rows.pop(row_id, None)
        if not row or self._form is None:
            return
        self._form.removeRow(row["label"])
        self._emit_definitions_changed()

    def _emit_definitions_changed(self):
        if self._suspend_live_updates:
            return
        definitions = self.definitions()
        save_custom_type_definitions(definitions)
        self.definitions_changed.emit(load_custom_type_definitions(force=True))

    def definitions(self) -> dict[int, dict[str, str]]:
        out: dict[int, dict[str, str]] = {}
        for row in self._rows.values():
            resolved_type_id = int(row["type_spin"].value())
            out[int(resolved_type_id)] = {
                "name": str(row["name_edit"].text()).strip(),
                "color": str(row["color"]).strip(),
                "notes": str(row["notes_edit"].text()).strip(),
            }
        return out

    def accept(self):
        seen: set[int] = set()
        for row in self._rows.values():
            type_id = int(row["type_spin"].value())
            name = str(row["name_edit"].text()).strip()
            if type_id in seen:
                QMessageBox.warning(self, "Duplicate Type ID", f"Type {type_id} appears more than once.")
                return
            if type_id < 5:
                QMessageBox.warning(self, "Invalid Type ID", "Custom type IDs must be 5 or greater.")
                return
            if not name:
                QMessageBox.warning(self, "Missing Name", f"Type {type_id} must have a name.")
                return
            seen.add(type_id)
        super().accept()
