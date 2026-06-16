"""Validation control panel: single-file auto label editing applied in-place.

The auto-labeling engine is the v12 QC-label-flag pipeline; the user can
optionally override the model directory to point at custom-trained models.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from swcstudio.core.auto_typing import (
    BatchOptions,
    backend_status,
    get_config as get_auto_typing_config,
    is_available,
    save_config as save_auto_typing_config,
)
from swcstudio.core.config import feature_config_path

_CFG_PATH = feature_config_path("batch_processing", "auto_typing")


class _AutoTypingConfigDialog(QDialog):
    saved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Auto-Typing JSON")
        self.resize(820, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        path_label = QLabel(f"Config file: {_CFG_PATH}")
        path_label.setWordWrap(True)
        path_label.setStyleSheet("font-size: 12px; color: #555;")
        root.addWidget(path_label)

        self._editor = QPlainTextEdit()
        self._editor.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #fafafa; border: 1px solid #ddd; color: #333;"
            "  font-family: Menlo, Consolas, monospace; font-size: 12px;"
            "}"
        )
        root.addWidget(self._editor, stretch=1)

        btn_row = QHBoxLayout()
        self._btn_reload = QPushButton("Reload")
        self._btn_reload.clicked.connect(self.reload_from_source)
        btn_row.addWidget(self._btn_reload)

        self._btn_save = QPushButton("Save")
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        btn_row.addStretch()
        self._status = QLabel("")
        self._status.setStyleSheet("font-size: 12px; color: #555;")
        btn_row.addWidget(self._status)

        self._btn_close = QPushButton("Close")
        self._btn_close.clicked.connect(self.close)
        btn_row.addWidget(self._btn_close)
        root.addLayout(btn_row)

        self.reload_from_source()

    def reload_from_source(self):
        try:
            txt = json.dumps(get_auto_typing_config(), indent=2, sort_keys=True)
            self._editor.setPlainText(txt)
            self._status.setText("Loaded.")
        except Exception as e:  # noqa: BLE001
            self._status.setText(f"Load failed: {e}")

    def _on_save(self):
        try:
            data = json.loads(self._editor.toPlainText())
            if not isinstance(data, dict):
                raise ValueError("JSON root must be an object")
            save_auto_typing_config(data)
            self._status.setText("Saved.")
            self.saved.emit("Auto-typing JSON saved.")
        except Exception as e:  # noqa: BLE001
            self._status.setText(f"Save failed: {e}")


class ValidationAutoLabelPanel(QWidget):
    # Emit (BatchOptions, settings_dict). The dict carries
    # ``{"model_dir": str|None}`` so the main window can pass it as
    # ``config_overrides`` to the auto-label entry point.
    process_requested = Signal(object, object)
    guide_requested = Signal()
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config_dialog: _AutoTypingConfigDialog | None = None
        self._build_ui()
        self.set_preview_state(False, None)
        self._refresh_backend_status()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.setAlignment(Qt.AlignTop)

        desc = QLabel(
            "Auto-label every node of the current SWC with the QC-label-flag "
            "pipeline: input QC, cell-type detection or override, subtree "
            "labeling, pyramidal apical/basal GNN rescue, topology cleanup, "
            "and compact bad-label flag scoring."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #555;")
        root.addWidget(desc)

        # ---- model dir picker (optional override)
        self._model_row = QHBoxLayout()
        self._model_row.setSpacing(6)
        model_lbl = QLabel("Model dir (optional):")
        model_lbl.setStyleSheet("font-size: 12px; color: #333;")
        self._model_row.addWidget(model_lbl)
        self._edit_model_dir = QLineEdit()
        self._edit_model_dir.setPlaceholderText("Leave blank for default models")
        self._edit_model_dir.setToolTip("Leave blank to use bundled / user-data models.")
        self._edit_model_dir.setFixedWidth(260)
        self._edit_model_dir.editingFinished.connect(self._refresh_backend_status)
        self._model_row.addWidget(self._edit_model_dir)
        self._btn_browse_model = QPushButton("Browse…")
        self._btn_browse_model.setText("Browse...")
        self._btn_browse_model.setFixedWidth(96)
        self._btn_browse_model.clicked.connect(self._on_browse_model_dir)
        self._model_row.addWidget(self._btn_browse_model)
        self._backend_status_lbl = QLabel("")
        self._backend_status_lbl.setStyleSheet("font-size: 11px; color: #888;")
        self._model_row.addWidget(self._backend_status_lbl)
        self._model_row.addStretch()
        root.addLayout(self._model_row)

        option_row = QHBoxLayout()
        option_row.setSpacing(8)
        cell_lbl = QLabel("Cell type:")
        cell_lbl.setStyleSheet("font-size: 12px; color: #333;")
        option_row.addWidget(cell_lbl)
        self._cell_type_combo = QComboBox()
        self._cell_type_combo.addItem("Unknown", "unknown")
        self._cell_type_combo.addItem("Pyramidal", "pyramidal")
        self._cell_type_combo.addItem("Interneuron", "interneuron")
        option_row.addWidget(self._cell_type_combo)
        self._flag_enabled = QCheckBox("Flag")
        self._flag_enabled.setChecked(True)
        option_row.addWidget(self._flag_enabled)
        strict_lbl = QLabel("Strictness:")
        strict_lbl.setStyleSheet("font-size: 12px; color: #333;")
        option_row.addWidget(strict_lbl)
        loose_lbl = QLabel("Loose")
        loose_lbl.setStyleSheet("font-size: 11px; color: #666;")
        option_row.addWidget(loose_lbl)
        self._flag_slider = QSlider(Qt.Horizontal)
        self._flag_slider.setRange(0, 100)
        self._flag_slider.setValue(50)
        self._flag_slider.setFixedWidth(120)
        option_row.addWidget(self._flag_slider)
        strict_side_lbl = QLabel("Strict")
        strict_side_lbl.setStyleSheet("font-size: 11px; color: #666;")
        option_row.addWidget(strict_side_lbl)
        self._flag_strictness_spin = QDoubleSpinBox()
        self._flag_strictness_spin.setRange(0.0, 1.0)
        self._flag_strictness_spin.setSingleStep(0.01)
        self._flag_strictness_spin.setDecimals(2)
        self._flag_strictness_spin.setValue(0.50)
        self._flag_strictness_spin.setFixedWidth(72)
        self._flag_strictness_spin.setToolTip(
            "Flag strictness from 0.00 loose to 1.00 strict."
        )
        option_row.addWidget(self._flag_strictness_spin)
        self._flag_slider.valueChanged.connect(
            lambda value: self._flag_strictness_spin.setValue(float(value) / 100.0)
        )
        self._flag_strictness_spin.valueChanged.connect(
            lambda value: self._flag_slider.setValue(int(round(float(value) * 100.0)))
        )
        option_row.addStretch()
        root.addLayout(option_row)

        top_btns = QHBoxLayout()
        self._btn_run = QPushButton("Run")
        self._btn_run.clicked.connect(
            lambda: self.process_requested.emit(
                self.current_options(), self.current_settings()
            )
        )
        top_btns.addWidget(self._btn_run)
        self._btn_edit_cfg = QPushButton("Show JSON")
        self._btn_edit_cfg.clicked.connect(self._on_edit_auto_typing_json)
        top_btns.addWidget(self._btn_edit_cfg)
        top_btns.addStretch()
        root.addLayout(top_btns)

        # Busy indicator: indeterminate progress bar (range 0-0) shown
        # only while a worker is running. Single-file inference is short
        # enough that a percentage-based bar isn't useful.
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._progress.setMaximumHeight(8)
        root.addWidget(self._progress)

        self._summary = QPlainTextEdit()
        self._summary.setReadOnly(True)
        self._summary.setMinimumHeight(160)
        self._summary.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #fafafa; border: 1px solid #ddd; color: #333;"
            "  font-family: Menlo, Consolas, monospace; font-size: 12px;"
            "}"
        )
        root.addWidget(self._summary, stretch=1)

    @staticmethod
    def _display_feature_mode(raw: object) -> str:
        _ = raw
        return "Simple"

    def current_options(self) -> BatchOptions:
        return BatchOptions(
            soma=True,
            axon=True,
            apic=True,
            basal=True,
            rad=False,
            zip_output=False,
            cell_type=self._cell_type_combo.currentData() or "unknown",
            flag_enabled=self._flag_enabled.isChecked(),
            flag_strictness=float(self._flag_slider.value()) / 100.0,
            flag_feature_mode="compact",
        )

    def current_settings(self) -> dict:
        """Return ``{"model_dir": str|None}``."""
        model_dir = (self._edit_model_dir.text() or "").strip() or None
        return {
            "model_dir": model_dir,
            "cell_type": self._cell_type_combo.currentData() or "unknown",
            "flag_enabled": self._flag_enabled.isChecked(),
            "flag_strictness": float(self._flag_slider.value()) / 100.0,
            "flag_feature_mode": "compact",
        }

    def _on_browse_model_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select directory containing auto-typing model files"
        )
        if path:
            self._edit_model_dir.setText(path)
            self._refresh_backend_status()

    def _refresh_backend_status(self) -> None:
        md = (self._edit_model_dir.text() or "").strip() or None
        ok, reason = is_available(model_dir=md)
        if ok:
            self._backend_status_lbl.setText("ready")
            self._backend_status_lbl.setStyleSheet("font-size: 11px; color: #2a7;")
            self._backend_status_lbl.setToolTip("All required model files are loaded.")
        else:
            self._backend_status_lbl.setText("unavailable — see details")
            self._backend_status_lbl.setStyleSheet("font-size: 11px; color: #c33;")
            self._backend_status_lbl.setToolTip(str(reason))

    def _on_edit_auto_typing_json(self):
        if self._config_dialog is None:
            self._config_dialog = _AutoTypingConfigDialog(self)
            self._config_dialog.saved.connect(self.log_message.emit)
        self._config_dialog.reload_from_source()
        self._config_dialog.show()
        self._config_dialog.raise_()
        self._config_dialog.activateWindow()

    def set_preview_state(self, has_preview: bool, summary: dict | None):
        _ = has_preview

        if not summary:
            self._summary.setPlainText(
                "No auto-label result yet.\n"
                "Use Run to apply auto-label editing to the current canvas."
            )
            return

        out_counts = dict(summary.get("out_type_counts", {}))
        flag_result = dict(summary.get("flag_result", {}) or {})
        lines = [
            "Auto Label Editing Result",
            "-------------------------",
            f"Nodes processed: {summary.get('nodes_total', 0)}",
            f"Type changes: {summary.get('type_changes', 0)}",
            f"Radius changes: {summary.get('radius_changes', 0)}",
            f"Cell type: {summary.get('cell_type') or 'unknown'} ({summary.get('cell_type_source') or 'stage1'})",
            f"Flagged: {bool(flag_result.get('flagged', False))}",
            (
                "Output types (soma/axon/basal/apic): "
                f"{out_counts.get(1, 0)}/{out_counts.get(2, 0)}/{out_counts.get(3, 0)}/{out_counts.get(4, 0)}"
            ),
        ]
        if flag_result:
            lines.append(
                f"Flag score: {float(flag_result.get('rank_score', 0.0)):.4f} "
                f"(prob_bad={float(flag_result.get('prob_bad', 0.0)):.4f})"
            )
            lines.append(
                "Flag features: "
                f"{self._display_feature_mode(flag_result.get('actual_feature_mode') or flag_result.get('selected_feature_mode'))}"
            )
            if flag_result.get("error"):
                lines.append(f"Flag error: {flag_result.get('error')}")
        log_path = str(summary.get("log_path", "") or "").strip()
        if log_path:
            lines.extend(["", f"Log file: {log_path}"])
        self._summary.setPlainText("\n".join(lines))

    def set_status_text(self, text: str):
        self._summary.setPlainText(str(text or ""))

    def set_running(self, running: bool, status_text: str | None = None) -> None:
        """Toggle the running state — disables interactive controls and
        shows a busy progress bar while a worker is in flight."""
        self._progress.setVisible(bool(running))
        self._btn_run.setEnabled(not running)
        self._btn_edit_cfg.setEnabled(not running)
        self._edit_model_dir.setEnabled(not running)
        self._btn_browse_model.setEnabled(not running)
        self._cell_type_combo.setEnabled(not running)
        self._flag_enabled.setEnabled(not running)
        self._flag_slider.setEnabled(not running)
        self._flag_strictness_spin.setEnabled(not running)
        if running and status_text:
            self._summary.setPlainText(str(status_text))
