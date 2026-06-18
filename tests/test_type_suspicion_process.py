from __future__ import annotations

import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swcstudio.core.swc_io import parse_swc_text_preserve_tokens
from swcstudio.gui.auto_typing_workers import (
    _AutoLabelBatchWorker,
    _AutoLabelFileWorker,
    _TypeSuspicionWorker,
)
from swcstudio.core.auto_typing.types import BatchOptions


FIXTURE = Path(__file__).parent / "fixtures" / "single-soma.swc"


class TypeSuspicionProcessTests(unittest.TestCase):
    def test_single_file_auto_label_runs_in_isolated_process(self) -> None:
        result = _AutoLabelFileWorker(
            1,
            str(FIXTURE),
            BatchOptions(),
            None,
        )._run_isolated()
        self.assertGreater(result.nodes_total, 0)

    def test_batch_auto_label_runs_in_isolated_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy2(FIXTURE, Path(tmp) / FIXTURE.name)
            result = _AutoLabelBatchWorker(
                1,
                tmp,
                BatchOptions(),
                None,
            )._run_isolated()
        self.assertEqual(result.files_processed, 1)

    def test_inference_runs_in_isolated_process(self) -> None:
        df = parse_swc_text_preserve_tokens(FIXTURE.read_text(encoding="utf-8"))
        issues = _TypeSuspicionWorker(1, df)._run_isolated()
        self.assertIsInstance(issues, list)

    def test_source_install_uses_python_module_worker(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            command = _TypeSuspicionWorker._subprocess_command("in.pkl", "out.pkl")
        self.assertEqual(
            command,
            [
                sys.executable,
                "-m",
                "swcstudio.gui.type_suspicion_process",
                "in.pkl",
                "out.pkl",
            ],
        )

    def test_frozen_app_uses_internal_worker_switch(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            command = _TypeSuspicionWorker._subprocess_command("in.pkl", "out.pkl")
        self.assertEqual(
            command,
            [
                sys.executable,
                "--swcstudio-type-suspicion-worker",
                "in.pkl",
                "out.pkl",
            ],
        )

    def test_auto_label_worker_commands_cover_source_and_frozen_apps(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            source_command = _AutoLabelFileWorker._subprocess_command(
                "request.pkl", "out.pkl"
            )
        self.assertEqual(
            source_command,
            [
                sys.executable,
                "-m",
                "swcstudio.gui.auto_label_process",
                "request.pkl",
                "out.pkl",
            ],
        )
        with patch.object(sys, "frozen", True, create=True):
            frozen_command = _AutoLabelFileWorker._subprocess_command(
                "request.pkl", "out.pkl"
            )
        self.assertEqual(
            frozen_command,
            [
                sys.executable,
                "--swcstudio-auto-label-worker",
                "request.pkl",
                "out.pkl",
            ],
        )


if __name__ == "__main__":
    unittest.main()
