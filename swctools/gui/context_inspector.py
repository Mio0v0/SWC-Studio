"""Contextual issue inspector for the issue-driven repair workflow."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _ExpandableDetailTextEdit(QPlainTextEdit):
    expanded = Signal()

    def mouseDoubleClickEvent(self, event):
        self.expanded.emit()
        super().mouseDoubleClickEvent(event)


class ContextInspectorWidget(QWidget):
    """Shows a single issue with a simple problem -> solution -> action flow."""

    apply_suggested_fix_requested = Signal(str)
    open_tool_requested = Signal(str)
    skip_issue_requested = Signal(str, bool)
    custom_action_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_issue_id = ""
        self._compact_mode = False
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._build_ui()
        self.clear()

    def _build_ui(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(10, 10, 10, 10)
        self._root.setSpacing(10)
        self._root.setAlignment(Qt.AlignTop)

        self._meta = QLabel("")
        self._meta.setWordWrap(True)
        self._meta.setStyleSheet("font-size: 12px; color: #5f6b7a;")
        self._meta.setVisible(False)

        self._title = QLabel("")
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size: 18px; font-weight: 700; color: #132238;")
        self._root.addWidget(self._title)

        self._problem_title = QLabel("Problem Detail")
        self._problem_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        self._root.addWidget(self._problem_title)

        self._problem_detail = QLabel("")
        self._problem_detail.setWordWrap(True)
        self._problem_detail.setStyleSheet("font-size: 13px; color: #334155;")
        self._root.addWidget(self._problem_detail)

        self._suggestion_title = QLabel("Suggested Solution")
        self._suggestion_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        self._root.addWidget(self._suggestion_title)

        self._suggested_solution = QLabel("")
        self._suggested_solution.setWordWrap(True)
        self._suggested_solution.setStyleSheet("font-size: 13px; color: #334155;")
        self._root.addWidget(self._suggested_solution)

        action_row = QHBoxLayout()
        self._btn_skip = QPushButton("Skip")
        self._btn_skip.clicked.connect(self._on_skip_clicked)
        action_row.addWidget(self._btn_skip)

        self._btn_apply_fix = QPushButton("Apply Suggested Fix")
        self._btn_apply_fix.clicked.connect(self._on_apply_fix_clicked)
        action_row.addWidget(self._btn_apply_fix)

        self._btn_open_tool = QPushButton("Open Related Tool")
        self._btn_open_tool.clicked.connect(self._on_open_tool_clicked)
        action_row.addWidget(self._btn_open_tool)

        self._btn_secondary = QPushButton("")
        self._btn_secondary.clicked.connect(self._on_secondary_clicked)
        action_row.addWidget(self._btn_secondary)
        action_row.addStretch()
        self._root.addLayout(action_row)

        self._detail_title = QLabel("Affected Items")
        self._detail_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        detail_row = QHBoxLayout()
        detail_row.addWidget(self._detail_title)
        detail_row.addStretch()
        self._btn_expand_detail = QPushButton("Expand")
        self._btn_expand_detail.clicked.connect(self._open_detail_dialog)
        detail_row.addWidget(self._btn_expand_detail)
        self._root.addLayout(detail_row)

        self._detail_text = _ExpandableDetailTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setMinimumHeight(64)
        self._detail_text.setMaximumHeight(72)
        self._detail_text.expanded.connect(self._open_detail_dialog)
        self._root.addWidget(self._detail_text, stretch=0)
        self._root.addStretch(1)

    def _apply_layout_mode(self, compact: bool):
        self._compact_mode = bool(compact)
        if self._compact_mode:
            self._root.setSpacing(8)
            self._detail_text.setMinimumHeight(0)
            self._detail_text.setMaximumHeight(0)
            self._root.setStretchFactor(self._detail_text, 0)
            self._root.setStretch(self._root.count() - 1, 1)
        else:
            self._root.setSpacing(10)
            self._detail_text.setMaximumHeight(72)
            self._detail_text.setMinimumHeight(64)
            self._root.setStretchFactor(self._detail_text, 0)
            self._root.setStretch(self._root.count() - 1, 1)

    def clear(
        self,
        *,
        title: str = "Inspector idle",
        problem_detail: str = "Choose an issue from the left to inspect it.",
        suggested_solution: str = "The inspector will show the best next action here.",
    ):
        self._current_issue_id = ""
        self._title.setText(title)
        self._problem_detail.setText(problem_detail)
        self._suggested_solution.setText(suggested_solution)
        self._detail_text.setPlainText("")
        self._btn_skip.setEnabled(False)
        self._btn_skip.setText("Skip")
        self._btn_skip.setVisible(False)
        self._btn_apply_fix.setEnabled(False)
        self._btn_apply_fix.setVisible(False)
        self._btn_apply_fix.setText("Apply Suggested Fix")
        self._btn_open_tool.setEnabled(False)
        self._btn_open_tool.setVisible(False)
        self._btn_open_tool.setText("Open Related Tool")
        self._btn_open_tool.setProperty("tool_target", "validation")
        self._btn_expand_detail.setVisible(False)
        self._btn_secondary.setVisible(False)
        self._btn_secondary.setEnabled(False)
        self._btn_secondary.setText("")
        self._btn_secondary.setProperty("action_id", "")
        self._problem_title.setVisible(True)
        self._problem_detail.setVisible(True)
        self._suggestion_title.setVisible(True)
        self._suggested_solution.setVisible(True)
        self._detail_title.setVisible(False)
        self._detail_text.setVisible(False)
        self._apply_layout_mode(True)

    def set_issue(self, issue: dict[str, Any] | None, context: dict[str, Any] | None = None):
        if not issue:
            self.clear()
            return

        ctx = dict(context or {})
        self._current_issue_id = str(issue.get("issue_id", "")).strip()
        self._title.setText(str(issue.get("title", "Issue")).strip() or "Issue")
        self._problem_detail.setText(str(ctx.get("problem_detail", "")).strip() or str(issue.get("description", "")).strip() or "No extra detail provided.")
        self._suggested_solution.setText(str(ctx.get("suggested_solution", "")).strip() or str(issue.get("suggested_fix", "")).strip() or "Inspect the issue and use the related tool to continue.")
        detail_text = "\n".join(str(line) for line in list(ctx.get("detail_lines", [])) if str(line).strip())
        self._detail_text.setPlainText(detail_text)
        self._btn_expand_detail.setVisible(bool(detail_text.strip()))

        self._btn_skip.setEnabled(bool(self._current_issue_id))
        self._btn_skip.setText("Restore" if str(issue.get("status", "")).strip().lower() == "skipped" else "Skip")

        tool_target = str(issue.get("tool_target", "validation")).strip() or "validation"
        self._btn_open_tool.setEnabled(True)
        self._btn_open_tool.setText(str(ctx.get("tool_button_label", "")).strip() or "Open Related Tool")
        self._btn_open_tool.setProperty("tool_target", tool_target)

        auto_fix_available = bool(ctx.get("auto_fix_available"))
        self._btn_apply_fix.setVisible(auto_fix_available)
        self._btn_apply_fix.setEnabled(auto_fix_available and bool(self._current_issue_id))
        self._btn_apply_fix.setText(str(ctx.get("auto_fix_label", "")).strip() or "Apply Suggested Fix")

        custom_primary = str(ctx.get("custom_primary_label", "")).strip()
        custom_primary_action = str(ctx.get("custom_primary_action", "")).strip()
        if custom_primary and custom_primary_action:
            self._btn_skip.setVisible(False)
            self._btn_apply_fix.setVisible(False)
            self._btn_open_tool.setVisible(True)
            self._btn_open_tool.setEnabled(True)
            self._btn_open_tool.setText(custom_primary)
            self._btn_open_tool.setProperty("tool_target", f"custom:{custom_primary_action}")
        else:
            self._btn_skip.setVisible(True)
            self._btn_open_tool.setVisible(True)

        custom_secondary = str(ctx.get("custom_secondary_label", "")).strip()
        custom_secondary_action = str(ctx.get("custom_secondary_action", "")).strip()
        if custom_secondary and custom_secondary_action:
            self._btn_secondary.setVisible(True)
            self._btn_secondary.setEnabled(bool(self._current_issue_id))
            self._btn_secondary.setText(custom_secondary)
            self._btn_secondary.setProperty("action_id", custom_secondary_action)
        else:
            self._btn_secondary.setVisible(False)
            self._btn_secondary.setEnabled(False)
            self._btn_secondary.setText("")
            self._btn_secondary.setProperty("action_id", "")

        if bool(ctx.get("hide_skip_button")):
            self._btn_skip.setVisible(False)
        if bool(ctx.get("hide_apply_button")):
            self._btn_apply_fix.setVisible(False)
        hide_detail = bool(ctx.get("hide_detail_section"))
        self._detail_title.setVisible(not hide_detail)
        self._detail_text.setVisible(not hide_detail)
        self._btn_expand_detail.setVisible((not hide_detail) and bool(detail_text.strip()))
        self._apply_layout_mode(hide_detail)

    def _on_skip_clicked(self):
        if not self._current_issue_id:
            return
        skipping = self._btn_skip.text().strip().lower() == "skip"
        self.skip_issue_requested.emit(self._current_issue_id, skipping)

    def _on_apply_fix_clicked(self):
        if not self._current_issue_id:
            return
        self.apply_suggested_fix_requested.emit(self._current_issue_id)

    def _on_open_tool_clicked(self):
        if not self._current_issue_id:
            return
        target = str(self._btn_open_tool.property("tool_target") or "validation")
        if target.startswith("custom:"):
            self.custom_action_requested.emit(self._current_issue_id, target.split(":", 1)[1])
            return
        self.open_tool_requested.emit(target)

    def _on_secondary_clicked(self):
        if not self._current_issue_id:
            return
        action_id = str(self._btn_secondary.property("action_id") or "").strip()
        if action_id:
            self.custom_action_requested.emit(self._current_issue_id, action_id)

    def _open_detail_dialog(self):
        text = self._detail_text.toPlainText().strip()
        if not text:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Issue Detail")
        dlg.resize(820, 560)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        title = QLabel(self._title.text().strip() or "Issue Detail")
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #132238;")
        root.addWidget(title)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(text)
        box.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #fafafa; border: 1px solid #ddd; color: #222;"
            "  font-family: Menlo, Consolas, monospace; font-size: 12px;"
            "}"
        )
        root.addWidget(box, stretch=1)
        row = QHBoxLayout()
        row.addStretch()
        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        row.addWidget(btn)
        root.addLayout(row)
        dlg.exec()
