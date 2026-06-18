from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"
SINGLE_SOMA = FIXTURE_DIR / "single-soma.swc"


class GUISmokeTests(unittest.TestCase):
    def test_close_path_suggestion_does_not_create_output_directory(self) -> None:
        from swcstudio.gui.main_window import _suggest_closed_output_path

        with tempfile.TemporaryDirectory(prefix="swcstudio-close-path-") as tmp:
            source = Path(tmp) / "cell.swc"
            source.write_text("1 1 0 0 0 1 -1\n", encoding="utf-8")

            suggested = _suggest_closed_output_path(
                source,
                timestamp="20260617_120000",
            )

            self.assertEqual(
                suggested,
                source.parent / "cell_closed_20260617_120000.swc",
            )
            self.assertFalse((source.parent / "cell_swc_studio_output").exists())
            self.assertFalse(suggested.exists())

    def test_history_panel_refreshes_after_archive_rewrite(self) -> None:
        script = textwrap.dedent(
            """
            import json
            import os
            import tempfile
            from pathlib import Path

            os.environ['QT_QPA_PLATFORM'] = 'offscreen'

            from PySide6.QtWidgets import QApplication, QMessageBox
            from swcstudio.core.provenance import OpKind, ensure_schema, open_index, tracked_op
            from swcstudio.gui.history_panel import HistoryPanel

            base = b"# test\\n1 1 0 0 0 1 -1\\n2 3 1 0 0 0.5 1\\n"
            type_edit = base.replace(b"2 3 1", b"2 2 1")
            radius_edit = type_edit.replace(b"0.5 1", b"0.8 1")

            app = QApplication([])
            with tempfile.TemporaryDirectory(prefix="swcstudio-history-refresh-") as tmp:
                swc = Path(tmp) / "cell.swc"
                swc.write_bytes(base)
                with tracked_op(swc, kind=OpKind.SET_TYPE, params={}, message="first") as op:
                    op.set_output(type_edit)

                panel = HistoryPanel(swc)
                assert panel._ops_tree.topLevelItemCount() == 1
                assert panel._ops_tree.topLevelItem(0).text(0) == "op-1"

                with tracked_op(swc, kind=OpKind.SET_RADIUS, params={}, message="second") as op:
                    op.set_output(radius_edit)

                assert not panel._hist.exists()
                panel.refresh()
                assert panel._hist.exists()
                assert panel._ops_tree.topLevelItemCount() == 2
                assert panel._ops_tree.topLevelItem(0).text(0) == "op-2"
                assert panel._ops_tree.topLevelItem(1).text(0) == "op-1"

                panel._ops_tree.setCurrentItem(panel._ops_tree.topLevelItem(0))
                QMessageBox.question = staticmethod(
                    lambda *_args, **_kwargs: QMessageBox.Yes
                )
                QMessageBox.information = staticmethod(
                    lambda *_args, **_kwargs: QMessageBox.Ok
                )
                QMessageBox.warning = staticmethod(
                    lambda *_args, **_kwargs: QMessageBox.Ok
                )
                panel._on_revert_clicked()
                assert panel._ops_tree.topLevelItem(0).text(0) == "op-3"

                conn = open_index(panel._hist)
                ensure_schema(conn)
                latest = conn.execute(
                    "SELECT params_json FROM ops ORDER BY op_id DESC LIMIT 1"
                ).fetchone()
                conn.close()
                params = json.loads(latest["params_json"])
                assert params["reverted_from_operation"] == "op-2"
                assert params["restore_mode"] == "Before selected operation"
                panel.close()
                app.processEvents()
            """
        )

        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"History refresh subprocess failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_main_window_load_and_tool_switching(self) -> None:
        script = textwrap.dedent(
            f"""
            import os
            import sys
            import time
            from pathlib import Path

            os.environ['QT_QPA_PLATFORM'] = 'offscreen'

            from PySide6.QtWidgets import QApplication
            from swcstudio.gui.main_window import SWCMainWindow

            app = QApplication([])
            window = SWCMainWindow()

            path = str(Path(r"{SINGLE_SOMA}"))
            window._load_swc(path)

            end = time.time() + 10
            while time.time() < end:
                app.processEvents()
                if (not window._validation_tab.is_running()) and len(getattr(window._validation_tab, "_results_rows", [])) > 0:
                    break
                time.sleep(0.05)

            assert len(window._documents) == 1, len(window._documents)
            assert window._active_document() is not None
            assert len(window._active_document().issues) > 0, len(window._active_document().issues)
            assert len(getattr(window._validation_tab, "_results_rows", [])) > 0
            assert [window._data_tabs.tabText(i) for i in range(window._data_tabs.count())] == ["Issues", "SWC File"]
            assert "single-soma.swc" in window._current_file_label.toolTip()

            expected_control_counts = {{
                "batch": 6,
                "validation": 2,
                "visualization": 1,
                "morphology_editing": 4,
                "geometry_editing": 2,
            }}
            for feature_name, expected_tabs in expected_control_counts.items():
                window._activate_feature(feature_name)
                app.processEvents()
                assert window._active_tool == feature_name, (feature_name, window._active_tool)
                assert window._control_tabs.count() == expected_tabs, (feature_name, window._control_tabs.count())

            assert len(window._runtime_log_lines) > 0

            doc = window._active_document()
            assert doc is not None
            duplicate_runs = []
            window._start_type_suspicion_worker = (
                lambda *_args, **_kwargs: duplicate_runs.append(True)
            )
            doc.pending_type_suspicion_issues = []
            window._on_validation_report_ready(doc.validation_report or {{}})
            assert duplicate_runs == [], duplicate_runs
            assert any(
                "reused the applied auto-label result" in line
                for line in window._runtime_log_lines
            )

            sys.stdout.write("GUI_SMOKE_OK\\n")
            sys.stdout.flush()
            os._exit(0)
            """
        )

        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=(
                "GUI smoke subprocess failed.\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
