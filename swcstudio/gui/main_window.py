"""Main window layout for the issue-driven SWC Studio workspace."""

import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QDialog,
    QFrame,
    QGroupBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .auto_typing_guide import AutoTypingGuideWidget
from .batch_tab import BatchTabWidget
from .constants import SWC_COLS, label_for_type
from .context_inspector import ContextInspectorWidget
from .custom_type_dialog import DefineCustomTypesDialog
from .editor_tab import EditorTab
from .geometry_editing_panel import GeometryEditingPanel
from .issue_panel import IssuePanelWidget
from .manual_radii_panel import ManualRadiiPanel
from .neuron_3d_widget import Neuron3DWidget
from .report_popup import ReportPopupDialog
from .radii_cleaning_panel import RadiiCleaningPanel
from .simplification_panel import SimplificationPanel
from .swc_table_widget import SWCTableWidget
from .validation_auto_label_panel import ValidationAutoLabelPanel
from .validation_tab import ValidationIndexCleanWidget, ValidationPrecheckWidget, ValidationTabWidget
from swcstudio.core.issues import (
    issues_from_radii_suspicion,
    issues_from_simplification_suggestion,
    issues_from_type_suspicion,
    issues_from_validation_report,
    validation_prerequisite_summary,
)
from swcstudio.core.custom_types import save_custom_type_definitions
from swcstudio.core.geometry_editing import (
    delete_node as geometry_delete_node,
    delete_subtree as geometry_delete_subtree,
    disconnect_branch,
    insert_node_between,
    move_selection_by_anchor_absolute,
    path_between_nodes,
    reconnect_branch,
    subtree_node_ids,
)
from swcstudio.core.radii_cleaning import radii_stats_by_type
from swcstudio.core.reporting import (
    auto_typing_log_path_for_file,
    correction_summary_log_path_for_file,
    format_correction_summary_report_text,
    format_auto_typing_report_text,
    format_morphology_session_log_text,
    format_simplification_report_text,
    morphology_session_log_path,
    output_dir_for_file,
    simplification_log_path_for_file,
    write_text_report,
)
from swcstudio.core.swc_io import parse_swc_text_preserve_tokens, write_swc_to_bytes_preserve_tokens
from swcstudio.core.validation_engine import consolidate_complex_somas_array
from swcstudio.tools.morphology_editing.features.simplification import simplify_dataframe
from swcstudio.tools.validation.features.auto_typing import (
    RuleBatchOptions,
    run_file as run_validation_auto_typing_file,
)


@dataclass
class _DocumentState:
    """Open SWC document state bound to one editor tab/window."""

    editor: EditorTab
    controls: QWidget
    df: pd.DataFrame
    filename: str
    file_path: str
    original_df: pd.DataFrame | None = None
    session_started_at: str = ""
    session_operations: list[dict] = field(default_factory=list)
    session_seq: int = 0
    is_preview: bool = False
    source_editor: EditorTab | None = None
    preview_kind: str = ""
    validation_report: dict | None = None
    issues: list[dict] = field(default_factory=list)
    issue_status_overrides: dict[str, str] = field(default_factory=dict)
    fixed_issue_count: int = 0
    pending_resolved_issue_ids: set[str] = field(default_factory=set)
    selected_issue_id: str = ""
    recovery_path: str = ""
    history_snapshots: list[pd.DataFrame] = field(default_factory=list)
    history_index: int = -1
    last_auto_label_result: dict | None = None
    last_auto_label_options: dict | None = None
    auto_label_preview_df: pd.DataFrame | None = None
    auto_label_preview_base_df: pd.DataFrame | None = None
    last_simplification_result: dict | None = None


class _CanvasTabs(QTabWidget):
    """Tab widget for open SWC documents with drag-out support."""

    detach_requested = Signal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self._drag_tab_index = -1
        self._drag_start_global = None
        self.tabBar().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.tabBar():
            et = event.type()
            if et == QEvent.MouseButtonPress and getattr(event, "button", lambda: None)() == Qt.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                self._drag_tab_index = self.tabBar().tabAt(pos)
                self._drag_start_global = (
                    event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                )
            elif et == QEvent.MouseMove and self._drag_tab_index >= 0 and self._drag_start_global is not None:
                now_global = (
                    event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                )
                if (now_global - self._drag_start_global).manhattanLength() >= QApplication.startDragDistance():
                    local = self.tabBar().mapFromGlobal(now_global)
                    if not self.tabBar().rect().adjusted(-32, -24, 32, 24).contains(local):
                        idx = int(self._drag_tab_index)
                        self._drag_tab_index = -1
                        self._drag_start_global = None
                        self.detach_requested.emit(idx, int(now_global.x()), int(now_global.y()))
                        return True
            elif et in (QEvent.MouseButtonRelease, QEvent.Leave):
                self._drag_tab_index = -1
                self._drag_start_global = None
        return super().eventFilter(watched, event)


