from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SINGLE_SOMA = REPO_ROOT / "data" / "single-soma.swc"


class GUISmokeTests(unittest.TestCase):
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
