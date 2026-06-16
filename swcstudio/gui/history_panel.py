"""GUI provenance widgets: timeline + branch picker + detail view.

Implements PROVENANCE_SPEC §14 GUI surface (v1). Built as a single
self-contained QWidget that the main window can host as a dock or
open as a modal dialog — no changes to ``main_window.py`` required
to land this slice.

Wiring (recommended single-line addition to ``main_window.py``)::

    from swcstudio.gui.history_panel import open_history_dialog
    # ... inside a menu/action handler:
    open_history_dialog(self, current_file)

That's the full GUI integration in slice 11. Slice 12 (converting GUI
*actions* to use tracked_op/tracked_session) is a separate, larger
change that this panel does not depend on.

The widget:

* Lists every commit on every branch in a sortable table.
* Filter chips for actor, kind, branch (no SQL exposure).
* Click a row → right-pane detail view with the
  ``render_commit_text`` output.
* Branch picker dropdown to switch the active branch.
* ``Mark as checkpoint`` button materializes a labeled .swc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from swcstudio.core.provenance import (
    DEFAULT_BRANCH,
    OpKind,
    archive_history_dir,
    archive_path_for,
    create_tag,
    ensure_schema,
    ensure_history_materialized,
    history_dir_for,
    history_archive_exists,
    list_branches,
    list_tags,
    open_index,
    query_commits,
    read_branch,
    read_head,
    render_commit_text,
    write_head,
)

__all__ = ["HistoryPanel", "open_history_dialog"]


class HistoryPanel(QWidget):
    """Self-contained provenance browser for a single SWC file."""

    commit_selected = Signal(str)  # emits commit_sha when user clicks a row
    reverted_to_state = Signal(str, bytes)  # (target_sha, new_swc_bytes) — emitted after Revert

    def __init__(self, swc_path: str | Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._swc_path = Path(swc_path)
        self._hist = history_dir_for(self._swc_path)
        ensure_history_materialized(self._swc_path, self._hist)
        self._build_ui()
        self.refresh()

    def closeEvent(self, event) -> None:
        if self._hist.exists():
            archive_history_dir(self._hist, self._swc_path, remove_dir=True)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Top toolbar — branch picker + filter chips
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Branch:"))
        self._branch_combo = QComboBox()
        self._branch_combo.currentTextChanged.connect(self._on_branch_changed)
        toolbar.addWidget(self._branch_combo)

        self._switch_btn = QPushButton("Switch")
        self._switch_btn.clicked.connect(self._on_switch_clicked)
        toolbar.addWidget(self._switch_btn)

        self._new_branch_btn = QPushButton("New branch…")
        self._new_branch_btn.clicked.connect(self._on_new_branch_clicked)
        toolbar.addWidget(self._new_branch_btn)

        toolbar.addSpacing(20)
        toolbar.addWidget(QLabel("Actor:"))
        self._actor_filter = QLineEdit()
        self._actor_filter.setPlaceholderText("(any)")
        self._actor_filter.setMaximumWidth(140)
        self._actor_filter.textChanged.connect(self.refresh)
        toolbar.addWidget(self._actor_filter)

        toolbar.addWidget(QLabel("Since:"))
        self._since_filter = QLineEdit()
        self._since_filter.setPlaceholderText("YYYY-MM-DD")
        self._since_filter.setMaximumWidth(120)
        self._since_filter.textChanged.connect(self.refresh)
        toolbar.addWidget(self._since_filter)

        toolbar.addStretch(1)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self._refresh_btn)

        layout.addLayout(toolbar)

        # Splitter: timeline table | detail view
        splitter = QSplitter(Qt.Horizontal)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["sha", "ts", "actor", "branch", "message"])
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self._table)

        right = QFrame()
        rlayout = QVBoxLayout(right)
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setFontFamily("Menlo, Consolas, monospace")
        rlayout.addWidget(self._detail, 1)

        row_buttons = QHBoxLayout()
        # Primary action: revert to the selected commit. Creates a new
        # commit on the current branch whose content equals the selected
        # past commit, then emits reverted_to_state so the main window
        # can reload the document.
        self._revert_btn = QPushButton("Revert to this commit…")
        self._revert_btn.setToolTip(
            "Materialize the selected commit's state, record a new commit "
            "on the active branch capturing the revert, and reload the "
            "open document. Nothing is lost — the intervening commits "
            "stay in history."
        )
        self._revert_btn.clicked.connect(self._on_revert_clicked)
        self._revert_btn.setEnabled(False)
        row_buttons.addWidget(self._revert_btn)

        # Read-only alternative: write the past state to a chosen file
        # path WITHOUT touching the open document or history.
        self._checkout_btn = QPushButton("Checkout to file…")
        self._checkout_btn.setToolTip(
            "Materialize the selected commit's state to a separate .swc "
            "file. Does NOT change history or the active document."
        )
        self._checkout_btn.clicked.connect(self._on_checkout_clicked)
        self._checkout_btn.setEnabled(False)
        row_buttons.addWidget(self._checkout_btn)

        self._checkpoint_btn = QPushButton("Mark as checkpoint…")
        self._checkpoint_btn.clicked.connect(self._on_checkpoint_clicked)
        self._checkpoint_btn.setEnabled(False)
        row_buttons.addWidget(self._checkpoint_btn)

        self._tag_btn = QPushButton("Tag commit…")
        self._tag_btn.clicked.connect(self._on_tag_clicked)
        self._tag_btn.setEnabled(False)
        row_buttons.addWidget(self._tag_btn)

        row_buttons.addStretch(1)
        rlayout.addLayout(row_buttons)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # data loading
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload branches and the commit table."""
        if not self._hist.exists():
            self._table.setRowCount(0)
            self._detail.setPlainText(
                f"No history archive at {archive_path_for(self._swc_path)}\n\n"
                f"Run 'swcstudio history init {self._swc_path}' to start tracking."
            )
            return

        # Branch dropdown
        head = read_head(self._hist)
        branches = list_branches(self._hist)
        # Block signals while we rebuild so currentTextChanged doesn't
        # fire spuriously and trigger an unwanted refresh.
        self._branch_combo.blockSignals(True)
        self._branch_combo.clear()
        self._branch_combo.addItems(branches)
        if head in branches:
            self._branch_combo.setCurrentText(head)
        self._branch_combo.blockSignals(False)

        # Commit table
        conn = open_index(self._hist)
        try:
            ensure_schema(conn)
            actor = self._actor_filter.text().strip() or None
            since = self._since_filter.text().strip() or None
            rows = query_commits(
                conn,
                branch=self._branch_combo.currentText() or None,
                actor=actor,
                since=since,
                limit=500,
            )
        finally:
            conn.close()

        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            short = (r["sha"] or "").removeprefix("sha256:")[:12]
            items = [
                short,
                r["ts"] or "",
                r["os_user"] or "",
                r["branch"] or "",
                r["message"] or "",
            ]
            for j, text in enumerate(items):
                cell = QTableWidgetItem(text)
                if j == 0:
                    # Keep the full sha on the row for later retrieval.
                    cell.setData(Qt.UserRole, r["sha"])
                self._table.setItem(i, j, cell)

        self._detail.clear()
        self._checkpoint_btn.setEnabled(False)
        self._tag_btn.setEnabled(False)
        self._revert_btn.setEnabled(False)
        self._checkout_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # signal handlers
    # ------------------------------------------------------------------

    def _on_branch_changed(self, _name: str) -> None:
        self.refresh()

    def _on_row_selected(self) -> None:
        sha = self._current_selection_sha()
        if not sha:
            return
        try:
            text = render_commit_text(self._hist, sha)
        except Exception as e:  # pragma: no cover - defensive
            text = f"(error rendering commit: {e})"
        self._detail.setPlainText(text)
        self._checkpoint_btn.setEnabled(True)
        self._tag_btn.setEnabled(True)
        self._revert_btn.setEnabled(True)
        self._checkout_btn.setEnabled(True)
        self.commit_selected.emit(sha)

    def _on_switch_clicked(self) -> None:
        target = self._branch_combo.currentText().strip()
        if not target:
            return
        try:
            write_head(self._hist, target)
        except Exception as e:
            QMessageBox.warning(self, "Switch branch", str(e))
            return
        QMessageBox.information(
            self,
            "Switch branch",
            f"Active branch is now {target!r}. "
            f"Future commits will land on this branch.",
        )
        self.refresh()

    def _on_new_branch_clicked(self) -> None:
        sha = self._current_selection_sha()
        if not sha:
            QMessageBox.information(
                self, "New branch",
                "Select a commit in the table to branch from.",
            )
            return
        name, ok = QInputDialog.getText(self, "New branch", "Branch name:")
        if not ok or not name.strip():
            return
        from swcstudio.core.provenance import write_branch, RefError
        try:
            write_branch(self._hist, name.strip(), sha)
        except RefError as e:
            QMessageBox.warning(self, "New branch", str(e))
            return
        QMessageBox.information(
            self, "New branch",
            f"Created branch {name.strip()!r} at {sha[:19]}.",
        )
        self.refresh()

    def _on_revert_clicked(self) -> None:
        """Revert to the selected commit's state.

        Creates a NEW commit on the active branch whose content equals
        the selected past commit, then emits ``reverted_to_state`` so
        the host main window can reload the open document.

        Nothing is destroyed: the intervening commits stay in
        ``events.jsonl`` and are still reachable. The new commit just
        sits at the active branch's tip with the past state.

        Two no-op cases are detected and surfaced as friendly
        messages instead of silently creating phantom commits:
          * Selecting the active branch's tip (the current state
            itself — there's nothing to revert).
          * Selecting a commit whose content equals the current state
            (rare: e.g., reverting twice in a row to the same target).
        """
        from swcstudio.cli.history_cli import _materialize_state_at  # noqa: PLC0415
        from swcstudio.core.provenance import OpKind, tracked_op  # noqa: PLC0415
        from swcstudio.core.provenance import read_branch, read_head  # noqa: PLC0415

        sha = self._current_selection_sha()
        if not sha:
            return

        # Detect "revert to current tip" — refuse with a clear message.
        try:
            head = read_head(self._hist)
            tip = read_branch(self._hist, head)
        except Exception:
            tip = None
        if tip and tip == sha:
            QMessageBox.information(
                self,
                "Revert",
                f"Commit {sha.removeprefix('sha256:')[:12]} is already "
                f"the tip of '{head}' — it IS your current state, so "
                f"there's nothing to revert to.\n\n"
                f"To see revert in action, make a few more edits first "
                f"(each one becomes its own commit), then come back here "
                f"and click an EARLIER commit to revert to.\n\n"
                f"Tip: 'Mark as checkpoint…' on this commit if you want "
                f"to save the current state as a separate labeled .swc.",
            )
            return

        # Confirm — this changes the active branch.
        reply = QMessageBox.question(
            self,
            "Revert to this commit?",
            (
                f"Revert the open document to commit "
                f"{sha.removeprefix('sha256:')[:12]}?\n\n"
                "A NEW commit will be added on the active branch "
                "capturing this revert. Intervening commits are kept "
                "in history and can be reached again later.\n\n"
                "Any unsaved in-memory edits in the GUI will be lost."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            past_bytes = _materialize_state_at(self._hist, sha)
        except Exception as e:
            QMessageBox.warning(self, "Revert", f"Could not materialize past state: {e}")
            return

        # Second no-op guard: if the past state is byte-identical to the
        # current state (rare but possible — e.g., user changed value
        # then changed it back), warn instead of writing a phantom commit.
        from swcstudio.core.provenance import (  # noqa: PLC0415
            canonical_swc,
            current_swc_path_for,
            sha256_hex,
            strip_prov_lines,
        )
        cur_path = current_swc_path_for(self._swc_path)
        if cur_path.exists():
            cur_canon = sha256_hex(canonical_swc(strip_prov_lines(cur_path.read_bytes())))
            past_canon = sha256_hex(canonical_swc(past_bytes))
            if cur_canon == past_canon:
                QMessageBox.information(
                    self, "Revert",
                    f"Commit {sha.removeprefix('sha256:')[:12]} has the SAME "
                    f"content as your current state — nothing would change.\n\n"
                    f"This usually means the selected commit is logically "
                    f"equivalent to the tip even though it has a different sha "
                    f"(e.g., the file was already in this state earlier).",
                )
                return

        # Record a new commit on the active branch capturing the revert.
        try:
            with tracked_op(
                self._swc_path,
                kind=OpKind.PLUGIN_OP,
                params={"action": "revert", "target_sha": sha},
                message=f"revert to {sha.removeprefix('sha256:')[:12]}",
            ) as op:
                op.set_output(past_bytes)
        except Exception as e:
            QMessageBox.warning(self, "Revert", f"Could not record revert commit: {e}")
            return

        # Notify the host so it can reload the open document.
        self.reverted_to_state.emit(sha, past_bytes)
        QMessageBox.information(
            self,
            "Reverted",
            f"Reverted to commit {sha.removeprefix('sha256:')[:12]}.\n\n"
            f"A new commit was added on the active branch.\n"
            f"The open document has been reloaded.",
        )
        self.refresh()

    def _on_checkout_clicked(self) -> None:
        """Materialize the selected commit's state to a chosen file.

        Pure read-only operation: does NOT touch history, refs, the
        active document, or current.swc.
        """
        sha = self._current_selection_sha()
        if not sha:
            return
        short = sha.removeprefix("sha256:")[:12]
        default = str(self._swc_path.parent / f"{self._swc_path.stem}_{short}.swc")
        from PySide6.QtWidgets import QFileDialog  # noqa: PLC0415
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Checkout commit to file",
            default,
            "SWC Files (*.swc);;All Files (*)",
        )
        if not path:
            return
        try:
            from swcstudio.cli.history_cli import _materialize_state_at  # noqa: PLC0415
            body = _materialize_state_at(self._hist, sha)
            Path(path).write_bytes(body)
        except Exception as e:
            QMessageBox.warning(self, "Checkout", f"Could not check out: {e}")
            return
        QMessageBox.information(self, "Checkout", f"Wrote {path}")

    def _on_checkpoint_clicked(self) -> None:
        sha = self._current_selection_sha()
        if not sha:
            return
        label, ok = QInputDialog.getText(
            self, "Checkpoint label",
            "Label (e.g. pre_paper):",
        )
        if not ok or not label.strip():
            return
        try:
            # Reuse the CLI's materialization helper so behavior matches exactly.
            from swcstudio.cli.history_cli import _materialize_state_at
            body = _materialize_state_at(self._hist, sha)
        except Exception as e:
            QMessageBox.warning(self, "Checkpoint", f"Could not materialize: {e}")
            return
        out_dir = (history_dir_for(self._swc_path)).parent
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label.strip())
        out_path = out_dir / f"{self._swc_path.stem}_{safe}.swc"
        out_path.write_bytes(body)
        QMessageBox.information(self, "Checkpoint", f"Wrote {out_path}")

    def _on_tag_clicked(self) -> None:
        sha = self._current_selection_sha()
        if not sha:
            return
        name, ok = QInputDialog.getText(self, "Tag commit", "Tag name:")
        if not ok or not name.strip():
            return
        from swcstudio.core.provenance import TagExistsError, RefError
        try:
            create_tag(self._hist, name.strip(), sha)
        except (TagExistsError, RefError) as e:
            QMessageBox.warning(self, "Tag commit", str(e))
            return
        QMessageBox.information(
            self, "Tag commit",
            f"Tagged {sha[:19]} as {name.strip()!r}.",
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _current_selection_sha(self) -> str | None:
        items = self._table.selectedItems()
        if not items:
            return None
        # All items in a row share the same UserRole sha (set on col 0).
        row = items[0].row()
        cell = self._table.item(row, 0)
        if cell is None:
            return None
        sha = cell.data(Qt.UserRole)
        return str(sha) if sha else None


def open_history_dialog(parent: Optional[QWidget], swc_path: str | Path) -> None:
    """Convenience: open the history panel as a modal dialog.

    The main window can add a single ``View → History…`` action
    that calls this. No other GUI wiring is required.

    If ``parent`` has a public method ``reload_swc_from_disk(path)``,
    the panel's Revert action wires through it so the GUI's open
    document refreshes after a revert. Without such a method, the
    revert still lands in .history/ + current.swc; the user just has
    to close and reopen the file to see the reverted state.
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"History — {Path(swc_path).name}")
    dlg.resize(1100, 600)
    layout = QVBoxLayout(dlg)
    panel = HistoryPanel(swc_path, parent=dlg)
    layout.addWidget(panel)

    # Wire revert to a host reload method if available.
    reload_method = getattr(parent, "reload_swc_from_disk", None) if parent else None
    if callable(reload_method):
        # _target_sha, _body: the bytes are already on disk via current.swc;
        # reload from disk so the GUI picks up the new state + @PROV header.
        panel.reverted_to_state.connect(lambda _sha, _body: reload_method(str(swc_path)))

    try:
        dlg.exec()
    finally:
        if panel._hist.exists():
            archive_history_dir(panel._hist, panel._swc_path, remove_dir=True)