class _DetachedEditorWindow(QMainWindow):
    """Floating window hosting one detached SWC editor."""

    editor_closing = Signal(QWidget)

    def __init__(self, editor: EditorTab, title: str, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(title)
        self.resize(980, 760)
        self.setCentralWidget(editor)

    def closeEvent(self, event):
        parent = self.parent()
        if parent is not None and hasattr(parent, "_request_detached_editor_close"):
            try:
                allow_close = bool(parent._request_detached_editor_close(self._editor))
            except Exception:
                allow_close = True
            if not allow_close:
                event.ignore()
                return
        else:
            self.editor_closing.emit(self._editor)
        super().closeEvent(event)


class SWCMainWindow(QMainWindow):
    """Top-level app window with tabbed top bar, workspace, side panels, and edit log."""

    swc_loaded = Signal(pd.DataFrame, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SWC Studio")
        self.setAcceptDrops(False)

        self._df: pd.DataFrame | None = None
        self._filename: str = ""
        self._file_path: str = ""
        self._recent_paths: list[str] = []
        self._active_tool: str = ""
        self._documents: dict[EditorTab, _DocumentState] = {}
        self._detached_windows: dict[EditorTab, _DetachedEditorWindow] = {}
        self._control_wrappers: dict[int, QScrollArea] = {}
        self._floating_control_dialogs: dict[str, QDialog] = {}
        self._simplify_preview_by_source: dict[EditorTab, EditorTab] = {}
        self._simplify_source_by_preview: dict[EditorTab, EditorTab] = {}
        self._simplify_result_by_preview: dict[EditorTab, dict] = {}
        self._auto_label_preview_by_source: dict[EditorTab, EditorTab] = {}
        self._auto_label_source_by_preview: dict[EditorTab, EditorTab] = {}
        self._auto_label_result_by_preview: dict[EditorTab, dict] = {}
        self._batch_has_results: bool = False
        self._closing_app: bool = False
        self._runtime_log_lines: list[str] = []

        self._build_ui()
        self._build_status_bar()
        self._apply_initial_window_geometry()

    def _apply_initial_window_geometry(self) -> None:
        """Start within the available screen work area to avoid Qt geometry warnings."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(1480, 920)
            return

        available = screen.availableGeometry()
        target_width = min(1480, max(1100, available.width() - 120))
        target_height = min(920, max(760, available.height() - 120))
        target_width = min(target_width, max(200, available.width()))
        target_height = min(target_height, max(200, available.height()))
        self.resize(target_width, target_height)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setDockOptions(QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks)
        self.setDockNestingEnabled(True)

        # Use an in-window top strip instead of the OS menu bar.
        self.menuBar().setVisible(False)

        # ---------------- Top unified bar: menu + tools/features ----------------
        self._top_bar = self._build_top_bar()

        # ---------------- Center workspace ----------------
        self._canvas_empty = QWidget()
        self._canvas_empty.setStyleSheet("background: #e9eef5; border-radius: 18px;")

        self._canvas_tabs = _CanvasTabs()
        self._canvas_tabs.currentChanged.connect(self._on_document_tab_changed)
        self._canvas_tabs.tabCloseRequested.connect(self._on_document_tab_close_requested)
        self._canvas_tabs.detach_requested.connect(self._on_document_detach_requested)

        self._batch_canvas = EditorTab()
        self._batch_canvas.set_mode(EditorTab.MODE_BATCH)

        self._canvas_stack = QStackedWidget()
        self._canvas_stack.addWidget(self._canvas_empty)
        self._canvas_stack.addWidget(self._canvas_tabs)
        self._canvas_stack.addWidget(self._batch_canvas)

        # ---------------- Side docks: issue navigation + contextual inspector ----------------
        self._data_tabs = QTabWidget()
        self._data_tabs.setMinimumWidth(0)
        self._data_tabs.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._data_tabs.tabBar().setUsesScrollButtons(False)
        self._issue_panel = IssuePanelWidget()
        self._issue_panel.issue_selected.connect(self._on_issue_selected)
        self._issue_panel.rule_guide_requested.connect(self._on_precheck_requested)
        self._issue_panel.export_swc_requested.connect(self._on_issue_panel_export_swc_requested)
        self._table_widget = SWCTableWidget()
        self._table_widget.setMinimumWidth(0)
        self._table_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

        self._info_label = QLabel("No SWC file loaded.")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("font-size: 13px; color: #444; padding: 8px;")
        file_panel = QWidget()
        file_layout = QVBoxLayout(file_panel)
        file_layout.setContentsMargins(6, 6, 6, 6)
        file_layout.setSpacing(8)
        file_layout.addWidget(self._info_label, stretch=0)
        file_layout.addWidget(self._table_widget, stretch=1)

        self._segment_label = QLabel(
            "Segment Info\n\nLoad an SWC file and select nodes in dendrogram mode."
        )
        self._segment_label.setWordWrap(True)
        self._segment_label.setStyleSheet("font-size: 13px; color: #555; padding: 8px;")
        seg_panel = QWidget()
        seg_layout = QVBoxLayout(seg_panel)
        seg_layout.setContentsMargins(6, 6, 6, 6)
        seg_layout.addWidget(self._segment_label)
        seg_layout.addStretch()

        self._edit_log_text = QPlainTextEdit()
        self._edit_log_text.setReadOnly(True)
        self._edit_log_text.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #fafafa; border: 1px solid #ddd; color: #333;"
            "  font-family: Menlo, Consolas, monospace; font-size: 12px;"
            "}"
        )
        self._edit_log_text.setPlainText("No morphology edits recorded for this session yet.")

        self._data_tabs.addTab(self._issue_panel, "Issues")
        self._data_tabs.addTab(file_panel, "SWC File")
        self._data_tabs.addTab(seg_panel, "Segment Info")
        self._control_tabs = QTabWidget()
        self._control_tabs.setMinimumWidth(0)
        self._control_tabs.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._control_tabs.tabBar().hide()
        self._batch_tab = BatchTabWidget()
        self._batch_tab.batch_validation_ready.connect(self._on_batch_validation_ready)
        self._batch_tab.precheck_requested.connect(self._on_precheck_requested)
        self._validation_tab = ValidationTabWidget(as_panel=False)
        self._validation_tab.precheck_requested.connect(self._on_precheck_requested)
        self._validation_tab.report_ready.connect(self._on_validation_report_ready)
        self._validation_tab.result_activated.connect(self._on_validation_result_activated)
        self._validation_index_clean = ValidationIndexCleanWidget(self)
        self._validation_index_clean.index_clean_requested.connect(self._on_validation_index_clean_requested)
        self._validation_auto_label_panel = ValidationAutoLabelPanel(self)
        self._validation_auto_label_panel.guide_requested.connect(self._show_auto_typing_guide_floating)
        self._validation_auto_label_panel.log_message.connect(lambda msg: self._append_log(msg, "AUTO"))
        self._validation_auto_label_panel.process_requested.connect(
            self._on_validation_auto_label_process_requested
        )
        self._validation_radii_panel = RadiiCleaningPanel(self)
        self._validation_radii_panel.log_message.connect(lambda msg: self._append_log(msg, "RADII"))
        self._validation_radii_panel.loaded_apply_requested.connect(self._on_validation_radii_apply_requested)
        self._manual_radii_panel = ManualRadiiPanel(self)
        self._manual_radii_panel.apply_requested.connect(self._on_manual_radii_apply_requested)
        self._geometry_panel = GeometryEditingPanel(self)
        self._geometry_panel.log_message.connect(lambda msg: self._append_log(msg, "GEOM"))
        self._geometry_panel.selection_preview_changed.connect(self._on_geometry_selection_preview_changed)
        self._geometry_panel.focus_requested.connect(self._on_geometry_focus_requested)
        self._geometry_panel.move_selection_requested.connect(self._on_geometry_move_selection_requested)
        self._geometry_panel.reconnect_requested.connect(self._on_geometry_reconnect_requested)
        self._geometry_panel.disconnect_requested.connect(self._on_geometry_disconnect_requested)
        self._geometry_panel.delete_node_requested.connect(self._on_geometry_delete_node_requested)
        self._geometry_panel.delete_subtree_requested.connect(self._on_geometry_delete_subtree_requested)
        self._geometry_panel.insert_node_requested.connect(self._on_geometry_insert_node_requested)
        self._validation_precheck = ValidationPrecheckWidget()
        self._auto_typing_guide = AutoTypingGuideWidget()
        self._simplification_panel = SimplificationPanel(self)
        self._simplification_panel.log_message.connect(lambda msg: self._append_log(msg, "SIMPLIFY"))
        self._simplification_panel.process_requested.connect(self._on_simplification_process_requested)
        self._viz_control = self._build_visualization_control_panel()
        self._control_tabs.currentChanged.connect(self._on_control_tab_changed)
        self._set_control_tabs_for_feature("")
        self._context_inspector = ContextInspectorWidget(self)
        self._context_inspector.apply_suggested_fix_requested.connect(self._on_apply_suggested_fix_requested)
        self._context_inspector.open_tool_requested.connect(self._on_context_open_tool_requested)
        self._context_inspector.skip_issue_requested.connect(self._on_skip_issue_requested)
        self._context_inspector.custom_action_requested.connect(self._on_context_custom_action_requested)
        self._inspector_host = QWidget()
        self._inspector_layout = QVBoxLayout(self._inspector_host)
        self._inspector_layout.setContentsMargins(0, 0, 0, 0)
        self._inspector_layout.setSpacing(10)
        self._inspector_layout.setAlignment(Qt.AlignTop)
        self._inspector_layout.addWidget(self._context_inspector, stretch=0)
        self._inspector_layout.addWidget(self._control_tabs, stretch=1)

        self._data_dock = QDockWidget("Issue Navigator", self)
        self._data_dock.setObjectName("DataExplorerDock")
        self._data_dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        self._data_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._data_dock.setMinimumWidth(24)
        self._data_dock.setWidget(self._data_tabs)
        self._make_panel_freely_resizable(self._data_dock)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._data_dock)

        self._control_dock = QDockWidget("Inspector", self)
        self._control_dock.setObjectName("ControlCenterDock")
        self._control_dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        self._control_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._control_dock.setMinimumWidth(24)
        self._control_dock.setWidget(self._inspector_host)
        self._make_panel_freely_resizable(self._control_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self._control_dock)

        self._precheck_dock = QDockWidget("Rule Guide", self)
        self._precheck_dock.setObjectName("ValidationPrecheckDock")
        self._precheck_dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        self._precheck_dock.setAllowedAreas(
            Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea | Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )
        self._precheck_dock.setWidget(self._validation_precheck)
        self._make_panel_freely_resizable(self._precheck_dock)
        self.addDockWidget(Qt.TopDockWidgetArea, self._precheck_dock)
        self._precheck_dock.hide()

        self._auto_guide_dock = QDockWidget("Auto Typing Guide", self)
        self._auto_guide_dock.setObjectName("AutoTypingGuideDock")
        self._auto_guide_dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        self._auto_guide_dock.setAllowedAreas(
            Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea | Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )
        self._auto_guide_dock.setWidget(self._auto_typing_guide)
        self._make_panel_freely_resizable(self._auto_guide_dock)
        self.addDockWidget(Qt.TopDockWidgetArea, self._auto_guide_dock)
        self._auto_guide_dock.hide()

        self._batch_tab.log_message.connect(lambda msg: self._append_log(msg, "BATCH"))

        # ---------------- Bottom edit log ----------------
        self._bottom_log_title = QLabel("Edit Log")
        self._bottom_log_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #132238; padding: 0 2px;")
        self._edit_log_text.setMinimumHeight(110)
        self._edit_log_text.setMaximumHeight(240)

        # ---------------- Root layout ----------------
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 0)
        root.setSpacing(6)
        root.addWidget(self._top_bar, stretch=0)
        root.addWidget(self._canvas_stack, stretch=1)
        root.addWidget(self._bottom_log_title, stretch=0)
        root.addWidget(self._edit_log_text, stretch=0)
        self.setCentralWidget(central)
        self._apply_modern_theme()

        self._refresh_canvas_surface()
        self._reset_layout()
        self._append_log("UI initialized. Open SWC files from File menu.", "INFO")

    def _build_top_bar(self) -> QWidget:
        top_bg = "#f7f9fc"
        top_fg = "#132238"
        top_border = "#d8e0eb"
        top_hover = "#edf3fb"

        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(
            "QFrame {"
            f"  background: {top_bg}; border: 1px solid {top_border}; border-radius: 18px;"
            "}"
        )

        root = QVBoxLayout(panel)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self._home_menu_bar = QMenuBar(panel)
        self._home_menu_bar.setNativeMenuBar(False)
        self._home_menu_bar.setStyleSheet(
            "QMenuBar {"
            f"  background: {top_bg}; border-bottom: 1px solid {top_border}; color: {top_fg};"
            "}"
            "QMenuBar::item {"
            "  padding: 8px 12px; background: transparent; border-radius: 8px;"
            "}"
            "QMenuBar::item:selected {"
            f"  background: {top_hover};"
            "}"
            "QMenu {"
            f"  background: {top_bg}; color: {top_fg}; border: 1px solid {top_border};"
            "}"
            "QMenu::item {"
            "  padding: 6px 20px 6px 24px; background: transparent;"
            "}"
            "QMenu::item:selected {"
            f"  background: {top_hover};"
            "}"
        )
        self._populate_home_menus(self._home_menu_bar)
        root.addWidget(self._home_menu_bar, stretch=0)

        group = QGroupBox("Tools")
        group.setStyleSheet(
            "QGroupBox { border: 1px solid #d8e0eb; margin-top: 8px; border-radius: 14px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; color: #5f6b7a; }"
            "QPushButton#toolMenuItem {"
            "  background: transparent; color: #132238; border: none;"
            "  padding: 8px 12px; text-align: left; border-radius: 10px;"
            "}"
            "QPushButton#toolMenuItem:hover {"
            "  background: #edf3fb;"
            "}"
            "QPushButton#toolMenuItem:checked {"
            "  background: #d9e8fb; border: 1px solid #84aee8; font-weight: 700;"
            "}"
            "QPushButton#featureBtn {"
            f"  background: {top_bg}; color: {top_fg}; border: 1px solid {top_border};"
            "  border-radius: 10px; padding: 8px 12px;"
            "}"
            "QPushButton#featureBtn:hover {"
            f"  background: {top_hover};"
            "}"
            "QPushButton#featureBtn:checked {"
            "  background: #d9e8fb; border: 1px solid #84aee8; font-weight: 700;"
            "}"
        )
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(8, 10, 8, 8)
        group_layout.setSpacing(6)

        tools_row = QHBoxLayout()
        tools_row.setContentsMargins(0, 0, 0, 0)
        tools_row.setSpacing(8)

        tool_defs = [
            ("Batch Processing", "batch"),
            ("Validation", "validation"),
            ("Visualization", "visualization"),
            ("Morphology Editing", "morphology_editing"),
            ("Geometry Editing", "geometry_editing"),
        ]

        normal_fm = QFontMetrics(self.font())
        bold_font = self.font()
        bold_font.setBold(True)
        bold_fm = QFontMetrics(bold_font)
        self._tool_menu_buttons: dict[str, QPushButton] = {}
        for label, key in tool_defs:
            btn = QPushButton(label)
            btn.setObjectName("toolMenuItem")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setMinimumWidth(max(normal_fm.horizontalAdvance(label), bold_fm.horizontalAdvance(label)) + 34)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._activate_feature(k))
            btn.setProperty("tool_key", key)
            tools_row.addWidget(btn)
            self._tool_menu_buttons[key] = btn
        tools_row.addStretch()
        group_layout.addLayout(tools_row)

        self._feature_strip = QWidget()
        self._feature_strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._feature_row = QHBoxLayout(self._feature_strip)
        self._feature_row.setContentsMargins(0, 0, 0, 0)
        self._feature_row.setSpacing(6)
        self._feature_row.addStretch()
        group_layout.addWidget(self._feature_strip)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(10)

        # Keep for backward compatibility with existing update calls, but hide from UI.
        self._feature_label = QLabel("")
        self._feature_label.setVisible(False)

        self._current_file_label = QLabel("Current file: (none)")
        self._current_file_label.setStyleSheet("font-size: 12px; color: #555;")
        self._current_file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._current_file_label.setMinimumWidth(0)
        self._current_file_label.setMaximumWidth(360)
        status_row.addWidget(self._current_file_label)
        self._set_current_file_label_text("")

        status_row.addStretch()
        group_layout.addLayout(status_row)

        root.addWidget(group)
        return panel

    def _populate_home_menus(self, menu: QMenuBar):
        menu.clear()

        # File
        file_menu = menu.addMenu("File")
        open_action = QAction("Open", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        export_action = QAction("Export", self)
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        self._recent_menu = file_menu.addMenu("Recent Files")
        self._recent_menu.addAction("(empty)").setEnabled(False)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit
        edit_menu = menu.addMenu("Edit")
        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._undo_edit)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut("Ctrl+Shift+Z")
        redo_action.triggered.connect(self._redo_edit)
        edit_menu.addAction(redo_action)

        pref_action = QAction("Preferences", self)
        pref_action.triggered.connect(
            lambda: self._append_log("Preferences dialog is not implemented yet.", "INFO")
        )
        edit_menu.addAction(pref_action)

        # View
        view_menu = menu.addMenu("View")
        show_log_action = QAction("Show/Hide Edit Log", self)
        show_log_action.triggered.connect(
            lambda: self._toggle_log_panel(not self._edit_log_text.isVisible())
        )
        view_menu.addAction(show_log_action)

        view_menu.addSeparator()
        cam_iso_action = QAction("Camera Isometric", self)
        cam_iso_action.triggered.connect(lambda: self._set_camera("iso"))
        view_menu.addAction(cam_iso_action)
        cam_top_action = QAction("Camera Top", self)
        cam_top_action.triggered.connect(lambda: self._set_camera("top"))
        view_menu.addAction(cam_top_action)
        cam_front_action = QAction("Camera Front", self)
        cam_front_action.triggered.connect(lambda: self._set_camera("front"))
        view_menu.addAction(cam_front_action)
        cam_side_action = QAction("Camera Side", self)
        cam_side_action.triggered.connect(lambda: self._set_camera("side"))
        view_menu.addAction(cam_side_action)

        # Window
        window_menu = menu.addMenu("Window")
        reset_layout_action = QAction("Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        window_menu.addAction(reset_layout_action)

        show_data_action = QAction("Show/Hide Issue Navigator", self)
        show_data_action.triggered.connect(
            lambda: self._toggle_data_panel(not self._data_dock.isVisible())
        )
        window_menu.addAction(show_data_action)

        show_control_action = QAction("Show/Hide Inspector", self)
        show_control_action.triggered.connect(
            lambda: self._toggle_control_panel(not self._control_dock.isVisible())
        )
        window_menu.addAction(show_control_action)

        show_precheck_action = QAction("Show/Hide Rule Guide", self)
        show_precheck_action.triggered.connect(
            lambda: self._toggle_precheck_panel(not self._precheck_dock.isVisible())
        )
        window_menu.addAction(show_precheck_action)

        show_auto_guide_action = QAction("Show/Hide Auto Typing Guide", self)
        show_auto_guide_action.triggered.connect(
            lambda: self._toggle_auto_typing_guide_panel(not self._auto_guide_dock.isVisible())
        )
        window_menu.addAction(show_auto_guide_action)

        # Help
        help_menu = menu.addMenu("Help")
        quick_action = QAction("Quick Manual", self)
        quick_action.triggered.connect(self._show_quick_manual)
        help_menu.addAction(quick_action)
        short_action = QAction("Shortcuts", self)
        short_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(short_action)
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _build_visualization_control_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        row1 = QHBoxLayout()
        b_iso = QPushButton("Isometric")
        b_iso.clicked.connect(lambda: self._set_camera("iso"))
        row1.addWidget(b_iso)
        b_top = QPushButton("Top")
        b_top.clicked.connect(lambda: self._set_camera("top"))
        row1.addWidget(b_top)
        b_front = QPushButton("Front")
        b_front.clicked.connect(lambda: self._set_camera("front"))
        row1.addWidget(b_front)
        b_side = QPushButton("Side")
        b_side.clicked.connect(lambda: self._set_camera("side"))
        row1.addWidget(b_side)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        b_reset = QPushButton("Reset Camera")
        b_reset.clicked.connect(self._reset_camera)
        row2.addWidget(b_reset)
        row2.addWidget(QLabel("Render mode:"))
        self._render_combo = QComboBox()
        self._render_combo.addItem("Lines", Neuron3DWidget.MODE_LINES)
        self._render_combo.addItem("Spheres", Neuron3DWidget.MODE_SPHERES)
        self._render_combo.addItem("Frustum", Neuron3DWidget.MODE_FRUSTUM)
        self._render_combo.currentIndexChanged.connect(self._on_render_mode_changed)
        row2.addWidget(self._render_combo)
        layout.addLayout(row2)

        hint = QLabel(
            "Visualization mode shows:\n"
            "- one 3D view on top\n"
            "- three 2D projections (top/front/side) below"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #555;")
        layout.addWidget(hint)
        layout.addStretch()
        return panel

    def _build_status_bar(self):
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._issue_status_label = QLabel("Issues: 0")
        self._issue_status_label.setStyleSheet("font-size: 12px; color: #5f6b7a; padding-right: 8px;")
        self._status.addPermanentWidget(self._issue_status_label)
        self._status.showMessage("Ready - open an SWC file to start.")

    def _apply_modern_theme(self):
        self.setStyleSheet(
            """
            QMainWindow {
              background: #f4f7fb;
            }
            QMainWindow::separator {
              background: #c6d3e3;
              width: 14px;
              height: 14px;
            }
            QMainWindow::separator:hover {
              background: #84aee8;
            }
            QDockWidget {
              font-size: 13px;
              color: #132238;
            }
            QDockWidget::title {
              background: #eef3f9;
              color: #132238;
              text-align: left;
              padding: 10px 12px;
              border: 1px solid #d8e0eb;
              border-bottom: none;
            }
            QTabWidget::pane, QScrollArea, QPlainTextEdit, QTreeWidget, QTableWidget {
              background: #ffffff;
              border: 1px solid #d8e0eb;
              border-radius: 12px;
            }
            QTabBar::tab {
              background: #eef3f9;
              color: #415062;
              border: 1px solid #d8e0eb;
              padding: 8px 12px;
              margin-right: 4px;
              border-top-left-radius: 10px;
              border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
              background: #ffffff;
              color: #132238;
            }
            QPushButton {
              background: #ffffff;
              color: #132238;
              border: 1px solid #cfd9e6;
              border-radius: 10px;
              padding: 7px 12px;
            }
            QPushButton:hover {
              background: #f4f7fb;
            }
            QPushButton:checked {
              background: #d9e8fb;
              border-color: #84aee8;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
              background: #ffffff;
              border: 1px solid #cfd9e6;
              border-radius: 10px;
              padding: 6px 10px;
            }
            QLabel {
              color: #132238;
            }
            QStatusBar {
              background: #eef3f9;
              border-top: 1px solid #d8e0eb;
            }
            """
        )

    def _clear_feature_row(self):
        while self._feature_row.count() > 0:
            item = self._feature_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _tool_feature_labels(self, tool_key: str | None = None) -> list[str]:
        key = str(tool_key if tool_key is not None else (self._active_tool or "")).strip().lower()
        mapping = {
            "batch": ["Split", "Validation", "Auto Label Editing", "Radii Cleaning", "Simplification", "Index Clean"],
            "validation": ["Validation", "Index Clean"],
            "visualization": ["View Controls"],
            "morphology_editing": ["Manual Label Editing", "Auto Label Editing", "Manual Radii Editing", "Auto Radii Editing"],
            "dendrogram": ["Manual Label Editing", "Auto Label Editing", "Manual Radii Editing", "Auto Radii Editing"],
            "geometry_editing": ["Geometry Editing", "Simplification"],
        }
        return list(mapping.get(key, []))

    def _refresh_top_feature_buttons(self):
        self._clear_feature_row()
        self._top_feature_buttons: list[QPushButton] = []

        labels = self._tool_feature_labels()
        if not labels:
            self._feature_row.addStretch()
            return

        normal_fm = QFontMetrics(self.font())
        bold_font = self.font()
        bold_font.setBold(True)
        bold_fm = QFontMetrics(bold_font)
        max_feature_w = max(max(normal_fm.horizontalAdvance(lb), bold_fm.horizontalAdvance(lb)) for lb in labels) + 36
        for label in labels:
            btn = QPushButton(label)
            btn.setObjectName("featureBtn")
            btn.setCheckable(True)
            btn.setMinimumWidth(max_feature_w)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _=False, lb=label: self._on_top_feature_button_clicked(lb))
            self._feature_row.addWidget(btn)
            self._top_feature_buttons.append(btn)

        self._feature_row.addStretch()
        self._sync_top_feature_button_selection()

    def _sync_top_feature_button_selection(self):
        buttons = getattr(self, "_top_feature_buttons", None)
        if not buttons:
            return

        active_label = ""
        idx = self._control_tabs.currentIndex()
        if idx >= 0:
            active_label = (self._control_tabs.tabText(idx) or "").strip().lower()

        for btn in buttons:
            btn.setChecked(bool(active_label) and btn.text().strip().lower() == active_label)

    def _sync_tool_tab_selection(self):
        buttons = getattr(self, "_tool_menu_buttons", None)
        if not buttons:
            return
        for key, btn in buttons.items():
            btn.setChecked(key == (self._active_tool or ""))

    def eventFilter(self, watched, event):
        # Tool changes should happen on explicit click only.
        return super().eventFilter(watched, event)

    def _on_top_feature_button_clicked(self, label: str):
        target = str(label or "").strip().lower()
        if not target:
            return

        # Keep button highlight even when no SWC/control tab is currently available.
        for btn in getattr(self, "_top_feature_buttons", []):
            btn.setChecked(btn.text().strip().lower() == target)

        for i in range(self._control_tabs.count()):
            if (self._control_tabs.tabText(i) or "").strip().lower() == target:
                self._control_tabs.setCurrentIndex(i)
                self._control_tabs.setVisible(self._control_tabs.count() > 0)
                return

        if self._active_tool in ("morphology_editing", "dendrogram", "geometry_editing") and self._active_document() is None:
            self._append_log("Open an SWC file to use editing feature controls.", "INFO")

    def _wrap_control_widget(self, inner: QWidget) -> QWidget:
        key = id(inner)
        existing = self._control_wrappers.get(key)
        if existing is not None:
            return existing

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        area.setMinimumWidth(0)
        area.setMinimumHeight(0)

        host = QWidget()
        host.setMinimumSize(0, 0)
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignTop)
        lay.addWidget(inner)

        area.setWidget(host)
        self._control_wrappers[key] = area
        return area

    def _detach_control_wrapper(self, wrapper: QWidget) -> None:
        for i in range(self._control_tabs.count()):
            if self._control_tabs.widget(i) is wrapper:
                self._control_tabs.removeTab(i)
                break
        wrapper.setParent(None)

    def _show_floating_control_dialog(self, dialog_key: str, title: str, inner: QWidget, *, width: int = 520, height: int = 720) -> None:
        existing = self._floating_control_dialogs.get(dialog_key)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return

        wrapper = self._wrap_control_widget(inner)
        self._detach_control_wrapper(wrapper)

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setSizeGripEnabled(True)
        dialog.setMinimumSize(180, 140)
        dialog.resize(width, height)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(wrapper)

        def _restore() -> None:
            wrapper.setParent(None)
            self._floating_control_dialogs.pop(dialog_key, None)
            if self._active_document() is not None:
                if self._active_tool in ("morphology_editing", "dendrogram"):
                    self._set_control_tabs_for_feature("morphology_editing")
                elif self._active_tool:
                    self._set_control_tabs_for_feature(self._active_tool)
            dialog.deleteLater()

        dialog.finished.connect(lambda _result=0: _restore())
        self._floating_control_dialogs[dialog_key] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _relax_widget_size_constraints(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        try:
            widget.setMinimumSize(0, 0)
        except Exception:
            pass
        try:
            widget.setMaximumSize(16777215, 16777215)
        except Exception:
            pass
        try:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass
        for child in widget.findChildren(QWidget):
            try:
                child.setMinimumSize(0, 0)
            except Exception:
                pass

    def _make_panel_freely_resizable(self, dock: QDockWidget | None) -> None:
        if dock is None:
            return
        try:
            dock.setMinimumSize(24, 24)
        except Exception:
            pass
        try:
            dock.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass
        self._relax_widget_size_constraints(dock.widget())

    # --------------------------------------------------------- Document helpers
    def _active_editor(self) -> EditorTab | None:
        idx = self._canvas_tabs.currentIndex()
        if idx < 0:
            return None
        w = self._canvas_tabs.widget(idx)
        return w if isinstance(w, EditorTab) else None

    def _active_document(self) -> _DocumentState | None:
        ed = self._active_editor()
        if ed is None:
            return None
        return self._documents.get(ed)

    def _editor_mode_for_feature(self) -> str:
        key = (self._active_tool or "").strip().lower()
        if key == "visualization":
            return EditorTab.MODE_VIS
        if key in ("morphology_editing", "dendrogram", "geometry_editing"):
            return EditorTab.MODE_DENDRO
        return EditorTab.MODE_CANVAS

    def _apply_editor_modes(self):
        mode = self._editor_mode_for_feature()
        for doc in self._documents.values():
            doc.editor.set_mode(mode)

    def _clear_active_editor_selection_if_unfocused(self):
        doc = self._active_document()
        if doc is None:
            return
        if str(doc.selected_issue_id or "").strip():
            return
        doc.editor.clear_selection()

    def _refresh_canvas_surface(self):
        if self._active_tool == "batch":
            if self._is_batch_validation_control_active():
                self._batch_canvas.set_mode(EditorTab.MODE_BATCH)
                self._canvas_stack.setCurrentWidget(self._batch_canvas)
            else:
                self._canvas_stack.setCurrentWidget(self._canvas_empty)
            return

        if self._canvas_tabs.count() > 0:
            self._canvas_stack.setCurrentWidget(self._canvas_tabs)
        else:
            self._canvas_stack.setCurrentWidget(self._canvas_empty)

    def _sync_from_active_document(self, *, auto_run_validation: bool):
        doc = self._active_document()
        if doc is None:
            self._df = None
            self._filename = ""
            self._file_path = ""
            self._set_current_file_label_text("")
            self._table_widget.load_dataframe(pd.DataFrame(columns=SWC_COLS), "No SWC loaded")
            self._info_label.setText("No SWC file loaded.")
            self._edit_log_text.setPlainText("No morphology edits recorded for this session yet.")
            self._issue_panel.clear_issues("Open an SWC to populate issues automatically.")
            self._set_issue_status([])
            self._context_inspector.clear()
            self._validation_radii_panel.set_loaded_swc(None, "", "")
            self._validation_index_clean.set_loaded_swc(None)
            self._manual_radii_panel.set_loaded_swc(None, "")
            self._geometry_panel.set_loaded_swc(None)
            self._geometry_panel.set_current_node(None)
            self._batch_tab.set_loaded_swc(None, "", "")
            self._refresh_canvas_surface()
            self._refresh_simplification_panel_state()
            self._refresh_validation_auto_label_panel_state()
            return

        self._df = doc.df
        self._filename = doc.filename
        self._file_path = doc.file_path
        self._set_current_file_label_text(doc.filename)

        n_roots = int((doc.df["parent"] == -1).sum())
        n_soma = int((doc.df["type"] == 1).sum())
        self._table_widget.load_dataframe(doc.df, doc.filename)
        self._update_info_label(doc.df, n_roots, n_soma, filename=doc.filename)
        self._refresh_morph_edit_tab(doc)
        self._validation_radii_panel.set_loaded_swc(doc.df, doc.filename, doc.file_path)
        self._validation_index_clean.set_loaded_swc(doc.df)
        self._manual_radii_panel.set_loaded_swc(doc.df, doc.filename)
        self._geometry_panel.set_loaded_swc(doc.df)
        self._geometry_panel.set_current_node(None)
        self._batch_tab.set_loaded_swc(doc.df, doc.filename, doc.file_path)
        should_auto_run_validation = bool(auto_run_validation and not doc.is_preview and doc.validation_report is None)
        self._validation_tab.load_swc(
            doc.df,
            doc.filename,
            file_path=doc.file_path,
            auto_run=should_auto_run_validation,
        )
        if should_auto_run_validation:
            self._issue_panel.clear_issues("Running validation and issue detectors...")
            self._set_issue_status([])
            self._context_inspector.clear()
            doc.editor.clear_selection()
        self._apply_issue_state(doc)
        self._refresh_canvas_surface()
        self._refresh_simplification_panel_state()
        self._refresh_validation_auto_label_panel_state()
        self._refresh_edit_history_state(doc)

    def _start_morphology_session(self, doc: _DocumentState):
        if doc.is_preview:
            return
        doc.session_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        doc.session_operations = []
        doc.session_seq = 0
        doc.issue_status_overrides = {}
        doc.fixed_issue_count = 0
        doc.pending_resolved_issue_ids = set()
        doc.selected_issue_id = ""
        doc.recovery_path = ""
        doc.history_snapshots = [doc.df.copy()] if isinstance(doc.df, pd.DataFrame) else []
        doc.history_index = len(doc.history_snapshots) - 1
        doc.last_auto_label_result = None
        doc.last_auto_label_options = None
        doc.auto_label_preview_df = None
        doc.auto_label_preview_base_df = None
        doc.editor.set_edit_history_state(False, False)
        if doc is self._active_document():
            self._refresh_morph_edit_tab(doc)

    def _connect_editor_signals(self, editor: EditorTab):
        editor.df_changed.connect(lambda new_df, ed=editor: self._on_editor_df_changed(ed, new_df))
        editor.node_selected.connect(lambda swc_id, ed=editor: self._on_editor_node_selected(ed, swc_id))

    def _push_document_history(self, doc: _DocumentState, df: pd.DataFrame):
        if doc is None or doc.is_preview or not isinstance(df, pd.DataFrame):
            return
        snapshot = df.copy()
        if doc.history_index >= 0 and doc.history_index < len(doc.history_snapshots):
            try:
                if doc.history_snapshots[doc.history_index].equals(snapshot):
                    self._refresh_edit_history_state(doc)
                    return
            except Exception:
                pass
        if doc.history_index < len(doc.history_snapshots) - 1:
            doc.history_snapshots = doc.history_snapshots[: doc.history_index + 1]
        doc.history_snapshots.append(snapshot)
        doc.history_index = len(doc.history_snapshots) - 1
        self._refresh_edit_history_state(doc)

    def _refresh_edit_history_state(self, doc: _DocumentState | None = None):
        row = doc or self._active_document()
        if row is None:
            return
        can_undo = (not row.is_preview) and row.history_index > 0
        can_redo = (not row.is_preview) and row.history_index >= 0 and row.history_index < (len(row.history_snapshots) - 1)
        row.editor.set_edit_history_state(can_undo, can_redo)

    def _restore_document_history(self, doc: _DocumentState, target_index: int, *, direction: str):
        if doc is None or doc.is_preview:
            return False
        if target_index < 0 or target_index >= len(doc.history_snapshots):
            return False
        doc.history_index = int(target_index)
        snapshot = doc.history_snapshots[doc.history_index].copy()
        self._apply_document_dataframe(
            doc,
            snapshot,
            event_title=direction,
            event_summary=f"{direction} one session edit step.",
            event_details=[],
            push_history=False,
            record_type_changes=True,
        )
        self._refresh_edit_history_state(doc)
        self._rerun_active_validation()
        return True

    def _undo_document(self, doc: _DocumentState | None) -> bool:
        if doc is None:
            return False
        return self._restore_document_history(doc, doc.history_index - 1, direction="Undo")

    def _redo_document(self, doc: _DocumentState | None) -> bool:
        if doc is None:
            return False
        return self._restore_document_history(doc, doc.history_index + 1, direction="Redo")

    def _snapshot_log_value(self, key: str, value):
        if value is None:
            return ""
        if key in {"id", "type", "parent"}:
            try:
                return str(int(value))
            except Exception:
                return str(value)
        if key in {"x", "y", "z", "radius"}:
            try:
                return f"{float(value):.6g}"
            except Exception:
                return str(value)
        return str(value)

    def _row_snapshot_for_log(self, row: pd.Series | dict) -> dict[str, str]:
        return {
            "id": self._snapshot_log_value("id", row["id"]),
            "type": self._snapshot_log_value("type", row["type"]),
            "parent": self._snapshot_log_value("parent", row["parent"]),
            "radius": self._snapshot_log_value("radius", row["radius"]),
            "x": self._snapshot_log_value("x", row["x"]),
            "y": self._snapshot_log_value("y", row["y"]),
            "z": self._snapshot_log_value("z", row["z"]),
        }

    def _format_snapshot_fields(self, snap: dict[str, str], keys: list[str]) -> str:
        labels = {
            "id": "id",
            "type": "type",
            "parent": "parent",
            "radius": "radius",
            "x": "x",
            "y": "y",
            "z": "z",
        }
        parts: list[str] = []
        for key in keys:
            val = str((snap or {}).get(key, "")).strip()
            if val == "":
                continue
            parts.append(f"{labels[key]}={val}")
        return ", ".join(parts)

    def _build_session_change_rows(
        self,
        old_df: pd.DataFrame | None,
        new_df: pd.DataFrame | None,
        *,
        id_map: dict[int, int] | None = None,
    ) -> list[dict]:
        if not isinstance(old_df, pd.DataFrame) and not isinstance(new_df, pd.DataFrame):
            return []

        old_lookup = {}
        new_lookup = {}
        if isinstance(old_df, pd.DataFrame) and not old_df.empty:
            old_lookup = {
                int(row["id"]): self._row_snapshot_for_log(row)
                for _, row in old_df.loc[:, ["id", "type", "x", "y", "z", "radius", "parent"]].iterrows()
            }
        if isinstance(new_df, pd.DataFrame) and not new_df.empty:
            new_lookup = {
                int(row["id"]): self._row_snapshot_for_log(row)
                for _, row in new_df.loc[:, ["id", "type", "x", "y", "z", "radius", "parent"]].iterrows()
            }

        change_rows: list[dict] = []
        used_old: set[int] = set()
        used_new: set[int] = set()
        compare_keys = ["id", "type", "parent", "radius", "x", "y", "z"]

        if isinstance(id_map, dict) and id_map:
            for old_id, new_id in sorted((int(k), int(v)) for k, v in id_map.items()):
                old_snap = old_lookup.get(old_id)
                new_snap = new_lookup.get(new_id)
                if old_snap is None or new_snap is None:
                    continue
                used_old.add(old_id)
                used_new.add(new_id)
                changed_keys = [key for key in compare_keys if str(old_snap.get(key, "")) != str(new_snap.get(key, ""))]
                if not changed_keys:
                    continue
                change_rows.append(
                    {
                        "node_id": f"{old_id}->{new_id}" if old_id != new_id else str(old_id),
                        "changed_keys": list(changed_keys),
                        "old_values": {key: str(old_snap.get(key, "")) for key in changed_keys},
                        "new_values": {key: str(new_snap.get(key, "")) for key in changed_keys},
                        "old_parameters": self._format_snapshot_fields(old_snap, changed_keys),
                        "new_parameters": self._format_snapshot_fields(new_snap, changed_keys),
                    }
                )

        for nid in sorted(set(old_lookup).intersection(new_lookup)):
            if nid in used_old or nid in used_new:
                continue
            old_snap = old_lookup[nid]
            new_snap = new_lookup[nid]
            used_old.add(nid)
            used_new.add(nid)
            changed_keys = [key for key in compare_keys if str(old_snap.get(key, "")) != str(new_snap.get(key, ""))]
            if not changed_keys:
                continue
            change_rows.append(
                {
                    "node_id": str(nid),
                    "changed_keys": list(changed_keys),
                    "old_values": {key: str(old_snap.get(key, "")) for key in changed_keys},
                    "new_values": {key: str(new_snap.get(key, "")) for key in changed_keys},
                    "old_parameters": self._format_snapshot_fields(old_snap, changed_keys),
                    "new_parameters": self._format_snapshot_fields(new_snap, changed_keys),
                }
            )
        for nid in sorted(set(old_lookup) - used_old):
            old_snap = old_lookup[nid]
            change_rows.append(
                {
                    "node_id": str(nid),
                    "changed_keys": ["id", "type", "parent", "radius", "x", "y", "z"],
                    "old_values": {key: str(old_snap.get(key, "")) for key in ["id", "type", "parent", "radius", "x", "y", "z"]},
                    "new_values": {},
                    "old_parameters": self._format_snapshot_fields(old_snap, ["id", "type", "parent", "radius", "x", "y", "z"]),
                    "new_parameters": "[deleted]",
                }
            )

        for nid in sorted(set(new_lookup) - used_new):
            new_snap = new_lookup[nid]
            change_rows.append(
                {
                    "node_id": str(nid),
                    "changed_keys": ["id", "type", "parent", "radius", "x", "y", "z"],
                    "old_values": {},
                    "new_values": {key: str(new_snap.get(key, "")) for key in ["id", "type", "parent", "radius", "x", "y", "z"]},
                    "old_parameters": "[inserted]",
                    "new_parameters": self._format_snapshot_fields(new_snap, ["id", "type", "parent", "radius", "x", "y", "z"]),
                }
            )

        return change_rows

    def _record_session_operation(
        self,
        doc: _DocumentState,
        *,
        title: str,
        summary: str,
        old_df: pd.DataFrame | None = None,
        new_df: pd.DataFrame | None = None,
        details: list[str] | None = None,
        id_map: dict[int, int] | None = None,
        change_rows: list[dict] | None = None,
    ):
        if doc.is_preview:
            return
        node_changes = list(change_rows or []) if isinstance(change_rows, list) else self._build_session_change_rows(old_df, new_df, id_map=id_map)
        stamped_rows: list[dict] = []
        for row in node_changes:
            doc.session_seq += 1
            stamped_rows.append(
                {
                    "seq": doc.session_seq,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "node_id": str(row.get("node_id", "")),
                    "changed_keys": list(row.get("changed_keys", []) or []),
                    "old_values": dict(row.get("old_values", {}) or {}),
                    "new_values": dict(row.get("new_values", {}) or {}),
                    "old_parameters": str(row.get("old_parameters", "")),
                    "new_parameters": str(row.get("new_parameters", "")),
                }
            )
        doc.session_operations.append(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "title": str(title),
                "summary": str(summary),
                "details": list(details or []),
                "affected_nodes": len(stamped_rows),
                "changes": stamped_rows,
            }
        )
        if doc is self._active_document():
            self._refresh_morph_edit_tab(doc)

    def _record_session_event(
        self,
        doc: _DocumentState,
        *,
        kind: str,
        title: str,
        summary: str,
        details: list[str] | None = None,
    ):
        self._record_session_operation(
            doc,
            title=str(title),
            summary=str(summary),
            old_df=None,
            new_df=None,
            details=list(details or []),
        )

    def _refresh_morph_edit_tab(self, doc: _DocumentState | None = None):
        row = doc or self._active_document()
        if row is None or not row.session_operations:
            self._edit_log_text.setPlainText("No morphology edits recorded for this session yet.")
            return

        lines = [f"Session changes ({row.filename}):"]
        for op in row.session_operations:
            lines.extend(
                [
                    "",
                    f"[{str(op.get('time', ''))}] {str(op.get('title', ''))}",
                    f"Summary: {str(op.get('summary', ''))}",
                    f"Affected nodes: {int(op.get('affected_nodes', 0))}",
                ]
            )
            for detail in list(op.get("details", []) or []):
                lines.append(f"- {detail}")
            changes = list(op.get("changes", []) or [])
            if changes:
                lines.append(f"{'Seq':<5}{'Time':<10}{'NodeID':<14}{'OldParameters':<48}NewParameters")
                for c in changes:
                    lines.append(
                        f"{int(c.get('seq', 0)):<5}"
                        f"{str(c.get('time', '')):<10}"
                        f"{str(c.get('node_id', '')):<14}"
                        f"{str(c.get('old_parameters', '')):<48}"
                        f"{str(c.get('new_parameters', ''))}"
                    )

        self._edit_log_text.setPlainText("\n".join(lines))

    def _finalize_morphology_session(
        self,
        doc: _DocumentState,
        *,
        show_popup: bool,
        source_override: str | None = None,
    ) -> str | None:
        if not doc.session_operations:
            return None

        source = str(source_override or doc.file_path or "")
        if source:
            log_path = morphology_session_log_path(source)
            source_name = os.path.basename(source)
        else:
            source_name = doc.filename or "swc"
            log_path = Path.cwd() / f"{Path(source_name).stem}_morphology_session_log.txt"

        txt = format_morphology_session_log_text(
            source_file=source_name,
            session_started=doc.session_started_at or "",
            session_ended=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            operations=list(doc.session_operations),
        )
        out_path = write_text_report(log_path, txt)
        self._append_log(f"Session report written: {out_path}", "INFO")
        if show_popup:
            try:
                ReportPopupDialog.open_report(self, title="SWC Session Report", report_path=out_path)
            except Exception as e:  # noqa: BLE001
                self._append_log(f"Could not open session report popup: {e}", "WARN")

        doc.session_operations = []
        doc.session_seq = 0
        if doc is self._active_document():
            self._refresh_morph_edit_tab(doc)
        return str(out_path)

    def _document_has_unsaved_edits(self, doc: _DocumentState) -> bool:
        if doc is None:
            return False
        original = doc.original_df
        current = doc.df
        if not isinstance(current, pd.DataFrame):
            return False
        if not isinstance(original, pd.DataFrame):
            return True
        try:
            return not original.equals(current)
        except Exception:  # noqa: BLE001
            return True

    def _recovery_directory(self) -> Path:
        path = Path.home() / ".swc_studio" / "recovery"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _recovery_path_for_document(self, doc: _DocumentState) -> Path:
        if str(doc.recovery_path or "").strip():
            return Path(doc.recovery_path)
        base_name = Path(doc.file_path).stem if str(doc.file_path or "").strip() else Path(doc.filename or "swc").stem
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self._recovery_directory() / f"{base_name}_recovery_{ts}.swc"
        doc.recovery_path = str(path)
        return path

    def _write_recovery_copy(self, doc: _DocumentState):
        if doc is None or doc.is_preview or doc.df is None or doc.df.empty:
            return
        if not self._document_has_unsaved_edits(doc):
            return
        recovery_path = self._recovery_path_for_document(doc)
        self._write_swc_file(str(recovery_path), doc.df)

    def _clear_recovery_copy(self, doc: _DocumentState):
        if doc is None:
            return
        recovery_path = Path(doc.recovery_path) if str(doc.recovery_path or "").strip() else None
        doc.recovery_path = ""
        if recovery_path is None:
            return
        try:
            if recovery_path.exists():
                recovery_path.unlink()
        except Exception as e:  # noqa: BLE001
            self._append_log(f"Could not remove recovery copy {recovery_path}: {e}", "WARN")

    def _next_closed_output_path(self, doc: _DocumentState) -> Path:
        base = Path(doc.file_path) if str(doc.file_path or "").strip() else Path.cwd() / (doc.filename or "swc")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = output_dir_for_file(base)
        cand = out_dir / f"{base.stem}_closed_{ts}.swc"
        i = 1
        while cand.exists():
            cand = out_dir / f"{base.stem}_closed_{ts}_{i}.swc"
            i += 1
        return cand

    def _plan_document_close(self, doc: _DocumentState, *, app_closing: bool) -> dict | None:
        if doc is None or doc.is_preview:
            return {"kind": "close"}

        filename = doc.filename or "SWC"
        has_unsaved_edits = self._document_has_unsaved_edits(doc)
        has_session_log = bool(doc.session_operations)
        title = "Exit SWC-Studio" if app_closing else "Close SWC File"

        if has_unsaved_edits:
            default_output_path = self._next_closed_output_path(doc)
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle(title)
            box.setText(f"Close {filename}?")
            box.setInformativeText(
                "Unsaved changes will be saved to:\n"
                f"{default_output_path}\n\n"
                "Or choose a different location."
            )
            save_default_btn = box.addButton("Save To Default Location", QMessageBox.AcceptRole)
            change_location_btn = box.addButton("Change Save Location...", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(save_default_btn)
            box.exec()

            clicked = box.clickedButton()
            if clicked is save_default_btn:
                return {"kind": "write_close_copy", "output_path": str(default_output_path)}
            if clicked is change_location_btn:
                path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Changed SWC Copy",
                    str(default_output_path),
                    "SWC Files (*.swc);;All Files (*)",
                )
                if not path:
                    self._append_log("Close cancelled while choosing a save location.", "INFO")
                    return None
                return {"kind": "write_close_copy", "output_path": str(path)}
            self._append_log(f"Close cancelled for {filename}.", "INFO")
            return None

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(f"Close {filename}?")
        if has_session_log:
            box.setInformativeText(
                "No new SWC copy will be saved.\n"
                "The session log will be written."
            )
        else:
            box.setInformativeText("No unsaved changes.")
        close_btn = box.addButton("Close", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(close_btn)
        box.exec()
        if box.clickedButton() is not close_btn:
            self._append_log(f"Close cancelled for {filename}.", "INFO")
            return None
        if has_session_log:
            return {"kind": "close_and_log"}
        return {"kind": "close"}

    def _apply_document_close_plan(self, doc: _DocumentState, plan: dict) -> bool:
        if doc is None:
            return True

        kind = str((plan or {}).get("kind", "close"))
        output_path = str((plan or {}).get("output_path", "") or "").strip()

        try:
            if kind == "write_close_copy":
                if not output_path:
                    raise ValueError("Missing output path for closing copy.")
                self._write_swc_file(output_path, doc.df)
                self._append_log(f"Changed SWC copy saved to: {output_path}", "INFO")
                self._finalize_morphology_session(doc, show_popup=False, source_override=output_path)
            elif kind == "close_and_log":
                self._finalize_morphology_session(doc, show_popup=False)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Close Failed",
                f"Could not finish closing {doc.filename or 'SWC'}.\n\n{e}",
            )
            self._append_log(f"Close failed for {doc.filename or 'SWC'}: {e}", "ERROR")
            return False

        self._clear_recovery_copy(doc)
        return True

    # --------------------------------------------------------- Controls per feature
    def _is_simplification_preview(self, doc: _DocumentState | None) -> bool:
        return bool(doc and doc.is_preview and doc.preview_kind == "simplification")

    def _source_document_for(self, doc: _DocumentState | None) -> _DocumentState | None:
        if doc is None:
            return None
        if self._is_simplification_preview(doc):
            src_editor = doc.source_editor or self._simplify_source_by_preview.get(doc.editor)
            if src_editor is None:
                return None
            return self._documents.get(src_editor)
        if self._is_validation_auto_label_preview(doc):
            src_editor = doc.source_editor or self._auto_label_source_by_preview.get(doc.editor)
            if src_editor is None:
                return None
            return self._documents.get(src_editor)
        return doc

    def _active_source_document(self) -> _DocumentState | None:
        return self._source_document_for(self._active_document())

    def _simplification_log_payload(
        self,
        source_doc: _DocumentState,
        result: dict,
        *,
        output_path: str | None,
    ) -> dict:
        return {
            "mode": "gui",
            "input_path": str(source_doc.file_path or source_doc.filename),
            "output_path": str(output_path or ""),
            "original_node_count": int(result.get("original_node_count", 0)),
            "new_node_count": int(result.get("new_node_count", 0)),
            "reduction_percent": float(result.get("reduction_percent", 0.0)),
            "params_used": dict(result.get("params_used", {})),
            "protected_counts": dict(result.get("protected_counts", {})),
            "removed_node_ids": list(result.get("removed_node_ids", [])),
        }

    def _write_simplification_log(self, payload: dict) -> str:
        input_path = str(payload.get("input_path", "") or "").strip()
        output_path = str(payload.get("output_path", "") or "").strip()

        if input_path:
            log_path = simplification_log_path_for_file(input_path)
        elif output_path:
            log_path = simplification_log_path_for_file(output_path)
        else:
            base = Path.cwd() / "simplified_preview.swc"
            log_path = simplification_log_path_for_file(base)

        return write_text_report(log_path, format_simplification_report_text(payload))

    def _resolve_simplification_context(self) -> tuple[_DocumentState | None, _DocumentState | None, dict | None]:
        active = self._active_document()
        if active is None:
            return None, None, None

        if self._is_simplification_preview(active):
            source_doc = self._source_document_for(active)
            result = self._simplify_result_by_preview.get(active.editor)
            return source_doc, active, result

        preview_editor = self._simplify_preview_by_source.get(active.editor)
        if preview_editor is None:
            return active, None, None

        preview_doc = self._documents.get(preview_editor)
        result = self._simplify_result_by_preview.get(preview_editor)
        return active, preview_doc, result

    def _remove_simplification_preview(self, preview_editor: EditorTab, *, switch_to_source: bool):
        preview_doc = self._documents.get(preview_editor)
        source_editor = self._simplify_source_by_preview.pop(preview_editor, None)
        if source_editor is not None:
            if self._simplify_preview_by_source.get(source_editor) is preview_editor:
                self._simplify_preview_by_source.pop(source_editor, None)
        self._simplify_result_by_preview.pop(preview_editor, None)

        if preview_doc is not None:
            self._documents.pop(preview_editor, None)

        idx = self._canvas_tabs.indexOf(preview_editor)
        if idx >= 0:
            self._canvas_tabs.removeTab(idx)

        float_win = self._detached_windows.pop(preview_editor, None)
        if float_win is not None:
            try:
                float_win.editor_closing.disconnect(self._on_detached_editor_closing)
            except Exception:
                pass
            float_win.close()

        if switch_to_source and source_editor is not None:
            src_idx = self._canvas_tabs.indexOf(source_editor)
            if src_idx >= 0:
                self._canvas_tabs.setCurrentIndex(src_idx)

    def _refresh_simplification_panel_state(self):
        source_doc = self._active_source_document()
        result = None if source_doc is None else source_doc.last_simplification_result
        if source_doc is None or not isinstance(result, dict):
            self._simplification_panel.set_preview_state(False, None, None)
            return
        summary = {
            "original_node_count": int(result.get("original_node_count", 0)),
            "new_node_count": int(result.get("new_node_count", 0)),
            "reduction_percent": float(result.get("reduction_percent", 0.0)),
            "params_used": dict(result.get("params_used", {})),
        }
        self._simplification_panel.set_preview_state(
            False,
            summary,
            None,
        )

    def _on_simplification_process_requested(self, config_overrides: dict):
        source_doc = self._active_source_document()
        if source_doc is None or source_doc.df is None or source_doc.df.empty:
            self._append_log("Simplification: no active SWC document.", "WARN")
            return

        try:
            result = simplify_dataframe(source_doc.df, config_overrides=dict(config_overrides or {}))
        except Exception as e:  # noqa: BLE001
            self._append_log(f"Simplification failed: {e}", "ERROR")
            return

        simplified_df = result.get("dataframe")
        if not isinstance(simplified_df, pd.DataFrame) or simplified_df.empty:
            self._append_log("Simplification produced empty output.", "WARN")
            return

        payload = self._simplification_log_payload(source_doc, result, output_path=None)
        source_doc.last_simplification_result = dict(payload)
        self._apply_document_dataframe(
            source_doc,
            simplified_df,
            event_title="Simplification",
            event_summary=(
                f"Simplified the current SWC from {payload.get('original_node_count', 0)} "
                f"to {payload.get('new_node_count', 0)} nodes."
            ),
            event_details=[
                f"Reduction (%): {float(payload.get('reduction_percent', 0.0)):.2f}",
                f"Removed nodes: {len(list(payload.get('removed_node_ids', []) or []))}",
                f"Protected counts: {dict(payload.get('protected_counts', {}))}",
                f"Parameters used: {dict(payload.get('params_used', {}))}",
            ],
        )
        self._rerun_active_validation()
        self._append_log(
            "Simplification applied: "
            f"{payload.get('original_node_count', 0)} -> {payload.get('new_node_count', 0)} "
            f"({payload.get('reduction_percent', 0.0):.2f}%).",
            "INFO",
        )
        self._refresh_simplification_panel_state()

    def _is_validation_auto_label_preview(self, doc: _DocumentState | None) -> bool:
        return bool(doc and doc.is_preview and doc.preview_kind == "validation_auto_label")

    def _resolve_validation_auto_label_context(
        self,
    ) -> tuple[_DocumentState | None, _DocumentState | None, dict | None]:
        active = self._active_document()
        if active is None:
            return None, None, None

        if self._is_validation_auto_label_preview(active):
            source_doc = self._source_document_for(active)
            result = self._auto_label_result_by_preview.get(active.editor)
            return source_doc, active, result

        preview_editor = self._auto_label_preview_by_source.get(active.editor)
        if preview_editor is None:
            return active, None, None

        preview_doc = self._documents.get(preview_editor)
        result = self._auto_label_result_by_preview.get(preview_editor)
        return active, preview_doc, result

    def _remove_validation_auto_label_preview(self, preview_editor: EditorTab, *, switch_to_source: bool):
        preview_doc = self._documents.get(preview_editor)
        source_editor = self._auto_label_source_by_preview.pop(preview_editor, None)
        if source_editor is not None:
            if self._auto_label_preview_by_source.get(source_editor) is preview_editor:
                self._auto_label_preview_by_source.pop(source_editor, None)
        self._auto_label_result_by_preview.pop(preview_editor, None)

        if preview_doc is not None:
            self._documents.pop(preview_editor, None)

        idx = self._canvas_tabs.indexOf(preview_editor)
        if idx >= 0:
            self._canvas_tabs.removeTab(idx)

        float_win = self._detached_windows.pop(preview_editor, None)
        if float_win is not None:
            try:
                float_win.editor_closing.disconnect(self._on_detached_editor_closing)
            except Exception:
                pass
            float_win.close()

        if switch_to_source and source_editor is not None:
            src_idx = self._canvas_tabs.indexOf(source_editor)
            if src_idx >= 0:
                self._canvas_tabs.setCurrentIndex(src_idx)

    def _auto_label_result_to_dataframe(self, result: object) -> pd.DataFrame:
        rows = list(getattr(result, "rows", []))
        types = list(getattr(result, "types", []))
        radii = list(getattr(result, "radii", []))
        if not rows:
            return pd.DataFrame(columns=SWC_COLS)
        data = []
        for i, row in enumerate(rows):
            data.append(
                {
                    "id": int(row.get("id", 0)),
                    "type": int(types[i] if i < len(types) else row.get("type", 0)),
                    "x": float(row.get("x", 0.0)),
                    "y": float(row.get("y", 0.0)),
                    "z": float(row.get("z", 0.0)),
                    "radius": float(radii[i] if i < len(radii) else row.get("radius", 0.0)),
                    "parent": int(row.get("parent", -1)),
                }
            )
        return pd.DataFrame(data, columns=SWC_COLS)

    def _merge_auto_label_types_only(self, base_df: pd.DataFrame, labeled_df: pd.DataFrame) -> pd.DataFrame:
        """Keep original geometry/radius columns and only replace type assignments."""
        if not isinstance(base_df, pd.DataFrame) or base_df.empty:
            return pd.DataFrame(columns=SWC_COLS)
        out = base_df.copy()
        if not isinstance(labeled_df, pd.DataFrame) or labeled_df.empty:
            return out
        type_map = {
            int(row["id"]): int(row["type"])
            for _, row in labeled_df.loc[:, ["id", "type"]].iterrows()
        }
        out["type"] = out["id"].astype(int).map(type_map).fillna(out["type"]).astype(int)
        return out

    def _refresh_validation_auto_label_panel_state(self):
        doc = self._active_source_document()
        if doc is None or not isinstance(doc.last_auto_label_result, dict):
            self._validation_auto_label_panel.set_preview_state(False, None)
            return
        self._validation_auto_label_panel.set_preview_state(False, doc.last_auto_label_result)

    def _on_validation_auto_label_process_requested(self, options: object):
        source_doc = self._active_source_document()
        if source_doc is None or source_doc.df is None or source_doc.df.empty:
            self._append_log("Validation Auto Label Editing: no active SWC document.", "WARN")
            self._validation_auto_label_panel.set_status_text("No active SWC loaded.")
            return

        tmp_fd, tmp_in = tempfile.mkstemp(prefix="swctools_auto_label_", suffix=".swc")
        os.close(tmp_fd)
        tmp_path = Path(tmp_in)
        try:
            self._write_swc_file(str(tmp_path), source_doc.df)
            result_obj = run_validation_auto_typing_file(
                str(tmp_path),
                options=options,
                write_output=False,
                write_log=False,
            )
        except Exception as e:  # noqa: BLE001
            self._append_log(f"Validation Auto Label Editing failed: {e}", "ERROR")
            self._validation_auto_label_panel.set_status_text(f"Auto Label Editing failed:\n{e}")
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

        preview_df = self._auto_label_result_to_dataframe(result_obj)
        if preview_df.empty:
            self._append_log("Validation Auto Label Editing produced empty output.", "WARN")
            self._validation_auto_label_panel.set_status_text("Auto Label Editing output is empty.")
            return
        preview_df = self._merge_auto_label_types_only(source_doc.df, preview_df)

        opts = options
        opts_dict = {
            "soma": bool(getattr(opts, "soma", False)),
            "axon": bool(getattr(opts, "axon", False)),
            "apic": bool(getattr(opts, "apic", False)),
            "basal": bool(getattr(opts, "basal", False)),
            "rad": bool(getattr(opts, "rad", False)),
        }
        result_payload = {
            "input_file": str(source_doc.file_path or source_doc.filename),
            "nodes_total": int(getattr(result_obj, "nodes_total", 0)),
            "type_changes": int(getattr(result_obj, "type_changes", 0)),
            "radius_changes": 0,
            "out_type_counts": dict(getattr(result_obj, "out_type_counts", {}) or {}),
            "change_details": [
                line
                for line in list(getattr(result_obj, "change_details", []) or [])
                if "radius_changes:" not in str(line).lower()
                and "old_radius=" not in str(line).lower()
                and "new_radius=" not in str(line).lower()
            ],
            "options": opts_dict,
            "log_path": "",
        }
        source_doc.last_auto_label_options = dict(opts_dict)
        source_doc.last_auto_label_result = dict(result_payload)

        out_counts = dict(result_payload.get("out_type_counts", {}))
        event_details = [
            f"Input: {source_doc.file_path or source_doc.filename}",
            f"Nodes: {int(result_payload.get('nodes_total', 0))}",
            f"Type changes: {int(result_payload.get('type_changes', 0))}",
            (
                "Out types (1/2/3/4): "
                f"{out_counts.get(1, 0)}/{out_counts.get(2, 0)}/{out_counts.get(3, 0)}/{out_counts.get(4, 0)}"
            ),
        ]
        self._apply_document_dataframe(
            source_doc,
            preview_df.copy(),
            event_title="Validation Auto Label Editing Run",
            event_summary=(
                "Applied auto label editing to current SWC; "
                f"type_changes={int(result_payload.get('type_changes', 0))}"
            ),
            event_details=event_details,
        )
        source_doc.auto_label_preview_base_df = None
        source_doc.auto_label_preview_df = None
        self._validation_auto_label_panel.set_preview_state(False, result_payload)
        self._rerun_active_validation()
        self._append_log(
            "Validation Auto Label Editing applied to current canvas: "
            f"nodes={result_payload['nodes_total']}, "
            f"type_changes={result_payload['type_changes']}, "
            f"radius_changes={result_payload['radius_changes']}",
            "INFO",
        )

    def _write_validation_auto_label_log(
        self,
        source_doc: _DocumentState,
        result: dict,
        *,
        output_path: str,
    ) -> str:
        out_p = Path(output_path)
        out_counts = dict(result.get("out_type_counts", {}))
        per_file = [
            f"{Path(source_doc.filename or 'swc').name}: "
            f"nodes={int(result.get('nodes_total', 0))}, "
            f"type_changes={int(result.get('type_changes', 0))}, "
            f"radius_changes={int(result.get('radius_changes', 0))}, "
            f"out_types(soma/axon/basal/apic)="
            f"{out_counts.get(1, 0)}/{out_counts.get(2, 0)}/{out_counts.get(3, 0)}/{out_counts.get(4, 0)}"
        ]
        payload = {
            "folder": str(out_p.parent),
            "out_dir": str(out_p.parent),
            "zip_path": None,
            "files_total": 1,
            "files_processed": 1,
            "files_failed": 0,
            "total_nodes": int(result.get("nodes_total", 0)),
            "total_type_changes": int(result.get("type_changes", 0)),
            "total_radius_changes": int(result.get("radius_changes", 0)),
            "failures": [],
            "per_file": per_file,
            "change_details": [],
        }
        source_path = str(source_doc.file_path or "").strip()
        log_path = auto_typing_log_path_for_file(source_path or out_p)
        return write_text_report(log_path, format_auto_typing_report_text(payload))

    def _on_manual_radii_apply_requested(self, node_id: int, new_radius: float):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Manual Radii: no active SWC document.", "WARN")
            return
        mask = doc.df["id"].astype(int) == int(node_id)
        if not bool(mask.any()):
            self._append_log(f"Manual Radii: node {int(node_id)} is no longer present.", "WARN")
            self._manual_radii_panel.clear_selection()
            return
        old_radius = float(doc.df.loc[mask, "radius"].iloc[0])
        target_radius = float(new_radius)
        if float(old_radius) == float(target_radius):
            self._append_log(f"Manual Radii: node {int(node_id)} already has radius {target_radius:.6g}.", "INFO")
            return

        new_df = doc.df.copy()
        new_df.loc[mask, "radius"] = target_radius
        node_type = int(new_df.loc[mask, "type"].iloc[0])
        self._apply_document_dataframe(
            doc,
            new_df,
            event_title="Manual Radius Edit",
            event_summary=f"Updated node {int(node_id)} radius from {old_radius:.6g} to {target_radius:.6g}.",
            event_details=[],
            record_type_changes=False,
        )
        self._manual_radii_panel.set_selected_node(int(node_id))
        self._append_log(
            f"Manual Radii applied: node {int(node_id)} {old_radius:.6g} -> {target_radius:.6g}.",
            "INFO",
        )
        self._rerun_active_validation()

    def _on_validation_radii_apply_requested(self, result: object):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Auto Radii Editing: no active SWC document.", "WARN")
            return
        payload = dict(result or {})
        new_df = payload.get("dataframe")
        if not isinstance(new_df, pd.DataFrame) or new_df.empty:
            self._append_log("Auto Radii Editing produced no dataframe output.", "WARN")
            return
        total_changes = int(payload.get("changes", 0))
        passes_used = int(payload.get("passes", 0))
        new_df_final = new_df.loc[:, SWC_COLS].copy()
        change_details = list(payload.get("change_details", []) or [])
        change_rows: list[dict] = []
        for row in change_details:
            node_id = int(row.get("node_id", -1))
            if node_id < 0:
                continue
            change_rows.append(
                {
                    "node_id": str(node_id),
                    "changed_keys": ["radius"],
                    "old_values": {"radius": f"{float(row.get('old_radius', 0.0)):.10g}"},
                    "new_values": {"radius": f"{float(row.get('new_radius', 0.0)):.10g}"},
                    "old_parameters": f"radius={float(row.get('old_radius', 0.0)):.10g}",
                    "new_parameters": f"radius={float(row.get('new_radius', 0.0)):.10g}",
                }
            )
        self._apply_document_dataframe(
            doc,
            new_df_final,
            event_title="Auto Radii Editing",
            event_summary=f"Applied automatic radii cleaning to current SWC; passes={passes_used}; radius_changes={total_changes}.",
            event_details=[],
            record_type_changes=False,
            change_rows=change_rows,
        )
        self._append_log(
            f"Auto Radii Editing applied to current SWC: radius_changes={total_changes}.",
            "INFO",
        )
        self._rerun_active_validation()

    def _on_geometry_selection_preview_changed(self, node_ids: object, visibility_mode: str, auto_zoom: bool):
        doc = self._active_document()
        if doc is None:
            return
        ids = [int(v) for v in list(node_ids or [])]
        if ids:
            doc.editor.set_geometry_selection(ids, visibility_mode)
            if auto_zoom:
                doc.editor.zoom_to_node_ids(ids)
        else:
            doc.editor.clear_geometry_selection()

    def _on_geometry_focus_requested(self, swc_id: int):
        doc = self._active_document()
        if doc is None:
            return
        doc.editor.focus_node(int(swc_id))
        self._geometry_panel.set_current_node(int(swc_id))

    def _apply_geometry_dataframe(
        self,
        doc: _DocumentState,
        new_df: pd.DataFrame,
        *,
        event_title: str,
        event_summary: str,
        event_details: list[str],
        focus_node_id: int | None = None,
    ):
        self._apply_document_dataframe(
            doc,
            new_df,
            event_title=event_title,
            event_summary=event_summary,
            event_details=event_details,
            record_type_changes=False,
        )
        if focus_node_id is not None:
            self._geometry_panel.set_current_node(int(focus_node_id))
            doc.editor.focus_node(int(focus_node_id))
        self._rerun_active_validation()

    def _on_geometry_move_selection_requested(self, node_ids: object, anchor_id: int, x: float, y: float, z: float):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Geometry Editing: no active SWC document.", "WARN")
            return
        try:
            selected_node_ids = [int(v) for v in list(node_ids or [])]
            if not selected_node_ids:
                raise ValueError("No selected nodes to move.")
            row = doc.df.loc[doc.df["id"].astype(int) == int(anchor_id)].iloc[0]
            old_xyz = (float(row["x"]), float(row["y"]), float(row["z"]))
            new_df = move_selection_by_anchor_absolute(doc.df, selected_node_ids, int(anchor_id), float(x), float(y), float(z))
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"Geometry Editing: {exc}", "WARN")
            return
        self._apply_geometry_dataframe(
            doc,
            new_df,
            event_title="Move Selection",
            event_summary=f"Moved {len(selected_node_ids)} selected node(s) using anchor {int(anchor_id)}.",
            event_details=[
                f"Anchor node ID: {int(anchor_id)}",
                f"Moved selected node count: {len(selected_node_ids)}",
                f"Old XYZ: ({old_xyz[0]:.5g}, {old_xyz[1]:.5g}, {old_xyz[2]:.5g})",
                f"New XYZ: ({float(x):.5g}, {float(y):.5g}, {float(z):.5g})",
            ],
            focus_node_id=int(anchor_id),
        )
        self._append_log(f"Geometry Editing: moved {len(selected_node_ids)} selected node(s).", "INFO")

    def _on_geometry_reconnect_requested(self, source_id: int, target_id: int):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Geometry Editing: no active SWC document.", "WARN")
            return
        try:
            end_row = doc.df.loc[doc.df["id"].astype(int) == int(target_id)].iloc[0]
            old_parent = int(end_row["parent"])
            new_df = reconnect_branch(doc.df, int(source_id), int(target_id))
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"Geometry Editing: {exc}", "WARN")
            return
        self._geometry_panel.clear_all_selections()
        self._geometry_panel.set_current_node(None)
        self._apply_geometry_dataframe(
            doc,
            new_df,
            event_title="Reconnect Branch",
            event_summary=f"Connected end node {int(target_id)} to start node {int(source_id)}.",
            event_details=[
                f"Start node ID: {int(source_id)}",
                f"End node ID: {int(target_id)}",
                f"End node old parent ID: {old_parent}",
                f"End node new parent ID: {int(source_id)}",
                "Node IDs preserved; no automatic renumbering.",
            ],
            focus_node_id=None,
        )
        self._append_log(
            f"Geometry Editing: connected end node {int(target_id)} to start node {int(source_id)}.",
            "INFO",
        )

    def _on_geometry_disconnect_requested(self, source_id: int, target_id: int):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Geometry Editing: no active SWC document.", "WARN")
            return
        try:
            parent_by_id = {
                int(row["id"]): int(row["parent"])
                for _, row in doc.df[["id", "parent"]].iterrows()
            }
            path = path_between_nodes(doc.df, int(source_id), int(target_id))
            if len(path) < 2:
                raise ValueError("Start and end nodes are not connected.")
            disconnected_children: list[int] = []
            old_edges: list[str] = []
            for left, right in zip(path[:-1], path[1:]):
                left = int(left)
                right = int(right)
                if int(parent_by_id.get(left, -1)) == right:
                    disconnected_children.append(left)
                    old_edges.append(f"{right} -> {left}")
                elif int(parent_by_id.get(right, -1)) == left:
                    disconnected_children.append(right)
                    old_edges.append(f"{left} -> {right}")
                else:
                    raise ValueError("Encountered a non-parent-child step while disconnecting the selected path.")
            new_df = disconnect_branch(doc.df, int(source_id), int(target_id))
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"Geometry Editing: {exc}", "WARN")
            return
        self._geometry_panel.clear_all_selections()
        self._geometry_panel.set_current_node(None)
        self._apply_geometry_dataframe(
            doc,
            new_df,
            event_title="Disconnect Branch",
            event_summary=f"Disconnected the path between {int(source_id)} and {int(target_id)}.",
            event_details=[
                f"Start node ID: {int(source_id)}",
                f"End node ID: {int(target_id)}",
                f"Path nodes: {', '.join(str(v) for v in path)}",
                f"Disconnected child node IDs: {', '.join(str(v) for v in disconnected_children)}",
                f"Disconnected edges: {', '.join(old_edges)}",
                "New parent IDs on disconnected child nodes: -1",
                "Node IDs preserved; no automatic renumbering.",
            ],
            focus_node_id=None,
        )
        self._append_log(
            f"Geometry Editing: disconnected the path between {int(source_id)} and {int(target_id)}.",
            "INFO",
        )

    def _on_geometry_delete_node_requested(self, node_id: int, reconnect_children: bool):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Geometry Editing: no active SWC document.", "WARN")
            return
        try:
            row = doc.df.loc[doc.df["id"].astype(int) == int(node_id)].iloc[0]
            child_count = int((doc.df["parent"].astype(int) == int(node_id)).sum())
            new_df = geometry_delete_node(doc.df, int(node_id), reconnect_children=bool(reconnect_children))
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"Geometry Editing: {exc}", "WARN")
            return
        self._geometry_panel.clear_all_selections()
        self._geometry_panel.set_current_node(None)
        event_title = "Delete Node" if not reconnect_children else "Delete Node + Reconnect Children"
        self._apply_geometry_dataframe(
            doc,
            new_df,
            event_title=event_title,
            event_summary=f"Deleted node {int(node_id)}.",
            event_details=[
                f"Node ID: {int(node_id)}",
                f"Type: {label_for_type(int(row['type']))} ({int(row['type'])})",
                f"Child count: {child_count}",
                f"Reconnect children: {'yes' if reconnect_children else 'no'}",
                "Remaining node IDs preserved; no automatic renumbering.",
            ],
            focus_node_id=None,
        )
        self._append_log(f"Geometry Editing: deleted node {int(node_id)}.", "INFO")

    def _on_geometry_delete_subtree_requested(self, root_id: int):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Geometry Editing: no active SWC document.", "WARN")
            return
        try:
            subtree_size = int(len(subtree_node_ids(doc.df, int(root_id))))
            parent_row = doc.df.loc[doc.df["id"].astype(int) == int(root_id)].iloc[0]
            parent_id = int(parent_row["parent"])
            new_df = geometry_delete_subtree(doc.df, int(root_id))
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"Geometry Editing: {exc}", "WARN")
            return
        self._geometry_panel.clear_all_selections()
        self._geometry_panel.set_current_node(None)
        self._apply_geometry_dataframe(
            doc,
            new_df,
            event_title="Delete Subtree",
            event_summary=f"Deleted subtree rooted at node {int(root_id)}.",
            event_details=[
                f"Subtree root ID: {int(root_id)}",
                f"Removed node count: {subtree_size}",
                "Remaining node IDs preserved; no automatic renumbering.",
            ],
            focus_node_id=None,
        )
        self._append_log(f"Geometry Editing: deleted subtree rooted at node {int(root_id)}.", "INFO")

    def _on_geometry_insert_node_requested(self, start_id: int, end_id: int, x: float, y: float, z: float):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Geometry Editing: no active SWC document.", "WARN")
            return
        try:
            end_row = None
            if int(end_id) >= 0:
                end_row = doc.df.loc[doc.df["id"].astype(int) == int(end_id)].iloc[0]
            inserted_node_id = int(doc.df["id"].astype(int).max()) + 1
            new_df = insert_node_between(doc.df, int(start_id), int(end_id), x=float(x), y=float(y), z=float(z))
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"Geometry Editing: {exc}", "WARN")
            return
        self._geometry_panel.clear_all_selections()
        self._geometry_panel.set_current_node(None)
        self._apply_geometry_dataframe(
            doc,
            new_df,
            event_title="Insert Node",
            event_summary=(
                f"Inserted a node between {int(start_id)} and {int(end_id)}."
                if int(end_id) >= 0
                else f"Inserted a child node under {int(start_id)}."
            ),
            event_details=[
                f"Start node ID: {int(start_id)}",
                f"End node ID: {int(end_id)}" if int(end_id) >= 0 else "End node ID: None",
                f"Inserted node ID: {inserted_node_id}",
                (
                    f"End node type: {label_for_type(int(end_row['type']))} ({int(end_row['type'])})"
                    if end_row is not None
                    else "Inserted node has no child; end node was not provided."
                ),
                f"Inserted XYZ: ({float(x):.5g}, {float(y):.5g}, {float(z):.5g})",
                "Existing node IDs preserved; inserted node uses max(existing ID)+1.",
            ],
            focus_node_id=None,
        )
        self._append_log(
            (
                f"Geometry Editing: inserted a node between {int(start_id)} and {int(end_id)}."
                if int(end_id) >= 0
                else f"Geometry Editing: inserted a child node under {int(start_id)}."
            ),
            "INFO",
        )

    def _set_control_tabs_for_feature(self, feature: str):
        """Show only control tabs relevant to the active feature."""
        key = (feature or "").strip().lower()
        previous_label = ""
        if self._control_tabs.count() > 0 and self._control_tabs.currentIndex() >= 0:
            previous_label = self._control_tabs.tabText(self._control_tabs.currentIndex()).strip().lower()
        while self._control_tabs.count() > 0:
            self._control_tabs.removeTab(0)
        self._control_tabs.tabBar().setVisible(False)

        current_idx = -1

        if key in ("", "none"):
            self._refresh_top_feature_buttons()
            return

        if key == "batch":
            self._control_tabs.addTab(self._wrap_control_widget(self._batch_tab.split_tab_widget()), "Split")
            self._control_tabs.addTab(self._wrap_control_widget(self._batch_tab.validation_tab_widget()), "Validation")
            self._control_tabs.addTab(self._wrap_control_widget(self._batch_tab.auto_tab_widget()), "Auto Label Editing")
            self._control_tabs.addTab(self._wrap_control_widget(self._batch_tab.radii_tab_widget()), "Radii Cleaning")
            self._control_tabs.addTab(self._wrap_control_widget(self._batch_tab.simplify_tab_widget()), "Simplification")
            self._control_tabs.addTab(self._wrap_control_widget(self._batch_tab.index_clean_tab_widget()), "Index Clean")
            current_idx = 0
        elif key == "validation":
            self._control_tabs.addTab(self._wrap_control_widget(self._validation_tab), "Validation")
            self._control_tabs.addTab(self._wrap_control_widget(self._validation_index_clean), "Index Clean")
            current_idx = {
                "validation": 0,
                "index clean": 1,
            }.get(previous_label, 0)
        elif key in ("morphology_editing", "dendrogram"):
            doc = self._active_document()
            if doc is None:
                self._refresh_top_feature_buttons()
                self._on_control_tab_changed(-1)
                return
            self._control_tabs.addTab(self._wrap_control_widget(doc.controls), "Manual Label Editing")
            self._control_tabs.addTab(self._wrap_control_widget(self._validation_auto_label_panel), "Auto Label Editing")
            self._control_tabs.addTab(self._wrap_control_widget(self._manual_radii_panel), "Manual Radii Editing")
            self._control_tabs.addTab(self._wrap_control_widget(self._validation_radii_panel), "Auto Radii Editing")
            current_idx = {
                "manual label editing": 0,
                "auto label editing": 1,
                "manual radii editing": 2,
                "auto radii editing": 3,
            }.get(previous_label, 0)
            self._refresh_simplification_panel_state()
        elif key == "geometry_editing":
            self._control_tabs.addTab(self._wrap_control_widget(self._geometry_panel), "Geometry Editing")
            self._control_tabs.addTab(self._wrap_control_widget(self._simplification_panel), "Simplification")
            current_idx = {
                "geometry editing": 0,
                "simplification": 1,
            }.get(previous_label, 0)
            self._refresh_simplification_panel_state()
        else:
            # default: visualization
            self._control_tabs.addTab(self._wrap_control_widget(self._viz_control), "View Controls")
            current_idx = 0

        if self._control_tabs.count() > 0:
            self._control_tabs.tabBar().setVisible(False)
            current_idx = max(0, min(current_idx, self._control_tabs.count() - 1))
            self._control_tabs.setCurrentIndex(current_idx)
            self._on_control_tab_changed(self._control_tabs.currentIndex())
        else:
            self._control_tabs.tabBar().setVisible(False)
            self._on_control_tab_changed(-1)

        self._refresh_top_feature_buttons()

    # --------------------------------------------------------- Feature routing
    def _activate_feature(self, name: str):
        key = (name or "").strip().lower()
        current = (self._active_tool or "").strip().lower()
        if key and key == current:
            return
        if (
            key != "validation"
            and key != current
            and hasattr(self, "_validation_tab")
            and self._validation_tab.is_running()
        ):
            self._append_log("Validation is running. Wait for completion before switching tools.", "WARN")
            return
        if key == "batch":
            self._active_tool = "batch"
            self._sync_tool_tab_selection()
            self._set_control_tabs_for_feature("batch")
            self._control_tabs.setVisible(self._control_tabs.count() > 0)
            self._control_dock.show()
            self._on_control_tab_changed(self._control_tabs.currentIndex())
            self._feature_label.setText("Active feature: Batch Processing")
            self._append_log("Feature switched: Batch Processing", "INFO")
            return
        if key == "validation":
            self._active_tool = "validation"
            self._sync_tool_tab_selection()
            self._set_control_tabs_for_feature("validation")
            self._control_tabs.setVisible(self._control_tabs.count() > 0)
            self._control_dock.show()
            self._precheck_dock.hide()
            self._auto_guide_dock.hide()
            self._apply_editor_modes()
            self._refresh_canvas_surface()
            self._feature_label.setText("Active feature: Validation")
            self._append_log("Feature switched: Validation", "INFO")
            return
        if key == "visualization":
            self._active_tool = "visualization"
            self._sync_tool_tab_selection()
            self._set_control_tabs_for_feature("visualization")
            self._control_tabs.setVisible(self._control_tabs.count() > 0)
            self._control_dock.show()
            self._precheck_dock.hide()
            self._auto_guide_dock.hide()
            self._apply_editor_modes()
            self._refresh_canvas_surface()
            self._feature_label.setText("Active feature: Visualization")
            self._append_log("Feature switched: Visualization", "INFO")
            return
        if key in ("morphology_editing", "dendrogram"):
            self._active_tool = "morphology_editing"
            self._sync_tool_tab_selection()
            self._set_control_tabs_for_feature("morphology_editing")
            self._control_tabs.setVisible(self._control_tabs.count() > 0)
            self._control_dock.show()
            self._precheck_dock.hide()
            self._auto_guide_dock.hide()
            self._apply_editor_modes()
            self._refresh_canvas_surface()
            self._clear_active_editor_selection_if_unfocused()
            self._feature_label.setText("Active feature: Morphology Editing")
            self._append_log("Feature switched: Morphology Editing", "INFO")
            return
        if key == "geometry_editing":
            self._active_tool = "geometry_editing"
            self._sync_tool_tab_selection()
            self._set_control_tabs_for_feature("geometry_editing")
            self._control_tabs.setVisible(self._control_tabs.count() > 0)
            self._control_dock.show()
            self._precheck_dock.hide()
            self._auto_guide_dock.hide()
            self._apply_editor_modes()
            self._refresh_canvas_surface()
            self._clear_active_editor_selection_if_unfocused()
            self._feature_label.setText("Active feature: Geometry Editing")
            self._append_log("Feature switched: Geometry Editing", "INFO")
            return
        self._active_tool = ""
        self._sync_tool_tab_selection()
        self._set_control_tabs_for_feature("")
        self._precheck_dock.hide()
        self._auto_guide_dock.hide()
        self._apply_editor_modes()
        self._refresh_canvas_surface()
        self._feature_label.setText("Active feature: None")
        self._append_log("No active tool selected.", "INFO")

    def _set_camera(self, preset: str):
        ed = self._active_editor()
        if ed is None:
            return
        ed.set_camera_view(preset)
        self._append_log(f"Camera preset: {preset}", "INFO")

    def _reset_camera(self):
        ed = self._active_editor()
        if ed is None:
            return
        ed.reset_camera()
        self._append_log("Camera reset.", "INFO")

    def _on_render_mode_changed(self, index: int):
        mode = self._render_combo.currentData()
        if mode is None:
            return
        ed = self._active_editor()
        if ed is None:
            return
        ed.set_render_mode(int(mode))
        self._append_log(f"Render mode set to {self._render_combo.currentText()}.", "INFO")

    # --------------------------------------------------------- File loading
    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open SWC file", "", "SWC Files (*.swc);;All Files (*)"
        )
        if path:
            self._load_swc(path)

    def _load_swc(self, path: str):
        try:
            df = parse_swc_text_preserve_tokens(Path(path).read_text(encoding="utf-8", errors="ignore"))
            if df.empty:
                self._append_log(f"Empty file: {path} contains no data rows.", "WARN")
                return

            for col in ("id", "type", "parent"):
                df[col] = df[col].astype(int)

            filename = os.path.basename(path)
            editor = EditorTab()
            self._connect_editor_signals(editor)
            controls = editor.take_dendrogram_controls_panel()
            editor.load_swc(df.loc[:, SWC_COLS].copy(), filename)

            doc = _DocumentState(
                editor=editor,
                controls=controls,
                df=df.copy(),
                filename=filename,
                file_path=str(path),
                original_df=df.copy(),
            )
            self._documents[editor] = doc
            self._start_morphology_session(doc)

            idx = self._canvas_tabs.addTab(editor, filename)
            self._canvas_tabs.setCurrentIndex(idx)

            self._update_recent_files(path)

            n_roots = int((df["parent"] == -1).sum())
            n_soma = int((df["type"] == 1).sum())
            self._status.showMessage(
                f"Loaded {filename}: {len(df)} nodes, {n_roots} root(s), {n_soma} soma(s)",
                5000,
            )
            self._append_log(
                f"Loaded {filename}: nodes={len(df)}, roots={n_roots}, soma={n_soma}",
                "INFO",
            )
            self.swc_loaded.emit(df.loc[:, SWC_COLS].copy(), filename)
        except Exception as e:
            self._append_log(f"Error loading SWC: {e}", "ERROR")

    def _on_save(self):
        doc = self._active_document()
        if doc is None or doc.df.empty:
            self._append_log("No SWC loaded. Nothing to save.", "WARN")
            return
        if not doc.file_path:
            self._on_save_as()
            return
        self._write_swc_file(doc.file_path, doc.df)
        self._after_document_write(doc, doc.file_path, action_name="Save")
        self._append_log(f"Saved {doc.file_path}", "INFO")

    def _on_save_as(self):
        doc = self._active_document()
        if doc is None or doc.df.empty:
            self._append_log("No SWC loaded. Nothing to save.", "WARN")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save SWC As",
            doc.filename or "edited.swc",
            "SWC Files (*.swc);;All Files (*)",
        )
        if not path:
            self._append_log("Save As cancelled.", "INFO")
            return

        self._write_swc_file(path, doc.df)
        doc.file_path = str(path)
        doc.filename = os.path.basename(path)
        tab_idx = self._canvas_tabs.indexOf(doc.editor)
        if tab_idx >= 0:
            self._canvas_tabs.setTabText(tab_idx, doc.filename)
        self._sync_from_active_document(auto_run_validation=False)
        self._after_document_write(doc, path, action_name="Save As")
        self._append_log(f"Saved As {path}", "INFO")
        self._update_recent_files(path)

    def _on_export(self):
        doc = self._active_document()
        if doc is None or doc.df.empty:
            self._append_log("No SWC loaded. Nothing to export.", "WARN")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export SWC",
            f"export_{doc.filename or 'swc'}.swc",
            "SWC Files (*.swc)",
        )
        if not path:
            self._append_log("Export cancelled.", "INFO")
            return
        self._write_swc_file(path, doc.df)
        self._after_document_write(doc, path, action_name="Export")
        self._append_log(f"Exported {path}", "INFO")

    def _write_swc_file(self, path: str, df: pd.DataFrame):
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = write_swc_to_bytes_preserve_tokens(df)
        fd, tmp_path = tempfile.mkstemp(prefix=f".{out_path.stem}_", suffix=".tmp", dir=str(out_path.parent))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, out_path)
        except Exception:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
            raise

    def _build_document_diff_summary(self, doc: _DocumentState) -> dict[str, int]:
        original = doc.original_df.copy() if isinstance(doc.original_df, pd.DataFrame) else pd.DataFrame(columns=SWC_COLS)
        current = doc.df.copy() if isinstance(doc.df, pd.DataFrame) else pd.DataFrame(columns=SWC_COLS)
        summary = {
            "original_nodes": int(len(original)),
            "current_nodes": int(len(current)),
            "type_changes": 0,
            "radius_changes": 0,
            "parent_changes": 0,
            "geometry_changes": 0,
        }
        if original.empty or current.empty:
            return summary
        common_ids = sorted(set(int(v) for v in original["id"].tolist()) & set(int(v) for v in current["id"].tolist()))
        if not common_ids:
            return summary
        old_map = original.set_index("id")
        new_map = current.set_index("id")
        for node_id in common_ids:
            old_row = old_map.loc[node_id]
            new_row = new_map.loc[node_id]
            if int(old_row["type"]) != int(new_row["type"]):
                summary["type_changes"] += 1
            if float(old_row["radius"]) != float(new_row["radius"]):
                summary["radius_changes"] += 1
            if int(old_row["parent"]) != int(new_row["parent"]):
                summary["parent_changes"] += 1
            if (
                float(old_row["x"]) != float(new_row["x"])
                or float(old_row["y"]) != float(new_row["y"])
                or float(old_row["z"]) != float(new_row["z"])
            ):
                summary["geometry_changes"] += 1
        return summary

    def _write_correction_summary(self, doc: _DocumentState, output_path: str) -> str:
        summary = self._build_document_diff_summary(doc)
        skipped = sum(1 for item in doc.issues if str(item.get("status", "")) == "skipped")
        remaining_titles = [str(item.get("title", "")) for item in doc.issues[:20]]
        provenance_lines = [
            f"[{event.get('time', '')}] {event.get('title', 'event')}: {event.get('summary', '')}"
            for event in list(doc.session_operations or [])
        ]
        payload = {
            "input_path": str(doc.file_path or doc.filename),
            "output_path": str(output_path),
            "remaining_issues": len(doc.issues),
            "fixed_issues": int(doc.fixed_issue_count),
            "skipped_issues": int(skipped),
            "diff_summary": summary,
            "remaining_issue_titles": remaining_titles,
            "provenance_lines": provenance_lines,
        }
        log_path = correction_summary_log_path_for_file(output_path)
        return write_text_report(log_path, format_correction_summary_report_text(payload))

    def _after_document_write(self, doc: _DocumentState, output_path: str, *, action_name: str):
        self._record_session_event(
            doc,
            kind="export",
            title=f"{action_name} SWC",
            summary=f"Wrote corrected SWC to {output_path}",
            details=[],
        )
        doc.original_df = doc.df.copy()
        doc.fixed_issue_count = 0
        if not doc.is_preview:
            self._clear_recovery_copy(doc)

    # --------------------------------------------------- Drag & drop
    def dragEnterEvent(self, event: QDragEnterEvent):
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        event.ignore()

    # --------------------------------------------------- Sync from editor
    def _on_editor_df_changed(self, editor: EditorTab, df: pd.DataFrame):
        doc = self._documents.get(editor)
        if doc is None:
            return

        old_df = doc.df.copy() if doc.df is not None else None
        doc.df = df.copy()
        doc.validation_report = None
        doc.issues = []
        if not doc.is_preview:
            self._record_session_operation(
                doc,
                title="Manual Label Edit",
                summary="Applied labeling edits in Morphology Editing.",
                old_df=old_df,
                new_df=doc.df,
                details=[],
            )
        self._push_document_history(doc, doc.df)
        self._write_recovery_copy(doc)
        self._refresh_edit_history_state(doc)

        if editor is self._active_editor():
            self._sync_from_active_document(auto_run_validation=not doc.is_preview)
            if not doc.is_preview:
                self._append_log("Dendrogram edits applied to current SWC.", "INFO")
            else:
                self._append_log("Dendrogram edits applied to simplification preview.", "INFO")

    def _on_editor_node_selected(self, editor: EditorTab, swc_id: int):
        doc = self._documents.get(editor)
        if doc is None or doc is not self._active_document():
            return
        self._manual_radii_panel.set_selected_node(int(swc_id))
        self._geometry_panel.set_current_node(int(swc_id))

    def _on_editor_undo_requested(self, editor: EditorTab):
        doc = self._documents.get(editor)
        if doc is None or doc is not self._active_document():
            return
        if self._undo_document(doc):
            self._append_log("Undo.", "INFO")

    def _on_editor_redo_requested(self, editor: EditorTab):
        doc = self._documents.get(editor)
        if doc is None or doc is not self._active_document():
            return
        if self._redo_document(doc):
            self._append_log("Redo.", "INFO")

    # --------------------------------------------------- Document tabs/windows
    def _on_document_tab_changed(self, _index: int):
        self._sync_from_active_document(auto_run_validation=True)
        if self._active_tool in ("morphology_editing", "dendrogram"):
            self._set_control_tabs_for_feature("morphology_editing")
            self._refresh_simplification_panel_state()
        elif self._active_tool == "geometry_editing":
            self._set_control_tabs_for_feature("geometry_editing")
        self._apply_editor_modes()

    def _on_document_tab_close_requested(self, index: int):
        editor = self._canvas_tabs.widget(index)
        if isinstance(editor, EditorTab):
            self._close_document_editor(editor, from_detached_window=False)

    def _on_document_detach_requested(self, index: int, x: int, y: int):
        editor = self._canvas_tabs.widget(index)
        if not isinstance(editor, EditorTab):
            return
        doc = self._documents.get(editor)
        if doc is None:
            return

        self._canvas_tabs.removeTab(index)
        float_win = _DetachedEditorWindow(editor, doc.filename, self)
        float_win.editor_closing.connect(self._on_detached_editor_closing)
        float_win.move(max(0, int(x - 120)), max(0, int(y - 20)))
        float_win.show()
        self._detached_windows[editor] = float_win

        self._append_log(f"Detached tab: {doc.filename}", "INFO")
        self._sync_from_active_document(auto_run_validation=False)
        self._refresh_canvas_surface()
        if self._active_tool in ("morphology_editing", "dendrogram"):
            self._set_control_tabs_for_feature("morphology_editing")
        elif self._active_tool == "geometry_editing":
            self._set_control_tabs_for_feature("geometry_editing")

    def _on_detached_editor_closing(self, editor_widget: QWidget):
        if self._closing_app:
            return
        if isinstance(editor_widget, EditorTab):
            self._close_document_editor(editor_widget, from_detached_window=True)

    def _request_detached_editor_close(self, editor: EditorTab) -> bool:
        if self._closing_app:
            return True
        return self._close_document_editor(editor, from_detached_window=True)

    def _close_document_editor(self, editor: EditorTab, *, from_detached_window: bool):
        doc = self._documents.get(editor)
        if doc is None:
            return True

        # If this source has a simplification preview tab, close preview first.
        preview_editor = self._simplify_preview_by_source.get(editor)
        if preview_editor is not None:
            self._remove_simplification_preview(preview_editor, switch_to_source=False)
        # If this source has an auto-label preview tab, close preview first.
        auto_preview_editor = self._auto_label_preview_by_source.get(editor)
        if auto_preview_editor is not None:
            self._remove_validation_auto_label_preview(auto_preview_editor, switch_to_source=False)

        # If closing a preview tab, just drop preview state and UI tab.
        if self._is_simplification_preview(doc):
            self._remove_simplification_preview(editor, switch_to_source=False)
            self._append_log(f"Closed tab: {doc.filename}", "INFO")
            self._sync_from_active_document(auto_run_validation=False)
            self._refresh_canvas_surface()
            if self._active_tool in ("morphology_editing", "dendrogram"):
                self._set_control_tabs_for_feature("morphology_editing")
                self._refresh_simplification_panel_state()
            elif self._active_tool == "geometry_editing":
                self._set_control_tabs_for_feature("geometry_editing")
            return True
        if self._is_validation_auto_label_preview(doc):
            self._remove_validation_auto_label_preview(editor, switch_to_source=False)
            self._append_log(f"Closed tab: {doc.filename}", "INFO")
            self._sync_from_active_document(auto_run_validation=False)
            self._refresh_canvas_surface()
            return True

        close_plan = self._plan_document_close(doc, app_closing=False)
        if close_plan is None:
            return False
        if not self._apply_document_close_plan(doc, close_plan):
            return False

        self._documents.pop(editor, None)

        if not from_detached_window:
            idx = self._canvas_tabs.indexOf(editor)
            if idx >= 0:
                self._canvas_tabs.removeTab(idx)

        float_win = self._detached_windows.pop(editor, None)
        if float_win is not None and not from_detached_window:
            try:
                float_win.editor_closing.disconnect(self._on_detached_editor_closing)
            except Exception:
                pass
            float_win.close()

        self._append_log(f"Closed tab: {doc.filename}", "INFO")
        self._sync_from_active_document(auto_run_validation=False)
        self._refresh_canvas_surface()
        if self._active_tool in ("morphology_editing", "dendrogram"):
            self._set_control_tabs_for_feature("morphology_editing")
            self._refresh_simplification_panel_state()
        elif self._active_tool == "geometry_editing":
            self._set_control_tabs_for_feature("geometry_editing")
        return True
    # --------------------------------------------------- Helpers
    def _append_log(self, text: str, level: str = "INFO"):
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] [{level}] {text}".rstrip()
        self._runtime_log_lines.append(line)
        if len(self._runtime_log_lines) > 500:
            self._runtime_log_lines = self._runtime_log_lines[-500:]
        try:
            self._status.showMessage(text, 5000)
        except Exception:
            pass

    def _set_current_file_label_text(self, filename: str):
        full = f"Current file: {filename or '(none)'}"
        self._current_file_label.setToolTip(full)
        # Keep top ribbon shrinkable when filenames are long.
        fm = QFontMetrics(self._current_file_label.font())
        max_px = max(120, self._current_file_label.maximumWidth())
        self._current_file_label.setText(fm.elidedText(full, Qt.ElideMiddle, max_px))

    def _update_info_label(self, df: pd.DataFrame, n_roots: int, n_soma: int, *, filename: str):
        self._info_label.setText(
            f"File: {filename}\n"
            f"Nodes: {len(df)}\n"
            f"Roots: {n_roots}\n"
            f"Soma nodes: {n_soma}\n"
            f"Type counts:\n"
            f"  Soma (1): {(df['type'] == 1).sum()}\n"
            f"  Axon (2): {(df['type'] == 2).sum()}\n"
            f"  Basal (3): {(df['type'] == 3).sum()}\n"
            f"  Apical (4): {(df['type'] == 4).sum()}"
        )

    def _update_recent_files(self, path: str):
        path = os.path.abspath(path)
        if path in self._recent_paths:
            self._recent_paths.remove(path)
        self._recent_paths.insert(0, path)
        self._recent_paths = self._recent_paths[:10]

        self._recent_menu.clear()
        for p in self._recent_paths:
            act = QAction(p, self)
            act.triggered.connect(lambda _=False, sp=p: self._load_swc(sp))
            self._recent_menu.addAction(act)

    def _reset_layout(self):
        self._data_dock.show()
        self._control_dock.show()
        self._precheck_dock.hide()
        self._auto_guide_dock.hide()
        try:
            self.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks)
            self.addDockWidget(Qt.LeftDockWidgetArea, self._data_dock)
            self.addDockWidget(Qt.RightDockWidgetArea, self._control_dock)
            self.resizeDocks([self._data_dock, self._control_dock], [340, 360], Qt.Horizontal)
        except Exception:
            pass
        self._append_log("Layout reset (docks movable).", "INFO")

    def _apply_issue_state(self, doc: _DocumentState | None):
        issues = list(doc.issues) if doc is not None else []
        self._issue_panel.set_issues(issues)
        self._set_issue_status(issues)
        if doc is None:
            return
        selected_issue = None
        if doc.selected_issue_id:
            selected_issue = next(
                (item for item in issues if str(item.get("issue_id", "")).strip() == str(doc.selected_issue_id).strip()),
                None,
            )
        doc.editor.set_issue_markers([selected_issue] if selected_issue else [])
        if selected_issue is None:
            self._issue_panel.clear_selection()
            doc.editor.clear_selection()

    def _set_issue_status(self, issues: list[dict]):
        critical = sum(1 for item in issues if str(item.get("severity", "")) == "critical")
        warning = sum(1 for item in issues if str(item.get("severity", "")) == "warning")
        info = sum(1 for item in issues if str(item.get("severity", "")) == "info")
        skipped = sum(1 for item in issues if str(item.get("status", "")).strip().lower() in {"muted", "skipped"})
        fixed = 0
        doc = self._active_document()
        if doc is not None:
            fixed = int(doc.fixed_issue_count)
        self._issue_status_label.setText(
            f"Issues: {len(issues)} total · {critical} critical · {warning} warning · "
            f"{info} info · {skipped} muted · {fixed} fixed"
        )

    def _build_all_issues_for_document(self, doc: _DocumentState, report: dict) -> list[dict]:
        base_issues = issues_from_validation_report(report)
        if doc.df is not None and not doc.df.empty:
            type_by_id = {
                int(row_id): int(row_type)
                for row_id, row_type in zip(doc.df["id"].tolist(), doc.df["type"].tolist())
                if pd.notna(row_id) and pd.notna(row_type)
            }
            soma_node_ids = [
                int(row_id)
                for row_id, row_type in zip(doc.df["id"].tolist(), doc.df["type"].tolist())
                if pd.notna(row_id) and pd.notna(row_type) and int(row_type) == 1
            ]
            filtered_base_issues: list[dict] = []
            for item in base_issues:
                issue = dict(item)
                if str(issue.get("source_key", "")).strip() == "soma_radius_nonzero" and not list(issue.get("node_ids", []) or []):
                    issue["node_ids"] = list(soma_node_ids)
                    payload = dict(issue.get("source_payload", {}) or {})
                    payload["failing_node_ids"] = list(soma_node_ids)
                    issue["source_payload"] = payload
                if str(issue.get("source_key", "")).strip() == "no_dangling_branches":
                    original_node_ids = [int(v) for v in issue.get("node_ids", [])]
                    kept_node_ids = [node_id for node_id in original_node_ids if type_by_id.get(int(node_id), -999) != 1]
                    if not kept_node_ids:
                        continue
                    issue["node_ids"] = kept_node_ids
                    payload = dict(issue.get("source_payload", {}) or {})
                    payload["failing_node_ids"] = kept_node_ids
                    issue["source_payload"] = payload
                filtered_base_issues.append(issue)
            base_issues = filtered_base_issues
        prereq = validation_prerequisite_summary(report)
        hard_blocked = bool(prereq.get("soma_gate_failed")) or bool(prereq.get("multiple_somas_failed"))
        critical_radii_node_ids = {
            int(node_id)
            for item in base_issues
            if str(item.get("domain", "")) == "radii" and str(item.get("severity", "")) == "critical"
            for node_id in item.get("node_ids", [])
        }
        suspicious_radii: list[dict] = []
        if not hard_blocked and not prereq.get("unsupported_section_types") and not prereq.get("missing_soma"):
            suspicious_radii = issues_from_radii_suspicion(doc.df, ignore_node_ids=critical_radii_node_ids)

        type_suspicious: list[dict] = []
        if not hard_blocked and doc.df is not None and not doc.df.empty:
            tmp_fd, tmp_in = tempfile.mkstemp(prefix="swctools_issue_type_", suffix=".swc")
            os.close(tmp_fd)
            tmp_path = Path(tmp_in)
            try:
                self._write_swc_file(str(tmp_path), doc.df)
                result_obj = run_validation_auto_typing_file(
                    str(tmp_path),
                    write_output=False,
                    write_log=False,
                )
                type_suspicious = issues_from_type_suspicion(
                    list(getattr(result_obj, "rows", []) or []),
                    list(getattr(result_obj, "types", []) or []),
                )
            except Exception:
                type_suspicious = []
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

        simplification_suggestion = issues_from_simplification_suggestion(doc.df)
        all_issues = list(base_issues) + list(suspicious_radii) + list(type_suspicious) + list(simplification_suggestion)
        def _issue_priority(item: dict) -> tuple[int, int, int, int, str]:
            source_key = str(item.get("source_key", "")).strip()
            severity = str(item.get("severity", "")).strip()
            status = str(item.get("status", "")).strip()
            certainty = str(item.get("certainty", "")).strip()
            return (
                0 if source_key == "has_soma" else 1,
                {"critical": 0, "warning": 1, "info": 2}.get(severity, 9),
                {"open": 0, "muted": 1, "skipped": 1, "fixed": 2}.get(status, 9),
                {"rule": 0, "suspicious": 1, "ai": 2}.get(certainty, 9),
                str(item.get("title", "")).lower(),
            )

        all_issues.sort(
            key=_issue_priority
        )
        return all_issues

    def _on_validation_report_ready(self, report: dict):
        doc = self._active_document()
        if doc is None:
            return
        previous_issue_id = str(doc.selected_issue_id or "").strip()
        previous_issue = self._find_issue_by_id(doc, previous_issue_id)
        doc.validation_report = dict(report)
        issues = self._build_all_issues_for_document(doc, report)
        issue_ids = {str(item.get("issue_id", "")) for item in issues}
        for item in issues:
            issue_id = str(item.get("issue_id", "")).strip()
            status = str(doc.issue_status_overrides.get(issue_id, "open")).strip().lower()
            if status == "skipped":
                status = "muted"
            if status:
                item["status"] = status
        if doc.pending_resolved_issue_ids:
            resolved_now = [issue_id for issue_id in doc.pending_resolved_issue_ids if issue_id and issue_id not in issue_ids]
            if resolved_now:
                doc.fixed_issue_count += len(resolved_now)
            doc.pending_resolved_issue_ids = set()
        doc.issue_status_overrides = {
            issue_id: status
            for issue_id, status in doc.issue_status_overrides.items()
            if issue_id in issue_ids and status in {"muted", "skipped"}
        }
        doc.issues = issues
        self._apply_issue_state(doc)
        self._data_tabs.setCurrentIndex(0)
        self._data_dock.show()
        self._append_log(f"Issue navigator updated: {len(doc.issues)} actionable findings.", "INFO")
        if previous_issue_id and self._issue_panel.select_issue(previous_issue_id):
            doc.selected_issue_id = previous_issue_id
            return
        replacement_issue = self._find_matching_issue(doc, previous_issue)
        replacement_issue_id = str((replacement_issue or {}).get("issue_id", "")).strip()
        if replacement_issue_id and self._issue_panel.select_issue(replacement_issue_id):
            doc.selected_issue_id = replacement_issue_id
            return
        doc.selected_issue_id = ""
        self._issue_panel.clear_selection()
        doc.editor.set_issue_markers([])
        self._context_inspector.clear(
            title="No issue selected",
            problem_detail="The previous issue was resolved.",
            suggested_solution="Click another issue in the left panel to continue.",
        )

    def _on_validation_result_activated(self, row: dict):
        if str(row.get("key", "")).strip() in {"parent_id_less_than_child_id", "no_node_id_gaps"}:
            self._activate_feature("validation")
            self._select_control_tab_by_label("index clean")
        issues = issues_from_validation_report({"results": [row]})
        if not issues:
            return
        self._on_issue_selected(issues[0])

    def _on_validation_index_clean_requested(self, new_df: object, id_map: object):
        doc = self._active_source_document()
        if doc is None or doc.df is None or doc.df.empty:
            self._append_log("Validation: no active SWC document for Index Clean.", "WARN")
            return
        if not isinstance(new_df, pd.DataFrame) or new_df.empty:
            self._append_log("Validation: Index Clean did not produce a valid SWC.", "WARN")
            return
        details = [
            "Validation Index Clean reordered the SWC so parents come before children.",
            "Node IDs were reassigned to a continuous parent-before-child order.",
        ]
        self._apply_document_dataframe(
            doc,
            new_df,
            event_title="Validation Index Clean",
            event_summary="Reordered and reindexed the SWC for clean parent-before-child indexing.",
            event_details=details,
            record_type_changes=False,
            id_map=dict(id_map or {}),
        )
        self._append_log("Validation: Index Clean applied.", "INFO")
        self._rerun_active_validation()

    def _focus_issue(self, issue: dict):
        doc = self._active_document()
        if doc is None:
            return
        node_ids = [int(v) for v in issue.get("node_ids", [])]
        if node_ids:
            doc.editor.focus_node(node_ids[0])
        elif issue.get("section_ids"):
            self._append_log("Issue has section-level context but no direct node target yet.", "INFO")

    def _select_control_tab_by_label(self, target: str):
        wanted = str(target or "").strip().lower()
        for i in range(self._control_tabs.count()):
            label = (self._control_tabs.tabText(i) or "").strip().lower()
            if label == wanted:
                if self._control_tabs.currentIndex() != i:
                    self._control_tabs.setCurrentIndex(i)
                return True
        return False

    def _issue_uses_popup_only_controls(self, issue: dict | None) -> bool:
        if not isinstance(issue, dict):
            return False
        return str(issue.get("source_key", "")).strip() in {
            "valid_soma_format",
            "multiple_somas",
            "has_soma",
            "has_axon",
            "has_basal_dendrite",
            "has_apical_dendrite",
            "no_invalid_negative_types",
            "custom_types_defined",
        }

    def _route_issue_to_tool(self, issue: dict):
        tool_target = str(issue.get("tool_target", "")).strip().lower()
        if not tool_target:
            return
        if tool_target in {"label_editing", "auto_label", "radii_cleaning", "manual_radii"}:
            self._activate_feature("morphology_editing")
            target_tab = {
                "label_editing": "manual label editing",
                "auto_label": "auto label editing",
                "manual_radii": "manual radii editing",
                "radii_cleaning": "auto radii editing",
            }.get(tool_target, "manual label editing")
            self._select_control_tab_by_label(target_tab)
            return
        if tool_target == "simplification":
            self._activate_feature("geometry_editing")
            self._select_control_tab_by_label("simplification")
            return
        if tool_target == "geometry_editing":
            self._activate_feature("geometry_editing")
            self._select_control_tab_by_label("geometry editing")
            return
        if tool_target == "index_clean":
            self._activate_feature("validation")
            self._select_control_tab_by_label("index clean")
            return
        self._activate_feature("validation")
        self._select_control_tab_by_label("validation")

    def _on_issue_selected(self, issue: dict):
        doc = self._active_document()
        if doc is not None:
            doc.selected_issue_id = str(issue.get("issue_id", "")).strip()
            doc.editor.clear_selection()
            doc.editor.clear_geometry_selection()
            self._manual_radii_panel.clear_selection()
            doc.editor.set_issue_markers([issue])
        self._data_tabs.setCurrentIndex(0)
        if self._issue_uses_popup_only_controls(issue):
            self._control_tabs.setVisible(False)
        else:
            self._control_tabs.setVisible(True)
            self._route_issue_to_tool(issue)
        self._context_inspector.set_issue(issue, self._build_issue_context(issue))
        title = str(issue.get("title", "Issue")).strip() or "Issue"
        self._status.showMessage(f"Selected issue: {title}", 4000)

    def _build_issue_context(self, issue: dict) -> dict:
        node_ids = [int(v) for v in issue.get("node_ids", [])]
        doc = self._active_document()
        node_preview = ", ".join(str(v) for v in node_ids[:25]) if node_ids else "None"
        remaining_nodes = max(0, len(node_ids) - 25)
        section_ids = [int(v) for v in issue.get("section_ids", [])]
        ctx = {
            "node_ids_text": ", ".join(str(v) for v in node_ids) or "None",
            "section_ids_text": ", ".join(str(v) for v in section_ids) or "None",
            "problem_detail": str(issue.get("description", "")).strip() or "No extra detail provided.",
            "suggested_solution": str(issue.get("suggested_fix", "")).strip() or "Inspect the affected morphology and fix the prerequisite issue first.",
            "tool_button_label": {
                "validation": "Validation",
                "index_clean": "Index Clean",
                "radii_cleaning": "Auto Radii Editing",
                "manual_radii": "Manual Radii Editing",
                "auto_label": "Auto Label Editing",
                "label_editing": "Manual Label Editing",
                "simplification": "Simplification",
                "geometry_editing": "Geometry Editing",
            }.get(str(issue.get("tool_target", "")).strip().lower(), "Related Tool"),
            "auto_fix_available": False,
            "auto_fix_label": "",
            "detail_lines": [],
        }
        if node_ids or section_ids:
            ctx["detail_lines"].extend(
                [
                    f"Total affected nodes: {len(node_ids)}",
                    f"Affected node IDs: {node_preview}",
                    *(["Additional nodes not shown here: " + str(remaining_nodes)] if remaining_nodes > 0 else []),
                    f"Sections: {', '.join(str(v) for v in section_ids) or 'None'}",
                ]
            )
        else:
            ctx["detail_lines"].extend(
                [
                    "Affected nodes: not provided by this check",
                    "Affected sections: not provided by this check",
                ]
            )
        if doc is None or doc.df is None or doc.df.empty:
            return ctx

        payload = dict(issue.get("source_payload", {}) or {})
        radii_stats = dict(radii_stats_by_type(doc.df, bins=20))
        type_stats_map = dict(radii_stats.get("type_stats", {}) or {})
        if node_ids:
            ctx["focus_node_id"] = int(node_ids[0])

        if str(issue.get("source_key", "")).strip() == "blocked_validation_checks":
            blocked_checks = list(payload.get("blocked_checks", []) or [])
            blocked_labels = [str(item.get("label", "")).strip() for item in blocked_checks if str(item.get("label", "")).strip()]
            blocked_reason = str(payload.get("blocked_reason", "Unknown prerequisite issue")).strip()
            preface_lines: list[str] = []
            if blocked_reason.lower() == "unsupported section type: 0":
                preface_lines = [
                    "Some dependent checks are still blocked because neurite sections still contain unsupported type 0 labels.",
                    "If you already assigned a soma, that part is fixed; the remaining blocked state comes from unlabeled neurite nodes.",
                    "",
                ]
            ctx["detail_lines"] = [
                *preface_lines,
                f"Blocked reason: {blocked_reason}",
                f"Checks that could not run ({len(blocked_labels)}):",
                *[f"- {label}" for label in blocked_labels],
                "",
                "Suggested next step:",
                str(ctx.get("suggested_solution", "")).strip(),
            ]
            return ctx

        radii_issue_keys = {
            "all_neurite_radii_nonzero",
            "soma_radius_nonzero",
            "no_ultranarrow_sections",
            "no_ultranarrow_starts",
            "no_fat_terminal_ends",
            "radius_upper_bound",
            "radii_outlier_batch",
        }
        if str(issue.get("domain", "")).strip() == "radii" or str(issue.get("source_key", "")).strip() in radii_issue_keys:
            ctx.update(
                {
                    "custom_primary_label": "Manual Radii Editing",
                    "custom_primary_action": "open_manual_radii_tool",
                    "custom_secondary_label": "Auto Radii Editing",
                    "custom_secondary_action": "open_auto_radii_tool",
                    "hide_skip_button": True,
                    "hide_apply_button": True,
                }
            )

        if str(issue.get("source_key", "")).strip() == "valid_soma_format":
            complex_groups = list(payload.get("metrics", {}).get("complex_groups", []) or [])
            preview = []
            for group in complex_groups[:10]:
                preview.append(
                    f"Group anchored at node {int(group.get('anchor_id', -1))}: "
                    f"{len(list(group.get('node_ids', []) or []))} connected soma nodes"
                )
            ctx.update(
                {
                    "problem_detail": str(issue.get("description", "")).strip() or "Complex multi-node soma format detected.",
                    "suggested_solution": (
                        "Consolidate each connected soma group into one mega-node: isolate connected type-1 nodes, "
                        "compute the centroid, set the radius to furthest-distance-plus-radius, and rewire all "
                        "non-soma children to the surviving anchor node."
                    ),
                    "custom_primary_label": "Consolidate Soma",
                    "custom_primary_action": "consolidate_soma",
                    "hide_detail_section": True,
                    "detail_lines": [
                        f"Complex soma groups: {len(complex_groups)}",
                        "",
                        "Consolidation steps:",
                        "1. Group connected soma nodes (type 1) by topology.",
                        "2. Replace each group with one mega-node at the centroid.",
                        "3. Set radius to furthest-node distance plus that node's radius.",
                        "4. Rewire all axon/dendrite children to the new anchor node.",
                        "",
                        *preview,
                    ],
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() in {"has_soma", "has_axon", "has_basal_dendrite", "has_apical_dendrite"}:
            missing_key = str(issue.get("source_key", "")).strip()
            missing_label_map = {
                "has_soma": "soma",
                "has_axon": "axon",
                "has_basal_dendrite": "basal dendrite",
                "has_apical_dendrite": "apical dendrite",
            }
            missing_label = missing_label_map.get(missing_key, "neurite type")
            ctx.update(
                {
                    "problem_detail": str(issue.get("description", "")).strip() or f"No {missing_label} node found.",
                    "suggested_solution": (
                        "Choose either Manual Label Editing or Auto Label Editing in Morphology Editing to assign the missing type."
                    ),
                    "custom_primary_label": "Manual Label Editing",
                    "custom_primary_action": "open_manual_label_popup",
                    "custom_secondary_label": "Auto Label Editing",
                    "custom_secondary_action": "open_auto_label_popup",
                    "hide_skip_button": True,
                    "hide_apply_button": True,
                    "hide_detail_section": True,
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() == "multiple_somas":
            soma_ids = list(payload.get("metrics", {}).get("soma_ids_after_consolidation", []) or [])
            ctx.update(
                {
                    "problem_detail": str(issue.get("description", "")).strip() or "Multiple disconnected soma groups detected.",
                    "suggested_solution": "This file must be split into one SWC per disconnected tree.",
                    "custom_primary_label": "Split",
                    "custom_primary_action": "split_trees",
                    "hide_detail_section": True,
                    "detail_lines": [
                        f"Disconnected soma groups: {len(soma_ids)}",
                        f"Soma anchor IDs: {', '.join(str(int(v)) for v in soma_ids) if soma_ids else 'None'}",
                        "",
                        "Suggested fix:",
                        "Split each disconnected tree into its own SWC file.",
                    ],
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() == "custom_types_defined":
            undefined_custom_types = list(payload.get("metrics", {}).get("undefined_custom_types", []) or [])
            detail_lines = [
                f"Total affected nodes: {len(node_ids)}",
                f"Affected node IDs: {node_preview}",
                *(["Additional nodes not shown here: " + str(remaining_nodes)] if remaining_nodes > 0 else []),
                "",
                "Undefined custom type groups:",
            ]
            if undefined_custom_types:
                for item in undefined_custom_types:
                    type_id = int(item.get("type_id", -1))
                    sample_ids = [int(v) for v in list(item.get("node_ids_sample", []) or [])]
                    detail_lines.append(
                        f"Type {type_id}: {int(item.get('node_count', 0))} node(s)"
                    )
                    if sample_ids:
                        detail_lines.append(
                            f"  sample node IDs: {', '.join(str(v) for v in sample_ids[:25])}"
                        )
            else:
                affected_rows = doc.df.loc[doc.df["id"].astype(int).isin(node_ids)].copy() if node_ids else pd.DataFrame(columns=SWC_COLS)
                for _, row in affected_rows.head(50).iterrows():
                    detail_lines.append(
                        f"Node {int(row['id'])}: current type={int(row['type'])}, "
                        f"label={label_for_type(int(row['type']))}"
                    )
                if len(affected_rows) > 50:
                    detail_lines.extend(["...", f"Only first 50 affected nodes shown here. Remaining nodes: {len(affected_rows) - 50}"])
            ctx.update(
                {
                    "problem_detail": str(issue.get("description", "")).strip() or "Custom SWC type IDs need display definitions.",
                    "suggested_solution": "Use Manual Label Editing and define each custom type with a type ID, name, color, and notes.",
                    "custom_primary_label": "Manual Label Editing",
                    "custom_primary_action": "open_manual_label_popup",
                    "hide_skip_button": True,
                    "hide_apply_button": True,
                    "detail_lines": detail_lines,
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() == "no_invalid_negative_types":
            detail_lines = [
                f"Total affected nodes: {len(node_ids)}",
                f"Affected node IDs: {node_preview}",
                *(["Additional nodes not shown here: " + str(remaining_nodes)] if remaining_nodes > 0 else []),
                "",
                "Invalid type values by node:",
            ]
            affected_rows = doc.df.loc[doc.df["id"].astype(int).isin(node_ids)].copy() if node_ids else pd.DataFrame(columns=SWC_COLS)
            affected_rows = affected_rows.sort_values("id")
            for _, row in affected_rows.head(50).iterrows():
                detail_lines.append(
                    f"Node {int(row['id'])}: current type={int(row['type'])}, "
                    f"radius={float(row['radius']):.5g}, parent={int(row['parent'])}"
                )
            if len(affected_rows) > 50:
                detail_lines.extend(["...", f"Only first 50 affected nodes shown here. Remaining nodes: {len(affected_rows) - 50}"])
            ctx.update(
                {
                    "problem_detail": str(issue.get("description", "")).strip() or "One or more nodes use invalid negative SWC type values.",
                    "suggested_solution": "Relabel nodes with invalid negative type values to supported SWC types.",
                    "custom_primary_label": "Manual Label Editing",
                    "custom_primary_action": "open_manual_label_popup",
                    "hide_skip_button": True,
                    "hide_apply_button": True,
                    "detail_lines": detail_lines,
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() == "simplification_suggestion":
            ctx.update(
                {
                    "problem_detail": str(issue.get("description", "")).strip() or "This SWC may benefit from simplification.",
                    "suggested_solution": "Open Simplification to preview and apply graph-aware cleanup on the current SWC.",
                    "custom_primary_label": "Simplification",
                    "custom_primary_action": "open_simplification_tool",
                    "hide_detail_section": True,
                    "detail_lines": [],
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() in {"parent_id_less_than_child_id", "no_node_id_gaps"}:
            source_key = str(issue.get("source_key", "")).strip()
            metrics = dict(payload.get("metrics", {}) or {})
            detail_lines = [
                f"Total affected nodes: {len(node_ids)}",
                f"Affected node IDs: {node_preview}",
                *(["Additional nodes not shown here: " + str(remaining_nodes)] if remaining_nodes > 0 else []),
            ]
            if source_key == "parent_id_less_than_child_id":
                detail_lines.extend(
                    [
                        "",
                        f"ID order violations: {int(metrics.get('id_order_violation_count', len(node_ids)))}",
                        "Meaning: one or more child nodes appear before their parent in ID order.",
                    ]
                )
            else:
                gap_samples = list(metrics.get("gap_samples", []) or [])
                detail_lines.extend(
                    [
                        "",
                        f"ID gaps found: {int(metrics.get('gap_count', 0))}",
                        f"Missing ID values: {int(metrics.get('missing_id_count', 0))}",
                        "Meaning: sorted node IDs skip one or more integers.",
                    ]
                )
                if gap_samples:
                    detail_lines.append("")
                    detail_lines.append("Gap examples:")
                    for sample in gap_samples[:10]:
                        detail_lines.append(
                            f"After {int(sample.get('after_id', -1))}, next ID is {int(sample.get('before_id', -1))} "
                            f"(missing {int(sample.get('missing_count', 0))})"
                        )
            ctx.update(
                {
                    "problem_detail": str(issue.get("description", "")).strip() or "Index consistency issue detected.",
                    "suggested_solution": "Open Validation -> Index Clean to reorder the SWC and rebuild a continuous parent-before-child ID sequence.",
                    "detail_lines": detail_lines,
                }
            )
            return ctx

        if (
            str(issue.get("source_key", "")).strip() == "no_fat_terminal_ends"
            and not node_ids
            and not section_ids
        ):
            ctx.update(
                {
                    "problem_detail": "This warning means one or more terminal branch endings appear abnormally thick compared with the local branch trend.",
                    "suggested_solution": "Inspect terminal tips in Auto Radii Editing or adjust individual nodes in Manual Radii Editing.",
                    "detail_lines": [
                        "This is a morphology-level NeuroM warning.",
                        "The current backend reports pass/fail for this check but does not return exact terminal node IDs.",
                        "",
                        "Suggested review focus:",
                        "- terminal tips with unusually large radii",
                        "- sudden radius inflation at branch endings",
                    ],
                }
            )
            return ctx

        radii_issue_keys = {
            "all_neurite_radii_nonzero",
            "soma_radius_nonzero",
            "no_ultranarrow_sections",
            "no_ultranarrow_starts",
            "no_fat_terminal_ends",
            "radius_upper_bound",
            "radii_outlier_batch",
        }
        if str(issue.get("domain", "")).strip() == "radii" or str(issue.get("source_key", "")).strip() in radii_issue_keys:
            detail_lines = [
                f"Total affected nodes: {len(node_ids)}",
                f"Affected node IDs: {node_preview}",
                *(["Additional nodes not shown here: " + str(remaining_nodes)] if remaining_nodes > 0 else []),
            ]
            if section_ids:
                detail_lines.append(f"Sections: {', '.join(str(v) for v in section_ids)}")
            detail_lines.append("")
            detail_lines.append("Affected node radii:")

            affected_rows = doc.df.loc[doc.df["id"].astype(int).isin(node_ids)].copy() if node_ids else pd.DataFrame(columns=SWC_COLS)
            affected_rows = affected_rows.sort_values("id")
            for _, row in affected_rows.head(50).iterrows():
                type_id = int(row["type"])
                stats_row = dict(type_stats_map.get(str(type_id), {}) or {})
                summary = []
                if stats_row.get("median") is not None:
                    summary.append(f"median={float(stats_row.get('median', 0.0)):.5g}")
                if stats_row.get("q1") is not None and stats_row.get("q3") is not None:
                    summary.append(
                        f"q1={float(stats_row.get('q1', 0.0)):.5g}"
                    )
                    summary.append(
                        f"q3={float(stats_row.get('q3', 0.0)):.5g}"
                    )
                summary_text = f" | type stats: {', '.join(summary)}" if summary else ""
                detail_lines.append(
                    f"Node {int(row['id'])}: radius={float(row['radius']):.5g}, "
                    f"type={label_for_type(type_id)} ({type_id}){summary_text}"
                )
            if len(affected_rows) > 50:
                detail_lines.extend(["...", f"Only first 50 affected nodes shown here. Remaining nodes: {len(affected_rows) - 50}"])
            ctx["detail_lines"] = detail_lines
            return ctx

        if (
            not node_ids
            and not section_ids
            and str(payload.get("source", "")).strip() == "neuron_morphology"
        ):
            recommended_tool = str(issue.get("tool_target", "") or "").strip()
            ctx.update(
                {
                    "detail_lines": [
                        "This is a morphology-level NeuroM check result.",
                        "The current backend reports pass/fail for this warning but does not return exact node IDs or section IDs.",
                        "",
                        f"Check key: {issue.get('source_key', '') or 'n/a'}",
                        *([f"Recommended tool: {recommended_tool}"] if recommended_tool else []),
                    ],
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() == "no_duplicate_3d_points":
            duplicate_groups = list(payload.get("metrics", {}).get("duplicate_groups_sample", []) or [])
            group_lines: list[str] = []
            for idx, group in enumerate(duplicate_groups, start=1):
                ids_in_group = [int(v) for v in list(group.get("ids", []) or [])]
                xyz = list(group.get("xyz", []) or [])
                xyz_text = ", ".join(f"{float(v):.5g}" for v in xyz[:3]) if len(xyz) >= 3 else "unknown"
                group_lines.append(
                    f"Group {idx}: nodes {', '.join(str(v) for v in ids_in_group)} share XYZ ({xyz_text})"
                )
            total_groups = int(payload.get("metrics", {}).get("duplicate_group_count", len(duplicate_groups)))
            ctx.update(
                {
                    "problem_detail": str(issue.get("description", "")).strip() or "Multiple nodes share exactly the same 3D position.",
                    "suggested_solution": "Review each duplicated node group and merge, delete, or simplify the redundant geometry.",
                    "detail_lines": [
                        f"Duplicate groups found: {total_groups}",
                        f"Total affected nodes: {len(node_ids)}",
                        "",
                        "Duplicated node groups:",
                        *group_lines,
                        *(["...", f"Only first {len(duplicate_groups)} duplicate groups shown here."] if total_groups > len(duplicate_groups) else []),
                    ],
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() == "radii_outlier_batch":
            changes = list(payload.get("changes", []) or [])
            preview_lines = []
            for item in changes[:50]:
                reasons = ", ".join(str(reason) for reason in list(item.get("reasons", [])) if str(reason).strip())
                preview_lines.append(
                    f"Node {int(item.get('node_id', -1))}: {float(item.get('old_radius', 0.0)):.5g} -> "
                    f"{float(item.get('new_radius', 0.0)):.5g}"
                    + (f" ({reasons})" if reasons else "")
                )
            ctx.update(
                {
                    "auto_fix_available": True,
                    "auto_fix_label": "Apply Suggested Radii",
                    "problem_detail": f"{len(changes)} nodes have suspicious radii that likely need cleanup.",
                    "suggested_solution": "Review the selected nodes in Manual Radii Editing or use Auto Radii Editing for broader cleanup.",
                    "detail_lines": [
                        f"Total affected nodes: {len(changes)}",
                        f"Affected node IDs: {', '.join(str(int(item.get('node_id', -1))) for item in changes[:25])}",
                        *(["Additional nodes not shown here: " + str(max(0, len(changes) - 25))] if len(changes) > 25 else []),
                        "",
                        "Problem details by node:",
                        "Suggested updates:",
                        *preview_lines,
                        *(["...", f"Only first 50 node updates shown here. Remaining nodes: {max(0, len(changes) - 50)}"] if len(changes) > 50 else []),
                    ],
                }
            )
            return ctx

        if str(issue.get("source_key", "")).strip() == "type_suspicion_batch":
            changes = list(payload.get("changes", []) or [])
            preview_lines = []
            for item in changes[:50]:
                preview_lines.append(
                    f"Node {int(item.get('node_id', -1))}: type {int(item.get('old_type', -1))} -> "
                    f"type {int(item.get('new_type', -1))}"
                )
            ctx.update(
                {
                    "custom_primary_label": "Auto Label Editing",
                    "custom_primary_action": "open_auto_label_popup",
                    "hide_apply_button": True,
                    "problem_detail": f"{len(changes)} nodes have likely incorrect neurite labels.",
                    "suggested_solution": "Review the suggested relabeling in Auto Label Editing and apply it from the tool if it looks correct.",
                    "detail_lines": [
                        f"Total affected nodes: {len(changes)}",
                        f"Affected node IDs: {', '.join(str(int(item.get('node_id', -1))) for item in changes[:25])}",
                        *(["Additional nodes not shown here: " + str(max(0, len(changes) - 25))] if len(changes) > 25 else []),
                        "",
                        "Problem details by node:",
                        "Suggested relabeling:",
                        *preview_lines,
                        *(["...", f"Only first 50 relabel suggestions shown here. Remaining nodes: {max(0, len(changes) - 50)}"] if len(changes) > 50 else []),
                    ],
                }
            )
            return ctx

        if node_ids:
            ctx["detail_lines"].extend(["", f"This issue is attached to {len(node_ids)} node(s). Use the highlighted nodes in the viewer to inspect the local morphology."])

        ctx["detail_lines"].append(f"Check key: {issue.get('source_key', '') or 'n/a'}")
        recommended_tool = str(issue.get("tool_target", "") or "").strip()
        if recommended_tool:
            ctx["detail_lines"].append(f"Recommended tool: {recommended_tool}")
        return ctx

    def _apply_document_dataframe(
        self,
        doc: _DocumentState,
        df: pd.DataFrame,
        *,
        event_title: str = "",
        event_summary: str = "",
        event_details: list[str] | None = None,
        push_history: bool = True,
        record_type_changes: bool = True,
        id_map: dict[int, int] | None = None,
        change_rows: list[dict] | None = None,
    ):
        old_df = doc.df.copy() if doc.df is not None else None
        doc.df = df.copy()
        if push_history:
            self._push_document_history(doc, doc.df)
        self._write_recovery_copy(doc)
        doc.editor.load_swc(doc.df, doc.filename)
        doc.editor.set_mode(self._editor_mode_for_feature())
        self._refresh_edit_history_state(doc)
        if event_title:
            self._record_session_operation(
                doc,
                title=event_title,
                summary=event_summary,
                old_df=old_df,
                new_df=doc.df,
                details=event_details or [],
                id_map=dict(id_map or {}) if isinstance(id_map, dict) else None,
                change_rows=list(change_rows or []) if isinstance(change_rows, list) else None,
            )
        self._sync_from_active_document(auto_run_validation=False)

    def _rerun_active_validation(self, *, resolved_issue_id: str | None = None):
        doc = self._active_document()
        if doc is None:
            return
        self._validation_tab.stop_worker(wait_ms=5000)
        if resolved_issue_id:
            doc.pending_resolved_issue_ids.add(str(resolved_issue_id))
            doc.issue_status_overrides.pop(str(resolved_issue_id), None)
        doc.validation_report = None
        self._issue_panel.clear_issues("Running validation and issue detectors...")
        self._set_issue_status([])
        doc.editor.set_issue_markers([])
        doc.editor.clear_selection()
        self._validation_tab.load_swc(doc.df, doc.filename, file_path=doc.file_path, auto_run=False)
        self._validation_tab.run_validation()

    def _find_issue_by_id(self, doc: _DocumentState | None, issue_id: str) -> dict | None:
        if doc is None:
            return None
        wanted = str(issue_id or "").strip()
        if not wanted:
            return None
        for item in doc.issues:
            if str(item.get("issue_id", "")).strip() == wanted:
                return dict(item)
        return None

    def _find_matching_issue(self, doc: _DocumentState | None, previous_issue: dict | None) -> dict | None:
        if doc is None or not isinstance(previous_issue, dict):
            return None
        candidates = [dict(item) for item in doc.issues if isinstance(item, dict)]
        if not candidates:
            return None

        previous_source_key = str(previous_issue.get("source_key", "")).strip()
        previous_title = str(previous_issue.get("title", "")).strip()
        previous_domain = str(previous_issue.get("domain", "")).strip()
        previous_certainty = str(previous_issue.get("certainty", "")).strip()

        scoped = candidates
        if previous_source_key:
            same_source = [
                item for item in candidates
                if str(item.get("source_key", "")).strip() == previous_source_key
            ]
            if same_source:
                scoped = same_source
        elif previous_title:
            same_title = [
                item for item in candidates
                if str(item.get("title", "")).strip() == previous_title
            ]
            if same_title:
                scoped = same_title

        previous_nodes = {int(v) for v in previous_issue.get("node_ids", [])}
        previous_sections = {int(v) for v in previous_issue.get("section_ids", [])}

        def _score(candidate: dict) -> tuple[int, int, int, int, int, int, str]:
            score = 0
            candidate_source = str(candidate.get("source_key", "")).strip()
            candidate_title = str(candidate.get("title", "")).strip()
            candidate_domain = str(candidate.get("domain", "")).strip()
            candidate_certainty = str(candidate.get("certainty", "")).strip()
            if candidate_source and candidate_source == previous_source_key:
                score += 1000
            if candidate_title and candidate_title == previous_title:
                score += 200
            if candidate_domain and candidate_domain == previous_domain:
                score += 100
            if candidate_certainty and candidate_certainty == previous_certainty:
                score += 50

            candidate_nodes = {int(v) for v in candidate.get("node_ids", [])}
            candidate_sections = {int(v) for v in candidate.get("section_ids", [])}
            node_overlap = len(previous_nodes & candidate_nodes)
            section_overlap = len(previous_sections & candidate_sections)
            score += node_overlap * 10
            score += section_overlap * 5

            return (
                score,
                node_overlap,
                section_overlap,
                -abs(len(candidate_nodes) - len(previous_nodes)),
                -abs(len(candidate_sections) - len(previous_sections)),
                -len(candidate_nodes),
                str(candidate.get("issue_id", "")).strip(),
            )

        best = max(scoped, key=_score, default=None)
        if not isinstance(best, dict):
            return None

        best_source = str(best.get("source_key", "")).strip()
        best_title = str(best.get("title", "")).strip()
        best_nodes = {int(v) for v in best.get("node_ids", [])}
        best_sections = {int(v) for v in best.get("section_ids", [])}
        if previous_source_key and best_source == previous_source_key:
            if (
                len(scoped) == 1
                or bool(previous_nodes & best_nodes)
                or bool(previous_sections & best_sections)
                or (not previous_nodes and not previous_sections)
            ):
                return best
            return None
        if previous_title and best_title == previous_title:
            return best
        return None

    def _on_apply_suggested_fix_requested(self, issue_id: str):
        doc = self._active_document()
        if doc is None or doc.df is None or doc.df.empty:
            return
        issue = self._find_issue_by_id(doc, issue_id)
        if not issue:
            return
        source_key = str(issue.get("source_key", "")).strip()
        payload = dict(issue.get("source_payload", {}) or {})

        if source_key == "radii_outlier_batch":
            changes = list(payload.get("changes", []) or [])
            if not changes:
                return
            df = doc.df.copy()
            applied = []
            for item in changes:
                node_id = int(item.get("node_id", -1))
                mask = df["id"] == node_id
                if not bool(mask.any()):
                    continue
                old_radius = float(df.loc[mask, "radius"].iloc[0])
                new_radius = float(item.get("new_radius", old_radius))
                df.loc[mask, "radius"] = new_radius
                applied.append(f"Node {node_id}: {old_radius:.5g} -> {new_radius:.5g}")
            if not applied:
                return
            self._apply_document_dataframe(
                doc,
                df,
                event_title="Apply Suggested Radii",
                event_summary=f"Applied suggested radii to {len(applied)} nodes.",
                event_details=applied[:20] + [f"Issue: {issue_id}"],
            )
            self._append_log(f"Applied suggested radii to {len(applied)} nodes.", "INFO")
            self._rerun_active_validation(resolved_issue_id=issue_id)
            return

        if source_key == "type_suspicion_batch":
            changes = list(payload.get("changes", []) or [])
            if not changes:
                return
            df = doc.df.copy()
            applied = []
            for item in changes:
                node_id = int(item.get("node_id", -1))
                mask = df["id"] == node_id
                if not bool(mask.any()):
                    continue
                old_type = int(df.loc[mask, "type"].iloc[0])
                new_type = int(item.get("new_type", old_type))
                df.loc[mask, "type"] = new_type
                applied.append(f"Node {node_id}: {old_type} -> {new_type}")
            if not applied:
                return
            self._apply_document_dataframe(
                doc,
                df,
                event_title="Apply Suggested Labels",
                event_summary=f"Applied suggested labels to {len(applied)} nodes.",
                event_details=applied[:20] + [f"Issue: {issue_id}"],
            )
            self._append_log(f"Applied suggested labels to {len(applied)} nodes.", "INFO")
            self._rerun_active_validation(resolved_issue_id=issue_id)

    def _on_skip_issue_requested(self, issue_id: str, skipping: bool):
        doc = self._active_document()
        if doc is None:
            return
        key = str(issue_id or "").strip()
        if not key:
            return
        if skipping:
            doc.issue_status_overrides[key] = "muted"
        else:
            doc.issue_status_overrides.pop(key, None)
        for item in doc.issues:
            if str(item.get("issue_id", "")).strip() == key:
                item["status"] = "muted" if skipping else "open"
        self._apply_issue_state(doc)
        if self._issue_panel.select_issue(key):
            self._on_issue_selected(next((item for item in doc.issues if str(item.get("issue_id", "")).strip() == key), None) or {})

    def _on_context_open_tool_requested(self, tool_target: str):
        target = str(tool_target or "").strip().lower()
        if target in {"label_editing", "auto_label", "radii_cleaning", "manual_radii"}:
            self._activate_feature("morphology_editing")
            target_tab = {
                "label_editing": "manual label editing",
                "auto_label": "auto label editing",
                "manual_radii": "manual radii editing",
                "radii_cleaning": "auto radii editing",
            }.get(target, "manual label editing")
            self._select_control_tab_by_label(target_tab)
            return
        if target == "simplification":
            self._activate_feature("geometry_editing")
            self._select_control_tab_by_label("simplification")
            return
        if target == "geometry_editing":
            self._activate_feature("geometry_editing")
            self._select_control_tab_by_label("geometry editing")
            return
        self._route_issue_to_tool({"tool_target": target})

    def _on_context_custom_action_requested(self, issue_id: str, action_id: str):
        action = str(action_id or "").strip().lower()
        if action == "open_manual_label_popup":
            self._control_tabs.setVisible(True)
            self._activate_feature("morphology_editing")
            self._select_control_tab_by_label("manual label editing")
            return
        if action == "open_auto_label_popup":
            self._control_tabs.setVisible(True)
            self._activate_feature("morphology_editing")
            self._select_control_tab_by_label("auto label editing")
            return
        if action == "open_manual_radii_tool":
            self._control_tabs.setVisible(True)
            self._activate_feature("morphology_editing")
            self._select_control_tab_by_label("manual radii editing")
            return
        if action == "open_auto_radii_tool":
            self._control_tabs.setVisible(True)
            self._activate_feature("morphology_editing")
            self._select_control_tab_by_label("auto radii editing")
            return
        if action == "open_simplification_tool":
            self._control_tabs.setVisible(True)
            self._activate_feature("geometry_editing")
            self._select_control_tab_by_label("simplification")
            return
        if action == "consolidate_soma":
            doc = self._active_document()
            issue = self._find_issue_by_id(doc, issue_id)
            if doc is None or issue is None or doc.df is None or doc.df.empty:
                return
            arr = np.zeros(
                len(doc.df),
                dtype=[
                    ("id", np.int64),
                    ("type", np.int64),
                    ("x", np.float64),
                    ("y", np.float64),
                    ("z", np.float64),
                    ("radius", np.float64),
                    ("parent", np.int64),
                ],
            )
            for col in SWC_COLS:
                arr[col] = doc.df[col].to_numpy()
            result = consolidate_complex_somas_array(arr)
            final_arr = np.array(result.get("array", arr), copy=True)
            if final_arr.size == 0:
                return
            new_df = pd.DataFrame({col: final_arr[col] for col in SWC_COLS}, columns=SWC_COLS)
            new_df["id"] = new_df["id"].astype(int)
            new_df["type"] = new_df["type"].astype(int)
            new_df["parent"] = new_df["parent"].astype(int)
            group_infos = list(result.get("groups", []) or [])
            changed = bool(result.get("changed"))
            removed_nodes = max(0, int(arr.size) - int(final_arr.size))
            event_details = [
                f"Collapsed soma groups: {int(result.get('group_count', 0))}",
                f"Complex groups changed: {len(list(result.get('complex_groups', []) or []))}",
                f"Removed soma nodes: {removed_nodes}",
                "Surviving node IDs are preserved; consolidation does not renumber the SWC.",
            ]
            for group in group_infos[:10]:
                event_details.append(
                    f"Anchor {int(group.get('anchor_id', -1))}: "
                    f"{int(group.get('group_size', 0))} node(s) -> radius {float(group.get('radius', 0.0)):.5g}"
                )
            if not changed:
                event_details.append("No connected multi-node soma groups required consolidation.")
            self._apply_document_dataframe(
                doc,
                new_df,
                event_title="Consolidate Soma",
                event_summary=(
                    f"Collapsed {len(list(result.get('complex_groups', []) or []))} complex soma group(s) "
                    f"into mega-node representation."
                ),
                event_details=event_details,
            )
            self._append_log(
                f"Consolidated soma representation: groups={int(result.get('group_count', 0))}, removed_nodes={removed_nodes}.",
                "INFO",
            )
            self._rerun_active_validation(resolved_issue_id=issue_id)
            return
        if action == "split_trees":
            doc = self._active_document()
            issue = self._find_issue_by_id(doc, issue_id) if doc is not None else None
            saved_paths = list(self._validation_tab._on_save_all() or [])
            if not saved_paths:
                return
            if doc is not None and not doc.is_preview:
                payload = dict((issue or {}).get("source_payload", {}) or {})
                soma_ids = list(payload.get("metrics", {}).get("soma_ids_after_consolidation", []) or [])
                event_details = [
                    f"Original file: {doc.file_path or doc.filename}",
                    f"Disconnected soma groups: {len(soma_ids)}",
                    f"Split output files: {len(saved_paths)}",
                ]
                preview_limit = 12
                for out_path in saved_paths[:preview_limit]:
                    event_details.append(f"Output: {out_path}")
                if len(saved_paths) > preview_limit:
                    event_details.append(f"... and {len(saved_paths) - preview_limit} more output file(s)")
                self._record_session_event(
                    doc,
                    kind="split",
                    title="Split Trees",
                    summary=f"Split {doc.filename or 'SWC'} into {len(saved_paths)} output SWC file(s).",
                    details=event_details,
                )
            first_path = str(saved_paths[0])
            reply = QMessageBox.question(
                self,
                "Open First Split Tree",
                (
                    f"Saved {len(saved_paths)} split SWC file(s).\n\n"
                    f"Do you want to open the first tree now?\n{first_path}"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._load_swc(first_path)
            return
        if action == "download_validation_report":
            self._validation_tab._on_download_report()
            return
        if action == "define_custom_types":
            doc = self._active_document()
            issue = self._find_issue_by_id(doc, issue_id)
            if not issue:
                return
            payload = dict(issue.get("source_payload", {}) or {})
            missing_defs = list(payload.get("metrics", {}).get("undefined_custom_types", []) or [])
            if not missing_defs:
                return
            dialog = DefineCustomTypesDialog(missing_defs, self)
            if dialog.exec() != QDialog.Accepted:
                return
            if doc is not None:
                doc.editor.load_swc(doc.df, doc.filename)
                self._table_widget.load_dataframe(doc.df, doc.filename)
            self._append_log(f"Saved {len(missing_defs)} custom type definition(s).", "INFO")
            self._rerun_active_validation(resolved_issue_id=issue_id)
            return

    def _on_issue_panel_export_swc_requested(self):
        self._on_export()

    def _toggle_data_panel(self, checked: bool):
        self._data_dock.setVisible(bool(checked))

    def _toggle_control_panel(self, checked: bool):
        self._control_dock.setVisible(bool(checked))

    def _toggle_precheck_panel(self, checked: bool):
        if checked:
            self._show_precheck_floating()
        else:
            self._precheck_dock.hide()

    def _toggle_auto_typing_guide_panel(self, checked: bool):
        if checked:
            if self._is_auto_label_control_active():
                self._show_auto_typing_guide_floating()
            else:
                self._auto_guide_dock.hide()
                self._append_log(
                    "Auto Typing Guide opens when an Auto Label Editing control tab is active.",
                    "INFO",
                )
        else:
            self._auto_guide_dock.hide()

    def _toggle_log_panel(self, checked: bool):
        self._bottom_log_title.setVisible(bool(checked))
        self._edit_log_text.setVisible(bool(checked))

    def _show_precheck_floating(self):
        self._precheck_dock.show()
        self._precheck_dock.setFloating(True)
        g = self.geometry()
        w = max(760, int(g.width() * 0.62))
        h = max(360, int(g.height() * 0.36))
        x = g.x() + max(40, int((g.width() - w) * 0.5))
        y = g.y() + 120
        self._precheck_dock.setGeometry(x, y, w, h)
        self._precheck_dock.raise_()

    def _show_auto_typing_guide_floating(self):
        self._auto_typing_guide.refresh()
        self._auto_guide_dock.show()
        self._auto_guide_dock.setFloating(True)
        g = self.geometry()
        w = max(760, int(g.width() * 0.62))
        h = max(360, int(g.height() * 0.36))
        x = g.x() + max(40, int((g.width() - w) * 0.5))
        y = g.y() + 160
        self._auto_guide_dock.setGeometry(x, y, w, h)
        self._auto_guide_dock.raise_()

    def _is_auto_label_control_active(self) -> bool:
        if self._active_tool not in ("batch", "validation"):
            return False
        idx = self._control_tabs.currentIndex()
        if idx < 0:
            return False
        label = self._control_tabs.tabText(idx).strip().lower()
        return label == "auto label editing"

    def _is_batch_validation_control_active(self) -> bool:
        if self._active_tool != "batch":
            return False
        idx = self._control_tabs.currentIndex()
        if idx < 0:
            return False
        label = self._control_tabs.tabText(idx).strip().lower()
        return label == "validation"

    def _on_control_tab_changed(self, _index: int):
        # Do not auto-popup guide docks on tab/tool switches.
        # Guides are opened only by explicit user actions.
        if hasattr(self, "_auto_guide_dock"):
            self._auto_guide_dock.hide()
        if hasattr(self, "_precheck_dock"):
            self._precheck_dock.hide()
        if self._active_tool in ("morphology_editing", "dendrogram"):
            self._refresh_simplification_panel_state()
            idx = self._control_tabs.currentIndex()
            if idx >= 0:
                label = self._control_tabs.tabText(idx).strip().lower()
                if label == "manual radii editing":
                    self._manual_radii_panel.ensure_stats_loaded()
                elif label == "auto radii editing":
                    self._validation_radii_panel.ensure_stats_loaded()
        self._refresh_canvas_surface()
        self._sync_top_feature_button_selection()

    def _on_precheck_requested(self):
        self._show_precheck_floating()

    def _on_batch_validation_ready(self, report: dict):
        self._batch_canvas.show_batch_validation_results(report)
        self._batch_canvas.set_mode(EditorTab.MODE_BATCH)
        self._batch_has_results = True
        self._refresh_canvas_surface()
        if self._active_tool == "batch":
            self._feature_label.setText("Active feature: Batch Processing")
        totals = dict(report.get("summary_total", {}))
        self._append_log(
            "Batch validation results loaded to canvas: "
            f"files={report.get('files_validated', 0)}/{report.get('files_total', 0)}, "
            f"pass={totals.get('pass', 0)}, warn={totals.get('warning', 0)}, "
            f"fail={totals.get('fail', 0)}",
            "INFO",
        )

    def _undo_edit(self):
        if self._undo_document(self._active_source_document()):
            self._append_log("Undo.", "INFO")

    def _redo_edit(self):
        if self._redo_document(self._active_source_document()):
            self._append_log("Redo.", "INFO")

    def closeEvent(self, event):
        close_plans: list[tuple[_DocumentState, dict]] = []
        self._closing_app = True

        if hasattr(self, "_validation_tab"):
            self._validation_tab.stop_worker(wait_ms=5000)

        for doc in list(self._documents.values()):
            close_plan = self._plan_document_close(doc, app_closing=True)
            if close_plan is None:
                self._closing_app = False
                event.ignore()
                return
            close_plans.append((doc, close_plan))

        for doc, close_plan in close_plans:
            if not self._apply_document_close_plan(doc, close_plan):
                self._closing_app = False
                event.ignore()
                return

        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_current_file_label_text(self._filename)

    # ---------------- Help ----------------
    def _show_help_text_dialog(self, title: str, text: str):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Information)
        box.setText(title)
        box.setInformativeText(text.replace("\n", "<br>"))
        box.exec()

    def _show_quick_manual(self):
        text = (
            "1) Top menu row: File/Edit/View/Window/Help dropdown menus.\n"
            "2) Tools bar: choose a tool, then choose its feature row under it.\n"
            "3) Issue Navigator and Inspector are dock windows (close, float, resize, move).\n"
            "4) You can open multiple SWC files as canvas tabs.\n"
            "5) Drag a canvas tab outside the tab bar to detach it into a floating window.\n"
            "6) Closing a SWC tab/window always asks for confirmation; edited SWC copies are only written when you confirm the close-save dialog.\n"
            "7) Opening an SWC runs checks and populates the Issue Navigator automatically.\n"
            "8) Clicking an issue focuses the viewer and opens the related repair workflow.\n"
            "9) Bottom panel shows all logs and warnings."
        )
        self._show_help_text_dialog("Quick Manual", text)
        self._append_log(text, "HELP")

    def _show_shortcuts(self):
        text = (
            "Ctrl+O: Open\n"
            "Ctrl+S: Save\n"
            "Ctrl+Shift+S: Save As\n"
            "Ctrl+Z: Undo\n"
            "Ctrl+Shift+Z: Redo"
        )
        self._show_help_text_dialog("Shortcuts", text)
        self._append_log(text, "HELP")

    def _show_about_dialog(self):
        text = (
            "SWC-Studio is an issue-driven workspace for inspecting, repairing, "
            "and exporting neuron morphology files in SWC format.\n\n"
            "It provides a shared desktop GUI, CLI, and Python backend so the "
            "same validation and editing logic can be used interactively or in scripts."
        )
        self._show_help_text_dialog("About SWC-Studio", text)
        self._append_log("Opened About dialog.", "INFO")
